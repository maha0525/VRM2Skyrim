"""Shipped PEX and actual generated ARMO masks; no scripted trade replacement."""
from pathlib import Path
import struct
import unittest

from build_npc import appearance_records
from equipment_runtime import rename_pex, PROPERTIES, pex_strings, runtime_records
from plugin import Record
from tests.pex_vm import PexVM, Actor
from tests.test_wardrobe import wardrobe_settings

TEMPLATE = (Path(__file__).resolve().parents[1]/'runtime/V2SInitialWardrobe.pex').read_bytes()


class Catalog:
    def require(self, name, kind):
        return Record(kind, 0x1234, 0, [(b'ETYP', struct.pack('<I', 0x13F42))] if kind == b'ARMO' else [])


class EquipmentRuntimeTests(unittest.TestCase):
    def fixture(self, teammate=False):
        settings = wardrobe_settings()
        coat = settings.appearance_parts['garments'][0]
        coat.update(slot=32)
        settings.appearance_parts['garments'].append({**coat, 'id': 'shoes', 'name': 'Shoes', 'nodes': [5], 'slot': 37})
        generated, _ = appearance_records(settings, Catalog())
        clothing = [r for r in generated if r.kind == b'ARMO' and 'Garment_' in r.editor_id]
        masks = {r.form_id: struct.unpack_from('<I', r.values(b'BOD2')[0])[0] for r in clothing}
        # Unknown/new armor need no converter FormList membership.
        masks.update({201: 1 << 2, 202: 1 << 7, 301: 1 << 5})
        actor = Actor({n: 1 for n in masks}, teammate, masks)
        binding = {name: tuple(struct.unpack('<I', value)[0] for value in r.values(b'LNAM'))
                   for name, r in zip(PROPERTIES, runtime_records(settings))}
        vm = PexVM(rename_pex(TEMPLATE, 'V2S_TestWardrobe'), actor, binding)
        return actor, vm, [r.form_id for r in clothing]

    def test_trade_exclusion_precedes_deferred_papyrus_events(self):
        actor, vm, (coat, shoes) = self.fixture()
        vm.run('OnInit')
        actor.drain_events(vm)
        inventory = actor.inventory.copy()
        actor.call('equipitem', [301, 0, 1])
        for _ in range(4):
            # Keep equip events queued as during a menu/VM delay.
            actor.call('equipitem', [201, 0, 1])
            self.assertEqual(actor.worn, {201, shoes, 301})
            actor.call('equipitem', [202, 0, 1])
            self.assertEqual(actor.worn, {201, 202, 301})
            actor.call('equipitem', [301, 0, 1])
            actor.drain_events(vm)
            self.assertEqual(actor.worn, {201, 202, 301})
            actor.call('equipitem', [coat, 0, 1])
            self.assertEqual(actor.worn, {coat, 202, 301})
            actor.call('equipitem', [shoes, 0, 1])
            self.assertEqual(actor.worn, {coat, shoes, 301})
            actor.drain_events(vm)
        self.assertEqual(actor.inventory, inventory)

    def test_aft_reload_and_delayed_events_never_change_equipment(self):
        actor, vm, (coat, shoes) = self.fixture(teammate=True)
        actor.worn = {201, 202, 301}
        vm.run('OnInit')
        self.assertEqual(actor.worn, {201, 202, 301})
        for event, args in [('OnLoad', ()), ('OnObjectEquipped', (coat, None)),
                            ('UnequipConflicts', ((201, 202),)), ('ResolveCurrentEquipment', ())]:
            vm.run(event, *args)
            self.assertEqual(actor.worn, {201, 202, 301})
        actor.worn.clear()
        vm.run('OnLoad')
        vm.run('OnInit')
        self.assertEqual(actor.worn, set())
        self.assertNotIn(shoes, actor.worn)

    def test_private_pex_contains_no_unequip_or_replacement_calls(self):
        _, _, _, strings = pex_strings(TEMPLATE)
        names = {s.lower() for s in strings}
        for forbidden in (b'unequipitem', b'setoutfit', b'hasform', b'getwornform', b'isequipped', b'queueninodeupdate'):
            self.assertNotIn(forbidden, names)
        _, vm, _ = self.fixture()
        self.assertEqual(set(vm.properties), set(PROPERTIES))
        for prop in PROPERTIES[1:]:
            self.assertEqual(vm.variables[vm.properties[prop]], ())
        renamed = rename_pex(TEMPLATE, 'V2S_TwoWardrobe')
        self.assertNotEqual(renamed, TEMPLATE)
        metadata, _, _, strings = pex_strings(renamed)
        self.assertEqual(metadata, [b'V2S_TwoWardrobe.psc', b'VRM2Skyrim', b'VRM2Skyrim'])
        self.assertIn(b'V2S_TwoWardrobe', strings)
        with self.assertRaises(ValueError):
            rename_pex(b'not a PEX', 'V2S_Invalid')
