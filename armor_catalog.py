"""Resolve playable humanoid equipment from actual master records."""
import struct

HUMAN_SLOTS = set(range(30, 50)) | set(range(53, 62))


def partition_slot(partition, fallback):
    # Skyrim's helmet partitions 130/131/142 use the same biped layer as
    # 30/31/42. A zero partition is an unpartitioned shape, not biped slot 0.
    slot = partition % 100 if partition >= 100 else partition
    if slot == 0:
        return fallback
    if slot not in HUMAN_SLOTS:
        raise ValueError(f'Unsupported native equipment partition: {partition}')
    return slot


def native_partition(partition, fallback):
    """Keep helmet/hood partition semantics; map only for equipment masks."""
    slot = partition_slot(partition, fallback)
    return int(partition) if partition >= 100 else slot


def official_choices(catalog, sex='female'):
    result = []
    for armor in catalog.choices(b'ARMO'):
        if armor.flags & (4 | 0x20) or not armor.values(b'FULL') or not (armor.values(b'BOD2') or armor.values(b'BODT')):
            continue
        mask = slot_mask(armor)
        addons = catalog.addon_records(armor, sex)
        if mask and addons and all(slot_mask(a) and not slot_mask(a) & ~sum(1 << (s-30) for s in HUMAN_SLOTS) for a in addons):
            result.append(armor)
    return result


def head_policy(settings, addon, key):
    mask = slot_mask(addon)
    if not mask & sum(1 << (s-30) for s in (30, 31, 41, 42, 43)):
        return {'hide_face': False, 'hide_hair': False}
    value = {'hide_face': settings.head_defaults['hide_face'],
             'hide_hair': settings.head_defaults['hide_hair'] and bool(mask & (1 << 1))}
    value.update(settings.head_overrides.get(key, {}))
    return value


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
