"""A local browser wizard; VRM data and game assets remain on this computer."""
import argparse
import errno
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib
import logging
import mimetypes
import socket
import sys
from pathlib import Path
import threading
from urllib.parse import parse_qs, unquote, urlparse
import uuid
import webbrowser

from converter import ROOT, convert, doctor, run_blender
from environment import find_blender, find_game
from game_catalog import GameCatalog
from inspect_vrm import inspect
from settings import FollowerSettings, VERSION
from wardrobe import validate_source


def source_fingerprint():
    paths = sorted(ROOT.glob('*.py')) + sorted((ROOT/'web').glob('*'))
    digest = hashlib.sha256()
    for path in paths:
        if path.is_file():
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


BOOT_FINGERPRINT = source_fingerprint()


class WizardHTTPServer(ThreadingHTTPServer):
    # Windows SO_REUSEADDR can report success while requests reach an old
    # listener. SO_EXCLUSIVEADDRUSE excludes reusable same-address listeners.
    allow_reuse_address = False
    allow_reuse_port = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def make_server(app, port):
    handler = handler_for(app)
    try:
        # Windows permits a specific-address bind beside some legacy wildcard
        # SO_REUSEADDR listeners even with SO_EXCLUSIVEADDRUSE. Detect those
        # before binding; do not issue an HTTP request to the other app.
        if port and port_is_listening(port):
            raise OSError(errno.EADDRINUSE, 'A listener already responds on this port')
        return WizardHTTPServer(('127.0.0.1', port), handler)
    except OSError as error:
        # Windows reports an exclusive-address collision as either of these.
        if port == 0 or (error.errno not in (errno.EADDRINUSE, errno.EACCES)
                         and getattr(error, 'winerror', None) not in (10048, 10013)):
            raise
        server = WizardHTTPServer(('127.0.0.1', 0), handler)
        logging.warning('Port %s is occupied or unavailable (%s). '
                        'Opening this wizard at http://127.0.0.1:%s; existing processes are unchanged.',
                        port, error, server.server_address[1])
        return server


def port_is_listening(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.25):
            return True
    except ConnectionRefusedError:
        return False
    except TimeoutError:
        # Windows can delay connection-refused notifications past this probe.
        # A timeout is not evidence of a listener; exclusive bind decides next.
        return False


def armor_environment(game):
    from skypatcher import installation_status
    return installation_status(Path(game)/'Data') if game else None


class WizardApplication:
    def __init__(self, workspace=None):
        self.workspace = Path(workspace or ROOT / "build/wizard").resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.sources = {}
        self.source_reports = {}
        self.jobs = {}
        self.catalogs = {}
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1)
        for path in self.workspace.glob('*/wizard-job.json'):
            try:
                job = json.loads(path.read_text(encoding='utf8'))
                uuid.UUID(hex=job['id'])
                if (job['status'] == 'complete' and Path(job['output']).resolve() == path.parent and
                        Path(job['archive']).name == job['archive'] and (path.parent/job['archive']).is_file()):
                    self.jobs[job['id']] = job
            except (ValueError, OSError, KeyError, TypeError):
                logging.warning('Could not restore completed wizard result: %s', path)

    def remember_job(self, job):
        output = Path(job['output']).resolve()
        if output.parent != self.workspace:
            raise ValueError('Completed output is outside the wizard workspace')
        (output/'wizard-job.json').write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding='utf8')

    def catalog(self, game):
        path = Path(game).resolve() / "Data"
        key = (str(path), (path / "Skyrim.esm").stat().st_mtime_ns)
        if key not in self.catalogs:
            self.catalogs[key] = GameCatalog(path)
        return self.catalogs[key]

    def upload(self, name, blob):
        if Path(name).suffix.lower() != ".vrm":
            raise ValueError("VRMファイルを選んでください")
        source_id = uuid.uuid4().hex
        path = self.workspace / "inputs" / (source_id + ".vrm")
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(blob)
        report = inspect(path)
        self.sources[source_id] = path
        self.source_reports[source_id] = report
        return {"source_id": source_id, "filename": Path(name).name,
                "triangles": report["total_triangles"], "mesh_count": len(report["parts"]),
                "parts": report["parts"], "sha256": report["sha256"],
                "suggested_name": report.get("vrm_meta", {}).get("name") or report.get("vrm_meta", {}).get("title") or Path(name).stem,
                "has_morphs": any(mesh["morphs"] for mesh in report["meshes"])}

    def start(self, request):
        source = self.sources.get(request.get("source_id"))
        if source is None:
            raise ValueError("先にVRMを選択してください")
        settings = FollowerSettings.from_dict(request["settings"])
        validate_source(settings, self.source_reports[request["source_id"]])
        game, blender = Path(request["game"]), Path(request["blender"])
        self.catalog(game).validate_settings(settings)
        checks = doctor(game, blender)
        if not all(checks.values()):
            raise ValueError("必要な環境が未設定です: " + ", ".join(key for key, value in checks.items() if not value))
        with self.lock:
            if any(job["status"] in ("queued", "running") for job in self.jobs.values()):
                raise ValueError("変換中です。完了してから次のモデルを変換してください")
            job_id = uuid.uuid4().hex
            output = self.workspace / f"{settings.mod_id}_{datetime.now():%Y%m%d_%H%M%S}_{job_id[:8]}"
            job = {"id": job_id, "status": "queued", "stage": "準備中", "output": str(output),
                   "npc_name": settings.npc_name, "plugin_name": settings.plugin_name, "events": []}
            job["armor_support"] = settings.armor_support
            job["garments"] = [{"id": g["id"], "name": g["name"]} for g in settings.appearance_parts.get("garments", [])] if settings.armor_support else []
            self.jobs[job_id] = job
        self.executor.submit(self._run, job, source, game, blender, output, settings)
        return {"job_id": job_id}

    def start_preview(self, request):
        source_id = request.get("source_id")
        source = self.sources.get(source_id)
        if source is None:
            raise ValueError("先にVRMを選択してください")
        settings = FollowerSettings.from_dict(request["settings"])
        if not settings.armor_support:
            raise ValueError("衣服の分離を有効にしてください")
        validate_source(settings, self.source_reports[source_id])
        blender = Path(request["blender"])
        if not blender.is_file():
            raise ValueError("Blenderの実行ファイルを確認してください")
        wardrobe = request.get("wardrobe", "all")
        valid = {"all", "underwear"} | {"without:" + g["id"] for g in settings.appearance_parts["garments"]}
        if wardrobe not in valid:
            raise ValueError("Unknown preview wardrobe")
        with self.lock:
            if any(job["status"] in ("queued", "running") for job in self.jobs.values()):
                raise ValueError("変換・プレビューの完了を待ってください")
            job_id = uuid.uuid4().hex
            output = self.workspace / "classification" / job_id
            job = {"id": job_id, "kind": "source_preview", "status": "queued", "output": str(output),
                   "stage": "分類を描画中", "events": []}
            self.jobs[job_id] = job
        self.executor.submit(self._run_preview, job, source, blender, output, settings, wardrobe)
        return {"job_id": job_id}

    def start_edit(self, job_id, mesh_key, blob, blender):
        original = self.snapshot(job_id)
        if original.get('armor_patch') and original.get('armor_registration') != 'skypatcher':
            raise ValueError('これは旧式パッチを使う変換結果です。SkyPatcher方式へ移行するには、このフォロワーを再出力してください。')
        if original['status'] != 'complete' or mesh_key not in {i['key'] for i in original.get('edit_meshes', [])}:
            raise ValueError('変換済みの装備を選んでください')
        with self.lock:
            if any(job['status'] in ('queued', 'running') for job in self.jobs.values()):
                raise ValueError('変換・編集の完了を待ってください')
            handle = uuid.uuid4().hex
            path = self.workspace/'edits'/(handle+'.nif')
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(blob)
            job = {**original, 'id': handle, 'kind': 'equipment_edit', 'status': 'queued', 'stage': '仕上げた装備を取り込み中', 'events': []}
            self.jobs[handle] = job
        self.executor.submit(self._run_edit, job, mesh_key, path, Path(blender))
        return {'job_id': handle}

    def start_head_preview(self, request):
        source_id = request.get('source_id')
        if source_id not in self.sources:
            raise ValueError('先にVRMを選択してください')
        settings = FollowerSettings.from_dict(request['settings'])
        if not settings.armor_support:
            raise ValueError('衣服・防具の対応を有効にしてください')
        validate_source(settings, self.source_reports[source_id])
        from official_catalog import OfficialCatalog
        catalog = OfficialCatalog(Path(request['game'])/'Data')
        armor = catalog.require(request['armor'], b'ARMO')
        addons = catalog.addon_records(armor, settings.sex)
        from armor_catalog import slot_mask
        if not any(slot_mask(a) & 0x3803 for a in addons):
            raise ValueError('プレビューする頭装備を選んでください')
        policy = request.get('policy', {})
        if set(policy) != {'hide_face', 'hide_hair'} or any(type(v) is not bool for v in policy.values()):
            raise ValueError('Invalid preview visibility')
        settings.fit_mode = 'selected'
        settings.fit_armors = [catalog.key(armor)]
        key = uuid.uuid4().hex
        output = self.workspace/'head-previews'/key
        with self.lock:
            if any(j['status'] in ('queued', 'running') for j in self.jobs.values()):
                raise ValueError('変換・プレビューの完了を待ってください')
            job_id = uuid.uuid4().hex
            job = dict(id=job_id, kind='head_preview', status='queued', output=str(output),
                       stage='頭装備を体型へ合わせています', events=[])
            self.jobs[job_id] = job
        self.executor.submit(self._run_head_preview, job, self.sources[source_id], Path(request['game']),
                             Path(request['blender']), settings, policy)
        return {'job_id': job_id}

    def _run_head_preview(self, job, source, game, blender, settings, policy):
        job['status'] = 'running'
        try:
            from head_preview import preview

            def progress(stage):
                with self.lock:
                    job['stage'] = stage
                logging.info('Head preview stage: %s', stage)

            result = preview(self.workspace, source, game, blender, settings, settings.fit_armors[0], policy, progress)
            with self.lock:
                job.update(result, status='complete', stage='頭装備のプレビューを更新しました')
        except Exception as error:
            logging.exception('Headgear preview failed')
            with self.lock:
                job.update(status='failed', error=str(error))

    def _run_edit(self, job, mesh_key, path, blender):
        job['status'] = 'running'
        try:
            from outfit_edits import apply_edit
            output = Path(job['output'])
            archive = apply_edit(output, mesh_key, path, blender)
            with self.lock:
                job.update(status='complete', archive=archive.name, stage='仕上げた装備をMODへ反映しました')
            self.remember_job(job)
        except Exception as error:
            logging.exception('Equipment finishing import failed')
            with self.lock:
                job.update(status='failed', error=str(error))

    def _run_preview(self, job, source, blender, output, settings, wardrobe):
        job["status"] = "running"
        try:
            output.mkdir(parents=True)
            settings.save(output / "settings.json")
            run_blender(blender, "render_source.py", ["--source", source, "--output", output, "--wardrobe", wardrobe], output, "Source classification")
            with self.lock:
                job.update(status="complete", previews=["front.png", "back.png"])
        except Exception as error:
            logging.exception("Classification preview failed")
            with self.lock:
                job.update(status="failed", error=str(error))

    def _run(self, job, source, game, blender, output, settings):
        job["status"] = "running"

        def progress(name):
            with self.lock:
                job["stage"] = name
                job["events"].append(name)

        try:
            archive = convert(source, game, blender, output, settings, progress)
            with self.lock:
                job.update(status="complete", archive=archive.name,
                           previews=sorted(path.relative_to(output).as_posix() for path in (output / "previews").glob("*.png")),
                           game_verified=False)
                if settings.fitting_enabled:
                    job["armor_registration"] = "skypatcher"
                    fitting = json.loads((output/'armor-fitting.json').read_text(encoding='utf8'))
                    job['fit_armors'] = list(dict.fromkeys(i['editor_id'] for i in fitting['equipment']))
                    job['edit_kit'] = 'OutfitStudio-EditKit.zip'
                    job['edit_meshes'] = list({i['source_key']: {'key': i['source_key'], 'name': i['editor_id']}
                                              for i in fitting['equipment']}.values())
            self.remember_job(job)
        except Exception as error:
            logging.exception("Wizard conversion failed")
            with self.lock:
                job.update(status="failed", error=str(error))

    def snapshot(self, job_id):
        with self.lock:
            if job_id not in self.jobs:
                raise ValueError("変換ジョブが見つかりません")
            return dict(self.jobs[job_id])

    def close(self):
        self.executor.shutdown(wait=True)


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, message, *args):
            logging.debug(message, *args)

        def trusted(self):
            port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host") not in hosts:
                raise ValueError("Invalid Host")
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + host for host in hosts}:
                raise ValueError("Invalid Origin")

        def reply(self, value, status=200):
            blob = json.dumps(value, ensure_ascii=False).encode("utf8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(blob)

        def file(self, path, attachment=False):
            blob = path.read_bytes()
            if path.resolve() == (ROOT / 'web/index.html').resolve():
                # One version source for the startup banner, API and page.
                # Source fingerprints still reject a server left alive during
                # an update; the HTML must not need a second manual version bump.
                blob = blob.replace(b'__CONVERTER_VERSION__', VERSION.encode('utf8'))
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            if attachment:
                self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
            self.end_headers()
            self.wfile.write(blob)

        def do_GET(self):
            try:
                self.trusted()
                url = urlparse(self.path)
                if url.path == "/api/environment":
                    return self.reply({"game": str(find_game() or ""), "blender": str(find_blender() or ""),
                                       "defaults": asdict(FollowerSettings()), "version": VERSION,
                                       "restart_required": source_fingerprint() != BOOT_FINGERPRINT,
                                        "armor_registration": armor_environment(find_game())})
                if url.path == '/api/jobs':
                    with app.lock:
                        return self.reply({'jobs': [dict(job) for job in app.jobs.values()
                                                   if job['status'] == 'complete' and job.get('plugin_name')]})
                if url.path == '/api/patch-status':
                    query = parse_qs(url.query)
                    job = app.snapshot(query.get('job', [''])[0])
                    from skypatcher import installation_status
                    return self.reply(installation_status(Path(query.get('game', [''])[0])/'Data', job.get('plugin_name'), job['output']))
                if url.path.startswith("/api/jobs/"):
                    job_id = url.path.split("/")[3]
                    job = app.snapshot(job_id)
                    if url.path.endswith("/file"):
                        name = parse_qs(url.query).get("name", [""])[0]
                        output = Path(job["output"]).resolve()
                        path = (output / name).resolve()
                        if not path.is_relative_to(output) or path.suffix.lower() not in {".png", ".zip", ".json", ".log", ".txt"}:
                            raise ValueError("Invalid output file")
                        return self.file(path, attachment=path.suffix == ".zip")
                    return self.reply(job)
                relative = "index.html" if url.path == "/" else url.path.lstrip("/")
                root = (ROOT / "web").resolve()
                path = (root / unquote(relative)).resolve()
                if not path.is_relative_to(root):
                    raise ValueError("Invalid path")
                return self.file(path)
            except (ValueError, OSError, KeyError) as error:
                self.reply({"error": str(error)}, 400)

        def do_POST(self):
            try:
                self.trusted()
                if source_fingerprint() != BOOT_FINGERPRINT:
                    logging.warning('Wizard sources changed after startup; refusing mixed-version request')
                    return self.reply({'error': '更新を反映するため、ウィザードのターミナルで Ctrl+C を押し、Launch.cmd を開き直してください。',
                                       'restart_required': True}, 409)
                size = int(self.headers.get("Content-Length", "0"))
                limit = 512 * 1024 * 1024 if self.path in ('/api/source', '/api/equipment-edit') else 1024 * 1024
                if not 0 < size <= limit:
                    raise ValueError("File/request exceeds size limit")
                blob = self.rfile.read(size)
                if len(blob) != size:
                    raise ValueError("Incomplete upload")
                if self.path == '/api/equipment-edit':
                    return self.reply(app.start_edit(self.headers.get('X-Job-Id'), self.headers.get('X-Mesh-Key'), blob,
                                                     unquote(self.headers.get('X-Blender', ''))), 202)
                if self.path == "/api/source":
                    return self.reply(app.upload(unquote(self.headers.get("X-Filename", "avatar.vrm")), blob))
                request = json.loads(blob)
                if self.path == "/api/catalog":
                    catalog = app.catalog(request["game"])
                    return self.reply({"choices": catalog.json_choices(request.get('sex', 'female')), "checks": doctor(request["game"], request["blender"])})
                if self.path == "/api/validate":
                    settings = FollowerSettings.from_dict(request["settings"])
                    if settings.armor_support:
                        source_id = request.get("source_id")
                        if source_id not in app.source_reports:
                            raise ValueError("先にVRMを選択してください")
                        validate_source(settings, app.source_reports[source_id])
                    app.catalog(request["game"]).validate_settings(settings)
                    return self.reply({"settings": asdict(settings)})
                if self.path == "/api/jobs":
                    return self.reply(app.start(request), 202)
                if self.path == "/api/appearance-preview":
                    return self.reply(app.start_preview(request), 202)
                if self.path == '/api/head-preview':
                    return self.reply(app.start_head_preview(request), 202)
                if self.path == "/api/armor-patch":
                    raise ValueError("共有防具パッチは廃止されました。体型合わせを使うフォロワーを再出力してください。")
                raise ValueError("Unknown API")
            except (ValueError, OSError, KeyError, TypeError, IndexError) as error:
                logging.info("Wizard request rejected: %s", error)
                self.reply({"error": str(error)}, 400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description="VRM2Skyrim guided follower creation")
    parser.add_argument("--port", type=int, default=8768)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.info('Python runtime: %s (%s)', sys.executable, sys.version.split()[0])
    app = WizardApplication()
    server = None
    try:
        server = make_server(app, args.port)
        url = f"http://127.0.0.1:{server.server_address[1]}"
        print(f"VRM2Skyrim {VERSION}: {url}\nCtrl+C to stop", flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.server_close()
        app.close()


if __name__ == "__main__":
    main()
