"""Attach private FSMP systems after all appearance exports.

Hidden skinned collision proxies use the avatar's weighted body vertices.
FSMP contacts use mesh surfaces; XML provides explicit rotational inertia.
"""
import json
import logging
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from scipy.spatial import ConvexHull, QhullError
from scipy.spatial.transform import Rotation

from custom_skeleton import NifFile, matrix, rigid_buffer, nifly
from settings import load_settings
from physics_rig import read_system
from physics_frames import shift_frames, translation
from pyn.pynifly import NiStringExtraData
from pyn.structs import TransformBuf

LINK = 'HDT Skinned Mesh Physics Object'
PROXY = 'V2SCollision_Body'
ARM_PROXY = 'V2SCollision_ArmCloth'
SECONDARY_PROXY = 'V2SCollision_Secondary'
SPRING_PROXY = 'V2SCollision_Spring'
GRAVITY = 9.8 / .01425  # FSMP scaleSkyrim: game units per second squared
MASS = .1
INERTIA_MULTIPLIER = 5.  # Increase geometric inertia without increasing spring torque
CONTACT_MARGIN = .4
TRIANGLE_MARGIN = .35


def contact_patches(base, names):
    """Split rigid contact owners into shapes the NIF skin can address; the first keeps the base name."""
    from nif_limits import SHAPE_BONE_LIMIT
    names = sorted(names)
    return [(base if index == 0 else f'{base}_{index:03}', names[start:start+SHAPE_BONE_LIMIT])
            for index, start in enumerate(range(0, len(names), SHAPE_BONE_LIMIT))]


def is_contact_patch(name, base):
    return name == base or (name.startswith(base+'_') and name[len(base)+1:].isdigit())


def contact_spring(info):
    """The VRM contact values of a mover: its own, or those borrowed_colliders gave it."""
    return info.get('spring') or info.get('borrowed')


def contact_margin(info):
    spring = contact_spring(info)
    return max(CONTACT_MARGIN, round(spring['hit_radius']*70, 3)) if spring else CONTACT_MARGIN


def contact_classes(base, owners, bones, contact_groups=None, helpers=()):
    """Partition patch owners by (margin, collider groups): [(patch base, margin, groups, owners)].

    Only the default class keeps the plain base name. A helper never touches anything.
    """
    classes = {}
    for name in sorted(owners):
        key = ((CONTACT_MARGIN, ()) if name in helpers else
               (contact_margin(bones[name]), tuple((contact_groups or {}).get(name, ()))))
        classes.setdefault(key, []).append(name)
    default = classes.pop((CONTACT_MARGIN, ()), None)
    result = [(base, CONTACT_MARGIN, (), default)] if default else []
    return result + [(f'{base}_S{index}', *key, classes[key]) for index, key in enumerate(sorted(classes), 1)]


def system_tag(settings, nif_path):
    return f'V2SBody_{settings.mod_id.lower()}_{Path(nif_path).stem}'


def spring_tag(collision_tag, group):
    return f'{collision_tag}_g{group}'


def segment_distance(point, head, tail):
    point, head = np.asarray(point), np.asarray(head)
    if tail is None:
        return float(np.linalg.norm(point-head))
    axis = np.asarray(tail)-head
    position = np.clip(np.dot(point-head, axis) / max(np.dot(axis, axis), 1e-12), 0, 1)
    return float(np.linalg.norm(point-head-position*axis))


def collider_groups(colliders):
    result = {}
    for collider in colliders:
        result.setdefault(collider['group'], []).append(collider)
    return result


def collider_depth(colliders):
    """Triangle penetration letting a group push out points that went inside it.

    FSMP ignores a point deeper behind a triangle than this, and the default 1 leaves a
    hollow shell. It keeps only the deepest contact per bone pair, so a point must never be
    deeper behind a far triangle than behind the one it entered through: the depth stops at
    the radius of the thinnest surface, where the far side becomes the nearer one.
    """
    return round(max(1., min(c['radius'] for c in colliders) - TRIANGLE_MARGIN), 3)


def contact_collider_groups(bones, contacts, groups):
    """Return ({bone: groups it collides with}, {bone: groups it starts inside}).

    A sphere starting inside a closed mesh gets an inward contact, so such a bone
    drops that group. It keeps the body tag.
    """
    kept, inside = {}, {}
    for name, point in contacts.items():
        spring = contact_spring(bones[name])
        if not spring:
            continue
        reach = spring['hit_radius']*70
        for group in spring['groups']:
            if group not in groups:
                continue
            start_inside = any(segment_distance(point, c['head'], c['tail']) < c['radius']+reach
                               for c in groups[group])
            (inside if start_inside else kept).setdefault(name, []).append(group)
    return kept, inside


def bone_inertia(radius, mass=MASS):
    """FSMP 4.1.1 passes XML inertia directly to Bullet, in mass*units².

    Shape radius does not automatically calculate or divide this value.
    Use an isotropic sphere approximation to avoid orientation-dependent bias.
    """
    return .4 * mass * radius**2 * INERTIA_MULTIPLIER


def rest_spring(radius, stiffness=1., mass=MASS):
    geometric_inertia = .4 * mass * radius**2
    omega = 2 * np.pi * .65 * np.sqrt(stiffness)
    return geometric_inertia * omega**2


def spring_joint(spring, stiffness, radius, mass, length):
    """(spring multiplier for joint_profile, gravity-factor) with VRM's droop at the preset's speed.

    VRM's steady direction gives tan(a) ~= (gravity/stiffness)*sin(tilt), so the joint spring
    and the scaled gravity torque keep that ratio. Their sum stays the preset spring plus full
    gravity, the restoring torque of a mover without VRM settings: lowering gravity alone left
    hair swinging about three times slower. Stiffness 0 hangs straight down under full gravity.
    """
    gravity_torque = mass * GRAVITY * length
    if spring['stiffness'] <= 0 or length <= .001:
        return (0. if spring['stiffness'] <= 0 else stiffness), 1.
    ratio = spring['gravity'] / spring['stiffness']
    unit = rest_spring(radius, 1., mass)
    joint = (rest_spring(radius, stiffness, mass) + gravity_torque) / (1 + ratio)
    if joint * ratio > gravity_torque:  # gravity-factor cannot exceed 1; keep the droop instead
        joint = gravity_torque / ratio
    return joint / unit, float(joint * ratio / gravity_torque)


def joint_profile(com, radius, global_matrix, stiffness=1., mass=MASS, gravity_factor=1.):
    """Geometry-scaled restoring torque and near-critical pendulum damping.

    Z follows the influenced surface, X permits falling towards gravity.
    Restrict sideways swing and axial twist without freezing horizontal cloth.
    Angular coefficients have inertia units; a constant .6 cannot damp both
    tiny hair tips and long sleeves. Include the pivot's parallel-axis inertia.
    """
    length = float(np.linalg.norm(com))
    z = np.asarray(com) / length if length > .001 else np.array([0., 0., 1.])
    gravity = np.asarray(global_matrix)[:3, :3].T @ np.array([0., 0., -1.])
    y = gravity - z * np.dot(gravity, z)
    if np.linalg.norm(y) < .001:
        axis = np.eye(3)[np.argmin(np.abs(z))]
        y = axis - z * np.dot(axis, z)
    y /= np.linalg.norm(y)
    basis = np.column_stack((np.cross(y, z), y, z))
    inertia = bone_inertia(radius, mass)
    lever = basis.T @ np.asarray(com)
    pivot_inertia = inertia + mass * (length**2 - lever**2)
    spring = np.full(3, rest_spring(radius, stiffness, mass))
    # Gravity supplies a restoring torque as a hanging chain moves; damping
    # must account for that too, not only the deliberately gentle rest spring.
    gravity_torque = mass * GRAVITY * gravity_factor * length * np.array([1., 1., 0.])
    damping = 2 * 1.1 * np.sqrt(pivot_inertia * (spring + gravity_torque))
    return basis, spring, damping


def vector(parent, tag, value):
    return ET.SubElement(parent, tag, {a: f'{float(n):.7f}' for a, n in zip('xyz', value)})


def scalar(parent, tag, value):
    ET.SubElement(parent, tag).text = str(value)


def transform(parent, tag, origin):
    vector(ET.SubElement(parent, tag), 'origin', origin)


def local_points(points, global_matrix):
    inverse = np.linalg.inv(global_matrix)
    return np.asarray(points) @ inverse[:3, :3].T + inverse[:3, 3]


def weighted_points(nif, shape_filter=None, minimum_weight=.001):
    result = {}
    for shape in nif.shapes:
        if shape.name.startswith(('V2SCollision_', 'V2SOutline_')):
            continue
        if shape_filter is not None and not shape_filter(shape):
            continue
        points = np.asarray(shape.verts)
        value = matrix(shape.transform)
        points = points @ value[:3, :3].T + value[:3, 3]
        for name, weights in shape.bone_weights.items():
            indices = [v for v, w in weights if w > minimum_weight]
            if indices:
                result.setdefault(name, []).extend(points[indices].tolist())
    return result


def skin_samples(nif):
    """Parallel points/weights, excluding generated contact geometry."""
    points, weights = {}, {}
    for shape in nif.shapes:
        if shape.name.startswith(('V2SCollision_', 'V2SOutline_')):
            continue
        value = matrix(shape.transform)
        vertices = np.asarray(shape.verts) @ value[:3, :3].T + value[:3, 3]
        for name, pairs in shape.bone_weights.items():
            for vertex, weight in pairs:
                if weight > .001:
                    points.setdefault(name, []).append(vertices[vertex].tolist())
                    weights.setdefault(name, []).append(weight)
    return points, weights


def arm_cloth_bones(bones, cloth_components, co_influences=()):
    """Identify sleeve movers from humanoid ancestry and ownership, not names."""
    result = set()
    for name, info in bones.items():
        if not info['dynamic'] or not set(info['components']) <= cloth_components:
            continue
        anchor = info['parent']
        while anchor in bones:
            anchor = bones[anchor]['parent']
        if any(anchor.startswith(f'NPC {side} {part} ') for side in ('L', 'R')
               for part in ('UpperArm', 'Forearm', 'Hand')):
            result.add(name)
    # A shawl or shared cloth bone can influence the same sleeve vertices while
    # being anchored to the spine. Its contacts must use the same physical path.
    eligible = {n for n, i in bones.items() if i['dynamic'] and
                set(i['components']) <= cloth_components}
    pending = [set(group) & eligible for group in co_influences]
    while pending:
        remainder = []
        before = set(result)
        for group in pending:
            if group & result:
                result.update(group)
            else:
                remainder.append(group)
        if result == before:
            break
        pending = remainder
    return result


def skin_co_influences(nif):
    """Bones affecting the same visual vertex; no generated proxy feedback."""
    groups = set()
    for shape in nif.shapes:
        if shape.name.startswith(('V2SCollision_', 'V2SOutline_')):
            continue
        vertices = {}
        for name, pairs in shape.bone_weights.items():
            for vertex, weight in pairs:
                if weight > .001:
                    vertices.setdefault(vertex, set()).add(name)
        groups.update(frozenset(names) for names in vertices.values() if len(names) > 1)
    return groups


def collision_hulls(mesh_dir, appearance, globals_, body_nodes=()):
    points = {}
    for part in appearance['components']:
        combined = part['id'] == 'appearance'
        if part['role'] != 'body' and part['id'] != 'face' and not combined:
            continue
        with NifFile(str(mesh_dir / part['file'])) as nif:
            def is_body(shape):
                return not combined or any(shape.name.startswith(f'VRMNode_{n:05}') for n in body_nodes)

            for name, values in weighted_points(nif, is_body, minimum_weight=.2).items():
                if name.startswith('NPC '):
                    points.setdefault(name, []).extend(values)
    result = {}
    for name, values in points.items():
        values = local_points(values, globals_[name])
        try:
            hull = ConvexHull(values)
        except QhullError:
            continue
        surface = values[hull.vertices]
        directions = np.array([[x, y, z] for x in (-1, 0, 1) for y in (-1, 0, 1)
                               for z in (-1, 0, 1) if (x, y, z) != (0, 0, 0)])
        indices = np.unique(np.argmax(surface @ directions.T, axis=0))
        result[name] = surface[indices].tolist()
    return result


def cloth_component_ids(appearance):
    return {p['id'] for p in appearance['components'] if p['role'] == 'garment'} | {'appearance_cloth'}


def arm_side(name):
    return next((s for s in ('L', 'R') if name.startswith(f'NPC {s} ') and
                 any(p in name for p in ('UpperArm', 'Forearm', 'Hand'))), None)


def borrowed_colliders(bones, movers, cloth_components):
    """{mover: hit_radius and groups} for cloth a VRM rigged but left out of its springs.

    An apron swinging among skirt chains would otherwise pass through the legs the
    skirt is kept off. It takes the contact values of the nearest chain of its own
    component, and only those: its joints stay on the preset without VRM settings.
    """
    def position(name):
        return np.asarray(bones[name]['matrix'])[:3, 3]

    covered = [n for n in movers if set(bones[n]['components']) <= cloth_components and
               (bones[n].get('spring') or {}).get('groups')]
    result = {}
    for name in movers:
        info = bones[name]
        if info.get('spring') or not set(info['components']) <= cloth_components:
            continue
        near = [n for n in covered if bones[n]['components'] == info['components']]
        if near:
            spring = bones[min(near, key=lambda n: np.linalg.norm(position(n)-position(name)))]['spring']
            result[name] = {'hit_radius': spring['hit_radius'], 'groups': spring['groups']}
    return result


def protect_attachments(bones, samples, hulls, globals_, cloth_components):
    """Keep garment attachment roots and nearby arm sleeves in animated FK.

    Proximity uses the actual avatar's arm hulls and positively weighted skin,
    never source bone/mesh names. Extend only the fixed prefix of a chain:
    pinning a distal node below a simulated parent would still move its cuff.
    VRM also rotates the first joint of a spring, so a root off the arm stays
    free when it has colliders to keep it off the body, its spring's or borrowed ones.
    A pinned fold carrying cloth down to the thighs would otherwise stay in the legs.
    """
    result = {n: dict(i) for n, i in bones.items()}
    protected = {}
    if not cloth_components:
        return result, protected
    world_hulls = {}
    for name, local in hulls.items():
        value = globals_[name]
        points = np.asarray(local) @ value[:3, :3].T + value[:3, 3]
        world_hulls[name] = ConvexHull(points)
    height = float(np.ptp(np.concatenate([h.points for h in world_hulls.values()]), axis=0)[2]) if world_hulls else 0.
    tolerance = height * .04

    def classify(name):
        info = result[name]
        parent = info['parent']
        if parent in result and parent not in visited:
            classify(parent)
        visited.add(name)
        if not set(info['components']) <= cloth_components:
            return
        if parent not in result:
            if not (contact_spring(info) or {}).get('groups') or arm_side(parent):
                info['dynamic'] = False
                protected[name] = 'garment attachment root'
            return
        if result[parent]['dynamic'] or not info['dynamic'] or name not in samples:
            return
        anchor = parent
        while anchor in result:
            if result[anchor]['dynamic']:
                return  # an unweighted kinematic helper may still inherit a mover
            anchor = result[anchor]['parent']
        side = arm_side(anchor)
        if side is None or not world_hulls:
            return
        arm = [h.equations for n, h in world_hulls.items() if arm_side(n) == side]
        if not arm:
            return
        points = np.asarray(samples[name])
        # Membership in outward-offset hull planes is a conservative proximity
        # region; use the 90th percentile so a stray tiny influence is not a pin.
        proximity = np.min([(points @ p[:, :3].T + p[:, 3]).max(axis=1) for p in arm], axis=0)
        if float(np.quantile(proximity, .9)) <= tolerance:
            info['dynamic'] = False
            protected[name] = 'arm-adjacent fixed attachment prefix'

    visited = set()
    for name in result:
        if name not in visited:
            classify(name)
    return result, protected


def system_xml(bones, samples, hulls, stiffness=1., mesh_names=(), collision_tag='V2SBody',
               sample_weights=None, arm_contacts=(), secondary_contacts=(), noncontact_helpers=(),
               contact_groups=None, collider_bones=(), collider_depths=None):
    root = ET.Element('system', xmlns='FSMP-Validator')
    scalar(ET.SubElement(root, 'bone-default'), 'mass', 0)
    colliders = sorted((set(hulls) | set(collider_bones)) - set(bones))
    anchors = sorted({i['parent'] for i in bones.values()} - set(bones))
    for name in sorted(set(colliders) | set(anchors)):
        bone = ET.SubElement(root, 'bone', name=name)
        scalar(bone, 'mass', 0)
    profiles = {}
    for name, info in bones.items():
        depth, parent = 0, info['parent']
        while parent in bones and bones[parent]['dynamic']:
            depth += 1
            parent = bones[parent]['parent']
        # A lighter distal chain puts less load on upstream joints and reduces
        # stretching at the ordinary 16-iteration runtime solver setting.
        mass = max(.0025, MASS * .6**depth)
        bone = ET.SubElement(root, 'bone', name=name)
        scalar(bone, 'mass', mass if info['dynamic'] else 0)
        if not info['dynamic']:
            continue
        points = local_points(samples.get(name, [np.asarray(info['matrix'])[:3, 3]]), info['matrix'])
        weights = sample_weights.get(name) if sample_weights else None
        com = np.average(points, axis=0, weights=weights)
        # This sphere describes the effective geometry, not contact surfaces.
        # FSMP does not derive inertia from the shape; serialize it explicitly.
        # Include the pivot-to-CoM lever. A tiny tip sphere on a long joint
        # lever can rotate explosively while the positional constraint catches
        # up, especially at ordinary runtime solver iteration counts.
        radius = max(.65, float(np.linalg.norm(com)),
                     float(np.sqrt(np.average(np.square(points-com).sum(axis=1), weights=weights))))
        transform(bone, 'centerOfMassTransform', [0, 0, 0] if info.get('centred_node') else com)
        scalar(bone, 'linearDamping', .85)
        scalar(bone, 'angularDamping', .95)
        spring = info.get('spring')
        if spring:
            joint_stiffness, factor = spring_joint(spring, stiffness, radius, mass, float(np.linalg.norm(com)))
            scalar(bone, 'gravity-factor', f'{factor:.9f}')
            profiles[name] = joint_profile(com, radius, info['matrix'], joint_stiffness, mass, factor)
        else:
            scalar(bone, 'gravity-factor', 1)
            profiles[name] = joint_profile(com, radius, info['matrix'], stiffness, mass)
        scalar(bone, 'wind-factor', 0)
        vector(bone, 'inertia', [bone_inertia(radius, mass)] * 3)
        scalar(ET.SubElement(bone, 'shape', type='sphere'), 'radius', round(radius, 6))
    for name, info in bones.items():
        if not info['dynamic']:
            continue
        joint = ET.SubElement(root, 'generic-constraint', bodyA=info['parent'], bodyB=name)
        # frameInB is bone-local. A centred node has identity rigToLocal and
        # an explicit negative node-centre frame to retain the source pivot.
        pivot = -np.asarray(info['node_centre']) if info.get('centred_node') else [0, 0, 0]
        transform(joint, 'frameInB', pivot)
        basis, spring, damping = profiles[name]
        ET.SubElement(joint.find('frameInB'), 'basis',
                      {a: f'{n:.9f}' for a, n in zip('xyzw', Rotation.from_matrix(basis).as_quat())})
        vector(joint, 'linearLowerLimit', [0, 0, 0])
        vector(joint, 'linearUpperLimit', [0, 0, 0])
        vector(joint, 'angularLowerLimit', [-1.7, -1.1, -.25])
        vector(joint, 'angularUpperLimit', [1.7, 1.1, .25])
        vector(joint, 'angularStiffness', spring)
        vector(joint, 'angularDamping', damping)
        scalar(joint, 'enableLinearSprings', 'false')
        scalar(joint, 'enableAngularSprings', 'true')
        # Retain Bullet's timestep safety caps when chains share moving bodies.
        scalar(joint, 'angularStiffnessLimited', 'true')
        scalar(joint, 'springDampingLimited', 'true')
    used_groups = sorted({g for groups in (contact_groups or {}).values() for g in groups})
    if hulls or used_groups:
        body_tags = [collision_tag] if hulls else []
        generated = body_tags + [spring_tag(collision_tag, g) for g in used_groups]
        if hulls:
            proxy = ET.SubElement(root, 'per-triangle-shape', name=PROXY)
            scalar(proxy, 'margin', TRIANGLE_MARGIN)
            scalar(proxy, 'tag', collision_tag)
            for tag in generated:
                scalar(proxy, 'no-collide-with-tag', tag)
        for group in used_groups:
            shape = ET.SubElement(root, 'per-triangle-shape', name=f'{SPRING_PROXY}{group}')
            scalar(shape, 'margin', TRIANGLE_MARGIN)
            if collider_depths:
                scalar(shape, 'penetration', collider_depths[group])
            scalar(shape, 'tag', spring_tag(collision_tag, group))
            # These surfaces are wider than the body; other actors' cloth must not see them.
            scalar(shape, 'shared', 'internal')
            for tag in generated:
                scalar(shape, 'no-collide-with-tag', tag)
        for name in mesh_names if hulls else ():
            shape = ET.SubElement(root, 'per-vertex-shape', name=name)
            scalar(shape, 'margin', CONTACT_MARGIN)
            scalar(shape, 'can-collide-with-tag', collision_tag)
            # Mixed meshes may also contain waist cloth. Retain those contacts,
            # but never feed their blended sleeve vertices back into sleeve rigs.
            for bone in sorted(set(arm_contacts) | set(secondary_contacts)):
                ET.SubElement(shape, 'weight-threshold', bone=bone).text = '1'
        for base, owners in ((ARM_PROXY, arm_contacts), (SECONDARY_PROXY, secondary_contacts)):
            for patch_base, margin, groups, members in contact_classes(base, owners, bones, contact_groups,
                                                                       noncontact_helpers):
                for patch, chunk in contact_patches(patch_base, members):
                    shape = ET.SubElement(root, 'per-vertex-shape', name=patch)
                    scalar(shape, 'margin', margin)
                    for tag in body_tags + [spring_tag(collision_tag, g) for g in groups]:
                        scalar(shape, 'can-collide-with-tag', tag)
                    for name in sorted(set(noncontact_helpers) & set(chunk)):
                        ET.SubElement(shape, 'weight-threshold', bone=name).text = '1'
    return root


def contact_surface_points(bones, samples, weights, hulls, globals_, preserve_clear_centres=()):
    """A rigid segment's CoM may be inside a wrapped sleeve or curved hair.

    Select a real strongly weighted surface sample near the CoM, preferring
    clearance from all body hulls. Never let a weak stray influence choose it.
    Unweighted chain helpers have no contact surface and are excluded in XML.
    The clearance covers the bone's contact margin and the triangle margin.
    A mover with VRM colliders is tested where VRM tests it, at its spring tail,
    unless that point starts inside the body.
    """
    equations = []
    for name, points in hulls.items():
        value = globals_[name]
        world = np.asarray(points) @ value[:3, :3].T + value[:3, 3]
        equations.append(ConvexHull(world).equations)
    result = {}
    for name, info in bones.items():
        if not info['dynamic'] or name not in samples:
            continue
        values = np.asarray(samples[name])
        w = np.asarray(weights[name])
        values = values[w >= min(.2, w.max()*.5)]
        centre = (np.asarray(info['matrix']) @ np.r_[info['node_centre'], 1])[:3]
        clearance = contact_margin(info) + TRIANGLE_MARGIN + .05

        def clear_of_body(point):
            return all(np.max(p[:, :3] @ point + p[:, 3]) > clearance for p in equations)

        tail = info.get('spring_tail')
        if tail is not None and (info.get('spring') or {}).get('groups') and clear_of_body(np.asarray(tail)):
            result[name] = list(tail)
            continue
        if name in preserve_clear_centres and clear_of_body(centre):
            result[name] = centre.tolist()
            continue
        clear = np.ones(len(values), dtype=bool)
        for planes in equations:
            clear &= np.max(values @ planes[:, :3].T + planes[:, 3], axis=1) > clearance
        if clear.any():
            values = values[clear]
        result[name] = values[np.argmin(np.square(values-centre).sum(axis=1))].tolist()
    return result


def add_rigid_collision_proxy(nif, skeleton, names, proxy_name, positions=None):
    """Small rigid contact patches on a secondary surface, one bone per patch.

    A blended visual vertex cannot deliver its full contact to every influencing
    rigid body. That feedback can coil long sleeves even with stationary anchors.
    These non-rendered patches keep contact torque local to the physical segment.
    """
    if not names:
        return
    patches = dict(contact_patches(proxy_name, names))
    existing = [s for s in nif.shapes if is_contact_patch(s.name, proxy_name)]
    if existing:
        if ({s.name for s in existing} != set(patches) or
                any(set(s.bone_names) != set(patches[s.name]) for s in existing)):
            raise ValueError('Secondary contact proxy ownership changed; regenerate appearance')
        if positions:
            for shape in existing:
                for name, pairs in shape.bone_weights.items():
                    centre = positions.get(name, matrix(skeleton.nodes[name].global_transform)[:3, 3])
                    if any(np.linalg.norm(np.asarray(shape.verts[v])-centre) > .003 for v, _ in pairs):
                        raise ValueError('Contact surface changed; regenerate appearance: '+name)
        return
    for patch, owners in patches.items():
        add_contact_patch_shape(nif, skeleton, owners, patch, proxy_name, positions)


def add_contact_patch_shape(nif, skeleton, names, proxy_name, base, positions):
    vertices, triangles, weights = [], [], {}
    for name in sorted(names):
        start = len(vertices)
        value = matrix(skeleton.nodes[name].global_transform)
        # Nondegenerate tiny triangles keep the NIF a valid skinned mesh.
        # FSMP uses their three per-vertex spheres, not the triangles themselves.
        patch = np.array([[0, 0, 0], [.001, 0, 0], [0, .001, 0]])
        centre = positions.get(name, value[:3, 3]) if positions else value[:3, 3]
        vertices.extend(map(tuple, (patch @ value[:3, :3].T + centre).tolist()))
        triangles.append((start, start+1, start+2))
        weights[name] = [(start+i, 1.) for i in range(3)]
    shape = nif.createShapeFromData(proxy_name, vertices, triangles, [(0., 0.)]*len(vertices),
                                    [(0., 0., 1.)]*len(vertices))
    texture = next((s.shader.textures.get('Normal') for s in nif.shapes if not is_contact_patch(s.name, base)
                    and s.shader.textures.get('Normal')), None)
    if texture:
        shape.set_texture('Diffuse', texture)
        shape.set_texture('Normal', texture)
    shape.skin()
    shape.set_global_to_skin(rigid_buffer(np.eye(4)))
    for name, pairs in weights.items():
        node = skeleton.nodes[name]
        if name not in nif.nodes:
            raise ValueError('Secondary contact requires an existing private skin bone: '+name)
        shape.add_bone(name, node.transform, node.parent.name if node.parent else None)
    # PyNifly add_bone resets all prior skin binds; add every owner first.
    for name, pairs in weights.items():
        node = skeleton.nodes[name]
        shape.set_skin_to_bone_xform(name, rigid_buffer(np.linalg.inv(matrix(node.global_transform))))
        shape.setShapeWeights(name, pairs)
    shape.demote_skin_instance()
    nifly.setNodeFlags(shape._handle, 1)


def add_arm_collision_proxy(nif, skeleton, names, positions=None):
    add_rigid_collision_proxy(nif, skeleton, names, ARM_PROXY, positions)


def add_collision_proxy(nif, skeleton, hulls):
    existing = [s for s in nif.shapes if s.name == PROXY]
    if existing:
        if len(existing) != 1:
            raise ValueError('Duplicate FSMP body proxies')
        return
    vertices, triangles, weights = [], [], {}
    for name, local in hulls.items():
        values = np.asarray(local)
        hull = ConvexHull(values)
        value = matrix(skeleton.nodes[name].global_transform)
        points = values @ value[:3, :3].T + value[:3, 3]
        start = len(vertices)
        vertices.extend(map(tuple, points.tolist()))
        # Use outward winding for the triangle collision surface.
        for tri, equation in zip(hull.simplices, hull.equations):
            a, b, c = values[tri]
            if np.dot(np.cross(b-a, c-a), equation[:3]) < 0:
                tri = tri[[0, 2, 1]]
            triangles.append(tuple(int(i)+start for i in tri))
        weights[name] = [(start+i, 1.) for i in range(len(points))]
    add_skinned_proxy(nif, skeleton, PROXY, vertices, triangles, weights)


def capsule_mesh(head, tail, radius, segments=12, rings=3):
    """Closed outward-wound capsule, or sphere when tail is None; returns (vertices, triangles)."""
    head = np.asarray(head, dtype=float)
    top = head if tail is None else np.asarray(tail, dtype=float)
    length = float(np.linalg.norm(top-head))
    z = (top-head)/length if length > 1e-6 else np.array([0., 0., 1.])
    x = np.cross(z, np.eye(3)[np.argmin(np.abs(z))])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    # Latitudes run from the top pole to the bottom pole; a sphere shares one equator.
    angles = np.linspace(0, np.pi/2, rings+1)[1:]
    latitudes = [(top, a) for a in angles] + [(head, np.pi-a) for a in angles[::-1]]
    if length <= 1e-6:
        del latitudes[rings]
    around = np.linspace(0, 2*np.pi, segments, endpoint=False)
    spokes = np.outer(np.cos(around), x) + np.outer(np.sin(around), y)
    vertices = [top + radius*z]
    for centre, angle in latitudes:
        vertices.extend(centre + radius*(np.sin(angle)*spokes + np.cos(angle)*z))
    vertices.append(head - radius*z)
    last = len(vertices)-1
    triangles = []
    for i in range(segments):
        j = (i+1) % segments
        triangles.append((0, 1+i, 1+j))
        triangles.append((last, last-segments+j, last-segments+i))
        for band in range(len(latitudes)-1):
            a, b = 1+band*segments, 1+(band+1)*segments
            triangles.append((a+i, b+i, b+j))
            triangles.append((a+i, b+j, a+j))
    return np.array(vertices), triangles


def spring_mesh(colliders):
    """Triangle-margin surfaces of one collider group, each collider rigid on its NPC bone."""
    vertices, triangles, weights = [], [], {}
    for collider in colliders:
        points, faces = capsule_mesh(collider['head'], collider['tail'],
                                     max(collider['radius']-TRIANGLE_MARGIN, .1))
        start = len(vertices)
        vertices.extend(map(tuple, points.tolist()))
        triangles.extend((a+start, b+start, c+start) for a, b, c in faces)
        weights.setdefault(collider['bone'], []).extend((start+i, 1.) for i in range(len(points)))
    return vertices, triangles, weights


def add_spring_proxy(nif, skeleton, group, colliders):
    name = f'{SPRING_PROXY}{group}'
    vertices, triangles, weights = spring_mesh(colliders)
    existing = [s for s in nif.shapes if s.name == name]
    if existing:
        if (len(existing) != 1 or set(existing[0].bone_names) != set(weights) or
                len(existing[0].verts) != len(vertices)):
            raise ValueError('Spring collider proxy changed; regenerate appearance: '+name)
        return
    add_skinned_proxy(nif, skeleton, name, vertices, triangles, weights)


def add_skinned_proxy(nif, skeleton, proxy_name, vertices, triangles, weights):
    """Hidden per-triangle surface, rigidly weighted to skeleton bones at their rest pose."""
    shape = nif.createShapeFromData(proxy_name, vertices, triangles, [(0., 0.)]*len(vertices),
                                    [(0., 0., 1.)]*len(vertices))
    # Valid private texture paths even if the renderer inspects hidden shapes.
    texture = next((s.shader.textures.get('Normal') for s in nif.shapes if s.name != proxy_name
                    and s.shader.textures.get('Normal')), None)
    if texture:
        shape.set_texture('Diffuse', texture)
        shape.set_texture('Normal', texture)
    shape.skin()

    def ensure(name):
        if name in nif.nodes:
            return
        node = skeleton.nodes[name]
        parent = node.parent
        if parent:
            ensure(parent.name)
        nif.add_node(name, node.transform, nif.nodes[parent.name] if parent else nif.rootNode)

    for name in weights:
        ensure(name)
        node = skeleton.nodes[name]
        shape.add_bone(name, node.transform, node.parent.name if node.parent else None)
    shape.set_global_to_skin(rigid_buffer(np.eye(4)))
    for name, pairs in weights.items():
        value = np.linalg.inv(matrix(skeleton.nodes[name].global_transform))
        scale = float(np.linalg.norm(value[:3, 0]))
        rotation = value[:3, :3] / scale
        if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-4):
            raise ValueError(f'Body collision bind transform contains shear: {name}')
        buf = TransformBuf()
        buf.store(value[:3, 3], rotation.tolist(), (scale, scale, scale))
        shape.set_skin_to_bone_xform(name, buf)
        shape.setShapeWeights(name, pairs)
    shape.demote_skin_instance()
    # Edit only flags: writing the entire generic NiShape buffer to a BSTriShape
    # also overwrites native name/skin IDs. FSMP can still locate hidden shapes.
    nifly.setNodeFlags(shape._handle, 1)


def attach(nif, relative):
    links = list(nif.rootNode.extra_data(name=LINK))
    if links:
        if len(links) != 1:
            raise ValueError('Duplicate FSMP links in NIF')
        if links[0].string_data != relative:
            raise ValueError('Existing FSMP link belongs to a different component; regenerate the NIF')
    else:
        NiStringExtraData.New(nif, name=LINK, string_value=relative, parent=nif.rootNode)
    nif.save()


def load_collider_groups(output):
    path = Path(output) / 'spring-colliders.json'
    return collider_groups(json.loads(path.read_text(encoding='utf8'))) if path.is_file() else {}


def build_physics(output):
    output = Path(output)
    settings = load_settings(output)
    if not settings.physics_enabled:
        return {'enabled': False, 'systems': []}
    mesh_dir = output / 'mod/meshes' / settings.asset_dir
    report = json.loads((output / 'skeleton.json').read_text(encoding='utf8'))
    all_bones = report['physics_bones']
    groups = load_collider_groups(output)
    appearance = json.loads((output / 'appearance.json').read_text(encoding='utf8'))
    with NifFile(str(mesh_dir / 'skeleton.nif')) as skeleton:
        globals_ = {name: matrix(node.global_transform) for name, node in skeleton.nodes.items()}
    source = json.loads((output/'source.json').read_text(encoding='utf8'))
    body_nodes = [p['node'] for p in source['parts'] if p['suggested_role'] == 'body' or
                  ('face' in p['name'].lower() and 'hair' not in p['name'].lower())]
    hulls = collision_hulls(mesh_dir, appearance, globals_, body_nodes)
    cloth_components = cloth_component_ids(appearance)
    paths = [mesh_dir / p['file'] for p in appearance['components']]
    paths += sorted(mesh_dir.glob('fixed_*.nif'))
    prepared, centres = [], {}
    for path in sorted(set(paths)):
        with NifFile(str(path)) as nif:
            samples, sample_weights = skin_samples(nif)
            used = set(samples) & set(all_bones)
            if not any(all_bones[n]['dynamic'] for n in used):
                continue
            for name in list(used):
                parent = all_bones[name]['parent']
                while parent in all_bones:
                    used.add(parent)
                    parent = all_bones[parent]['parent']
            bones = {n: all_bones[n] for n in all_bones if n in used}
            borrowed = borrowed_colliders(bones, [n for n, i in bones.items() if i['dynamic']], cloth_components)
            bones = {n: {**i, **({'borrowed': borrowed[n]} if n in borrowed else {})} for n, i in bones.items()}
            bones, protected = protect_attachments(bones, weighted_points(nif, minimum_weight=.2),
                                                   hulls, globals_, cloth_components)
            arm_contacts = arm_cloth_bones(bones, cloth_components, skin_co_influences(nif))
            for name, info in bones.items():
                if not info['dynamic']:
                    continue
                points = local_points(samples.get(name, [np.asarray(info['matrix'])[:3, 3]]), info['matrix'])
                centre = np.average(points, axis=0, weights=sample_weights.get(name))
                if name in centres and not np.allclose(centres[name], centre, atol=.001, rtol=0):
                    raise ValueError('Alternate appearance variants disagree on a physics mass centre: '+name)
                centres[name] = centre
                info.update(centred_node=True, node_centre=centre.tolist())
            contacts = contact_surface_points(bones, samples, sample_weights, hulls, globals_, arm_contacts)
            prepared.append((path, samples, sample_weights, bones, protected, arm_contacts, contacts))
    targets = {n: np.asarray(i['matrix']) @ translation(centres.get(n, [0, 0, 0])) for n, i in all_bones.items()}
    for path in sorted(set(paths) | {mesh_dir/'skeleton.nif'}):
        shift_frames(path, targets)
    frame_report = {'runtime': 'FSMP v4.1.1', 'centre_of_mass_transform': 'identity',
                    'node_centres': {n: c.tolist() for n, c in centres.items()},
                    'rest_frames': {n: m.tolist() for n, m in targets.items()}}
    (output/'physics-frames.json').write_text(json.dumps(frame_report, indent=2), encoding='utf8')
    systems = []
    for path, samples, sample_weights, bones, protected, arm_contacts, contacts in prepared:
        with NifFile(str(path)) as nif:
            relative = f'SKSE/Plugins/hdtSkinnedMeshConfigs/{settings.asset_dir}/{path.stem}.xml'
            xml_path = output / 'mod' / relative
            xml_path.parent.mkdir(parents=True, exist_ok=True)
            # Blended visual surfaces must never reintroduce amplified contacts
            # into any secondary chain, including hair and waist cloth.
            secondary_contacts = {n for n in bones if bones[n]['dynamic']} - arm_contacts
            noncontact_helpers = {n for n in bones if bones[n]['dynamic'] and n not in samples}
            mesh_names = []
            contact_groups, rest_inside = contact_collider_groups(bones, contacts, groups)
            used_groups = sorted({g for values in contact_groups.values() for g in values})
            if not hulls:  # Only VRM colliders remain to touch; a patch needs one of them.
                arm_contacts = arm_contacts & set(contact_groups)
                secondary_contacts = secondary_contacts & set(contact_groups)
            if hulls or used_groups:
                with NifFile(str(mesh_dir / 'skeleton.nif')) as skeleton:
                    if hulls:
                        add_collision_proxy(nif, skeleton, hulls)
                    for group in used_groups:
                        add_spring_proxy(nif, skeleton, group, groups[group])
                    for base, owners in ((ARM_PROXY, arm_contacts), (SECONDARY_PROXY, secondary_contacts)):
                        for patch_base, _, _, members in contact_classes(base, owners, bones, contact_groups,
                                                                         noncontact_helpers):
                            add_rigid_collision_proxy(nif, skeleton, members, patch_base, contacts)
            root = system_xml(bones, samples, hulls, settings.physics_stiffness,
                              mesh_names, system_tag(settings, path),
                              sample_weights, arm_contacts, secondary_contacts, noncontact_helpers,
                              contact_groups, {c['bone'] for g in used_groups for c in groups[g]},
                              {g: collider_depth(groups[g]) for g in used_groups})
            ET.indent(root)
            ET.ElementTree(root).write(xml_path, encoding='utf-8', xml_declaration=True)
            attach(nif, relative.replace('/', '\\'))
            systems.append({'nif': path.relative_to(output / 'mod').as_posix(), 'xml': relative,
                            'dynamic_bones': [n for n in bones if bones[n]['dynamic']],
                            'protected_bones': protected,
                            'arm_contact_bones': sorted(arm_contacts),
                            'secondary_contact_bones': sorted(secondary_contacts),
                            'noncontact_helpers': sorted(noncontact_helpers),
                            'contact_points': contacts,
                            'contact_groups': contact_groups,
                            'rest_inside_colliders': rest_inside,
                            'tail_contacts': sorted(n for n, p in contacts.items() if p == bones[n].get('spring_tail')),
                            'borrowed_colliders': {n: i['borrowed'] for n, i in bones.items() if 'borrowed' in i},
                            'body_hulls': len(hulls)})
            inertias = [float(b.find('inertia').attrib['x']) for b in root.findall('bone')
                        if float(b.findtext('mass', '0')) > 0]
            logging.info('FSMP %s: %s attachments fixed, %s movers; direct inertia %.7g..%.7g mass*units²',
                         path.name, len(protected), len(inertias),
                         min(inertias, default=0), max(inertias, default=0))
            logging.info('FSMP %s: %s sleeve segments use rigid surface contact patches',
                         path.name, len(arm_contacts))
            logging.info('FSMP %s: %s hair/other cloth segments use rigid surface contact patches',
                         path.name, len(secondary_contacts))
            logging.info('FSMP %s: %s unweighted chain helpers retain joints without contact feedback',
                         path.name, len(noncontact_helpers))
            logging.info('FSMP %s: %s VRM collider groups, %s segments use them, %s start inside one, '
                         '%s contacts at their spring tail, %s movers borrow colliders',
                         path.name, len(used_groups), len(contact_groups), len(rest_inside),
                         len(systems[-1]['tail_contacts']), len(systems[-1]['borrowed_colliders']))
    if not systems:
        raise ValueError('FSMP enabled but no appearance NIF retained movable bone weights')
    result = {'enabled': True, 'systems': systems, 'profile': 'rigid_secondary_contacts_v6',
              'frame_policy': {'centre_of_mass_transform': 'identity',
                               'compensated_skin_binds': True, 'preserve_original_joint_pivots': True},
              'inertia_policy': {'semantics': 'direct Bullet local inertia in mass*game_units²',
                                 'sphere_multiplier': INERTIA_MULTIPLIER,
                                 'verified_runtime_source': 'FSMP v4.1.1'},
              'attachment_policy': {'arm_margin_body_height': .04, 'weight_threshold': .2,
                                    'proximity_quantile': .9, 'fixed_prefix_only': True},
              'stiffness': settings.physics_stiffness,
              'arm_contact_policy': 'single-owner patches on strongly weighted body-clear cloth surfaces',
              'secondary_contact_policy': 'single-owner surface patches for all weighted hair and cloth movers',
              'collision_source': 'weighted original avatar body vertices'}
    (output / 'physics.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    validate_physics(output)
    logging.info('FSMP calm profile: %s systems, %s body hulls, stiffness %.3f; gravity %.3f',
                 len(systems), len(hulls), settings.physics_stiffness, GRAVITY)
    return result


def validate_spring_contacts(system, root, proxies, bones, groups, patch_classes, tag):
    """Re-derive collider contacts from the rest pose; compare them with the XML and NIF."""
    kept, inside = contact_collider_groups(bones, system.get('contact_points', {}), groups)
    if kept != system.get('contact_groups', {}) or inside != system.get('rest_inside_colliders', {}):
        raise ValueError('Collider contact groups do not match the rest contact points')
    used = sorted({g for values in kept.values() for g in values})
    body_tags = {tag} if system['body_hulls'] else set()
    generated = body_tags | {spring_tag(tag, g) for g in used}
    surfaces = root.findall('per-triangle-shape')
    if ({s.attrib['name'] for s in surfaces} !=
            ({PROXY} if system['body_hulls'] else set()) | {f'{SPRING_PROXY}{g}' for g in used}):
        raise ValueError('Spring collider shapes do not match the groups in use')
    if any(root.findtext(f"per-triangle-shape[@name='{SPRING_PROXY}{g}']/shared") != 'internal' for g in used):
        raise ValueError('Spring collider shapes must stay internal to their actor')
    for surface in surfaces:
        if (float(surface.findtext('margin')) != TRIANGLE_MARGIN or
                {e.text for e in surface.findall('no-collide-with-tag')} != generated):
            raise ValueError('Generated collision shapes must not collide with each other: '+surface.attrib['name'])
    for group in used:
        depth = root.findtext(f"per-triangle-shape[@name='{SPRING_PROXY}{group}']/penetration")
        if depth is None or float(depth) != collider_depth(groups[group]):
            raise ValueError('Spring collider depth differs from its colliders: '+str(group))
    for name in system.get('tail_contacts', []):
        if not np.allclose(system['contact_points'][name], bones[name]['spring_tail'], atol=.001):
            raise ValueError('Tail contact is displaced from its VRM spring tail: '+name)
    for surface in root.findall('per-vertex-shape'):
        margin, member_groups = patch_classes[surface.attrib['name']]
        if (float(surface.findtext('margin')) != margin or
                {e.text for e in surface.findall('can-collide-with-tag')} !=
                body_tags | {spring_tag(tag, g) for g in member_groups}):
            raise ValueError('Contact patch margin or tags differ from its class: '+surface.attrib['name'])
    shapes = {s.name: s for s in proxies}
    for group in used:
        name = f'{SPRING_PROXY}{group}'
        vertices, triangles, weights = spring_mesh(groups[group])
        shape = shapes.get(name)
        if shape is None or not shape.properties.flags & 1:
            raise ValueError('Spring collider proxy must be present and hidden: '+name)
        if (len(shape.tris) != len(triangles) or len(shape.verts) != len(vertices) or
                not np.allclose(shape.verts, vertices, atol=.001)):
            raise ValueError('Spring collider proxy differs from its colliders: '+name)
        if (set(shape.bone_weights) != set(weights) or
                any(sorted(shape.bone_weights[b]) != pairs for b, pairs in weights.items())):
            raise ValueError('Spring collider vertices must have one rigid influence: '+name)


def validate_physics(output):
    output = Path(output)
    settings = load_settings(output)
    if not settings.physics_enabled:
        return
    report = json.loads((output / 'physics.json').read_text(encoding='utf8'))
    physics_bones = json.loads((output/'skeleton.json').read_text(encoding='utf8'))['physics_bones']
    groups = load_collider_groups(output)
    appearance = json.loads((output/'appearance.json').read_text(encoding='utf8'))
    cloth_components = cloth_component_ids(appearance)
    component_files = {p['file'] for p in appearance['components']}
    active = set()
    for system in report['systems']:
        if Path(system['nif']).name in component_files:
            overlap = active & set(system['dynamic_bones'])
            if overlap:
                raise ValueError(f'Equipped components share dynamic bones: {sorted(overlap)}')
            active.update(system['dynamic_bones'])
    with NifFile(str(output / 'mod/meshes' / settings.asset_dir / 'skeleton.nif')) as skeleton:
        names = set(skeleton.nodes)
        globals_ = {n: matrix(node.global_transform) for n, node in skeleton.nodes.items()}
    if report.get('profile') in ('unified_contact_frames_v4', 'rigid_sleeve_contacts_v5', 'rigid_secondary_contacts_v6'):
        frames = json.loads((output/'physics-frames.json').read_text(encoding='utf8'))
        for name, expected in frames['rest_frames'].items():
            if not np.allclose(globals_[name], expected, atol=.001, rtol=0):
                raise ValueError('Skeleton mass-centre frame mismatch: '+name)
    for system in report['systems']:
        root = read_system(output / 'mod' / system['xml'])
        bones = {b.attrib['name'] for b in root.findall('bone')}
        if bones - names:
            raise ValueError(f'FSMP bones missing from skeleton: {bones - names}')
        for bone in root.findall('bone'):
            if float(bone.findtext('mass', '0')) > 0:
                inertia = bone.find('inertia')
                values = [float(inertia.attrib[a]) for a in 'xyz'] if inertia is not None else []
                if len(values) != 3 or not np.isfinite(values).all() or min(values) <= 0:
                    raise ValueError('FSMP mover requires finite positive explicit inertia: '+bone.attrib['name'])
                if not 0 <= float(bone.findtext('gravity-factor', '1')) <= 1:
                    raise ValueError('FSMP gravity-factor outside 0..1: '+bone.attrib['name'])
                if report.get('profile') in ('unified_contact_frames_v4', 'rigid_sleeve_contacts_v5'):
                    centre = bone.find('centerOfMassTransform/origin')
                    if centre is None or any(abs(float(centre.attrib[a])) > 1e-7 for a in 'xyz'):
                        raise ValueError('FSMP render/contact frames require identity COM: '+bone.attrib['name'])
        for joint in root.findall('generic-constraint'):
            if {joint.attrib['bodyA'], joint.attrib['bodyB']} - bones:
                raise ValueError('FSMP constraint references undeclared bodies')
        for name in system.get('protected_bones', {}):
            if root.find(f"bone[@name='{name}']/mass").text != '0':
                raise ValueError('Garment attachment bone is simulated: '+name)
            if any(j.attrib['bodyB'] == name for j in root.findall('generic-constraint')):
                raise ValueError('Garment attachment bone has a physics constraint: '+name)
        with NifFile(str(output / 'mod' / system['nif'])) as nif:
            links = list(nif.rootNode.extra_data(name=LINK))
            if len(links) != 1 or links[0].string_data.replace('\\', '/') != system['xml']:
                raise ValueError('FSMP NIF link does not match its private system')
            if system['dynamic_bones'] and not set(system['dynamic_bones']) & set(weighted_points(nif)):
                raise ValueError('Physics system has no movable mesh weights')
            shape_names = {s.name for s in nif.shapes}
            for tag in ('per-triangle-shape', 'per-vertex-shape'):
                if any(s.attrib['name'] not in shape_names for s in root.findall(tag)):
                    raise ValueError('FSMP collision shape missing from its owning NIF')
            proxies = [s for s in nif.shapes if s.name.startswith('V2SCollision_')]
            body = [s for s in proxies if s.name == PROXY]
            if system['body_hulls'] and (len(body) != 1 or not body[0].properties.flags & 1):
                raise ValueError('FSMP body collision proxy must be present and hidden')
            helpers = set(system.get('noncontact_helpers', []))
            contact_groups = system.get('contact_groups', {})
            # Borrowing happens before attachments are pinned, over every mover of the plan.
            planned = [n for n in [*system['dynamic_bones'], *system.get('protected_bones', {})]
                       if physics_bones[n]['dynamic']]
            borrowed = borrowed_colliders(physics_bones, planned, cloth_components)
            if borrowed != system.get('borrowed_colliders', borrowed):
                raise ValueError('Borrowed colliders do not match the movers of this system')
            contact_bones = {**physics_bones, **{n: {**physics_bones[n], 'borrowed': v} for n, v in borrowed.items()}}

            def classified_patches(base, owners):
                return [(patch, chunk, margin, tuple(member_groups))
                        for patch_base, margin, member_groups, members in contact_classes(
                            base, owners, contact_bones, contact_groups, helpers)
                        for patch, chunk in contact_patches(patch_base, members)]

            classified = {ARM_PROXY: classified_patches(ARM_PROXY, system.get('arm_contact_bones', [])),
                          SECONDARY_PROXY: classified_patches(SECONDARY_PROXY, system.get('secondary_contact_bones', []))}
            arm_patches, secondary_patches = [[p[:2] for p in classified[b]] for b in (ARM_PROXY, SECONDARY_PROXY)]
            patch_owners = dict(arm_patches + secondary_patches)
            spring_names = {f'{SPRING_PROXY}{g}' for values in contact_groups.values() for g in values}
            if {s.name for s in proxies} - {PROXY} - set(patch_owners) - spring_names:
                raise ValueError('Unexpected generated collision shape in NIF')

            def patches_match(base, patches):
                shapes = [s for s in proxies if s.name == base or s.name.startswith(base+'_')]
                return {s.name for s in shapes} == {n for n, _ in patches} and all(
                    s.properties.flags & 1 and set(s.bone_names) == set(patch_owners[s.name]) for s in shapes)
            if system.get('arm_contact_bones'):
                if not patches_match(ARM_PROXY, arm_patches):
                    raise ValueError('Sleeve collision proxy must be hidden and match its private bone owners')
                if any(root.find(f"per-vertex-shape[@name='{n}']") is None for n, _ in arm_patches):
                    raise ValueError('Sleeve collision proxy has no XML contact declaration')
                for surface in root.findall('per-vertex-shape'):
                    if surface.attrib['name'] in patch_owners:
                        continue
                    for name in system['arm_contact_bones']:
                        if surface.findtext(f"weight-threshold[@bone='{name}']") != '1':
                            raise ValueError('Visual sleeve still generates blended contact forces')
            if report.get('profile') == 'rigid_secondary_contacts_v6' and (system['body_hulls'] or groups):
                arm = set(system['arm_contact_bones'])
                secondary = set(system['secondary_contact_bones'])
                contact_owners = set(system['dynamic_bones']) if system['body_hulls'] else set(contact_groups)
                if arm & secondary or arm | secondary != contact_owners:
                    raise ValueError('Secondary contact ownership must partition all movable bones')
                if secondary and not patches_match(SECONDARY_PROXY, secondary_patches):
                    raise ValueError('Secondary contact proxy must be hidden and match its bone owners')
                if {s.attrib['name'] for s in root.findall('per-vertex-shape')} != set(patch_owners):
                    raise ValueError('Visual surfaces must not generate blended secondary contact forces')
                samples, _ = skin_samples(nif)
                if helpers != set(system['dynamic_bones']) - set(samples):
                    raise ValueError('Noncontact helpers must be exactly the unweighted movable bones')
                points = system.get('contact_points', {})
                if set(points) != set(system['dynamic_bones']) - helpers:
                    raise ValueError('Every weighted secondary bone needs a declared contact surface point')
                tail_contacts = set(system.get('tail_contacts', []))
                for name, point in points.items():
                    if name in arm and np.linalg.norm(globals_[name][:3, 3]-point) < .001:
                        continue  # Preserve established sleeve contacts clear of the rest body.
                    if name in tail_contacts:
                        continue  # validate_spring_contacts holds it to the VRM spring tail.
                    if np.min(np.linalg.norm(np.asarray(samples[name])-point, axis=1)) > .001:
                        raise ValueError('Secondary contact point is not on its original weighted surface')
                for surface in root.findall('per-vertex-shape'):
                    owners = set(patch_owners[surface.attrib['name']])
                    actual = {e.attrib['bone'] for e in surface.findall('weight-threshold') if e.text == '1'}
                    if actual != helpers & owners:
                        raise ValueError('Unweighted helper contact exclusion does not match its proxy')
                validate_spring_contacts(system, root, proxies, contact_bones, groups,
                                         {p[0]: p[2:] for values in classified.values() for p in values},
                                         system_tag(settings, system['nif']))
            for shape in proxies:
                if not shape.shader.textures.get('Diffuse') or not shape.shader.textures.get('Normal'):
                    raise ValueError('Body collision proxy lacks valid texture references')
                if set(shape.bone_names) - names:
                    raise ValueError('Body collision proxy has unresolved bones')
                sums = np.zeros(len(shape.verts))
                for name, pairs in shape.bone_weights.items():
                    bind = shape.get_shape_skin_to_bone(name)
                    if bind is None or not np.allclose(globals_[name] @ matrix(bind), np.eye(4), atol=.001):
                        raise ValueError('Body collision bind pose mismatch: '+name)
                    for vertex, weight in pairs:
                        sums[vertex] += weight
                    if shape.name in patch_owners:
                        if any(weight != 1. for _, weight in pairs):
                            raise ValueError('Sleeve contact vertices must have one rigid influence')
                        centre = np.asarray(system.get('contact_points', {}).get(name, globals_[name][:3, 3]))
                        if any(np.linalg.norm(np.asarray(shape.verts[v])-centre) > .003 for v, _ in pairs):
                            raise ValueError('Secondary contact patch is displaced from its declared surface point')
                if not np.allclose(sums, 1., atol=.001):
                    raise ValueError('Body collision proxy has invalid weights')
                for texture in shape.shader.textures.values():
                    if texture and not (output/'mod'/texture.replace('\\', '/')).is_file():
                        raise ValueError('Missing body collision texture: '+texture)
