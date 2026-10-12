"""Build a private-race, fixed-appearance vanilla follower and temple placement."""
import argparse
import copy
import json
import logging
from pathlib import Path
import struct

from game_catalog import GameCatalog
from head_visibility import HEAD_COVER_ID, configure_native_head, head_records
from equipment_runtime import runtime_records, vmad, write_runtime
from plugin import Record, records, write_plugin
from settings import SKILLS, load_settings
from wardrobe import components, keyword_names

NPC_ID = 0x01000800
ARMOR_ID = 0x01000801
ADDON_ID = 0x01000802
OUTFIT_ID = 0x01000803
RACE_ID = 0x01000804
RELATIONSHIP_ID = 0x01000805
REFERENCE_ID = 0x01000806
SLOTS = (30, 31, 32, 33, 34, 37, 38, 41, 42, 43)
SLOT_MASK = sum(1 << (slot - 30) for slot in SLOTS)


def uint(value):
    return struct.pack("<I", value)


def text(value):
    return value.encode("utf8") + b"\0"


def before(record, tag, additions):
    index = next(i for i, (key, _) in enumerate(record.fields) if key == tag)
    record.fields[index:index] = additions


def after(record, tag, additions):
    index = next(i for i, (key, _) in enumerate(record.fields) if key == tag)
    record.fields[index + 1:index + 1] = additions


def appearance_records(settings, catalog):
    """Build either the original fixed appearance or independent skin/clothes."""
    path = settings.asset_dir.replace("/", "\\")
    if not settings.armor_support:
        addon = Record(b"ARMA", ADDON_ID, 0, [
            (b"EDID", text(settings.prefix + "AppearanceAA")),
            (b"BOD2", struct.pack("<II", SLOT_MASK, 2)), (b"RNAM", uint(RACE_ID)),
            (b"DNAM", bytes((10, 10, 0, 0, 2, 0, 0, 0)) + struct.pack("<f", 0.)),
            (b"MOD2", text(path + "\\avatar.nif")), (b"MOD3", text(path + "\\avatar.nif"))])
        armor = Record(b"ARMO", ARMOR_ID, 4, [
            (b"EDID", text(settings.prefix + "Appearance")), (b"OBND", bytes(12)),
            (b"FULL", text(settings.npc_name + " - Original Appearance")),
            (b"BOD2", struct.pack("<II", SLOT_MASK, 2)), (b"RNAM", uint(RACE_ID)),
            (b"MODL", uint(ADDON_ID)), (b"DATA", struct.pack("<If", 0, 0.)), (b"DNAM", struct.pack("<i", 0))])
        outfit = Record(b"OTFT", OUTFIT_ID, 0, [(b"EDID", text(settings.prefix + "Outfit")), (b"INAM", uint(ARMOR_ID))])
        return [addon, armor, outfit], []
    skin_ids = {"body": ADDON_ID, "underwear": 0x01000807, "fixed": 0x01000808,
                "hands": 0x01000809, "feet": 0x0100080A}
    clothing_template = catalog.require("ClothesFarmClothes01", b"ARMO")
    inventory_fields = [(tag, data) for tag, data in clothing_template.fields if tag in {b"MOD2", b"MOD4", b"YNAM", b"ZNAM", b"ETYP"}]
    # Retain 0.5.1's FormID for saves/AFT snapshots, but retire its worn mask.
    head_cover = Record(b"ARMO", HEAD_COVER_ID, 4, [
        (b"EDID", text(settings.prefix + "NativeHeadCover")), (b"OBND", bytes(12)),
        (b"FULL", text(settings.npc_name + " - Head Cover")),
        *[(tag, data) for tag, data in inventory_fields if tag == b"ETYP"],
        (b"BOD2", struct.pack("<II", 0, 2)), (b"RNAM", uint(RACE_ID)),
        (b"DATA", struct.pack("<If", 0, 0.)), (b"DNAM", struct.pack("<i", 0))])
    result, skin_addons, skin_mask, inventory = [head_cover], [], 0, []
    garment_index = 0
    for part in components(settings):
        wearable = part["role"] == "garment"
        addon_id = 0x01000810 + garment_index * 2 if wearable else skin_ids[part["id"]]
        armor_id = addon_id + 1
        item_name = settings.prefix + ("Garment_" + part["id"] if wearable else part["id"].title())
        mask = sum(1 << (slot - 30) for slot in part.get("slots", [part["slot"]]))
        armor_type = {"light": 0, "heavy": 1, "clothing": 2}[part.get("armor_type", "clothing")]
        result.append(Record(b"ARMA", addon_id, 0, [
            (b"EDID", text(item_name + "AA")), (b"BOD2", struct.pack("<II", mask, armor_type)),
            (b"RNAM", uint(RACE_ID)), (b"DNAM", bytes((0, 0, 0, 0, 2, 0, 0, 0)) + struct.pack("<f", 0.)),
            (b"MOD2", text(path + "\\" + part["file"])), (b"MOD3", text(path + "\\" + part["file"]))]))
        if not wearable:
            skin_addons.append(addon_id)
            skin_mask |= mask
            continue
        keywords = [catalog.require(name, b"KYWD").form_id for name in keyword_names(part)]
        result.append(Record(b"ARMO", armor_id, 0, [
            (b"EDID", text(item_name)), (b"OBND", bytes(12)), (b"FULL", text(part["name"])),
            *inventory_fields,
            (b"BOD2", struct.pack("<II", mask, armor_type)), (b"RNAM", uint(RACE_ID)),
            (b"KSIZ", uint(len(keywords))), (b"KWDA", b''.join(uint(k) for k in keywords)), (b"MODL", uint(addon_id)),
            (b"DATA", struct.pack("<If", part["value"], part["weight"])),
            (b"DNAM", struct.pack("<i", round(part["armor_rating"] * 100)))]))
        inventory.append((b"CNTO", uint(armor_id) + struct.pack("<i", 1)))
        garment_index += 1
    result.append(Record(b"ARMO", ARMOR_ID, 4, [
        (b"EDID", text(settings.prefix + "Appearance")), (b"OBND", bytes(12)),
        (b"FULL", text(settings.npc_name + " - Base Appearance")),
        (b"BOD2", struct.pack("<II", skin_mask, 2)), (b"RNAM", uint(RACE_ID)),
        *[(b"MODL", uint(form_id)) for form_id in skin_addons],
        (b"DATA", struct.pack("<If", 0, 0.)), (b"DNAM", struct.pack("<i", 0))]))
    result.append(Record(b"OTFT", OUTFIT_ID, 0, [(b"EDID", text(settings.prefix + "Outfit")),
                                              (b"INAM", b"")]))
    return result, inventory


def configure_actor(npc, settings, catalog, base_stats):
    npc.remove(b"VMAD", b"SNAM", b"PKID", b"CNTO", b"COED", b"COCT", b"CRIF", b"TPLT", b"WNAM",
               b"SPCT", b"SPLO", b"PRKZ", b"PRKR", b"SOFT")
    npc.replace(b"EDID", text(settings.prefix + "NPC"))
    npc.replace(b"FULL", text(settings.npc_name))
    npc.replace(b"SHRT", text(settings.npc_name))
    npc.replace(b"RNAM", uint(RACE_ID))
    npc.replace(b"DOFT", uint(OUTFIT_ID))
    npc.replace(b"VTCK", uint(catalog.require(settings.voice, b"VTYP").form_id))
    npc.replace(b"CNAM", uint(catalog.require(settings.combat_class, b"CLAS").form_id))
    npc.replace(b"ZNAM", uint(catalog.require(settings.combat_style, b"CSTY").form_id))
    npc.replace(b"NAM6", struct.pack("<f", settings.height_scale))
    acbs = bytearray(npc.values(b"ACBS")[0])
    # NPC flags and byte offsets are from xEdit's TES5 schema (see docs/FORMAT.md).
    flags = 0x20 | (0x10 if settings.auto_calculate else 0)
    flags |= 1 if settings.sex == "female" else 0
    flags |= {"protected": 0x800, "essential": 2, "mortal": 0}[settings.protection]
    level = settings.level
    if settings.level_mode == "player":
        flags |= 0x80
        level = round(settings.level_multiplier * 1000)
    struct.pack_into("<IhhHHHHhHhH", acbs, 0, flags,
                     round(settings.magicka - base_stats[1]), round(settings.stamina - base_stats[2]),
                     level, settings.min_level, settings.max_level, 100, 0, 0, round(settings.health - base_stats[0]), 0)
    npc.replace(b"ACBS", bytes(acbs))
    dnam = bytearray(npc.values(b"DNAM")[0])
    for name, value in settings.skills.items():
        dnam[SKILLS.index(name)] = value
    dnam[18:36] = bytes(18)
    struct.pack_into("<HHH", dnam, 36, settings.health, settings.magicka, settings.stamina)
    npc.replace(b"DNAM", bytes(dnam))
    aidt = bytearray(npc.values(b"AIDT")[0])
    aidt[0] = settings.aggression
    aidt[1] = settings.confidence
    aidt[3] = settings.morality
    aidt[5] = 2  # Helps Friends and Allies
    npc.replace(b"AIDT", bytes(aidt))
    factions = [("PlayerFaction", 0), ("PotentialFollowerFaction", 0), ("CurrentFollowerFaction", -1)]
    if settings.marriage:
        factions.append(("PotentialMarriageFaction", 0))
    after(npc, b"ACBS", [(b"SNAM", uint(catalog.require(name, b"FACT").form_id)
                          + struct.pack("<b3x", rank)) for name, rank in factions])
    if settings.spells:
        after(npc, b"RNAM", [(b"SPCT", uint(len(settings.spells)))]
              + [(b"SPLO", uint(catalog.require(name, b"SPEL").form_id)) for name in settings.spells])
    additions = []
    if settings.perks:
        additions += [(b"PRKZ", uint(len(settings.perks)))]
        additions += [(b"PRKR", uint(catalog.require(item["editor_id"], b"PERK").form_id)
                       + struct.pack("<B3x", item["rank"])) for item in settings.perks]
    inventory = []
    if settings.weapon:
        inventory.append((b"CNTO", uint(catalog.require(settings.weapon, b"WEAP").form_id) + struct.pack("<i", 1)))
    if settings.ammunition:
        inventory.append((b"CNTO", uint(catalog.require(settings.ammunition, b"AMMO").form_id) + struct.pack("<i", 100)))
    if inventory:
        additions += [(b"COCT", uint(len(inventory))), *inventory]
    before(npc, b"AIDT", additions)
    after(npc, b"AIDT", [(b"PKID", uint(catalog.require("DefaultSandboxEditorLocation1024", b"PACK").form_id))])
    return factions


def build_npc(game_data, output, settings=None, catalog=None):
    output = Path(output)
    settings = settings or load_settings(output)
    catalog = catalog or GameCatalog(game_data)
    catalog.validate_settings(settings)
    race = copy.deepcopy(catalog.require("NordRace", b"RACE"))
    race.form_id, race.flags = RACE_ID, 0
    race.replace(b"EDID", text(settings.prefix + "Race"))
    race.replace(b"FULL", text(settings.npc_name + " Race"))
    race.replace(b"DESC", text("Private VRM2Skyrim avatar race"))
    race.replace(b"WNAM", uint(ARMOR_ID))
    race.remove(b"RNAM")
    if len(race.values(b"ANAM")) != 2:
        raise ValueError("Expected male and female skeleton fields")
    path = settings.asset_dir.replace("/", "\\")
    race.fields = [(tag, text(path + "\\skeleton.nif") if tag == b"ANAM" else data) for tag, data in race.fields]
    data = bytearray(race.values(b"DATA")[0])
    struct.pack_into("<I", data, 32, struct.unpack_from("<I", data, 32)[0] & ~1)
    struct.pack_into("<ff", data, 16, 1., 1.)
    race.replace(b"DATA", bytes(data))
    appearance, inventory = appearance_records(settings, catalog)
    if settings.fit_armors:
        fitting = json.loads((output / "armor-fitting.json").read_text())
        for item in fitting["equipment"]:
            appearance.append(Record(b"ARMA", 0x01000000 | item["addon_local_id"], 0, [
                (b"EDID", text(settings.prefix + "Fitted_" + item["editor_id"])),
                (b"BOD2", struct.pack("<II", sum(1 << (s - 30) for s in item["slots"]), 2)),
                (b"RNAM", uint(RACE_ID)),
                (b"DNAM", bytes((item["priority"], item["priority"], 2, 2, 0, 0, 0, 0)) + struct.pack("<f", 0.)),
                (b"MOD2", text(path + "\\" + item["file"])),
                (b"MOD3", text(path + "\\" + item["file"]))]))
    template = "HousecarlWhiterun" if settings.sex == "female" else "HousecarlWindhelm"
    npc = copy.deepcopy(catalog.require(template, b"NPC_"))
    npc.form_id, npc.flags = NPC_ID, 0
    base_stats = struct.unpack_from("<fff", race.values(b"DATA")[0], 36)
    factions = configure_actor(npc, settings, catalog, base_stats)
    configure_native_head(npc, race)
    appearance += head_records(settings, RACE_ID)
    if settings.armor_support:
        appearance += runtime_records(settings, catalog)
        after(npc, b"EDID", [(b"VMAD", vmad(settings))])
    if inventory:
        existing = npc.values(b"CNTO")
        npc.remove(b"COCT")
        before(npc, b"AIDT", [(b"COCT", uint(len(existing) + len(inventory))), *inventory])
    player = catalog.require("Player", b"NPC_")
    # RELA rank is an enum (Ally=1), not Papyrus's signed relationship rank.
    relation = Record(b"RELA", RELATIONSHIP_ID, 0, [
        (b"EDID", text(settings.prefix + "PlayerRelationship")),
        (b"DATA", struct.pack("<IIHBBI", NPC_ID, player.form_id, 1, 0, 0, 0))])
    cell = copy.deepcopy(catalog.require("WhiterunTempleofKynareth", b"CELL"))
    marker = catalog.require("WhiterunTempleofKynarethCenterMarker", b"REFR")
    location = list(struct.unpack("<6f", marker.values(b"DATA")[0]))
    location[0] += settings.spawn_offset_x
    location[1] += settings.spawn_offset_y
    actor = Record(b"ACHR", REFERENCE_ID, 0x400, [
        (b"EDID", text(settings.prefix + "FollowerREF")), (b"NAME", uint(NPC_ID)),
        (b"DATA", struct.pack("<6f", *location))])
    plugin_path = output / "mod" / settings.plugin_name
    items = [race, *appearance, npc, relation]
    write_plugin(plugin_path, items, author=settings.author or "VRM2Skyrim",
                 placement=(cell, actor))
    write_runtime(output, settings)
    generated = list(records(plugin_path))
    if len(generated) != len(items) + 3 or len({r.form_id for r in generated}) != len(generated):
        raise RuntimeError("Follower plugin record count mismatch")
    reference = next(r for r in generated if r.kind == b"ACHR")
    if (uint(cell.form_id), 6) not in reference.groups or reference.groups[-1] != (uint(cell.form_id), 8):
        raise RuntimeError("Placed follower is not in the temple's persistent reference group")
    report = {"plugin": str(plugin_path), "npc_editor_id": settings.prefix + "NPC", "npc_local_form_id": "000800",
              "reference_editor_id": settings.prefix + "FollowerREF", "reference_local_form_id": "000806",
              "covered_slots": SLOTS if not settings.armor_support else [part["slot"] for part in components(settings)],
              "armor_support": settings.armor_support, "factions": factions, "relationship": "Ally", "voice": settings.voice,
              "spawn_cell": cell.editor_id, "spawn_cell_form_id": hex(cell.form_id), "spawn_position": location,
              "spawn_source": marker.editor_id, "custom_race": settings.prefix + "Race",
              "skeleton": settings.asset_dir + "/skeleton.nif",
              "garment_keywords": {g['id']: {name: catalog.require(name,b'KYWD').form_id for name in keyword_names(g)}
                                   for g in settings.appearance_parts.get('garments', [])} if settings.armor_support else {},
              "records": [{"type": r.kind.decode(), "id": hex(r.form_id), "editor_id": r.editor_id} for r in generated],
              "game_verified": False}
    (output / "npc.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    logging.info("Follower plugin generated: %s; placement %s", plugin_path, cell.editor_id)
    return plugin_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("game_data", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    build_npc(args.game_data, args.output)
