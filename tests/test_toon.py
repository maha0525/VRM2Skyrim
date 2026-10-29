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
from toon import (BOTTLED_SHADERS_RELEASE, COMMUNITY_SHADERS_DLL_VERSION, LICENSE_FILES, LICENSE_FOLDER,
                  MODIFIED_NOTICE, ROOT, SHIPPED_SHADER, SIGNATURE, SUPPORTED_COMPOSITE, SUPPORTED_LIGHTING,
                  control_bytes, parameters_for, patch_composite, patch_lighting, prepare_materials, shader_package,
                  shipped_adapter, validate_toon)

NATIVE = os.name == 'nt' and (Path(__file__).resolve().parents[1]/'dependencies/io_scene_nifly/NiflyDLL.dll').is_file()


class ToonTests(unittest.TestCase):
    def test_shader_packages_keep_normal_and_diagnostic_distinct(self):
        # Exercise packaging separately from the full Windows FXC/GPU checks.
        source = (b'#\tinclude "Common/LightingEval.hlsli"\n'
                  b'\tPS_OUTPUT psout;\n\tfloat4 color = 0;\n'
                  b'\tfloat3 worldNormal = normalize(mul(tbn, normal.xyz));\n'
                  b'#\tif !defined(DEFERRED)\n\tcolor.xyz = ColorManagement::SceneToLinear(color.xyz);\n'
                  b'\t// Stored as 1 - vertexAO so the cleared default (0) means no occlusion\n'
                  b'#\tif defined(FUR_SHELLS_DEPTH)\n\tpsout = (PS_OUTPUT)0;\n#\tendif\n\n\treturn psout;\n')
        composite = (b'#include "Common/GBuffer.hlsli"\n'
                     b'\tfloat3 albedo = AlbedoTexture[dispatchID.xy];\n'
                     b'\tSampleSSGI(dispatchID.xy, normalWS, ssgiAo, ssgiIl);\n')
        with tempfile.TemporaryDirectory() as temp:
            # The layout of the Bottled Shaders mod folder: Shaders/ and the
            # licence folder SKSE/Plugins/CommunityShaders/Licenses beside it.
            mod = Path(temp)
            root = mod/'Shaders'
            root.mkdir()
            (root/'Lighting.hlsl').write_bytes(source)
            (root/'DeferredCompositeCS.hlsl').write_bytes(composite)
            licenses = mod/LICENSE_FOLDER
            licenses.mkdir(parents=True)
            for name in LICENSE_FILES:
                (licenses/name).write_text('Fixture '+name, encoding='utf8')
            (licenses/'LICENSE-SebH-MIT.txt').write_text('Not for these files', encoding='utf8')
            with patch('toon.SUPPORTED_LIGHTING', hashlib.sha256(source).hexdigest()), \
                    patch('toon.SUPPORTED_COMPOSITE', hashlib.sha256(composite).hexdigest()):
                normal = shader_package(root, mod/'output')
                diagnostic = shader_package(root, mod/'output', diagnostic=True)
                # An explicit licence folder is used instead of the derived one.
                explicit = mod/'explicit'
                explicit.mkdir()
                for name in LICENSE_FILES:
                    (explicit/name).write_text('Explicit '+name, encoding='utf8')
                with zipfile.ZipFile(shader_package(root, mod/'explicit-output', licenses=explicit)) as package:
                    self.assertEqual(package.read('Shaders/VRM2Skyrim/Licenses/COPYING.txt'), b'Explicit COPYING.txt')
                (licenses/'EXCEPTIONS.md').unlink()
                with self.assertRaisesRegex(ValueError, 'licence files not found.*EXCEPTIONS.md'):
                    shader_package(root, mod/'missing-output')
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
                    self.assertEqual(len(package.namelist()), 13)
                    self.assertNotIn(b'defined(SKINNED)', lighting)
                    self.assertEqual(metadata['bottled_shaders_release'], '1.0.22')
                    self.assertEqual(hashlib.sha256(package.read('Shaders/DeferredCompositeCS.hlsl')).hexdigest(),
                                     metadata['patched_composite_sha256'])
                    for name in LICENSE_FILES:
                        self.assertEqual(package.read('Shaders/VRM2Skyrim/Licenses/'+name), ('Fixture '+name).encode())
                    self.assertFalse(any('SebH' in name or 'CommunityShaders-LICENSE' in name for name in package.namelist()))
                    self.assertIn('Shaders/VRM2Skyrim/VRM2Skyrim-LICENSE.txt', package.namelist())
                    for name in ('Lighting.hlsl', 'DeferredCompositeCS.hlsl'):
                        self.assertTrue(package.read('Shaders/'+name).startswith(MODIFIED_NOTICE.encode()), name)
                    # The diagnostic colour precedes the fur-shell depth clear.
                    self.assertLess(lighting.index(b'psout.Diffuse.xyz = float3(1, 0, 1);'),
                                    lighting.index(b'psout = (PS_OUTPUT)0;'))
            (root/'Lighting.hlsl').write_bytes(source+b'changed')
            with self.assertRaisesRegex(ValueError, 'Unsupported Community'):
                shader_package(root, mod/'output', licenses=explicit)

    def test_committed_shader_zip_is_the_patch_of_bottled_shaders_1_0_22(self):
        # The originals are not in the repository. Removing exactly the lines
        # the adapter inserts from the committed ZIP must give files whose
        # SHA256 are the 1.0.22 originals, and patching those must give the ZIP.
        with zipfile.ZipFile(SHIPPED_SHADER) as package:
            lighting = package.read('Shaders/Lighting.hlsl').decode('utf8')
            composite = package.read('Shaders/DeferredCompositeCS.hlsl').decode('utf8')
        guard = '#if !defined(LANDSCAPE) && !defined(LODLANDSCAPE) && !defined(TRUE_PBR)'
        self.assertTrue(lighting.startswith(MODIFIED_NOTICE))
        kept, depth, closed = [], 0, False
        for line in lighting[len(MODIFIED_NOTICE):].split('\n'):
            if depth == 0 and line.startswith(guard):
                depth = 1
            elif depth:
                depth += line.startswith('#if') - line.startswith('#endif')
                closed = depth == 0
            elif closed and line == '' and kept[-1] == '':
                closed = False  # the separating blank line after the GBuffer marker
            else:
                kept.append(line)
                closed = False
        original_lighting = '\n'.join(kept).encode('utf8')
        self.assertTrue(composite.startswith(MODIFIED_NOTICE))
        original_composite = composite[len(MODIFIED_NOTICE):]
        for inserted in ('#include "VRM2Skyrim/ToonDeferred.hlsli"\n',
                         '\tconst bool v2sMarked = V2SIsMarkedMask(MasksTexture[dispatchID.xy]);\n',
                         '    if (v2sMarked) {\n        ssgiAo = 1;\n        ssgiIl = 0;\n    }\n'):
            self.assertEqual(original_composite.count(inserted), 1, inserted)
            original_composite = original_composite.replace(inserted, '')
        original_composite = original_composite.encode('utf8')
        self.assertEqual(hashlib.sha256(original_lighting).hexdigest(), SUPPORTED_LIGHTING)
        self.assertEqual(hashlib.sha256(original_composite).hexdigest(), SUPPORTED_COMPOSITE)
        self.assertEqual(SUPPORTED_LIGHTING, '188f5016869dc3a2cf1460a56296b01ddf848b641e4c9e0c36d809a02c800b90')
        self.assertEqual(SUPPORTED_COMPOSITE, '8abca54c90d1f2f732120ee8c9d43318d342cda74cc3b12e7206a5c5a0e0a7a9')
        self.assertEqual(patch_lighting(original_lighting), lighting.encode('utf8'))
        self.assertEqual(patch_composite(original_composite), composite.encode('utf8'))
        diagnostic = patch_lighting(original_lighting, diagnostic=True)
        self.assertEqual(diagnostic.replace(b'#define V2S_TOON_DIAGNOSTIC 1', b'#define V2S_TOON_DIAGNOSTIC 0'),
                         lighting.encode('utf8'))
        # Already patched files and the 1.0.4 forward anchor are refused.
        for function, patched in ((patch_lighting, lighting), (patch_composite, composite)):
            with self.assertRaisesRegex(ValueError, 'Unsupported Community'):
                function(patched.encode('utf8'))
        old = original_lighting.replace(b'ColorManagement::SceneToLinear(color.xyz);\n\tcolor.xyz += specularColor;',
                                        b'Color::IrradianceToLinear(color.xyz);\n\tcolor.xyz += specularColor;')
        self.assertNotEqual(old, original_lighting)
        with patch('toon.SUPPORTED_LIGHTING', hashlib.sha256(old).hexdigest()), \
                self.assertRaisesRegex(ValueError, 'anchor changed'):
            patch_lighting(old)

    def test_committed_shader_zip_matches_this_version_and_adapter(self):
        # Users install this ZIP directly; a VERSION bump or HLSL change
        # without rebuilding it with toon.py --shader-root must fail here.
        self.assertEqual(SHIPPED_SHADER, ROOT/'toon-shader'/f'VRM2Skyrim-Toon-Shader-{VERSION}.zip')
        self.assertTrue(SHIPPED_SHADER.is_file(), f'Rebuild {SHIPPED_SHADER.name} with toon.py --shader-root')
        with zipfile.ZipFile(SHIPPED_SHADER) as package:
            self.assertIsNone(package.testzip())
            metadata = json.loads(package.read('Shaders/VRM2Skyrim/adapter.json'))
            self.assertEqual(metadata['version'], VERSION)
            self.assertIs(metadata['diagnostic'], False)
            self.assertEqual(metadata['lighting_sha256'], SUPPORTED_LIGHTING)
            self.assertEqual(metadata['composite_sha256'], SUPPORTED_COMPOSITE)
            self.assertEqual(metadata['community_shaders_dll_version'], COMMUNITY_SHADERS_DLL_VERSION)
            self.assertEqual(metadata['bottled_shaders_release'], BOTTLED_SHADERS_RELEASE)
            self.assertEqual(metadata, shipped_adapter())
            lighting = package.read('Shaders/Lighting.hlsl')
            self.assertEqual(hashlib.sha256(lighting).hexdigest(), metadata['patched_lighting_sha256'])
            self.assertIn(b'#define V2S_TOON_DIAGNOSTIC 0', lighting)
            self.assertEqual(hashlib.sha256(package.read('Shaders/DeferredCompositeCS.hlsl')).hexdigest(),
                             metadata['patched_composite_sha256'])
            # GPL-3.0 with the Community Shaders exceptions for the patched files.
            self.assertEqual(sorted(name for name in package.namelist() if '/Licenses/' in name),
                             sorted('Shaders/VRM2Skyrim/Licenses/'+name for name in LICENSE_FILES))
            self.assertIn(b'GNU GENERAL PUBLIC LICENSE', package.read('Shaders/VRM2Skyrim/Licenses/COPYING.txt'))
            self.assertIn(b'Version 3', package.read('Shaders/VRM2Skyrim/Licenses/COPYING.txt'))
            self.assertIn(b'Modding Exception', package.read('Shaders/VRM2Skyrim/Licenses/EXCEPTIONS.md'))
            self.assertNotIn('Shaders/VRM2Skyrim/CommunityShaders-LICENSE.txt', package.namelist())
            self.assertEqual(package.read('Shaders/VRM2Skyrim/VRM2Skyrim-LICENSE.txt'), (ROOT/'LICENSE').read_bytes())
            self.assertEqual(package.read('Shaders/VRM2Skyrim/README.md'), (ROOT/'docs/TOON.md').read_bytes())
            runtime = sorted((ROOT/'runtime/toon').glob('*.hlsli'))
            self.assertTrue(runtime)
            self.assertEqual(sorted(name for name in package.namelist() if name.endswith('.hlsli')),
                             sorted(f'Shaders/VRM2Skyrim/{path.name}' for path in runtime))
            for path in runtime:
                self.assertEqual(package.read(f'Shaders/VRM2Skyrim/{path.name}'), path.read_bytes(), path.name)

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

    def test_preview_outline_and_split_skin_policies_follow_manifest(self):
        from types import SimpleNamespace
        from toon_outlines import outline_name as build_outline_name
        from toon_preview import assign_toon_shape_policies, effects_for, outline_name

        self.assertEqual(outline_name('Body_Mesh.001'), build_outline_name('Body_Mesh.001'))
        policy = {'extensions': {'VRMC_materials_mtoon': {
            'shadeColorFactor': [0.6, 0.7, 0.8], 'outlineColorFactor': [0.1, 0.2, 0.3], 'outlineLightingMixFactor': 0.5}}}
        effects = effects_for(policy, outline=True)
        self.assertTrue(effects['outline'])
        self.assertEqual((effects['outline_r'], effects['outline_g'], effects['outline_b']), (0.1, 0.2, 0.3))

        class FakeMat(dict):
            def __init__(self, name):
                super().__init__()
                self.name = name

            def copy(self):
                cloned = FakeMat(self.name)
                cloned.update(self)
                return cloned

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output / 'appearance.json').write_text(json.dumps({
                'components': [{'id': 'body', 'shapes': [{'name': 'Body', 'material_policy': policy}]}]}), encoding='utf8')
            out_shape = outline_name('Body')
            shared = FakeMat('SharedMat')
            body_obj = SimpleNamespace(name='OriginalSkin_Body_32', type='MESH', visible_shadow=True,
                                       data=SimpleNamespace(materials=[shared]))
            outline_obj = SimpleNamespace(name=out_shape, type='MESH', visible_shadow=True,
                                          data=SimpleNamespace(materials=[shared]))
            armor_obj = SimpleNamespace(name='Fitted_IronCuirass', type='MESH', visible_shadow=True,
                                        data=SimpleNamespace(materials=[FakeMat('ArmorMat')]))
            mat_a = FakeMat('MultiA')
            mat_a['V2S_Preview_Policy'] = json.dumps({'name': 'MatA'})
            mat_b = FakeMat('MultiB')
            mat_b['V2S_Preview_Policy'] = json.dumps({'name': 'MatB'})
            multi_obj = SimpleNamespace(name='Original_VRMNode_00290', type='MESH', visible_shadow=True,
                                        data=SimpleNamespace(materials=[mat_a, mat_b]))
            assign_toon_shape_policies(output, [body_obj, outline_obj, armor_obj, multi_obj])
            self.assertEqual(json.loads(body_obj.data.materials[0]['V2S_Preview_Policy']), policy)
            self.assertFalse(outline_obj.visible_shadow)
            self.assertIsNot(outline_obj.data.materials[0], body_obj.data.materials[0])
            self.assertTrue(outline_obj.data.materials[0].get('V2S_Preview_Outline'))
            self.assertEqual(json.loads(outline_obj.data.materials[0]['V2S_Preview_Policy']), policy)
            self.assertNotIn('V2S_Preview_Policy', armor_obj.data.materials[0])
            self.assertEqual(json.loads(multi_obj.data.materials[0]['V2S_Preview_Policy']), {'name': 'MatA'})
            self.assertEqual(json.loads(multi_obj.data.materials[1]['V2S_Preview_Policy']), {'name': 'MatB'})

    def test_base_texture_lookup_ignores_non_base_color_textures(self):
        from types import SimpleNamespace
        from toon_preview import _find_base_texture_node

        normal_img = SimpleNamespace(filepath='textures/normal.png')
        normal_node = SimpleNamespace(name='Normal_Texture', type='TEX_IMAGE', image=normal_img)
        shader_node = SimpleNamespace(
            name='Principled BSDF', type='BSDF_PRINCIPLED',
            inputs={'Base Color': SimpleNamespace(is_linked=False, links=[])})

        class FakeNodes(list):
            def get(self, name):
                return next((n for n in self if n.name == name), None)

        tree = SimpleNamespace(nodes=FakeNodes([shader_node, normal_node]))
        solid_with_normal = {'pbrMetallicRoughness': {'baseColorFactor': [0.8, 0.2, 0.2, 1.0]},
                             'normalTexture': {'index': 0}}
        self.assertEqual(_find_base_texture_node(tree, policy=solid_with_normal), (None, False))
        # Even if a dummy Diffuse_Texture node exists on a solid NIF material, policy without baseColorTexture stays solid.
        diffuse_node = SimpleNamespace(name='Diffuse_Texture', type='TEX_IMAGE',
                                       image=SimpleNamespace(filepath='dds-preview/solid.png'))
        tree_with_dummy = SimpleNamespace(nodes=FakeNodes([shader_node, diffuse_node, normal_node]))
        self.assertEqual(_find_base_texture_node(tree_with_dummy, policy=solid_with_normal), (None, False))
        textured_policy = {'pbrMetallicRoughness': {'baseColorFactor': [1, 1, 1, 1], 'baseColorTexture': {'index': 0}}}
        self.assertEqual(_find_base_texture_node(tree_with_dummy, policy=textured_policy), (diffuse_node, True))
