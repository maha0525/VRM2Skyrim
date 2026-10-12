"""Source material contracts without Blender or private avatars."""
import unittest
import os
from pathlib import Path
import tempfile
from nif_materials import culling_flags, lighting_flags_2, DOUBLE_SIDED


class MaterialTests(unittest.TestCase):
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
