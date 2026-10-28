"""Follower shouts: settings, SPLO/SPCT, DLC masters, reference numbering and the output check."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from build_npc import configure_actor
from environment import find_game
from follower_plugin import follower_records, write_follower
from game_catalog import GameCatalog
from official_catalog import OfficialCatalog
from plugin import Record, records
from settings import FollowerSettings
import shouts
from shouts import SHOUTS, official_references, validate_generated

ROOT = Path(__file__).resolve().parents[1]
CYCLONE, FORCE, SOUL_TEAR = 'Dragonborn.esm:0200C0', 'Skyrim.esm:013E07', 'Dawnguard.esm:007CB6'
SOUND, ADDON, SPELL = 0x001234, 0x000ABD, 0x000ABC  # Dragonborn.esm local IDs in the fake data
MASTERS = {'Skyrim.esm': (), 'Update.esm': ('Skyrim.esm',), 'Dawnguard.esm': ('Skyrim.esm', 'Update.esm'),
           'Dragonborn.esm': ('Skyrim.esm', 'Update.esm')}
PARTS = {'body': [1], 'underwear': [2], 'fixed': [3], 'garments': [
    dict(id='coat', name='Coat', nodes=[4], slot=44, armor_type='clothing', armor_rating=0,
         weight=1, value=1, equipped=True)]}


def uint(value):
    return struct.pack('<I', value)


def plugin_file(path, masters, items):
    """Minimal unlocalized master: TES4 plus one top group per record type."""
    header = Record(b'TES4', 0, 0, [(b'HEDR', struct.pack('<fII', 1.7, len(items), 0x800)),
                                    *[(tag, value) for name in masters
                                      for tag, value in ((b'MAST', name.encode() + b'\0'), (b'DATA', bytes(8)))]])
    body = b''
    for kind in dict.fromkeys(r.kind for r in items):
        payload = b''.join(r.encode() for r in items if r.kind == kind)
        body += struct.pack('<4sI4sIHHHH', b'GRUP', 24 + len(payload), kind, 0, 0, 0, 0, 0) + payload
    path.write_bytes(header.encode() + body)


def fake_data(directory, plugins=('Skyrim.esm', 'Update.esm', 'Dawnguard.esm', 'Dragonborn.esm'), missing=()):
    data = Path(directory) / 'Data'
    data.mkdir()
    for name in plugins:
        own = len(MASTERS[name]) << 24
        items = [Record(b'SHOU', own | local, 0, [(b'EDID', editor_id.encode() + b'\0'),
                                                 (b'FULL', editor_id[:12].encode() + b'\0'),
                                                 (b'DESC', b'About ' + editor_id.encode() + b'\0')])
                 for plugin, editor_id, local in SHOUTS if plugin == name and editor_id not in missing]
        if name == 'Dragonborn.esm':
            items += [Record(b'SPEL', own | SPELL, 0, [(b'EDID', b'NotAShout\0')]),
                      Record(b'ARMA', own | ADDON, 0, [(b'EDID', b'SkaalBootsAA\0'), (b'SNDD', uint(own | SOUND))])]
        plugin_file(data / name, MASTERS[name], items)
    return data


def fitted_settings(**values):
    return FollowerSettings(armor_support=True, appearance_source_sha256='a' * 64, appearance_parts=PARTS,
                            sitting_enabled=False, **values)


def profile(plugin):
    return {'plugin': plugin, 'equipment': [dict(editor_id='SkaalBoots', original_form_id=0x04000AAA,
                                                 origin_plugin='Dragonborn.esm', origin_local_id=0xAAA,
                                                 addon_local_id=0x1000, slots=[37], priority=0,
                                                 source_addon_key=f'Dragonborn.esm:{ADDON:06X}',
                                                 file='fitted_test_1.nif')]}


class FakeCatalog:
    def __init__(self):
        self.ids = {}

    def require(self, name, kind=None):
        return Record(kind or b'NONE', self.ids.setdefault(name, 0x100 + len(self.ids)), 0, [])


class SettingsTests(unittest.TestCase):
    def test_round_trip_and_old_files_load_as_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            FollowerSettings(shouts=[CYCLONE, FORCE]).save(path)
            self.assertEqual(FollowerSettings.load(path).shouts, [CYCLONE, FORCE])
            old = json.loads(path.read_text(encoding='utf8'))
            del old['shouts']
            self.assertEqual(FollowerSettings.from_dict(old).shouts, [])
        self.assertEqual(FollowerSettings().shouts, [])
        for invalid in ('Skyrim.esm:013E07', ['UnrelentingForceShout'], [1], [FORCE, FORCE.lower()],
                        ['Skyrim.esm:13E07']):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                FollowerSettings(shouts=invalid)

    def test_allowlist_has_the_27_approved_shouts(self):
        self.assertEqual(len(SHOUTS), 27)
        self.assertEqual(len({(p, e) for p, e, _ in SHOUTS}), 27)
        self.assertEqual([sum(p == name for p, _, _ in SHOUTS) for name in ('Skyrim.esm', 'Dawnguard.esm', 'Dragonborn.esm')],
                         [20, 3, 4])
        self.assertEqual(shouts.entry(CYCLONE)[1], 'DLC2CycloneShout')
        self.assertEqual(shouts.entry('dragonborn.esm:0200c0')[1], 'DLC2CycloneShout')
        self.assertIsNone(shouts.entry('Dragonborn.esm:000ABC'))


class SpellListTests(unittest.TestCase):
    def configured(self, spells, shout_ids):
        npc = Record(b'NPC_', 0x01000800, 0, [
            (b'EDID', b'Template\0'), (b'FULL', b'T\0'), (b'SHRT', b'T\0'), (b'ACBS', bytes(24)),
            (b'RNAM', uint(1)), (b'SPCT', uint(1)), (b'SPLO', uint(0x99)), (b'AIDT', bytes(20)),
            (b'DOFT', uint(1)), (b'VTCK', uint(1)), (b'CNAM', uint(1)), (b'ZNAM', uint(1)),
            (b'NAM6', bytes(4)), (b'DNAM', bytes(52))])
        catalog = FakeCatalog()
        settings = FollowerSettings(spells=spells, shouts=[CYCLONE, FORCE][:len(shout_ids)])
        configure_actor(npc, settings, catalog, (0, 0, 0), shout_ids)
        return npc, [uint(catalog.ids[name]) for name in spells]

    def test_spells_first_then_shouts_and_spct_counts_both(self):
        for spells, shout_ids in ((['Firebolt'], []), ([], [0x040200C0]), (['Firebolt', 'FastHealing'], [0x040200C0, 0x13E07]),
                                  ([], [])):
            with self.subTest(spells=spells, shouts=shout_ids):
                npc, spell_values = self.configured(spells, shout_ids)
                expected = spell_values + [uint(v) for v in shout_ids]
                self.assertEqual(npc.values(b'SPLO'), expected)
                self.assertEqual(npc.values(b'SPCT'), [uint(len(expected))] if expected else [])
                tags = [tag for tag, _ in npc.fields]
                if expected:  # SPCT directly after RNAM, followed by every SPLO.
                    start = tags.index(b'RNAM') + 1
                    self.assertEqual(tags[start:start + len(expected) + 1], [b'SPCT'] + [b'SPLO'] * len(expected))

    def test_shout_reference_count_must_match_settings(self):
        npc = self.configured([], [])[0]
        with self.assertRaisesRegex(ValueError, 'Shout references'):
            configure_actor(npc, FollowerSettings(shouts=[CYCLONE]), FakeCatalog(), (0, 0, 0), [])


class SyntheticCatalogTests(unittest.TestCase):
    def test_choices_hide_missing_dlc_and_fail_on_missing_listed_record(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = OfficialCatalog(fake_data(directory, ('Skyrim.esm', 'Update.esm', 'Dragonborn.esm')))
            rows = shouts.choices(catalog)
            self.assertEqual(len(rows), 24)
            self.assertFalse(any(r['plugin'] == 'Dawnguard.esm' for r in rows))
            cyclone = next(r for r in rows if r['editor_id'] == 'DLC2CycloneShout')
            self.assertEqual((cyclone['id'], cyclone['dlc']), (CYCLONE, 'Dragonborn'))
            self.assertEqual(cyclone['descriptions'], {'ja': 'About DLC2CycloneShout', 'en': 'About DLC2CycloneShout'})
            self.assertIsNone(next(r for r in rows if r['id'] == FORCE)['dlc'])
            # Armor lookups by Editor ID never see shouts.
            self.assertNotIn('DLC2CycloneShout', catalog.by_editor_id)
        with tempfile.TemporaryDirectory() as directory:
            catalog = OfficialCatalog(fake_data(directory, missing=('DLC2BendWillShout',)))
            with self.assertRaisesRegex(ValueError, 'DLC2BendWillShout'):
                shouts.choices(catalog)

    def test_creation_shout_with_an_outside_master_does_not_break_the_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            data = fake_data(directory)
            # Creation masters: Skyrim.esm 0, Outside.esm 1 (not in the catalog), own records 2.
            plugin_file(data / 'ccTestCreation.esl', ('Skyrim.esm', 'Outside.esm'), [
                Record(b'ARMO', 0x02000801, 0, [(b'EDID', b'ccTestArmor\0')]),
                Record(b'SHOU', 0x02000802, 0, [(b'EDID', b'ccTestShout\0'),
                                                (b'SNAM', uint(0x01000123) + uint(0) + struct.pack('<f', 1.0))])])
            catalog = OfficialCatalog(data)
            self.assertIn('ccTestCreation.esl', catalog.plugins)
            self.assertEqual(catalog.key(catalog.require('ccTestArmor', b'ARMO')), 'ccTestCreation.esl:000801')
            self.assertFalse(any(catalog.source[r.form_id] == 'ccTestCreation.esl' for r in catalog.by_id.values()
                                 if r.kind == b'SHOU'))
            self.assertEqual(len(shouts.choices(catalog)), 27)
            # An ARMO reference into the outside master still fails, as before.
            plugin_file(data / 'ccTestCreation.esl', ('Skyrim.esm', 'Outside.esm'), [
                Record(b'ARMO', 0x02000801, 0, [(b'EDID', b'ccTestArmor\0'), (b'RNAM', uint(0x01000123))])])
            with self.assertRaisesRegex(ValueError, 'Unresolved master reference ccTestCreation.esl:01000123'):
                OfficialCatalog(data)

    def test_unavailable_rows_name_the_shout_and_missing_dlc(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = OfficialCatalog(fake_data(directory, ('Skyrim.esm', 'Update.esm', 'Dragonborn.esm')))
            rows = shouts.unavailable(catalog)
            self.assertEqual([r['editor_id'] for r in rows],
                             ['DLC1DrainVitalityShout', 'DLC1SoulTearShout', 'DLC1SummonDragonShout'])
            soul = rows[1]
            self.assertEqual((soul['id'], soul['dlc'], soul['requires']),
                             (SOUL_TEAR, 'Dawnguard', 'Dawnguard (Dawnguard.esm)'))
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(shouts.unavailable(OfficialCatalog(fake_data(directory))), [])

    def test_missing_dlc_is_an_error_naming_the_shout_and_dlc(self):
        with tempfile.TemporaryDirectory() as directory:
            data = fake_data(directory, ('Skyrim.esm', 'Update.esm', 'Dragonborn.esm'))
            catalog = OfficialCatalog(data)
            with self.assertRaisesRegex(ValueError, r'DLC1SoulTearShout .*Dawnguard \(Dawnguard\.esm\)'):
                shouts.resolve(catalog, [FORCE, SOUL_TEAR])
            with self.assertRaisesRegex(ValueError, '選べません'):
                shouts.resolve(catalog, ['Dragonborn.esm:000ABC'])
            game = GameCatalog.__new__(GameCatalog)
            game.path = data / 'Skyrim.esm'
            game.follower_voice_ids = game.marriage_voice_ids = {1}
            game.require = lambda name, kind=None: Record(kind, 1, 0, [])
            game.validate_settings(FollowerSettings(shouts=[CYCLONE, FORCE]))
            with self.assertRaisesRegex(ValueError, r'DLC1SoulTearShout .*Dawnguard'):
                game.validate_settings(FollowerSettings(shouts=[SOUL_TEAR]))

    def test_combined_masters_renumber_footsteps_and_shouts(self):
        with tempfile.TemporaryDirectory() as directory:
            data = fake_data(directory)
            fitting = profile('Probe.esp')
            alone = official_references(data, FollowerSettings(), fitting)
            self.assertEqual(alone['masters'], ['Update.esm', 'Dragonborn.esm'])
            self.assertEqual(alone['sounds'], {0x1000: 3 << 24 | SOUND})
            both = official_references(data, FollowerSettings(shouts=[SOUL_TEAR, FORCE, CYCLONE]), fitting)
            # Dawnguard.esm joins between Update.esm and Dragonborn.esm: Dragonborn moves from 3 to 4.
            self.assertEqual(both['masters'], ['Update.esm', 'Dawnguard.esm', 'Dragonborn.esm'])
            self.assertEqual(both['sounds'], {0x1000: 4 << 24 | SOUND})
            self.assertEqual(both['shouts'], [3 << 24 | 0x007CB6, 0x013E07, 4 << 24 | 0x0200C0])
            only = official_references(data, FollowerSettings(shouts=[FORCE]))
            self.assertEqual((only['masters'], only['shouts']), ([], [0x013E07]))
            self.assertEqual(official_references(data, FollowerSettings()), {'masters': [], 'sounds': {}, 'shouts': []})


class OutputCheckTests(unittest.TestCase):
    def write(self, directory, data, settings, splo, extras, spct=None, fitting=None, sndd=0, npc=None, addons=None):
        """Write a follower ESP whose NPC carries the given internal SPLO values.

        sndd: internal SNDD of fitted addon 001000; addons: {local id: internal SNDD} replaces it."""
        output = Path(directory) / 'out'
        (output / 'mod').mkdir(parents=True)
        if npc is not False:
            (output / 'npc.json').write_text(json.dumps({'game_data': str(data)} if npc is None else npc))
        if fitting:
            (output / 'armor-fitting.json').write_text(json.dumps(fitting))
        fields = [(b'EDID', (settings.prefix + 'NPC\0').encode()), (b'RNAM', uint(0x01000804))]
        if splo:
            fields += [(b'SPCT', uint(len(splo) if spct is None else spct))] + [(b'SPLO', uint(v)) for v in splo]
        items = [Record(b'NPC_', 0x01000800, 0, fields)]
        if fitting:
            for local, value in ({0x1000: sndd} if addons is None else addons).items():
                items.append(Record(b'ARMA', 0x01000000 | local, 0,
                                    [(b'RNAM', uint(0x01000804)), *([(b'SNDD', uint(value))] if value is not None else [])]))
        cell = Record(b'CELL', 0x165A7, 0, [], ((b'CELL', 0), (struct.pack('<i', 7), 2), (struct.pack('<i', 1), 3)))
        actor = Record(b'ACHR', 0x01000806, 0x400, [(b'NAME', uint(0x01000800))])
        write_follower(output / 'mod' / settings.plugin_name, items, author='test', placement=(cell, actor),
                       extra_masters=extras)
        return output, follower_records(output / 'mod' / settings.plugin_name)

    def test_written_esp_resolves_selected_shouts_and_rejects_bad_references(self):
        with tempfile.TemporaryDirectory() as directory:
            data = fake_data(directory)
            settings = FollowerSettings(mod_id='Probe', spells=['Firebolt'], shouts=[SOUL_TEAR, FORCE, CYCLONE])
            refs = official_references(data, settings)
            firebolt = 0x12FCD
            good = [firebolt, *refs['shouts']]
            output, generated = self.write(directory, data, settings, good, refs['masters'])
            disk = list(records(output / 'mod' / settings.plugin_name))
            self.assertEqual(shouts.master_names(disk[0]), ['Skyrim.esm', 'Update.esm', 'Dawnguard.esm', 'Dragonborn.esm'])
            npc = next(r for r in disk if r.kind == b'NPC_')
            # On disk: Dawnguard.esm is master 2 and Dragonborn.esm master 3; Skyrim.esm stays 0.
            self.assertEqual(npc.values(b'SPLO'), [uint(firebolt), uint(2 << 24 | 0x007CB6), uint(0x013E07), uint(3 << 24 | 0x0200C0)])
            self.assertEqual(npc.values(b'SPCT'), [uint(4)])
            self.assertEqual(next(r for r in generated if r.kind == b'NPC_').values(b'SPLO'), [uint(v) for v in good])
            validate_generated(generated, settings, output)
            cases = (
                ([firebolt, 2 << 24 | 0x007CB6, 0x013E07, 4 << 24 | 0x0200C0], refs['masters'], None, 'Update.esm'),  # wrong index
                ([firebolt, refs['shouts'][0], 0x013E07, 9 << 24 | 0x0200C0], refs['masters'], None, 'has no master'),
                ([firebolt, refs['shouts'][0], 0x013E07, 4 << 24 | SPELL], refs['masters'], None, 'not a SHOU'),
                ([firebolt, refs['shouts'][0], 0x07097F, refs['shouts'][2]], refs['masters'], None, 'differs from settings'),
                ([firebolt, refs['shouts'][0], 0x013E07, 0x05FC77], refs['masters'], None, 'differs from settings'),
                (good, refs['masters'], 3, 'SPCT'),
                (good[:-1], refs['masters'], None, 'SPLO has 3'),
                (good, ['Update.esm', 'Dawnguard.esm', 'Dragonborn.esm', 'HearthFires.esm'], None, 'masters'),
                ([0x02000ABC, *refs['shouts']], refs['masters'], None, 'spells must reference Skyrim.esm'),
            )
            for index, (splo, extras, spct, message) in enumerate(cases):
                with self.subTest(case=index), tempfile.TemporaryDirectory(dir=directory) as case:
                    output, generated = self.write(case, data, settings, splo, extras, spct)
                    with self.assertRaisesRegex(ValueError, message):
                        validate_generated(generated, settings, output)

    def test_fitting_footsteps_and_shout_share_the_checked_master_order(self):
        with tempfile.TemporaryDirectory() as directory:
            data = fake_data(directory)
            settings = fitted_settings(mod_id='Probe', fit_armors=['Dragonborn.esm:000AAA'], shouts=[SOUL_TEAR])
            fitting = profile(settings.plugin_name)
            refs = official_references(data, settings, fitting)
            output, generated = self.write(directory, data, settings, refs['shouts'], refs['masters'], fitting=fitting,
                                           sndd=refs['sounds'][0x1000])
            validate_generated(generated, settings, output)
            # Footstep-only masters are no longer enough once the Dawnguard shout is selected.
            with tempfile.TemporaryDirectory(dir=directory) as case:
                output, generated = self.write(case, data, settings, refs['shouts'], ['Update.esm', 'Dragonborn.esm'],
                                               fitting=fitting, sndd=refs['sounds'][0x1000])
                with self.assertRaisesRegex(ValueError, 'masters'):
                    validate_generated(generated, settings, output)

    def test_fitted_footsteps_are_read_back_through_the_written_masters(self):
        with tempfile.TemporaryDirectory() as directory:
            data = fake_data(directory)
            settings = fitted_settings(mod_id='Probe', fit_armors=['Dragonborn.esm:000AAA'], shouts=[SOUL_TEAR])
            fitting = profile(settings.plugin_name)
            refs = official_references(data, settings, fitting)
            # Internal numbering: Update 2, Dawnguard 3, Dragonborn 4; on disk Dragonborn is master 3.
            self.assertEqual(refs['sounds'], {0x1000: 4 << 24 | SOUND})
            output, generated = self.write(directory, data, settings, refs['shouts'], refs['masters'],
                                           fitting=fitting, sndd=refs['sounds'][0x1000])
            arma = next(r for r in records(output / 'mod' / settings.plugin_name) if r.kind == b'ARMA')
            self.assertEqual(arma.values(b'SNDD'), [uint(3 << 24 | SOUND)])
            # The readback never uses official_references' sound numbering.
            real = official_references
            with patch('shouts.official_references', lambda *a, **k: {**real(*a, **k), 'sounds': {0x1000: 0}}):
                validate_generated(generated, settings, output)
            cases = (
                (dict(sndd=0), r"footsteps \[\] differ from the source addon \[\('dragonborn.esm', 4660\)\]"),
                (dict(sndd=None), 'differ from the source addon'),
                (dict(sndd=3 << 24 | SOUND), r"\('dawnguard.esm', 4660\)"),  # Dawnguard instead of Dragonborn
                (dict(sndd=4 << 24 | SOUND + 1), 'differ from the source addon'),
                (dict(sndd=9 << 24 | SOUND), 'has no master'),
                (dict(addons={}), 'missing from the written plugin'),
                (dict(addons={0x1000: refs['sounds'][0x1000], 0x1001: refs['sounds'][0x1000]}), 'Addon 001001'),
            )
            for index, (values, message) in enumerate(cases):
                with self.subTest(case=index), tempfile.TemporaryDirectory(dir=directory) as case:
                    output, generated = self.write(case, data, settings, refs['shouts'], refs['masters'],
                                                   fitting=fitting, **values)
                    with self.assertRaisesRegex(ValueError, message):
                        validate_generated(generated, settings, output)

    def test_game_data_from_the_caller_or_npc_json(self):
        with tempfile.TemporaryDirectory() as directory:
            data = fake_data(directory)
            settings = fitted_settings(mod_id='Probe', fit_armors=['Dragonborn.esm:000AAA'], shouts=[CYCLONE])
            fitting = profile(settings.plugin_name)
            refs = official_references(data, settings, fitting)
            moved = str(Path(directory) / 'moved' / 'Data')
            for index, npc in enumerate(({'plugin': 'Probe.esp'}, False, {'game_data': moved})):
                with self.subTest(npc=npc), tempfile.TemporaryDirectory(dir=directory) as case:
                    output, generated = self.write(case, data, settings, refs['shouts'], refs['masters'],
                                                   fitting=fitting, sndd=refs['sounds'][0x1000], npc=npc)
                    message = 'Skyrim.esm がありません' if index == 2 else r'npc\.json に game_data の記録が無い.*--game-data'
                    with self.assertRaisesRegex(ValueError, message):
                        validate_generated(generated, settings, output)
                    validate_generated(generated, settings, output, data)  # the caller's folder wins
            with tempfile.TemporaryDirectory(dir=directory) as case:
                output, generated = self.write(case, data, settings, refs['shouts'], refs['masters'],
                                               fitting=fitting, sndd=refs['sounds'][0x1000])
                with self.assertRaisesRegex(ValueError, 'Skyrim.esm がありません'):
                    validate_generated(generated, settings, output, moved)

    def test_no_shouts_without_fitting_keeps_skyrim_only(self):
        with tempfile.TemporaryDirectory() as directory:
            data = fake_data(directory)
            settings = FollowerSettings(mod_id='Probe')
            output, generated = self.write(directory, data, settings, [], [])
            validate_generated(generated, settings, output)
            output, generated = self.write(Path(directory) / 'second', data, settings, [], ['Dragonborn.esm'])
            with self.assertRaisesRegex(ValueError, 'only Skyrim.esm'):
                validate_generated(generated, settings, output)


class ReadmeTests(unittest.TestCase):
    def readme(self, directory, masters, **values):
        import zipfile
        from converter import package
        from plugin import write_plugin
        settings = FollowerSettings(mod_id='Readme', sitting_enabled=False, toon_enabled=False, **values)
        output = Path(directory) / '-'.join(masters)
        write_plugin(output / 'mod' / settings.plugin_name, [], masters=masters)
        with zipfile.ZipFile(package(output, settings)) as archive:
            return archive.read(settings.asset_dir + '/README.txt').decode('utf8').replace('\r\n', '\n')

    def test_required_dlc_replaces_the_no_prerequisite_sentence(self):
        with tempfile.TemporaryDirectory() as directory:
            plain = self.readme(directory, ('Skyrim.esm',))
            self.assertIn('No additional prerequisite MOD is required.', plain)
            self.assertNotIn('Requires the official DLC', plain)
            text = self.readme(directory, ('Skyrim.esm', 'Update.esm', 'Dragonborn.esm'), shouts=[CYCLONE, FORCE])
            self.assertNotIn('No additional prerequisite MOD is required.', text)
            self.assertIn('Requires the official DLC/Creations: Dragonborn (Dragonborn.esm). Readme.esp does not load '
                          'without them. No other prerequisite MOD is required.', text)
            self.assertIn('Shouts: DLC2CycloneShout (Dragonborn.esm:0200C0), UnrelentingForceShout (Skyrim.esm:013E07)', text)
            self.assertNotIn('has not been verified in game', text)
            skse = self.readme(Path(directory) / 'skse', ('Skyrim.esm', 'Update.esm', 'Dawnguard.esm'),
                               shouts=[SOUL_TEAR], physics_enabled=True)
            self.assertIn('launch through skse64_loader.exe.\nRequires the official DLC/Creations: Dawnguard (Dawnguard.esm).', skse)


@unittest.skipUnless(find_game(), 'Local Skyrim.esm required')
class GameShoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = find_game() / 'Data'
        cls.catalog = GameCatalog(cls.data)
        cls.official = OfficialCatalog(cls.data)
        (ROOT / 'build/test-tmp').mkdir(parents=True, exist_ok=True)

    def test_all_27_allowlisted_shouts_resolve_with_names(self):
        rows = shouts.choices(self.official)
        self.assertEqual(len(rows), sum(p in self.official.plugins for p, _, _ in SHOUTS))
        for plugin, editor_id, local in SHOUTS:
            with self.subTest(shout=editor_id):
                self.assertIn(plugin, self.official.plugins, 'Installed game data lacks this DLC')
                record = shouts.require(self.official, (plugin, editor_id, local))
                self.assertEqual((record.kind, self.official.key(record)), (b'SHOU', shouts.key(plugin, local)))
                row = next(r for r in rows if r['id'] == shouts.key(plugin, local))
                self.assertTrue(row['labels']['ja'] and row['descriptions']['ja'])
        cyclone = next(r for r in rows if r['id'] == CYCLONE)
        self.assertEqual((cyclone['editor_id'], cyclone['dlc'], cyclone['labels']['en']),
                         ('DLC2CycloneShout', 'Dragonborn', 'Cyclone'))

    def build(self, settings, fitting=None):
        from build_npc import build_npc
        from plugin_validation import validate_private_records
        temp = tempfile.TemporaryDirectory(dir=ROOT / 'build/test-tmp')
        self.addCleanup(temp.cleanup)
        output = Path(temp.name)
        if fitting:
            (output / 'armor-fitting.json').write_text(json.dumps(fitting))
        self.catalog.validate_settings(settings)
        path = build_npc(self.data, output, settings, self.catalog)
        generated = follower_records(path)
        validate_private_records(generated, settings, output)
        # An output built before npc.json recorded game_data: the caller's Data folder is used.
        report = json.loads((output / 'npc.json').read_text(encoding='utf8'))
        del report['game_data']
        (output / 'npc.json').write_text(json.dumps(report), encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'game_data'):
            validate_private_records(generated, settings, output)
        validate_private_records(generated, settings, output, self.data)
        disk = list(records(path))
        return shouts.master_names(disk[0]), next(r for r in disk if r.kind == b'NPC_'), disk

    def resolve(self, masters, value):
        """Owner file and record of an on-disk follower reference, read from that master file."""
        owner = masters[value >> 24]
        loaded = list(records(self.data / owner, {b'TES4', b'SHOU'}))
        own = len(shouts.master_names(loaded[0]))
        return owner, next((r for r in loaded if r.form_id == own << 24 | value & 0xFFFFFF), None)

    def test_cyclone_unrelenting_force_and_spell(self):
        settings = FollowerSettings(mod_id='ShoutProbe', sitting_enabled=False, spells=['Firebolt'],
                                    shouts=[CYCLONE, FORCE])
        masters, npc, _ = self.build(settings)
        self.assertEqual(masters, ['Skyrim.esm', 'Update.esm', 'Dragonborn.esm'])
        values = [struct.unpack('<I', v)[0] for v in npc.values(b'SPLO')]
        self.assertEqual(npc.values(b'SPCT'), [uint(3)])
        self.assertEqual(values[0], self.catalog.require('Firebolt', b'SPEL').form_id)
        self.assertEqual([self.resolve(masters, v)[1].editor_id for v in values[1:]],
                         ['DLC2CycloneShout', 'UnrelentingForceShout'])

    def test_shouts_only_keeps_skyrim_master_and_writes_spct(self):
        masters, npc, _ = self.build(FollowerSettings(mod_id='ShoutOnly', sitting_enabled=False, shouts=[FORCE]))
        self.assertEqual(masters, ['Skyrim.esm'])
        self.assertEqual((npc.values(b'SPCT'), npc.values(b'SPLO')), ([uint(1)], [uint(0x013E07)]))

    def test_dragonborn_footsteps_with_dawnguard_shout(self):
        armor = self.official.require('DLC2ClothesSkaalBoots', b'ARMO')
        source = next(a for a in self.official.addon_records(armor, 'female') if a.values(b'SNDD'))
        sound = struct.unpack('<I', source.values(b'SNDD')[0])[0]
        sound_owner = self.official.plugins[sound >> 24], sound & 0xFFFFFF
        owner, local = self.official.identity(armor)
        settings = fitted_settings(mod_id='ShoutFitted', fit_armors=[self.official.key(armor)], shouts=[SOUL_TEAR])
        fitting = {'plugin': settings.plugin_name, 'wardrobe_policy': 'native_slots', 'equipment': [dict(
            editor_id=armor.editor_id, original_form_id=armor.form_id, origin_plugin=owner, origin_local_id=local,
            addon_local_id=0x1000, source_addon_key=self.official.key(source), slots=[37], priority=0,
            file='fitted_test_1.nif')]}
        masters, npc, disk = self.build(settings, fitting)
        self.assertEqual(masters, ['Skyrim.esm', 'Update.esm', 'Dawnguard.esm', 'Dragonborn.esm'])
        shout = struct.unpack('<I', npc.values(b'SPLO')[0])[0]
        self.assertEqual(self.resolve(masters, shout)[1].editor_id, 'DLC1SoulTearShout')
        addon = next(r for r in disk if r.kind == b'ARMA' and r.form_id & 0xFFFFFF == 0x1000)
        value = struct.unpack('<I', addon.values(b'SNDD')[0])[0]
        # The written footstep reference still names the source addon's sound record.
        self.assertEqual((masters[value >> 24], value & 0xFFFFFF), sound_owner)


if __name__ == '__main__':
    unittest.main()
