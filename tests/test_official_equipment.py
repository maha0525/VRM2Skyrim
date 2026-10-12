"""Master identities, all-category selection and shipped head-visibility PEX."""
from pathlib import Path
import struct
import tempfile
import unittest
import json
from types import SimpleNamespace
from unittest.mock import patch

from armor_catalog import official_choices, head_policy
from equipment_runtime import rename_pex
from gear_head_runtime import PROPERTIES
from official_catalog import OfficialCatalog, remap_record
from plugin import Record, write_plugin
from settings import FollowerSettings
from tests.pex_vm import Actor, PexVM
from wizard import WizardApplication
from outfit_edits import apply_edit
import outfit_edits

ROOT = Path(__file__).resolve().parents[1]


def uint(n):
    return struct.pack('<I', n)


class CatalogTests(unittest.TestCase):
    def test_failed_finishing_restores_mesh_and_saved_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root/'conversion'
            output.mkdir()
            settings = FollowerSettings(appearance_source_sha256='a'*64)
            settings.save(output/'settings.json')
            key = 'b'*16
            (output/'armor-fitting.json').write_text(json.dumps({'equipment': [{'source_key': key, 'file': 'fitted_test_1.nif'}]}))
            mesh = output/'mod/meshes'/settings.asset_dir/'fitted_test_1.nif'
            mesh.parent.mkdir(parents=True)
            mesh.write_bytes(b'original mesh')
            low = mesh.with_name('fitted_test_0.nif')
            low.write_bytes(b'original low mesh')

            def broken_export(*args, **kwargs):
                mesh.write_bytes(b'failed export')
                low.write_bytes(b'failed low export')
                raise ValueError('export failed')

            with patch.object(outfit_edits, 'ROOT', root):
                override = outfit_edits.override_path('a'*64, key)
                def save_override(*args):
                    override.parent.mkdir(parents=True, exist_ok=True)
                    override.write_bytes(b'new edit')
                with self.assertLogs('outfit_edits', level='ERROR'), \
                     patch.dict('sys.modules', {'armor_validation': SimpleNamespace(validate_fitting=lambda p: None)}), \
                     patch('outfit_edits.import_edit', side_effect=save_override), \
                     patch('converter.run_blender', side_effect=broken_export):
                    with self.assertRaisesRegex(ValueError, 'export failed'):
                        apply_edit(output, key, root/'edited.nif', root/'Blender.exe')
                self.assertEqual(mesh.read_bytes(), b'original mesh')
                self.assertEqual(low.read_bytes(), b'original low mesh')
                self.assertFalse(override.exists())

    def test_completed_edit_result_survives_wizard_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            output = workspace/'Follower'
            output.mkdir()
            (output/'follower.zip').write_bytes(b'local artifact')
            job = dict(id='0123456789abcdef0123456789abcdef', status='complete',
                       output=str(output), archive='follower.zip', plugin_name='Follower.esp', edit_kit='kit.zip')
            app = WizardApplication(workspace)
            app.remember_job(job)
            app.close()
            restored = WizardApplication(workspace)
            try:
                self.assertEqual(restored.snapshot(job['id']), job)
            finally:
                restored.close()
            job['output'] = str(workspace.parent)
            (output/'wizard-job.json').write_text(json.dumps(job))
            rejected = WizardApplication(workspace)
            try:
                self.assertEqual(rejected.jobs, {})
            finally:
                rejected.close()
    def test_shared_model_female_fallback(self):
        addon = Record(b'ARMA', 1, 0, [(b'MOD2', b'shield.nif\0')])
        self.assertEqual(OfficialCatalog.model_tag(addon, 'female'), b'MOD2')
        self.assertEqual(OfficialCatalog.model_tag(addon, 'male'), b'MOD2')
        addon.fields.append((b'MOD3', b'female.nif\0'))
        self.assertEqual(OfficialCatalog.model_tag(addon, 'female'), b'MOD3')
        addon.fields = [(b'MOD3', b'female.nif\0')]
        self.assertIsNone(OfficialCatalog.model_tag(addon, 'male'))

    def test_plugin_relative_ids_and_multimodel_headgear(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            aa = Record(b'ARMA', 0x200, 0, [(b'EDID', b'HumanHelmetAA\0'), (b'RNAM', uint(0x19)),
                 (b'MODL', uint(0x13746)), (b'BOD2', uint(2 | 1 << 12)), (b'MOD3', b'armor/head.nif\0')])
            beast = Record(b'ARMA', 0x201, 0, [(b'EDID', b'BeastHelmetAA\0'), (b'RNAM', uint(0x19)),
                 (b'MODL', uint(0x13740)), (b'BOD2', uint(2 | 1 << 12)), (b'MOD3', b'armor/beast.nif\0')])
            header = Record(b'TES4', 0, 0, [(b'HEDR', struct.pack('<fII', 1.7, 2, 0x800))])
            (root/'Skyrim.esm').write_bytes(header.encode()+aa.encode()+beast.encode())
            (root/'Update.esm').write_bytes(Record(b'TES4', 0, 0, [(b'MAST', b'Skyrim.esm\0')]).encode())
            armor = Record(b'ARMO', 0x02000800, 0, [(b'EDID', b'DLCHead\0'), (b'FULL', b'DLC Head\0'),
                (b'BOD2', uint(2 | 1 << 12)), (b'MODL', uint(0x200)), (b'MODL', uint(0x201)),
                (b'EITM', uint(0x02000900)), (b'KWDA', uint(0x01000801)+uint(0x02000802))])
            write_plugin(root/'Dawnguard.esm', [armor], masters=('Skyrim.esm', 'Update.esm'))
            # ESL disk references use its own master array, not a runtime FE index.
            cc = Record(b'ARMO', 0x02000801, 0, [(b'EDID', b'CCHead\0'), (b'FULL', b'CC Head\0'),
                (b'BOD2', uint(2 | 1 << 12)), (b'MODL', uint(0x200)), (b'EITM', uint(0x01000900))])
            write_plugin(root/'ccTest.esl', [cc], masters=('Skyrim.esm', 'Dawnguard.esm'))
            catalog = OfficialCatalog(root)
            choice = catalog.require('ccTest.esl:000801')
            # A profile's old virtual index can differ after another official plugin is installed.
            item = dict(origin_plugin='ccTest.esl', origin_local_id=0x801, original_form_id=0x09000801)
            self.assertEqual(catalog.fitted_item(item), choice)
            with self.assertRaises(ValueError):
                catalog.fitted_item({**item, 'original_form_id': 0x09000802})
            self.assertEqual(choice.form_id, 0x03000801)
            self.assertEqual(choice.values(b'EITM'), [uint(0x02000900)])
            self.assertEqual(len(official_choices(catalog)), 2)
            self.assertEqual(catalog.addon_records(choice, 'female'), [catalog.require('HumanHelmetAA')])
            remapped = catalog.in_masters(choice, ['Skyrim.esm', 'ccTest.esl', 'Dawnguard.esm', 'Update.esm'])
            self.assertEqual(remapped.form_id, 0x01000801)
            self.assertEqual(remapped.values(b'EITM'), [uint(0x02000900)])

    def test_vmad_object_properties_and_arrays_remap(self):
        def string(value):
            return struct.pack('<H', len(value))+value
        obj = struct.pack('<HhI', 0, -1, 0x02000800)
        vmad = struct.pack('<HHH', 5, 2, 1)+string(b'Script')+struct.pack('<BH', 0, 2)
        vmad += string(b'Object')+bytes((1, 1))+obj
        vmad += string(b'Objects')+bytes((11, 1))+uint(1)+obj
        record = Record(b'ARMO', 0x02000801, 0, [(b'VMAD', vmad)])
        mapped = remap_record(record, lambda n: (n+0x01000000) if n else 0)
        self.assertEqual(mapped.values(b'VMAD')[0].count(uint(0x03000800)), 2)

    def test_policy_defaults_and_independent_overrides(self):
        settings = FollowerSettings()
        helmet = Record(b'ARMA', 1, 0, [(b'BOD2', uint(2 | 1 << 12))])
        circlet = Record(b'ARMA', 2, 0, [(b'BOD2', uint(1 << 12))])
        self.assertEqual(head_policy(settings, helmet, 'Skyrim.esm:000001'), {'hide_face': False, 'hide_hair': True})
        self.assertEqual(head_policy(settings, circlet, 'Skyrim.esm:000002'), {'hide_face': False, 'hide_hair': False})
        settings.head_overrides['Skyrim.esm:000001'] = {'hide_face': True, 'hide_hair': False}
        self.assertEqual(head_policy(settings, helmet, 'Skyrim.esm:000001'), {'hide_face': True, 'hide_hair': False})


class HeadRuntimeTests(unittest.TestCase):
    def test_equip_remove_load_and_external_scene_refresh(self):
        template = (ROOT/'runtime/V2SHeadVisibility.pex').read_bytes()
        actor = Actor({101: 1, 102: 1, 103: 1})
        actor.worn_slots = {1: 101, 2: 102, 4: 103}
        bindings = dict(zip(PROPERTIES, (201, 202, 203, 204, (101, 103), (102, 103))))
        vm = PexVM(rename_pex(template, 'V2S_TestHead', template_name='V2SHeadVisibility'), actor, bindings)
        vm.run('OnInit')
        self.assertEqual(actor.skin, 201)
        for worn, skin in (({101}, 202), ({102}, 203), ({103}, 204), (set(), 201)):
            actor.worn = worn
            vm.run('OnObjectEquipped', 101, None)
            self.assertEqual(actor.skin, skin)
        previous = actor.refreshes
        vm.run('OnNiNodeUpdate', actor)
        self.assertEqual(actor.refreshes, previous)  # no refresh recursion
        actor.skin = 999  # a scene/base reset must restore the desired private skin
        vm.run('OnLoad')
        self.assertEqual(actor.skin, 201)
        self.assertEqual(actor.inventory, {101: 1, 102: 1, 103: 1})
        actor.worn = {102}
        vm.run('OnObjectUnequipped', 103, None)
        self.assertEqual(actor.skin, 203)
        self.assertTrue(actor.registered)


if __name__ == '__main__':
    unittest.main()
