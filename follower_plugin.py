"""Keep private IDs canonical in conversion while encoding additional official masters."""

import copy
import struct

from plugin import records, write_plugin


# Internally slot 0 is Skyrim, slot 1 is this follower; optional masters start at 2.
# On disk all masters precede the follower. Never remap numeric/material payloads.
REFS = {
    # SPLO: spells stay index 0; DLC shouts use 2+ like SNDD.
    b"NPC_": {b"RNAM", b"WNAM", b"DOFT", b"PNAM", b"ZNAM", b"SPLO"},
    b"RACE": {b"WNAM", b"HEAD"},
    b"ARMO": {b"RNAM", b"MODL"},
    b"ARMA": {b"RNAM", b"MODL", b"SNDD"},
    b"FLST": {b"LNAM"},
    b"OTFT": {b"INAM"},
    b"HDPT": {b"RNAM"},
    b"ACHR": {b"NAME"},
    # WEAP/STAT MODL is a path string, unlike ARMO MODL; only WNAM is a FormID.
    b"WEAP": {b"WNAM"},
}


def remap(record, mapping):
    result = copy.deepcopy(record)

    def resolve(value):
        return (
            (mapping.get(value >> 24, value >> 24) << 24 | (value & 0xFFFFFF))
            if value
            else 0
        )

    result.form_id = resolve(result.form_id)
    fields = []
    for tag, payload in result.fields:
        if tag in REFS.get(result.kind, set()):
            payload = b"".join(
                struct.pack("<I", resolve(n))
                for (n,) in struct.iter_unpack("<I", payload)
            )
        elif tag == b"VMAD":
            from official_catalog import vmad_refs

            payload = vmad_refs(payload, resolve)
        elif result.kind == b"RELA" and tag == b"DATA":
            payload = (
                b"".join(
                    struct.pack("<I", resolve(n))
                    for (n,) in struct.iter_unpack("<I", payload[:8])
                )
                + payload[8:]
            )
        elif result.kind == b"NPC_" and tag == b"CNTO":
            payload = (
                struct.pack("<I", resolve(struct.unpack_from("<I", payload)[0]))
                + payload[4:]
            )
        fields.append((tag, payload))
    result.fields = fields
    result.groups = tuple(
        (
            struct.pack("<I", resolve(struct.unpack("<I", label)[0]))
            if kind in (6, 8, 9)
            else label,
            kind,
        )
        for label, kind in result.groups
    )
    return result


def write_follower(path, items, *, author, placement, extra_masters=()):
    masters = ["Skyrim.esm", *extra_masters]
    mapping = {1: len(masters), **{i + 2: i + 1 for i in range(len(extra_masters))}}
    write_plugin(
        path,
        [remap(r, mapping) for r in items],
        author=author,
        placement=tuple(remap(r, mapping) for r in placement),
        masters=masters,
    )


def follower_records(path):
    parsed = list(records(path))
    header = next(r for r in parsed if r.kind == b"TES4")
    count = len(header.values(b"MAST"))
    mapping = {count: 1, **{i: i + 1 for i in range(1, count)}}
    return [r if r.kind == b"TES4" else remap(r, mapping) for r in parsed]
