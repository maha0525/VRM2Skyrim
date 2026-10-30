"""Blender Cycles MToon node graph for VRM avatar and outline previews."""
import hashlib
import json
import logging
from pathlib import Path

import numpy as np

try:
    import bpy
except ImportError:  # pragma: no cover - imported outside Blender in unit tests
    bpy = None

from inspect_vrm import read_glb
from nif_materials import normalize_material_colors
from toon import parameters_for

LOG = logging.getLogger(__name__)
PREFIX = 'V2SOutline_'
UNITS_PER_METRE = 70.0
EXTENSION_MAP = {10497: 'REPEAT', 33071: 'EXTEND', 33648: 'MIRROR'}
FLOAT_FIELDS = ('rim_r', 'rim_g', 'rim_b', 'rim_power', 'rim_lift', 'rim_mix',
                'outline_r', 'outline_g', 'outline_b', 'outline_mix')
# Camera-space directional light vector (slightly right, above, and in front of the viewer).
CAMERA_LIGHT_DIRECTION = (0.321806, 0.422371, 0.854798)


def outline_name(shape_name):
    return PREFIX + hashlib.sha256(shape_name.encode('utf8')).hexdigest()[:12]


def effects_for(material, outline=False):
    mtoon = material.get('extensions', {}).get('VRMC_materials_mtoon', {})
    values = [*mtoon.get('parametricRimColorFactor', [0, 0, 0]),
              mtoon.get('parametricRimFresnelPowerFactor', 5.), mtoon.get('parametricRimLiftFactor', 0.),
              mtoon.get('rimLightingMixFactor', 1.), *mtoon.get('outlineColorFactor', [0, 0, 0]),
              mtoon.get('outlineLightingMixFactor', 1.)]
    result = dict(zip(FLOAT_FIELDS, values))
    result['normal_scale'] = material.get('normalTexture', {}).get('scale', 1.)
    if len(values) != len(FLOAT_FIELDS) or not all(np.isfinite(v) for v in result.values()):
        raise ValueError('Invalid authored MToon effect controls')
    result['outline'] = bool(outline)
    return result


def _toon_shade_fallback(shade):
    peak = max(shade[0], shade[1], shade[2])
    scale = min(1.0, 0.55 / max(peak, 0.0001))
    return [c * scale for c in shade]


def _load_glb_texture(cache_dir, document, binary, tex_info, colorspace='sRGB'):
    if not isinstance(tex_info, dict) or 'index' not in tex_info or document is None or binary is None:
        return None
    texture = document.get('textures', [])[tex_info['index']]
    if 'source' not in texture:
        return None
    image_info = document.get('images', [])[texture['source']]
    if 'bufferView' not in image_info:
        return None
    view = document['bufferViews'][image_info['bufferView']]
    offset = view.get('byteOffset', 0)
    blob = binary[offset:offset + view['byteLength']]
    ext = '.jpg' if image_info.get('mimeType') == 'image/jpeg' else '.png'
    digest = hashlib.sha256(blob).hexdigest()[:16]
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f'{digest}{ext}'
    if not path.is_file():
        path.write_bytes(blob)
    sampler = document.get('samplers', [])[texture['sampler']] if 'sampler' in texture else {}
    wrap = [sampler.get('wrapS', 10497), sampler.get('wrapT', 10497)]
    image = bpy.data.images.load(str(path), check_existing=True)
    image.colorspace_settings.name = colorspace
    return image, wrap


def _load_source_glb(output, source_glb=None):
    for candidate in (source_glb, Path(output) / 'source.glb', Path(output) / 'preview-source.glb'):
        if candidate and Path(candidate).is_file():
            document, binary = read_glb(candidate)
            normalize_material_colors(document)
            return document, binary
    return None, None


def _is_baked_preview_image(image):
    return bool(image and image.filepath and 'dds-preview' in Path(image.filepath).parts)


def _find_base_texture_node(tree, policy=None):
    if policy is not None and 'baseColorTexture' not in policy.get('pbrMetallicRoughness', {}):
        return None, False
    diffuse = tree.nodes.get('Diffuse_Texture')
    if diffuse is not None and diffuse.type == 'TEX_IMAGE' and diffuse.image is not None:
        return diffuse, True
    from blender_meshes import linked_texture_nodes
    for node_type, socket_name in (('BSDF_PRINCIPLED', 'Base Color'), ('EMISSION', 'Color'), ('BACKGROUND', 'Color')):
        shader = next((n for n in tree.nodes if n.type == node_type), None)
        if shader is not None and socket_name in shader.inputs:
            found = linked_texture_nodes(shader.inputs[socket_name])
            if found:
                return found[0], _is_baked_preview_image(found[0].image)
    return None, False


def _add_rgb_multiply(tree, socket_a, color_b):
    mix = tree.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Factor'].default_value = 1.0
    if isinstance(socket_a, (tuple, list)):
        mix.inputs['A'].default_value = (*socket_a[:3], 1.0)
    else:
        tree.links.new(socket_a, mix.inputs['A'])
    if isinstance(color_b, (tuple, list)):
        mix.inputs['B'].default_value = (*color_b[:3], 1.0)
    else:
        tree.links.new(color_b, mix.inputs['B'])
    return mix.outputs['Result']


def _add_rgb_mix(tree, factor, color_a, color_b, blend_type='MIX', clamp=True):
    mix = tree.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = blend_type
    mix.clamp_factor = clamp
    if isinstance(factor, (int, float)):
        mix.inputs['Factor'].default_value = float(factor)
    else:
        tree.links.new(factor, mix.inputs['Factor'])
    if isinstance(color_a, (tuple, list)):
        mix.inputs['A'].default_value = (*color_a[:3], 1.0)
    else:
        tree.links.new(color_a, mix.inputs['A'])
    if isinstance(color_b, (tuple, list)):
        mix.inputs['B'].default_value = (*color_b[:3], 1.0)
    else:
        tree.links.new(color_b, mix.inputs['B'])
    return mix.outputs['Result']


def _add_math(tree, operation, a, b=None, clamp=False):
    node = tree.nodes.new('ShaderNodeMath')
    node.operation = operation
    node.use_clamp = clamp
    if isinstance(a, (int, float)):
        node.inputs[0].default_value = float(a)
    else:
        tree.links.new(a, node.inputs[0])
    if b is not None:
        if isinstance(b, (int, float)):
            node.inputs[1].default_value = float(b)
        else:
            tree.links.new(b, node.inputs[1])
    return node.outputs['Value']


def _make_tex_node(tree, image, wrap=None):
    node = tree.nodes.new('ShaderNodeTexImage')
    node.image = image
    if wrap and wrap[0] in EXTENSION_MAP:
        node.extension = EXTENSION_MAP[wrap[0]]
    return node


def _sample_outline_width_mask(image, wrap, uvs):
    columns, height = image.size
    if columns <= 0 or height <= 0:
        return np.ones(len(uvs), dtype=np.float32)
    # Blender image.pixels is bottom-up RGBA, matching Blender's bottom-up UV coordinates.
    values = np.asarray(image.pixels[:], dtype=np.float32).reshape((height, columns, 4))[..., 1]
    uv = np.asarray(uvs, dtype=np.float64)

    def addressed(index, count, mode):
        if mode == 33071:
            return np.clip(index, 0, count - 1)
        if mode == 33648:
            result = index % (2 * count)
            return np.where(result < count, result, 2 * count - 1 - result)
        return index % count

    x, y = uv[:, 0] * columns - 0.5, uv[:, 1] * height - 0.5
    ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
    wx, wy = x - ix, y - iy
    u_mode, v_mode = wrap if wrap else (10497, 10497)

    def sample(dx, dy):
        return values[addressed(iy + dy, height, v_mode), addressed(ix + dx, columns, u_mode)]

    return ((sample(0, 0) * (1 - wx) + sample(1, 0) * wx) * (1 - wy)
            + (sample(0, 1) * (1 - wx) + sample(1, 1) * wx) * wy).astype(np.float32)


def _vertex_uvs(mesh):
    n_verts = len(mesh.vertices)
    uvs = np.zeros((n_verts, 2), dtype=np.float32)
    uv_layer = mesh.uv_layers.active
    if uv_layer is None or not len(mesh.loops):
        return uvs
    n_loops = len(mesh.loops)
    loop_verts = np.empty(n_loops, dtype=np.int32)
    loop_uvs = np.empty(n_loops * 2, dtype=np.float32)
    mesh.loops.foreach_get('vertex_index', loop_verts)
    uv_layer.data.foreach_get('uv', loop_uvs)
    # Assign in reverse so the first loop of each vertex wins deterministically.
    uvs[loop_verts[::-1]] = loop_uvs.reshape((-1, 2))[::-1]
    return uvs


def _transparent_non_outline_material():
    name = 'V2S_TransparentNonOutline'
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new('ShaderNodeOutputMaterial')
    trans = tree.nodes.new('ShaderNodeBsdfTransparent')
    tree.links.new(trans.outputs['BSDF'], out.inputs['Surface'])
    return mat


def _slot_outline_widths(cache_dir, document, binary, mesh, policy, uvs, units_per_metre):
    mtoon = policy.get('extensions', {}).get('VRMC_materials_mtoon', {})
    if not isinstance(mtoon, dict):
        return None
    mode = mtoon.get('outlineWidthMode', 'none')
    width = float(mtoon.get('outlineWidthFactor', 0.0))
    if mode != 'worldCoordinates' or not np.isfinite(width) or width <= 0.0:
        return None
    mask = np.ones(len(mesh.vertices), dtype=np.float32)
    if 'outlineWidthMultiplyTexture' in mtoon and document is not None and binary is not None:
        try:
            loaded = _load_glb_texture(cache_dir, document, binary, mtoon['outlineWidthMultiplyTexture'], 'Non-Color')
            if loaded is not None:
                mask = _sample_outline_width_mask(loaded[0], loaded[1], uvs)
        except Exception as exc:
            LOG.warning('Falling back to unmasked outline width for %s: %s', mesh.name, exc)
    return width * float(units_per_metre) * mask


def ensure_preview_outline_meshes(output, meshes, document=None, binary=None, units_per_metre=UNITS_PER_METRE):
    """Create inverted-hull V2SOutline_* preview objects when the scene does not already include them."""
    if bpy is None:
        return []
    cache_dir = Path(output) / 'toon-preview-cache'
    existing_names = {o.name for o in bpy.context.scene.objects}
    created = []
    for obj in list(meshes):
        if obj.type != 'MESH' or obj.hide_render or obj.name.startswith(PREFIX) or not len(obj.data.vertices):
            continue
        hull_name = outline_name(obj.name)
        if hull_name in existing_names:
            continue
        uvs = None
        slot_widths = {}
        for index, mat in enumerate(obj.data.materials):
            if not mat or not mat.get('V2S_Preview_Policy'):
                continue
            policy = json.loads(mat['V2S_Preview_Policy'])
            if uvs is None:
                uvs = _vertex_uvs(obj.data)
            widths = _slot_outline_widths(cache_dir, document, binary, obj.data, policy, uvs, units_per_metre)
            if widths is not None:
                slot_widths[index] = (widths, policy)
        if not slot_widths:
            continue

        hull_mesh = obj.data.copy()
        n_verts = len(hull_mesh.vertices)
        verts = np.empty(n_verts * 3, dtype=np.float32)
        norms = np.empty(n_verts * 3, dtype=np.float32)
        hull_mesh.vertices.foreach_get('co', verts)
        hull_mesh.vertices.foreach_get('normal', norms)
        verts = verts.reshape((-1, 3))
        norms = norms.reshape((-1, 3))
        norms = norms / np.maximum(np.linalg.norm(norms, axis=1)[:, None], 1e-12)

        if len(slot_widths) == 1 and len(obj.data.materials) <= 1:
            vertex_widths = next(iter(slot_widths.values()))[0]
        else:
            vertex_widths = np.zeros(n_verts, dtype=np.float32)
            for poly in hull_mesh.polygons:
                if poly.material_index in slot_widths:
                    w = slot_widths[poly.material_index][0]
                    for v_idx in poly.vertices:
                        vertex_widths[v_idx] = w[v_idx]

        verts = verts + norms * vertex_widths[:, None]
        hull_mesh.vertices.foreach_set('co', verts.reshape(-1))
        hull_mesh.flip_normals()
        hull_mesh.normals_split_custom_set_from_vertices(norms.tolist())
        hull_mesh.update()

        hull_obj = obj.copy()
        hull_obj.data = hull_mesh
        hull_obj.name = hull_name
        hull_obj.visible_shadow = False
        for index, mat in enumerate(hull_obj.data.materials):
            if index in slot_widths and mat is not None:
                mat_copy = mat.copy()
                mat_copy.name = f'{hull_name}_OutlineMat_{index}'
                mat_copy['V2S_Preview_Outline'] = True
                mat_copy['V2S_Preview_Policy'] = json.dumps(slot_widths[index][1])
                hull_obj.data.materials[index] = mat_copy
            else:
                hull_obj.data.materials[index] = _transparent_non_outline_material()
        collections = obj.users_collection or (bpy.context.scene.collection,)
        for col in collections:
            col.objects.link(hull_obj)
        existing_names.add(hull_name)
        meshes.append(hull_obj)
        created.append(hull_obj)
    return created


def assign_toon_shape_policies(output, meshes):
    """Ensure split skin, clothing skin, and V2SOutline_* shapes carry their source V2S_Preview_Policy."""
    output = Path(output)
    manifest_path = output / 'appearance.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf8')) if manifest_path.is_file() else {'components': []}
    shape_policies = {}
    for comp in manifest.get('components', []):
        for shape in comp.get('shapes', []):
            if 'material_policy' in shape:
                shape_policies[shape['name']] = shape['material_policy']
                shape_policies[outline_name(shape['name'])] = shape['material_policy']
    toon_path = output / 'toon.json'
    if toon_path.is_file():
        toon_report = json.loads(toon_path.read_text(encoding='utf8'))
        for entry in toon_report.get('materials', []):
            source_name = entry.get('source_shape') or entry.get('shape')
            if source_name in shape_policies:
                shape_policies[entry['shape']] = shape_policies[source_name]

    for obj in meshes:
        if obj.type != 'MESH':
            continue
        is_outline = obj.name.startswith(PREFIX)
        if is_outline:
            obj.visible_shadow = False
        fallback_policy = shape_policies.get(obj.name)
        if fallback_policy is None and obj.name.startswith('OriginalSkin_'):
            # OriginalSkin_<source_name>_<slot> in fitted armor NIFs
            middle = obj.name[len('OriginalSkin_'):].rsplit('_', 1)[0]
            fallback_policy = shape_policies.get(middle)
        for index, mat in enumerate(obj.data.materials):
            if mat is None:
                continue
            raw_policy = mat.get('V2S_Preview_Policy')
            policy = json.loads(raw_policy) if raw_policy else fallback_policy
            if policy is None:
                continue
            if is_outline and not mat.get('V2S_Preview_Outline'):
                mat = mat.copy()
                mat.name = f'{obj.name}_OutlineMat'
                obj.data.materials[index] = mat
                mat['V2S_Preview_Outline'] = True
            mat['V2S_Preview_Policy'] = json.dumps(policy)


def build_toon_material_nodes(material, output, document=None, binary=None):
    """Replace a material's surface graph with an MToon Cycles shader matching Community Shaders."""
    if not material or not material.use_nodes or not material.get('V2S_Preview_Policy'):
        return False
    if material.get('V2S_Toon_Built'):
        return True
    policy = json.loads(material['V2S_Preview_Policy'])
    is_outline = bool(material.get('V2S_Preview_Outline', False))
    tree = material.node_tree
    outputs = [n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL']
    output_node = next((n for n in outputs if n.is_active_output), outputs[0] if outputs else None)
    if output_node is None:
        return False

    # Remove existing BackfaceCulling wrapper if present so we rebuild cleanly and wrap at the end.
    culling = tree.nodes.get('V2S_BackfaceCulling')
    if culling is not None:
        tree.nodes.remove(culling)

    base_tex_node, baked_rgb = _find_base_texture_node(tree, policy=policy)
    pbr = policy.get('pbrMetallicRoughness', {})
    base_factor = pbr.get('baseColorFactor', [1.0, 1.0, 1.0, 1.0])
    alpha_mode = policy.get('alphaMode', 'OPAQUE')
    if base_tex_node is not None and base_tex_node.image is not None:
        base_tex_node['V2S_BaseColor'] = True
        if alpha_mode in ('MASK', 'BLEND') and base_tex_node.image.filepath:
            try:
                base_tex_node.image.alpha_mode = 'STRAIGHT'
            except AttributeError:
                pass
        lit_socket = (base_tex_node.outputs['Color'] if baked_rgb or tuple(base_factor[:3]) == (1.0, 1.0, 1.0)
                      else _add_rgb_multiply(tree, base_tex_node.outputs['Color'], base_factor[:3]))
        alpha_socket = (_add_math(tree, 'MULTIPLY', base_tex_node.outputs['Alpha'], base_factor[3], clamp=True)
                        if base_factor[3] < 0.9999 else base_tex_node.outputs['Alpha'])
    else:
        rgb_node = tree.nodes.new('ShaderNodeRGB')
        rgb_node.outputs['Color'].default_value = (*base_factor[:3], 1.0)
        lit_socket = rgb_node.outputs['Color']
        alpha_socket = float(base_factor[3])

    mtoon = policy.get('extensions', {}).get('VRMC_materials_mtoon')
    authored = isinstance(mtoon, dict)
    params = parameters_for(policy, strength=0.0 if authored else 0.15, authored=authored)
    toony = float(params['toony'])
    shift = float(params['shift'])
    gi_eq = float(params['gi_equalization'])

    cache_dir = Path(output) / 'toon-preview-cache'
    shade_img = matcap_img = rim_mask_img = normal_img = None
    if authored and document is not None and binary is not None:
        try:
            shade_img = _load_glb_texture(cache_dir, document, binary, mtoon.get('shadeMultiplyTexture'), 'sRGB')
            if any(mtoon.get('matcapFactor', [1.0, 1.0, 1.0])):
                matcap_img = _load_glb_texture(cache_dir, document, binary, mtoon.get('matcapTexture'), 'sRGB')
            rim_mask_img = _load_glb_texture(cache_dir, document, binary, mtoon.get('rimMultiplyTexture'), 'sRGB')
            normal_img = _load_glb_texture(cache_dir, document, binary, policy.get('normalTexture'), 'Non-Color')
        except Exception as exc:
            LOG.warning('Falling back to factor MToon preview for %s: %s', material.name, exc)

    geom = tree.nodes.new('ShaderNodeNewGeometry')
    double_sided = False if is_outline else bool(policy.get('doubleSided', False))

    # Normal vector (with optional normal map and double-sided backface flip)
    if normal_img is not None:
        norm_tex = _make_tex_node(tree, normal_img[0], normal_img[1])
        norm_map = tree.nodes.new('ShaderNodeNormalMap')
        norm_map.inputs['Strength'].default_value = float(policy.get('normalTexture', {}).get('scale', 1.0))
        tree.links.new(norm_tex.outputs['Color'], norm_map.inputs['Color'])
        normal_socket = norm_map.outputs['Normal']
    else:
        normal_socket = geom.outputs['Normal']

    if double_sided:
        neg_norm = tree.nodes.new('ShaderNodeVectorMath')
        neg_norm.operation = 'SCALE'
        neg_norm.inputs['Scale'].default_value = -1.0
        tree.links.new(normal_socket, neg_norm.inputs[0])
        flip_mix = tree.nodes.new('ShaderNodeMix')
        flip_mix.data_type = 'VECTOR'
        tree.links.new(geom.outputs['Backfacing'], flip_mix.inputs['Factor'])
        tree.links.new(normal_socket, flip_mix.inputs['A'])
        tree.links.new(neg_norm.outputs['Vector'], flip_mix.inputs['B'])
        normal_socket = flip_mix.outputs['Result']

    # Camera-relative main directional light vector in World space
    light_dir = tree.nodes.new('ShaderNodeVectorTransform')
    light_dir.vector_type = 'NORMAL'
    light_dir.convert_from = 'CAMERA'
    light_dir.convert_to = 'WORLD'
    light_dir.inputs['Vector'].default_value = CAMERA_LIGHT_DIRECTION

    ndotl = tree.nodes.new('ShaderNodeVectorMath')
    ndotl.operation = 'DOT_PRODUCT'
    tree.links.new(normal_socket, ndotl.inputs[0])
    tree.links.new(light_dir.outputs['Vector'], ndotl.inputs[1])

    width = max(0.0001 if authored else 0.02, 1.0 - toony)
    band_num = _add_math(tree, 'ADD', ndotl.outputs['Value'], shift + width)
    band = _add_math(tree, 'DIVIDE', band_num, 2.0 * width, clamp=True)

    # Ambient ratio matching V2SToonResolveAuthored / V2SToonResolve
    ambient_ratio = 0.14 + 0.16 * gi_eq
    direct_ratio = 1.0 - ambient_ratio

    if authored:
        shade_factor = mtoon.get('shadeColorFactor', [0.75, 0.77, 0.85])
        if shade_img is not None:
            shade_tex = _make_tex_node(tree, shade_img[0], shade_img[1])
            shade_surface = (shade_tex.outputs['Color'] if tuple(shade_factor[:3]) == (1.0, 1.0, 1.0)
                             else _add_rgb_multiply(tree, shade_tex.outputs['Color'], shade_factor[:3]))
        elif 'shadeMultiplyTexture' in mtoon and base_tex_node is not None:
            shade_surface = _add_rgb_multiply(tree, base_tex_node.outputs['Color'], shade_factor[:3])
        else:
            shade_surface = shade_factor[:3]
        shaded_band = _add_rgb_mix(tree, ambient_ratio, shade_surface, lit_socket)
        surface = _add_rgb_mix(tree, band, shaded_band, lit_socket)
    else:
        shade_mult = _toon_shade_fallback(params['shade'])
        eff_shade = [direct_ratio * s + ambient_ratio for s in shade_mult]
        shaded_band = _add_rgb_multiply(tree, lit_socket, eff_shade)
        surface = _add_rgb_mix(tree, band, shaded_band, lit_socket)

    if authored:
        effects = effects_for(policy, outline=is_outline)
        rim_term = None
        if matcap_img is not None:
            cam_norm = tree.nodes.new('ShaderNodeVectorTransform')
            cam_norm.vector_type = 'NORMAL'
            cam_norm.convert_from = 'WORLD'
            cam_norm.convert_to = 'CAMERA'
            tree.links.new(normal_socket, cam_norm.inputs['Vector'])
            sep = tree.nodes.new('ShaderNodeSeparateXYZ')
            tree.links.new(cam_norm.outputs['Vector'], sep.inputs['Vector'])
            u = _add_math(tree, 'MULTIPLY', sep.outputs['X'], 0.495)
            u = _add_math(tree, 'ADD', u, 0.5, clamp=True)
            v = _add_math(tree, 'MULTIPLY', sep.outputs['Y'], 0.495)
            v = _add_math(tree, 'ADD', v, 0.5, clamp=True)
            comb = tree.nodes.new('ShaderNodeCombineXYZ')
            tree.links.new(u, comb.inputs['X'])
            tree.links.new(v, comb.inputs['Y'])
            mcap_tex = _make_tex_node(tree, matcap_img[0], matcap_img[1])
            tree.links.new(comb.outputs['Vector'], mcap_tex.inputs['Vector'])
            matcap_factor = mtoon.get('matcapFactor', [1.0, 1.0, 1.0])
            rim_term = (mcap_tex.outputs['Color'] if tuple(matcap_factor[:3]) == (1.0, 1.0, 1.0)
                        else _add_rgb_multiply(tree, mcap_tex.outputs['Color'], matcap_factor[:3]))

        rim_color = [effects[k] for k in ('rim_r', 'rim_g', 'rim_b')]
        if any(c > 1e-5 for c in rim_color):
            ndotv = tree.nodes.new('ShaderNodeVectorMath')
            ndotv.operation = 'DOT_PRODUCT'
            tree.links.new(normal_socket, ndotv.inputs[0])
            tree.links.new(geom.outputs['Incoming'], ndotv.inputs[1])
            one_minus = _add_math(tree, 'SUBTRACT', 1.0, ndotv.outputs['Value'])
            lifted = _add_math(tree, 'ADD', one_minus, effects['rim_lift'], clamp=True)
            fresnel = _add_math(tree, 'POWER', lifted, max(effects['rim_power'], 1e-5), clamp=True)
            param_rim = _add_rgb_mix(tree, fresnel, (0.0, 0.0, 0.0), rim_color)
            rim_term = param_rim if rim_term is None else _add_rgb_mix(tree, 1.0, rim_term, param_rim, blend_type='ADD')

        if rim_term is not None:
            if rim_mask_img is not None:
                rmask_tex = _make_tex_node(tree, rim_mask_img[0], rim_mask_img[1])
                rim_term = _add_rgb_multiply(tree, rim_term, rmask_tex.outputs['Color'])
            # Lighting mix modulation: lerp(1.0, direct_ratio * band + ambient_ratio, rim_mix)
            lit_exposure = _add_math(tree, 'MULTIPLY', band, direct_ratio)
            lit_exposure = _add_math(tree, 'ADD', lit_exposure, ambient_ratio, clamp=True)
            rim_mod = _add_math(tree, 'MULTIPLY', lit_exposure, effects['rim_mix'])
            rim_mod = _add_math(tree, 'ADD', rim_mod, 1.0 - effects['rim_mix'], clamp=True)
            rim_term = _add_rgb_mix(tree, rim_mod, (0.0, 0.0, 0.0), rim_term)
            surface = _add_rgb_mix(tree, 1.0, surface, rim_term, blend_type='ADD')

        if is_outline:
            outline_color = [effects[k] for k in ('outline_r', 'outline_g', 'outline_b')]
            mixed = _add_rgb_mix(tree, effects['outline_mix'], (1.0, 1.0, 1.0), surface)
            surface = _add_rgb_multiply(tree, mixed, outline_color)

    emission = tree.nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = 1.0
    tree.links.new(surface, emission.inputs['Color'])
    final_shader = emission.outputs['Emission']

    if alpha_mode == 'MASK':
        cutoff = float(policy.get('alphaCutoff', 0.5))
        is_transparent = _add_math(tree, 'LESS_THAN', alpha_socket, cutoff)
        transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
        mix_shader = tree.nodes.new('ShaderNodeMixShader')
        tree.links.new(is_transparent, mix_shader.inputs[0])
        tree.links.new(final_shader, mix_shader.inputs[1])
        tree.links.new(transparent.outputs['BSDF'], mix_shader.inputs[2])
        final_shader = mix_shader.outputs['Shader']
    elif alpha_mode == 'BLEND':
        transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
        mix_shader = tree.nodes.new('ShaderNodeMixShader')
        if isinstance(alpha_socket, (int, float)):
            mix_shader.inputs[0].default_value = float(alpha_socket)
        else:
            tree.links.new(alpha_socket, mix_shader.inputs[0])
        tree.links.new(transparent.outputs['BSDF'], mix_shader.inputs[1])
        tree.links.new(final_shader, mix_shader.inputs[2])
        final_shader = mix_shader.outputs['Shader']

    tree.links.new(final_shader, output_node.inputs['Surface'])
    material['V2S_Toon_Built'] = True
    from blender_meshes import preview_face_culling
    preview_face_culling(material, double_sided=double_sided)
    return True


def apply_toon_preview(output, meshes=None, source_glb=None, units_per_metre=UNITS_PER_METRE):
    """Apply MToon preview shader nodes and outline hulls to all VRM-owned materials in the current scene."""
    output = Path(output)
    if meshes is None:
        meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH' and not o.hide_render]
    assign_toon_shape_policies(output, meshes)
    document, binary = _load_source_glb(output, source_glb=source_glb)
    ensure_preview_outline_meshes(output, meshes, document=document, binary=binary, units_per_metre=units_per_metre)
    materials = {m for obj in meshes if obj.type == 'MESH' and not obj.hide_render
                 for m in obj.data.materials if m and m.get('V2S_Preview_Policy')}
    count = 0
    for material in sorted(materials, key=lambda m: m.name):
        if build_toon_material_nodes(material, output, document=document, binary=binary):
            count += 1
    LOG.info('Applied MToon preview shader to %d materials', count)
    return count
