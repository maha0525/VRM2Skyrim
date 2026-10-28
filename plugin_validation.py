"""Generated follower record counts and references, shared with the output gate."""
import json
import logging
from pathlib import Path
import struct

from wardrobe import skin_components
from gear_head_runtime import head_variants
from equipment_runtime import PROPERTIES
from combat_style import validate_generated_style


def validate_private_records(generated, settings, output, game_data=None):
    """Check the same generated plugin contract used by the final output gate.

    game_data: the game's Data folder; without it the shout/footstep check uses npc.json's record."""
    output = Path(output)
    local_ids = {
        record.form_id for record in generated if record.kind not in (b"TES4", b"CELL")
    }
    expected_records = (
        9
        if not settings.armor_support
        else 9 + len(PROPERTIES)
        + len(skin_components(settings))
        + 2 * len(settings.appearance_parts["garments"])
        + (len({i['addon_local_id'] for i in json.loads((output/'armor-fitting.json').read_text())['equipment']})
           if settings.fitting_enabled else 0)
        + ((5 + sum(bool(p['nodes']) for p in head_variants(settings))) if settings.head_switch_enabled else 0)
    )
    expected_records += int(settings.sitting_enabled) + int(settings.combat_style_mode == 'custom')
    expected_records += 2 * (settings.weapon_mode == 'original')  # private WEAP + first-person STAT
    if len(local_ids) != expected_records:
        raise ValueError(f"Expected {expected_records} private follower records, found {len(local_ids)} "
                         f"(combat style: {settings.combat_style_mode})")
    if any(form_id >> 24 != 1 for form_id in local_ids):
        raise ValueError("Plugin overrides an existing record")
    for record in generated:
        for tag, payload in record.fields:
            reference_tags = {b"ARMO": {b"MODL", b"RNAM"}, b"ARMA": {b"RNAM", b"MODL"},
                              b"NPC_": {b"DOFT", b"RNAM", b"WNAM", b"CNTO", b"ZNAM"},
                                b"RACE": {b"WNAM", b"HEAD"}, b"OTFT": {b"INAM"},
                                b"HDPT": {b"RNAM"}, b"FLST": {b"LNAM"}, b"WEAP": {b"WNAM"}}
            if tag in reference_tags.get(record.kind, set()):
                if (tag == b"CNTO" and len(payload) != 8) or (tag != b"CNTO" and len(payload) % 4):
                    raise ValueError("Malformed plugin reference field")
                refs = (
                    [payload[:4]]
                    if tag == b"CNTO"
                    else [payload[i : i + 4] for i in range(0, len(payload), 4)]
                )
                for ref in refs:
                    value = struct.unpack("<I", ref)[0]
                    if value >> 24 == 1 and value not in local_ids:
                        raise ValueError("Dangling local record reference")
    validate_generated_style(generated, settings)
    from shouts import validate_generated
    validate_generated(generated, settings, output, game_data)
    from weapon import validate_weapon_records
    npc_path = output / 'npc.json'
    report = json.loads(npc_path.read_text(encoding='utf8')).get('original_weapon') if npc_path.is_file() else None
    validate_weapon_records(generated, settings, report)
    logging.info('Validated private plugin: %s records; combat style=%s',
                 len(local_ids), settings.combat_style_mode)
    return local_ids


