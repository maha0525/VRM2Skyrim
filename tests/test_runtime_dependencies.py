"""Native dependency checks must detect import and decompression failures early."""
from pathlib import Path
import json
import os
import subprocess
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bsa import BSA
from converter import doctor
from runtime_dependencies import dependency_checks, LZ4_PROBE


class RuntimeDependencyTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows launcher')
    def test_launcher_without_environment_does_not_fall_back_to_system_python(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory)/'Launch.cmd'
            launcher.write_bytes((root/'Launch.cmd').read_bytes())
            result = subprocess.run([str(Path(os.environ['SystemRoot'])/'System32/cmd.exe'),
                                     '/d', '/c', str(launcher)], input='\n', text=True,
                                    capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn('run Setup.cmd first', result.stdout)

    def test_cached_headgear_preview_reads_japanese_run_metadata_as_utf8(self):
        from wizard import WizardApplication
        from settings import FollowerSettings
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root/'preview'
            output.mkdir()
            (output/'run.json').write_text(json.dumps({'state': 'offline_verified', 'stage': '変換完了'},
                                                     ensure_ascii=False), encoding='utf8')
            app = WizardApplication(root)
            original = Path.read_text

            def read(path, *args, **kwargs):
                # Reproduce Japanese Windows' legacy locale even on UTF-8 CI.
                if path.name == 'run.json' and not args and 'encoding' not in kwargs:
                    return original(path, encoding='cp932')
                return original(path, *args, **kwargs)

            job = {'id': 'cached', 'output': str(output)}
            try:
                with patch('wizard.convert') as convert, patch('wizard.run_blender') as render, patch.object(Path, 'read_text', read):
                    app._run_head_preview(job, root/'input.vrm', root/'game', root/'blender', output,
                                          FollowerSettings(), 'TestHelmet',
                                          {'hide_face': False, 'hide_hair': True}, 'cached')
                self.assertEqual(job['status'], 'complete', job.get('error'))
                convert.assert_not_called()
                self.assertIn('--head-closeup', render.call_args.args[2])
            finally:
                app.close()

    def test_installed_lz4_can_extract_real_compressed_bsa_payload(self):
        # A minimal v105 archive, with a real LZ4 frame compressed payload.
        folder = b'meshes\0'
        filename = b'probe.nif\0'
        offset = 36+24+1+len(folder)+16+len(filename)
        payload = struct.pack('<I', 20)+LZ4_PROBE
        data = struct.pack('<4s8I', b'BSA\0', 105, 36, 7, 1, 1, len(folder), len(filename), 1)
        data += struct.pack('<QIIQ', 0, 1, 0, 0)
        data += bytes([len(folder)])+folder+struct.pack('<QII', 0, len(payload), offset)+filename+payload
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'probe.bsa'
            target = Path(directory)/'extracted.nif'
            source.write_bytes(data)
            BSA(source).extract('meshes/probe.nif', target)
            self.assertEqual(target.read_bytes(), b'VRM2Skyrim LZ4 probe')
        self.assertTrue(dependency_checks()['lz4'])

    def test_present_but_unloadable_package_is_rejected_by_doctor(self):
        import importlib
        original = importlib.import_module

        def load(name):
            if name == 'lz4.frame':
                raise ModuleNotFoundError("No module named 'lz4._version'")
            return original(name)

        with patch('runtime_dependencies.importlib.import_module', side_effect=load), self.assertLogs(level='ERROR') as logs:
            checks = doctor(None, None)
        self.assertFalse(checks['lz4'])
        self.assertIn('lz4._version', '\n'.join(logs.output))
        self.assertIn('Setup.cmd', '\n'.join(logs.output))

    def test_importable_but_broken_decompressor_is_rejected(self):
        fake = SimpleNamespace(decompress=lambda _: b'wrong')
        with patch('runtime_dependencies.importlib.import_module', return_value=fake), self.assertLogs(level='ERROR'):
            self.assertFalse(dependency_checks()['lz4'])

    def test_unsupported_python_is_not_reported_ready(self):
        with patch('runtime_dependencies.sys.version_info', (3, 13, 2)), self.assertLogs(level='ERROR'):
            self.assertFalse(dependency_checks()['python'])
