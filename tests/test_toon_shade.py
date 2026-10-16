"""Authored shade data must survive the native texture format and reuse path."""
import io
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from nif_materials import normalize_material_colors
from toon import parameters_for
from toon_shade import ROOT, build_shade, metadata_pixels, shade_image, validate_shade


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

    def test_unsupported_coordinate_and_addressing_are_rejected(self):
        doc, blob, material = fixture()
        material['extensions']['VRMC_materials_mtoon']['shadeMultiplyTexture']['texCoord'] = 1
        with self.assertRaisesRegex(ValueError, 'UV0'):
            shade_image(doc, blob, material)
        material['extensions']['VRMC_materials_mtoon']['shadeMultiplyTexture']['texCoord'] = 0
        doc['samplers'] = [{'wrapT': 33071}]
        # An omitted sampler uses glTF defaults, not sampler index zero.
        self.assertEqual(shade_image(doc, blob, material)[0].size, (64, 8))
        doc['textures'][0]['sampler'] = 0
        with self.assertRaisesRegex(ValueError, 'repeat'):
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
            self.assertEqual(report['size'], [64, 20])
            validate_shade(path, parameters, report['size'], report['sha256'])
            self.assertEqual(build_shade(temp, doc, blob, material, parameters)[0], data)
            with Image.open(path) as image:
                decoded = np.asarray(image.convert('RGBA'))
            np.testing.assert_allclose(decoded[0, 0], [220, 180, 160, 255], atol=2)
            np.testing.assert_allclose(decoded[16, :36:4], metadata_pixels(parameters), atol=1)
            path.write_bytes(data[:-1]+bytes([data[-1]^1]))
            with self.assertRaisesRegex(ValueError, 'DDS changed'):
                build_shade(temp, doc, blob, material, parameters)
