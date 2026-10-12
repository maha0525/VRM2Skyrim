"""Execute shipped Skyrim PEX bytes, not a reimplementation of switch policy."""
from pathlib import Path
import unittest

from equipment_runtime import rename_pex, PROPERTIES, pex_strings
from tests.pex_vm import PexVM, Actor

TEMPLATE = (Path(__file__).resolve().parents[1]/'runtime/V2SInitialWardrobe.pex').read_bytes()


class EquipmentRuntimeTests(unittest.TestCase):
    def fixture(self, teammate=False):
        binding = dict(zip(PROPERTIES, ((101, 102, 103), (101, 102), (), (103,), (201,), (), (202,))))
        actor = Actor({n: 1 for n in (101, 102, 103, 201, 202, 301)}, teammate)
        vm = PexVM(rename_pex(TEMPLATE, 'V2S_TestWardrobe'), actor, binding)
        self.assertEqual(vm.name, 'V2S_TestWardrobe')
        self.assertEqual(vm.parent.lower(), 'actor')
        self.assertEqual(set(vm.properties), set(PROPERTIES))
        return actor, vm

    def test_armor_has_priority_over_repeated_clothing_equips(self):
        actor, vm = self.fixture()
        inventory = actor.inventory.copy()
        vm.run('OnInit')
        actor.drain_events(vm)
        self.assertEqual(actor.worn, {101, 102, 103})
        actor.call('equipitem', [201, 0, 1])
        actor.drain_events(vm)
        self.assertEqual(actor.worn, {201, 103})
        actor.call('equipitem', [202, 0, 1])
        actor.drain_events(vm)
        self.assertEqual(actor.worn, {201, 202})
        actor.call('equipitem', [101, 0, 1])
        actor.drain_events(vm)
        self.assertEqual(actor.worn, {201, 202})
        # NPC/AFT re-equipping a later garment must not strip the cuirass.
        for _ in range(3):
            actor.call('equipitem', [102, 0, 1])
            actor.drain_events(vm)
            self.assertEqual(actor.worn, {201, 202})
        actor.call('equipitem', [103, 0, 1])
        actor.drain_events(vm)
        self.assertEqual(actor.worn, {201, 202})
        actor.call('unequipitem', [201, 0, 1])
        actor.call('equipitem', [101, 0, 1])
        actor.drain_events(vm)
        self.assertEqual(actor.worn, {101, 202})
        actor.call('unequipitem', [202, 0, 1])
        actor.call('equipitem', [103, 0, 1])
        actor.drain_events(vm)
        self.assertEqual(actor.worn, {101, 103})
        self.assertEqual(actor.inventory, inventory)
        self.assertTrue(actor.logs)

    def test_aft_clear_reload_and_delayed_events_do_not_restore_or_strip_gear(self):
        actor, vm = self.fixture(teammate=True)
        actor.worn = {101, 102, 103, 201, 202, 301}
        vm.run('OnInit')
        self.assertEqual(actor.worn, {201, 202, 301})
        actor.worn.clear()
        vm.run('OnLoad')
        vm.run('OnInit')
        self.assertEqual(actor.worn, set())
        actor.call('equipitem', [201, 0, 1])
        actor.call('equipitem', [101, 0, 1])
        actor.drain_events(vm)
        self.assertEqual(actor.worn, {201})
        # A queued event for removed clothes must not undress the current armor.
        actor.worn = {201, 202, 301}
        vm.run('OnObjectEquipped', 101, None)
        self.assertEqual(actor.worn, {201, 202, 301})
        vm.run('OnLoad')
        self.assertEqual(actor.worn, {201, 202, 301})

    def test_private_pex_identity_and_metadata(self):
        a, b = (rename_pex(TEMPLATE, n) for n in ('V2S_OneWardrobe', 'V2S_TwoWardrobe'))
        self.assertNotEqual(a, b)
        metadata, _, _, strings = pex_strings(a)
        self.assertEqual(metadata, [b'V2S_OneWardrobe.psc', b'VRM2Skyrim', b'VRM2Skyrim'])
        self.assertIn(b'V2S_OneWardrobe', strings)
        with self.assertRaises(ValueError):
            rename_pex(b'not a PEX', 'V2S_Invalid')

    def test_all_equipment_lists_check_worn_slots(self):
        actor = Actor({n: 1 for n in (101, 102, 103, 201, 202, 203, 301)}, teammate=True)
        binding = dict(zip(PROPERTIES, ((101, 102, 103), (101,), (102,), (103,), (), (), ())))
        for prop, mask, gear in (('BodyEquipment', 4, 201), ('HandsEquipment', 8, 202), ('FeetEquipment', 128, 203)):
            binding[prop] = tuple(range(1000, 4000))+(gear,)
            actor.worn_slots[mask] = gear
        vm = PexVM(TEMPLATE, actor, binding)
        actor.worn = {101, 102, 103, 201, 202, 203, 301}
        vm.run('OnLoad')
        self.assertEqual(actor.worn, {201, 202, 203, 301})

    def test_one_item_replacing_several_body_groups(self):
        actor = Actor({n: 1 for n in (101, 102, 103, 900)})
        binding = dict(zip(PROPERTIES, ((101, 102, 103), (101,), (102,), (103,), (900,), (900,), (900,))))
        vm = PexVM(TEMPLATE, actor, binding)
        actor.worn = {101, 102, 103, 900}
        vm.run('OnObjectEquipped', 900, None)
        self.assertEqual(actor.worn, {900})

    def test_all_groups_ignore_equip_order_and_leave_accessories_alone(self):
        binding = dict(zip(PROPERTIES, ((101,102,103,301), (101,), (102,), (103,), (201,), (202,), (203,))))
        for clothing_first in (True,False):
            actor = Actor({n:1 for n in (101,102,103,201,202,203,301)})
            vm = PexVM(TEMPLATE,actor,binding)
            actor.call('equipitem',[301,0,1])
            for clothes,gear in ((101,201),(102,202),(103,203)):
                for item in ((clothes,gear) if clothing_first else (gear,clothes)):
                    actor.call('equipitem',[item,0,1])
                    actor.drain_events(vm)
            self.assertEqual(actor.worn,{201,202,203,301})
