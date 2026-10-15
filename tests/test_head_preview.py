"""Cache ownership, invalidation and no-MOD preview pipeline contracts."""
from contextlib import ExitStack
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
import head_preview
from settings import FollowerSettings


class HeadPreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root/'input.vrm'
        self.source.write_bytes(b'avatar')
        self.game = self.root/'game'
        self.game.mkdir()
        self.asset = self.game/'asset-version'
        self.asset.write_bytes(b'original')
        self.blender = self.root/'blender.exe'
        self.blender.write_bytes(b'blender')
        self.settings = FollowerSettings(armor_support=True, appearance_source_sha256='a'*64,
                                         appearance_parts=dict(body=[0], underwear=[], fixed=[1, 2], garments=[
                                             dict(id='cape', name='Cape', nodes=[3], slot=46, armor_type='clothing',
                                                  armor_rating=0, weight=0, value=0, equipped=True)]),
                                         appearance_heads=dict(face=[1], hair=[2]))
        self.calls = dict(prepare=0, skin=0, equipment=0, render=0)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        fake = SimpleNamespace(require=lambda key, kind: SimpleNamespace(editor_id=key), key=lambda armor: armor.editor_id)
        for name, value in [('doctor', lambda *a: {'ready': True}), ('OfficialCatalog', lambda *a: fake),
                            ('source_assets', lambda *a: head_preview.file_identity(self.asset)),
                            ('prepare_source', self.prepare), ('convert_appearance', self.appearance),
                            ('fit', self.fit), ('run_blender', self.render)]:
            self.stack.enter_context(patch.object(head_preview, name, value))
        self.convert = self.stack.enter_context(patch('converter.convert'))
        self.package = self.stack.enter_context(patch('converter.package'))

    def prepare(self, source, output, settings):
        self.calls['prepare'] += 1
        settings.save(output/'settings.json')

    def appearance(self, source, game, blender, output, settings, progress):
        folder = output/'mod/meshes'/settings.asset_dir
        folder.mkdir(parents=True)
        for name in ('body', 'skeleton', 'face', 'hair'):
            (folder/(name+'.nif')).write_bytes(name.encode())
        (output/'appearance.json').write_text(json.dumps({'components': []}), encoding='utf8')
        decoded = output/'dds-preview'
        decoded.mkdir()
        Image.new('RGB', (4, 4)).save(decoded/'avatar.png')

    def fit(self, output, data, blender, skin_only=False, reuse_body=False):
        settings = FollowerSettings.load(output/'settings.json')
        if skin_only:
            self.calls['skin'] += 1
            folder = output/'armor-source'
            folder.mkdir()
            (folder/'body.nif').write_bytes(b'whole body')
        else:
            self.calls['equipment'] += 1
            self.assertTrue(reuse_body)
            self.assertTrue((output/'dds-preview/avatar.png').is_file(), 'Prepared avatar textures must be reused with geometry')
            (output/'armor-fitting.json').write_text('{}', encoding='utf8')
            (output/'mod/meshes'/settings.asset_dir/'equipment.nif').write_bytes(settings.fit_armors[0].encode())

    def render(self, blender, script, arguments, output, name):
        self.calls['render'] += 1
        self.assertEqual(script, 'render_blender.py')
        armor = arguments[arguments.index('--wardrobe')+1][6:]
        folder = output/'previews'
        folder.mkdir(exist_ok=True)
        Image.new('RGB', (4, 4)).save(folder/f'wardrobe-armor-{armor}-rest-01.png')

    def run_preview(self, armor='HelmetA', policy=None, settings=None):
        return head_preview.preview(self.root/'cache', self.source, self.game, self.blender,
                                    settings or self.settings, armor,
                                    policy or dict(hide_face=False, hide_hair=True), lambda stage: None)

    def test_different_armor_and_policy_reuse_independent_preparation(self):
        first = self.run_preview()
        second = self.run_preview('HelmetB')
        third = self.run_preview('HelmetB', dict(hide_face=True, hide_hair=True))
        fourth = self.run_preview('HelmetB', dict(hide_face=True, hide_hair=True))
        self.assertFalse(first['avatar_reused'])
        self.assertTrue(second['avatar_reused'])
        self.assertFalse(second['equipment_reused'])
        self.assertTrue(third['equipment_reused'])
        self.assertFalse(third['render_reused'])
        self.assertTrue(fourth['render_reused'])
        self.assertEqual(self.calls, dict(prepare=1, skin=1, equipment=2, render=3))
        self.convert.assert_not_called()
        self.package.assert_not_called()
        self.assertEqual(list((self.root/'cache').rglob('*.esp')), [])
        self.assertEqual(list((self.root/'cache').rglob('*.zip')), [])

    def test_inputs_and_deleted_outputs_invalidate_only_affected_cache(self):
        first = self.run_preview()
        (Path(first['output'])/'appearance.json').unlink()
        rebuilt = self.run_preview()
        self.assertTrue(rebuilt['avatar_reused'])
        self.assertFalse(rebuilt['equipment_reused'])
        changed = copy.deepcopy(self.settings)
        changed.height_scale = .9
        self.assertFalse(self.run_preview(settings=changed)['avatar_reused'])
        changed.appearance_heads = dict(face=[2], hair=[1])
        self.assertFalse(self.run_preview(settings=changed)['avatar_reused'])
        self.asset.write_bytes(b'updated game assets')
        self.assertFalse(self.run_preview(settings=changed)['avatar_reused'])
        self.source.write_bytes(b'new VRM')
        self.assertFalse(self.run_preview(settings=changed)['avatar_reused'])

    def test_failure_never_publishes_a_ready_avatar(self):
        with patch.object(head_preview, 'convert_appearance', side_effect=ValueError('conversion failed')):
            with self.assertRaisesRegex(ValueError, 'conversion failed'):
                self.run_preview()
        self.assertFalse(self.run_preview()['avatar_reused'])
        self.assertEqual(self.calls['prepare'], 2)

    def test_wizard_forwards_progress_without_full_conversion(self):
        from wizard import WizardApplication
        app = WizardApplication(self.root/'wizard')
        job = {'id': 'preview'}
        try:
            with patch('head_preview.preview', side_effect=lambda *args: (
                    args[-1]('準備済みのモデルを使用'), dict(output='prepared', previews=['head.png']))[1]):
                self.settings.fit_armors = ['HelmetA']
                app._run_head_preview(job, self.source, self.game, self.blender, self.settings,
                                      dict(hide_face=False, hide_hair=True))
            self.assertEqual(job['status'], 'complete')
            self.assertEqual(job['previews'], ['head.png'])
            self.convert.assert_not_called()
        finally:
            app.close()
