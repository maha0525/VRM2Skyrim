"""Read local game translations without treating Japanese English-file overrides as English."""
import logging
from pathlib import Path
import re
import struct

from bsa import BSA

JAPANESE = re.compile('[\u3040-\u30ff\u3400-\u9fff]')


def decode_table(blob, extension):
    if len(blob) < 8:
        raise ValueError('Invalid localized string table header')
    count, size = struct.unpack_from('<II', blob)
    start = 8+count*8
    if start+size > len(blob):
        raise ValueError('Invalid localized string table size')
    result = {}
    for index in range(count):
        key, offset = struct.unpack_from('<II', blob, 8+index*8)
        if offset >= size:
            raise ValueError('Invalid localized string offset')
        position = start+offset
        if extension == 'dlstrings':
            if position+4 > start+size:
                raise ValueError('Invalid localized description length')
            length = struct.unpack_from('<I', blob, position)[0]
            if position+4+length > start+size:
                raise ValueError('Invalid localized description size')
            value = blob[position+4:position+4+length].rstrip(b'\0')
        else:
            value = blob[position:blob.index(b'\0', position, start+size)]
        result[key] = value.decode('utf8', 'replace')
    return result


def load_table(data, plugin, extension='strings', languages=('japanese', 'english'), archives=None):
    data = Path(data)
    archives = {} if archives is None else archives
    names = ['Skyrim - Interface.bsa'] if plugin.lower() in ('skyrim.esm', 'update.esm') else [Path(plugin).stem+'.bsa']
    if plugin.lower() in ('dawnguard.esm', 'hearthfires.esm', 'dragonborn.esm'):
        names.append('Skyrim - Interface.bsa')  # Special Edition ships the DLC tables there.
    for language in languages:
        filename = f'{Path(plugin).stem.lower()}_{language}.{extension}'
        loose = next((p for p in (data/'Strings'/filename, data/'strings'/filename) if p.is_file()), None)
        table = decode_table(loose.read_bytes(), extension) if loose else {}
        if language != 'english' and table:
            return table
        # Japanese game setups sometimes put Japanese translations under an English filename.
        # Resolve those entries from the original English BSA instead of retranslating names.
        ignored = sum(bool(JAPANESE.search(value)) for value in table.values()) if language == 'english' else 0
        if table and not ignored:
            return table
        packaged = {}
        for name in names:
            if not (data/name).is_file():
                continue
            if name not in archives:
                archives[name] = BSA(data/name)
            archive = archives[name]
            relative = 'strings/'+filename
            if relative in archive.entries:
                packaged = decode_table(archive.read(relative), extension)
                break
        if language == 'english':
            packaged = {key: value for key, value in packaged.items() if not JAPANESE.search(value)}
            packaged.update({key: value for key, value in table.items() if not JAPANESE.search(value)})
            if ignored:
                logging.warning('Ignored %d Japanese entries in %s; using native English archive strings or Editor IDs',
                                ignored, filename)
        if packaged:
            return packaged
    return {}
