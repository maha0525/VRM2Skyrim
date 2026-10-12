"""Detect old patches that trigger wardrobe switches without displaying armor."""
from pathlib import Path
import struct
import tempfile
import unittest

from armor_patch import installed_patch_status
from plugin import Record, write_plugin


class PatchDeploymentTests(unittest.TestCase):
    def test_missing_old_wrong_addon_and_correct_deployed_patch(self):
        profile = {'plugin': 'Avatar.esp', 'equipment': [
            dict(original_form_id=0x123, origin_plugin='Skyrim.esm', origin_local_id=0x123, addon_local_id=0x1000),
            dict(original_form_id=0x124, origin_plugin='Skyrim.esm', origin_local_id=0x124, addon_local_id=0x1001)]}
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            self.assertEqual(installed_patch_status(data, profile)['status'], 'missing')
            path = data/'VRM2SkyrimArmorPatch.esp'
            boot = Record(b'ARMO', 0x123, 0, [(b'EDID', b'Boots\0'), (b'MODL', struct.pack('<I', 0x01000880))])
            write_plugin(path, [boot], masters=['Skyrim.esm', 'Avatar.esp'])
            result = installed_patch_status(data, profile)
            self.assertEqual((result['installed_items'], result['missing_bindings']), (1, 2))
            boot.replace(b'MODL', struct.pack('<I', 0x01001000))
            hood = Record(b'ARMO', 0x124, 0, [(b'EDID', b'Hood\0'), (b'MODL', struct.pack('<I', 0x01001001))])
            write_plugin(path, [boot, hood], masters=['Skyrim.esm', 'Avatar.esp'])
            self.assertEqual(installed_patch_status(data, profile)['status'], 'current')
