"""Original GLB weapon: settings, kind catalog, placement, textures, records and NIF readback."""
from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image

from environment import find_game
from game_catalog import ORIGINAL_WEAPON_KINDS, weapon_kind
from inspect_vrm import write_glb
from plugin import Record, records
from settings import FollowerSettings, WEAPON_KINDS
import weapon
from weapon_nif import HULL_COVERAGE, MAX_HULL_VERTICES, hull, placement

ROOT = Path(__file__).resolve().parents[1]
SHA = 'a' * 64
NIFLY = os.name == 'nt' and (ROOT / 'dependencies/io_scene_nifly/NiflyDLL.dll').is_file()


def original(**changes):
    return {'sha256': SHA, 'filename': 'staff.glb', 'kind': 'staff', 'base': 'StaffFlames', 'name': '三日月の杖',
            'grip': .44, 'length': 120.7, 'flip': False, 'roll': 0, **changes}


def text(value):
    return value.encode('utf8') + b'\0'


def dnam(animation, flags=0):
    data = bytearray(100)
    data[0] = animation
    struct.pack_into('<H', data, 12, flags)
    return bytes(data)


def weap(animation=8, flags=0, record_flags=0, named=True):
    fields = [(b'EDID', text('BaseStaff')), (b'OBND', bytes(12))]
    if named:
        fields.append((b'FULL', struct.pack('<I', 0x1234)))
    fields += [(b'MODL', text('Weapons\\Staff01\\Staff01.nif')), (b'MODT', bytes(24)), (b'EITM', struct.pack('<I', 0x4DEE5)),
               (b'EAMT', struct.pack('<H', 500)), (b'KSIZ', struct.pack('<I', 1)), (b'KWDA', struct.pack('<I', 0x1E718)),
               (b'DESC', struct.pack('<I', 0)), (b'WNAM', struct.pack('<I', 0x29B80)), (b'DATA', struct.pack('<IfH', 5, 8., 0)),
               (b'DNAM', dnam(animation, flags)), (b'CRDT', bytes(24)), (b'VNAM', struct.pack('<I', 1)),
               (b'CNAM', struct.pack('<I', 0xBE11F))]
    return Record(b'WEAP', 0x4DEE0, record_flags, fields)


def stat():
    return Record(b'STAT', 0x29B80, 0, [(b'EDID', text('1stPersonStaff')), (b'OBND', bytes(12)),
                                        (b'MODL', text('Weapons\\Staff01\\1stPersonStaff01.nif')),
                                        (b'MODT', bytes(12)), (b'DNAM', bytes(8))])


class SettingsTests(unittest.TestCase):
    def test_old_settings_load_as_official_and_original_roundtrips(self):
        legacy = {k: v for k, v in asdict(FollowerSettings()).items() if k not in ('weapon_mode', 'original_weapon')}
        loaded = FollowerSettings.from_dict(legacy)
        self.assertEqual((loaded.weapon_mode, loaded.original_weapon), ('official', {}))
        settings = FollowerSettings(weapon_mode='original', original_weapon=original())
        with tempfile.TemporaryDirectory() as directory:
            settings.save(Path(directory) / 'settings.json')
            self.assertEqual(FollowerSettings.load(Path(directory) / 'settings.json'), settings)
        # Switching back keeps both selections; only the mode decides what is given.
        self.assertEqual(FollowerSettings(weapon_mode='official', original_weapon=original()).weapon, 'SteelSword')

    def test_invalid_original_weapon_is_rejected(self):
        invalid = [original(grip=0), original(grip=1), original(length=0), original(length=float('inf')),
                   original(roll=360), original(roll=-1), original(flip=1), original(sha256='A' * 64),
                   original(kind='bow'), original(name=''), original(name='a\nb'), original(base='Steel Sword'),
                   {k: v for k, v in original().items() if k != 'roll'}, {**original(), 'extra': 1}]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                FollowerSettings(weapon_mode='original', original_weapon=value)
        for mode, value in (('original', {}), ('custom', original()), ('official', [])):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                FollowerSettings(weapon_mode=mode, original_weapon=value)


class KindTests(unittest.TestCase):
    def test_kind_table_matches_settings(self):
        self.assertEqual(tuple(ORIGINAL_WEAPON_KINDS), WEAPON_KINDS)

    def test_animation_type_and_keyword_pairs(self):
        self.assertEqual(weapon_kind(weap(8), ['WeapTypeStaff']), 'staff')
        self.assertEqual(weapon_kind(weap(6), ['WeapTypeBattleaxe', 'VendorItemWeapon']), 'battleaxe')
        self.assertEqual(weapon_kind(weap(6), ['WeapTypeWarhammer']), 'warhammer')
        self.assertEqual(weapon_kind(weap(1), ['WeapTypeSword']), 'sword')
        for record, keywords in ((weap(1), ['WeapTypeStaff']), (weap(5), ['WeapTypeSword']), (weap(7), ['WeapTypeBow']),
                                 (weap(8), ['WeapTypeStaff', 'WeapTypeSword']), (weap(8), []),
                                 (weap(8, record_flags=4), ['WeapTypeStaff']), (weap(8, flags=0x80), ['WeapTypeStaff']),
                                 (weap(8, named=False), ['WeapTypeStaff'])):
            with self.subTest(keywords=keywords):
                self.assertIsNone(weapon_kind(record, keywords))
        scripted = weap(8)
        scripted.fields.insert(1, (b'VMAD', bytes(6)))
        self.assertIsNone(weapon_kind(scripted, ['WeapTypeStaff']))


class CatalogTests(unittest.TestCase):
    def test_update_overrides_apply_unless_they_need_update_records(self):
        from game_catalog import update_overrides
        from plugin import write_plugin
        base = {0x4DEE0: weap(), 0x29B80: stat()}

        def override(**fields):
            record = weap()
            for tag, value in fields.items():
                record.replace(tag.encode(), value)
            return record
        cases = {'sounds': (override(NAM8=struct.pack('<I', 0x3CEDB)), False),
                 'update record': (override(NAM9=struct.pack('<I', 0x01002E34)), True),
                 'update keyword': (override(KWDA=struct.pack('<II', 0x1E718, 0x01000F00)), True),
                 'critical spell': (override(CRDT=bytes(16) + struct.pack('<I', 0x01000123) + bytes(4)), True),
                 'unknown field': (override(ZZZZ=b'x'), True),
                 'name string': (override(FULL=struct.pack('<I', 0x9999)), True)}
        material = stat()
        material.replace(b'DNAM', struct.pack('<fI', 90, 0x01000ABC))
        with tempfile.TemporaryDirectory() as directory:
            for name, (record, refused) in cases.items():
                with self.subTest(case=name):
                    path = Path(directory) / f'{name}.esm'
                    added = Record(b'WEAP', 0x01000900, 0, [(b'EDID', text('NewInUpdate'))])
                    write_plugin(path, [record, added], masters=('Skyrim.esm',))
                    overrides, rejected = update_overrides(path, base)
                    self.assertEqual(set(overrides), {0x4DEE0})  # new Update.esm records are not overrides
                    self.assertEqual(overrides[0x4DEE0].fields, record.fields)
                    self.assertEqual(rejected, {0x4DEE0} if refused else set())
            path = Path(directory) / 'stat.esm'
            write_plugin(path, [material], masters=('Skyrim.esm',))
            self.assertEqual(update_overrides(path, base)[1], {0x29B80})
            write_plugin(path, [weap()], masters=('Dawnguard.esm',))
            with self.assertRaisesRegex(ValueError, 'masters'):
                update_overrides(path, base)

    def test_refused_overrides_are_not_bases_and_missing_defaults_fall_back(self):
        from types import SimpleNamespace
        from game_catalog import GameCatalog
        static = stat()
        catalog = SimpleNamespace(update_refused=set(), first_person_static=lambda record: static,
                                  keyword_names=lambda record: ['WeapTypeStaff'])
        self.assertEqual(GameCatalog.original_weapon_kind(catalog, weap()), 'staff')
        catalog.update_refused = {weap().form_id}
        self.assertIsNone(GameCatalog.original_weapon_kind(catalog, weap()))
        catalog.update_refused = {static.form_id}
        self.assertIsNone(GameCatalog.original_weapon_kind(catalog, weap()))
        # A missing default base (here StaffFlames) keeps the kind with its first candidate.
        other = weap()
        catalog = SimpleNamespace(choices=lambda kind: [other], label=lambda record: 'Staff',
                                  localized=lambda record: {'ja': 'Staff', 'en': 'Staff'},
                                  original_weapon_kind=lambda record: 'staff')
        with self.assertLogs(level='WARNING') as logs:
            choices = GameCatalog.original_weapon_choices(catalog)
        self.assertEqual([(c['id'], c['default']) for c in choices], [('staff', 'BaseStaff')])
        self.assertTrue(any('StaffFlames' in line for line in logs.output))


class GeometryTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(3)
        self.points = rng.normal(size=(400, 3)) * [.4, .03, .05] + [.4, 0, 0]  # long along glTF X

    def apply(self, matrix, points):
        return points @ matrix[:3, :3].T + matrix[:3, 3]

    def test_longest_axis_becomes_y_with_low_end_at_the_bottom(self):
        matrix = placement(self.points, .25, 80)
        placed = self.apply(matrix, self.points)
        self.assertAlmostEqual(np.ptp(placed[:, 1]), 80, places=6)
        self.assertAlmostEqual(placed[:, 1].min(), -.25 * 80, places=6)
        self.assertGreater(np.linalg.det(matrix[:3, :3]), 0)
        self.assertEqual(int(np.argmin(placed[:, 1])), int(np.argmin(self.points[:, 0])))
        flipped = self.apply(placement(self.points, .25, 80, flip=True), self.points)
        self.assertEqual(int(np.argmax(flipped[:, 1])), int(np.argmin(self.points[:, 0])))
        self.assertAlmostEqual(flipped[:, 1].min(), -20, places=6)

    def test_roll_turns_around_y_and_grip_slice_is_centred(self):
        rolled = self.apply(placement(self.points, .5, 100, roll=90), self.points)
        plain = self.apply(placement(self.points, .5, 100), self.points)
        np.testing.assert_allclose(rolled[:, 1], plain[:, 1], atol=1e-9)
        near = plain[np.abs(plain[:, 1]) <= 2]
        np.testing.assert_allclose((near.min(0) + near.max(0))[[0, 2]] / 2, 0, atol=1e-9)
        for invalid in ((0, 10), (1, 10), (.5, 0)):
            with self.assertRaises(ValueError):
                placement(self.points, *invalid)
        with self.assertRaises(ValueError):
            placement(np.zeros((4, 3)), .5, 10)

    def test_hull_is_small_and_contains_every_vertex(self):
        cloud = self.points * 100
        points, planes = hull(cloud)
        self.assertLessEqual(len(points), MAX_HULL_VERTICES)
        size = np.ptp(cloud, axis=0).max()
        self.assertLessEqual((cloud @ planes[:, :3].T - planes[:, 3]).max(), HULL_COVERAGE * size + 1e-9)
        # Every hull vertex is a vertex of the source and lies on the hull surface.
        self.assertTrue(all(np.any(np.all(cloud == p, axis=1)) for p in points))
        self.assertTrue(np.all(np.abs(points @ planes[:, :3].T - planes[:, 3]).min(1) <= 1e-6 * size))
        np.testing.assert_allclose(np.linalg.norm(planes[:, :3], axis=1), 1)
        np.testing.assert_allclose(points.min(0), (self.points * 100).min(0))
        np.testing.assert_allclose(points.max(0), (self.points * 100).max(0))
        box = np.array([[x, y, z] for x in (0, 1) for y in (0, 10) for z in (0, 2)], float)
        corners, faces = hull(box)
        self.assertEqual((len(corners), len(faces)), (8, 6))

    def test_hull_centre_of_mass_and_box_inertia(self):
        from weapon_nif import hull_mass
        box = np.array([[x, y, z] for x in (0, 1) for y in (0, 10) for z in (0, 2)], float)
        centre, inertia = hull_mass(*hull(box))
        np.testing.assert_allclose(centre, [.5, 5, 1], atol=1e-9)
        np.testing.assert_allclose(inertia, [(100 + 4) / 12, (1 + 4) / 12, (1 + 100) / 12])
        # A wedge (tetrahedron) has its volume centroid at the vertex mean, not the box centre.
        wedge = np.array([[0, 0, 0], [4, 0, 0], [0, 4, 0], [0, 0, 4]], float)
        np.testing.assert_allclose(hull_mass(*hull(wedge))[0], [1, 1, 1], atol=1e-9)


def png(image):
    stream = io.BytesIO()
    image.save(stream, 'PNG')
    return stream.getvalue()


def glb_document(materials, images):
    binary, views = b'', []
    for blob in images:
        views.append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(blob)})
        binary += blob + b'\0' * (-len(blob) % 4)
    primitives = [{'attributes': {'POSITION': 0}, 'indices': 1, **({'material': i} if i is not None else {})}
                  for i in range(len(materials))]
    document = {'asset': {'version': '2.0'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
                'nodes': [{'mesh': 0}], 'meshes': [{'primitives': primitives}],
                'accessors': [{'count': 3, 'type': 'VEC3', 'componentType': 5126}, {'count': 3, 'type': 'SCALAR', 'componentType': 5125}],
                'materials': materials, 'textures': [{'source': i} for i in range(len(images))],
                'images': [{'bufferView': i, 'mimeType': 'image/png'} for i in range(len(images))],
                'bufferViews': views, 'buffers': [{'byteLength': len(binary)}]}
    return document, binary


def two_material_glb(path, nodes=False, mirror=False):
    """A real GLB: textured shaft (material 0) and untextured solid red head (material 1), Y up;
    nodes=True gives each its own node and mesh, the head node rotated (mirror=True: also scaled -1 on X)."""
    binary, views, accessors, primitives = bytearray(), [], [], []

    def add(array, kind, component):
        data = np.ascontiguousarray(array).tobytes()
        binary.extend(b'\0' * (-len(binary) % 4))
        views.append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(data)})
        binary.extend(data)
        accessors.append({'bufferView': len(views) - 1, 'componentType': component, 'count': len(array), 'type': kind,
                          **({'min': array.min(0).tolist(), 'max': array.max(0).tolist()} if kind == 'VEC3' else {})})
        return len(accessors) - 1
    for material, (low, high) in enumerate((((-.02, 0, -.02), (.02, .8, .02)), ((-.08, .8, -.03), (.08, 1., .03)))):
        positions, normals, uvs, indices = [], [], [], []
        for axis in range(3):
            for sign in (0, 1):
                u, v = (axis + 1) % 3, (axis + 2) % 3
                for a, b in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    point = list(low)
                    point[axis] = (low, high)[sign][axis]
                    point[u], point[v] = (low[u], high[u])[a], (low[v], high[v])[b]
                    positions.append(point)
                    normals.append([(1 if sign else -1) if i == axis else 0 for i in range(3)])
                    uvs.append((a, b))
                quad = [(0, 1, 2), (0, 2, 3)] if sign else [(0, 2, 1), (0, 3, 2)]
                indices += [len(positions) - 4 + i for tri in quad for i in tri]
        primitives.append({'attributes': {'POSITION': add(np.array(positions, np.float32), 'VEC3', 5126),
                                          'NORMAL': add(np.array(normals, np.float32), 'VEC3', 5126),
                                          'TEXCOORD_0': add(np.array(uvs, np.float32), 'VEC2', 5126)},
                           'indices': add(np.array(indices, np.uint32), 'SCALAR', 5125), 'material': material})
    image = png(Image.new('RGBA', (16, 16), (200, 170, 60, 255)))
    binary.extend(b'\0' * (-len(binary) % 4))
    views.append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(image)})
    binary.extend(image)
    if nodes:
        head = {'mesh': 1, 'rotation': [0, .3826834, 0, .9238795], **({'scale': [-1, 1, 1]} if mirror else {})}
        scene = {'nodes': [{'mesh': 0}, head],
                 'meshes': [{'primitives': primitives[:1]}, {'primitives': primitives[1:]}], 'scenes': [{'nodes': [0, 1]}]}
    else:
        scene = {'nodes': [{'mesh': 0}], 'meshes': [{'primitives': primitives}], 'scenes': [{'nodes': [0]}]}
    write_glb(path, {'asset': {'version': '2.0'}, 'scene': 0, **scene, 'accessors': accessors, 'bufferViews': views,
                     'buffers': [{'byteLength': len(binary)}], 'textures': [{'source': 0}],
                     'images': [{'bufferView': len(views) - 1, 'mimeType': 'image/png'}],
                     'materials': [{'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}, 'metallicFactor': 0}},
                                   {'pbrMetallicRoughness': {'baseColorFactor': [.9, .1, .1, 1], 'metallicFactor': 0}}]},
              bytes(binary))


class TextureTests(unittest.TestCase):
    def build(self, metal_value, normal_green=40, materials=None, size=(8, 8)):
        base = Image.new('RGBA', size, (200, 100, 50, 255))
        packed = Image.new('RGB', size, (0, 64, metal_value))  # glTF: G roughness, B metallic
        normal = Image.new('RGB', size, (120, normal_green, 250))
        material = {'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}, 'metallicRoughnessTexture': {'index': 1},
                                             'baseColorFactor': [.8, .8, .8, 1], 'roughnessFactor': .5},
                    'normalTexture': {'index': 2}}
        return glb_document(materials or [material], [png(base), png(packed), png(normal)])

    def prepare(self, document, binary):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        output = Path(directory.name)
        return output, weapon.prepare_textures(document, binary, output, FollowerSettings(mod_name='Probe'))

    def test_pbr_maps_become_skyrim_maps(self):
        output, (manifest, materials, policies, coverage) = self.prepare(*self.build(255))
        self.assertEqual([Path(e['relative']).name for e in manifest], ['weapon.dds', 'weapon_n.dds', 'weapon_m.dds'])
        self.assertEqual(manifest[0]['base_color_factor'], [.8, .8, .8])
        self.assertTrue(manifest[1]['normal'])
        self.assertIs(manifest[2]['srgb'], False)
        normal = Image.open(manifest[1]['png'])
        # Green unchanged; alpha = 1 - roughness = 1 - 64/255 * .5.
        self.assertEqual(normal.getpixel((0, 0)), (120, 40, 250, round((1 - 64 / 255 * .5) * 255)))
        self.assertEqual(Image.open(manifest[2]['png']).getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(Image.open(manifest[0]['png']).getpixel((0, 0)), (200, 100, 50, 255))
        shader = materials['V2SWeaponMaterial_00000']
        self.assertTrue(shader['metal'])
        self.assertEqual(shader['textures']['EnvMap'], 'textures\\cubemaps\\ShinyDull_e.dds')
        self.assertEqual(shader['textures']['Normal'], 'textures\\vrm2skyrim\\probe\\weapon_n.dds')
        self.assertEqual(coverage['V2SWeaponMaterial_00000'], 1)
        self.assertEqual(json.loads((output / 'weapon-textures.json').read_text(encoding='utf8')), manifest)

    def test_metal_mask_threshold_and_green_switch(self):
        _, (manifest, materials, _, _) = self.prepare(*self.build(100))  # metallic .39 < .5
        self.assertEqual(len(manifest), 2)
        self.assertFalse(materials['V2SWeaponMaterial_00000']['metal'])
        self.assertNotIn('EnvMap', materials['V2SWeaponMaterial_00000']['textures'])
        with mock.patch.object(weapon, 'FLIP_NORMAL_GREEN', True):
            _, (manifest, _, _, _) = self.prepare(*self.build(100))
        self.assertEqual(Image.open(manifest[1]['png']).getpixel((0, 0))[1], 255 - 40)

    def test_metal_coverage_needs_one_percent(self):
        size = (20, 10)
        for metal_pixels, expected in ((1, False), (2, True)):
            document, binary = self.build(0, size=size)
            packed = Image.new('RGB', size, (0, 64, 0))
            for x in range(metal_pixels):
                packed.putpixel((x, 0), (0, 64, 255))
            document, binary = glb_document(document['materials'], [png(Image.new('RGBA', size)), png(packed), png(Image.new('RGB', size))])
            with self.subTest(metal_pixels=metal_pixels):
                _, (_, materials, _, _) = self.prepare(document, binary)
                self.assertIs(materials['V2SWeaponMaterial_00000']['metal'], expected)

    def test_multiple_materials_use_material_numbers_and_defaults(self):
        materials = [{'pbrMetallicRoughness': {'baseColorFactor': [1, 0, 0, 1], 'metallicFactor': 0}},
                     {'alphaMode': 'MASK', 'alphaCutoff': .3, 'doubleSided': True,
                      'pbrMetallicRoughness': {'baseColorFactor': [0, 0, 1, .5]}}]
        document, binary = glb_document(materials, [])
        _, (manifest, shaders, policies, _) = self.prepare(document, binary)
        self.assertEqual([Path(e['relative']).name for e in manifest],
                         ['weapon_0.dds', 'weapon_0_n.dds', 'weapon_1.dds', 'weapon_1_n.dds', 'weapon_1_m.dds'])
        self.assertEqual(Image.open(manifest[0]['png']).getpixel((0, 0)), (255, 0, 0, 255))
        # The alpha factor .5 is applied once, by the shader: the solid texture stays opaque.
        self.assertEqual(Image.open(manifest[2]['png']).getpixel((0, 0))[3], 255)
        self.assertEqual(manifest[0]['base_color_factor'], [1, 1, 1])  # solid colour is already tinted
        # glTF defaults: metallic 1, roughness 1 (alpha 0).
        self.assertEqual(Image.open(manifest[3]['png']).getpixel((0, 0)), (128, 128, 255, 0))
        self.assertEqual(shaders['V2SWeaponMaterial_00001']['alpha'], .5)
        self.assertTrue(shaders['V2SWeaponMaterial_00001']['double_sided'])
        self.assertEqual(policies['V2SWeaponMaterial_00001'], {'alphaMode': 'MASK', 'alphaCutoff': .3, 'doubleSided': True})

    def test_unsupported_texture_coordinates_are_rejected(self):
        document, binary = self.build(255)
        document['materials'][0]['normalTexture']['texCoord'] = 1
        with self.assertRaisesRegex(ValueError, 'TEXCOORD_0'):
            self.prepare(document, binary)

    def test_mask_is_converted_without_srgb(self):
        from textures import convert_textures
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            FollowerSettings(mod_name='Probe').save(output / 'settings.json')
            Image.new('RGBA', (4, 4)).save(output / 'weapon_m.png')
            Image.new('RGBA', (4, 4)).save(output / 'weapon.png')
            (output / 'weapon-textures.json').write_text(json.dumps([
                {'png': str(output / 'weapon_m.png'), 'relative': 'textures/a/weapon_m.dds', 'srgb': False},
                {'png': str(output / 'weapon.png'), 'relative': 'textures/a/weapon.dds'}]), encoding='utf8')
            commands = []

            def run(command, **_):
                commands.append(command)
                destination = Path(command[command.index('-o') + 1]) / (Path(command[-1]).stem + '.dds')
                destination.write_bytes(b'')
                return mock.Mock(returncode=0)
            with mock.patch('textures.subprocess.run', run), mock.patch('textures.validate_dds'):
                convert_textures(output, 'weapon-textures.json')
            self.assertEqual(['-srgb' in c for c in commands], [False, True])
            self.assertFalse((output / 'texture-sources').exists())  # avatar flat_n is not added


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.settings = FollowerSettings(mod_name='Probe', weapon_mode='original', original_weapon=original())

    def records(self):
        return weapon.weapon_records(self.settings, weap(), stat(), 'A plain staff.', [[-3.2, -53.1, -2], [3.9, 67.6, 2.5]])

    def test_copy_replaces_only_model_identity_fields(self):
        item, first_person = self.records()
        self.assertEqual((item.form_id, first_person.form_id), (0x010008D0, 0x010008D1))
        self.assertEqual(item.editor_id, 'V2S_ProbeOriginalWeapon')
        self.assertEqual(first_person.editor_id, 'V2S_ProbeOriginalWeapon1stPerson')
        path = text('vrm2skyrim\\probe\\weapon.nif')
        self.assertEqual(item.values(b'MODL'), [path])
        self.assertEqual(first_person.values(b'MODL'), [path])
        self.assertEqual(item.values(b'FULL'), [text('三日月の杖')])
        self.assertEqual(item.values(b'DESC'), [text('A plain staff.')])
        self.assertEqual(item.values(b'WNAM'), [struct.pack('<I', 0x010008D1)])
        self.assertEqual(struct.unpack('<6h', item.values(b'OBND')[0]), (-4, -54, -2, 4, 68, 3))
        self.assertEqual(item.values(b'OBND'), first_person.values(b'OBND'))
        self.assertFalse(item.values(b'MODT') or item.values(b'CNAM') or first_person.values(b'MODT'))
        kept = [f for f in weap().fields if f[0] not in weapon.CHANGED_FIELDS]
        self.assertEqual([f for f in item.fields if f[0] not in weapon.CHANGED_FIELDS], kept)
        self.assertEqual(first_person.values(b'DNAM'), [bytes(8)])
        weapon.check_copied(self.records(), weap(), stat())
        self.assertEqual(weap().values(b'MODL'), [text('Weapons\\Staff01\\Staff01.nif')])  # source untouched

    def test_dlc_masters_keep_first_person_reference_private(self):
        from follower_plugin import follower_records, write_follower
        npc = Record(b'NPC_', 0x01000800, 0, [(b'EDID', text('V2S_ProbeNPC')),
                                              (b'CNTO', struct.pack('<Ii', 0x010008D0, 1))])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'Probe.esp'
            cell = Record(b'CELL', 0x165A7, 0, [(b'EDID', text('Temple'))], ((b'\0' * 4, 0), (b'\0' * 4, 2), (b'\0' * 4, 3)))
            actor = Record(b'ACHR', 0x01000806, 0x400, [(b'NAME', struct.pack('<I', 0x01000800))])
            write_follower(path, [npc, *self.records()], author='test', placement=(cell, actor),
                           extra_masters=['Dawnguard.esm'])
            raw = {r.kind: r for r in records(path)}
            self.assertEqual(raw[b'WEAP'].values(b'WNAM'), [struct.pack('<I', 0x020008D1)])
            self.assertEqual(raw[b'WEAP'].form_id, 0x020008D0)
            self.assertEqual(raw[b'WEAP'].values(b'MODL'), [text('vrm2skyrim\\probe\\weapon.nif')])
            generated = follower_records(path)
        report = {'description': 'A plain staff.', 'official_weapon_form_id': 0x12EB7}
        self.assertEqual(weapon.validate_weapon_records(generated, self.settings, report)['first_person'], '0x10008d1')

    def test_record_contract_rejections(self):
        npc = Record(b'NPC_', 0x01000800, 0, [(b'CNTO', struct.pack('<Ii', 0x010008D0, 1))])
        generated = [npc, *self.records()]
        weapon.validate_weapon_records(generated, self.settings)
        cases = []
        missing = [Record(b'NPC_', npc.form_id, 0, []), *self.records()]
        cases.append(missing)
        wrong_model = [npc, *self.records()]
        wrong_model[2].replace(b'MODL', text('other.nif'))
        cases.append(wrong_model)
        official_kept = [Record(b'NPC_', 0x01000800, 0, [(b'CNTO', struct.pack('<Ii', 0x010008D0, 1)),
                                                         (b'CNTO', struct.pack('<Ii', 0x12EB7, 1))]), *self.records()]
        for case in cases:
            with self.assertRaises(ValueError):
                weapon.validate_weapon_records(case, self.settings)
        with self.assertRaisesRegex(ValueError, 'Official starting weapon'):
            weapon.validate_weapon_records(official_kept, self.settings, {'official_weapon_form_id': 0x12EB7,
                                                                          'description': 'A plain staff.'})
        with self.assertRaisesRegex(ValueError, 'inline string'):
            weapon.validate_weapon_records(generated, self.settings, {'description': 'other'})
        with self.assertRaisesRegex(ValueError, 'Official weapon mode'):
            weapon.validate_weapon_records(generated, FollowerSettings(mod_name='Probe'))
        self.assertIsNone(weapon.validate_weapon_records([npc], FollowerSettings(mod_name='Probe')))

    def test_bounds_match_the_measured_nif_with_the_writer_rounding(self):
        generated = self.records()
        weapon.check_bounds(generated, [[-3.2, -53.1, -2], [3.9, 67.6, 2.5]])
        weapon.check_bounds(generated, [[-3.9, -53.9, -1.1], [3.1, 67.1, 2.1]])  # same floor/ceil
        for bounds in ([[-3.2, -54.1, -2], [3.9, 67.6, 2.5]], [[-3.2, -53.1, -2], [3.9, 68.2, 2.5]]):
            with self.subTest(bounds=bounds), self.assertRaisesRegex(ValueError, 'OBND'):
                weapon.check_bounds(generated, bounds)
        stale = self.records()
        stale[1].replace(b'OBND', struct.pack('<6h', -4, -54, -2, 4, 70, 3))
        with self.assertRaisesRegex(ValueError, 'OBND'):
            weapon.check_bounds(stale, [[-3.2, -53.1, -2], [3.9, 67.6, 2.5]])

    def test_copy_check_uses_the_overridden_record(self):
        updated = weap()
        updated.replace(b'DNAM', dnam(8, 0x40))
        records_ = weapon.weapon_records(self.settings, updated, stat(), 'A plain staff.', [[0, 0, 0], [1, 1, 1]])
        weapon.check_copied(records_, updated, stat())
        with self.assertRaisesRegex(ValueError, 'differs from its official source'):
            weapon.check_copied(records_, weap(), stat())

    def test_readme_mentions_the_environment_map_only_when_used(self):
        with tempfile.TemporaryDirectory() as directory:
            for shared, expected in (({}, False), ({weapon.ENVIRONMENT_MAP: {'path': weapon.ENVIRONMENT_MAP}}, True)):
                with self.subTest(shared=bool(shared)), mock.patch.object(weapon, 'validate_shared', return_value=shared):
                    text_ = weapon.readme_text(directory, self.settings)
                    self.assertIn('三日月の杖', text_)
                    self.assertEqual('ShinyDull_e.dds' in text_, expected)


class SourceTests(unittest.TestCase):
    def test_glb_fingerprint_must_match_settings(self):
        document, binary = glb_document([{}], [])
        with tempfile.TemporaryDirectory() as directory:
            glb = Path(directory) / 'staff.glb'
            write_glb(glb, document, binary)
            settings = FollowerSettings(weapon_mode='original', original_weapon=original())
            with self.assertRaisesRegex(ValueError, 'GLB'):
                weapon.convert_weapon(glb, directory, None, Path(directory) / 'out', settings, None)
            summary = weapon.inspect_glb(glb)
            self.assertEqual((summary['triangles'], summary['vertices'], summary['materials']), (1, 3, 1))

    def test_malformed_glb_json_is_a_value_error(self):
        document, binary = glb_document([{}], [])
        broken = {'array document': [], 'string accessors': {**document, 'accessors': 'x'},
                  'accessor view': {**document, 'accessors': [{'count': 3, 'bufferView': 4}, document['accessors'][1]]},
                  'node mesh': {**document, 'nodes': [{'mesh': 2}]}, 'scene node': {**document, 'scenes': [{'nodes': [3]}]},
                  'primitive list': {**document, 'meshes': [{'primitives': {}}]},
                  'material texture': {**document, 'materials': [{'normalTexture': {'index': 0}}]},
                  'count': {**document, 'accessors': [{'count': '3'}, document['accessors'][1]]}}
        with tempfile.TemporaryDirectory() as directory:
            for name, value in broken.items():
                with self.subTest(case=name):
                    path = Path(directory) / 'broken.glb'
                    write_glb(path, value, binary)
                    with self.assertRaises(ValueError):
                        weapon.inspect_glb(path)

    def test_weapon_glb_is_refused_for_official_settings(self):
        import converter
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'a.vrm'
            source.write_bytes(b'vrm')
            with mock.patch.object(converter, 'doctor', return_value={'ready': True}), \
                    self.assertRaisesRegex(ValueError, '--weapon-glb'):
                converter.convert(source, directory, directory, Path(directory) / 'out', FollowerSettings(),
                                  weapon_glb=Path(directory) / 'staff.glb')
            self.assertFalse((Path(directory) / 'out').exists())


def base_nif(path, mass=9., transformed=False, listed=False, lit=True):
    """Official-like weapon NIF. transformed: bhkRigidBodyT moving its shape (EbonySword-like);
    listed: bhkListShape of a box (SteelDagger-like); lit=False: effect shader only."""
    from pyn.nifdefs import (PynBufferTypes, bhkConvexTransformShapeProps, bhkConvexVerticesShapeProps,
                             bhkListShapeProps, bhkRigidBodyProps)
    from pyn.pynifly import BSEffectShaderProperty, BSTriShape, BSXFlags, NifFile, NiStringExtraData
    nif = NifFile()
    nif.initialize('SKYRIMSE', str(path), root_type='BSFadeNode', root_name='Base')
    BSXFlags.New(nif, flags=194, parent=nif.rootNode)
    NiStringExtraData.New(nif, name='Prn', string_value='WeaponStaff', parent=nif.rootNode)
    nif.createShapeFromData('Base:0', [(0, -40, 0), (1, 80, 0), (0, 0, 1)], [(0, 1, 2)], [(0, 0)] * 3, [(0, 0, 1)] * 3,
                            props=BSTriShape.getbuf(), parent=nif.rootNode)
    if lit:
        nif.shapes[0].shader.properties.bufType = PynBufferTypes.BSLightingShaderPropertyBufType
    else:
        nif.shapes[0].shader._properties = BSEffectShaderProperty.getbuf()
    nif.shapes[0].save_shader_attributes()
    collision = nif.rootNode.add_collision(None, flags=129, collision_type=PynBufferTypes.bhkCollisionObjectBufType)
    body = bhkRigidBodyProps()
    body.mass, body.collisionFilter_layer, body.motionSystem, body.qualityType = mass, 5, 3, 4
    body.friction, body.restitution, body.penetrationDepth = .3, .2, .05
    if transformed:
        body.bufType = PynBufferTypes.bhkRigidBodyTBufType
        body.translation[:] = (0, .414, 0, 0)
        body.rotation[:] = (.7071068, 0, 0, .7071068)
        body.center[:] = (0, 3, 0, 0)
    rigid = collision.add_body(body)
    if listed:
        props = bhkListShapeProps(game='SKYRIMSE')
        props.bhkMaterial = 2617944780
        listed_shape = nif.add_shape(props, parent=rigid)
        child = bhkConvexTransformShapeProps()
        child.bhkMaterial, child.bhkRadius = 2617944780, .0057
        listed_shape.add_shape(child)
    else:
        shape = bhkConvexVerticesShapeProps(game='SKYRIMSE')
        shape.bhkMaterial, shape.bhkRadius = 1060167844, .02
        nif.add_shape(shape, parent=rigid, vertices=[(0, 0, 0), (.1, 0, 0), (0, .1, 0), (0, 0, .1)],
                      normals=[(0, 0, -1, 0), (0, -1, 0, 0), (-1, 0, 0, 0), (.577, .577, .577, -.0577)])
    nif.save()


@unittest.skipUnless(NIFLY, 'Requires local NiflyDLL')
class NifTests(unittest.TestCase):
    def test_written_weapon_reads_back_with_collision_and_base_values(self):
        from weapon_nif import base_dimensions, read_weapon, write_weapon_nif
        rng = np.random.default_rng(5)
        points = rng.normal(size=(300, 3)) * [.02, .5, .04]
        settings = FollowerSettings(mod_name='Probe', weapon_mode='original', original_weapon=original(grip=.3, length=90))
        placed = points @ placement(points, .3, 90)[:3, :3].T + placement(points, .3, 90)[:3, 3]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            base_nif(output / 'base.nif')
            self.assertAlmostEqual(base_dimensions(output / 'base.nif')['grip'], 1 / 3)
            texture_dir = output / 'mod/textures' / settings.asset_dir
            texture_dir.mkdir(parents=True)
            for name in ('weapon.dds', 'weapon_n.dds'):
                (texture_dir / name).write_bytes(b'DDS ')
            nif = output / 'mod/meshes' / settings.asset_dir / 'weapon.nif'
            nif.parent.mkdir(parents=True)
            shapes = [{'name': f'Weapon_00000_Part{i:03}', 'vertices': part, 'normals': np.tile([0, 0, 1.], (len(part), 1)),
                       'uvs': np.zeros((len(part), 2)), 'triangles': [(j, j + 1, j + 2) for j in range(0, len(part) - 2, 3)],
                       'metal': False, 'textures': {'Diffuse': 'textures\\vrm2skyrim\\probe\\weapon.dds',
                                                    'Normal': 'textures\\vrm2skyrim\\probe\\weapon_n.dds'}}
                      for i, part in enumerate(np.array_split(placed, 2))]
            result = write_weapon_nif(nif, shapes, output / 'base.nif', 'WeaponStaff')
            self.assertEqual((result['flags'], result['prn'], result['mass']), (129, ['WeaponStaff'], 9.))
            back = read_weapon(nif)
            self.assertEqual((back['root'], back['collision'], back['body'], back['shape'], back['layer'], back['prn']),
                             ('BSFadeNode', 'bhkCollisionObject', 'bhkRigidBody', 'bhkConvexVerticesShape', 5, ['WeaponStaff']))
            self.assertEqual([s['vertices'] for s in back['shapes']], [150, 150])
            np.testing.assert_allclose(back['hull'].min(0), placed.min(0), atol=1e-3)
            (output / 'weapon.json').write_text(json.dumps({'nif': nif.relative_to(output / 'mod').as_posix(),
                                                            'collision': result, 'shared_textures': []}), encoding='utf8')
            report, textures = weapon.validate_weapon_model(output, settings)
            self.assertAlmostEqual(report['length'], 90, places=3)
            self.assertAlmostEqual(report['grip'], .3, places=4)
            self.assertEqual(len(textures), 2)
            bad = FollowerSettings(mod_name='Probe', weapon_mode='original', original_weapon=original(grip=.5, length=90))
            with self.assertRaisesRegex(ValueError, 'origin'):
                weapon.validate_weapon_model(output, bad)
            sword = FollowerSettings(mod_name='Probe', weapon_mode='original',
                                     original_weapon=original(grip=.3, length=90, kind='sword', base='SteelSword'))
            with self.assertRaisesRegex(ValueError, 'sheathes at'):
                weapon.validate_weapon_model(output, sword)
            (texture_dir / 'weapon_n.dds').unlink()
            with self.assertRaisesRegex(ValueError, 'texture'):
                weapon.validate_weapon_model(output, settings)

    def test_transformed_and_list_bases_give_an_untransformed_body(self):
        """bhkRigidBodyT bases (EbonySword) must not move the new hull; bhkListShape bases (SteelDagger) load."""
        from pyn.nifconstants import HAVOC_SCALE_FACTOR
        from pyn.pynifly import NifFile
        from weapon_nif import base_collision, read_weapon, write_weapon_nif
        rng = np.random.default_rng(7)
        points = rng.normal(size=(300, 3)) * [.02, .5, .04]
        placed = points @ placement(points, .3, 90)[:3, :3].T + placement(points, .3, 90)[:3, 3]
        shapes = [{'name': 'Weapon_00000', 'vertices': placed, 'normals': np.tile([0, 0, 1.], (len(placed), 1)),
                   'uvs': np.zeros((len(placed), 2)), 'triangles': [(j, j + 1, j + 2) for j in range(0, 297, 3)],
                   'metal': False, 'textures': {}}]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name, options, material, radius in (('transformed', dict(transformed=True), 1060167844, .02),
                                                    ('listed', dict(listed=True), 2617944780, .0057),
                                                    ('both', dict(transformed=True, listed=True), 2617944780, .0057)):
                with self.subTest(base=name):
                    base_nif(output / f'{name}.nif', mass=7., **options)
                    base = base_collision(output / f'{name}.nif')
                    self.assertEqual((base['material'], round(base['radius'], 4), base['body']['mass']), (material, radius, 7.))
                    self.assertNotIn('translation', base['body'])
                    result = write_weapon_nif(output / f'{name}-out.nif', shapes, output / f'{name}.nif', 'WeaponSword')
                    back = read_weapon(output / f'{name}-out.nif')
                    self.assertEqual((back['body'], back['prn']), ('bhkRigidBody', ['WeaponSword']))
                    np.testing.assert_allclose(back['body_translation'], 0, atol=1e-6)
                    np.testing.assert_allclose(back['body_rotation'], [0, 0, 0, 1], atol=1e-6)
                    np.testing.assert_allclose(back['hull'].min(0), placed.min(0), atol=1e-3)
                    np.testing.assert_allclose(back['hull'].max(0), placed.max(0), atol=1e-3)
                    self.assertTrue(np.all(back['body_center'] > placed.min(0)) and np.all(back['body_center'] < placed.max(0)))
                    np.testing.assert_allclose(back['body_center'], result['center'], atol=1e-3)
                    with NifFile(str(output / f'{name}-out.nif')) as nif:
                        body = nif.root.collision_object.body.properties
                        self.assertEqual((body.friction, body.restitution, body.motionSystem, body.qualityType),
                                         (np.float32(.3), np.float32(.2), 3, 4))
                        self.assertAlmostEqual(body.penetrationDepth, .05, places=6)
                        size = np.ptp(placed, axis=0) / HAVOC_SCALE_FACTOR
                        np.testing.assert_allclose(np.array(body.inertiaMatrix[:])[[0, 5, 10]],
                                                   7 / 12 * np.array([size[1] ** 2 + size[2] ** 2, size[0] ** 2 + size[2] ** 2,
                                                                      size[0] ** 2 + size[1] ** 2]), rtol=1e-4)

    def test_validator_refuses_a_moved_body(self):
        from pyn.nifconstants import HAVOC_SCALE_FACTOR
        from pyn.nifdefs import PynBufferTypes, bhkConvexVerticesShapeProps, bhkRigidBodyProps
        from pyn.pynifly import BSTriShape, NifFile, NiStringExtraData
        settings = FollowerSettings(mod_name='Probe', weapon_mode='original', original_weapon=original(grip=.25, length=80))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            path = output / 'mod/meshes' / settings.asset_dir / 'weapon.nif'
            path.parent.mkdir(parents=True)
            vertices = [(0, -20, 0), (1, 60, 0), (0, 0, 1), (-1, 0, -1)]
            nif = NifFile()
            nif.initialize('SKYRIMSE', str(path), root_type='BSFadeNode', root_name='weapon')
            NiStringExtraData.New(nif, name='Prn', string_value='WeaponStaff', parent=nif.rootNode)
            shape = nif.createShapeFromData('Weapon_00000', vertices, [(0, 1, 2), (0, 1, 3)], [(0, 0)] * 4,
                                            [(0, 0, 1)] * 4, props=BSTriShape.getbuf(), parent=nif.rootNode)
            shape.shader.properties.bufType = PynBufferTypes.BSLightingShaderPropertyBufType
            for slot in ('Diffuse', 'Normal'):
                relative = f'textures/{settings.asset_dir}/weapon_{slot}.dds'
                shape.set_texture(slot, relative.replace('/', '\\'))
                (output / 'mod' / relative).parent.mkdir(parents=True, exist_ok=True)
                (output / 'mod' / relative).write_bytes(b'DDS ')
            shape.save_shader_attributes()
            collision = nif.rootNode.add_collision(None, flags=129, collision_type=PynBufferTypes.bhkCollisionObjectBufType)
            body = bhkRigidBodyProps()
            body.translation[:] = (0, .4, 0, 0)  # a plain body with a stray offset, as copied from bhkRigidBodyT bases
            body.rotation[:] = (0, 0, 0, 1)
            points, planes = hull(np.array(vertices, float))
            rigid = collision.add_body(body)
            nif.add_shape(bhkConvexVerticesShapeProps(game='SKYRIMSE'), parent=rigid,
                          vertices=[tuple(p) for p in points / HAVOC_SCALE_FACTOR],
                          normals=[(*n, -d / HAVOC_SCALE_FACTOR) for *n, d in planes])
            nif.save()
            (output / 'weapon.json').write_text(json.dumps({'nif': path.relative_to(output / 'mod').as_posix(),
                                                            'collision': {'flags': 129}, 'shared_textures': []}))
            with self.assertRaisesRegex(ValueError, 'must not move'):
                weapon.validate_weapon_model(output, settings)

    def test_private_skeleton_adds_the_staff_sheath_node(self):
        from custom_skeleton import HELPER_NODES, NifFile, create_skeleton, matrix, rigid_buffer, staff_local
        from weapon_nif import SHEATH_NODES
        self.assertEqual(SHEATH_NODES['staff'], 'WeaponStaff')
        self.assertEqual(HELPER_NODES['WeaponStaff'][0], 'WeaponBack')
        def about_x(degrees, translation):
            angle = np.radians(degrees)
            result = np.eye(4)
            result[1:3, 1:3] = [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
            result[:3, 3] = translation
            return result
        tilt, back = about_x(-7.7, [0, -.02, 9.9]), about_x(-95, [12.5, -6.3, 28.7])  # vanilla-like Spine2/WeaponBack
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / 'skeleton.nif', Path(directory) / 'private.nif'
            with NifFile() as file:
                file.initialize('SKYRIMSE', str(source))
                spine1 = file.add_node('NPC Spine1 [Spn1]', rigid_buffer(about_x(0, [0, 0, 81])), file.rootNode)
                spine2 = file.add_node('NPC Spine2 [Spn2]', rigid_buffer(tilt), spine1)
                file.add_node('WeaponBack', rigid_buffer(back), spine2)
                file.save()
            report = create_skeleton(source, target, {'NPC Spine2 [Spn2]': [0, 1, 79]})
            self.assertEqual(report['helper_nodes']['WeaponStaff']['parent'], 'NPC Spine2 [Spn2]')
            with NifFile(str(target)) as file:
                staff = file.nodes['WeaponStaff']
                self.assertEqual(staff.parent.name, 'NPC Spine2 [Spn2]')
                spine = matrix(file.nodes['NPC Spine2 [Spn2]'].global_transform)
                np.testing.assert_allclose(spine[:3, 3], [0, 1, 79], atol=1e-4)  # follows the custom spine
                np.testing.assert_allclose(matrix(staff.global_transform), spine @ staff_local(), atol=1e-4)
                np.testing.assert_allclose(matrix(file.nodes['WeaponBack'].transform), back, atol=1e-5)
                # The staff's +Y leans toward +X (the right shoulder) and up; +Z faces forward.
                axes = matrix(staff.global_transform)[:3, :3]
                self.assertTrue(axes[0, 1] > .4 and axes[2, 1] > .7 and axes[1, 2] > .9)
            # A skeleton without WeaponBack gets no helper node.
            with NifFile() as file:
                file.initialize('SKYRIMSE', str(source))
                file.add_node('NPC Spine1 [Spn1]', rigid_buffer(np.eye(4)), file.rootNode)
                file.save()
            self.assertEqual(create_skeleton(source, target, {})['helper_nodes'], {})

    def test_effect_shader_geometry_is_measured(self):
        from weapon_nif import base_dimensions
        from pyn.pynifly import NifFile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'magic.nif'
            base_nif(path, lit=False)
            with NifFile(str(path)) as nif:
                self.assertEqual(nif.shapes[0].shader.blockname, 'BSEffectShaderProperty')
            self.assertAlmostEqual(base_dimensions(path)['grip'], 1 / 3)


@unittest.skipUnless(find_game(), 'Local Skyrim.esm required')
class GameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from game_catalog import GameCatalog
        cls.data = find_game() / 'Data'
        cls.catalog = GameCatalog(cls.data)

    def test_candidates_defaults_and_settings_validation(self):
        choices = {c['id']: c for c in self.catalog.original_weapon_choices()}
        self.assertEqual(list(choices), list(WEAPON_KINDS))
        for kind, (_, _, default) in ORIGINAL_WEAPON_KINDS.items():
            self.assertEqual(choices[kind]['default'], default)
        self.assertNotIn('HuntingBow', {c['id'] for kind in choices.values() for c in kind['candidates']})
        self.catalog.validate_settings(FollowerSettings(weapon_mode='original', original_weapon=original(), weapon='NoSuchWeapon'))
        with self.assertRaises(ValueError):
            self.catalog.validate_settings(FollowerSettings(weapon='NoSuchWeapon'))
        with self.assertRaisesRegex(ValueError, 'not a playable'):
            self.catalog.validate_settings(FollowerSettings(weapon_mode='original', original_weapon=original(base='SteelSword')))

    def test_follower_plugin_with_and_without_original_weapon(self):
        from build_npc import build_npc
        from follower_plugin import follower_records
        from plugin_validation import validate_private_records
        for mode in ('official', 'original'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(dir=ROOT / 'build') as directory:
                output = Path(directory)
                settings = FollowerSettings(mod_name='Probe', weapon_mode=mode, original_weapon=original(),
                                            sitting_enabled=False)
                (output / 'weapon.json').write_text(json.dumps({'base': 'StaffFlames', 'source': {'sha256': SHA},
                                                                'bounds': [[-10.5, -53.1, -11.9], [9.6, 67.6, 11.5]]}))
                plugin = build_npc(self.data, output, settings, self.catalog)
                generated = follower_records(plugin)
                local = validate_private_records(generated, settings, output)
                self.assertEqual(len(local), 9 + 2 * (mode == 'original'))
                npc = next(r for r in generated if r.kind == b'NPC_')
                inventory = [struct.unpack_from('<I', v)[0] for v in npc.values(b'CNTO')]
                steel = self.catalog.require('SteelSword').form_id
                self.assertEqual(inventory, [steel] if mode == 'official' else [0x010008D0])
                if mode == 'original':
                    base = self.catalog.require('StaffFlames')
                    item = next(r for r in generated if r.kind == b'WEAP')
                    self.assertTrue(base.values(b'CNAM') and not item.values(b'CNAM'))
                    weapon.check_copied(generated, base, self.catalog.first_person_static(base))
                    self.assertEqual(self.catalog.require('StaffFlames').values(b'MODL'),
                                     [text('Weapons\\DragonPriest\\DragonPriestStaff3rd.nif')])

    def test_update_esm_values_are_copied(self):
        update = {r.form_id: r for r in records(self.data / 'Update.esm', {b'WEAP'})}
        dagger = self.catalog.require('SteelDagger', b'WEAP')
        for tag in (b'NAM8', b'NAM9', b'DNAM'):
            self.assertEqual(dagger.values(tag), update[dagger.form_id].values(tag))
        raw = next(r for r in records(self.data / 'Skyrim.esm', {b'WEAP'}) if r.form_id == dagger.form_id)
        self.assertNotEqual(raw.values(b'NAM8'), dagger.values(b'NAM8'))
        settings = FollowerSettings(weapon_mode='original', original_weapon=original(base='SteelDagger', kind='dagger'))
        static = self.catalog.first_person_static(dagger)
        generated = weapon.weapon_records(settings, dagger, static, self.catalog.label(dagger, b'DESC'), [[0, 0, 0], [1, 1, 1]])
        weapon.check_copied(generated, dagger, static)
        self.assertEqual(generated[0].values(b'NAM8'), update[dagger.form_id].values(b'NAM8'))
        with self.assertRaisesRegex(ValueError, 'differs'):
            weapon.check_copied(generated, raw, static)

    def test_default_bases_load_collision_and_size(self):
        """Every kind's default base NIF from the game archives (SteelDagger/SteelBattleaxe use bhkListShape)."""
        if not NIFLY:
            self.skipTest('Requires local NiflyDLL')
        from game_assets import GameAssets
        from weapon_nif import CONVEX_SHAPES, base_collision, base_dimensions
        with tempfile.TemporaryDirectory(dir=ROOT / 'build') as directory:
            assets = GameAssets(self.data, [], directory)
            for kind, (_, _, default) in ORIGINAL_WEAPON_KINDS.items():
                with self.subTest(kind=kind, base=default):
                    record = self.catalog.require(default, b'WEAP')
                    self.assertEqual(self.catalog.original_weapon_kind(record), kind)
                    path = assets.extract(record.values(b'MODL')[0].rstrip(b'\0').decode('utf8'))
                    collision = base_collision(path)
                    self.assertTrue(collision['material'] and 0 < collision['radius'] < .0501)
                    self.assertEqual(collision['body']['collisionFilter_layer'], 5)
                    self.assertGreater(collision['body']['mass'], 0)
                    if collision['shape_type'] not in CONVEX_SHAPES + ('bhkListShape',):
                        self.assertEqual(collision['radius'], .05)  # capsule: default convex radius
                    size = base_dimensions(path)
                    self.assertTrue(20 < size['length'] < 150 and 0 < size['grip'] < 1)

    def test_two_material_glb_through_blender(self):
        """Textured and untextured materials survive the real weapon_blender step and the preview import."""
        from environment import find_blender
        from converter import run_blender
        from textures import decode_dds
        from weapon_nif import read_weapon
        if not NIFLY or not find_blender():
            self.skipTest('Requires local NiflyDLL and Blender')
        for nodes, mirror in ((False, False), (True, False), (True, True)):
            with self.subTest(nodes=nodes, mirror=mirror), tempfile.TemporaryDirectory(dir=ROOT / 'build') as directory:
                directory = Path(directory)
                glb = directory / 'two.glb'
                two_material_glb(glb, nodes, mirror)
                settings = FollowerSettings(mod_name='Probe', weapon_mode='original', original_weapon=original(
                    sha256=weapon.sha256(glb), kind='mace', base='SteelMace', grip=.2, length=60))
                output = directory / 'out'
                output.mkdir()
                report = weapon.convert_weapon(glb, self.data, find_blender(), output, settings, self.catalog)
                shapes = {s['textures']['Diffuse'].rsplit('\\', 1)[-1]: s for s in read_weapon(output / 'mod' / report['nif'])['shapes']}
                self.assertEqual(sorted(shapes), ['weapon_0.dds', 'weapon_1.dds'])
                self.assertLess(shapes['weapon_0.dds']['points'][:, 1].max(), shapes['weapon_1.dds']['points'][:, 1].min() + 1e-3)
                for name, shape in shapes.items():  # every face winds outwards, along its corner normals
                    corners = shape['points'][shape['faces']]
                    winding = np.cross(corners[:, 1] - corners[:, 0], corners[:, 2] - corners[:, 0])
                    facing = np.einsum('ij,ij->i', winding, shape['normals'][shape['faces']].sum(1))
                    self.assertTrue((facing > 0).all(), name)
                for texture in (output / 'mod/textures').rglob('*.dds'):
                    decode_dds(texture, output / 'dds-preview')
                plan = json.loads((output / 'weapon-plan.json').read_text(encoding='utf8'))
                run_blender(find_blender(), 'weapon_compare_blender.py',
                            ['--weapon-nif', output / 'mod' / report['nif'], '--weapon-textures', output / 'dds-preview',
                             '--base-nif', plan['base_nif'], '--output', output / 'compare.png'], output, 'Weapon comparison')
                self.assertTrue((output / 'compare.png').is_file())

    def test_localized_description_becomes_inline_text(self):
        base = self.catalog.require('SteelSword')
        static = self.catalog.first_person_static(base)
        description = self.catalog.label(base, b'DESC')
        records_ = weapon.weapon_records(FollowerSettings(weapon_mode='original', original_weapon=original(base='SteelSword', kind='sword')),
                                         base, static, description, [[0, 0, 0], [1, 1, 1]])
        self.assertEqual(records_[0].values(b'DESC'), [text(description)])
        self.assertEqual(len(base.values(b'DESC')[0]), 4)


if __name__ == '__main__':
    unittest.main()
