"""Wizard-time original weapon preview: cache ownership, invalidation and the no-MOD pipeline."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from settings import FollowerSettings
import weapon_preview


def original(sha, **changes):
    return {'sha256': sha, 'filename': 'staff.glb', 'kind': 'staff', 'base': 'StaffFlames', 'name': 'Staff',
            'grip': .44, 'length': 120.7, 'flip': False, 'roll': 0, **changes}


class WeaponPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'input.vrm'
        self.source.write_bytes(b'avatar')
        self.glb = self.root / 'staff.glb'
        self.glb.write_bytes(b'weapon')
        self.sha = hashlib.sha256(b'weapon').hexdigest()
        self.game = self.root / 'game'
        (self.game / 'Data').mkdir(parents=True)
        self.blender = self.root / 'blender.exe'
        self.blender.write_bytes(b'blender')
        self.refs = self.root / 'refs'
        self.settings = FollowerSettings(weapon_mode='original', original_weapon=original(self.sha))
        self.calls = dict(avatar=0, weapon=0, compare=0, render=0, animation=0)
        stack = ExitStack()
        self.addCleanup(stack.close)
        for name, value in [('doctor', lambda *a: {'ready': True}), ('prepare_source', self.prepare),
                            ('convert_appearance', self.appearance), ('run_blender', self.blender_script),
                            ('decode_dds', self.decode), ('drawn_animation', self.animation)]:
            stack.enter_context(patch.object(weapon_preview, name, value))
        stack.enter_context(patch('weapon.convert_weapon', self.convert_weapon))
        self.package = stack.enter_context(patch('converter.package'))

    def prepare(self, source, output, settings):
        self.calls['avatar'] += 1
        self.assertEqual(settings.weapon_mode, 'official', 'The cached avatar must not depend on the weapon')
        self.assertFalse(settings.fitting_enabled or settings.toon_enabled or settings.physics_enabled)
        settings.save(output / 'settings.json')

    def appearance(self, source, game, blender, output, settings, progress):
        (output / 'appearance.json').write_text('{}', encoding='utf8')
        (output / 'references.json').write_text(json.dumps({'root': str(self.refs)}), encoding='utf8')
        texture = output / 'mod/textures' / settings.asset_dir / 'avatar.dds'
        texture.parent.mkdir(parents=True)
        texture.write_bytes(b'dds')

    def decode(self, texture, preview):
        preview.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (2, 2)).save(preview / (texture.stem + '.png'))

    def animation(self, data, refs, kind):
        self.calls['animation'] += 1
        self.assertEqual((refs, kind), (self.refs, 'staff'))

    def convert_weapon(self, glb, data, blender, output, settings, catalog):
        self.calls['weapon'] += 1
        self.assertEqual(Path(glb), self.glb)
        self.assertEqual(settings.original_weapon, self.current)
        nif = f'meshes/{settings.asset_dir}/weapon.nif'
        (output / 'mod' / nif).parent.mkdir(parents=True)
        (output / 'mod' / nif).write_bytes(b'nif')
        texture = output / 'mod/textures' / settings.asset_dir / 'weapon.dds'
        texture.parent.mkdir(parents=True)
        texture.write_bytes(b'dds')
        (output / 'weapon-plan.json').write_text(json.dumps({'nif': nif, 'base_nif': str(output / 'base.nif')}), encoding='utf8')
        (output / 'weapon.json').write_text(json.dumps({'source': {'triangles': 19999},
                                                        'base_dimensions': {'length': 134., 'grip': .52}}), encoding='utf8')

    def blender_script(self, blender, script, arguments, output, label):
        arguments = [str(a) for a in arguments]
        if script == 'weapon_compare_blender.py':
            self.calls['compare'] += 1
            Image.new('RGB', (2, 2)).save(arguments[arguments.index('--output') + 1])
        elif script == 'render_blender.py':
            self.calls['render'] += 1
            name = arguments[arguments.index('--weapon-preview') + 1]
            self.assertEqual(arguments[arguments.index('--weapon-kind') + 1], 'staff')
            self.assertTrue(Path(arguments[arguments.index('--weapon-nif') + 1]).is_file())
            (output / 'previews').mkdir(exist_ok=True)
            for view in ('drawn', 'hand', 'sheathed'):
                Image.new('RGB', (2, 2)).save(output / 'previews' / f'weapon-{name}-{view}.png')
        else:
            self.fail('Unexpected Blender script: ' + script)

    def run_preview(self, **changes):
        self.current = original(self.sha, **changes)
        settings = FollowerSettings(weapon_mode='original', original_weapon=self.current)
        return weapon_preview.preview(self.root / 'cache', self.source, self.glb, self.game, self.blender,
                                      settings, SimpleNamespace(), lambda stage: None)

    def test_size_changes_rebuild_only_the_weapon_and_render(self):
        first = self.run_preview()
        self.assertEqual(first['views'], ['drawn', 'hand', 'sheathed', 'compare'])
        for path in first['previews']:
            self.assertTrue((Path(first['output']) / path).is_file(), path)
        self.assertEqual((first['avatar_reused'], first['weapon_reused'], first['render_reused']), (False, False, False))
        again = self.run_preview()
        self.assertEqual((again['avatar_reused'], again['weapon_reused'], again['render_reused']), (True, True, True))
        longer = self.run_preview(length=100.)
        self.assertEqual((longer['avatar_reused'], longer['weapon_reused'], longer['render_reused']), (True, False, False))
        self.assertNotEqual(longer['previews'], first['previews'])
        self.assertEqual(self.calls, dict(avatar=1, weapon=2, compare=2, render=2, animation=2))
        self.package.assert_not_called()
        self.assertEqual(list((self.root / 'cache').rglob('*.esp')) + list((self.root / 'cache').rglob('*.zip')), [])

    def test_deleted_preview_or_comparison_is_rebuilt(self):
        first = self.run_preview()
        (Path(first['output']) / first['previews'][0]).unlink()
        self.assertFalse(self.run_preview()['render_reused'])
        weapon_dir = next((self.root / 'cache/weapon-preview-cache/weapons').iterdir())
        (weapon_dir / 'compare.png').unlink()
        self.assertFalse(self.run_preview()['weapon_reused'])

    def test_different_glb_and_official_mode_are_refused(self):
        with self.assertRaisesRegex(ValueError, '別のGLB'):
            self.run_preview(sha256='f' * 64)
        settings = FollowerSettings()
        with self.assertRaisesRegex(ValueError, 'オリジナル武器'):
            weapon_preview.preview(self.root / 'cache', self.source, self.glb, self.game, self.blender, settings,
                                   SimpleNamespace(), lambda stage: None)
        self.assertEqual(self.calls['avatar'], 0)

    def test_base_dimensions_accept_only_candidates_and_cache_the_measurement(self):
        record = SimpleNamespace(values=lambda tag: [b'Weapons\\Staff\\Staff01.nif\0'])
        kinds = {'StaffFlames': 'staff', 'Torch': None}
        catalog = SimpleNamespace(require=lambda key, kind: SimpleNamespace(key=key, values=record.values),
                                  original_weapon_kind=lambda r: kinds[r.key])
        measured = []

        class Assets:
            def __init__(self, data, plugins, output):
                self.output = Path(output)

            def extract(self, name):
                path = self.output / name.replace('\\', '/').lower()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'nif')
                return path

        def measure(path):
            measured.append(path)
            return {'length': 134., 'grip': .52}

        with patch('game_assets.GameAssets', Assets), patch('weapon_nif.base_dimensions', measure):
            first = weapon_preview.base_dimensions(self.root / 'cache', self.game / 'Data', catalog, 'StaffFlames')
            second = weapon_preview.base_dimensions(self.root / 'cache', self.game / 'Data', catalog, 'StaffFlames')
            with self.assertRaisesRegex(ValueError, 'not an original-weapon base'):
                weapon_preview.base_dimensions(self.root / 'cache', self.game / 'Data', catalog, 'Torch')
        self.assertEqual(first, second)
        self.assertEqual((first['kind'], first['length'], first['grip']), ('staff', 134., .52))
        self.assertEqual(len(measured), 1)


if __name__ == '__main__':
    unittest.main()
