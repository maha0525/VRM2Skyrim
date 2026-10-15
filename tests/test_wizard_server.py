"""Version mismatch rejects mutations before uploads or conversion can start."""
import errno
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import tempfile
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen, build_opener, ProxyHandler

from wizard import WizardApplication, handler_for, BOOT_FINGERPRINT, WizardHTTPServer, make_server, main, port_is_listening
from converter import convert
from settings import FollowerSettings, VERSION


class WizardServerTests(unittest.TestCase):
    def test_slow_connection_refusal_does_not_report_a_busy_port(self):
        with patch('wizard.socket.create_connection', side_effect=TimeoutError):
            self.assertFalse(port_is_listening(12345))

    def test_busy_port_uses_new_listener_without_stopping_previous_server(self):
        class OldHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                data = b'{"version":"0.9.5-dev"}'
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        opener = build_opener(ProxyHandler({}))
        for host, server_type in [('127.0.0.1', ThreadingHTTPServer),
                                  ('0.0.0.0', ThreadingHTTPServer),
                                  ('127.0.0.1', WizardHTTPServer)]:
            with self.subTest(host=host, server=server_type.__name__), tempfile.TemporaryDirectory() as directory:
                old = server_type((host, 0), OldHandler)
                servers = [old]
                workers = []
                app = WizardApplication(directory)
                try:
                    with self.assertLogs(level='WARNING') as logs:
                        new = make_server(app, old.server_address[1])
                        servers.append(new)
                    self.assertNotEqual(new.server_address[1], old.server_address[1])
                    self.assertIn('existing processes are unchanged', logs.output[0])
                    for server in servers:
                        worker = threading.Thread(target=server.serve_forever)
                        worker.start()
                        workers.append(worker)
                    for _ in range(3):
                        for server, version in [(old, '0.9.5-dev'), (new, VERSION)]:
                            url = f'http://127.0.0.1:{server.server_address[1]}/api/environment'
                            self.assertEqual(json.load(opener.open(url, timeout=5))['version'], version)
                    # Exclusive binding must also reject a legacy server which
                    # still enables SO_REUSEADDR (the original failure mode).
                    with self.assertRaises(OSError):
                        duplicate = ThreadingHTTPServer(new.server_address, OldHandler)
                        duplicate.server_close()
                finally:
                    for server in servers[:len(workers)]:
                        server.shutdown()
                    for worker in workers:
                        worker.join()
                    for server in servers:
                        server.server_close()
                    app.close()

    def test_launcher_opens_actual_selected_port_and_closes_on_interrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            app = WizardApplication(directory)
            old = ThreadingHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler)
            opened = []
            try:
                def remember(url):
                    response = json.load(build_opener(ProxyHandler({})).open(url+'/api/environment', timeout=5))
                    self.assertEqual(response['version'], VERSION)

                def serve(server):
                    worker = threading.Thread(target=ThreadingHTTPServer.serve_forever, args=(server,))
                    worker.start()
                    try:
                        remember(opened[-1])
                    finally:
                        server.shutdown()
                        worker.join()
                    raise KeyboardInterrupt

                with patch('sys.argv', ['wizard.py', '--port', str(old.server_address[1])]), \
                        patch('wizard.WizardApplication', return_value=app), \
                        patch('wizard.webbrowser.open', side_effect=opened.append), \
                        patch.object(WizardHTTPServer, 'serve_forever', autospec=True, side_effect=serve):
                    main()
                self.assertNotEqual(opened[0], f'http://127.0.0.1:{old.server_address[1]}')
            finally:
                old.server_close()
                app.close()

    def test_unrelated_bind_failure_is_not_hidden_by_fallback(self):
        for port, error in [(8768, OSError(errno.EMFILE, 'Too many files')), (0, OSError(errno.EADDRINUSE, 'Busy'))]:
            with self.subTest(port=port), patch('wizard.port_is_listening', return_value=False), \
                    patch('wizard.WizardHTTPServer', side_effect=error) as factory:
                with self.assertRaises(OSError) as raised:
                    make_server(None, port)
                self.assertIs(raised.exception, error)
                self.assertEqual(factory.call_count, 1)

    def test_free_port_restarts_and_bind_race_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            app = WizardApplication(directory)
            server = make_server(app, 0)
            port = server.server_address[1]
            server.server_close()
            try:
                for _ in range(3):
                    server = make_server(app, port)
                    self.assertEqual(server.server_address[1], port)
                    server.server_close()
                server = WizardHTTPServer(('127.0.0.1', port), BaseHTTPRequestHandler)
                # A listener can appear between the preflight and bind.
                with patch('wizard.port_is_listening', return_value=False), self.assertLogs(level='WARNING'):
                    newer = make_server(app, port)
                try:
                    self.assertNotEqual(newer.server_address[1], port)
                finally:
                    newer.server_close()
            finally:
                server.server_close()
                app.close()

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
