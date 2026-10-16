"""Authored shade data must survive the native texture format and reuse path."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from nif_materials import normalize_material_colors
from toon import parameters_for, prepare_materials, validate_toon
from toon_shade import ROOT, build_shade, metadata_pixels, pack_shade, shade_image, validate_shade


def fixture():
    image = Image.new('RGBA', (64, 8), (220, 180, 160, 0))
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    blob = stream.getvalue()
    doc = {'bufferViews': [{'byteLength': len(blob)}], 'images': [{'bufferView': 0}],
           'textures': [{'source': 0}]}
    material = {'extensions': {'VRMC_materials_mtoon': {
        'shadeColorFactor': [1, 1, 1], 'shadeMultiplyTexture': {'index': 0}}}}
    return doc, blob, material


class AuthoredShadeTests(unittest.TestCase):
    def test_small_and_unaligned_images_keep_original_pixels_and_addressing_borders(self):
        for width, height in [(2, 2), (66, 6), (1254, 1254), (1, 1), (7, 5)]:
            source = np.zeros((height, width, 4), dtype=np.uint8)
            source[..., 3] = 255
            source[:, 0, 0] = 255
            for wrap in [10497, 33071, 33648]:
                image = Image.fromarray(source)
                image.info['wrap'] = [wrap, wrap]
                result = pack_shade(image, parameters_for({}, authored=True))
                self.assertEqual(result.width % 4, 0)
                self.assertEqual(result.height % 4, 0)
                np.testing.assert_array_equal(np.asarray(result)[4:4+height, 4:4+width], source)
                expected = source[0, -1 if wrap == 10497 else 0]
                np.testing.assert_array_equal(np.asarray(result)[4, 3], expected)

    @unittest.skipUnless(os.name == 'nt' and (ROOT/'dependencies/texconv.exe').exists(), 'Requires native NIF/BC7 tools')
    def test_all_components_and_derived_materials_use_their_source_shade(self):
        from custom_skeleton import NifFile
        from inspect_vrm import write_glb
        from settings import FollowerSettings
        doc, blob, skin = fixture()
        skin['name'] = 'Skin'
        cloth = copy.deepcopy(skin)
        cloth['name'] = 'Cloth'
        cloth['extensions']['VRMC_materials_mtoon']['shadeColorFactor'] = [.2, .3, .4]
        # Identical diffuse resources do not imply identical shade ownership.
        constant = {'name': 'Constant', 'extensions': {'VRMC_materials_mtoon': {
            'shadeColorFactor': [.05, .1, .2], 'giEqualizationFactor': .35}}}
        ordinary = {'name': 'Ordinary'}
        doc['materials'] = [skin, cloth, constant, ordinary]
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            settings = FollowerSettings(mod_id='AllAuthored')
            settings.save(output/'settings.json')
            write_glb(output/'source.glb', doc, blob)
            folder = output/'mod/meshes'/settings.asset_dir
            folder.mkdir(parents=True)
            components = []
            definitions = [('face', [('Face', skin)]), ('body', [('Torso', skin)]),
                           ('hands', [('Hands', skin)]), ('feet', [('Feet', skin)]),
                           ('hair', [('Hair', cloth)]), ('underwear', [('Underwear', constant)]),
                           ('outfit', [('Clothing', cloth), ('RetainedSkin', skin), ('Ordinary', ordinary)])]
            before = {}
            for index, (component, entries) in enumerate(definitions):
                filename = component+'.nif'
                with NifFile() as nif:
                    nif.initialize('SKYRIMSE', str(folder/filename))
                    for name, material in entries:
                        shape = nif.createShapeFromData(name, [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
                                                        [(0, 1, 2)], [(0, 0), (1, 0), (0, 1)], [(0, 0, 1)]*3)
                        shape.set_texture('Diffuse', 'textures/shared.dds')
                    nif.save()
                shapes = [{'name': name, 'source_node': index, 'material_policy': material} for name, material in entries]
                components.append({'id': component, 'file': filename, 'shapes': shapes})
                if component == 'hair':
                    # Head-visibility variants inherit source ownership too.
                    (folder/'fixed_no_face.nif').write_bytes((folder/filename).read_bytes())
            (output/'appearance.json').write_text(json.dumps({'components': components}))
            for path in folder.glob('*.nif'):
                with NifFile(str(path)) as nif:
                    before[path.name] = {s.name: (s.verts, s.normals, s.uvs, s.tris) for s in nif.shapes}
            report = prepare_materials(output)
            self.assertEqual(report['authored_shapes'], 9)
            self.assertEqual(report['authored_face_shapes'], 1)
            self.assertEqual(validate_toon(output), 10)
            rows = {e['shape']: e for e in report['materials']}
            self.assertNotIn('profile', rows['Ordinary'])
            self.assertEqual(rows['Torso']['control'], rows['RetainedSkin']['control'])
            self.assertNotEqual(rows['Torso']['control'], rows['Clothing']['control'])
            self.assertEqual(rows['Underwear']['parameters']['gi_equalization'], .35)
            self.assertTrue(all(e.get('profile') == 'authored_material' for e in report['materials'] if e['shape'] != 'Ordinary'))
            # Reused DDS validation must not hide a conflicting source domain
            # on a later derived shape that shares the very same asset/hash.
            retained = rows['RetainedSkin']
            original_size = retained['source_size'][:]
            retained['source_size'] = [original_size[0]+1, original_size[1]]
            (output/'toon.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'source domain'):
                validate_toon(output)
            retained['source_size'] = original_size
            for path in folder.glob('*.nif'):
                with NifFile(str(path)) as nif:
                    for shape in nif.shapes:
                        for old, new in zip(before[path.name][shape.name], (shape.verts, shape.normals, shape.uvs, shape.tris)):
                            np.testing.assert_array_equal(old, new)
            # Old face reports retain their original meaning and remain readable.
            face = next(e for e in report['materials'] if e['shape'] == 'Face')
            face['profile'] = 'authored_face'
            (output/'toon.json').write_text(json.dumps(report))
            self.assertEqual(validate_toon(output), 10)
            hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.nif')}
            repeated = prepare_materials(output)
            self.assertEqual(repeated['authored_shapes'], 9)
            self.assertEqual(hashes, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.nif')})

    def test_source_rgb_and_resolution_retained_but_shade_alpha_is_not_opacity(self):
        doc, blob, material = fixture()
        image, key = shade_image(doc, blob, material)
        self.assertEqual(image.size, (64, 8))
        np.testing.assert_array_equal(np.asarray(image)[0, 0], [220, 180, 160, 255])
        self.assertEqual(len(key), 64)

    def test_missing_texture_is_white_before_authored_factor(self):
        material = {'extensions': {'VRMC_materials_mtoon': {'shadeColorFactor': [.5, .5, .5]}}}
        image, _ = shade_image({}, b'', material)
        self.assertEqual(image.getpixel((0, 0)), (188, 188, 188, 255))

    def test_authored_ramp_does_not_inherit_prototype_feather_cap(self):
        material = {'extensions': {'VRMC_materials_mtoon': {'shadingToonyFactor': 1.}}}
        self.assertEqual(parameters_for(material, authored=True)['toony'], 1.)
        self.assertEqual(parameters_for(material)['toony'], .98)

    def test_unsupported_coordinate_and_invalid_addressing_are_rejected(self):
        doc, blob, material = fixture()
        material['extensions']['VRMC_materials_mtoon']['shadeMultiplyTexture']['texCoord'] = 1
        with self.assertRaisesRegex(ValueError, 'UV0'):
            shade_image(doc, blob, material)
        material['extensions']['VRMC_materials_mtoon']['shadeMultiplyTexture']['texCoord'] = 0
        doc['samplers'] = [{'wrapT': 33071}]
        # An omitted sampler uses glTF defaults, not sampler index zero.
        self.assertEqual(shade_image(doc, blob, material)[0].size, (64, 8))
        doc['textures'][0]['sampler'] = 0
        self.assertEqual(shade_image(doc, blob, material)[0].info['wrap'], [10497, 33071])
        doc['samplers'][0]['wrapT'] = 123
        with self.assertRaisesRegex(ValueError, 'addressing'):
            shade_image(doc, blob, material)

    def test_vrm0_and_vrm1_ramps_have_the_same_endpoints(self):
        for low, toony in [(-.138000011, .757469237), (-.1, .8), (-1., 1.), (0., 0.), (.2, .7)]:
            doc = {'materials': [{}], 'extensions': {'VRM': {'materialProperties': [{
                'shader': 'VRM/MToon', 'floatProperties': {'_ShadeShift': low, '_ShadeToony': toony},
                'textureProperties': {'_ShadeTexture': 5}}]}}}
            normalize_material_colors(doc)
            m = doc['materials'][0]['extensions']['VRMC_materials_mtoon']
            width = 1-m['shadingToonyFactor']
            np.testing.assert_allclose([-m['shadingShiftFactor']-width, -m['shadingShiftFactor']+width],
                                       [low, 1+(low-1)*toony], atol=1e-7)
            self.assertEqual(m['shadeMultiplyTexture']['index'], 5)

    @unittest.skipUnless((ROOT/'dependencies/texconv.exe').exists(), 'Requires local BC7 compressor')
    def test_compressed_texture_metadata_and_completed_cache_are_verified(self):
        doc, blob, material = fixture()
        parameters = parameters_for(material, strength=0.)
        with tempfile.TemporaryDirectory() as temp:
            data, report = build_shade(temp, doc, blob, material, parameters)
            path = next((Path(temp)/'toon-shade-cache').glob('*.dds'))
            self.assertEqual(report['size'], [72, 20])
            validate_shade(path, parameters, report['size'], report['sha256'], report['source_size'], report['wrap'])
            self.assertEqual(build_shade(temp, doc, blob, material, parameters)[0], data)
            with Image.open(path) as image:
                decoded = np.asarray(image.convert('RGBA'))
            np.testing.assert_allclose(decoded[4, 4], [220, 180, 160, 255], atol=2)
            np.testing.assert_allclose(decoded[16, :60:4], metadata_pixels(parameters, [64, 8], [10497, 10497]), atol=1)
            path.write_bytes(data[:-1]+bytes([data[-1]^1]))
            with self.assertRaisesRegex(ValueError, 'DDS changed'):
                build_shade(temp, doc, blob, material, parameters)
