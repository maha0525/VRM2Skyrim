"""Language-specific game data must never substitute Japanese for English."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from game_catalog import GameCatalog, SKILL_LABELS_EN
from official_catalog import OfficialCatalog
from plugin import Record


def string_table(text, extension='strings'):
    data = text.encode('utf8')+b'\0'
    if extension == 'dlstrings':
        data = struct.pack('<I', len(data))+data
    return struct.pack('<IIII', 1, len(data), 42, 0)+data


class LocalizationTests(unittest.TestCase):
    def test_english_tables_are_explicit_and_missing_english_is_not_japanese(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data/'Strings').mkdir()
            (data/'Strings/skyrim_japanese.strings').write_bytes(string_table('隠術'))
            (data/'Strings/skyrim_english.strings').write_bytes(string_table('Stealth'))
            self.assertEqual(GameCatalog.load_strings(data)[42], '隠術')
            self.assertEqual(GameCatalog.load_strings(data, language='english')[42], 'Stealth')
            (data/'Strings/skyrim_english.strings').unlink()
            self.assertEqual(GameCatalog.load_strings(data, language='english'), {})
            catalog = GameCatalog.__new__(GameCatalog)
            catalog.strings = {42: '隠術'}
            catalog.descriptions = {42: '説明'}
            catalog.english_strings = catalog.english_descriptions = {}
            record = Record(b'PERK', 1, 0, [(b'EDID', b'Stealth00\0'), (b'FULL', struct.pack('<I', 42)),
                                          (b'DESC', struct.pack('<I', 42))])
            self.assertEqual(catalog.localized(record), {'ja': '隠術', 'en': 'Stealth00'})
            self.assertEqual(catalog.localized(record, b'DESC'), {'ja': '説明', 'en': ''})

    def test_requested_language_archive_precedes_other_language_loose_file(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data/'Strings').mkdir()
            (data/'Strings/skyrim_english.strings').write_bytes(string_table('Stealth'))
            (data/'Skyrim - Interface.bsa').touch()
            with patch('localized_strings.BSA') as archive:
                archive.return_value.entries = {'strings/skyrim_japanese.strings': None}
                archive.return_value.read.return_value = string_table('隠術')
                self.assertEqual(GameCatalog.load_strings(data)[42], '隠術')
                self.assertEqual(GameCatalog.load_strings(data, language='english')[42], 'Stealth')

    def test_japanese_overrides_in_english_filenames_use_native_english_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data/'Strings').mkdir()
            (data/'Strings/skyrim_english.strings').write_bytes(string_table('隠術'))
            (data/'Skyrim - Interface.bsa').touch()
            with patch('localized_strings.BSA') as archive:
                archive.return_value.entries = {'strings/skyrim_english.strings': None}
                archive.return_value.read.return_value = string_table('Stealth')
                self.assertEqual(GameCatalog.load_strings(data, language='english')[42], 'Stealth')
                archive.return_value.read.return_value = string_table('隠術')
                self.assertEqual(GameCatalog.load_strings(data, language='english'), {})

    def test_official_equipment_uses_separate_language_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data/'strings').mkdir()
            (data/'strings/skyrim_japanese.strings').write_bytes(string_table('鋼鉄の剣'))
            (data/'strings/skyrim_english.strings').write_bytes(string_table('Steel Sword'))
            catalog = OfficialCatalog.__new__(OfficialCatalog)
            catalog.data, catalog.archives, catalog.tables = data, {}, {}
            catalog.source, catalog.localized = {1: 'Skyrim.esm'}, {1: True}
            record = Record(b'ARMO', 1, 0, [(b'EDID', b'Equipment\0'), (b'FULL', struct.pack('<I', 42))])
            self.assertEqual(catalog.label(record), '鋼鉄の剣')
            self.assertEqual(catalog.label(record, language='en'), 'Steel Sword')
            self.assertEqual(catalog.label(record), '鋼鉄の剣')
            (data/'strings/skyrim_english.strings').unlink()
            catalog.tables.clear()
            self.assertEqual(catalog.label(record, language='en'), 'Equipment')

    def test_description_table_and_canonical_skill_names(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data/'Strings').mkdir()
            (data/'Strings/skyrim_english.dlstrings').write_bytes(string_table('Sneaking is 20% harder to detect.', 'dlstrings'))
            self.assertEqual(GameCatalog.load_strings(data, 'dlstrings', language='english')[42],
                             'Sneaking is 20% harder to detect.')
        self.assertEqual(SKILL_LABELS_EN['Sneak'], 'Sneak')
        self.assertEqual(SKILL_LABELS_EN['Marksman'], 'Archery')
        self.assertEqual(SKILL_LABELS_EN['Speechcraft'], 'Speech')
