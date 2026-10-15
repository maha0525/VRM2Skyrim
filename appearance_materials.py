"""Retain source material ownership when avatar geometry is split or copied."""
import copy
import logging


def derived_shape(source, name):
    if not isinstance(source.get('material_policy'), dict):
        raise ValueError('Missing source material metadata: '+source['name'])
    return {**copy.deepcopy(source), 'name': name,
            'source_shape': source.get('source_shape', source['name'])}


def exported_shapes(path, bindings):
    """Bind actual exported names to their explicit source, never by texture."""
    from custom_skeleton import NifFile
    from nif_materials import apply_alpha
    with NifFile(str(path)) as nif:
        names = [s.name for s in nif.shapes if not s.name.startswith('V2SCollision_')]
    unknown = set(names)-bindings.keys()
    missing = bindings.keys()-set(names)
    if unknown or missing:
        raise ValueError(f'Exported source material bindings changed in {path.name}: '
                         f'unknown={sorted(unknown)}, missing={sorted(missing)}')
    shapes = [derived_shape(bindings[name], name) for name in names]
    apply_alpha(path, {s['name']: s['material_policy'] for s in shapes})
    logging.info('Retained source material ownership: %s, %d shapes', path.name, len(shapes))
    return shapes
