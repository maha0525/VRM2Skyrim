"""Source material contracts without Blender or private avatars."""
import unittest
from export_names import stable_shape_name
import os
from pathlib import Path
import tempfile
from nif_materials import culling_flags, lighting_flags_2, DOUBLE_SIDED
from nif_materials import normalize_material_colors


class MaterialTests(unittest.TestCase):
    def test_split_and_retained_skin_keep_exact_source_policy(self):
        from appearance_materials import derived_shape
        original = {'name': 'VRMNode_00494', 'source_node': 494, 'diffuse': 'textures/shared.dds',
                    'material_policy': {'name': 'Skin', 'alphaMode': 'MASK', 'alphaCutoff': .2,
                                        'extensions': {'VRMC_materials_mtoon': {'shadingToonyFactor': .6}}}}
        torso = derived_shape(original, 'VRMNode_00494_body_32')
        retained = derived_shape(torso, 'V2SClothingSkin_VRMNode_00494_body_32_32')
        self.assertEqual(retained['source_shape'], original['name'])
        self.assertEqual(retained['material_policy'], original['material_policy'])
        self.assertEqual(retained['source_node'], 494)
        retained['material_policy']['alphaCutoff'] = .8
        self.assertEqual(original['material_policy']['alphaCutoff'], .2)
        self.assertEqual(torso['material_policy']['alphaCutoff'], .2)
        with self.assertRaisesRegex(ValueError, 'Missing source material metadata'):
            derived_shape({'name': 'Missing'}, 'Split')

    def test_vrm0_mtoon_uses_authoritative_srgb_color_once_and_preserves_opacity(self):
        material = {'pbrMetallicRoughness': {'baseColorFactor': [.5, .25, 1, .375]}, 'alphaMode': 'BLEND'}
        document = {'materials': [material], 'extensions': {'VRM': {'materialProperties': [
            {'shader': 'VRM/MToon', 'vectorProperties': {'_Color': [.5, .25, 1, .375]},
             'floatProperties': {'_BlendMode': 3}}]}}}
        for _ in range(2):
            normalize_material_colors(document)
            color = material['pbrMetallicRoughness']['baseColorFactor']
            self.assertAlmostEqual(color[0], .21404114048223255)
            self.assertAlmostEqual(color[1], .05087608817155679)
            self.assertEqual(color[2:], [1, .375])
            self.assertTrue(material['extensions']['VRMC_materials_mtoon']['transparentWithZWrite'])

    def test_linear_vrm1_and_non_mtoon_factors_are_not_gamma_converted(self):
        for legacy in ([], [{'shader': 'VRM_USE_GLTFSHADER', 'vectorProperties': {'_Color': [.5, .5, .5, 1]}}]):
            document = {'materials': [{'pbrMetallicRoughness': {'baseColorFactor': [.5, .5, .5, 1]}}],
                        'extensions': {'VRM': {'materialProperties': legacy}}}
            normalize_material_colors(document)
            self.assertEqual(document['materials'][0]['pbrMetallicRoughness']['baseColorFactor'], [.5, .5, .5, 1])

    def test_split_primary_does_not_rename_other_material_to_its_base(self):
        names = ['VRMNode_00634.001', 'VRMNode_00634_Part000', 'VRMNode_00634_Part001']
        actual = [stable_shape_name(name) for name in names]
        self.assertEqual(actual, ['VRMNode_00634_Primitive001', 'VRMNode_00634_Part000', 'VRMNode_00634_Part001'])
        self.assertEqual(len(set(actual)), len(actual))
        self.assertTrue(all('.001' not in name for name in actual))
    def test_source_culling_is_independent_of_alpha_mode(self):
        unrelated = 0x80000021
        for mode in ('OPAQUE', 'MASK', 'BLEND'):
            for value in (False, True, None):
                material = {'alphaMode': mode}
                if value is not None:
                    material['doubleSided'] = value
                flags = culling_flags(unrelated | DOUBLE_SIDED, material)
                self.assertEqual(bool(flags & DOUBLE_SIDED), value is True)
                self.assertEqual(flags & ~DOUBLE_SIDED, unrelated)
                self.assertEqual(culling_flags(flags,material),flags)
                self.assertEqual('DOUBLE_SIDED' in lighting_flags_2(material),value is True)

    def test_transparent_depth_write_is_preserved(self):
        self.assertNotIn('ZBUFFER_WRITE',lighting_flags_2({'alphaMode':'BLEND'}))
        self.assertIn('ZBUFFER_WRITE',lighting_flags_2({'alphaMode':'MASK'}))
        self.assertIn('ZBUFFER_WRITE',lighting_flags_2({'alphaMode':'BLEND','extensions':{
            'VRMC_materials_mtoon':{'transparentWithZWrite':True}}}))


@unittest.skipUnless(os.name=='nt' and (Path(__file__).resolve().parents[1]/'dependencies/io_scene_nifly').exists(),
                     'Local native PyNifly required')
class NativeMaterialTests(unittest.TestCase):
    def test_explicit_transparent_queues_survive_native_export_and_reapplication(self):
        from custom_skeleton import NifFile, children
        from nif_materials import apply_alpha, NO_SORTER
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'order.nif'
            with NifFile() as nif:
                nif.initialize('SKYRIMSE', str(path), 'BSFadeNode', 'MaterialTest')
                for name in ('LateLashes', 'EarlyOverlay', 'OpaqueFace'):
                    nif.createShapeFromData(name, [(0,0,0),(1,0,0),(0,1,0)], [(0,1,2)],
                                            [(0,0),(1,0),(0,1)], [(0,0,1)]*3)
                nif.save()
            materials = {'LateLashes': {'alphaMode': 'BLEND', 'extras': {'V2S_render_queue': 4000}},
                         'EarlyOverlay': {'alphaMode': 'BLEND', 'extras': {'V2S_render_queue': 3000}},
                         'OpaqueFace': {'alphaMode': 'OPAQUE'}}
            for _ in range(2):
                apply_alpha(path, materials)
                with NifFile(str(path)) as nif:
                    names = {s.id:s.name for s in nif.shapes}
                    self.assertEqual([names[n] for n in children(nif, nif.rootNode) if n in names],
                                     ['OpaqueFace', 'EarlyOverlay', 'LateLashes'])
                    for shape in nif.shapes:
                        if shape.name != 'OpaqueFace':
                            self.assertTrue(shape.alpha_property.properties.flags & NO_SORTER)

    def test_real_nif_readback_preserves_alpha_and_changes_only_culling_bit(self):
        from custom_skeleton import NifFile
        from nif_materials import apply_alpha
        with tempfile.TemporaryDirectory() as tmp:
            for mode in ('OPAQUE','MASK','BLEND'):
                for side in (False,True):
                    name=mode+str(side)
                    path=Path(tmp)/(name+'.nif')
                    with NifFile() as nif:
                        nif.initialize('SKYRIMSE',str(path),'BSFadeNode','MaterialTest')
                        nif.createShapeFromData(name,[(0,0,0),(1,0,0),(0,1,0)],[(0,1,2)],
                                                [(0,0),(1,0),(0,1)],[(0,0,1)]*3)
                        nif.save()
                    # Reload native-created buffers before setting shader fields.
                    with NifFile(str(path)) as nif:
                        shape=nif.shapes[0]
                        shape.shader.properties.Shader_Flags_2=1|DOUBLE_SIDED
                        shape.shader.write_properties()
                        nif.save()
                    policy={'alphaMode':mode,'doubleSided':side}
                    for _ in range(2):
                        apply_alpha(path,{name:policy})
                        with NifFile(str(path)) as nif:
                            shape=nif.shapes[0]
                            self.assertEqual(shape.shader.properties.Shader_Flags_2 & ~DOUBLE_SIDED,1)
                            self.assertEqual(bool(shape.shader.properties.Shader_Flags_2 & DOUBLE_SIDED),side)
                            self.assertEqual(shape.tris,[(0,1,2)])
                            self.assertEqual(shape.has_alpha_property,mode!='OPAQUE')
