"""Player shouts a follower can learn: SPLO references to official SHOU records, never copies."""
import json
import logging
from pathlib import Path
import re
import struct

from plugin import records

# Player-learnable shouts (docs/intent/follower-shouts.md). No data rule separates them from
# NPC/dragon/quest versions, so the list is fixed: plugin, Editor ID, local FormID.
SHOUTS = (
    ('Skyrim.esm', 'animalAllegianceShout', 0x05FC77),
    ('Skyrim.esm', 'AuraWhisperShout', 0x07097B),
    ('Skyrim.esm', 'BecomeEtherealShout', 0x032920),
    ('Skyrim.esm', 'CallDragonShout', 0x046B8C),
    ('Skyrim.esm', 'CallofValorShout', 0x05196A),
    ('Skyrim.esm', 'ClearSkiesShout', 0x03CD34),
    ('Skyrim.esm', 'DisarmShout', 0x070981),
    ('Skyrim.esm', 'Dismay', 0x02395A),
    ('Skyrim.esm', 'DragonrendShout', 0x044250),
    ('Skyrim.esm', 'ElementalFuryShout', 0x032921),
    ('Skyrim.esm', 'FireBreathShout', 0x03F9EA),
    ('Skyrim.esm', 'FrostBreathShout', 0x05D16B),
    ('Skyrim.esm', 'IceFormShout', 0x070980),
    ('Skyrim.esm', 'KynesPeaceShout', 0x07097E),
    ('Skyrim.esm', 'MarkedforDeathShout', 0x07097C),
    ('Skyrim.esm', 'SlowTimeShout', 0x048AC9),
    ('Skyrim.esm', 'StormCallShout', 0x07097D),
    ('Skyrim.esm', 'ThrowVoiceShout', 0x07097F),
    ('Skyrim.esm', 'UnrelentingForceShout', 0x013E07),
    ('Skyrim.esm', 'WhirlwindSprintShout', 0x02F7BA),
    ('Dawnguard.esm', 'DLC1DrainVitalityShout', 0x008A62),
    ('Dawnguard.esm', 'DLC1SoulTearShout', 0x007CB6),
    ('Dawnguard.esm', 'DLC1SummonDragonShout', 0x0030D2),
    ('Dragonborn.esm', 'DLC2BattleFuryShout', 0x02AD09),
    ('Dragonborn.esm', 'DLC2BendWillShout', 0x0179D8),
    ('Dragonborn.esm', 'DLC2CycloneShout', 0x0200C0),
    ('Dragonborn.esm', 'DLC2DragonAspectShout', 0x01DF92),
)
DLC_NAMES = {'Dawnguard.esm': 'Dawnguard', 'HearthFires.esm': 'Hearthfire', 'Dragonborn.esm': 'Dragonborn'}
KEY = re.compile(r'([A-Za-z0-9_-]+\.(?:esm|esl|esp)):([0-9A-Fa-f]{6})')


def key(plugin, local):
    return f'{plugin}:{local:06X}'


def entry(value):
    """SHOUTS row for an OfficialCatalog key, or None."""
    match = KEY.fullmatch(value) if isinstance(value, str) else None
    if not match:
        return None
    plugin, local = match[1].casefold(), int(match[2], 16)
    return next((row for row in SHOUTS if row[0].casefold() == plugin and row[2] == local), None)


def dlc_label(plugin):
    return f'{DLC_NAMES[plugin]} ({plugin})' if plugin in DLC_NAMES else plugin


def require(catalog, row):
    plugin, editor_id, local = row
    record = catalog.find(plugin, editor_id, b'SHOU')
    if record is None or catalog.identity(record) != (plugin, local):
        raise ValueError(f'ゲームのデータにシャウト {editor_id} ({key(plugin, local)}) が見つかりません。'
                         f'{plugin} が壊れているか、想定と違う版です。')
    return record


def resolve(catalog, keys):
    """Catalog records for settings.shouts; a missing DLC is an error, never a silent drop."""
    result = []
    for value in keys:
        row = entry(value)
        if row is None:
            raise ValueError(f'このシャウトは選べません: {value}')
        if row[0] not in catalog.plugins:
            raise ValueError(f'シャウト {row[1]} ({value}) には {dlc_label(row[0])} が必要ですが、インストールされていません。')
        result.append(require(catalog, row))
    return result


def choices(catalog):
    """Wizard rows for installed plugins; a listed record missing from an installed plugin fails."""
    result = []
    for row in SHOUTS:
        if row[0] not in catalog.plugins:
            continue
        record = require(catalog, row)
        result.append({'id': catalog.key(record), 'editor_id': record.editor_id, 'plugin': row[0],
                       'dlc': DLC_NAMES.get(row[0]), 'label': catalog.label(record),
                       'labels': {'ja': catalog.label(record), 'en': catalog.label(record, language='en')},
                       'description': catalog.label(record, b'DESC'),
                       'descriptions': {'ja': catalog.label(record, b'DESC'),
                                        'en': catalog.label(record, b'DESC', language='en')}})
    return result


def unavailable(catalog):
    """Allowlisted shouts whose plugin is not installed, so the wizard can show and remove them."""
    return [{'id': key(plugin, local), 'editor_id': editor_id, 'plugin': plugin, 'dlc': DLC_NAMES.get(plugin),
             'requires': dlc_label(plugin)}
            for plugin, editor_id, local in SHOUTS if plugin not in catalog.plugins]


def official_references(game_data, settings, fitting=None, catalog=None):
    """Combined follower masters (footsteps + shouts) and references numbered against them.

    Internal numbering (follower_plugin): Skyrim.esm 0, follower 1, masters[i] is 2 + i.
    """
    if not settings.shouts and not fitting:
        return {'masters': [], 'sounds': {}, 'shouts': []}
    from official_catalog import OfficialCatalog
    from skypatcher import footstep_bindings
    catalog = catalog or OfficialCatalog(game_data)
    shouts = resolve(catalog, settings.shouts)
    masters, sounds = footstep_bindings(game_data, fitting or {'equipment': []},
                                        [catalog.identity(r)[0] for r in shouts], catalog)
    return {'masters': masters, 'sounds': sounds,
            'shouts': [catalog.follower_form_id(r.form_id, masters) for r in shouts]}


def master_names(header):
    return [value.rstrip(b'\0').decode('utf8') for value in header.values(b'MAST')]


def game_folder(output, game_data=None):
    """Game Data folder for the output check: the caller's, else the one npc.json recorded at build time."""
    if game_data is None:
        npc = Path(output) / 'npc.json'
        game_data = json.loads(npc.read_text(encoding='utf8')).get('game_data') if npc.is_file() else None
        if not game_data:
            raise ValueError('シャウトと装備の足音の検査には、ゲームの Data フォルダが必要です。'
                             f'{npc} に game_data の記録が無いので、Data フォルダを指定して検査してください'
                             '(validate.py は --game-data)。')
    data = Path(game_data)
    if not (data / 'Skyrim.esm').is_file():
        raise ValueError(f'ゲームの Data フォルダに Skyrim.esm がありません: {data}。'
                         'ゲームを別の場所へ移した場合は、今の Data フォルダを指定して検査してください。')
    return data


def footstep_sounds(addon, plugin_of):
    """(owner plugin, local id) of each non-zero ARMA SNDD; plugin_of maps the index byte to a file name."""
    result = set()
    for blob in addon.values(b'SNDD'):
        value = struct.unpack('<I', blob)[0]
        if value:
            result.add((plugin_of(value).casefold(), value & 0xFFFFFF))
    return result


def validate_footsteps(disk, masters, fitting, catalog):
    """Written fitted ARMA SNDD, read through the ESP's own MAST list, names the source addon's sound.

    Independent of official_references: expected values come from the source addon in the catalog,
    observed values only from the bytes and master list of the written plugin."""
    expected = {}
    for item in fitting['equipment']:
        sounds = expected.setdefault(item['addon_local_id'], set())
        if item.get('source_addon_key'):
            source = catalog.require(item['source_addon_key'], b'ARMA')
            sounds |= footstep_sounds(source, lambda v: catalog.plugins[v >> 24])
    own, checked, fitting_ids = len(masters), {}, set(expected)

    def master(value):
        if value >> 24 >= own:
            raise ValueError(f'Fitted addon footstep {value:08X} has no master (masters: {own})')
        return masters[value >> 24]
    for addon in disk:
        if addon.kind != b'ARMA' or addon.form_id >> 24 != own:
            continue
        local = addon.form_id & 0xFFFFFF
        observed = footstep_sounds(addon, master)
        wanted = expected.pop(local, set())
        if len(wanted) > 1:
            raise ValueError(f'Fitted addon {local:06X} has conflicting source footstep sounds')
        if observed != wanted:
            raise ValueError(f'Addon {local:06X} footsteps {sorted(observed)} differ from the '
                             f'source addon {sorted(wanted)}')
        if local in fitting_ids:
            checked[local] = observed
    if expected:
        raise ValueError(f'Fitted addons missing from the written plugin: {[f"{n:06X}" for n in expected]}')
    logging.info('Validated fitted footsteps against source addons: %s',
                 {f'{n:06X}': sorted(s) for n, s in checked.items()})


def validate_generated(generated, settings, output, game_data=None):
    """Read the written ESP back: SPLO shouts resolve to the selected SHOU in their master file,
    and fitted ARMA footsteps to the source addon's sound."""
    output = Path(output)
    npc = next(r for r in generated if r.kind == b'NPC_' and r.editor_id == settings.prefix + 'NPC')
    spells = npc.values(b'SPLO')
    if len(spells) != len(settings.spells) + len(settings.shouts):
        raise ValueError(f'Follower SPLO has {len(spells)} entries; settings select '
                         f'{len(settings.spells)} spells and {len(settings.shouts)} shouts')
    if npc.values(b'SPCT') != ([struct.pack('<I', len(spells))] if spells else []):
        raise ValueError('Follower SPCT differs from its SPLO count')
    header = next((r for r in generated if r.kind == b'TES4'), None)
    if not settings.shouts and not settings.fitting_enabled:
        if header is not None and master_names(header) != ['Skyrim.esm']:
            raise ValueError('Follower without shouts or fitting must use only Skyrim.esm as master')
        return
    data = game_folder(output, game_data)
    fitting = json.loads((output / 'armor-fitting.json').read_text()) if settings.fitting_enabled else None
    from official_catalog import OfficialCatalog
    catalog = OfficialCatalog(data)
    # Recomputed with the same official_references the build used: catches a stale or edited
    # header, not an error in official_references itself. The SNDD/SPLO readbacks below are independent.
    expected = ['Skyrim.esm', *official_references(data, settings, fitting, catalog)['masters']]
    disk = list(records(output / 'mod' / settings.plugin_name, {b'TES4', b'NPC_', b'ARMA'}))
    masters = master_names(disk[0])
    if masters != expected:
        raise ValueError(f'Follower masters {masters} differ from the computed {expected}')
    if fitting:
        validate_footsteps(disk, masters, fitting, catalog)
    disk_npc = next(r for r in disk if r.kind == b'NPC_' and r.editor_id == settings.prefix + 'NPC')
    values = [struct.unpack('<I', v)[0] for v in disk_npc.values(b'SPLO')]
    if any(v >> 24 for v in values[:len(settings.spells)]):
        raise ValueError('Follower spells must reference Skyrim.esm')
    owned = {}
    for value, wanted in zip(values[len(settings.spells):], settings.shouts, strict=True):
        index = value >> 24
        if index >= len(masters):
            raise ValueError(f'Shout reference {value:08X} has no master (masters: {len(masters)})')
        owner = masters[index]
        if owner not in owned:
            loaded = list(records(data / owner, {b'TES4', b'SHOU'}))
            own = len(master_names(loaded[0]))
            owned[owner] = {r.form_id & 0xFFFFFF for r in loaded if r.kind == b'SHOU' and r.form_id >> 24 == own}
        if value & 0xFFFFFF not in owned[owner]:
            raise ValueError(f'Shout reference {value:08X} is not a SHOU record of {owner}')
        if key(owner, value & 0xFFFFFF).casefold() != wanted.casefold():
            raise ValueError(f'Shout reference {key(owner, value & 0xFFFFFF)} differs from settings ({wanted})')
    logging.info('Validated follower shouts: %s; masters %s', settings.shouts, masters)
