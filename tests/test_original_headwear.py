from dataclasses import asdict
from pathlib import Path
import struct
import tempfile
import unittest

from build_npc import build_npc, NPC_ID
from environment import find_game
from equipment_runtime import rename_pex
from gear_head_runtime import IDS
from plugin import records
from settings import FollowerSettings
from tests.pex_vm import Actor, PexVM
from wardrobe import equip_slots, keyword_names, nif_partition, original_head_visibility, suggest_role

ROOT = Path(__file__).resolve().parents[1]


def hat_settings(**flags):
    hat = {'id': 'hat', 'name': 'Hat', 'nodes': [4], 'slot': 30, 'slot_mode': 'auto',
           'record_index': 2, 'item_kind': 'head', 'armor_type': 'clothing', 'armor_rating': 0,
           'weight': .1, 'value': 10, 'equipped': True, **flags}
    return FollowerSettings(mod_id='HeadwearTest', armor_support=True, sitting_enabled=False,
                            appearance_source_sha256='a' * 64,
                            appearance_parts={'body': [0], 'underwear': [], 'fixed': [1, 2, 3],
                                              'garments': [hat]},
                            appearance_heads={'face': [1], 'hair': [2]})


class OriginalHeadwearTests(unittest.TestCase):
    def test_headwear_without_hiding_needs_no_visibility_runtime(self):
        settings = hat_settings()
        self.assertFalse(settings.head_switch_enabled)
        self.assertFalse(settings.fitting_enabled)
        hat = settings.appearance_parts['garments'][0]
        self.assertEqual(equip_slots(hat), [30])
        self.assertEqual(nif_partition(30), 130)
        self.assertEqual(nif_partition(31), 131)
        self.assertEqual(nif_partition(42), 142)
        self.assertEqual(keyword_names(hat), ['ArmorClothing', 'VendorItemClothing', 'ClothingHead'])
        self.assertIn('ArmorHelmet', keyword_names({**hat, 'armor_type': 'heavy'}))
        self.assertEqual(suggest_role('Witch_Hat', ['Hat']), 'garment')
        self.assertEqual(suggest_role('Head_Helmet', []), 'garment')

    def test_optional_visibility_requires_independent_meshes_and_headwear(self):
        for part in ('face', 'hair'):
            with self.subTest(part=part):
                settings = hat_settings(**{'hide_' + part: True})
                self.assertTrue(settings.head_switch_enabled)
                values = asdict(settings)
                values['appearance_heads'][part] = []
                with self.assertRaisesRegex(ValueError, '別メッシュ'):
                    FollowerSettings.from_dict(values)
        values = asdict(hat_settings(hide_hair=True))
        values['appearance_parts']['garments'][0].update(slot=32, item_kind='body')
        with self.assertRaisesRegex(ValueError, '頭装備'):
            FollowerSettings.from_dict(values)

    def test_original_hat_skin_switch_restores_hair_without_inventory_mutations(self):
        hat = 0x01000815
        actor = Actor({hat: 1})
        actor.worn_slots = {1: hat}
        actor.skin = 501
        data = rename_pex((ROOT/'runtime/V2SHeadVisibility.pex').read_bytes(),
                          'V2S_HeadwearTestVisibility', 'V2SHeadVisibility')
        bindings = {'FullSkin': 501, 'FaceHiddenSkin': 502, 'HairHiddenSkin': 503,
                    'BothHiddenSkin': 504, 'FaceHidingEquipment': (), 'HairHidingEquipment': (hat,)}
        vm = PexVM(data, actor, bindings)
        vm.run('OnInit')
        self.assertEqual(actor.skin, 501)
        actor.worn.add(hat)
        vm.run('OnObjectEquipped', hat, None)
        self.assertEqual(actor.skin, 503)
        vm.run('OnNiNodeUpdate', actor)
        self.assertEqual(actor.refreshes, 1)
        actor.worn.remove(hat)
        vm.run('OnObjectUnequipped', hat, None)
        self.assertEqual(actor.skin, 501)
        self.assertEqual(actor.inventory, {hat: 1})
        self.assertEqual(actor.events, [])
        self.assertEqual(original_head_visibility([]), {'hide_face': False, 'hide_hair': False})

    @unittest.skipUnless(find_game(), 'Local Skyrim.esm required')
    def test_actual_plugin_head_slots_keywords_and_private_visibility_lists_without_fitting(self):
        for flags in ({}, {'hide_hair': True}, {'hide_face': True, 'hide_hair': True}):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as folder:
                settings = hat_settings(**flags)
                path = build_npc(find_game()/'Data', Path(folder), settings)
                by_id = {r.form_id: r for r in records(path)}
                hat = by_id[0x01000815]
                addon = by_id[0x01000814]
                self.assertEqual(struct.unpack('<II', hat.values(b'BOD2')[0]), (1, 2))
                self.assertEqual(struct.unpack('<II', addon.values(b'BOD2')[0]), (1, 2))
                self.assertIn(struct.pack('<Ii', hat.form_id, 1), by_id[NPC_ID].values(b'CNTO'))
                vanilla = {r.editor_id: r for r in records(find_game()/'Data/Skyrim.esm', {b'KYWD', b'ARMO'})}
                self.assertIn(struct.pack('<I', vanilla['ClothingHead'].form_id), hat.values(b'KWDA')[0])
                self.assertEqual(hat.values(b'MOD2'), vanilla['ClothesFarmHat01'].values(b'MOD2'))
                if flags:
                    for name, flag in (('FaceHidingEquipment', 'hide_face'), ('HairHidingEquipment', 'hide_hair')):
                        self.assertEqual(by_id[IDS[name]].values(b'LNAM'),
                                         [struct.pack('<I', hat.form_id)] if flags.get(flag) else [])
                    self.assertIn((settings.prefix+'HeadVisibility').encode(), by_id[NPC_ID].values(b'VMAD')[0])
                    self.assertTrue((Path(folder)/'mod/scripts'/(settings.prefix+'HeadVisibility.pex')).exists())
                else:
                    self.assertNotIn(IDS['HairHidingEquipment'], by_id)


if __name__ == '__main__':
    unittest.main()
