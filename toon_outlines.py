"""Per-shape skinned inverted hulls with explicit ownership and checked originals."""
import hashlib
import json
import logging
from pathlib import Path
import shutil

import numpy as np

from custom_skeleton import NifFile, children, set_children
from toon_shade import shade_image

UNITS_PER_METRE = 70.
PREFIX = 'V2SOutline_'


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reset_originals(output, paths):
    folder = Path(output)/'toon-originals'
    folder.mkdir(exist_ok=True)
    state_file = folder/'state.json'
    state = json.loads(state_file.read_text(encoding='utf8')) if state_file.exists() else {}
    for path in paths:
        cache = folder/path.name
        saved = state.get(path.name)
        current = file_hash(path)
        if saved and current in {saved['original'], saved.get('prepared')}:
            if not cache.exists() or file_hash(cache) != saved['original']:
                raise ValueError('Toon original cache changed; regenerate conversion: '+path.name)
            shutil.copy2(cache, path)
        else:
            with NifFile(str(path.resolve())) as nif:
                if any(s.name.startswith(PREFIX) for s in nif.shapes):
                    raise ValueError('Unknown outline-bearing input; regenerate conversion: '+path.name)
            shutil.copy2(path, cache)
            state[path.name] = {'original': current}
    state_file.write_text(json.dumps(state, indent=2), encoding='utf8')


def remember_prepared(output, paths):
    path = Path(output)/'toon-originals/state.json'
    state = json.loads(path.read_text(encoding='utf8'))
    for source in paths:
        state[source.name]['prepared'] = file_hash(source)
    path.write_text(json.dumps(state, indent=2), encoding='utf8')


def width_for(document, binary, material, uvs):
    mtoon = material.get('extensions', {}).get('VRMC_materials_mtoon', {})
    mode = mtoon.get('outlineWidthMode', 'none')
    width = mtoon.get('outlineWidthFactor', 0.)
    if mode == 'none' or width == 0:
        return None
    if mode != 'worldCoordinates':
        raise ValueError('Screen-coordinate MToon outlines require a runtime width pass; world-coordinate outlines are supported')
    if not np.isfinite(width) or width < 0:
        raise ValueError('Invalid MToon outline width')
    mask = np.ones(len(uvs))
    if 'outlineWidthMultiplyTexture' in mtoon:
        synthetic = {'extensions': {'VRMC_materials_mtoon': {
            'shadeMultiplyTexture': mtoon['outlineWidthMultiplyTexture'], 'shadeColorFactor': [1, 1, 1]}}}
        image, _ = shade_image(document, binary, synthetic)
        values = np.asarray(image)[..., 1]/255.
        height, columns = values.shape
        uv = np.asarray(uvs, dtype=float)
        def addressed(index, count, mode):
            if mode == 33071:
                return np.clip(index, 0, count-1)
            if mode == 33648:
                result = index % (2*count)
                return np.where(result < count, result, 2*count-1-result)
            return index % count
        x, y = uv[:, 0]*columns-.5, uv[:, 1]*height-.5
        ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
        wx, wy = x-ix, y-iy
        u, v = image.info['wrap']
        def sample(dx, dy):
            return values[addressed(iy+dy, height, v), addressed(ix+dx, columns, u)]
        mask = ((sample(0, 0)*(1-wx)+sample(1, 0)*wx)*(1-wy)
                +(sample(0, 1)*(1-wx)+sample(1, 1)*wx)*wy)
    return width*UNITS_PER_METRE*mask


def outline_name(source):
    return PREFIX+hashlib.sha256(source.encode()).hexdigest()[:12]


def create_hull(path, source_name, widths, control):
    name = outline_name(source_name)
    with NifFile(str(path.resolve())) as nif:
        original = next(s for s in nif.shapes if s.name == source_name)
        normals = np.asarray(original.normals, dtype=float)
        normals /= np.maximum(np.linalg.norm(normals, axis=1)[:, None], 1e-12)
        vertices = np.asarray(original.verts)+normals*np.asarray(widths)[:, None]
        triangles = np.asarray(original.tris)[:, [0, 2, 1]]
        # Reversed faces implement front-face culling without a global state hook.
        hull = nif.createShapeFromData(name, [tuple(v) for v in vertices], [tuple(t) for t in triangles], original.uvs, original.normals,
                                       parent=original.parent)
        hull.transform = original.transform
        props = hull.shader.properties
        for field in ['Shader_Type', 'Shader_Flags_1', 'Shader_Flags_2', 'Emissive_Mult', 'Alpha']:
            setattr(props, field, getattr(original.shader.properties, field))
        props.Shader_Flags_2 &= ~(1 << 4)  # Hull must cull one side, even for double-sided source hair.
        props.Shader_Flags_1 &= ~(1 << 9)  # Generated shell must not cast an enlarged shadow.
        props.Emissive_Color[:] = (0., 0., 0., 1.)
        props.Emissive_Mult = 0.
        hull.shader.write_properties()
        for key, value in original.shader.textures.items():
            if value:
                hull.set_texture(key, value)
        hull.set_texture('Glow', control.replace('/', '\\'))
        if original.colors:
            hull.set_colors(original.colors)
        if original.has_skin_instance:
            hull.skin()
            hull.set_global_to_skin(original.global_to_skin)
            names = original.bone_names
            binds = {bone: original.get_shape_skin_to_bone(bone) for bone in names}
            weights = original.bone_weights
            for bone in names:
                node = nif.nodes[bone]
                hull.add_bone(bone, node.transform, node.parent.name if node.parent else None)
            for bone in names:
                hull.set_skin_to_bone_xform(bone, binds[bone])
                hull.setShapeWeights(bone, weights[bone])
            if original.partitions:
                hull.set_partitions(original.partitions, original.partition_tris)
            else:
                hull.demote_skin_instance()
        if original.has_alpha_property:
            hull.has_alpha_property = True
            hull.alpha_property.properties.flags = original.alpha_property.properties.flags
            hull.alpha_property.properties.threshold = original.alpha_property.properties.threshold
            hull.save_alpha_property()
        nif.save()
    logging.info('MToon outline: %s / %s, %d vertices, width %.6f..%.6f game units',
                 path.name, source_name, len(widths), float(min(widths)), float(max(widths)))
    return name


def order_hulls(path, entries):
    owners = {e['shape']: e['source_shape'] for e in entries}
    with NifFile(str(path.resolve())) as nif:
        by_name = {s.name: s for s in nif.shapes}
        for parent in {s.parent.name for s in nif.shapes if s.name in owners}:
            node = nif.nodes[parent]
            ids = children(nif, node)
            hulls = {by_name[name].id for name in owners if by_name[name].parent.name == parent}
            before = {}
            for name, owner in owners.items():
                if by_name[name].parent.name == parent:
                    before.setdefault(by_name[owner].id, []).append(by_name[name].id)
            ordered = []
            for ident in ids:
                if ident not in hulls:
                    ordered.extend(before.get(ident, []))
                    ordered.append(ident)
            set_children(nif, node, ordered)
        nif.save()


def validate_hull(nif, entry):
    hull = next((s for s in nif.shapes if s.name == entry['shape']), None)
    original = next((s for s in nif.shapes if s.name == entry['source_shape']), None)
    if hull is None or original is None or hull.parent.name != original.parent.name:
        raise ValueError('MToon outline lost its source owner')
    delta = np.asarray(hull.verts)-np.asarray(original.verts)
    if hashlib.sha256(np.asarray(delta, dtype='<f4').tobytes()).hexdigest() != entry['offset_sha256']:
        raise ValueError('MToon outline vertex offsets changed')
    if not np.array_equal(hull.tris, np.asarray(original.tris)[:, [0, 2, 1]]) or not np.array_equal(hull.uvs, original.uvs):
        raise ValueError('MToon outline topology/UV differs from its source')
    if not np.array_equal(hull.normals, original.normals) or not np.array_equal(hull.colors, original.colors):
        raise ValueError('MToon outline normal/colour differs from its source')
    if bytes(hull.transform) != bytes(original.transform) or hull.partition_tris != original.partition_tris:
        raise ValueError('MToon outline transform/partitions differ from its source')
    if [(p.id, p.flags) for p in hull.partitions] != [(p.id, p.flags) for p in original.partitions]:
        raise ValueError('MToon outline body partitions differ from its source')
    if hull.has_alpha_property != original.has_alpha_property:
        raise ValueError('MToon outline alpha differs from its source')
    if original.has_alpha_property and (hull.alpha_property.properties.flags != original.alpha_property.properties.flags
                                      or hull.alpha_property.properties.threshold != original.alpha_property.properties.threshold):
        raise ValueError('MToon outline alpha controls differ from its source')
    if hull.bone_names != original.bone_names or hull.bone_weights != original.bone_weights:
        raise ValueError('MToon outline skin differs from its source')
    if bytes(hull.global_to_skin) != bytes(original.global_to_skin):
        raise ValueError('MToon outline skin transform changed')
    for bone in original.bone_names:
        if bytes(hull.get_shape_skin_to_bone(bone)) != bytes(original.get_shape_skin_to_bone(bone)):
            raise ValueError('MToon outline bone bind changed: '+bone)
    if hull.shader.properties.Shader_Flags_2 & (1 << 4) or hull.shader.properties.Shader_Flags_1 & (1 << 9):
        raise ValueError('MToon outline must use single-sided culling')
    ordered = children(nif, original.parent)
    if ordered.index(hull.id)+1 != ordered.index(original.id):
        raise ValueError('MToon outline lost its source draw order')
