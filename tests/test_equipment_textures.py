"""Official asset reuse, private replacers and strict shared-dependency gates."""
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from equipment_textures import shared_candidates, validate_shared, preview_image, compact, prepare_preview_assets
from settings import FollowerSettings
from toon import control_bytes, parameters_for


def write_bsa(path, files):
    folders = {}
    for name, data in files.items():
        folder, filename = name.rsplit('/', 1)
        folders.setdefault(folder, []).append((filename.encode()+b'\0', data))
    names = b''.join(name for entries in folders.values() for name, _ in entries)
    folder_bytes = sum(1+len(folder.encode())+1+16*len(entries) for folder, entries in folders.items())
    offset = 36+16*len(folders)+folder_bytes+len(names)
    header = struct.pack('<4s8I', b'BSA\0', 104, 36, 3, len(folders), len(files), 0, len(names), 2)
    records = b''.join(struct.pack('<QII', 0, len(entries), 0) for entries in folders.values())
    blocks, payload = bytearray(), bytearray()
    for folder, entries in folders.items():
        folder = folder.encode()+b'\0'
        blocks += bytes([len(folder)])+folder
        for _, data in entries:
            blocks += struct.pack('<QII', 0, len(data), offset)
            payload += data
            offset += len(data)
    path.write_bytes(header+records+blocks+names+payload)


class EquipmentTextureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output, self.data = self.root/'output', self.root/'Data'
        self.output.mkdir()
        self.data.mkdir()
        self.settings = FollowerSettings(mod_id='TextureReuse')
        self.settings.save(self.output/'settings.json')
        self.payload = control_bytes(parameters_for({}))
        self.archive = self.data/'Skyrim - Textures0.bsa'
        self.name = 'textures/armor/test.dds'
        write_bsa(self.archive, {self.name:self.payload})
        self.relative = 'textures/'+self.settings.asset_dir+'/equipment/hash_test.dds'
        private = self.output/'mod'/self.relative
        private.parent.mkdir(parents=True)
        private.write_bytes(self.payload)
        self.plan = {'plugins':['Skyrim.esm'], 'textures':{self.name:self.relative}}

    def candidates(self):
        return shared_candidates(self.output, self.data, self.plan)

    def report(self):
        entries = list(self.candidates().values())
        report = {'schema':1, 'game_data':str(self.data), 'plugins':['Skyrim.esm'], 'textures':entries}
        (self.output/'equipment-textures.json').write_text(json.dumps(report))
        return report

    def test_only_identical_official_bytes_are_reused(self):
        self.assertEqual(self.candidates()[self.relative]['path'], self.name)
        (self.output/'mod'/self.relative).write_bytes(self.payload+b'modified')
        self.assertEqual(self.candidates(), {})
        write_bsa(self.archive, {'textures/armor/other.dds':self.payload})
        self.assertEqual(self.candidates(), {})

    def test_loose_and_optional_archives_cannot_silently_change_selected_appearance(self):
        loose = self.data/self.name
        loose.parent.mkdir(parents=True)
        loose.write_bytes(b'replacer')
        self.assertEqual(self.candidates(), {})
        loose.write_bytes(self.payload)
        self.assertEqual(len(self.candidates()), 1)
        write_bsa(self.data/'OptionalMod.bsa', {self.name:b'override'})
        self.assertEqual(len(self.candidates()), 1, 'Identical loose file wins over archives')
        loose.unlink()
        self.assertEqual(self.candidates(), {}, 'Do not guess whether an optional archive is active')

    def test_installed_profile_reuses_native_path_but_bundles_mod_only_paths(self):
        self.plan['source_profile'] = 'installed'
        self.settings.fit_source = 'installed'
        self.settings.save(self.output/'settings.json')
        loose = self.data/self.name
        loose.parent.mkdir(parents=True)
        loose.write_bytes(b'installed replacer')
        (self.output/'mod'/self.relative).write_bytes(b'installed replacer')
        self.assertEqual(len(self.candidates()),1)
        report = self.report()
        report['source_profile'] = 'installed'
        (self.output/'equipment-textures.json').write_text(json.dumps(report))
        self.assertEqual(len(validate_shared(self.output)),1)
        loose.unlink()
        with self.assertRaisesRegex(ValueError,'overridden'):
            validate_shared(self.output)
        self.assertEqual(self.candidates(),{})
        self.plan['textures'] = {'textures/modonly/test.dds':self.relative}
        custom = self.data/'textures/modonly/test.dds'
        custom.parent.mkdir(parents=True)
        custom.write_bytes(b'installed replacer')
        self.assertEqual(self.candidates(),{},'Do not add a required dependency on mod-only paths')

    def test_unreadable_optional_archive_keeps_private_images(self):
        (self.data/'Unknown.bsa').write_bytes(b'unknown format')
        with self.assertLogs('equipment_textures', level='WARNING'):
            self.assertEqual(self.candidates(), {})

    def test_gate_rejects_changed_missing_duplicated_or_unsafe_dependencies(self):
        report = self.report()
        self.assertEqual(set(validate_shared(self.output)), {self.name})
        loose = self.data/self.name
        loose.parent.mkdir(parents=True)
        loose.write_bytes(b'late override')
        with self.assertRaisesRegex(ValueError, 'overridden'):
            validate_shared(self.output)
        loose.unlink()
        write_bsa(self.archive, {self.name:b'changed archive'})
        with self.assertRaisesRegex(ValueError, 'differs from fitted source'):
            validate_shared(self.output)
        write_bsa(self.archive, {self.name:self.payload})
        path = self.output/'equipment-textures.json'
        for key,value in [('path','textures/../escape.dds'),('preview','../escape.png'),
                          ('private_path','textures/unrelated.dds'),('sha256','wrong')]:
            entry = {**report['textures'][0],key:value}
            path.write_text(json.dumps({**report,'textures':[entry]}))
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_shared(self.output)
        path.write_text(json.dumps({**report,'textures':report['textures']*2}))
        with self.assertRaises(ValueError):
            validate_shared(self.output)
        path.write_text(json.dumps(report))
        self.archive.unlink()
        with self.assertRaises(FileNotFoundError):
            validate_shared(self.output)

    def test_preview_keeps_full_path_identity_when_basenames_match(self):
        report = self.report()
        entry = {**report['textures'][0], 'path':'textures/other/test.dds','preview':'other_test.png'}
        report['textures'].append(entry)
        (self.output/'equipment-textures.json').write_text(json.dumps(report))
        self.assertEqual(preview_image(self.output, r'C:\Game\Data\textures\armor\test.dds').name, 'hash_test.png')
        self.assertEqual(preview_image(self.output, '//textures/other/test.dds').name, 'other_test.png')
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            preview_image(self.output, 'test.dds')

    @unittest.skipUnless(os.name == 'nt', 'Requires local NiflyDLL')
    def test_compaction_preserves_geometry_both_variants_and_effect_shader_readback(self):
        from custom_skeleton import NifFile
        from pyn.pynifly import BSEffectShaderProperty
        mesh = self.output/'mod/meshes'/self.settings.asset_dir
        mesh.mkdir(parents=True)
        name = 'fitted_test_1.nif'
        with NifFile() as nif:
            nif.initialize('SKYRIMSE', str(mesh/name))
            for surface in ('Lit','Effect'):
                shape = nif.createShapeFromData(surface, [(0,0,0),(1,0,0),(0,1,0)], [(0,1,2)],
                                                [(0,0),(1,0),(0,1)], [(0,0,1)]*3)
                if surface == 'Effect':
                    shape.shader._properties = BSEffectShaderProperty.getbuf()
                shape.set_texture('Diffuse', self.relative)
                if surface == 'Effect':
                    shape.set_texture('Greyscale', self.relative)
                    shape.save_shader_attributes()
                    shape.write_properties()
            nif.save()
        (mesh/'fitted_test_0.nif').write_bytes((mesh/name).read_bytes())
        (self.output/'armor-fit-plan.json').write_text(json.dumps(self.plan))
        (self.output/'armor-fitting.json').write_text(json.dumps({'equipment':[{'file':name}]}))
        before = {}
        with NifFile(str(mesh/name)) as nif:
            for s in nif.shapes:
                before[s.name] = (s.verts,s.tris,s.uvs,s.normals)
        compact(self.output,self.data)
        self.assertFalse((self.output/'mod'/self.relative).exists())
        with patch('equipment_textures.GameAssets', side_effect=AssertionError('Blender must not load archives')):
            preview_root = prepare_preview_assets(self.output,[mesh/name])
            self.assertEqual((preview_root/self.name).read_bytes(),self.payload)
        self.assertEqual((mesh/name).read_bytes(),(mesh/'fitted_test_0.nif').read_bytes())
        with NifFile(str(mesh/name)) as nif:
            for s in nif.shapes:
                self.assertEqual((s.verts,s.tris,s.uvs,s.normals),before[s.name])
                self.assertEqual(s.textures['Diffuse'].replace('\\','/'),self.name)
                if s.name == 'Effect':
                    self.assertEqual(s.shader.blockname,'BSEffectShaderProperty')
                    self.assertEqual(s.textures['Greyscale'].replace('\\','/'),self.name)
        once = (mesh/name).read_bytes()
        compact(self.output,self.data)
        self.assertEqual((mesh/name).read_bytes(),once)
