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
from pyn.pynifly import NiStringExtraData
from pyn.structs import TransformBuf

LINK = 'HDT Skinned Mesh Physics Object'
PROXY = 'V2SCollision_Body'
GRAVITY = 9.8 / .01425  # FSMP scaleSkyrim: game units per second squared
MASS = .1
INERTIA_MULTIPLIER = 5.  # Increase geometric inertia without increasing spring torque


def bone_inertia(radius, mass=MASS):
    """FSMP 4.1.1 passes XML inertia directly to Bullet, in mass*units².

    Shape radius does not automatically calculate or divide this value.
    Use an isotropic sphere approximation to avoid orientation-dependent bias.
    """
    return .4 * mass * radius**2 * INERTIA_MULTIPLIER


def joint_profile(com, radius, global_matrix, stiffness=1., mass=MASS):
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
    geometric_inertia = .4 * mass * radius**2
    inertia = bone_inertia(radius, mass)
    lever = basis.T @ np.asarray(com)
    pivot_inertia = inertia + mass * (length**2 - lever**2)
    omega = 2 * np.pi * .65 * np.sqrt(stiffness)
    spring = np.full(3, geometric_inertia * omega**2)
    # Gravity supplies a restoring torque as a hanging chain moves; damping
    # must account for that too, not only the deliberately gentle rest spring.
    gravity_torque = mass * GRAVITY * length * np.array([1., 1., 0.])
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
        if shape.name == PROXY:
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


def protect_attachments(bones, samples, hulls, globals_, cloth_components):
    """Keep garment attachment roots and nearby arm sleeves in animated FK.

    Proximity uses the actual avatar's arm hulls and positively weighted skin,
    never source bone/mesh names. Extend only the fixed prefix of a chain:
    pinning a distal node below a simulated parent would still move its cuff.
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
        side = next((s for s in ('L', 'R') if anchor.startswith(f'NPC {s} ') and
                     any(p in anchor for p in ('UpperArm', 'Forearm', 'Hand'))), None)
        if side is None or not world_hulls:
            return
        arm = [h.equations for n, h in world_hulls.items() if n.startswith(f'NPC {side} ') and
               any(p in n for p in ('UpperArm', 'Forearm', 'Hand'))]
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


def system_xml(bones, samples, hulls, stiffness=1., mesh_names=(), collision_tag='V2SBody'):
    root = ET.Element('system', xmlns='FSMP-Validator')
    scalar(ET.SubElement(root, 'bone-default'), 'mass', 0)
    colliders = sorted(set(hulls) - set(bones))
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
        com = points.mean(axis=0)
        transform(bone, 'centerOfMassTransform', com)
        scalar(bone, 'linearDamping', .85)
        scalar(bone, 'angularDamping', .95)
        scalar(bone, 'gravity-factor', 1)
        scalar(bone, 'wind-factor', 0)
        # This sphere describes the effective geometry, not contact surfaces.
        # FSMP does not derive inertia from the shape; serialize it explicitly.
        # Include the pivot-to-CoM lever. A tiny tip sphere on a long joint
        # lever can rotate explosively while the positional constraint catches
        # up, especially at ordinary runtime solver iteration counts.
        radius = max(.65, float(np.linalg.norm(com)),
                     float(np.sqrt(np.square(points-com).sum(axis=1).mean())))
        vector(bone, 'inertia', [bone_inertia(radius, mass)] * 3)
        scalar(ET.SubElement(bone, 'shape', type='sphere'), 'radius', round(radius, 6))
        profiles[name] = joint_profile(com, radius, info['matrix'], stiffness, mass)
    for name, info in bones.items():
        if not info['dynamic']:
            continue
        joint = ET.SubElement(root, 'generic-constraint', bodyA=info['parent'], bodyB=name)
        # frameInB is BONE-local, not rigid-body-local. FSMP applies rigToLocal
        # itself. Subtracting CoM here would apply the offset twice.
        transform(joint, 'frameInB', [0, 0, 0])
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
    if hulls:
        proxy = ET.SubElement(root, 'per-triangle-shape', name=PROXY)
        scalar(proxy, 'margin', .35)
        scalar(proxy, 'tag', collision_tag)
        scalar(proxy, 'no-collide-with-tag', collision_tag)
        for name in mesh_names:
            shape = ET.SubElement(root, 'per-vertex-shape', name=name)
            scalar(shape, 'margin', .4)
            scalar(shape, 'can-collide-with-tag', collision_tag)
    return root


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
    shape = nif.createShapeFromData(PROXY, vertices, triangles, [(0., 0.)]*len(vertices),
                                    [(0., 0., 1.)]*len(vertices))
    # Valid private texture paths even if the renderer inspects hidden shapes.
    texture = next((s.shader.textures.get('Normal') for s in nif.shapes if s.name != PROXY
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


def build_physics(output):
    output = Path(output)
    settings = load_settings(output)
    if not settings.physics_enabled:
        return {'enabled': False, 'systems': []}
    mesh_dir = output / 'mod/meshes' / settings.asset_dir
    report = json.loads((output / 'skeleton.json').read_text(encoding='utf8'))
    all_bones = report['physics_bones']
    appearance = json.loads((output / 'appearance.json').read_text(encoding='utf8'))
    with NifFile(str(mesh_dir / 'skeleton.nif')) as skeleton:
        globals_ = {name: matrix(node.global_transform) for name, node in skeleton.nodes.items()}
    source = json.loads((output/'source.json').read_text(encoding='utf8'))
    body_nodes = [p['node'] for p in source['parts'] if p['suggested_role'] == 'body' or
                  ('face' in p['name'].lower() and 'hair' not in p['name'].lower())]
    hulls = collision_hulls(mesh_dir, appearance, globals_, body_nodes)
    cloth_components = {p['id'] for p in appearance['components'] if p['role'] == 'garment'} | {'appearance_cloth'}
    paths = [mesh_dir / p['file'] for p in appearance['components']]
    paths += sorted(mesh_dir.glob('fixed_*.nif'))
    systems = []
    for path in sorted(set(paths)):
        with NifFile(str(path)) as nif:
            samples = weighted_points(nif)
            used = set(samples) & set(all_bones)
            if not any(all_bones[n]['dynamic'] for n in used):
                continue
            for name in list(used):
                parent = all_bones[name]['parent']
                while parent in all_bones:
                    used.add(parent)
                    parent = all_bones[parent]['parent']
            bones = {n: all_bones[n] for n in all_bones if n in used}
            bones, protected = protect_attachments(bones, weighted_points(nif, minimum_weight=.2),
                                                   hulls, globals_, cloth_components)
            relative = f'SKSE/Plugins/hdtSkinnedMeshConfigs/{settings.asset_dir}/{path.stem}.xml'
            xml_path = output / 'mod' / relative
            xml_path.parent.mkdir(parents=True, exist_ok=True)
            mesh_names = [s.name for s in nif.shapes if set(s.bone_names) &
                          {n for n in bones if bones[n]['dynamic']} and s.name != PROXY]
            if hulls:
                with NifFile(str(mesh_dir / 'skeleton.nif')) as skeleton:
                    add_collision_proxy(nif, skeleton, hulls)
            root = system_xml(bones, samples, hulls, settings.physics_stiffness,
                              mesh_names, 'V2SBody_'+settings.mod_id.lower()+'_'+path.stem)
            ET.indent(root)
            ET.ElementTree(root).write(xml_path, encoding='utf-8', xml_declaration=True)
            attach(nif, relative.replace('/', '\\'))
            systems.append({'nif': path.relative_to(output / 'mod').as_posix(), 'xml': relative,
                            'dynamic_bones': [n for n in bones if bones[n]['dynamic']],
                            'protected_bones': protected,
                            'body_hulls': len(hulls)})
            inertias = [float(b.find('inertia').attrib['x']) for b in root.findall('bone')
                        if float(b.findtext('mass', '0')) > 0]
            logging.info('FSMP %s: %s attachments fixed, %s movers; direct inertia %.7g..%.7g mass*units²',
                         path.name, len(protected), len(inertias),
                         min(inertias, default=0), max(inertias, default=0))
    if not systems:
        raise ValueError('FSMP enabled but no appearance NIF retained movable bone weights')
    result = {'enabled': True, 'systems': systems, 'profile': 'calm_explicit_inertia_v3',
              'inertia_policy': {'semantics': 'direct Bullet local inertia in mass*game_units²',
                                 'sphere_multiplier': INERTIA_MULTIPLIER,
                                 'verified_runtime_source': 'FSMP v4.1.1'},
              'attachment_policy': {'arm_margin_body_height': .04, 'weight_threshold': .2,
                                    'proximity_quantile': .9, 'fixed_prefix_only': True},
              'stiffness': settings.physics_stiffness,
              'collision_source': 'weighted original avatar body vertices'}
    (output / 'physics.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    validate_physics(output)
    logging.info('FSMP calm profile: %s systems, %s body hulls, stiffness %.3f; gravity %.3f',
                 len(systems), len(hulls), settings.physics_stiffness, GRAVITY)
    return result


def validate_physics(output):
    output = Path(output)
    settings = load_settings(output)
    if not settings.physics_enabled:
        return
    report = json.loads((output / 'physics.json').read_text(encoding='utf8'))
    appearance = json.loads((output/'appearance.json').read_text(encoding='utf8'))
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
            proxies = [s for s in nif.shapes if s.name == PROXY]
            if system['body_hulls'] and (len(proxies) != 1 or not proxies[0].properties.flags & 1):
                raise ValueError('FSMP body collision proxy must be present and hidden')
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
                if not np.allclose(sums, 1., atol=.001):
                    raise ValueError('Body collision proxy has invalid weights')
                for texture in shape.shader.textures.values():
                    if texture and not (output/'mod'/texture.replace('\\', '/')).is_file():
                        raise ValueError('Missing body collision texture: '+texture)
