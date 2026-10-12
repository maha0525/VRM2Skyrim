"""Shared wardrobe classification, validation and deterministic asset layout."""
import logging
import math
import re

BODY_SLOT, UNDERWEAR_SLOT, FIXED_SLOT = 32, 52, 60
# Prefer generic layers; 46/47 are commonly displayed as cloak/backpack by UI mods.
GARMENT_SLOTS = tuple(range(53, 60)) + (44, 45, 48, 49, 46, 47) + tuple(range(32, 44))
ROLES = ("body", "underwear", "fixed")
ITEM_KINDS = ("body", "legs", "full", "hands", "feet", "cloak", "backpack", "accessory")
MAX_GARMENTS = 16  # 0x810..0x82f; 0x830 and later are reserved runtime/head records.


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
    if not isinstance(garments, list) or not 1 <= len(garments) <= MAX_GARMENTS:
        raise ValueError(f"衣服を1〜{MAX_GARMENTS}品にまとめてください")
    ids, equipped, record_indices = set(), set(), set()
    for index, garment in enumerate(garments):
        keys = {"id", "name", "nodes", "slot", "armor_type", "armor_rating", "weight", "value", "equipped"}
        if not isinstance(garment, dict) or set(garment) - {"equipment_group", "item_kind", "slot_mode", "record_index"} != keys:
            raise ValueError("Invalid garment settings")
        record_index = garment.get('record_index', index)
        if type(record_index) is not int or not 0 <= record_index < MAX_GARMENTS or record_index in record_indices:
            raise ValueError('Invalid or duplicate garment record index')
        record_indices.add(record_index)
        if item_kind(garment) not in ITEM_KINDS:
            raise ValueError("Invalid garment item kind")
        if equipment_group(garment) not in {"body", "hands", "feet", "accessory"}:
            raise ValueError("Invalid garment equipment group")
        item_id, name = garment["id"], garment["name"]
        if not isinstance(item_id, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", item_id) or item_id.lower() in ids:
            raise ValueError("Garment IDs must be unique ASCII identifiers")
        ids.add(item_id.lower())
        if item_id.lower() in {'body', 'underwear', 'fixed', 'hands', 'feet', 'face', 'hair', 'appearance'}:
            raise ValueError('Garment ID is reserved for a body component; prefix the ID with outfit_')
        if not isinstance(name, str) or not name.strip() or len(name) > 128 or any(ord(c) < 32 for c in name):
            raise ValueError("Invalid garment name")
        nodes(garment["nodes"])
        if not garment["nodes"]:
            raise ValueError("装備に含めるメッシュを選んでください")
        if type(garment["slot"]) is not int or garment["slot"] not in GARMENT_SLOTS:
            raise ValueError("衣服には32–49または53–59の装備枠を使ってください。52・60は内部予約枠です")
        if garment.get('slot_mode', 'manual') not in ('auto', 'manual'):
            raise ValueError('Invalid garment slot mode')
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
            slots = set(equip_slots(garment))
            if slots.intersection(equipped):
                raise ValueError("初期装備の衣服が同じ枠を使っています。同時に着る胴の衣服は一品にまとめてください。重ね着する場合だけ追加枠を選んでください")
            equipped.update(slots)
    return seen


def equip_slots(garment):
    """Inventory mutual exclusion, distinct from ARMA skin coverage."""
    if garment['slot'] == 32 and item_kind(garment) == 'full':
        return [32, 33, 37]
    return [garment['slot']]


def migrate_legacy_parts(parts):
    """Replace legacy scripted groups with real native outfit items."""
    import copy
    parts = copy.deepcopy(parts)
    garments, combined = [], {}
    for index, garment in enumerate(parts.get('garments', [])):
        garment['record_index'] = index
        category = equipment_group(garment)
        if category == 'accessory':
            garment.pop('equipment_group', None)
            garments.append(garment)
            continue
        garment.update(slot={'body': 32, 'hands': 33, 'feet': 37}[category], slot_mode='auto')
        if category in ('hands', 'feet'):
            garment['item_kind'] = category
        garment.pop('equipment_group', None)
        # Only simultaneous initial clothes need merging; alternatives stay separate.
        if garment['equipped'] and category in combined:
            target = combined[category]
            if target['armor_type'] != garment['armor_type']:
                raise ValueError('以前の衣服設定に同じ部位の衣服と軽装・重装が混在しています。ウィザードで衣装セットの防具分類を選び直してください')
            target['nodes'].extend(garment['nodes'])
            target['weight'] += garment['weight']
            target['value'] += garment['value']
            target['armor_rating'] = max(target['armor_rating'], garment['armor_rating'])
            target['name'] += ' / ' + garment['name']
            target['name'] = target['name'][:128]
            logging.info('Native wardrobe: merged %s into %s at slot %s', garment['id'], target['id'], target['slot'])
        else:
            garments.append(garment)
            if garment['equipped']:
                combined[category] = garment
    parts['garments'] = garments
    return parts


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
    keyword = ({"body": "ClothingBody", "legs": "ClothingBody", "full": "ClothingBody", "hands": "ClothingHands", "feet": "ClothingFeet"}
               if armor_type == "clothing" else
               {"body": "ArmorCuirass", "legs": "ArmorCuirass", "full": "ArmorCuirass", "hands": "ArmorGauntlets", "feet": "ArmorBoots"}).get(kind)
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
    if settings.skin_partition_enabled and fitting:
        result[0]["slots"] = [32, 34, 38]
        result[0]["partial_source"] = True
        result += [{"id": role, "file": role + ".nif", "nodes": parts["body"], "slot": slot,
                    "role": "body", "slots": [slot], "partial_source": True}
                   for role, slot in (("hands", 33), ("feet", 37))]
    result += [{**garment, "file": "garment_" + garment["id"].lower() + ".nif", "role": "garment"}
               for garment in parts["garments"]]
    for part in result:
        if part['role'] == 'garment':
            part['priority'] = 1
            if part['slot'] == 32:
                part['slots'] = [32, 33, 34, 37, 38] if item_kind(part) == 'full' else [32, 34, 38]
    return result
