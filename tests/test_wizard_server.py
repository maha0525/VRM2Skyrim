"""Version mismatch rejects mutations before uploads or conversion can start."""
from dataclasses import asdict
import errno
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import tempfile
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen, build_opener, ProxyHandler

from wizard import WizardApplication, handler_for, BOOT_FINGERPRINT, WizardHTTPServer, make_server, main, port_is_listening
from converter import convert
from settings import FollowerSettings, VERSION


class WizardServerTests(unittest.TestCase):
    def test_served_page_and_api_share_version_after_a_release_bump(self):
        opener = build_opener(ProxyHandler({}))
        with tempfile.TemporaryDirectory() as directory:
            app = WizardApplication(directory)
            server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(app))
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            base = 'http://127.0.0.1:'+str(server.server_address[1])
            try:
                for version in (VERSION, '99.88.77'):
                    with self.subTest(version=version), patch('wizard.VERSION', version):
                        for route in ('/', '/index.html'):
                            response = opener.open(base+route, timeout=5)
                            page = response.read()
                            self.assertIn(f'name="converter-version" content="{version}"'.encode(), page)
                            self.assertNotIn(b'__CONVERTER_VERSION__', page)
                            self.assertEqual(int(response.headers['Content-Length']), len(page))
                            self.assertEqual(response.headers['Cache-Control'], 'no-store')
                        self.assertEqual(json.load(opener.open(base+'/api/environment', timeout=5))['version'], version)
            finally:
                server.shutdown()
                worker.join()
                server.server_close()
                app.close()

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


class WeaponServerTests(unittest.TestCase):
    """GLB upload, base sizes, weapon previews and the conversion hand-off; no Blender or game data."""

    def setUp(self):
        from inspect_vrm import write_glb
        from tests.test_original_weapon import glb_document
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        document, binary = glb_document([{}], [])
        self.glb = self.root / 'staff.glb'
        write_glb(self.glb, document, binary)
        self.app = WizardApplication(self.root / 'workspace')
        self.addCleanup(self.app.close)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.app))
        self.worker = threading.Thread(target=self.server.serve_forever)
        self.worker.start()
        self.addCleanup(self.stop)
        self.base = 'http://127.0.0.1:' + str(self.server.server_address[1])
        self.opener = build_opener(ProxyHandler({}))
        source = self.root / 'avatar.vrm'
        source.write_bytes(b'vrm')
        self.app.sources['avatar'] = source
        self.app.source_reports['avatar'] = {'parts': [], 'sha256': 'f' * 64}
        self.catalog = SimpleNamespace(validate_settings=lambda settings: None,
                                       require=lambda key, kind: SimpleNamespace(key=key),
                                       original_weapon_kind=lambda record: 'staff' if record.key == 'StaffFlames' else None)

    def stop(self):
        self.server.shutdown()
        self.worker.join()
        self.server.server_close()

    def post(self, route, data, headers=None):
        body = data if isinstance(data, bytes) else json.dumps(data).encode()
        try:
            response = self.opener.open(Request(self.base + route, data=body, headers=headers or {}), timeout=10)
            return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def upload(self, name='staff.glb', blob=None):
        return self.post('/api/weapon-glb', blob if blob is not None else self.glb.read_bytes(),
                         {'X-Filename': quote(name), 'Content-Type': 'application/octet-stream'})

    def settings(self, uploaded, **changes):
        weapon = {'sha256': uploaded['sha256'], 'filename': uploaded['filename'], 'kind': 'staff',
                  'base': 'StaffFlames', 'name': '三日月の杖', 'grip': .44, 'length': 120.7, 'flip': False, 'roll': 0}
        return {**asdict(FollowerSettings(mod_name='Probe', weapon_mode='original', original_weapon=weapon)), **changes}

    def test_glb_upload_reports_counts_and_rejects_other_files(self):
        status, uploaded = self.upload()
        self.assertEqual(status, 200)
        self.assertEqual((uploaded['filename'], uploaded['triangles'], uploaded['vertices'], uploaded['materials']),
                         ('staff.glb', 1, 3, 1))
        self.assertEqual(uploaded['sha256'], hashlib.sha256(self.glb.read_bytes()).hexdigest())
        stored = self.app.weapons[uploaded['weapon_id']]['path']
        self.assertEqual(stored.parent, self.app.workspace / 'inputs')
        self.assertEqual(stored.read_bytes(), self.glb.read_bytes())
        status, result = self.upload('staff.vrm')
        self.assertEqual((status, result['error']), (400, 'GLBファイルを選んでください'))
        status, result = self.upload('broken.glb', b'not a glb')
        self.assertEqual(status, 400)
        self.assertTrue(result['error'].startswith('GLBを読み込めませんでした: '))
        self.assertEqual(sorted((self.app.workspace / 'inputs').iterdir()), [stored])
        with self.assertRaisesRegex(ValueError, 'VRM'):
            self.app.upload('staff.glb', self.glb.read_bytes())

    def test_glb_with_a_non_object_document_is_refused_and_removed(self):
        from inspect_vrm import write_glb
        for name, document in (('array.glb', []), ('mesh.glb', {'meshes': [{'primitives': [1]}]}),
                               ('accessors.glb', {'meshes': [{'primitives': [{'attributes': {'POSITION': 0}}]}],
                                                  'accessors': [[]]})):
            with self.subTest(name=name):
                path = self.root / name
                write_glb(path, document, b'')
                status, result = self.upload(name, path.read_bytes())
                self.assertEqual(status, 400)
                self.assertTrue(result['error'].startswith('GLBを読み込めませんでした: '), result)
                self.assertEqual(list((self.app.workspace / 'inputs').glob('*')), [])

    def test_weapon_base_without_skyrim_esm_says_so(self):
        game = self.root / 'empty-game'
        (game / 'Data').mkdir(parents=True)
        status, result = self.post('/api/weapon-base', {'game': str(game), 'base': 'StaffFlames'})
        self.assertEqual(status, 400)
        self.assertTrue(result['error'].startswith('Skyrim.esmが見つかりません。'), result)

    def test_conversion_and_weapon_preview_never_run_together(self):
        _, uploaded = self.upload()
        release = threading.Event()

        def slow(*args, **kwargs):
            release.wait(10)
            return {'output': str(self.root), 'previews': [], 'views': []}

        def fake_convert(source, game, blender, output, settings, progress=None, weapon_glb=None):
            release.wait(10)
            output.mkdir(parents=True)
            (output / 'Probe.zip').write_bytes(b'zip')
            return output / 'Probe.zip'

        request = {'source_id': 'avatar', 'game': str(self.root), 'blender': str(self.root),
                   'settings': self.settings(uploaded), 'weapon_id': uploaded['weapon_id']}
        with patch.object(self.app, 'catalog', return_value=self.catalog), patch('weapon_preview.preview', slow), \
                patch('wizard.doctor', return_value={'ready': True}), patch('wizard.convert', fake_convert):
            self.assertEqual(self.post('/api/weapon-preview', request)[0], 202)
            status, result = self.post('/api/jobs', request)
            self.assertEqual((status, result['error']), (400, 'プレビューまたは装備の編集を処理中です。完了してから変換してください'))
            release.set()
            self.app.executor.submit(lambda: None).result(timeout=10)
            release.clear()
            self.assertEqual(self.post('/api/jobs', request)[0], 202)
            status, result = self.post('/api/weapon-preview', request)
            self.assertEqual((status, result['error']), (400, '変換・プレビューの完了を待ってください'))
            release.set()
            self.app.executor.submit(lambda: None).result(timeout=10)

    def test_validation_requires_the_same_glb_only_when_asked(self):
        _, uploaded = self.upload()
        settings = self.settings(uploaded)
        with patch.object(self.app, 'catalog', return_value=self.catalog):
            request = {'source_id': 'avatar', 'game': str(self.root), 'settings': settings}
            self.assertEqual(self.post('/api/validate', {**request, 'check_weapon': False})[0], 200)
            status, result = self.post('/api/validate', request)
            self.assertEqual((status, result['error']), (400, 'オリジナル武器のGLBを選んでください'))
            status, result = self.post('/api/validate', {**request, 'weapon_id': uploaded['weapon_id']})
            self.assertEqual(status, 200)
            self.assertEqual(result['settings']['original_weapon'], settings['original_weapon'])
            other = self.settings({**uploaded, 'sha256': '0' * 64})
            status, result = self.post('/api/validate', {**request, 'settings': other, 'weapon_id': uploaded['weapon_id']})
            self.assertEqual(status, 400)
            self.assertIn('別のファイル', result['error'])
            official = {**settings, 'weapon_mode': 'official'}
            self.assertEqual(self.post('/api/validate', {**request, 'settings': official})[0], 200)

    def test_validation_checks_shouts_only_when_asked(self):
        # STEP 01-03 send check_shouts=false so a settings file with a shout whose DLC is missing
        # can still reach STEP 04, where the shout is shown and removable.
        def validate_settings(settings):
            if settings.shouts:
                raise ValueError('シャウト DLC1SoulTearShout (Dawnguard.esm:007CB6) には Dawnguard (Dawnguard.esm) が必要ですが、インストールされていません。')
        catalog = SimpleNamespace(validate_settings=validate_settings)
        request = {'source_id': 'avatar', 'game': str(self.root),
                   'settings': asdict(FollowerSettings(mod_name='Probe', shouts=['Dawnguard.esm:007CB6']))}
        with patch.object(self.app, 'catalog', return_value=catalog):
            status, result = self.post('/api/validate', {**request, 'check_shouts': False})
            self.assertEqual((status, result['settings']['shouts']), (200, []))
            malformed = {**request, 'settings': {**request['settings'], 'shouts': ['Skyrim.esm:13E07']}, 'check_shouts': False}
            self.assertEqual(self.post('/api/validate', malformed)[0], 200)
            for flags in ({}, {'check_shouts': True}):
                with self.subTest(flags=flags):
                    status, result = self.post('/api/validate', {**request, **flags})
                    self.assertEqual(status, 400)
                    self.assertIn('DLC1SoulTearShout', result['error'])

    def test_conversion_receives_the_glb_path_but_settings_do_not(self):
        _, uploaded = self.upload()
        captured = {}

        def fake_convert(source, game, blender, output, settings, progress=None, weapon_glb=None):
            captured.update(weapon_glb=weapon_glb, settings=asdict(settings))
            output.mkdir(parents=True)
            archive = output / 'Probe.zip'
            archive.write_bytes(b'zip')
            return archive

        with patch.object(self.app, 'catalog', return_value=self.catalog), \
                patch('wizard.doctor', return_value={'ready': True}), patch('wizard.convert', fake_convert):
            request = {'source_id': 'avatar', 'game': str(self.root), 'blender': str(self.root),
                       'settings': self.settings(uploaded)}
            status, result = self.post('/api/jobs', request)
            self.assertEqual((status, result['error']), (400, 'オリジナル武器のGLBを選んでください'))
            status, result = self.post('/api/jobs', {**request, 'weapon_id': uploaded['weapon_id']})
            self.assertEqual(status, 202)
            self.app.executor.submit(lambda: None).result(timeout=10)
        job = self.app.snapshot(result['job_id'])
        self.assertEqual((job['status'], job['weapon_mode']), ('complete', 'original'), job.get('error'))
        self.assertEqual(captured['weapon_glb'], self.app.weapons[uploaded['weapon_id']]['path'])
        saved = json.dumps(captured['settings'], ensure_ascii=False)
        self.assertNotIn(str(self.app.workspace), saved)
        self.assertNotIn(uploaded['weapon_id'], saved)
        self.assertEqual(captured['settings']['original_weapon']['sha256'], uploaded['sha256'])

    def test_base_size_is_measured_once_per_game(self):
        game = self.root / 'game'
        (game / 'Data').mkdir(parents=True)
        (game / 'Data/Skyrim.esm').write_bytes(b'master')
        measured = []

        def measure(workspace, data, catalog, base):
            measured.append(base)
            return {'base': base, 'kind': 'staff', 'model': 'x.nif', 'length': 134., 'grip': .52}

        with patch.object(self.app, 'catalog', return_value=self.catalog), patch('weapon_preview.base_dimensions', measure):
            for _ in range(2):
                status, result = self.post('/api/weapon-base', {'game': str(game), 'base': 'StaffFlames'})
                self.assertEqual((status, result['length'], result['grip']), (200, 134., .52))
        self.assertEqual(measured, ['StaffFlames'])

    def test_weapon_preview_job_passes_the_uploaded_glb(self):
        _, uploaded = self.upload()
        calls = []

        def fake_preview(workspace, source, glb, game, blender, settings, catalog, progress):
            progress('武器を持たせて描画しています…')
            calls.append((glb, settings.original_weapon))
            return {'output': str(workspace), 'previews': ['previews/weapon-x-drawn.png'], 'views': ['drawn']}

        with patch.object(self.app, 'catalog', return_value=self.catalog), patch('weapon_preview.preview', fake_preview):
            request = {'source_id': 'avatar', 'game': str(self.root), 'blender': str(self.root),
                       'settings': self.settings(uploaded), 'weapon_id': uploaded['weapon_id']}
            official = self.settings(uploaded, weapon_mode='official')
            status, result = self.post('/api/weapon-preview', {**request, 'settings': official})
            self.assertEqual((status, result['error']), (400, 'オリジナル武器を選んでください'))
            wrong = self.settings(uploaded)
            wrong['original_weapon'] = {**wrong['original_weapon'], 'base': 'Torch'}
            self.assertEqual(self.post('/api/weapon-preview', {**request, 'settings': wrong})[0], 400)
            status, result = self.post('/api/weapon-preview', request)
            self.assertEqual(status, 202)
            self.app.executor.submit(lambda: None).result(timeout=10)
        job = self.app.snapshot(result['job_id'])
        self.assertEqual((job['kind'], job['status'], job['stage']),
                         ('weapon_preview', 'complete', '武器のプレビューを更新しました'))
        self.assertEqual(calls, [(self.app.weapons[uploaded['weapon_id']]['path'], self.settings(uploaded)['original_weapon'])])
        self.assertEqual(job['previews'], ['previews/weapon-x-drawn.png'])
