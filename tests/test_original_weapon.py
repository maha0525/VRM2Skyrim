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


def base_nif(path, mass=9.):
    from pyn.nifdefs import PynBufferTypes, bhkConvexVerticesShapeProps, bhkRigidBodyProps
    from pyn.pynifly import BSTriShape, BSXFlags, NifFile, NiStringExtraData
    nif = NifFile()
    nif.initialize('SKYRIMSE', str(path), root_type='BSFadeNode', root_name='Base')
    BSXFlags.New(nif, flags=194, parent=nif.rootNode)
    NiStringExtraData.New(nif, name='Prn', string_value='WeaponStaff', parent=nif.rootNode)
    nif.createShapeFromData('Base:0', [(0, -40, 0), (1, 80, 0), (0, 0, 1)], [(0, 1, 2)], [(0, 0)] * 3, [(0, 0, 1)] * 3,
                            props=BSTriShape.getbuf(), parent=nif.rootNode)
    nif.shapes[0].shader.properties.bufType = PynBufferTypes.BSLightingShaderPropertyBufType
    nif.shapes[0].save_shader_attributes()
    collision = nif.rootNode.add_collision(None, flags=129, collision_type=PynBufferTypes.bhkCollisionObjectBufType)
    body = bhkRigidBodyProps()
    body.mass, body.collisionFilter_layer, body.motionSystem, body.qualityType = mass, 5, 3, 4
    rigid = collision.add_body(body)
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
            result = write_weapon_nif(nif, shapes, output / 'base.nif')
            self.assertEqual((result['flags'], result['prn'], result['mass']), (129, ['WeaponStaff'], 9.))
            back = read_weapon(nif)
            self.assertEqual((back['root'], back['collision'], back['body'], back['shape'], back['layer']),
                             ('BSFadeNode', 'bhkCollisionObject', 'bhkRigidBody', 'bhkConvexVerticesShape', 5))
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
            (texture_dir / 'weapon_n.dds').unlink()
            with self.assertRaisesRegex(ValueError, 'texture'):
                weapon.validate_weapon_model(output, settings)


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
