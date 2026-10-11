"""Resolve playable humanoid equipment from actual master records."""
import struct


def slot_mask(record):
    values = record.values(b"BOD2") or record.values(b"BODT")
    if not values:
        raise ValueError(f"Equipment has no body slots: {record.editor_id}")
    return struct.unpack_from("<I", values[0])[0]


def equipment_choices(catalog):
    base_race = catalog.require("NakedTorso", b"ARMA").values(b"RNAM")[0]
    addons = {r.form_id: r for r in catalog.choices(b"ARMA")}
    allowed = {1 << (s - 30) for s in (32, 33, 37)}
    result = []
    for armor in catalog.choices(b"ARMO"):
        if armor.flags & 4 or not (armor.values(b"BOD2") or armor.values(b"BODT")) or slot_mask(armor) not in allowed:
            continue
        matched = [addons.get(struct.unpack("<I", value)[0]) for value in armor.values(b"MODL")]
        matched = [a for a in matched if a and a.values(b"RNAM") == [base_race] and a.values(b"MOD2") and a.values(b"MOD3")
                   and (a.values(b"BOD2") or a.values(b"BODT")) and slot_mask(a) & slot_mask(armor)
                   and not slot_mask(a) & ~sum(1 << (s - 30) for s in (32, 33, 34, 37, 38))]
        if len(matched) == 1:
            result.append(armor)
    return result
