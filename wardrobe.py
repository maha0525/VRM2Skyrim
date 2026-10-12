"""Shared wardrobe classification, validation and deterministic asset layout."""
import logging
import math
import re

BODY_SLOT, UNDERWEAR_SLOT, FIXED_SLOT = 32, 52, 60
# Prefer generic layers; 46/47 are commonly displayed as cloak/backpack by UI mods.
GARMENT_SLOTS = tuple(range(53, 60)) + (44, 45, 48, 49, 46, 47)
ROLES = ("body", "underwear", "fixed")
ITEM_KINDS = ("body", "legs", "hands", "feet", "cloak", "backpack", "accessory")


def suggest_role(name, materials):
    name = name.lower()
    if "underwear" in name or any(word in name for word in ("panties", "lingerie")):
        return "underwear"
    if any(word in name for word in ("hair", "face", "eyelash", "eyebrow", "eye", "head")):
        return "fixed"
    if any(word in name for word in ("jacket", "shirt", "skirt", "dress", "tights", "loafer", "boot", "coat", "pants", "glove", "shoe")):
        return "garment"
    if materials and any(any(word in material.lower() for word in ("face", "eye", "hair")) for material in materials) and not any("body" in material.lower() or "skin" in material.lower() for material in materials):
        return "fixed"
    if "body" in name or "skin" in name:
        return "body"
    return "fixed"


def validate_parts(parts):
    if not isinstance(parts, dict) or set(parts) != {*ROLES, "garments"}:
        raise ValueError("Appearance parts require body, underwear, fixed and garments")
    seen = set()

    def nodes(values):
        if not isinstance(values, list) or any(type(n) is not int or n < 0 for n in values):
            raise ValueError("Appearance nodes must be non-negative integer lists")
        if len(values) != len(set(values)) or seen.intersection(values):
            raise ValueError("A mesh node must belong to exactly one appearance part")
        seen.update(values)

    for role in ROLES:
        nodes(parts[role])
    if not parts["body"]:
        raise ValueError("無装備の身体に含めるメッシュを選んでください")
    garments = parts["garments"]
    if not isinstance(garments, list) or not 1 <= len(garments) <= len(GARMENT_SLOTS):
        raise ValueError(f"衣服を1〜{len(GARMENT_SLOTS)}品にまとめてください")
    ids, equipped = set(), set()
    for garment in garments:
        keys = {"id", "name", "nodes", "slot", "armor_type", "armor_rating", "weight", "value", "equipped"}
        if not isinstance(garment, dict) or set(garment) - {"equipment_group", "item_kind"} != keys:
            raise ValueError("Invalid garment settings")
        if item_kind(garment) not in ITEM_KINDS:
            raise ValueError("Invalid garment item kind")
        if equipment_group(garment) not in {"body", "hands", "feet", "accessory"}:
            raise ValueError("Invalid garment equipment group")
        item_id, name = garment["id"], garment["name"]
        if not isinstance(item_id, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", item_id) or item_id.lower() in ids:
            raise ValueError("Garment IDs must be unique ASCII identifiers")
        ids.add(item_id.lower())
        if not isinstance(name, str) or not name.strip() or len(name) > 128 or any(ord(c) < 32 for c in name):
            raise ValueError("Invalid garment name")
        nodes(garment["nodes"])
        if not garment["nodes"]:
            raise ValueError("装備に含めるメッシュを選んでください")
        if type(garment["slot"]) is not int or garment["slot"] not in GARMENT_SLOTS:
            raise ValueError("元衣装には44–49または53–59の重ね着枠を使ってください")
        if garment["armor_type"] not in ("clothing", "light", "heavy"):
            raise ValueError("Invalid garment armor type")
        for key, maximum in (("armor_rating", 10000), ("weight", 1000)):
            value = garment[key]
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= maximum:
                raise ValueError(f"Invalid garment {key}")
        if type(garment["value"]) is not int or not 0 <= garment["value"] <= 2147483647:
            raise ValueError("Invalid garment value")
        if type(garment["equipped"]) is not bool:
            raise ValueError("Garment equipped must be true or false")
        if garment["equipped"]:
            if garment["slot"] in equipped:
                raise ValueError("初期装備の衣服が同じ枠を使っています。枠を分けるか一品にまとめてください")
            equipped.add(garment["slot"])
    return seen


def validate_source(settings, report):
    if not settings.armor_support:
        return
    selected = validate_parts(settings.appearance_parts)
    available = {part["node"] for part in report["parts"]}
    if settings.appearance_source_sha256 != report["sha256"]:
        raise ValueError("衣服の分類が別のVRM用です。このVRMを確認して分類し直してください")
    if selected != available:
        raise ValueError(f"全メッシュを一回だけ分類してください。未分類={sorted(available-selected)}、不明={sorted(selected-available)}")
    logging.info("Wardrobe: %s body, %s underwear, %s fixed nodes, %s garments",
                 *(len(settings.appearance_parts[role]) for role in ROLES), len(settings.appearance_parts["garments"]))


def equipment_group(garment):
    if "equipment_group" in garment:
        return garment["equipment_group"]
    name = garment["name"].lower()
    if re.search(r"boot|shoe|loafer|sandal|靴|ブーツ|サンダル", name):
        return "feet"
    if re.search(r"glove|gauntlet|手袋|籠手", name):
        return "hands"
    if re.search(r"accessor|ring|necklace|bracelet|earring|backpack|cloak|cape|眼鏡|指輪|首飾り|アクセ|リュック|マント|ケープ", name):
        return "accessory"
    return "body"


def item_kind(garment):
    if "item_kind" in garment:
        return garment["item_kind"]
    name = garment["name"].lower()
    for kind, pattern in (("feet", r"boot|shoe|loafer|sandal|靴|ブーツ|サンダル"),
                          ("hands", r"glove|gauntlet|手袋|籠手"),
                          ("backpack", r"backpack|リュック|バックパック"),
                          ("cloak", r"cloak|cape|マント|ケープ"),
                          ("legs", r"tights|stocking|skirt|pants|trouser|タイツ|スカート|ズボン"),
                          ("accessory", r"accessor|ring|necklace|bracelet|earring|眼鏡|指輪|首飾り|アクセ")):
        if re.search(pattern, name):
            return kind
    return "body"


def keyword_names(garment):
    """Semantic/vendor keywords; UI subtype still follows the occupied layer."""
    armor_type, kind = garment["armor_type"], item_kind(garment)
    result = [{"clothing": "ArmorClothing", "light": "ArmorLight", "heavy": "ArmorHeavy"}[armor_type],
              "VendorItemClothing" if armor_type == "clothing" else "VendorItemArmor"]
    keyword = ({"body": "ClothingBody", "legs": "ClothingBody", "hands": "ClothingHands", "feet": "ClothingFeet"}
               if armor_type == "clothing" else
               {"body": "ArmorCuirass", "legs": "ArmorCuirass", "hands": "ArmorGauntlets", "feet": "ArmorBoots"}).get(kind)
    if keyword:
        result.append(keyword)
    return result


def skin_components(settings):
    """Use one fixed-layer addon per skin to avoid multiple models competing at slot 60."""
    parts = [p for p in components(settings) if p['role'] != 'garment']
    if settings.head_switch_enabled:
        parts = [p for p in parts if p['id'] not in ('fixed', 'face', 'hair')]
        parts.append({'id': 'fixed', 'role': 'fixed', 'file': 'fixed_full.nif',
                      'slot': FIXED_SLOT, 'nodes': settings.appearance_parts['fixed']})
    return parts


def components(settings, fitting=True):
    if not settings.armor_support:
        return [{"id": "appearance", "file": "avatar.nif", "nodes": None, "slot": 32, "role": "fixed"}]
    parts = settings.appearance_parts
    result = [{"id": role, "file": role + ".nif", "nodes": parts[role], "slot": slot, "role": role}
              for role, slot in zip(ROLES, (BODY_SLOT, UNDERWEAR_SLOT, FIXED_SLOT)) if parts[role]]
    if settings.head_switch_enabled:
        result = [p for p in result if p['id'] != 'fixed']
        selected = set(sum(settings.appearance_heads.values(), []))
        remaining = [n for n in parts['fixed'] if n not in selected]
        for name, nodes in [('fixed', remaining), *settings.appearance_heads.items()]:
            if nodes:
                result.append({'id': name, 'file': name+'.nif', 'nodes': nodes, 'slot': FIXED_SLOT, 'role': 'fixed'})
    if settings.fitting_enabled and fitting:
        result[0]["slots"] = [32, 34, 38]
        result[0]["partial_source"] = True
        result += [{"id": role, "file": role + ".nif", "nodes": parts["body"], "slot": slot,
                    "role": "body", "slots": [slot], "partial_source": True}
                   for role, slot in (("hands", 33), ("feet", 37))]
    result += [{**garment, "file": "garment_" + garment["id"].lower() + ".nif", "role": "garment"}
               for garment in parts["garments"]]
    return result
