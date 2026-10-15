"""CSTY field semantics, serialization and private follower linkage."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest

from combat_style import CUSTOM_STYLE_ID, FIELDS, private_style, read_style, validate_custom
from build_npc import build_npc, NPC_ID
from environment import find_game
from game_catalog import GameCatalog
from plugin import Record, records
from settings import FollowerSettings

ROOT = Path(__file__).resolve().parents[1]


class Catalog:
    def __init__(self, record):
        self.record = record

    def require(self, key, kind):
        assert key == self.record.editor_id and kind == self.record.kind
        return self.record


class CombatStyleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT/'build/test-tmp').mkdir(parents=True, exist_ok=True)

    def test_clone_preserves_omitted_tails_unknowns_and_unedited_source(self):
        source = Record(b'CSTY', 12, 0x80000, [(b'EDID', b'Base\0'),
                        (b'CSGD', struct.pack('<10f', .1, .2, .3, 3, 4, 5, 6, 7, 8, .9)),
                        (b'CSME', struct.pack('<7f', *range(7))),
                        (b'CSFL', struct.pack('<7f', *[.5]*7)),
                        (b'DATA', struct.pack('<I', 0x80 | 1)), (b'ZZZZ', b'keep')])
        original = copy.deepcopy(source)
        config = read_style(source)
        self.assertEqual(config['values']['staff_score'], 8)
        self.assertNotIn('special_attack', config['values'])
        self.assertNotIn('flying_attack', config['values'])
        self.assertEqual(config['flags'], 5)
        config['values']['magic_score'] = 7.25
        config['values']['strafe'] = .75  # Inserts an absent known block before DATA.
        config['flags'] = 2
        settings = FollowerSettings(combat_style_mode='custom', combat_style_custom=config)
        result = private_style(settings, Catalog(source))
        self.assertEqual(source, original)
        self.assertEqual(result.form_id, CUSTOM_STYLE_ID)
        self.assertNotEqual(result.editor_id, source.editor_id)
        self.assertEqual(result.values(b'CSME'), source.values(b'CSME'))
        self.assertEqual(result.values(b'CSFL'), source.values(b'CSFL'))
        self.assertEqual(result.values(b'ZZZZ'), [b'keep'])
        self.assertEqual(struct.unpack('<I', result.values(b'DATA')[0])[0], 0x82)
        self.assertFalse(result.flags & 0x80000)
        self.assertEqual(read_style(result)['values']['magic_score'], 7.25)
        tags = [tag for tag, _ in result.fields]
        self.assertLess(tags.index(b'CSLR'), tags.index(b'DATA'))
        config['values']['special_attack'] = .2
        extended = private_style(settings, Catalog(source))
        self.assertEqual(len(extended.values(b'CSME')[0]), 32)
        self.assertEqual(extended.values(b'CSME')[0][:28], source.values(b'CSME')[0])

    def test_settings_roundtrip_legacy_and_invalid_inputs(self):
        self.assertEqual(FollowerSettings.from_dict({}).combat_style_mode, 'existing')
        config = {'source': 'csHumanMagic', 'values': {'magic_score': 4.05}, 'flags': 5}
        settings = FollowerSettings(combat_style_mode='custom', combat_style_custom=config)
        with tempfile.TemporaryDirectory(dir=ROOT/'build/test-tmp') as directory:
            path = Path(directory)/'settings.json'
            settings.save(path)
            self.assertEqual(FollowerSettings.load(path), settings)
        for change in ({'flags': True}, {'flags': 8}, {'values': {'typo': 1}},
                       {'values': {'magic_score': float('nan')}}, {'values': {'circle': 1.1}},
                       {'values': {'magic_score': float('inf')}}, {'values': {'magic_score': 10**1000}},
                       {'values': {'magic_score': True}},
                       {'values': {'magic_score': -1}}, {'source': ''}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_custom({**config, **change})
        with self.assertRaises(ValueError):
            FollowerSettings(combat_style_mode='custom')
        self.assertEqual(len(FIELDS), 31)


@unittest.skipUnless(find_game(), 'Local Skyrim.esm required')
class CombatStyleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT/'build/test-tmp').mkdir(parents=True, exist_ok=True)
        cls.data = find_game()/'Data'
        cls.catalog = GameCatalog(cls.data)

    def test_real_ck_values_dual_wield_and_every_style_snapshot(self):
        magic = read_style(self.catalog.require('csHumanMagic', b'CSTY'))
        self.assertAlmostEqual(magic['values']['magic_score'], 4.05, places=5)
        self.assertFalse(magic['flags'] & 4)
        for name in ('csAlikrBerserker', 'csMercerFreyMelee', 'csForswornBerserker'):
            self.assertTrue(read_style(self.catalog.require(name, b'CSTY'))['flags'] & 4)
        for source in self.catalog.choices(b'CSTY'):
            config = read_style(source)
            if config:
                with self.subTest(source=source.editor_id):
                    validate_custom(config)
                    result = private_style(FollowerSettings(combat_style_custom=config), self.catalog)
                    self.assertEqual(read_style(result)['values'], config['values'])
                    for tag in (b'CSGD', b'CSME', b'CSCR', b'CSLR', b'CSFL'):
                        self.assertEqual(result.values(tag), source.values(tag))

    def test_private_esp_links_only_its_npc_and_existing_path_stays_shared(self):
        config = read_style(self.catalog.require('csHumanMagic', b'CSTY'))
        config['flags'] |= 4
        config['values']['magic_score'] = 5.5
        for mode in ('existing', 'custom'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(dir=ROOT/'build/test-tmp') as directory:
                settings = FollowerSettings(combat_style_mode=mode, combat_style_custom=config)
                path = build_npc(self.data, directory, settings, self.catalog)
                parsed = list(records(path))
                styles = [r for r in parsed if r.kind == b'CSTY']
                npc = next(r for r in parsed if r.form_id == NPC_ID)
                self.assertEqual(len({r.form_id for r in parsed}), len(parsed))
                if mode == 'custom':
                    self.assertEqual(len(styles), 1)
                    self.assertEqual(struct.unpack('<I', npc.values(b'ZNAM')[0])[0], CUSTOM_STYLE_ID)
                    self.assertEqual(read_style(styles[0])['values']['magic_score'], 5.5)
                    self.assertTrue(read_style(styles[0])['flags'] & 4)
                else:
                    self.assertEqual(styles, [])
                    self.assertEqual(struct.unpack('<I', npc.values(b'ZNAM')[0])[0],
                                     self.catalog.require(settings.combat_style, b'CSTY').form_id)
