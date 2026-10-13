"""Plan private secondary bones from actual influences, never bone names alone."""
import hashlib
import xml.etree.ElementTree as ET


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
    weighted cloth roots can pivot directly on their humanoid anchor. Shared paths remain kinematic, so
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
