"""Native opt-in markers, color-space-safe controls and strict adapter scope."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from nif_materials import normalize_material_colors
from settings import FollowerSettings, VERSION
from toon import SIGNATURE, control_bytes, parameters_for, patch_composite, patch_lighting, prepare_materials, shader_package, validate_toon

NATIVE = os.name == 'nt' and (Path(__file__).resolve().parents[1]/'dependencies/io_scene_nifly/NiflyDLL.dll').is_file()


class ToonTests(unittest.TestCase):
    def test_shader_packages_keep_normal_and_diagnostic_distinct(self):
        # Exercise packaging separately from the full Windows FXC/GPU checks.
        source = (b'#\tinclude "Common/LightingEval.hlsli"\n'
                  b'\tPS_OUTPUT psout;\n\tfloat4 color = 0;\n'
                  b'\tfloat3 worldNormal = normalize(mul(tbn, normal.xyz));\n'
                  b'#\tif !defined(DEFERRED)\n\tcolor.xyz = Color::IrradianceToLinear(color.xyz);\n'
                  b'\t// Stored as 1 - vertexAO so the cleared default (0) means no occlusion\n'
                  b'\treturn psout;\n')
        composite = (b'#include "Common/GBuffer.hlsli"\n'
                     b'\tfloat3 albedo = AlbedoTexture[dispatchID.xy];\n'
                     b'\tSampleSSGI(dispatchID.xy, normalWS, ssgiAo, ssgiIl);\n')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/'Lighting.hlsl').write_bytes(source)
            (root/'DeferredCompositeCS.hlsl').write_bytes(composite)
            (root/'LICENSE').write_text('Fixture upstream license', encoding='utf8')
            with patch('toon.SUPPORTED_LIGHTING', hashlib.sha256(source).hexdigest()), \
                    patch('toon.SUPPORTED_COMPOSITE', hashlib.sha256(composite).hexdigest()):
                normal = shader_package(root, root/'output')
                diagnostic = shader_package(root, root/'output', diagnostic=True)
            self.assertNotEqual(normal, diagnostic)
            for path, is_diagnostic in [(normal, False), (diagnostic, True)]:
                with zipfile.ZipFile(path) as package:
                    self.assertIsNone(package.testzip())
                    self.assertTrue(all(name.startswith('Shaders/') for name in package.namelist()))
                    self.assertFalse(any(name.endswith(('.dll', '.pso', '.cso')) for name in package.namelist()))
                    metadata = json.loads(package.read('Shaders/VRM2Skyrim/adapter.json'))
                    self.assertEqual(metadata['prototype'], 6)
                    self.assertEqual(metadata['version'], VERSION)
                    self.assertEqual(path.name, f'VRM2Skyrim-Toon-Shader-{VERSION}'+('-Diagnostic' if is_diagnostic else '')+'.zip')
                    self.assertEqual(metadata['diagnostic'], is_diagnostic)
                    lighting = package.read('Shaders/Lighting.hlsl')
                    self.assertEqual(hashlib.sha256(lighting).hexdigest(), metadata['patched_lighting_sha256'])
                    self.assertIn(f'#define V2S_TOON_DIAGNOSTIC {int(is_diagnostic)}'.encode(), lighting)
                    self.assertEqual(len(package.namelist()), 10)
                    self.assertNotIn(b'defined(SKINNED)', lighting)
                    self.assertEqual(hashlib.sha256(package.read('Shaders/DeferredCompositeCS.hlsl')).hexdigest(),
                                     metadata['patched_composite_sha256'])
                    self.assertEqual(package.read('Shaders/VRM2Skyrim/CommunityShaders-LICENSE.txt'),
                                     b'Fixture upstream license')
                    self.assertIn('Shaders/VRM2Skyrim/VRM2Skyrim-LICENSE.txt', package.namelist())
            (root/'Lighting.hlsl').write_bytes(source+b'changed')
            with self.assertRaisesRegex(ValueError, 'Unsupported Community'):
                shader_package(root, root/'output')

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

    def test_default_enabled_and_explicit_saved_choices(self):
        self.assertTrue(FollowerSettings().toon_enabled)
        self.assertTrue(FollowerSettings.from_dict({}).toon_enabled)
        with self.assertRaises(ValueError):
            FollowerSettings(toon_enabled='true')
        self.assertTrue(FollowerSettings.from_dict({'toon_enabled': True}).toon_enabled)
        self.assertFalse(FollowerSettings.from_dict({'toon_enabled': False}).toon_enabled)

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
        np.testing.assert_allclose([parameters['toony'], parameters['shift']], [.89, -.01])

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
        for function in (patch_lighting, patch_composite):
            for source in (b'', b'#include "Common/LightingEval.hlsli"', b'other graphics mod'):
                with self.assertRaisesRegex(ValueError, 'Unsupported Community'):
                    function(source)

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
