"""Isolated real wizard HTTP fixture for the SkyPatcher install workflow."""
import json
from pathlib import Path
import sys
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from wizard import WizardApplication, make_server
from settings import VERSION

root = Path(sys.argv[1]).resolve()
game = root/'game'
data = game/'Data'
data.mkdir(parents=True, exist_ok=True)
(data/'VRM2SkyrimArmorPatch.esp').write_bytes(b'legacy patch marker')
app = WizardApplication(root/'jobs')
for name, mode in [('Fitted', 'skypatcher'), ('Plain', ''), ('Legacy', 'legacy')]:
    output = app.workspace/name
    output.mkdir(parents=True, exist_ok=True)
    (output/'follower.zip').write_bytes(b'fixture download')
    job = dict(id=uuid.uuid4().hex, status='complete', output=str(output), archive='follower.zip',
               npc_name=name, plugin_name=name+'.esp', previews=[])
    if mode == 'skypatcher':
        (data/(name+'.esp')).write_bytes(b'fixture ESP')
        for kind in ('armor', 'formList'):
            config = output/'mod/SKSE/Plugins/SkyPatcher'/kind/'VRM2Skyrim'/(name+'.esp.ini')
            config.parent.mkdir(parents=True, exist_ok=True)
            config.write_text('; generated config')
        job['armor_registration'] = mode
    if mode == 'legacy':
        job['armor_patch'] = 'armor-patch/VRM2SkyrimArmorPatch.zip'
    app.jobs[job['id']] = job
with patch('wizard.find_game', return_value=game):
    server = make_server(app, 0)
    print(json.dumps(dict(port=server.server_address[1], version=VERSION, game=str(game))), flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        app.close()
