"""Run real old/new HTTP listeners and the browser startup regression in isolation."""
from http.server import ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wizard import WizardApplication, handler_for, make_server  # noqa: E402


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as directory:
        old_app = WizardApplication(Path(directory)/'old')
        new_app = WizardApplication(Path(directory)/'new')

        class OldHandler(handler_for(old_app)):
            def do_GET(self):
                if self.path == '/api/environment':
                    return self.reply({'version': '0.9.5-dev'})
                return super().do_GET()

        servers = [ThreadingHTTPServer(('127.0.0.1', 0), OldHandler)]
        workers = []
        try:
            servers.append(make_server(new_app, servers[0].server_address[1]))
            for server in servers:
                worker = threading.Thread(target=server.serve_forever)
                worker.start()
                workers.append(worker)
            urls = [f'http://127.0.0.1:{s.server_address[1]}' for s in servers]
            subprocess.run([shutil.which('node') or 'C:/Program Files/nodejs/node.exe',
                            str(ROOT/'tests/browser-startup.cjs'), *urls], check=True)
        finally:
            for server in servers[:len(workers)]:
                server.shutdown()
            for worker in workers:
                worker.join()
            for server in servers:
                server.server_close()
            old_app.close()
            new_app.close()
