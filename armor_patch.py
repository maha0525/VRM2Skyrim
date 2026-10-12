"""Combine private fitted addons without competing per-follower ARMO overrides."""
import argparse
import json
import logging
from pathlib import Path
import re
import struct
import zipfile

from official_catalog import OfficialCatalog
from plugin import Record, records, write_plugin


def installed_patch_status(game_data, profile):
    """Check actual deployed item-to-private-addon bindings, read-only."""
    expected = set()
    for item in profile['equipment']:
        expected.add((item.get('origin_plugin', 'Skyrim.esm').casefold(),
                      item.get('origin_local_id', item['original_form_id'] & 0xFFFFFF),
                      item['addon_local_id']))
    path = Path(game_data)/'VRM2SkyrimArmorPatch.esp'
    installed, linked = 0, set()
    if path.is_file():
        parsed = list(records(path))
        header = next(r for r in parsed if r.kind == b'TES4')
        masters = [value.rstrip(b'\0').decode('utf8').casefold() for value in header.values(b'MAST')]
        masters.append(path.name.casefold())
        for record in parsed:
            if record.kind != b'ARMO':
                continue
            installed += 1
            owner = record.form_id >> 24
            if owner >= len(masters):
                raise ValueError('Deployed armor patch has an invalid master reference')
            for value in record.values(b'MODL'):
                addon = struct.unpack('<I', value)[0]
                index = addon >> 24
                if index < len(masters) and masters[index] == profile['plugin'].casefold():
                    linked.add((masters[owner], record.form_id & 0xFFFFFF, addon & 0xFFFFFF))
    missing = expected-linked
    status = 'current' if not missing else 'needs_update' if path.is_file() else 'missing'
    result = dict(status=status, installed_items=installed,
                  expected_items=len({(p, i) for p, i, _ in expected}), missing_bindings=len(missing))
    logging.info('Deployed armor patch: %s, items=%s, missing private bindings=%s, follower=%s',
                 status, installed, len(missing), profile['plugin'])
    return result


def build_patch(game_data, manifests, output):
    output = Path(output)
    if not manifests:
        raise ValueError("Select at least one fitted follower")
    profiles = [json.loads(Path(path).read_text(encoding="utf8")) for path in manifests]
    plugins = [p["plugin"] for p in profiles]
    if len({name.casefold() for name in plugins}) != len(plugins) or any(
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}\.esp", name) for name in plugins):
        raise ValueError("Fitted follower plugin names must be distinct")
    catalog = OfficialCatalog(game_data)
    needed = {'Skyrim.esm'}
    originals = {}
    for profile in profiles:
        for equipment in profile['equipment']:
            original = catalog.fitted_item(equipment)
            originals[original.form_id] = original
            def collect(value):
                if value:
                    needed.add(catalog.plugins[value >> 24])
                return value
            from official_catalog import remap_record
            remap_record(original, collect)
            if equipment.get('source_addon_key'):
                addon = catalog.require(equipment['source_addon_key'], b'ARMA')
                for value in addon.values(b'SNDD'):
                    collect(struct.unpack('<I', value)[0])
    changed = True
    while changed:
        previous = set(needed)
        for name in previous:
            needed.update(catalog.master_lists[name])
        changed = needed != previous
    masters = [name for name in catalog.plugins if name in needed] + plugins
    items = {}
    for profile_index, profile in enumerate(profiles):
        index = masters.index(profile['plugin'])
        manifest = Path(manifests[profile_index]).resolve()
        native_slots = profile.get('wardrobe_policy') == 'native_slots'
        settings_path = manifest.parent/'settings.json'
        if settings_path.is_file():
            native_slots |= json.loads(settings_path.read_text(encoding='utf-8-sig')).get('wardrobe_policy') == 'native_slots'
        candidates = [manifest.parent / "mod" / profile["plugin"]]
        candidates += [parent / profile["plugin"] for parent in manifest.parents]
        plugin = next((p for p in candidates if p.is_file()), None)
        if plugin is None:
            raise ValueError(f"Follower plugin is missing: {profile['plugin']}")
        source_records = list(records(plugin))
        header = next(r for r in source_records if r.kind == b'TES4')
        own_index = len(header.values(b'MAST'))
        addons = {r.form_id & 0xFFFFFF: r for r in source_records if r.kind == b'ARMA' and r.form_id >> 24 == own_index}
        list_values = {name: set() for name in (('FaceHidingEquipment', 'HairHidingEquipment') if native_slots else
                                               ('BodyEquipment', 'HandsEquipment', 'FeetEquipment',
                                                'FaceHidingEquipment', 'HairHidingEquipment'))}
        for equipment in profile["equipment"]:
            original = catalog.fitted_item(equipment)
            local_id = equipment["addon_local_id"]
            if type(local_id) is not int or not (0x880 <= local_id < 0x8C0 or 0x1000 <= local_id < 0xFFFFFF):
                raise ValueError("Invalid private armor addon ID")
            addon = addons.get(local_id)
            if addon is None or addon.values(b"RNAM") != [struct.pack("<I", own_index << 24 | 0x804)]:
                raise ValueError("Fitted addon is missing or has a different private race")
            mapped = catalog.in_masters(original, masters)
            record = items.setdefault(mapped.form_id, mapped)
            record.flags &= ~0x40000  # encoder emits uncompressed fields
            for tag in (b"FULL", b"DESC"):
                if record.values(tag):
                    record.replace(tag, (catalog.label(original, tag) + "\0").encode("utf8"))
            value = struct.pack('<I', index << 24 | local_id)
            if value not in record.values(b'MODL'):
                record.fields.append((b'MODL', value))
            if equipment.get('source_addon_key'):
                native = catalog.require(equipment['source_addon_key'], b'ARMA')
                if native.values(b'SNDD'):
                    fitted = addons[local_id]
                    # Follower records use Skyrim + their own file; retain that
                    # race/model and only add the source armor's footstep sound.
                    from official_catalog import remap_record
                    def follower_ref(value):
                        if not value:
                            return 0
                        return (index << 24 | (value & 0xFFFFFF)) if value >> 24 == own_index else value
                    fitted = remap_record(fitted, follower_ref)
                    step = struct.unpack('<I', native.values(b'SNDD')[0])[0]
                    owner = catalog.plugins[step >> 24]
                    fitted.replace(b'SNDD', struct.pack('<I', masters.index(owner) << 24 | (step & 0xFFFFFF)))
                    items[fitted.form_id] = fitted
            mask = equipment.get('armor_mask', sum(1 << (s-30) for s in equipment.get('slots', [])))
            for slot, name in ((32, 'BodyEquipment'), (33, 'HandsEquipment'), (37, 'FeetEquipment')):
                if not native_slots and mask & (1 << (slot-30)):
                    list_values[name].add(mapped.form_id)
            for flag, name in (('hide_face', 'FaceHidingEquipment'), ('hide_hair', 'HairHidingEquipment')):
                if equipment.get(flag):
                    list_values[name].add(mapped.form_id)
        from equipment_runtime import LIST_IDS
        from gear_head_runtime import IDS
        ids = {**LIST_IDS, **IDS}
        for name, values in list_values.items():
            # Old profiles without runtime lists remain valid patch inputs.
            existing = next((r for r in source_records if r.form_id == (own_index << 24 | (ids[name] & 0xFFFFFF))), None)
            if existing is not None:
                form_id = index << 24 | (ids[name] & 0xFFFFFF)
                items[form_id] = Record(b'FLST', form_id, 0, [(b'EDID', existing.values(b'EDID')[0]),
                                                           *[(b'LNAM', struct.pack('<I', n)) for n in sorted(values)]])
    path = output / "mod/VRM2SkyrimArmorPatch.esp"
    write_plugin(path, list(items.values()), masters=masters)
    loaded = list(records(path))
    header = next(r for r in loaded if r.kind == b"TES4")
    if header.values(b"MAST") != [(m + "\0").encode() for m in masters]:
        raise RuntimeError("Armor patch master order mismatch")
    mapped_originals = {catalog.in_masters(r, masters).form_id: r for r in originals.values()}
    for record in loaded:
        if record.kind != b"ARMO":
            continue
        original = mapped_originals[record.form_id]
        mapped = catalog.in_masters(original, masters)
        if [f for f in record.fields if f[0] not in (b"MODL", b"FULL", b"DESC")] != [f for f in mapped.fields if f[0] not in (b"MODL", b"FULL", b"DESC")]:
            raise RuntimeError("Armor patch changed original item data")
        for tag in (b"FULL", b"DESC"):
            if original.values(tag) and record.values(tag) != [(catalog.label(original, tag) + "\0").encode("utf8")]:
                raise RuntimeError("Armor patch changed a localized item name/description")
        if record.values(b"MODL")[:len(mapped.values(b"MODL"))] != mapped.values(b"MODL"):
            raise RuntimeError("Armor patch removed an original race addon")
    (output / "mod/VRM2SkyrimArmorPatch-README.txt").write_text(
        "Enable these fitted follower ESPs, then VRM2SkyrimArmorPatch.esp:\n" + "\n".join(plugins)
        + '\nRequired official masters:\n' + '\n'.join(masters[:-len(plugins)])
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
    logging.info("Combined armor patch: %s follower masters, %s original items, %s records", len(plugins), len(originals), len(items))
    return archive


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-data", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build_patch(args.game_data, args.manifest, args.output)
