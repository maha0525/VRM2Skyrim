"""Plan private secondary bones from actual influences, never bone names alone."""
import hashlib
import math
import xml.etree.ElementTree as ET

import numpy as np


def rotation_step_angles(rotations):
    """Geodesic step angles without acos amplifying float32 rest-pose drift.

    atan2 uses both the skew (sin) and trace (cos). Identical, slightly rounded
    matrices have a symmetric relative matrix and therefore zero step angle.
    """
    rotations = np.asarray(rotations)
    relative = np.swapaxes(rotations[:-1], -1, -2) @ rotations[1:]
    skew = np.stack((relative[..., 2, 1]-relative[..., 1, 2],
                     relative[..., 0, 2]-relative[..., 2, 0],
                     relative[..., 1, 0]-relative[..., 0, 1]), axis=-1)
    sine = np.linalg.norm(skew, axis=-1) * .5
    cosine = (np.trace(relative, axis1=-2, axis2=-1)-1) * .5
    return np.arctan2(sine, cosine)


def inertia_sphere_radius(mass, inertia):
    """Sphere radius giving exactly the XML's direct inertia in Bullet.

    Blender exposes shape-derived inertia only. Refuse unsupported anisotropic
    tensors instead of silently approximating them in the diagnostic.
    """
    if mass <= 0 or not math.isfinite(mass) or len(inertia) != 3:
        raise ValueError('Preview requires a finite positive dynamic mass and three inertia values')
    if not all(math.isfinite(i) and i > 0 and math.isclose(i, inertia[0], rel_tol=1e-6)
               for i in inertia):
        raise ValueError('Preview requires isotropic positive explicit inertia')
    return math.sqrt(inertia[0] / (.4 * mass))


def read_system(path):
    root = ET.parse(path).getroot()
    for element in root.iter():
        element.tag = element.tag.removeprefix('{FSMP-Validator}')
    if root.tag != 'system':
        raise ValueError('Invalid FSMP system root')
    return root


def spring_nodes(document):
    """Read both VRM spring formats as candidate hints, not Bullet parameters."""
    extension = document.get('extensions', {})
    result = {j['node'] for s in extension.get('VRMC_springBone', {}).get('springs', [])
              for j in s.get('joints', [])}
    for group in extension.get('VRM', {}).get('secondaryAnimation', {}).get('boneGroups', []):
        stack = list(group.get('bones', []))
        while stack:
            index = stack.pop()
            if index in result:
                continue
            result.add(index)
            stack.extend(document['nodes'][index].get('children', []))
    return {f'VRMNode_{i:05}' for i in result}


def spring_settings(document):
    """{node: stiffness, gravity, hit_radius, groups} for both VRM formats; the first declaration wins."""
    extension = document.get('extensions', {})
    result = {}
    for spring in extension.get('VRMC_springBone', {}).get('springs', []):
        groups = sorted(set(spring.get('colliderGroups', [])))
        for joint in spring.get('joints', []):
            result.setdefault(f'VRMNode_{joint["node"]:05}', {
                'stiffness': float(joint.get('stiffness', 1)), 'gravity': float(joint.get('gravityPower', 0)),
                'hit_radius': float(joint.get('hitRadius', 0)), 'groups': groups})
    for group in extension.get('VRM', {}).get('secondaryAnimation', {}).get('boneGroups', []):
        values = {'stiffness': float(group.get('stiffiness', 1)), 'gravity': float(group.get('gravityPower', 0)),
                  'hit_radius': float(group.get('hitRadius', 0)),
                  'groups': sorted(set(group.get('colliderGroups', [])))}
        stack = list(group.get('bones', []))
        while stack:
            index = stack.pop()
            name = f'VRMNode_{index:05}'
            if name in result:
                continue
            result[name] = values
            stack.extend(document['nodes'][index].get('children', []))
    return result


def spring_colliders(document):
    """{group: [{node, head, tail, radius}]} in glTF node-local coordinates; tail None is a sphere.

    VRM 0 offsets keep a left-handed node frame: x matches glTF, z is negated.
    On AnimalKawaii_01_Kuro.vrm arm offsets run along the limb unchanged in x, and forearm
    and thigh offsets lie on the limb only once z is negated.
    """
    extension = document.get('extensions', {})
    result = {}
    springs = extension.get('VRMC_springBone', {})
    colliders = springs.get('colliders', [])
    for index, group in enumerate(springs.get('colliderGroups', [])):
        for collider in (colliders[i] for i in group.get('colliders', [])):
            shape = collider.get('shape', {})
            values = shape.get('capsule') or shape.get('sphere')
            if values is None:
                continue
            tail = [float(n) for n in values.get('tail', [0, 0, 0])] if 'capsule' in shape else None
            result.setdefault(index, []).append({
                'node': collider['node'], 'head': [float(n) for n in values.get('offset', [0, 0, 0])],
                'tail': tail, 'radius': float(values.get('radius', 0))})
    secondary = extension.get('VRM', {}).get('secondaryAnimation', {})
    for index, group in enumerate(secondary.get('colliderGroups', [])):
        for collider in group.get('colliders', []):
            offset = collider.get('offset', {})
            result.setdefault(index, []).append({
                'node': group['node'], 'head': [float(offset.get('x', 0)), float(offset.get('y', 0)),
                                                -float(offset.get('z', 0))],
                'tail': None, 'radius': float(collider.get('radius', 0))})
    return result


def inherited_spring(name, parents, settings):
    """A bone's own spring settings, else those of its nearest ancestor that has them."""
    while name is not None:
        if name in settings:
            return settings[name]
        name = parents.get(name)
    return None


def node_local_matrix(node):
    if 'matrix' in node:
        return np.asarray(node['matrix'], dtype=float).reshape(4, 4).T
    x, y, z, w = node.get('rotation', [0, 0, 0, 1])
    rotation = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                         [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                         [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    result = np.eye(4)
    result[:3, :3] = rotation * np.asarray(node.get('scale', [1, 1, 1]), dtype=float)
    result[:3, 3] = node.get('translation', [0, 0, 0])
    return result


def node_world_matrices(document):
    nodes = document['nodes']
    children = {child for node in nodes for child in node.get('children', [])}
    stack = [(index, np.eye(4)) for index in range(len(nodes)) if index not in children]
    result = {}
    while stack:
        index, parent = stack.pop()
        result[index] = parent @ node_local_matrix(nodes[index])
        stack.extend((child, result[index]) for child in nodes[index].get('children', []))
    return result


def blender_point(point):
    """The glTF importer's Y-up to Z-up conversion."""
    x, y, z = point
    return np.array([x, -z, y])


def posed_colliders(groups, worlds, node_parents, source_bones, transforms, orient, mapping, fallback):
    """Colliders in the custom pose, anchored to the NPC bone of their node or nearest skinned ancestor."""
    orient = np.asarray(orient)
    result = []
    for group, colliders in sorted(groups.items()):
        for collider in colliders:
            index = collider['node']
            while index is not None and f'VRMNode_{index:05}' not in source_bones:
                index = node_parents.get(index)
            bone = fallback if index is None else f'VRMNode_{index:05}'
            pose = np.asarray(transforms[bone]) @ orient
            world = worlds[collider['node']]

            def place(offset):
                point = blender_point(world[:3, :3] @ np.asarray(offset) + world[:3, 3])
                return (pose[:3, :3] @ point + pose[:3, 3]).tolist()

            tail = collider['tail']
            result.append({'group': group, 'bone': mapping[bone], 'head': place(collider['head']),
                           'tail': None if tail is None else place(tail), 'radius': collider['radius']*70})
    return result


def unswayable_nodes(settings):
    """Body meshes cut into slot NIFs and clothing skin copies; their bones would span several files."""
    if not settings.armor_support or not settings.skin_partition_enabled:
        return set()
    return set(settings.appearance_parts['body'])


def selected_meshes(settings, original_names, available):
    if settings.physics_nodes:
        missing = set(settings.physics_nodes) - set(available)
        if missing:
            raise ValueError(f'Physics meshes absent from this VRM: {sorted(missing)}')
        return set(settings.physics_nodes)
    nodes = set(settings.appearance_heads.get('hair', []))
    if settings.armor_support:
        nodes.update(n for g in settings.appearance_parts['garments'] for n in g['nodes'])
    else:
        # An unclassified model requires an explicit mesh choice for clothing.
        nodes.update(i for i in available if 'hair' in original_names[i].lower())
    return nodes & set(available)


def plan_bones(parents, direct, influences, mod_id, hints=(), fixed_bones=(), root_components=()):
    """influences maps component IDs to positively weighted source bones.

    Preserve complete non-humanoid paths. Hair scalp roots remain kinematic;
    weighted cloth roots are retained as candidates. The XML stage classifies
    fixed garment attachments using the exported skin/body geometry. Shared paths remain kinematic, so
    removing one outfit cannot leave another system controlling the same joint.
    """
    owners = {}
    for component, weighted in influences.items():
        for name in weighted:
            while name in parents and name not in direct:
                owners.setdefault(name, set()).add(component)
                name = parents[name]
    prefix = 'V2SP_' + hashlib.sha256(mod_id.lower().encode()).hexdigest()[:10] + '_'
    retained = {name: prefix + name.removeprefix('VRMNode_') for name in owners}
    result = {}
    hints = set(hints)
    fixed_bones = set(fixed_bones)
    root_components = set(root_components)
    for name, components in owners.items():
        parent = parents[name]
        # A singleton helper/rigid accessory has no independent chain to bend.
        has_chain = any(parents[child] == name for child in retained)
        has_anchor = parent in retained or (parent in direct and components <= root_components and
                                             (has_chain or name in hints))
        movable = name not in fixed_bones and has_anchor and len(components) == 1 and (name in hints or
            any(name in weights for weights in influences.values()))
        result[name] = {'name': retained[name], 'parent': retained.get(parent, direct.get(parent)),
                        'dynamic': movable, 'components': sorted(components)}
        if result[name]['parent'] is None:
            raise ValueError(f'Physics bone has no humanoid anchor: {name}')
    # Drop complete branches with no dynamic member.
    useful = set()
    for name, info in result.items():
        if info['dynamic']:
            while name in result:
                useful.add(name)
                name = parents[name]
    return {name: result[name] for name in sorted(useful)}
