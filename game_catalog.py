"""Read selectable records from the user's Skyrim.esm, without bundled game data."""
import logging
import struct
from pathlib import Path

from plugin import records
from localized_strings import JAPANESE, load_table
from settings import SKILLS

KINDS = {b"NPC_", b"ARMO", b"ARMA", b"RACE", b"FACT", b"VTYP", b"WEAP", b"PACK",
         b"CLAS", b"CSTY", b"PERK", b"SPEL", b"FLST", b"CELL", b"REFR", b"AMMO", b"KYWD", b'BOOK',
         b'AVIF', b'MGEF'}


def castable_spell(record):
    values = record.values(b'SPIT')
    if not values or len(values[0]) < 24 or not record.values(b'FULL'):
        return False
    kind = struct.unpack_from('<I', values[0], 8)[0]
    casting = struct.unpack_from('<I', values[0], 16)[0]
    return kind == 0 and casting in (1, 2) and not record.flags & 0x20


CLASS_LABELS = {'Blade': 'ブレイズの戦士（デルフィンのクラス）'}
SKILL_LABELS = dict(zip(SKILLS, ('片手武器', '両手武器', '弓術', '防御', '鍛冶', '重装', '軽装',
                                'スリ', '開錠', '隠密', '錬金術', '話術', '変性', '召喚', '破壊',
                                '幻惑', '回復', '付呪')))
SKILL_LABELS_EN = dict(zip(SKILLS, ('One-Handed', 'Two-Handed', 'Archery', 'Block', 'Smithing',
                                   'Heavy Armor', 'Light Armor', 'Pickpocket', 'Lockpicking',
                                   'Sneak', 'Alchemy', 'Speech', 'Alteration', 'Conjuration',
                                   'Destruction', 'Illusion', 'Restoration', 'Enchanting')))


def effect_ranks(record):
    """PRKE ranks that actually have effects; DATA Num Ranks alone is not enough."""
    return sorted({value[1] for value in record.values(b'PRKE') if len(value) >= 3}) or [0]


def class_growth(record):
    """CLAS DATA layout: xEdit wbDefinitionsTES5 Skill/Attribute Weights."""
    values = record.values(b'DATA')
    if not values or len(values[0]) < 36:
        return None
    data = values[0]
    return {'skills': dict(zip(SKILLS, data[6:24])),
            'attributes': dict(zip(('health', 'magicka', 'stamina'), data[32:35]))}


class GameCatalog:
    def __init__(self, data):
        self.path = Path(data) / "Skyrim.esm"
        self.by_form_id = {r.form_id: r for r in records(self.path, KINDS)}
        self.by_editor_id = {r.editor_id: r for r in self.by_form_id.values() if r.editor_id}
        # Spell type alone also includes shrine/script/trap effects. The books
        # identify the ordinary spells that actors can learn and cast.
        self.learnable_spells = {struct.unpack_from('<I', value, 4)[0] for r in self.by_editor_id.values()
                                 if r.kind == b'BOOK' for value in r.values(b'DATA')
                                 if len(value) >= 8 and value[0] & 4}
        follower_list = self.require("VoicesFollowerAll", b"FLST")
        self.follower_voice_ids = {struct.unpack("<I", value)[0] for value in follower_list.values(b"LNAM")}
        marriage_list = self.require("VoicesMarriageAll", b"FLST")
        self.marriage_voice_ids = {struct.unpack("<I", value)[0] for value in marriage_list.values(b"LNAM")}
        self.strings = self.load_strings(Path(data))
        self.descriptions = self.load_strings(Path(data), "dlstrings")
        self.english_strings = self.load_strings(Path(data), language='english')
        self.english_descriptions = self.load_strings(Path(data), 'dlstrings', language='english')

    @staticmethod
    def load_strings(data, extension="strings", language=None):
        return load_table(data, 'Skyrim.esm', extension, (language,) if language else ('japanese', 'english'))

    def label(self, record, tag=b"FULL", language=None):
        values = record.values(tag)
        if not values:
            return record.editor_id if tag == b"FULL" else ""
        value = values[0]
        if len(value) == 4:
            if language == 'en':
                table = self.english_descriptions if tag == b'DESC' else self.english_strings
            else:
                table = self.descriptions if tag == b"DESC" else self.strings
            return table.get(struct.unpack("<I", value)[0], record.editor_id if tag == b"FULL" else "")
        text = value.rstrip(b"\0").decode("utf8", "replace")
        if language == 'en' and JAPANESE.search(text):
            return record.editor_id if tag == b'FULL' else ''
        return text

    def localized(self, record, tag=b'FULL'):
        return {'ja': self.label(record, tag), 'en': self.label(record, tag, language='en')}

    def require(self, editor_id, kind=None):
        record = self.by_editor_id.get(editor_id)
        if record is None or (kind and record.kind != kind):
            raise ValueError(f"Skyrim.esm {kind.decode() if kind else 'record'} not found: {editor_id}")
        return record

    def choices(self, kind):
        return sorted((r for r in self.by_editor_id.values() if r.kind == kind), key=lambda r: r.editor_id.lower())

    def actor_race(self, actor, seen=None):
        # Use Traits inherits RNAM. Leveled-list templates have multiple possible
        # actors; leave those unclassified rather than guessing a race.
        seen = set() if seen is None else seen
        if actor.form_id in seen:
            return None
        seen.add(actor.form_id)
        acbs = actor.values(b'ACBS')
        if acbs and len(acbs[0]) >= 20 and struct.unpack_from('<H', acbs[0], 18)[0] & 1:
            template = actor.values(b'TPLT')
            parent = self.by_form_id.get(struct.unpack('<I', template[0])[0]) if template else None
            return self.actor_race(parent, seen) if parent and parent.kind == b'NPC_' else None
        race = actor.values(b'RNAM')
        result = self.by_form_id.get(struct.unpack('<I', race[0])[0]) if race else None
        return result if result and result.kind == b'RACE' else None

    def style_usage(self, language=None):
        """Positive usage evidence, not a claim that CSTY is race-restricted."""
        usage = {}
        for actor in self.choices(b'NPC_'):
            acbs = actor.values(b'ACBS')
            # Positive evidence only: skip deleted actors and AI-data inherited
            # actors whose local ZNAM may not be their effective combat style.
            if actor.flags & 4 or (acbs and len(acbs[0]) >= 20
                                   and struct.unpack_from('<H', acbs[0], 18)[0] & 0x10):
                continue
            values = actor.values(b'ZNAM')
            race = self.actor_race(actor)
            if not values or not race:
                continue
            style = struct.unpack('<I', values[0])[0]
            paths = [v.rstrip(b'\0').decode('utf8', 'replace').replace('\\', '/').lower()
                     for v in race.values(b'ANAM')]
            if not paths:
                continue
            kind = 'humanoid' if all(p.startswith('actors/character/') for p in paths) else 'other'
            row = usage.setdefault(style, {'humanoid': set(), 'other': set()})
            row[kind].add(self.label(race, language=language))
        return usage

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
            if perk['rank'] not in effect_ranks(record):
                raise ValueError(f"このPerkの指定ランクに効果がありません: {perk['editor_id']}")
        for spell in settings.spells:
            self.require(spell, b"SPEL")
        if settings.fit_armors:
            from armor_catalog import official_choices
            from official_catalog import OfficialCatalog
            equipment = OfficialCatalog(self.path.parent)
            allowed = {r.form_id for r in official_choices(equipment, settings.sex)}
            if any(equipment.require(key, b'ARMO').form_id not in allowed for key in settings.fit_armors):
                raise ValueError('人型向けの公式装備を選んでください')

    def perk_categories(self):
        """Follow AVIF PNAM trees and PERK NNAM chains, not translated names."""
        result, stages = {}, {}
        for skill, label in SKILL_LABELS.items():
            tree = self.by_editor_id.get('AVMysticism' if skill == 'Illusion' else 'AV'+skill)
            if not tree:
                continue
            for value in tree.values(b'PNAM'):
                if len(value) != 4:
                    continue
                chain, seen = [], set()
                record = self.by_form_id.get(struct.unpack('<I', value)[0])
                while record and record.kind == b'PERK' and record.form_id not in seen:
                    seen.add(record.form_id)
                    chain.append(record)
                    result.setdefault(record.form_id, set()).add(skill)
                    next_ = record.values(b'NNAM')
                    record = self.by_form_id.get(struct.unpack('<I', next_[0])[0]) if next_ else None
                if len(chain) > 1:
                    for index, record in enumerate(chain):
                        stages.setdefault(record.form_id, {'index': index+1, 'total': len(chain)})
        return result, stages

    def spell_categories(self, record, perks):
        data = record.values(b'SPIT')
        if data and len(data[0]) >= 36:
            perk = struct.unpack_from('<I', data[0], 32)[0]
            if perks.get(perk):
                return sorted(perks[perk])
        schools = set()
        for value in record.values(b'EFID'):
            effect = self.by_form_id.get(struct.unpack('<I', value)[0])
            data = effect.values(b'DATA') if effect and effect.kind == b'MGEF' else []
            if not data or len(data[0]) < 16 or struct.unpack_from('<f', data[0], 4)[0] <= 0:
                continue  # Zero-cost perk helpers do not define the spell's school.
            school = struct.unpack_from('<i', data[0], 12)[0]
            if 18 <= school <= 22:
                schools.add(SKILLS[school-6])
        return sorted(schools) or ['other']

    def json_choices(self, sex='female'):
        if sex not in ('female', 'male'):
            raise ValueError('Invalid equipment sex')
        result = {}
        for key, kind in (("voices", b"VTYP"), ("classes", b"CLAS"), ("styles", b"CSTY"),
                          ("weapons", b"WEAP"), ("ammunition", b"AMMO"), ("perks", b"PERK"), ("spells", b"SPEL")):
            result[key] = [{"id": r.editor_id, "label": self.label(r), "description": self.label(r, b"DESC"),
                            'labels': self.localized(r), 'descriptions': self.localized(r, b'DESC'),
                            "ranks": r.values(b"DATA")[0][2] if kind == b"PERK" else None}
                           for r in self.choices(kind)
                           if (kind != b"VTYP" or r.form_id in self.follower_voice_ids)
                           and (kind != b'SPEL' or (castable_spell(r) and r.form_id in self.learnable_spells))]
        for item in result['classes']:
            item['label'] = CLASS_LABELS.get(item['id'], item['label'])
            if item['id'] == 'Blade':
                item['labels'] = {'ja': CLASS_LABELS['Blade'], 'en': "Blades Warrior (Delphine's class)"}
            item['growth'] = class_growth(self.require(item['id']))
        perk_categories, stages = self.perk_categories()
        for item in result['perks']:
            record = self.require(item['id'])
            item['categories'] = sorted(perk_categories.get(record.form_id, {'other'}))
            item['stage'] = stages.get(record.form_id)
            item['effect_ranks'] = effect_ranks(record)
        for item in result['spells']:
            item['categories'] = self.spell_categories(self.require(item['id']), perk_categories)
        result['categories'] = [{'id': key, 'label': label, 'labels': {'ja': label, 'en': SKILL_LABELS_EN[key]}}
                                for key, label in SKILL_LABELS.items()]
        result['categories'].append({'id': 'other', 'label': 'その他・特殊効果',
                                     'labels': {'ja': 'その他・特殊効果', 'en': 'Other / special effects'}})
        usage = self.style_usage()
        english_usage = self.style_usage(language='en')
        for item in result['styles']:
            row = usage.get(self.require(item['id']).form_id, {'humanoid': set(), 'other': set()})
            item['humanoid'] = bool(row['humanoid'])
            item['used_by'] = sorted(row['humanoid'] | row['other'])
            en_row = english_usage.get(self.require(item['id']).form_id, {'humanoid': set(), 'other': set()})
            item['used_by_localized'] = {'ja': item['used_by'], 'en': sorted(en_row['humanoid'] | en_row['other'])}
        logging.debug('Wizard catalog: %d classes, %d combat styles (%d with character-skeleton NPC usage)',
                      len(result['classes']), len(result['styles']), sum(s['humanoid'] for s in result['styles']))
        result["marriage_voices"] = [r.editor_id for r in self.choices(b"VTYP") if r.form_id in self.marriage_voice_ids]
        result['english_strings_available'] = bool(self.english_strings)
        from armor_catalog import official_choices, slot_mask
        from official_catalog import OfficialCatalog
        catalog = OfficialCatalog(self.path.parent)
        result['equipment_plugins'] = catalog.plugins
        result['armors'] = [{'id': catalog.key(r), 'editor_id': r.editor_id, 'key': catalog.key(r), 'label': catalog.label(r),
                             'labels': {'ja': catalog.label(r), 'en': catalog.label(r, language='en')},
                             'plugin': catalog.identity(r)[0], 'mask': slot_mask(r),
                             'addons': [{'key': catalog.key(a), 'name': a.editor_id, 'mask': slot_mask(a)}
                                        for a in catalog.addon_records(r, sex)]}
                            for r in official_choices(catalog, sex)]
        return result
