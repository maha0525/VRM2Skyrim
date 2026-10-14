"""Version mismatch rejects mutations before uploads or conversion can start."""
from http.server import ThreadingHTTPServer
import json
import tempfile
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from wizard import WizardApplication, handler_for, BOOT_FINGERPRINT
from converter import convert
from settings import FollowerSettings


class WizardServerTests(unittest.TestCase):
    def test_conversion_failure_retains_stage_and_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'invalid.vrm'
            source.write_bytes(b'invalid input')
            output = root/'output'
            with patch('converter.doctor', return_value={'fixture': True}), \
                    patch('converter.inspect', side_effect=ValueError('invalid fixture source')):
                with self.assertRaisesRegex(ValueError, 'invalid fixture source'):
                    convert(source, root, root/'blender', output, FollowerSettings())
            report = json.loads((output/'run.json').read_text(encoding='utf8'))
            self.assertEqual(report['state'], 'failed')
            self.assertEqual(report['stage'], '入力と設定の検査')
            log = Path(report['failure_log']).read_text(encoding='utf8')
            self.assertIn('Traceback', log)
            self.assertIn('invalid fixture source', log)

    def test_updated_sources_require_restart_and_block_post(self):
        with tempfile.TemporaryDirectory() as directory:
            app = WizardApplication(directory)
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(app))
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            base = 'http://127.0.0.1:'+str(server.server_address[1])
            try:
                with patch('wizard.source_fingerprint', return_value=BOOT_FINGERPRINT):
                    env = json.load(urlopen(base+'/api/environment'))
                    self.assertFalse(env['restart_required'])
                    self.assertEqual(env['defaults']['protection'], 'essential')
                    self.assertEqual(env['defaults']['morality'], 0)
                with patch('wizard.source_fingerprint', return_value='changed'):
                    self.assertTrue(json.load(urlopen(base+'/api/environment'))['restart_required'])
                    with self.assertRaises(HTTPError) as raised:
                        urlopen(Request(base+'/api/jobs', data=b'{}'))
                    self.assertEqual(raised.exception.code, 409)
                    self.assertTrue(json.load(raised.exception)['restart_required'])
                    self.assertFalse(app.jobs)
                self.assertEqual(urlopen(base+'/wizard.js').headers['Cache-Control'], 'no-store')
            finally:
                server.shutdown()
                worker.join()
                server.server_close()
                app.close()
