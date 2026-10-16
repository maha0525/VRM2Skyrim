"""Authored effect units, storage, ownership and repeat-safe native shells."""
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np
from PIL import Image

from nif_materials import normalize_material_colors
from toon import parameters_for
from toon_effects import effects_for, images_for, pack_material, effect_metadata, build_material, validate_material
from toon_outlines import width_for, create_hull, order_hulls, validate_hull, reset_originals, remember_prepared


def embedded(images, wraps=None):
    binary = b''
    doc = {'images': [], 'bufferViews': [], 'textures': [], 'samplers': []}
    for i, image in enumerate(images):
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        blob = stream.getvalue()
        doc['bufferViews'].append({'byteOffset': len(binary), 'byteLength': len(blob)})
        doc['images'].append({'bufferView': i})
        doc['textures'].append({'source': i, 'sampler': i})
        doc['samplers'].append(dict(zip(('wrapS', 'wrapT'), (wraps or [[10497]*2]*len(images))[i])))
        binary += blob
    return doc, binary


class EffectTests(unittest.TestCase):
    def test_legacy_migration_matches_univrm_units_colours_and_is_idempotent(self):
        doc = {'materials': [{}], 'extensions': {'VRM': {'materialProperties': [{
            'shader': 'VRM/MToon', 'vectorProperties': {'_RimColor': [.5, .25, 0, 1], '_OutlineColor': [.25]*4},
            'textureProperties': {'_SphereAdd': 2, '_RimTexture': 3, '_OutlineWidthTexture': 4, '_BumpMap': 5},
            'floatProperties': {'_OutlineWidthMode': 1, '_OutlineWidth': .06, '_BumpScale': .42,
                                '_RimFresnelPower': 7.2, '_RimLift': -.1, '_RimLightingMix': 0}}]}}}
        normalize_material_colors(doc)
        saved = copy.deepcopy(doc)
        normalize_material_colors(doc)
        self.assertEqual(saved, doc)
        material = doc['materials'][0]
        controls = material['extensions']['VRMC_materials_mtoon']
        self.assertAlmostEqual(controls['outlineWidthFactor'], .0006)
        np.testing.assert_allclose(controls['parametricRimColorFactor'], [.21404114, .05087609, 0])
        self.assertEqual(controls['rimLightingMixFactor'], 1)
        self.assertEqual(controls['matcapFactor'], [1]*3)
        self.assertEqual(material['normalTexture'], {'index': 5, 'scale': .42})

    def test_mixed_colour_and_linear_images_preserve_exact_domains_and_float_controls(self):
        source = [Image.new('RGBA', size, colour) for size, colour in [
            ((2, 2), (205, 175, 155, 255)), ((7, 5), (35, 75, 120, 255)),
            ((64, 8), (20, 80, 180, 255)), ((5, 7), (128, 190, 230, 255))]]
        doc, binary = embedded(source, [[33071, 33648]]*4)
        material = {'normalTexture': {'index': 3, 'scale': -.25}, 'extensions': {'VRMC_materials_mtoon': {
            'shadeMultiplyTexture': {'index': 0}, 'shadeColorFactor': [1]*3,
            'matcapTexture': {'index': 1}, 'matcapFactor': [1]*3, 'rimMultiplyTexture': {'index': 2},
            'parametricRimLiftFactor': -.1234567, 'parametricRimFresnelPowerFactor': 13.125}}}
        params, effects = parameters_for(material, authored=True), effects_for(material)
        images = images_for(doc, binary, material)
        atlas, rectangles = pack_material(images, params, effects)
        for original, rect in zip(source, rectangles):
            x, y, w, h, _, _ = rect
            np.testing.assert_array_equal(original, atlas.crop((x, y, x+w, y+h)))
        row = effect_metadata(params, rectangles, effects)
        self.assertEqual(struct.unpack('<f', bytes(row[i][3] for i in range(73, 77)))[0],
                         np.float32(-.1234567))
        with tempfile.TemporaryDirectory() as temp:
            data, report = build_material(temp, doc, binary, material, params)
            path = Path(temp)/'check.dds'
            path.write_bytes(data)
            validate_material(path, params, report)
            self.assertEqual(report['format'], 'R8G8B8A8_UNORM')
            invalid = copy.deepcopy(report)
            invalid['effects']['normal_scale'] = 2
            with self.assertRaisesRegex(ValueError, 'controls changed'):
                validate_material(path, params, invalid)

    def test_outline_width_uses_linear_green_and_metres(self):
        im = Image.new('RGBA', (2, 2), (255, 128, 0, 255))
        doc, binary = embedded([im], [[33071, 33071]])
        material = {'extensions': {'VRMC_materials_mtoon': {'outlineWidthMode': 'worldCoordinates',
            'outlineWidthFactor': .001, 'outlineWidthMultiplyTexture': {'index': 0}}}}
        np.testing.assert_allclose(width_for(doc, binary, material, [[.5, .5], [-1, 2]]), .07*128/255)
        material['extensions']['VRMC_materials_mtoon']['outlineWidthMode'] = 'screenCoordinates'
        with self.assertRaisesRegex(ValueError, 'runtime width pass'):
            width_for(doc, binary, material, [[0, 0]])

    def test_native_hull_keeps_binds_alpha_order_and_never_drives_physics(self):
        from custom_skeleton import NifFile, rigid_buffer
        from fsmp import weighted_points
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            path = output/'source.nif'
            with NifFile() as nif:
                nif.initialize('SKYRIMSE', str(path))
                shape = nif.createShapeFromData('Owner', [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
                    [(0, 1, 2)], [(0, 0), (1, 0), (0, 1)], [(0, 0, 1)]*3)
                shape.skin()
                shape.add_bone('NPC Root [Root]', rigid_buffer(np.eye(4)), None)
                shape.set_global_to_skin(rigid_buffer(np.eye(4)))
                shape.set_skin_to_bone_xform('NPC Root [Root]', rigid_buffer(np.eye(4)))
                shape.setShapeWeights('NPC Root [Root]', [(0, 1.), (1, 1.), (2, 1.)])
                shape.has_alpha_property = True
                shape.alpha_property.properties.flags = 4845
                shape.save_alpha_property()
                nif.save()
            original = path.read_bytes()
            reset_originals(output, [path])
            name = create_hull(path, 'Owner', [.1]*3, 'textures/marker.dds')
            with NifFile(str(path)) as nif:
                values = {s.name: s for s in nif.shapes}
                delta = np.asarray(values[name].verts)-np.asarray(values['Owner'].verts)
            entry = {'shape': name, 'source_shape': 'Owner',
                     'offset_sha256': hashlib.sha256(np.asarray(delta, dtype='<f4').tobytes()).hexdigest()}
            order_hulls(path, [entry])
            with NifFile(str(path)) as nif:
                validate_hull(nif, entry)
                self.assertEqual(len(weighted_points(nif)['NPC Root [Root]']), 3)
            remember_prepared(output, [path])
            reset_originals(output, [path])
            self.assertEqual(path.read_bytes(), original)
            state = json.loads((output/'toon-originals/state.json').read_text())
            self.assertIn('prepared', state[path.name])
