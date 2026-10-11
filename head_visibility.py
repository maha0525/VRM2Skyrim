"""Check engine-generated heads separately from the exported avatar meshes."""
import struct

HEAD_COVER_ID = 0x0100080B
HEAD_SLOTS = (30, 31, 41, 42, 43)
HEAD_MASK = sum(1 << (slot - 30) for slot in HEAD_SLOTS)


def validate_head_visibility(generated, settings):
    """Skin masks do not contribute to the engine's worn-item hiding mask."""
    by_name = {record.editor_id: record for record in generated}
    by_id = {record.form_id: record for record in generated}
    outfit = by_name[settings.prefix + "Outfit"]
    payload = b"".join(outfit.values(b"INAM"))
    equipped = [by_id[value[0]] for value in struct.iter_unpack("<I", payload)]
    worn_mask = 0
    for item in equipped:
        if item.kind != b"ARMO":
            raise ValueError("Initial outfit contains a non-armor record")
        worn_mask |= struct.unpack_from("<I", item.values(b"BOD2")[0])[0]
    if worn_mask & HEAD_MASK != HEAD_MASK:
        raise ValueError("Initial worn equipment does not hide the vanilla head/hair")
    if settings.armor_support:
        cover = by_id.get(HEAD_COVER_ID)
        if cover is None or cover not in equipped or not cover.flags & 4:
            raise ValueError("Hidden head cover is missing from the default outfit")
        mask, kind = struct.unpack("<II", cover.values(b"BOD2")[0])
        if mask != HEAD_MASK or kind != 2 or cover.values(b"MODL"):
            raise ValueError("Head cover must hide only native head slots without a mesh")
        if cover.values(b"DATA") != [struct.pack("<If", 0, 0.)] or cover.values(b"DNAM") != [struct.pack("<i", 0)]:
            raise ValueError("Head cover must have zero value, weight and armor rating")
        fixed = by_name.get(settings.prefix + "FixedAA")
        if settings.appearance_parts["fixed"] and (
                fixed is None or struct.unpack_from("<I", fixed.values(b"BOD2")[0])[0] != 1 << 30):
            raise ValueError("VRM fixed face/hair must remain in its independent slot 60")
    return {"native_head_hidden_by_default_outfit": True,
            "head_cover_slots": list(HEAD_SLOTS), "worn_mask": worn_mask,
            "game_verified": False}
