"""A separate local HTTP server with an isolated output directory; no game writes."""
from http.server import ThreadingHTTPServer
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wizard import WizardApplication, handler_for  # noqa: E402

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    app = WizardApplication(ROOT/'build/ui-live-feedback')
    server = ThreadingHTTPServer(('127.0.0.1', int(sys.argv[1])), handler_for(app))
    print('Isolated wizard ready', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        app.close()
