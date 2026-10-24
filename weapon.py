"""Original GLB weapon: inputs, PBR textures, private WEAP/STAT records and output checks."""
import copy
import hashlib
import io
import json
import logging
import math
from pathlib import Path
import shutil
import struct

import numpy as np
from PIL import Image

from inspect_vrm import primitive_triangles, read_glb, write_glb

WEAPON_ID = 0x010008D0
FIRST_PERSON_ID = 0x010008D1
# Fields replaced or removed on the copied base WEAP; every other field is copied unchanged.
CHANGED_FIELDS = {b'EDID', b'FULL', b'MODL', b'WNAM', b'OBND', b'MODT', b'DESC', b'CNAM'}
STATIC_CHANGED_FIELDS = {b'EDID', b'MODL', b'OBND', b'MODT'}
ENVIRONMENT_MAP = 'textures/cubemaps/shinydull_e.dds'
ENVIRONMENT_MAP_NIF = 'textures\\cubemaps\\ShinyDull_e.dds'
METAL_THRESHOLD = .5
METAL_COVERAGE = .01
# glTF and the official SteelSword/ForswornStaff/SteelMace normal maps read with the
# same green direction (2026-10-25). Flip here if in-game shading looks inverted.
FLIP_NORMAL_GREEN = False


def text(value):
    return value.encode('utf8') + b'\0'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def skyrim_normal(image):
    """glTF normal-map RGB as Skyrim normal-map RGB; the only green-channel decision."""
    red, green, blue = image.convert('RGB').split()
    if FLIP_NORMAL_GREEN:
        green = green.point(lambda value: 255 - value)
    return Image.merge('RGB', (red, green, blue))


def scene_primitives(document):
    """(node, primitive) pairs of the default scene, as Blender's glTF importer loads them."""
    nodes = document.get('nodes', [])
    scenes = document.get('scenes', [])
    roots = scenes[document.get('scene', 0)].get('nodes', []) if scenes else range(len(nodes))
    active, stack = set(), list(roots)
    while stack:
        index = stack.pop()
        if index not in active:
            active.add(index)
            stack.extend(nodes[index].get('children', []))
    return [(index, primitive) for index in sorted(active) if 'mesh' in nodes[index]
            for primitive in document['meshes'][nodes[index]['mesh']]['primitives']]


def used_materials(document):
    used = {primitive.get('material') for _, primitive in scene_primitives(document)}
    return sorted(used, key=lambda index: (index is None, index or 0))


def check_document(document):
    """ValueError unless the glTF JSON has the shape the weapon steps index into (uploads are untrusted)."""
    if not isinstance(document, dict):
        raise ValueError('The GLB JSON is not an object')

    def items(key):
        value = document.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise ValueError(f'glTF {key} must be a list of objects')
        return value

    def index(value, collection, name):
        if type(value) is not int or not 0 <= value < len(collection):
            raise ValueError(f'glTF {name} index is invalid')

    def texture(info):
        if not isinstance(info, dict):
            raise ValueError('glTF texture reference must be an object')
        index(info.get('index'), textures, 'texture')

    scenes, nodes, meshes, accessors, views = (items(k) for k in ('scenes', 'nodes', 'meshes', 'accessors', 'bufferViews'))
    buffers, materials, textures, images = (items(k) for k in ('buffers', 'materials', 'textures', 'images'))
    if scenes:
        index(document.get('scene', 0), scenes, 'scene')
    for scene in scenes:
        if not isinstance(scene.get('nodes', []), list):
            raise ValueError('glTF scene nodes must be a list')
        for node in scene.get('nodes', []):
            index(node, nodes, 'node')
    for node in nodes:
        if not isinstance(node.get('children', []), list):
            raise ValueError('glTF node children must be a list')
        for child in node.get('children', []):
            index(child, nodes, 'node')
        if 'mesh' in node:
            index(node['mesh'], meshes, 'mesh')
    for mesh in meshes:
        primitives = mesh.get('primitives')
        if not isinstance(primitives, list) or not all(isinstance(p, dict) for p in primitives):
            raise ValueError('glTF mesh primitives must be a list of objects')
        for primitive in primitives:
            if not isinstance(primitive.get('attributes'), dict):
                raise ValueError('glTF primitive attributes must be an object')
            index(primitive['attributes'].get('POSITION'), accessors, 'POSITION accessor')
            for key, collection in (('indices', accessors), ('material', materials)):
                if key in primitive:
                    index(primitive[key], collection, key)
    for accessor in accessors:
        if type(accessor.get('count')) is not int or accessor['count'] < 0:
            raise ValueError('glTF accessor count is invalid')
        if 'bufferView' in accessor:
            index(accessor['bufferView'], views, 'bufferView')
    for view in views:
        index(view.get('buffer'), buffers, 'buffer')
        if type(view.get('byteLength')) is not int or type(view.get('byteOffset', 0)) is not int:
            raise ValueError('glTF bufferView range is invalid')
    for item in textures:
        if 'source' in item:
            index(item['source'], images, 'image')
    for image in images:
        if 'bufferView' in image:
            index(image['bufferView'], views, 'bufferView')
    for material in materials:
        pbr = material.get('pbrMetallicRoughness', {})
        if not isinstance(pbr, dict):
            raise ValueError('glTF pbrMetallicRoughness must be an object')
        for info in [pbr.get(k) for k in ('baseColorTexture', 'metallicRoughnessTexture')] + [material.get('normalTexture')]:
            if info is not None:
                texture(info)


def inspect_glb(path):
    """Counts shown before conversion; no polygon reduction is applied."""
    document, _ = read_glb(path)
    check_document(document)
    primitives = scene_primitives(document)
    if not primitives:
        raise ValueError('The GLB contains no mesh')
    for resource in document.get('buffers', []) + document.get('images', []):
        if 'uri' in resource and not str(resource['uri']).startswith('data:'):
            raise ValueError('The GLB must embed its textures and buffers')
    return {'sha256': sha256(path), 'generator': document.get('asset', {}).get('generator'),
            'triangles': sum(primitive_triangles(document, p) for _, p in primitives),
            'vertices': sum(document['accessors'][p['attributes']['POSITION']]['count'] for _, p in primitives),
            'materials': len(used_materials(document)),
            'extensions': sorted(document.get('extensionsUsed', []))}


def texture_image(document, binary, info):
    if info.get('texCoord', 0) != 0 or 'KHR_texture_transform' in info.get('extensions', {}):
        raise ValueError('Weapon textures must use TEXCOORD_0 without KHR_texture_transform')
    texture = document['textures'][info['index']]
    if 'source' not in texture:
        raise ValueError('Weapon texture has no PNG/JPEG source image')
    image = document['images'][texture['source']]
    if 'bufferView' not in image:
        raise ValueError('The GLB must embed its textures')
    view = document['bufferViews'][image['bufferView']]
    start = view.get('byteOffset', 0)
    result = Image.open(io.BytesIO(binary[start:start + view['byteLength']]))
    result.load()
    return result


def srgb_byte(linear):
    value = linear * 12.92 if linear <= .0031308 else 1.055 * linear ** (1 / 2.4) - .055
    return round(min(1., max(0., value)) * 255)


def material_textures(document, binary, index, stem, source_dir, texture_dir):
    """PNG sources for <stem>.dds, <stem>_n.dds (alpha = 1 - roughness) and optional <stem>_m.dds."""
    material = document['materials'][index] if index is not None else {}
    pbr = material.get('pbrMetallicRoughness', {})
    factor = pbr.get('baseColorFactor', [1, 1, 1, 1])
    manifest = []
    if 'baseColorTexture' in pbr:
        diffuse, tint = texture_image(document, binary, pbr['baseColorTexture']).convert('RGBA'), factor[:3]
    else:
        diffuse = Image.new('RGBA', (4, 4), (*map(srgb_byte, factor[:3]), round(factor[3] * 255)))
        tint = [1, 1, 1]
    diffuse.save(source_dir / f'{stem}.png')
    manifest.append({'png': str(source_dir / f'{stem}.png'), 'relative': f'{texture_dir}/{stem}.dds',
                     'base_color_factor': [float(n) for n in tint]})
    roughness_factor, metallic_factor = pbr.get('roughnessFactor', 1.), pbr.get('metallicFactor', 1.)
    if 'metallicRoughnessTexture' in pbr:
        packed = np.asarray(texture_image(document, binary, pbr['metallicRoughnessTexture']).convert('RGB'), float) / 255
        roughness, metallic = packed[..., 1] * roughness_factor, packed[..., 2] * metallic_factor
    else:
        roughness, metallic = np.full((4, 4), float(roughness_factor)), np.full((4, 4), float(metallic_factor))
    if 'normalTexture' in material:
        if material['normalTexture'].get('scale', 1) != 1:
            logging.warning('Weapon normal map scale %s is not applied', material['normalTexture']['scale'])
        normal = skyrim_normal(texture_image(document, binary, material['normalTexture']))
    else:
        normal = Image.new('RGB', roughness.shape[::-1], (128, 128, 255))
    gloss = Image.fromarray(np.round((1 - np.clip(roughness, 0, 1)) * 255).astype(np.uint8), 'L')
    normal.putalpha(gloss.resize(normal.size, Image.BILINEAR) if gloss.size != normal.size else gloss)
    normal.save(source_dir / f'{stem}_n.png')
    manifest.append({'png': str(source_dir / f'{stem}_n.png'), 'relative': f'{texture_dir}/{stem}_n.dds', 'normal': True})
    nif_dir = texture_dir.replace('/', '\\')
    textures = {'Diffuse': f'{nif_dir}\\{stem}.dds', 'Normal': f'{nif_dir}\\{stem}_n.dds'}
    coverage = float(np.mean(metallic >= METAL_THRESHOLD))
    if coverage >= METAL_COVERAGE:
        mask = Image.fromarray(np.round(np.clip(metallic, 0, 1) * 255).astype(np.uint8), 'L').convert('RGB')
        mask.save(source_dir / f'{stem}_m.png')
        manifest.append({'png': str(source_dir / f'{stem}_m.png'), 'relative': f'{texture_dir}/{stem}_m.dds',
                         'srgb': False})
        textures.update(EnvMap=ENVIRONMENT_MAP_NIF, EnvMask=f'{nif_dir}\\{stem}_m.dds')
    alpha = 1. if material.get('alphaMode', 'OPAQUE') == 'OPAQUE' else float(factor[3])
    logging.info('Weapon material %s: %s, metal coverage %.3f, %s', index, stem, coverage,
                 'environment mask' if 'EnvMask' in textures else 'no environment map')
    return manifest, {'textures': textures, 'metal': 'EnvMask' in textures,
                      'double_sided': bool(material.get('doubleSided', False)), 'alpha': alpha}, \
        {key: material[key] for key in ('alphaMode', 'alphaCutoff', 'doubleSided') if key in material}, coverage


def material_key(index):
    return 'default' if index is None else f'V2SWeaponMaterial_{index:05}'


def prepare_textures(document, binary, output, settings):
    used = used_materials(document)
    source_dir = Path(output) / 'weapon-texture-sources'
    source_dir.mkdir(parents=True, exist_ok=True)
    manifest, materials, policies, coverage = [], {}, {}, {}
    for index in used:
        stem = 'weapon' if len(used) == 1 else 'weapon_' + ('default' if index is None else str(index))
        sources, shader, policy, metal = material_textures(
            document, binary, index, stem, source_dir, f'textures/{settings.asset_dir}')
        manifest += sources
        materials[material_key(index)], policies[material_key(index)] = shader, policy
        coverage[material_key(index)] = metal
    (Path(output) / 'weapon-textures.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    return manifest, materials, policies, coverage


def shared_environment(game_data, output):
    """Use the game's official ShinyDull_e.dds in place; record where it was found."""
    from equipment_textures import RuntimeTextures
    from game_assets import GameAssets
    assets = GameAssets(game_data, [], Path(output) / 'shared-textures')
    archive_path, archive = assets.archive_source(ENVIRONMENT_MAP, 'textures')
    digest = hashlib.sha256(archive.read(ENVIRONMENT_MAP)).hexdigest()
    overridden = not RuntimeTextures(game_data, assets.paths).matches(ENVIRONMENT_MAP, digest, digest)
    if overridden:
        logging.info('Weapon environment map %s is replaced by an installed file; the replacement is used in game',
                     ENVIRONMENT_MAP)
    return {'path': ENVIRONMENT_MAP, 'archive': archive_path.name, 'sha256': digest, 'archive_sha256': digest,
            'overridden': overridden}


def validate_shared(output):
    """Verify the recorded official textures still exist with the recorded bytes."""
    from game_assets import GameAssets, asset_name
    report = json.loads((Path(output) / 'weapon.json').read_text(encoding='utf8'))
    result = {}
    if not report['shared_textures']:
        return result
    assets = GameAssets(report['game_data'], [], Path(output) / 'shared-textures')
    for entry in report['shared_textures']:
        name = asset_name(entry['path'], 'textures')
        if name != entry['path'] or name != ENVIRONMENT_MAP:
            raise ValueError('Unexpected shared weapon texture: ' + entry['path'])
        archive_path, archive = assets.archive_source(name, 'textures')
        if archive_path.name != entry['archive'] or hashlib.sha256(archive.read(name)).hexdigest() != entry['archive_sha256']:
            raise ValueError('Shared official weapon texture differs from the recorded game file: ' + name)
        result[name] = entry
    return result


def readme_text(output, settings):
    """README lines for the original weapon; the environment map line only when a metal mask uses it."""
    shared = validate_shared(output)
    weapon = settings.original_weapon
    text = (f"Original weapon: {weapon['name']} ({settings.prefix}OriginalWeapon, local FormID 0008D0),\n"
            f"converted from {weapon['filename']} with the stats, sounds and enchantment of {weapon['base']}.\n")
    if shared:
        text += "Its environment map uses the game's textures\\cubemaps\\ShinyDull_e.dds.\n"
    return text


def reuse_textures(source, output, digest, settings):
    """Texture results of an earlier convert_weapon output for the same GLB and asset_dir."""
    source = Path(source)
    report = json.loads((source / 'weapon-textures-report.json').read_text(encoding='utf8'))
    if report['glb'] != digest or report['asset_dir'] != settings.asset_dir:
        raise ValueError('Reused weapon textures were converted from another GLB or folder')
    for relative in report['textures']:
        target = Path(output) / 'mod' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / 'mod' / relative, target)
    return report


def convert_weapon(glb, game_data, blender, output, settings, catalog, textures=None):
    """Build the weapon NIF and DDS into output. textures: an earlier output of this function
    for the same GLB and asset_dir whose DDS are copied instead of converted (wizard previews)."""
    from converter import run_blender
    from game_assets import GameAssets
    from textures import convert_textures
    from weapon_nif import SHEATH_NODES, base_dimensions, read_weapon
    output, game_data = Path(output).resolve(), Path(game_data).resolve()
    weapon = settings.original_weapon
    glb = Path(glb).resolve()
    if not glb.is_file() or glb.suffix.lower() != '.glb':
        raise ValueError('Select a local .glb weapon file')
    if glb.is_relative_to(output):
        raise ValueError('Output cannot contain the original weapon GLB')
    digest = sha256(glb)
    if digest != weapon['sha256']:
        raise ValueError('オリジナル武器の設定は別のGLB用です。設定したときと同じGLBを選び直してください')
    summary = inspect_glb(glb)
    document, binary = read_glb(glb)
    for index, material in enumerate(document.get('materials', [])):
        material['name'] = material_key(index)
    work = output / 'weapon-source.glb'
    write_glb(work, document, binary)
    base = catalog.require(weapon['base'], b'WEAP')
    model = base.values(b'MODL')[0].rstrip(b'\0').decode('utf8')
    base_nif = GameAssets(game_data, [], output / 'weapon-reference').extract(model)
    dimensions = base_dimensions(base_nif)
    if textures is None:
        manifest, materials, policies, coverage = prepare_textures(document, binary, output, settings)
        shared = [shared_environment(game_data, output)] if any(m['metal'] for m in materials.values()) else []
        texture_report = {'glb': digest, 'asset_dir': settings.asset_dir, 'materials': materials, 'policies': policies,
                          'coverage': coverage, 'shared': shared, 'textures': [e['relative'] for e in manifest]}
    else:
        texture_report = reuse_textures(textures, output, digest, settings)
    nif = f'meshes/{settings.asset_dir}/weapon.nif'
    plan = {'glb': str(work), 'nif': nif, 'base_nif': str(base_nif), 'grip': weapon['grip'], 'length': weapon['length'],
            'flip': weapon['flip'], 'roll': weapon['roll'], 'prn': SHEATH_NODES[weapon['kind']],
            'materials': texture_report['materials'], 'policies': texture_report['policies']}
    (output / 'weapon-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf8')
    run_blender(blender, 'weapon_blender.py', ['--output', output], output, 'Original weapon')
    if textures is None:
        convert_textures(output, 'weapon-textures.json')
    (output / 'weapon-textures-report.json').write_text(json.dumps(texture_report, indent=2), encoding='utf8')
    built = json.loads((output / 'weapon-nif.json').read_text(encoding='utf8'))
    points = np.concatenate([s['points'] for s in read_weapon(output / 'mod' / nif)['shapes']])
    report = {'schema': 1, 'source': summary, 'filename': weapon['filename'], 'kind': weapon['kind'],
              'base': weapon['base'], 'base_model': model, 'base_dimensions': dimensions,
              'grip': weapon['grip'], 'length': weapon['length'], 'flip': weapon['flip'], 'roll': weapon['roll'],
              'nif': nif, 'bounds': [points.min(0).tolist(), points.max(0).tolist()],
              'placement': built['placement'], 'shapes': built['shapes'], 'collision': built['collision'],
              'metal_coverage': texture_report['coverage'], 'textures': texture_report['textures'],
              'shared_textures': texture_report['shared'], 'game_data': str(game_data), 'game_verified': False}
    (output / 'weapon.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    validate_weapon_model(output, settings)
    if sha256(glb) != digest:
        raise RuntimeError('Original weapon GLB changed during conversion')
    logging.info('Original weapon %s from %s: %s triangles in %s shapes', weapon['name'], weapon['base'],
                 summary['triangles'], len(built['shapes']))
    return report


def object_bounds(bounds):
    low, high = bounds
    values = [math.floor(v) for v in low] + [math.ceil(v) for v in high]
    return [max(-32768, min(32767, v)) for v in values]


def weapon_records(settings, base, static, description, bounds):
    """Private copies of the base WEAP and its first-person STAT with the original model."""
    path = text(settings.asset_dir.replace('/', '\\') + '\\weapon.nif')
    obnd = struct.pack('<6h', *object_bounds(bounds))
    weapon = copy.deepcopy(base)
    weapon.form_id = WEAPON_ID
    weapon.replace(b'EDID', text(settings.prefix + 'OriginalWeapon'))
    weapon.replace(b'OBND', obnd)
    weapon.replace(b'FULL', text(settings.original_weapon['name']))
    weapon.replace(b'MODL', path)
    weapon.replace(b'WNAM', struct.pack('<I', FIRST_PERSON_ID))
    if weapon.values(b'DESC'):
        weapon.replace(b'DESC', text(description))
    weapon.remove(b'MODT', b'CNAM')
    first_person = copy.deepcopy(static)
    first_person.form_id = FIRST_PERSON_ID
    first_person.replace(b'EDID', text(settings.prefix + 'OriginalWeapon1stPerson'))
    first_person.replace(b'OBND', obnd)
    first_person.replace(b'MODL', path)
    first_person.remove(b'MODT')
    return [weapon, first_person]


def catalog_records(settings, catalog, output):
    base = catalog.require(settings.original_weapon['base'], b'WEAP')
    static = catalog.first_person_static(base)
    if static is None:
        raise ValueError('Base weapon has no first-person STAT: ' + base.editor_id)
    report = json.loads((Path(output) / 'weapon.json').read_text(encoding='utf8'))
    if report['base'] != base.editor_id or report['source']['sha256'] != settings.original_weapon['sha256']:
        raise ValueError('Original weapon model was built for different settings')
    description = catalog.label(base, b'DESC') if base.values(b'DESC') else ''
    return base, static, description, weapon_records(settings, base, static, description, report['bounds'])


def check_copied(generated, base, static):
    """The private copies equal their official sources outside the replaced fields."""
    by_id = {r.form_id: r for r in generated}
    for record, source, changed in ((by_id.get(WEAPON_ID), base, CHANGED_FIELDS),
                                    (by_id.get(FIRST_PERSON_ID), static, STATIC_CHANGED_FIELDS)):
        if record is None or record.kind != source.kind:
            raise ValueError('Original weapon record is missing')
        if [f for f in record.fields if f[0] not in changed] != [f for f in source.fields if f[0] not in changed]:
            raise ValueError(f'Original weapon {record.kind.decode()} differs from its official source')


def validate_weapon_records(generated, settings, npc_report=None):
    """Plugin contract for the private WEAP/STAT pair; shared by build and output checks."""
    by_id = {r.form_id: r for r in generated}
    if settings.weapon_mode != 'original':
        if WEAPON_ID in by_id or FIRST_PERSON_ID in by_id:
            raise ValueError('Official weapon mode must not contain an original weapon')
        return None
    weapon, static = by_id.get(WEAPON_ID), by_id.get(FIRST_PERSON_ID)
    if weapon is None or weapon.kind != b'WEAP' or static is None or static.kind != b'STAT':
        raise ValueError('Original weapon WEAP/STAT records are missing')
    path = text(settings.asset_dir.replace('/', '\\') + '\\weapon.nif')
    if weapon.values(b'MODL') != [path] or static.values(b'MODL') != [path]:
        raise ValueError('Original weapon and its first-person model must use the same NIF')
    if weapon.values(b'WNAM') != [struct.pack('<I', FIRST_PERSON_ID)]:
        raise ValueError('Original weapon does not use its private first-person STAT')
    if weapon.values(b'MODT') or static.values(b'MODT') or weapon.values(b'CNAM'):
        raise ValueError('Original weapon retains official model data or a template')
    if weapon.editor_id != settings.prefix + 'OriginalWeapon' or static.editor_id != settings.prefix + 'OriginalWeapon1stPerson':
        raise ValueError('Original weapon Editor IDs mismatch')
    if weapon.values(b'FULL') != [text(settings.original_weapon['name'])]:
        raise ValueError('Original weapon name was not written as a string')
    for value in weapon.values(b'DESC'):
        if not value.endswith(b'\0') or (npc_report and value != text(npc_report['description'])):
            raise ValueError('Original weapon description is not an inline string')
    if weapon.values(b'OBND') != static.values(b'OBND') or len(weapon.values(b'OBND')[0]) != 12:
        raise ValueError('Original weapon bounds mismatch')
    npc = next(r for r in generated if r.kind == b'NPC_')
    inventory = [struct.unpack_from('<I', v)[0] for v in npc.values(b'CNTO')]
    if inventory.count(WEAPON_ID) != 1:
        raise ValueError('Original weapon is not in the follower inventory')
    if npc_report and npc_report.get('official_weapon_form_id') in inventory:
        raise ValueError('Official starting weapon is still in the follower inventory')
    return {'weapon': hex(WEAPON_ID), 'first_person': hex(FIRST_PERSON_ID)}


def validate_weapon_model(output, settings):
    """Read the delivered weapon NIF back: axes, grip origin, length, shapes, textures, collision."""
    from weapon_nif import HULL_COVERAGE, SHEATH_NODES, read_weapon
    output = Path(output)
    mod = (output / 'mod').resolve()
    report = json.loads((output / 'weapon.json').read_text(encoding='utf8'))
    weapon = settings.original_weapon
    nif = read_weapon(mod / report['nif'])
    if nif['game'] != 'SKYRIMSE' or nif['root'] != 'BSFadeNode' or not nif['shapes']:
        raise ValueError('Weapon NIF needs a SKYRIMSE BSFadeNode root with shapes')
    if nif['prn'] != [SHEATH_NODES[weapon['kind']]]:
        raise ValueError(f"Weapon NIF sheathes at {nif['prn']}, not {SHEATH_NODES[weapon['kind']]}")
    shared = {e['path'] for e in validate_shared(output).values()}
    textures = set()
    for shape in nif['shapes']:
        if shape['block'] != 'BSTriShape' or not 0 < shape['vertices'] <= 65535:
            raise ValueError('Invalid weapon shape: ' + shape['name'])
        if any(abs(v) > 1e-6 for v in shape['translation']) or abs(shape['scale'] - 1) > 1e-6:
            raise ValueError('Weapon shapes must be placed by their vertices: ' + shape['name'])
        if not shape['textures'].get('Diffuse') or not shape['textures'].get('Normal'):
            raise ValueError('Weapon shape lacks diffuse or normal texture: ' + shape['name'])
        for texture in filter(None, shape['textures'].values()):
            relative = texture.replace('\\', '/').lower()
            if relative in shared:
                continue
            path = (mod / relative).resolve()
            if not path.is_relative_to(mod / 'textures' / settings.asset_dir) or not path.is_file():
                raise ValueError('Missing or external weapon texture: ' + texture)
            textures.add(path)
    points = np.concatenate([s['points'] for s in nif['shapes']])
    low, high = points.min(0), points.max(0)
    extent = high - low
    tolerance = 1e-3 * weapon['length']
    if abs(extent[1] - weapon['length']) > tolerance:
        raise ValueError(f"Weapon length {extent[1]:.4f} differs from {weapon['length']}")
    if abs(low[1] + weapon['grip'] * weapon['length']) > tolerance:
        raise ValueError(f"Weapon origin is not at grip {weapon['grip']}: lowest Y {low[1]:.4f}")
    if weapon['roll'] % 90 == 0 and extent[1] + tolerance < max(extent[0], extent[2]):
        raise ValueError('Weapon length does not run along +Y')
    # A plain bhkRigidBody places its shape in the NIF frame; bhkRigidBodyT bases offset it.
    if (nif['collision'] != 'bhkCollisionObject' or nif['collision_flags'] != report['collision']['flags']
            or nif['body'] != 'bhkRigidBody' or nif['shape'] != 'bhkConvexVerticesShape'):
        raise ValueError('Weapon NIF lacks bhkCollisionObject/bhkRigidBody/bhkConvexVerticesShape collision')
    if np.abs(nif['body_translation']).max() > 1e-4 or np.abs(nif['body_rotation'] - [0, 0, 0, 1]).max() > 1e-6:
        raise ValueError('Weapon rigid body must not move or rotate its collision shape')
    planes = nif['hull_planes']
    if not 4 <= len(nif['hull']) <= 64 or len(planes) < 4:
        raise ValueError('Weapon collision hull has an unexpected size')
    outside = float((points @ planes[:, :3].T - planes[:, 3]).max())
    if (np.abs(nif['hull'].min(0) - low).max() > .01 or np.abs(nif['hull'].max(0) - high).max() > .01
            or outside > HULL_COVERAGE * extent.max() + .01):
        raise ValueError('Weapon collision hull does not cover the weapon geometry')
    if np.any(nif['body_center'] < low - .01) or np.any(nif['body_center'] > high + .01):
        raise ValueError('Weapon centre of mass lies outside its collision hull')
    result = {'shapes': [{k: s[k] for k in ('name', 'vertices', 'triangles', 'textures')} for s in nif['shapes']],
              'triangles': sum(s['triangles'] for s in nif['shapes']), 'bounds': [low.tolist(), high.tolist()],
              'length': float(extent[1]), 'grip': float(-low[1] / extent[1]), 'prn': nif['prn'],
              'collision': {'object': nif['collision'], 'flags': nif['collision_flags'], 'body': nif['body'],
                            'layer': nif['layer'], 'mass': nif['mass'], 'shape': nif['shape'],
                            'center': nif['body_center'].tolist(),
                            'hull_vertices': len(nif['hull']), 'hull_planes': len(planes)},
              'shared_textures': sorted(shared), 'game_verified': False}
    return result, textures


def check_bounds(generated, bounds):
    """WEAP and first-person STAT OBND equal the measured NIF bounds as weapon_records rounds them."""
    by_id = {r.form_id: r for r in generated}
    expected = [struct.pack('<6h', *object_bounds(bounds))]
    for form_id in (WEAPON_ID, FIRST_PERSON_ID):
        if form_id not in by_id or by_id[form_id].values(b'OBND') != expected:
            raise ValueError('Original weapon OBND differs from the weapon NIF bounds')


def npc_report(settings, catalog, base, description):
    official = catalog.by_editor_id.get(settings.weapon) if settings.weapon else None
    return {'official_weapon_form_id': official.form_id if official else None,
            'editor_id': settings.prefix + 'OriginalWeapon', 'local_form_id': '0008D0',
            'first_person_editor_id': settings.prefix + 'OriginalWeapon1stPerson', 'first_person_local_form_id': '0008D1',
            'base': base.editor_id, 'base_form_id': base.form_id, 'description': description,
            'name': settings.original_weapon['name']}
