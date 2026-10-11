"""Strict little-endian Skyrim records, used to clone only vanilla base records."""
from dataclasses import dataclass
from pathlib import Path
import struct
import zlib


@dataclass
class Record:
    kind: bytes
    form_id: int
    flags: int
    fields: list
    groups: tuple = ()

    @property
    def editor_id(self):
        return next((value.rstrip(b"\0").decode("utf-8", "replace")
                     for tag, value in self.fields if tag == b"EDID"), "")

    def values(self, tag):
        return [value for key, value in self.fields if key == tag]

    def replace(self, tag, value):
        # Replacements retain order, important for gender-dependent RACE fields.
        indices = [i for i, (key, _) in enumerate(self.fields) if key == tag]
        if indices:
            self.fields[indices[0]] = (tag, value)
            for i in reversed(indices[1:]):
                del self.fields[i]
        else:
            self.fields.append((tag, value))

    def remove(self, *tags):
        self.fields = [(key, value) for key, value in self.fields if key not in tags]

    def encode(self):
        payload = b"".join(subrecord(tag, value) for tag, value in self.fields)
        return struct.pack("<4sIIIIHH", self.kind, len(payload), self.flags & ~0x40000,
                           self.form_id, 0, 44, 0) + payload


def subrecord(tag, data):
    if len(tag) != 4:
        raise ValueError("Subrecord tags have four bytes")
    if len(data) > 65535:
        return b"XXXX\x04\0" + struct.pack("<I", len(data)) + tag + b"\0\0" + data
    return tag + struct.pack("<H", len(data)) + data


def parse_fields(payload):
    fields = []
    offset = 0
    extended = None
    while offset < len(payload):
        if len(payload) - offset < 6:
            raise ValueError("Truncated subrecord header")
        tag, size = struct.unpack_from("<4sH", payload, offset)
        offset += 6
        if tag == b"XXXX":
            if size != 4:
                raise ValueError("Malformed extended size")
            extended = struct.unpack_from("<I", payload, offset)[0]
            offset += 4
            continue
        size = extended if extended is not None else size
        extended = None
        value = payload[offset:offset + size]
        if len(value) != size:
            raise ValueError("Truncated subrecord")
        fields.append((tag, value))
        offset += size
    return fields


def records(path, kinds=None):
    data = Path(path).read_bytes()

    def walk(start, end, groups=()):
        offset = start
        while offset < end:
            if end - offset < 24:
                raise ValueError("Truncated record header")
            kind, size = struct.unpack_from("<4sI", data, offset)
            if kind == b"GRUP":
                if size < 24 or offset + size > end:
                    raise ValueError("Malformed group")
                label, group_type = struct.unpack_from("<4sI", data, offset + 8)
                yield from walk(offset + 24, offset + size, groups + ((label, group_type),))
                offset += size
                continue
            flags, form_id = struct.unpack_from("<II", data, offset + 8)
            stop = offset + 24 + size
            if stop > end:
                raise ValueError("Truncated record")
            if kinds is None or kind in kinds:
                payload = data[offset + 24:stop]
                if flags & 0x40000:
                    expected = struct.unpack_from("<I", payload)[0]
                    payload = zlib.decompress(payload[4:])
                    if len(payload) != expected:
                        raise ValueError("Bad compressed record")
                yield Record(kind, form_id, flags, parse_fields(payload), groups)
            offset = stop
    yield from walk(0, len(data))


def write_plugin(path, items, author="VRM2Skyrim", placement=None):
    by_kind = {}
    for item in items:
        by_kind.setdefault(item.kind, []).append(item)
    group_count = 0

    def group(label, kind, payload):
        nonlocal group_count
        group_count += 1
        return struct.pack("<4sI4sIHHHH", b"GRUP", 24 + len(payload), label, kind, 0, 0, 0, 0) + payload

    output = b""
    order = {kind: index for index, kind in enumerate((b"RACE", b"ARMO", b"NPC_", b"CELL", b"ARMA", b"OTFT", b"RELA"))}
    record_count = len(items)
    kinds = set(by_kind) | ({b"CELL"} if placement else set())
    for kind in sorted(kinds, key=lambda key: order.get(key, len(order))):
        if kind == b"CELL" and placement:
            if b"CELL" in by_kind:
                raise ValueError("Cell placement cannot be combined with a separate CELL record")
            cell, actor = placement
            if [kind for _, kind in cell.groups] != [0, 2, 3]:
                raise ValueError("Expected an interior cell in master block/sub-block groups")
            payload = group(struct.pack("<I", cell.form_id), 8, actor.encode())
            payload = group(struct.pack("<I", cell.form_id), 6, payload)
            payload = cell.encode() + payload
            for label, group_type in reversed(cell.groups):
                payload = group(label, group_type, payload)
            output += payload
            record_count += 2
        else:
            output += group(kind, 0, b"".join(item.encode() for item in by_kind[kind]))
    header = Record(b"TES4", 0, 0, [
        (b"HEDR", struct.pack("<fII", 1.7, record_count + group_count, 0x900)),
        (b"CNAM", author.encode() + b"\0"),
        (b"SNAM", b"VRM follower; generated by VRM2Skyrim\0"),
        (b"MAST", b"Skyrim.esm\0"), (b"DATA", b"\0" * 8),
    ])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(header.encode() + output)
