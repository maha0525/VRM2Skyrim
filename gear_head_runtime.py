"""Independent VRM face/hair visibility without head parts or worn helper items."""
import copy
from collections import Counter
import hashlib
import json
import logging
from pathlib import Path
import struct

from plugin import Record

PROPERTIES = ('FullSkin', 'FaceHiddenSkin', 'HairHiddenSkin', 'BothHiddenSkin',
              'FaceHidingEquipment', 'HairHidingEquipment')
IDS = dict(zip(PROPERTIES, (0x01000801, 0x01000852, 0x01000853, 0x01000854, 0x01000855, 0x01000856)))
TEMPLATE = 'V2SHeadVisibility'


def script_name(settings):
    return settings.prefix + 'HeadVisibility'


def binding(settings):
    def string(value):
        raw = value.encode()
        return struct.pack('<H', len(raw)) + raw
    data = string(script_name(settings)) + struct.pack('<BH', 0, len(PROPERTIES))
    for prop in PROPERTIES:
        data += string(prop) + bytes((1, 1)) + struct.pack('<HhI', 0, -1, IDS[prop])
    return data


def head_variants(settings):
    fixed = set(settings.appearance_parts['fixed'])
    heads = settings.appearance_heads
    return [{'name': name, 'addon_id': 0x01000860+i, 'file': 'fixed_'+suffix+'.nif',
             'nodes': sorted(fixed-set(sum((heads[k] for k in remove), [])))}
            for i, (name, suffix, remove) in enumerate((('FaceHiddenSkin', 'no_face', ('face',)),
                 ('HairHiddenSkin', 'no_hair', ('hair',)), ('BothHiddenSkin', 'no_face_hair', ('face', 'hair'))))]


def head_skin_records(settings, skin, profile, fixed_addon):
    result = []
    for variant in head_variants(settings):
        name = variant['name']
        record = copy.deepcopy(skin)
        record.form_id = IDS[name]
        record.replace(b'EDID', (settings.prefix+name+'\0').encode())
        fields = []
        for tag, blob in record.fields:
            if tag == b'MODL' and struct.unpack('<I', blob)[0] == 0x01000808:
                if variant['nodes']:
                    fields.append((tag, struct.pack('<I', variant['addon_id'])))
            else:
                fields.append((tag, blob))
        record.fields = fields
        # Layer 60 is still occupied if a permanent accessory or either head component remains.
        if not variant['nodes']:
            data = bytearray(record.values(b'BOD2')[0])
            struct.pack_into('<I', data, 0, struct.unpack_from('<I', data)[0] & ~(1 << 30))
            record.replace(b'BOD2', bytes(data))
        result.append(record)
        if variant['nodes']:
            addon = copy.deepcopy(fixed_addon)
            addon.form_id = variant['addon_id']
            addon.replace(b'EDID', (settings.prefix+name+'AA\0').encode())
            for tag in (b'MOD2', b'MOD3'):
                addon.replace(tag, (settings.asset_dir.replace('/', '\\')+'\\'+variant['file']+'\0').encode())
            result.append(addon)
    for name, flag in (('FaceHidingEquipment', 'hide_face'), ('HairHidingEquipment', 'hide_hair')):
        ids = sorted({i['original_form_id'] for i in (profile or {}).get('equipment', [])
                      if i.get(flag) and i.get('origin_plugin', 'Skyrim.esm').lower() == 'skyrim.esm'})
        result.append(Record(b'FLST', IDS[name], 0, [(b'EDID', (settings.prefix+name+'\0').encode()),
                                                  *[(b'LNAM', struct.pack('<I', n)) for n in ids]]))
    return result


def write_runtime(output, settings):
    if not settings.head_switch_enabled:
        return
    from equipment_runtime import rename_pex
    root = Path(__file__).parent
    name = script_name(settings)
    # Reuse the strict PEX renamer, with the head template's object-name string.
    data = (root/'runtime'/(TEMPLATE+'.pex')).read_bytes()
    data = rename_pex(data, name, template_name=TEMPLATE)
    target = Path(output)/'mod/scripts'
    target.mkdir(parents=True, exist_ok=True)
    (target/(name+'.pex')).write_bytes(data)
    target = Path(output)/'mod/source/scripts'
    target.mkdir(parents=True, exist_ok=True)
    source = (root/'runtime'/(TEMPLATE+'.psc')).read_text().replace(TEMPLATE, name)
    (target/(name+'.psc')).write_text(source, encoding='utf8')
    logging.info('Private head visibility runtime: %s; SKSE skin refresh, no outfit mutation', name)


def validate_head_models(output, settings):
    """Merged permanent models must be exact subsets of the original parts."""
    if not settings.head_switch_enabled:
        return []
    import numpy as np
    from custom_skeleton import NifFile, matrix
    from wardrobe import components
    root = Path(output)/'mod/meshes'/settings.asset_dir

    def signatures(path):
        result = Counter()
        with NifFile(str(path)) as nif:
            for shape in nif.shapes:
                if settings.physics_enabled and shape.name == 'V2SCollision_Body':
                    continue  # Physics-only body; validated by the FSMP readback.
                digest = hashlib.sha256()
                for value in (shape.verts, shape.tris, shape.uvs, shape.normals, matrix(shape.transform)):
                    digest.update(np.asarray(value).tobytes())
                props = shape.shader.properties
                alpha = ((shape.alpha_property.properties.flags, shape.alpha_property.properties.threshold)
                         if shape.has_alpha_property else None)
                digest.update(json.dumps([shape.textures, shape.bone_weights,
                              int(props.Shader_Flags_1), int(props.Shader_Flags_2), alpha], sort_keys=True).encode())
                result[digest.hexdigest()] += 1
        return result

    parts = [p for p in components(settings) if p['role'] == 'fixed']
    sources = {p['id']: signatures(root/p['file']) for p in parts}
    result = []
    for variant in [{'file': 'fixed_full.nif', 'nodes': settings.appearance_parts['fixed']}, *head_variants(settings)]:
        expected = Counter()
        for part in parts:
            if set(part['nodes']).issubset(variant['nodes']):
                expected.update(sources[part['id']])
        if not variant['nodes']:
            result.append({'file': None, 'shapes': 0})
            continue
        if signatures(root/variant['file']) != expected:
            raise ValueError('Head visibility model changed original appearance: '+variant['file'])
        result.append({'file': variant['file'], 'shapes': sum(expected.values())})
    logging.info('Head models retained original geometry, weights, UVs, normals and material flags: %s', result)
    return result
