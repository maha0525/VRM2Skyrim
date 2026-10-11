"""Read selectable records from the user's Skyrim.esm, without bundled game data."""
import struct
from pathlib import Path

from plugin import records
from bsa import BSA

KINDS = {b"NPC_", b"ARMO", b"ARMA", b"RACE", b"FACT", b"VTYP", b"WEAP", b"PACK",
         b"CLAS", b"CSTY", b"PERK", b"SPEL", b"FLST", b"CELL", b"REFR", b"AMMO", b"KYWD"}


class GameCatalog:
    def __init__(self, data):
        self.path = Path(data) / "Skyrim.esm"
        self.by_editor_id = {r.editor_id: r for r in records(self.path, KINDS) if r.editor_id}
        follower_list = self.require("VoicesFollowerAll", b"FLST")
        self.follower_voice_ids = {struct.unpack("<I", value)[0] for value in follower_list.values(b"LNAM")}
        marriage_list = self.require("VoicesMarriageAll", b"FLST")
        self.marriage_voice_ids = {struct.unpack("<I", value)[0] for value in marriage_list.values(b"LNAM")}
        self.strings = self.load_strings(Path(data))
        self.descriptions = self.load_strings(Path(data), "dlstrings")

    @staticmethod
    def load_strings(data, extension="strings"):
        blob = None
        for language in ("japanese", "english"):
            path = data / "Strings" / f"skyrim_{language}.{extension}"
            if path.exists():
                blob = path.read_bytes()
                break
        if blob is None and (data / "Skyrim - Interface.bsa").exists():
            archive = BSA(data / "Skyrim - Interface.bsa")
            for language in ("japanese", "english"):
                name = f"strings/skyrim_{language}.{extension}"
                if name in archive.entries:
                    blob = archive.read(name)
                    break
        if blob is None:
            return {}
        count, size = struct.unpack_from("<II", blob)
        start = 8 + count * 8
        if start + size > len(blob):
            raise ValueError("Invalid Skyrim localized string table")
        result = {}
        for index in range(count):
            key, offset = struct.unpack_from("<II", blob, 8 + index * 8)
            if offset >= size:
                raise ValueError("Invalid Skyrim string offset")
            position = start + offset
            if extension == "dlstrings":
                length = struct.unpack_from("<I", blob, position)[0]
                value = blob[position + 4:position + 4 + length].rstrip(b"\0")
            else:
                end = blob.index(b"\0", position)
                value = blob[position:end]
            result[key] = value.decode("utf8", "replace")
        return result

    def label(self, record, tag=b"FULL"):
        values = record.values(tag)
        if not values:
            return record.editor_id if tag == b"FULL" else ""
        value = values[0]
        if len(value) == 4:
            table = self.descriptions if tag == b"DESC" else self.strings
            return table.get(struct.unpack("<I", value)[0], record.editor_id if tag == b"FULL" else "")
        return value.rstrip(b"\0").decode("utf8", "replace")

    def require(self, editor_id, kind=None):
        record = self.by_editor_id.get(editor_id)
        if record is None or (kind and record.kind != kind):
            raise ValueError(f"Skyrim.esm {kind.decode() if kind else 'record'} not found: {editor_id}")
        return record

    def choices(self, kind):
        return sorted((r for r in self.by_editor_id.values() if r.kind == kind), key=lambda r: r.editor_id.lower())

    def validate_settings(self, settings):
        voice = self.require(settings.voice, b"VTYP")
        if voice.form_id not in self.follower_voice_ids:
            raise ValueError("Selected voice has no standard follower dialogue in VoicesFollowerAll")
        if settings.marriage and voice.form_id not in self.marriage_voice_ids:
            raise ValueError("Selected voice has no standard marriage dialogue")
        self.require(settings.combat_class, b"CLAS")
        self.require(settings.combat_style, b"CSTY")
        if settings.weapon:
            self.require(settings.weapon, b"WEAP")
        if settings.ammunition:
            self.require(settings.ammunition, b"AMMO")
        for perk in settings.perks:
            record = self.require(perk["editor_id"], b"PERK")
            ranks = record.values(b"DATA")[0][2]
            if perk["rank"] >= ranks:
                raise ValueError(f"Perk rank exceeds available ranks: {perk['editor_id']} (0–{ranks - 1})")
        for spell in settings.spells:
            self.require(spell, b"SPEL")

    def json_choices(self):
        result = {}
        for key, kind in (("voices", b"VTYP"), ("classes", b"CLAS"), ("styles", b"CSTY"),
                          ("weapons", b"WEAP"), ("ammunition", b"AMMO"), ("perks", b"PERK"), ("spells", b"SPEL")):
            result[key] = [{"id": r.editor_id, "label": self.label(r), "description": self.label(r, b"DESC"),
                            "ranks": r.values(b"DATA")[0][2] if kind == b"PERK" else None}
                           for r in self.choices(kind)
                           if kind != b"VTYP" or r.form_id in self.follower_voice_ids]
        result["marriage_voices"] = [r.editor_id for r in self.choices(b"VTYP") if r.form_id in self.marriage_voice_ids]
        return result
