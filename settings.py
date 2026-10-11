"""Portable, shared settings for the wizard, CLI and all conversion stages."""
from dataclasses import asdict, dataclass, field, fields
import hashlib
import json
import math
from pathlib import Path
import re

VERSION = "0.3.0"


def identifier(name):
    ascii_name = re.sub(r"[^A-Za-z0-9_]", "", name.replace(" ", "_"))[:48]
    if not ascii_name:
        return "Avatar_" + hashlib.sha256(name.encode()).hexdigest()[:12]
    return ascii_name if ascii_name[0].isalpha() else "Avatar_" + ascii_name


@dataclass
class FollowerSettings:
    npc_name: str = "Avatar"
    mod_name: str = "AvatarFollower"
    mod_id: str = ""  # stable ASCII ID; different IDs can coexist in the game
    author: str = ""
    sex: str = "female"
    voice: str = "FemaleEvenToned"
    combat_class: str = "CombatWarrior1H"
    combat_style: str = "csHumanMeleeLvl1"
    level_mode: str = "player"
    auto_calculate: bool = True
    level: int = 10
    level_multiplier: float = 1.0
    min_level: int = 5
    max_level: int = 80
    health: int = 200
    magicka: int = 100
    stamina: int = 150
    protection: str = "protected"
    confidence: int = 4
    aggression: int = 1
    morality: int = 3
    marriage: bool = False
    height_scale: float = 1.0
    weapon: str = "SteelSword"
    ammunition: str = ""
    perks: list = field(default_factory=list)  # {editor_id, rank}; rank is CK's zero-based rank
    spells: list = field(default_factory=list)
    skills: dict = field(default_factory=dict)
    spawn_offset_x: float = 0.0
    spawn_offset_y: float = 0.0
    render_previews: bool = True

    def __post_init__(self):
        if not isinstance(self.mod_id, str) or not isinstance(self.author, str):
            raise ValueError("MOD ID and author must be strings")
        self.mod_id = self.mod_id or identifier(self.mod_name)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", self.mod_id):
            raise ValueError("MOD ID must start with an ASCII letter and contain letters, numbers or underscores (1–64)")
        for name in ("npc_name", "mod_name"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip() or len(value) > 128 or any(ord(c) < 32 for c in value):
                raise ValueError(f"Invalid {name}")
        choices = {"sex": ("female", "male"), "level_mode": ("player", "fixed"),
                   "protection": ("protected", "essential", "mortal")}
        for name, options in choices.items():
            if getattr(self, name) not in options:
                raise ValueError(f"Invalid {name}")
        for name, low, high in (("level", 1, 1000), ("min_level", 1, 1000), ("max_level", 1, 1000),
                                 ("health", 1, 32000), ("magicka", 0, 32000), ("stamina", 0, 32000),
                                 ("confidence", 0, 4), ("aggression", 0, 2), ("morality", 0, 3)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in {low}–{high}")
        if self.min_level > self.max_level:
            raise ValueError("Minimum level exceeds maximum level")
        for name, low, high in (("level_multiplier", .1, 10), ("height_scale", .25, 3),
                                ("spawn_offset_x", -200, 200), ("spawn_offset_y", -200, 200)):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} must be in {low}–{high}")
        if not isinstance(self.skills, dict) or not isinstance(self.perks, list) or not isinstance(self.spells, list):
            raise ValueError("skills must be an object; perks and spells must be lists")
        if self.auto_calculate and self.skills:
            raise ValueError("Individual skills require manual stats calculation")
        for key, value in self.skills.items():
            if key not in SKILLS or type(value) is not int or not 0 <= value <= 100:
                raise ValueError(f"Invalid skill: {key}")
        for perk in self.perks:
            if not isinstance(perk, dict) or set(perk) != {"editor_id", "rank"} or not isinstance(perk["editor_id"], str) or type(perk["rank"]) is not int or not 0 <= perk["rank"] <= 255:
                raise ValueError("Perks require editor_id and a zero-based integer rank")
        if any(not isinstance(spell, str) for spell in self.spells):
            raise ValueError("Spell IDs must be strings")
        for name in ("auto_calculate", "marriage", "render_previews"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be true or false")

    @property
    def prefix(self):
        return "V2S_" + self.mod_id

    @property
    def asset_dir(self):
        return "vrm2skyrim/" + self.mod_id.lower()

    @property
    def plugin_name(self):
        return self.mod_id + ".esp"

    @classmethod
    def from_dict(cls, value):
        unknown = set(value) - {item.name for item in fields(cls)}
        if unknown:
            raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")
        return cls(**value)

    @classmethod
    def load(cls, path):
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8-sig")))

    def save(self, path):
        Path(path).write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf8")


SKILLS = ("OneHanded", "TwoHanded", "Marksman", "Block", "Smithing", "HeavyArmor", "LightArmor",
          "Pickpocket", "Lockpicking", "Sneak", "Alchemy", "Speechcraft", "Alteration", "Conjuration",
          "Destruction", "Illusion", "Restoration", "Enchanting")


def load_settings(output):
    path = Path(output) / "settings.json"
    return FollowerSettings.load(path) if path.exists() else FollowerSettings()


def reference_root(output):
    path = Path(output) / "references.json"
    if path.exists():
        return Path(json.loads(path.read_text(encoding="utf8"))["root"])
    return Path(__file__).resolve().parent / "reference"
