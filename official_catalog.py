"""Official equipment with plugin-relative FormIDs resolved before merging."""
import copy
import logging
from pathlib import Path
import struct

from localized_strings import JAPANESE, load_table
from plugin import records

LOG = logging.getLogger(__name__)
BASE = ('Skyrim.esm', 'Update.esm', 'Dawnguard.esm', 'HearthFires.esm', 'Dragonborn.esm')
SINGLE_REFS = {b'RNAM', b'EITM', b'TNAM', b'YNAM', b'ZNAM', b'ETYP', b'BIDS', b'BAMT', b'MODL', b'SNDD'}


def vmad_refs(blob, resolve):
    """Remap Skyrim object properties, including object arrays, without editing scripts."""
    data = bytearray(blob)
    version, fmt, scripts = struct.unpack_from('<HHH', data)
    if version > 5 or fmt not in (1, 2):
        raise ValueError('Unsupported Skyrim VMAD object format')
    offset = 6

    def string():
        nonlocal offset
        size = struct.unpack_from('<H', data, offset)[0]
        offset += 2 + size

    def value(kind):
        nonlocal offset
        if kind == 1:
            position = offset + (4 if fmt == 2 else 0)
            struct.pack_into('<I', data, position, resolve(struct.unpack_from('<I', data, position)[0]))
            offset += 8
        elif kind == 2:
            string()
        elif kind in (3, 4):
            offset += 4
        elif kind == 5:
            offset += 1
        elif kind in (11, 12, 13, 14, 15):
            count = struct.unpack_from('<I', data, offset)[0]
            offset += 4
            for _ in range(count):
                value(kind - 10)
        else:
            raise ValueError(f'Unsupported VMAD property type {kind}')
    for _ in range(scripts):
        string()
        offset += 1
        count = struct.unpack_from('<H', data, offset)[0]
        offset += 2
        for _ in range(count):
            string()
            kind = data[offset]
            offset += 2
            value(kind)
    if offset != len(data):
        raise ValueError('Unexpected armor VMAD fragments/trailing bytes')
    return bytes(data)


def remap_record(record, resolve):
    result = copy.deepcopy(record)
    result.form_id = resolve(record.form_id)
    fields = []
    for tag, blob in result.fields:
        if tag in SINGLE_REFS or tag in (b'KWDA', b'LNAM'):
            if len(blob) % 4:
                raise ValueError(f'Invalid reference field {tag!r}')
            blob = b''.join(struct.pack('<I', resolve(n[0])) for n in struct.iter_unpack('<I', blob))
        elif tag in (b'MO2S', b'MO3S', b'MO4S', b'MO5S'):
            data = bytearray(blob)
            count = struct.unpack_from('<I', data)[0]
            offset = 4
            for _ in range(count):
                size = struct.unpack_from('<I', data, offset)[0]
                offset += 4 + size
                struct.pack_into('<I', data, offset, resolve(struct.unpack_from('<I', data, offset)[0]))
                offset += 8
            if offset != len(data):
                raise ValueError('Invalid alternate-texture references')
            blob = bytes(data)
        elif tag == b'VMAD':
            blob = vmad_refs(blob, resolve)
        elif record.kind == b'SHOU' and tag in (b'MDOB', b'SNAM'):
            # SHOU SNAM: word (WOOP), spell (SPEL), recovery time (float).
            count = 1 if tag == b'MDOB' else 2
            if len(blob) < 4 * count:
                raise ValueError(f'Invalid shout field {tag!r}')
            refs = struct.unpack_from(f'<{count}I', blob)
            blob = struct.pack(f'<{count}I', *(resolve(n) for n in refs)) + blob[4 * count:]
        fields.append((tag, blob))
    result.fields = fields
    return result


class OfficialCatalog:
    def __init__(self, data):
        self.data = Path(data)
        self.plugins = [n for n in BASE if (self.data / n).is_file()]
        self.plugins += sorted(p.name for p in self.data.glob('cc*') if p.suffix.lower() in ('.esm', '.esl'))
        self.indices = {n.casefold(): i for i, n in enumerate(self.plugins)}
        self.by_id, self.source, self.localized = {}, {}, {}
        self.tables = {}
        self.master_lists = {}
        self.archives = {}
        from shouts import SHOUTS
        # SHOU only from the plugins that own allowlisted shouts: a Creation's SHOU may reference a
        # master outside this catalog and must not break armor loading.
        shout_plugins = {plugin.casefold() for plugin, _, _ in SHOUTS}
        for name in self.plugins:
            kinds = {b'TES4', b'ARMO', b'ARMA', b'TXST'} | ({b'SHOU'} if name.casefold() in shout_plugins else set())
            loaded = list(records(self.data / name, kinds))
            header = next(r for r in loaded if r.kind == b'TES4')
            masters = [b.rstrip(b'\0').decode('utf8') for b in header.values(b'MAST')] + [name]
            self.master_lists[name] = masters[:-1]
            def resolve(value):
                if not value:
                    return 0
                index = value >> 24
                if index >= len(masters) or masters[index].casefold() not in self.indices:
                    raise ValueError(f'Unresolved master reference {name}:{value:08X}')
                return self.indices[masters[index].casefold()] << 24 | (value & 0xFFFFFF)
            for original in loaded:
                if original.kind == b'TES4':
                    continue
                record = remap_record(original, resolve)
                self.by_id[record.form_id] = record
                self.source[record.form_id] = name
                self.localized[record.form_id] = bool(header.flags & 0x80)
        # Editor IDs are not unique across plugins; shouts are found per owner plugin.
        self.by_editor_id = {r.editor_id: r for r in self.by_id.values() if r.editor_id and r.kind != b'SHOU'}
        self.by_plugin_editor_id = {(self.identity(r)[0].casefold(), r.editor_id): r
                                    for r in self.by_id.values() if r.editor_id and r.kind == b'SHOU'}
        LOG.info('Official equipment catalog: %s plugins, %s records', len(self.plugins), len(self.by_id))

    def identity(self, record):
        return self.plugins[record.form_id >> 24], record.form_id & 0xFFFFFF

    def key(self, record):
        name, local = self.identity(record)
        return f'{name}:{local:06X}'

    def require(self, key, kind=None):
        if ':' in key:
            name, local = key.split(':')
            record = self.by_id.get(self.indices.get(name.casefold(), 255) << 24 | int(local, 16))
        else:
            record = self.by_editor_id.get(key)
        if record is None or kind and record.kind != kind:
            raise ValueError(f'Official equipment not found: {key}')
        return record

    def find(self, plugin, editor_id, kind):
        """Record owned by plugin (its own FormID, not an override) with this Editor ID, or None."""
        record = self.by_plugin_editor_id.get((plugin.casefold(), editor_id))
        return record if record is not None and record.kind == kind else None

    def extra_masters(self, owners):
        """Masters besides Skyrim.esm that references into owners need, with their master chains."""
        needed = set(owners)
        while True:
            expanded = needed | {m for n in needed for m in self.master_lists[n]}
            if expanded == needed:
                break
            needed = expanded
        return [n for n in self.plugins if n in needed and n != 'Skyrim.esm']

    def follower_form_id(self, value, extras):
        """Catalog FormID as a follower-plugin reference: Skyrim.esm 0, extras from 2 (follower_plugin)."""
        owner = self.plugins[value >> 24]
        return (0 if owner == 'Skyrim.esm' else extras.index(owner) + 2) << 24 | (value & 0xFFFFFF)

    def choices(self, kind):
        return sorted((r for r in self.by_id.values() if r.kind == kind), key=lambda r: self.key(r))

    def fitted_item(self, equipment):
        if 'origin_plugin' in equipment:
            key = f"{equipment['origin_plugin']}:{equipment['origin_local_id']:06X}"
            record = self.require(key, b'ARMO')
            # Canonical indices are a catalog-local workspace, not saved identity.
            # Installing another Creation may move the owner in that workspace.
            if equipment['original_form_id'] & 0xFFFFFF != equipment['origin_local_id']:
                raise ValueError('Armor manifest has inconsistent local identity')
        else:
            record = self.require(equipment['editor_id'], b'ARMO')
            if record.form_id != equipment['original_form_id']:
                raise ValueError('Armor manifest does not match this game master')
        return record

    def addon_records(self, armor, sex):
        result = []
        # Human addons use DefaultRace (0x19), as does Skyrim's NakedTorso.
        for blob in armor.values(b'MODL'):
            addon = self.by_id.get(struct.unpack('<I', blob)[0])
            race = struct.pack('<I', 0x13746)  # NordRace: matches the private race's template.
            if addon and addon.values(b'RNAM') in ([struct.pack('<I', 0x19)], [race]) and (
                    addon.values(b'RNAM') == [race] or race in addon.values(b'MODL')) and self.model_tag(addon, sex):
                result.append(addon)
        return result

    @staticmethod
    def model_tag(addon, sex):
        """Female actors use the shared male model when no female model exists."""
        for tag in ((b'MOD3', b'MOD2') if sex == 'female' else (b'MOD2',)):
            if any(value.rstrip(b'\0') for value in addon.values(tag)):
                return tag
        return None

    def label(self, record, tag=b'FULL', language=None):
        values = record.values(tag)
        fallback = record.editor_id if tag == b'FULL' else ''
        if not values:
            return fallback
        if not self.localized[record.form_id]:
            text = values[0].rstrip(b'\0').decode('utf8', 'replace')
            return fallback if language == 'en' and JAPANESE.search(text) else text
        if len(values[0]) != 4:
            raise ValueError('Invalid localized equipment string')
        name = self.source[record.form_id]
        extension = 'dlstrings' if tag == b'DESC' else 'strings'
        key = name, extension, language
        if key not in self.tables:
            self.tables[key] = self._strings(name, extension, language)
        return self.tables[key].get(struct.unpack('<I', values[0])[0], fallback)

    def _strings(self, plugin, extension, language=None):
        return load_table(self.data, plugin, extension,
                          ('english',) if language == 'en' else ('japanese', 'english'), self.archives)

    def in_masters(self, record, masters):
        indices = {n.casefold(): i for i, n in enumerate(masters)}
        def resolve(value):
            if not value:
                return 0
            owner = self.plugins[value >> 24]
            return indices[owner.casefold()] << 24 | (value & 0xFFFFFF)
        return remap_record(record, resolve)
