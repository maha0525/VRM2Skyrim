"""Combine private fitted addons without competing per-follower ARMO overrides."""
import argparse
import copy
import json
import logging
from pathlib import Path
import re
import struct
import zipfile

from game_catalog import GameCatalog
from plugin import records, write_plugin


def build_patch(game_data, manifests, output):
    output = Path(output)
    if not manifests:
        raise ValueError("Select at least one fitted follower")
    profiles = [json.loads(Path(path).read_text(encoding="utf8")) for path in manifests]
    plugins = [p["plugin"] for p in profiles]
    if len({name.casefold() for name in plugins}) != len(plugins) or any(
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}\.esp", name) for name in plugins):
        raise ValueError("Fitted follower plugin names must be distinct")
    masters = ["Skyrim.esm", *plugins]
    catalog = GameCatalog(game_data)
    items = {}
    for index, profile in enumerate(profiles, 1):
        manifest = Path(manifests[index - 1]).resolve()
        candidates = [manifest.parent / "mod" / profile["plugin"]]
        candidates += [parent / profile["plugin"] for parent in manifest.parents]
        plugin = next((p for p in candidates if p.is_file()), None)
        if plugin is None:
            raise ValueError(f"Follower plugin is missing: {profile['plugin']}")
        addons = {r.form_id & 0xFFFFFF: r for r in records(plugin, {b"ARMA"})}
        for equipment in profile["equipment"]:
            original = catalog.require(equipment["editor_id"], b"ARMO")
            if original.form_id != equipment["original_form_id"]:
                raise ValueError("Armor manifest does not match this game master")
            local_id = equipment["addon_local_id"]
            if type(local_id) is not int or not 0x880 <= local_id < 0x8C0:
                raise ValueError("Invalid private armor addon ID")
            addon = addons.get(local_id)
            if addon is None or addon.values(b"RNAM") != [struct.pack("<I", 0x01000804)]:
                raise ValueError("Fitted addon is missing or has a different private race")
            record = items.setdefault(original.form_id, copy.deepcopy(original))
            record.flags &= ~0x40000  # encoder emits uncompressed fields
            for tag in (b"FULL", b"DESC"):
                if record.values(tag):
                    record.replace(tag, (catalog.label(original, tag) + "\0").encode("utf8"))
            record.fields.append((b"MODL", struct.pack("<I", index << 24 | local_id)))
    path = output / "mod/VRM2SkyrimArmorPatch.esp"
    write_plugin(path, list(items.values()), masters=masters)
    loaded = list(records(path))
    header = next(r for r in loaded if r.kind == b"TES4")
    if header.values(b"MAST") != [(m + "\0").encode() for m in masters]:
        raise RuntimeError("Armor patch master order mismatch")
    for record in loaded:
        if record.kind != b"ARMO":
            continue
        original = catalog.require(record.editor_id, b"ARMO")
        if [f for f in record.fields if f[0] not in (b"MODL", b"FULL", b"DESC")] != [f for f in original.fields if f[0] not in (b"MODL", b"FULL", b"DESC")]:
            raise RuntimeError("Armor patch changed original item data")
        for tag in (b"FULL", b"DESC"):
            if original.values(tag) and record.values(tag) != [(catalog.label(original, tag) + "\0").encode("utf8")]:
                raise RuntimeError("Armor patch changed a localized item name/description")
        if record.values(b"MODL")[:len(original.values(b"MODL"))] != original.values(b"MODL"):
            raise RuntimeError("Armor patch removed an original race addon")
    (output / "mod/VRM2SkyrimArmorPatch-README.txt").write_text(
        "Enable these fitted follower ESPs, then VRM2SkyrimArmorPatch.esp:\n" + "\n".join(plugins)
        + "\nOnly one combined armor patch should be active. Regenerate it after adding/removing fitted followers.\n"
          "The patch adds private-race appearances to original Skyrim armor items. Their stats and original addons remain.\n"
          "Other plugins overriding the same armor may require a load-order/compatibility patch.\n", encoding="utf8")
    archive = output / "VRM2SkyrimArmorPatch.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as target:
        for file in sorted((output / "mod").iterdir()):
            target.write(file, file.name)
    with zipfile.ZipFile(archive) as source:
        if source.testzip() is not None:
            raise RuntimeError("Armor patch ZIP is corrupt")
    logging.info("Combined armor patch: %s follower masters, %s original items", len(plugins), len(items))
    return archive


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-data", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_patch(args.game_data, args.manifest, args.output)
