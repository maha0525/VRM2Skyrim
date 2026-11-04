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
from settings import MAX_ORIGINAL_WEAPONS

# Weapon 0; weapon i uses WEAP 0x8D0 + 2i and STAT 0x8D1 + 2i (settings.MAX_ORIGINAL_WEAPONS pairs).
WEAPON_ID = 0x010008D0
FIRST_PERSON_ID = 0x010008D1
# Fields replaced or removed on the copied base WEAP; every other field is copied unchanged
# except the overridden stats (STAT_FIELDS) and a changed enchantment (ENCHANTMENT_FIELDS).
CHANGED_FIELDS = {b'EDID', b'FULL', b'MODL', b'WNAM', b'OBND', b'MODT', b'DESC', b'CNAM'}
STATIC_CHANGED_FIELDS = {b'EDID', b'MODL', b'OBND', b'MODT'}
# xEdit wbDefinitionsTES5 WEAP: DATA = Value uint32, Weight float, Damage uint16;
# DNAM = Animation Type uint8, 3 unused bytes, Speed float, Reach float, Flags uint16, ...
STAT_FIELDS = {'damage': (b'DATA', 8, '<H'), 'weight': (b'DATA', 4, '<f'), 'value': (b'DATA', 0, '<I'),
               'speed': (b'DNAM', 4, '<f'), 'reach': (b'DNAM', 8, '<f')}
# EITM: Object Effect (ENCH) FormID; EAMT: Enchantment Amount uint16 (the charge).
ENCHANTMENT_FIELDS = (b'EITM', b'EAMT')
# WEAP fields xEdit orders before EITM/EAMT; an added enchantment goes after the last of these.
BEFORE_ENCHANTMENT = {b'EDID', b'VMAD', b'OBND', b'FULL', b'MODL', b'MODT', b'MODS', b'ICON', b'MICO'}
ENVIRONMENT_MAP = 'textures/cubemaps/shinydull_e.dds'
ENVIRONMENT_MAP_NIF = 'textures\\cubemaps\\ShinyDull_e.dds'
METAL_THRESHOLD = .5
METAL_COVERAGE = .01
# glTF and the official SteelSword/ForswornStaff/SteelMace normal maps read with the
# same green direction (2026-10-25). Flip here if in-game shading looks inverted.
FLIP_NORMAL_GREEN = False


def text(value):
    return value.encode('utf8') + b'\0'


def weapon_id(index):
    return WEAPON_ID + 2 * index


def first_person_id(index):
    return FIRST_PERSON_ID + 2 * index


def stem(index):
    """File stem of weapon index: its NIF, DDS and work files. Weapon 0 keeps the single-weapon names;
    'weapon2'... never collide with weapon 0's multi-material 'weapon_<n>' textures."""
    return 'weapon' if index == 0 else f'weapon{index + 1}'


def editor_ids(settings, index):
    """(WEAP, STAT) Editor IDs; weapon 0 keeps the single-weapon IDs."""
    name = settings.prefix + ('OriginalWeapon' if index == 0 else f'OriginalWeapon{index + 1}')
    return name, name + ('1stPerson' if index == 0 else '_1stPerson')


def model_path(settings, index):
    return text(settings.asset_dir.replace('/', '\\') + f'\\{stem(index)}.nif')


def read_stats(record):
    """The five overridable stats of a WEAP as the game reads them."""
    result = {}
    for name, (tag, offset, layout) in STAT_FIELDS.items():
        values = record.values(tag)
        if not values or len(values[0]) < offset + struct.calcsize(layout):
            raise ValueError(f'{record.editor_id} has no {tag.decode()} {name}')
        result[name] = struct.unpack_from(layout, values[0], offset)[0]
    return result


def expected_stat(name, value):
    """A settings stat as its field stores it (floats round to 4 bytes)."""
    return struct.unpack(STAT_FIELDS[name][2], struct.pack(STAT_FIELDS[name][2], value))[0]


def write_stats(record, stats):
    for name, value in stats.items():
        tag, offset, layout = STAT_FIELDS[name]
        values = record.values(tag)
        if not values or len(values[0]) < offset + struct.calcsize(layout):
            raise ValueError(f'{record.editor_id} has no {tag.decode()} {name}')
        data = bytearray(values[0])
        struct.pack_into(layout, data, offset, value)
        record.replace(tag, bytes(data))


def write_enchantment(record, enchantment):
    """enchantment: None removes EITM/EAMT, else (ENCH FormID, charge) replaces or adds them in xEdit order."""
    record.remove(*ENCHANTMENT_FIELDS)
    if enchantment is None:
        return
    form_id, amount = enchantment
    index = max(i for i, (tag, _) in enumerate(record.fields) if tag in BEFORE_ENCHANTMENT) + 1
    record.fields[index:index] = [(b'EITM', struct.pack('<I', form_id)), (b'EAMT', struct.pack('<H', amount))]


def enchantment_values(record):
    """(EITM FormID, EAMT) of a WEAP; None for either it lacks."""
    eitm, eamt = record.values(b'EITM'), record.values(b'EAMT')
    return (struct.unpack('<I', eitm[0])[0] if eitm else None, struct.unpack('<H', eamt[0])[0] if eamt else None)


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
        # Opaque: the alpha factor reaches the NIF once, through the shader Alpha below.
        diffuse = Image.new('RGBA', (4, 4), (*map(srgb_byte, factor[:3]), 255))
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


def prepare_textures(document, binary, output, settings, weapon_index=0):
    used = used_materials(document)
    name = stem(weapon_index)
    source_dir = Path(output) / f'{name}-texture-sources'
    source_dir.mkdir(parents=True, exist_ok=True)
    manifest, materials, policies, coverage = [], {}, {}, {}
    for index in used:
        texture_stem = name if len(used) == 1 else f'{name}_' + ('default' if index is None else str(index))
        sources, shader, policy, metal = material_textures(
            document, binary, index, texture_stem, source_dir, f'textures/{settings.asset_dir}')
        manifest += sources
        materials[material_key(index)], policies[material_key(index)] = shader, policy
        coverage[material_key(index)] = metal
    (Path(output) / f'{name}-textures.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
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


def validate_shared(output, index=0):
    """Verify the recorded official textures of weapon index still exist with the recorded bytes."""
    from game_assets import GameAssets, asset_name
    report = json.loads((Path(output) / f'{stem(index)}.json').read_text(encoding='utf8'))
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
    """README lines for the original weapons; the environment map line only when a metal mask uses it."""
    lines, shared = [], False
    for index, weapon in enumerate(settings.original_weapons):
        shared |= bool(validate_shared(output, index))
        changes = [f'{name} {value}' for name, value in weapon['stats'].items()]
        if weapon['enchantment'] != 'keep':
            changes.append('enchantment ' + weapon['enchantment'])
        lines.append(f"Original weapon: {weapon['name']} ({editor_ids(settings, index)[0]}, local FormID "
                     f"{weapon_id(index) & 0xFFFFFF:06X}),\nconverted from {weapon['filename']} with the stats, sounds "
                     f"and enchantment of {weapon['base']}" + (f" except {', '.join(changes)}" if changes else '') + '.\n')
    text = ''.join(lines)
    if len(lines) > 1:
        text += ('All original weapons are in the follower inventory. The game AI chooses which to wield;\n'
                 'dual wielding also depends on the combat style.\n')
    if shared:
        text += "Environment maps use the game's textures\\cubemaps\\ShinyDull_e.dds.\n"
    return text


def reuse_textures(source, output, digest, settings, index=0):
    """Texture results of an earlier convert_weapon output for the same GLB, asset_dir and file stem."""
    source = Path(source)
    report = json.loads((source / f'{stem(index)}-textures-report.json').read_text(encoding='utf8'))
    if (report['glb'] != digest or report['asset_dir'] != settings.asset_dir
            or report.get('stem', 'weapon') != stem(index)):
        raise ValueError('Reused weapon textures were converted from another GLB or folder')
    for relative in report['textures']:
        target = Path(output) / 'mod' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / 'mod' / relative, target)
    return report


def convert_weapon(glb, game_data, blender, output, settings, catalog, textures=None, index=0):
    """Build the NIF and DDS of original weapon index into output. textures: an earlier output of this
    function for the same GLB, asset_dir and index whose DDS are copied instead of converted (wizard previews)."""
    from converter import run_blender
    from game_assets import GameAssets
    from textures import convert_textures
    from weapon_nif import SHEATH_NODES, base_dimensions, read_weapon
    output, game_data = Path(output).resolve(), Path(game_data).resolve()
    weapon = settings.original_weapons[index]
    name = stem(index)
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
    for number, material in enumerate(document.get('materials', [])):
        material['name'] = material_key(number)
    work = output / f'{name}-source.glb'
    write_glb(work, document, binary)
    base = catalog.require(weapon['base'], b'WEAP')
    model = base.values(b'MODL')[0].rstrip(b'\0').decode('utf8')
    base_nif = GameAssets(game_data, [], output / 'weapon-reference').extract(model)
    dimensions = base_dimensions(base_nif)
    if textures is None:
        manifest, materials, policies, coverage = prepare_textures(document, binary, output, settings, index)
        shared = [shared_environment(game_data, output)] if any(m['metal'] for m in materials.values()) else []
        texture_report = {'glb': digest, 'asset_dir': settings.asset_dir, 'stem': name, 'materials': materials,
                          'policies': policies, 'coverage': coverage, 'shared': shared,
                          'textures': [e['relative'] for e in manifest]}
    else:
        texture_report = reuse_textures(textures, output, digest, settings, index)
    nif = f'meshes/{settings.asset_dir}/{name}.nif'
    plan = {'glb': str(work), 'nif': nif, 'base_nif': str(base_nif), 'grip': weapon['grip'], 'length': weapon['length'],
            'flip': weapon['flip'], 'roll': weapon['roll'], 'prn': SHEATH_NODES[weapon['kind']],
            'materials': texture_report['materials'], 'policies': texture_report['policies'],
            'report': f'{name}-nif.json'}
    (output / f'{name}-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf8')
    run_blender(blender, 'weapon_blender.py', ['--output', output, '--plan', f'{name}-plan.json'], output,
                'Original weapon' if index == 0 else f'Original weapon {index + 1}')
    if textures is None:
        convert_textures(output, f'{name}-textures.json')
    (output / f'{name}-textures-report.json').write_text(json.dumps(texture_report, indent=2), encoding='utf8')
    built = json.loads((output / plan['report']).read_text(encoding='utf8'))
    points = np.concatenate([s['points'] for s in read_weapon(output / 'mod' / nif)['shapes']])
    report = {'schema': 1, 'index': index, 'source': summary, 'filename': weapon['filename'], 'kind': weapon['kind'],
              'base': weapon['base'], 'base_model': model, 'base_dimensions': dimensions,
              'grip': weapon['grip'], 'length': weapon['length'], 'flip': weapon['flip'], 'roll': weapon['roll'],
              'nif': nif, 'bounds': [points.min(0).tolist(), points.max(0).tolist()],
              'placement': built['placement'], 'shapes': built['shapes'], 'collision': built['collision'],
              'metal_coverage': texture_report['coverage'], 'textures': texture_report['textures'],
              'shared_textures': texture_report['shared'], 'game_data': str(game_data), 'game_verified': False}
    (output / f'{name}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    validate_weapon_model(output, settings, index)
    if sha256(glb) != digest:
        raise RuntimeError('Original weapon GLB changed during conversion')
    logging.info('Original weapon %s (%s) from %s: %s triangles in %s shapes', index + 1, weapon['name'],
                 weapon['base'], summary['triangles'], len(built['shapes']))
    return report


def object_bounds(bounds):
    low, high = bounds
    values = [math.floor(v) for v in low] + [math.ceil(v) for v in high]
    return [max(-32768, min(32767, v)) for v in values]


def weapon_records(settings, base, static, description, bounds, index=0, enchantment=None):
    """Private copies of the base WEAP and its first-person STAT with the original model, stats and enchantment.

    enchantment: (ENCH FormID, EAMT) for an enchantment chosen by Editor ID (catalog.weapon_enchantment);
    'keep' leaves the base's EITM/EAMT and 'none' removes them."""
    original = settings.original_weapons[index]
    path = model_path(settings, index)
    obnd = struct.pack('<6h', *object_bounds(bounds))
    weapon_editor_id, static_editor_id = editor_ids(settings, index)
    weapon = copy.deepcopy(base)
    weapon.form_id = weapon_id(index)
    weapon.replace(b'EDID', text(weapon_editor_id))
    weapon.replace(b'OBND', obnd)
    weapon.replace(b'FULL', text(original['name']))
    weapon.replace(b'MODL', path)
    weapon.replace(b'WNAM', struct.pack('<I', first_person_id(index)))
    if weapon.values(b'DESC'):
        weapon.replace(b'DESC', text(description))
    weapon.remove(b'MODT', b'CNAM')
    write_stats(weapon, original['stats'])
    if original['enchantment'] == 'none':
        write_enchantment(weapon, None)
    elif original['enchantment'] != 'keep':
        if enchantment is None:
            raise ValueError('Enchantment was not resolved: ' + original['enchantment'])
        write_enchantment(weapon, enchantment)
    first_person = copy.deepcopy(static)
    first_person.form_id = first_person_id(index)
    first_person.replace(b'EDID', text(static_editor_id))
    first_person.replace(b'OBND', obnd)
    first_person.replace(b'MODL', path)
    first_person.remove(b'MODT')
    return [weapon, first_person]


def expected_enchantment(original, base, chosen):
    """(EITM FormID, EAMT) the copy must carry; (None, None) without an enchantment."""
    if original['enchantment'] == 'keep':
        return enchantment_values(base)
    return (None, None) if original['enchantment'] == 'none' else tuple(chosen)


def catalog_records(settings, catalog, output):
    """Per original weapon: its official sources, records and the values the plugin must carry."""
    result = []
    for index, original in enumerate(settings.original_weapons):
        base = catalog.require(original['base'], b'WEAP')
        static = catalog.first_person_static(base)
        if static is None:
            raise ValueError('Base weapon has no first-person STAT: ' + base.editor_id)
        report = json.loads((Path(output) / f'{stem(index)}.json').read_text(encoding='utf8'))
        if report['base'] != base.editor_id or report['source']['sha256'] != original['sha256']:
            raise ValueError(f'Original weapon {index + 1} model was built for different settings')
        description = catalog.label(base, b'DESC') if base.values(b'DESC') else ''
        chosen = None
        if original['enchantment'] not in ('keep', 'none'):
            chosen = catalog.weapon_enchantment(original['enchantment'])
            if enchantment_values(base)[0] == chosen[0] and base.values(b'EAMT'):
                chosen = enchantment_values(base)  # the base's own charge for its own enchantment
        result.append({'index': index, 'base': base, 'static': static, 'description': description,
                       'enchantment': expected_enchantment(original, base, chosen),
                       'records': weapon_records(settings, base, static, description, report['bounds'], index, chosen)})
    return result


def comparable_fields(record, changed, original=None):
    """record fields outside changed, with overridden stat bytes zeroed and a changed enchantment dropped."""
    stats = original['stats'] if original else {}
    enchantment = original['enchantment'] if original else 'keep'
    result = []
    for tag, value in record.fields:
        if tag in changed or (enchantment != 'keep' and tag in ENCHANTMENT_FIELDS):
            continue
        for name in stats:
            field, offset, layout = STAT_FIELDS[name]
            if tag == field:
                value = value[:offset] + bytes(struct.calcsize(layout)) + value[offset + struct.calcsize(layout):]
        result.append((tag, value))
    return result


def check_copied(generated, base, static, settings=None, index=0):
    """The private copies equal their official sources outside the replaced fields; settings: the
    overridden stats and changed enchantment of original weapon index are compared by validate_weapon_records."""
    original = settings.original_weapons[index] if settings else None
    by_id = {r.form_id: r for r in generated}
    for record, source, changed in ((by_id.get(weapon_id(index)), base, CHANGED_FIELDS),
                                    (by_id.get(first_person_id(index)), static, STATIC_CHANGED_FIELDS)):
        if record is None or record.kind != source.kind:
            raise ValueError(f'Original weapon {index + 1} record is missing')
        extra = original if record.kind == b'WEAP' else None
        if comparable_fields(record, changed, extra) != comparable_fields(source, changed, extra):
            raise ValueError(f'Original weapon {index + 1} {record.kind.decode()} differs from its official source')


def weapon_reports(npc_report):
    """Per-weapon entries of npc.json's original_weapon report; a single-weapon report is weapon 0."""
    if not npc_report:
        return None
    return npc_report['weapons'] if 'weapons' in npc_report else [npc_report]


def validate_weapon_records(generated, settings, npc_report=None):
    """Plugin contract for the private WEAP/STAT pairs; shared by build and output checks."""
    by_id = {r.form_id: r for r in generated}
    count = len(settings.original_weapons) if settings.weapon_mode == 'original' else 0
    reserved = {form_id for i in range(MAX_ORIGINAL_WEAPONS) for form_id in (weapon_id(i), first_person_id(i))}
    unexpected = sorted(set(by_id) & reserved - {f(i) for i in range(count) for f in (weapon_id, first_person_id)})
    if unexpected:
        if not count:
            raise ValueError('Official weapon mode must not contain an original weapon')
        raise ValueError(f'Unexpected original weapon records: {", ".join(map(hex, unexpected))}')
    if not count:
        return None
    reports = weapon_reports(npc_report)
    if reports is not None and len(reports) != count:
        raise ValueError(f'npc.json reports {len(reports)} original weapons, settings have {count}')
    npc = next(r for r in generated if r.kind == b'NPC_')
    inventory = [struct.unpack_from('<I', v)[0] for v in npc.values(b'CNTO')]
    result = []
    for index, original in enumerate(settings.original_weapons):
        report = reports[index] if reports else None
        weapon, static = by_id.get(weapon_id(index)), by_id.get(first_person_id(index))
        if weapon is None or weapon.kind != b'WEAP' or static is None or static.kind != b'STAT':
            raise ValueError(f'Original weapon {index + 1} WEAP/STAT records are missing')
        path = model_path(settings, index)
        if weapon.values(b'MODL') != [path] or static.values(b'MODL') != [path]:
            raise ValueError(f'Original weapon {index + 1} and its first-person model must use the same NIF')
        if weapon.values(b'WNAM') != [struct.pack('<I', first_person_id(index))]:
            raise ValueError(f'Original weapon {index + 1} does not use its private first-person STAT')
        if weapon.values(b'MODT') or static.values(b'MODT') or weapon.values(b'CNAM'):
            raise ValueError(f'Original weapon {index + 1} retains official model data or a template')
        if (weapon.editor_id, static.editor_id) != editor_ids(settings, index):
            raise ValueError(f'Original weapon {index + 1} Editor IDs mismatch')
        if weapon.values(b'FULL') != [text(original['name'])]:
            raise ValueError(f'Original weapon {index + 1} name was not written as a string')
        for value in weapon.values(b'DESC'):
            if not value.endswith(b'\0') or (report and value != text(report['description'])):
                raise ValueError(f'Original weapon {index + 1} description is not an inline string')
        if weapon.values(b'OBND') != static.values(b'OBND') or len(weapon.values(b'OBND')[0]) != 12:
            raise ValueError(f'Original weapon {index + 1} bounds mismatch')
        stats = read_stats(weapon)
        expected = {**(report.get('base_stats', {}) if report else {}),
                    **{name: expected_stat(name, value) for name, value in original['stats'].items()}}
        wrong = [name for name, value in expected.items() if stats[name] != value]
        if wrong:
            raise ValueError(f'Original weapon {index + 1} {", ".join(wrong)} differs from the settings')
        eitm, eamt = enchantment_values(weapon)
        if original['enchantment'] == 'none' and (eitm is not None or eamt is not None):
            raise ValueError(f'Original weapon {index + 1} keeps an enchantment the settings remove')
        if original['enchantment'] not in ('keep', 'none') and (eitm is None or eamt is None):
            raise ValueError(f'Original weapon {index + 1} lacks the chosen enchantment')
        if report and 'enchantment' in report:
            if report['enchantment']['choice'] != original['enchantment'] or (eitm, eamt) != (
                    report['enchantment']['form_id'], report['enchantment']['amount']):
                raise ValueError(f'Original weapon {index + 1} enchantment differs from the settings')
        if inventory.count(weapon_id(index)) != 1:
            raise ValueError(f'Original weapon {index + 1} is not in the follower inventory')
        result.append({'weapon': hex(weapon_id(index)), 'first_person': hex(first_person_id(index))})
    if npc_report and npc_report.get('official_weapon_form_id') in inventory:
        raise ValueError('Official starting weapon is still in the follower inventory')
    return result


def validate_weapon_model(output, settings, index=0):
    """Read the delivered weapon NIF back: axes, grip origin, length, shapes, textures, collision."""
    from weapon_nif import HULL_COVERAGE, SHEATH_NODES, read_weapon
    output = Path(output)
    mod = (output / 'mod').resolve()
    report = json.loads((output / f'{stem(index)}.json').read_text(encoding='utf8'))
    weapon = settings.original_weapons[index]
    if report['nif'] != f'meshes/{settings.asset_dir}/{stem(index)}.nif':
        raise ValueError(f"Original weapon {index + 1} NIF is {report['nif']}, not {stem(index)}.nif")
    nif = read_weapon(mod / report['nif'])
    if nif['game'] != 'SKYRIMSE' or nif['root'] != 'BSFadeNode' or not nif['shapes']:
        raise ValueError('Weapon NIF needs a SKYRIMSE BSFadeNode root with shapes')
    if nif['prn'] != [SHEATH_NODES[weapon['kind']]]:
        raise ValueError(f"Weapon NIF sheathes at {nif['prn']}, not {SHEATH_NODES[weapon['kind']]}")
    shared = {e['path'] for e in validate_shared(output, index).values()}
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
            if path.stem.lower() != stem(index) and not path.stem.lower().startswith(stem(index) + '_'):
                raise ValueError(f'Original weapon {index + 1} uses another weapon\'s texture: {texture}')
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


def check_bounds(generated, bounds, index=0):
    """WEAP and first-person STAT OBND equal the measured NIF bounds as weapon_records rounds them."""
    by_id = {r.form_id: r for r in generated}
    expected = [struct.pack('<6h', *object_bounds(bounds))]
    for form_id in (weapon_id(index), first_person_id(index)):
        if form_id not in by_id or by_id[form_id].values(b'OBND') != expected:
            raise ValueError(f'Original weapon {index + 1} OBND differs from the weapon NIF bounds')


def npc_report(settings, catalog, built):
    """npc.json original_weapon: per weapon (catalog_records order) its IDs, base and the values it must carry."""
    official = catalog.by_editor_id.get(settings.weapon) if settings.weapon else None
    weapons = []
    for item in built:
        index, base = item['index'], item['base']
        original = settings.original_weapons[index]
        weapon_editor_id, static_editor_id = editor_ids(settings, index)
        form_id, amount = item['enchantment']
        weapons.append({'index': index, 'editor_id': weapon_editor_id, 'local_form_id': f'{weapon_id(index) & 0xFFFFFF:06X}',
                        'first_person_editor_id': static_editor_id,
                        'first_person_local_form_id': f'{first_person_id(index) & 0xFFFFFF:06X}',
                        'base': base.editor_id, 'base_form_id': base.form_id, 'description': item['description'],
                        'name': original['name'], 'base_stats': read_stats(base), 'stats': original['stats'],
                        'enchantment': {'choice': original['enchantment'], 'form_id': form_id, 'amount': amount}})
    return {'official_weapon_form_id': official.form_id if official else None, 'weapons': weapons}
