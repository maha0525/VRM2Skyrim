"""Native opt-in markers, color-space-safe controls and strict adapter scope."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from nif_materials import normalize_material_colors
from settings import FollowerSettings
from toon import SIGNATURE, control_bytes, parameters_for, patch_lighting, prepare_materials, validate_toon

NATIVE = os.name == 'nt' and (Path(__file__).resolve().parents[1]/'dependencies/io_scene_nifly/NiflyDLL.dll').is_file()


class ToonTests(unittest.TestCase):
    @unittest.skipUnless(NATIVE, 'Requires local Windows NiflyDLL')
    def test_split_materials_with_shared_texture_are_not_guessed_and_coverage_is_complete(self):
        from custom_skeleton import NifFile
        from appearance_materials import derived_shape, exported_shapes
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            settings = FollowerSettings(mod_id='SplitToon')
            settings.save(output/'settings.json')
            mesh = output/'mod/meshes'/settings.asset_dir
            mesh.mkdir(parents=True)
            sources = [
                {'name': 'OriginalSkin', 'material_policy': {'extensions': {
                    'VRMC_materials_mtoon': {'shadeColorFactor': [.3, .4, .5], 'shadingToonyFactor': .6}}}},
                {'name': 'OriginalClothing', 'material_policy': {'extensions': {
                    'VRMC_materials_mtoon': {'shadeColorFactor': [.8, .7, .6], 'shadingToonyFactor': .9}}}}]
            components = []
            for filename, names in [('body.nif', ['OriginalSkin_body_32']),
                                    ('garment.nif', ['Clothing', 'V2SClothingSkin_OriginalSkin_body_32_32'])]:
                with NifFile() as nif:
                    nif.initialize('SKYRIMSE', str(mesh/filename))
                    for name in names:
                        s = nif.createShapeFromData(name, [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
                                                    [(0, 1, 2)], [(0, 0), (1, 0), (0, 1)], [(0, 0, 1)]*3)
                        s.set_texture('Diffuse', 'textures/shared.dds')
                    nif.save()
                bindings = {name: sources[1 if name == 'Clothing' else 0] for name in names}
                components.append({'file': filename, 'shapes': exported_shapes(mesh/filename, bindings)})
            (output/'appearance.json').write_text(json.dumps({'components': components}))
            report = prepare_materials(output)
            self.assertEqual(validate_toon(output), 3)
            values = {e['shape']: e for e in report['materials']}
            self.assertEqual(values['OriginalSkin_body_32']['parameters'],
                             values['V2SClothingSkin_OriginalSkin_body_32_32']['parameters'])
            self.assertNotEqual(values['Clothing']['parameters'], values['OriginalSkin_body_32']['parameters'])
            hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in mesh.glob('*.nif')}
            self.assertEqual(prepare_materials(output), report)
            self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in mesh.glob('*.nif')}, hashes)
            report['materials'].pop()
            (output/'toon.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'coverage differs'):
                validate_toon(output)
            # A familiar diffuse texture is not evidence of material ownership.
            components[0]['shapes'] = [derived_shape(sources[0], 'WrongName')]
            (output/'appearance.json').write_text(json.dumps({'components': components}))
            with self.assertRaisesRegex(ValueError, 'Unregistered source material'):
                prepare_materials(output)
            with self.assertRaisesRegex(ValueError, 'bindings changed'):
                exported_shapes(mesh/'body.nif', {'WrongName': sources[0]})

    def test_default_opt_out_and_explicit_setting(self):
        self.assertFalse(FollowerSettings().toon_enabled)
        with self.assertRaises(ValueError):
            FollowerSettings(toon_enabled='true')
        self.assertTrue(FollowerSettings.from_dict({'toon_enabled': True}).toon_enabled)

    def test_shadow_multiplier_is_not_applied_twice(self):
        material = {'pbrMetallicRoughness': {'baseColorFactor': [.5, .8, 0, 1]},
                    'extensions': {'VRMC_materials_mtoon': {'shadeColorFactor': [.25, .4, 0],
                                                          'shadingToonyFactor': .9, 'shadingShiftFactor': -.2}}}
        original = copy.deepcopy(material)
        value = parameters_for(material, strength=0.)
        self.assertEqual(value['shade'], [.5, .5, 1.])
        self.assertEqual(value['toony'], .9)
        self.assertEqual(value['shift'], -.2)
        self.assertEqual(material, original)

    def test_legacy_shade_color_is_linearized_and_retained(self):
        document = {'materials': [{'name': 'Legacy'}], 'extensions': {'VRM': {'materialProperties': [
            {'shader': 'VRM/MToon', 'vectorProperties': {'_Color': [1, 1, 1, 1], '_ShadeColor': [.5, .5, .5, 1]},
             'floatProperties': {'_ShadeToony': .8, '_ShadeShift': -.1}}]}}}
        normalize_material_colors(document)
        parameters = parameters_for(document['materials'][0], strength=0.)
        np.testing.assert_allclose(parameters['shade'], [.21404114]*3)
        self.assertEqual((parameters['toony'], parameters['shift']), (.8, -.1))

    def test_control_alpha_survives_srgb_views_and_has_valid_dds_storage(self):
        parameters = parameters_for({})
        blob = control_bytes(parameters)
        self.assertEqual(len(blob), 148+8*4*4)
        self.assertEqual(struct.unpack_from('<I', blob, 128)[0], 28)
        self.assertEqual(blob[148:156], SIGNATURE)
        alpha = [blob[148+i*4+3]/255 for i in range(2, 8)]
        expected = [*parameters['shade'], parameters['toony'], (parameters['shift']+1)/2, parameters['gi_equalization']]
        np.testing.assert_allclose(alpha, expected, atol=.5/255)
        with self.assertRaises(ValueError):
            control_bytes({**parameters, 'toony': float('nan')})

    def test_unverified_adapter_does_not_silently_patch_other_versions(self):
        for source in (b'', b'#include "Common/LightingEval.hlsli"', b'other graphics mod'):
            with self.assertRaisesRegex(ValueError, 'Unsupported Community'):
                patch_lighting(source)

    @unittest.skipUnless(NATIVE, 'Requires local Windows NiflyDLL')
    def test_native_marker_preserves_visual_data_and_includes_head_variants(self):
        from custom_skeleton import NifFile
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            settings = FollowerSettings(mod_id='ToonFixture')
            settings.save(output/'settings.json')
            mesh = output/'mod/meshes'/settings.asset_dir
            mesh.mkdir(parents=True)
            manifest = {'components': [{'file': 'avatar.nif', 'shapes': [
                {'name': 'Surface', 'diffuse': 'textures/fixture.dds', 'material_policy': {}}]}]}
            (output/'appearance.json').write_text(json.dumps(manifest))
            for filename in ('avatar.nif', 'fixed_hair_on.nif'):
                with NifFile() as nif:
                    nif.initialize('SKYRIMSE', str(mesh/filename))
                    shape = nif.createShapeFromData('Surface', [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
                                                    [(0, 1, 2)], [(0, 0), (1, 0), (0, 1)], [(0, 0, 1)]*3)
                    shape.set_texture('Diffuse', 'textures/fixture.dds')
                    shape.set_texture('Normal', 'textures/normal.dds')
                    nif.save()
            before = {}
            for path in mesh.glob('*.nif'):
                with NifFile(str(path)) as nif:
                    s = nif.shapes[0]
                    before[path.name] = (s.verts, s.tris, s.normals, s.uvs, s.shader.textures['Diffuse'])
            report = prepare_materials(output)
            self.assertEqual(len(report['materials']), 2)
            self.assertEqual(validate_toon(output), 2)
            hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in mesh.glob('*.nif')}
            prepare_materials(output)
            self.assertEqual(hashes, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in mesh.glob('*.nif')})
            for path in mesh.glob('*.nif'):
                with NifFile(str(path)) as nif:
                    s = nif.shapes[0]
                    for old, new in zip(before[path.name][:-1], (s.verts, s.tris, s.normals, s.uvs)):
                        np.testing.assert_array_equal(old, new)
                    self.assertEqual(s.shader.textures['Diffuse'], before[path.name][-1])
                    self.assertEqual(s.shader.properties.Emissive_Mult, 0)
            control = output/'mod'/report['materials'][0]['control']
            control.write_bytes(control.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, 'DDS parameters changed'):
                validate_toon(output)
