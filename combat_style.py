"""Private CSTY copies; field order follows xEdit's TES5 definition and CK."""
import copy
import logging
import math
import struct

CUSTOM_STYLE_ID = 0x01000880


def field(tag, index, key, ja, en, section, limit=1, basic=False):
    return dict(tag=tag, index=index, key=key, labels={'ja': ja, 'en': en},
                section=section, slider_max=limit, basic=basic)


FIELDS = [
    field('CSGD', 0, 'offensive', '攻撃への積極性', 'Offensive Mult', 'general'),
    field('CSGD', 1, 'defensive', '防御への積極性', 'Defensive Mult', 'general'),
    field('CSGD', 2, 'group_offensive', '集団戦での攻撃への積極性', 'Group Offensive Mult', 'general'),
    field('CSGD', 3, 'melee_score', '近接武器の優先度', 'Equipment Score Mult - Melee', 'general', 10, True),
    field('CSGD', 4, 'magic_score', '魔法の優先度', 'Equipment Score Mult - Magic', 'general', 10, True),
    field('CSGD', 5, 'ranged_score', '弓・クロスボウの優先度', 'Equipment Score Mult - Ranged', 'general', 10, True),
    field('CSGD', 6, 'shout_score', 'シャウトの優先度', 'Equipment Score Mult - Shout', 'general', 10),
    field('CSGD', 7, 'unarmed_score', '素手の優先度', 'Equipment Score Mult - Unarmed', 'general', 10),
    field('CSGD', 8, 'staff_score', '杖の優先度', 'Equipment Score Mult - Staff', 'general', 10),
    field('CSGD', 9, 'avoid_threat', '脅威を避ける傾向', 'Avoid Threat Chance', 'general'),
    field('CSME', 0, 'attack_staggered', 'よろめいた相手への攻撃', 'Attack Staggered Mult', 'melee', 10),
    field('CSME', 1, 'power_attack_staggered', 'よろめいた相手への強攻撃', 'Power Attack Staggered Mult', 'melee', 10),
    field('CSME', 2, 'power_attack_blocking', '防御中の相手への強攻撃', 'Power Attack Blocking Mult', 'melee', 10),
    field('CSME', 3, 'bash', 'バッシュ', 'Bash Mult', 'melee', 10),
    field('CSME', 4, 'bash_recoil', '攻撃を弾かれた相手へのバッシュ', 'Bash Recoil Mult', 'melee', 10),
    field('CSME', 5, 'bash_attack', '攻撃中の相手へのバッシュ', 'Bash Attack Mult', 'melee', 10),
    field('CSME', 6, 'bash_power_attack', '強攻撃中の相手へのバッシュ', 'Bash Power Attack Mult', 'melee', 10),
    field('CSME', 7, 'special_attack', '特殊攻撃', 'Special Attack Mult', 'melee', 10),
    field('CSCR', 0, 'circle', '相手の周りを回り込む傾向', 'Circle Mult', 'close'),
    field('CSCR', 1, 'fallback', '後退する傾向', 'Fallback Mult', 'close'),
    field('CSCR', 2, 'flank_distance', '側面へ回る距離の調整', 'Flank Distance', 'close'),
    field('CSCR', 3, 'stalk_time', '側面で機をうかがう時間の調整', 'Stalk Time', 'close'),
    field('CSLR', 0, 'strafe', '遠距離戦で横移動する傾向', 'Strafe Mult', 'long'),
    field('CSFL', 0, 'hover_chance', 'ホバリングする傾向', 'Hover Chance', 'flight'),
    field('CSFL', 1, 'dive_bomb', '急降下攻撃する傾向', 'Dive Bomb Chance', 'flight'),
    field('CSFL', 2, 'ground_attack', '地上攻撃する傾向', 'Ground Attack Chance', 'flight'),
    field('CSFL', 3, 'hover_time', 'ホバリング時間の調整', 'Hover Time', 'flight'),
    field('CSFL', 4, 'ground_attack_time', '地上攻撃時間の調整', 'Ground Attack Time', 'flight'),
    field('CSFL', 5, 'perch_attack', '着地場所から攻撃する傾向', 'Perch Attack Chance', 'flight'),
    field('CSFL', 6, 'perch_attack_time', '着地場所からの攻撃時間の調整', 'Perch Attack Time', 'flight'),
    field('CSFL', 7, 'flying_attack', '飛行中に攻撃する傾向', 'Flying Attack Chance', 'flight'),
]
BY_KEY = {f['key']: f for f in FIELDS}


def read_style(record):
    values = {}
    for f in FIELDS:
        data = record.values(f['tag'].encode())
        offset = 4 * f['index']
        if data and len(data[0]) >= offset + 4:
            values[f['key']] = struct.unpack_from('<f', data[0], offset)[0]
    if not values:
        return None
    data = record.values(b'DATA')
    flags = struct.unpack('<I', data[0])[0] if data else 0
    if record.flags & 0x80000:
        flags |= 4
    return {'source': record.editor_id, 'values': values, 'flags': flags & 7}


def validate_custom(value):
    if not isinstance(value, dict):
        raise ValueError('Custom combat style must be an object')
    if not value:
        return
    if set(value) != {'source', 'values', 'flags'} or not isinstance(value['source'], str) or not value['source']:
        raise ValueError('Custom combat style requires source, values and flags')
    if type(value['flags']) is not int or not 0 <= value['flags'] <= 7:
        raise ValueError('Invalid custom combat style flags')
    if not isinstance(value['values'], dict) or not value['values'] or set(value['values']) - BY_KEY.keys():
        raise ValueError('Invalid custom combat style fields')
    for key, number in value['values'].items():
        f = BY_KEY[key]
        # CK's normalized controls use 0..1; equipment/melee multipliers 0..10.
        if type(number) not in (int, float) or not 0 <= number <= f['slider_max'] or not math.isfinite(number):
            raise ValueError(f"Combat style {key} must be between 0 and {f['slider_max']}")


def private_style(settings, catalog):
    config = settings.combat_style_custom
    validate_custom(config)
    source = catalog.require(config['source'], b'CSTY')
    if read_style(source) is None:
        raise ValueError('Selected combat style has no editable data')
    result = copy.deepcopy(source)
    result.form_id = CUSTOM_STYLE_ID
    result.replace(b'EDID', (settings.prefix+'CombatStyle\0').encode())
    order = [*dict.fromkeys(f['tag'] for f in FIELDS), 'DATA']
    for tag in order[:-1]:
        selected = [f for f in FIELDS if f['tag'] == tag and f['key'] in config['values']]
        if not selected:
            continue
        original = result.values(tag.encode())
        blob = bytearray(original[0] if original else b'')
        length = 4 * (max(f['index'] for f in selected) + 1)
        blob.extend(bytes(max(0, length - len(blob))))
        for f in selected:
            struct.pack_into('<f', blob, 4*f['index'], config['values'][f['key']])
        if original:
            result.replace(tag.encode(), bytes(blob))
        else:
            later = {t.encode() for t in order[order.index(tag)+1:]}
            index = next((i for i, (key, _) in enumerate(result.fields) if key in later), len(result.fields))
            result.fields.insert(index, (tag.encode(), bytes(blob)))
    old = source.values(b'DATA')
    flags = struct.unpack('<I', old[0])[0] if old else 0
    result.replace(b'DATA', struct.pack('<I', (flags & ~7) | config['flags']))
    # Older CSTY records may also store dual wield on the record header.
    result.flags = (result.flags & ~0x80000) | (0x80000 if config['flags'] & 4 else 0)
    baseline = read_style(source)
    changed = [key for key, value in config['values'].items() if baseline['values'].get(key) != value]
    logging.info('Private combat style %s (%08X) copied from %s (%08X); changed=%s flags=%s',
                 result.editor_id, result.form_id, source.editor_id, source.form_id, changed, config['flags'])
    return result


def validate_generated_style(generated, settings):
    """Read the delivered CSTY and NPC link, including float32 serialization."""
    styles = [r for r in generated if r.kind == b'CSTY']
    npc = next(r for r in generated if r.kind == b'NPC_' and r.editor_id == settings.prefix+'NPC')
    if settings.combat_style_mode != 'custom':
        if styles or any(struct.unpack('<I', value)[0] >> 24 == 1 for value in npc.values(b'ZNAM')):
            raise ValueError('Existing combat style unexpectedly references a private style')
        return
    if len(styles) != 1 or styles[0].form_id != CUSTOM_STYLE_ID or styles[0].editor_id != settings.prefix+'CombatStyle':
        raise ValueError('Private combat style identity/count mismatch')
    if npc.values(b'ZNAM') != [struct.pack('<I', CUSTOM_STYLE_ID)]:
        raise ValueError('Follower does not reference its private combat style')
    style = styles[0]
    config = settings.combat_style_custom
    actual = read_style(style)
    flags = style.values(b'DATA')
    if (actual is None or not flags or struct.unpack('<I', flags[0])[0] & 7 != config['flags']
            or bool(style.flags & 0x80000) != bool(config['flags'] & 4)):
        raise ValueError('Private combat style flags differ from settings')
    for key, value in config['values'].items():
        if key not in actual['values'] or struct.pack('<f', actual['values'][key]) != struct.pack('<f', value):
            raise ValueError('Private combat style value differs from settings: '+key)
