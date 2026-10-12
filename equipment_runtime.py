"""Private per-follower Papyrus bindings, inventory, and replacement groups."""
import logging
from pathlib import Path
import struct

from plugin import Record
from wardrobe import equipment_group

ROOT = Path(__file__).resolve().parent
TEMPLATE_NAME = 'V2SInitialWardrobe'
PROPERTIES = ('InitialItems', 'BodyClothes', 'HandsClothes', 'FeetClothes',
              'BodyEquipment', 'HandsEquipment', 'FeetEquipment')
LIST_IDS = {name: 0x01000840 + i for i, name in enumerate(PROPERTIES)}


def pex_strings(data):
    if data[:8] != bytes.fromhex('fa57c0de03020001'):
        raise ValueError('Expected Skyrim PEX 3.2 (game ID 1)')
    offset = 16
    metadata = []
    def read_string():
        nonlocal offset
        size = struct.unpack_from('>H', data, offset)[0]
        offset += 2
        value = data[offset:offset+size]
        if len(value) != size:
            raise ValueError('Truncated PEX string')
        offset += size
        return value
    for _ in range(3):
        metadata.append(read_string())
    start = offset
    count = struct.unpack_from('>H', data, offset)[0]
    offset += 2
    strings = [read_string() for _ in range(count)]
    return metadata, start, offset, strings


def rename_pex(data, script_name, template_name=TEMPLATE_NAME):
    _, _, end, strings = pex_strings(data)
    def encoded(value):
        return struct.pack('>H', len(value))+value
    matches = [s.lower() == template_name.lower().encode() for s in strings]
    replacements = [script_name.encode() if match else s for s, match in zip(strings, matches)]
    if not any(matches):
        raise ValueError('PEX template script name not found')
    # String indices/object sizes remain unchanged; only the string table grows.
    result = data[:16] + b''.join(encoded(v) for v in (
        (script_name+'.psc').encode(), b'VRM2Skyrim', b'VRM2Skyrim'))
    result += struct.pack('>H', len(strings)) + b''.join(encoded(v) for v in replacements) + data[end:]
    pex_strings(result)
    return result


def script_name(settings):
    return settings.prefix+'Wardrobe'


def vmad(settings):
    def string(value):
        raw = value.encode()
        return struct.pack('<H', len(raw))+raw
    payload = struct.pack('<hhh', 5, 2, 2 if settings.head_switch_enabled else 1)+string(script_name(settings))+struct.pack('<BH', 0, len(PROPERTIES))
    for prop in PROPERTIES:
        payload += string(prop)+bytes((1, 1))+struct.pack('<HhI', 0, -1, LIST_IDS[prop])
    if settings.head_switch_enabled:
        from gear_head_runtime import binding
        payload += binding(settings)
    return payload


def runtime_records(settings, catalog=None, profile=None):
    groups = {name: [] for name in PROPERTIES}
    for i, garment in enumerate(settings.appearance_parts['garments']):
        form_id = 0x01000811 + 2*i
        if garment['equipped']:
            groups['InitialItems'].append(form_id)
        category = equipment_group(garment)
        if category != 'accessory':
            groups[category.title()+'Clothes'].append(form_id)
    equipment = profile['equipment'] if profile else []
    names = list(dict.fromkeys(item['editor_id'] for item in equipment)) if profile else settings.fit_armors
    for name in names:
        if catalog is not None:
            armor = catalog.require(name, b'ARMO')
            form_id = armor.form_id
            mask = struct.unpack_from('<I', armor.values(b'BOD2')[0])[0]
        else:
            item = next(i for i in equipment if i['editor_id'] == name)
            if item.get('origin_plugin', 'Skyrim.esm').lower() != 'skyrim.esm':
                continue  # Combined patch supplies DLC references in its own master order.
            form_id = item['original_form_id']
            mask = item.get('armor_mask', sum(1 << (slot-30) for slot in item['slots']))
        for slot, category in ((32, 'Body'), (33, 'Hands'), (37, 'Feet')):
            if mask & (1 << (slot-30)) and form_id not in groups[category+'Equipment']:
                groups[category+'Equipment'].append(form_id)
    return [Record(b'FLST', LIST_IDS[name], 0, [
        (b'EDID', (settings.prefix+name+'\0').encode()),
        *[(b'LNAM', struct.pack('<I', form_id)) for form_id in groups[name]]]) for name in PROPERTIES]


def write_runtime(output, settings):
    if not settings.armor_support:
        return
    target = Path(output)/'mod/scripts'
    target.mkdir(parents=True, exist_ok=True)
    name = script_name(settings)
    (target/(name+'.pex')).write_bytes(rename_pex((ROOT/'runtime'/ (TEMPLATE_NAME+'.pex')).read_bytes(), name))
    source_dir = Path(output)/'mod/source/scripts'
    source_dir.mkdir(parents=True, exist_ok=True)
    source = (ROOT/'runtime'/(TEMPLATE_NAME+'.psc')).read_text(encoding='utf8').replace(TEMPLATE_NAME, name)
    (source_dir/(name+'.psc')).write_text(source, encoding='utf8')
    logging.info('Private wardrobe runtime: %s; equip conflicts only, no inventory/outfit resets', name)
