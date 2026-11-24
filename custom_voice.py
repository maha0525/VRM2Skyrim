"""Custom Skyrim SE VoiceType (VTYP), follower/combat dialogue (QUST/DIAL/INFO), and .fuz/.lip audio pipeline."""
import copy
import json
import logging
import re
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

from plugin import Record

ROOT = Path(__file__).resolve().parent
LOG = logging.getLogger(__name__)

CUSTOM_VOICE_ID = 0x010008E0
VOICE_QUEST_ID = 0x010008E1
VOICE_DIAL_BASE_ID = 0x010008E2  # up to 0x010008FD (28 private DIAL slots)
VOICE_RECRUIT_DIAL_ID = 0x010008FE  # private top-level recruit DIAL (replaces DialogueFavorGeneric)
VOICE_RECRUIT_DLBR_ID = 0x010008FF  # private top-level recruit DLBR
VOICE_INFO_BASE_ID = 0x01000900  # private INFO records start here
VOICES_FOLLOWER_ALL_ID = 0x000C78E7
DEFAULT_NPC_VOICE_TYPES_ID = 0x0003B4A5
RECRUIT_VANILLA_DIAL_ID = 0x000B0EE6
VOICE_REG_TEMPLATE = "V2SVoiceRegister"

# Scene catalog: 30 follower-relevant scenes across 3 tiers (required / recommended / optional).
# Excludes the 10 stealth/search/combat-start-end topics that vanilla Skyrim forces silent for teammates.
VOICE_SCENES = [
    # --- Tier 1: required (core follower dialogue via vanilla DialogueFavorGeneric / DialogueFollower DIALs) ---
    {
        "id": "recruit_accept",
        "tier": "required",
        "group": "follower",
        "label_ja": "勧誘されたとき（承諾）",
        "label_en": "Recruit (Accept)",
        "context_ja": "プレイヤーに「ついて来てくれ。手を貸してほしい」と勧誘され、同行を引き受けるときの返事。",
        "context_en": "Accepting the player's request to follow them.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFavorGeneric",
        "vanilla_dial_id": 0x000B0EE6,
        "vanilla_topic_edid": "DialogueFavorGenericFollowBranchTopic",
        "template_info_id": 0x000B0EE9,
        "sample_info_ids": [0x000B0EE9, 0x000D8DDF, 0x000D8DE0],
        "default_lines_ja": ["いいだろう。先導してくれ。"],
    },
    {
        "id": "recruit_full",
        "tier": "required",
        "group": "follower",
        "label_ja": "勧誘されたとき（すでに同行者がいる）",
        "label_en": "Recruit (Already Has Follower)",
        "context_ja": "プレイヤーがすでに別のフォロワーを連れている状態で勧誘されたときの返事。",
        "context_en": "Responding when the player already has another follower.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFavorGeneric",
        "vanilla_dial_id": 0x000B0EE6,
        "vanilla_topic_edid": "DialogueFavorGenericFollowBranchTopic",
        "template_info_id": 0x0005C829,
        "sample_info_ids": [0x0005C829, 0x000D8DE3, 0x000D8DE6],
        "default_lines_ja": ["すでに誰かを連れているようだが。"],
    },
    {
        "id": "follower_hello",
        "tier": "required",
        "group": "follower",
        "label_ja": "同行中に話しかけたとき",
        "label_en": "Follower Greeting",
        "context_ja": "同行中のフォロワーにプレイヤーが話しかけたときの第一声。",
        "context_en": "Greeting when the player talks to them while following.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x000284F6,
        "vanilla_topic_edid": "DialogueFollowerHellos",
        "template_info_id": 0x000D235E,
        "sample_info_ids": [0x000D235E, 0x000D235F, 0x0005C82B, 0x000E1563, 0x000E1561],
        "default_lines_ja": ["準備はいいか？", "すぐ後ろにいる。"],
    },
    {
        "id": "follow",
        "tier": "required",
        "group": "follower",
        "label_ja": "「ついて来て」",
        "label_en": "Follow Me",
        "context_ja": "待機状態から再び同行を命じられたときの返事。",
        "context_en": "Resuming following after waiting.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x00075083,
        "vanilla_topic_edid": "DialogueFollowerFollowTopic",
        "template_info_id": 0x0007A1EB,
        "sample_info_ids": [0x0007A1EB, 0x0007508E],
        "default_lines_ja": ["行こう。"],
    },
    {
        "id": "wait",
        "tier": "required",
        "group": "follower",
        "label_ja": "「待っていて」",
        "label_en": "Wait Here",
        "context_ja": "その場で待機するよう命じられたときの返事。",
        "context_en": "Being told to wait in place.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x00075084,
        "vanilla_topic_edid": "DialogueFollowerWaitTopic",
        "template_info_id": 0x0007A1E9,
        "sample_info_ids": [0x0007A1E9, 0x000E158B],
        "default_lines_ja": ["分かった。ここで待っている。"],
    },
    {
        "id": "trade",
        "tier": "required",
        "group": "follower",
        "label_ja": "「持ち物を見せて」（取引）",
        "label_en": "Trade Items",
        "context_ja": "持ち物の交換画面を開くときの返事。",
        "context_en": "Opening the inventory trade screen.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x00060020,
        "vanilla_topic_edid": "DialogueFollowerTradeTopic",
        "template_info_id": 0x0007A1E8,
        "sample_info_ids": [0x0007A1E8, 0x0007A510],
        "default_lines_ja": ["何を持ちましょうか？"],
    },
    {
        "id": "dismiss",
        "tier": "required",
        "group": "follower",
        "label_ja": "「もう行っていい」（解雇）",
        "label_en": "Dismiss",
        "context_ja": "同行を解除して別れるときの返事。",
        "context_en": "Being dismissed from following.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x0005C80C,
        "vanilla_topic_edid": "DialogueFollowerDismissTopic",
        "template_info_id": 0x0007A1EA,
        "sample_info_ids": [0x0007A1EA, 0x0007A50B],
        "default_lines_ja": ["なら戻っているよ。用があったら来てくれ。"],
    },
    {
        "id": "follower_goodbye",
        "tier": "required",
        "group": "follower",
        "label_ja": "同行中の会話を終えるとき",
        "label_en": "Follower Goodbye",
        "context_ja": "同行中の会話メニューを閉じるときのひとこと。",
        "context_en": "Closing dialogue while following.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x00026B30,
        "vanilla_topic_edid": "",
        "template_info_id": 0x000D2351,
        "sample_info_ids": [0x000D2351, 0x000D2352, 0x000E1573, 0x000E1571],
        "default_lines_ja": ["先に行ってくれ。ついて行く。"],
    },
    # --- Tier 2: recommended (favor commands + combat) ---
    {
        "id": "favor_start",
        "tier": "recommended",
        "group": "favor",
        "label_ja": "「頼みたいことがある」",
        "label_en": "Favor Start",
        "context_ja": "プレイヤーから「手伝ってもらおうかな」と指示モードに入るときの返事。",
        "context_en": "Entering follower command mode.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x00026E0E,
        "vanilla_topic_edid": "DialogueFollowerFavorStateTopic",
        "template_info_id": 0x000E1567,
        "sample_info_ids": [0x000E1567],
        "default_lines_ja": ["何が必要だ？"],
    },
    {
        "id": "favor_show",
        "tier": "recommended",
        "group": "favor",
        "label_ja": "頼み事モードに入ったとき",
        "label_en": "Favor Prompt",
        "context_ja": "指示対象を選んでいる最中の問いかけ。",
        "context_en": "Waiting for a target in command mode.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x00026ED0,
        "vanilla_topic_edid": "",
        "template_info_id": 0x00026F4F,
        "sample_info_ids": [0x00026F4F],
        "default_lines_ja": ["何をしてほしい？"],
    },
    {
        "id": "favor_agree",
        "tier": "recommended",
        "group": "favor",
        "label_ja": "頼み事を引き受ける",
        "label_en": "Favor Agree",
        "context_ja": "物を拾う・開けるなどの指示を承諾するとき。",
        "context_en": "Agreeing to perform a commanded action.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x00026EC9,
        "vanilla_topic_edid": "",
        "template_info_id": 0x00026F4A,
        "sample_info_ids": [0x00026F4A],
        "default_lines_ja": ["分かった。"],
    },
    {
        "id": "favor_refuse",
        "tier": "recommended",
        "group": "favor",
        "label_ja": "頼み事を断る（実行不能）",
        "label_en": "Favor Refuse",
        "context_ja": "届かない・開けられないなど実行できない指示を断るとき。",
        "context_en": "Refusing an impossible command.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x00026EC3,
        "vanilla_topic_edid": "",
        "template_info_id": 0x00026FE4,
        "sample_info_ids": [0x00026FE4],
        "default_lines_ja": ["それはできない。"],
    },
    {
        "id": "favor_moral_refuse",
        "tier": "recommended",
        "group": "favor",
        "label_ja": "頼み事を道徳的に断る",
        "label_en": "Favor Moral Refuse",
        "context_ja": "犯罪行為など道徳的に受け入れられない指示を断るとき。",
        "context_en": "Refusing a crime or immoral command.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x00026E7D,
        "vanilla_topic_edid": "",
        "template_info_id": 0x000D8DC7,
        "sample_info_ids": [0x000D8DC7],
        "default_lines_ja": ["それは断る。"],
    },
    {
        "id": "favor_exit",
        "tier": "recommended",
        "group": "favor",
        "label_ja": "頼み事モードを抜ける",
        "label_en": "Favor Exit",
        "context_ja": "指示を実行し終えて通常状態に戻るとき。",
        "context_en": "Finishing command mode.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x00026E81,
        "vanilla_topic_edid": "",
        "template_info_id": 0x00026F64,
        "sample_info_ids": [0x00026F64],
        "default_lines_ja": ["他に何か？"],
    },
    {
        "id": "favor_end",
        "tier": "recommended",
        "group": "favor",
        "label_ja": "頼み事をキャンセルされたとき",
        "label_en": "Favor Cancel",
        "context_ja": "「いや、気にしないでくれ」と指示を取り消されたとき。",
        "context_en": "Command mode canceled by the player.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x00026DFD,
        "vanilla_topic_edid": "DialogueFollowerEndFavorState",
        "template_info_id": 0x000D8E14,
        "sample_info_ids": [0x000D8E14],
        "default_lines_ja": ["分かった。"],
    },
    {
        "id": "favor_continue",
        "tier": "recommended",
        "group": "favor",
        "label_ja": "頼み事を続けるとき",
        "label_en": "Favor Continue",
        "context_ja": "指示を続けるよう言われたとき。",
        "context_en": "Continuing command mode.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x00026DFF,
        "vanilla_topic_edid": "DialogueFollowerContinueFavorState",
        "template_info_id": 0x000D8DCC,
        "sample_info_ids": [0x000D8DCC],
        "default_lines_ja": ["見せてくれ。"],
    },
    {
        "id": "favor_blocking",
        "tier": "recommended",
        "group": "favor",
        "label_ja": "頼み事の最中に話しかけたとき",
        "label_en": "Favor In Progress",
        "context_ja": "指示モード中に再度話しかけられたときの問いかけ。",
        "context_en": "Spoken to while command mode is active.",
        "mode": "vanilla_dial",
        "vanilla_quest": "DialogueFollower",
        "vanilla_dial_id": 0x00026E0D,
        "vanilla_topic_edid": "DialogueFollowerDoingFavorBlockingTopic",
        "template_info_id": 0x000E1565,
        "sample_info_ids": [0x000E1565],
        "default_lines_ja": ["まだ何かあるか？"],
    },
    # Combat (private DIALs under V2S_<ModID>VoiceQuest)
    {
        "id": "combat_attack",
        "tier": "recommended",
        "group": "combat",
        "label_ja": "戦闘：攻撃するとき",
        "label_en": "Combat: Attack",
        "context_ja": "敵に通常攻撃や魔法を仕掛けるときの掛け声・台詞。",
        "context_en": "Shouting or speaking when attacking an enemy.",
        "mode": "private_dial",
        "subtype": "ATCK",
        "dial_data": bytes.fromhex("00031400"),
        "sample_subtype": "ATCK",
        "default_lines_ja": ["そこだ！", "逃がさない！"],
    },
    {
        "id": "combat_power_attack",
        "tier": "recommended",
        "group": "combat",
        "label_ja": "戦闘：強攻撃",
        "label_en": "Combat: Power Attack",
        "context_ja": "力を込めた強攻撃を放つときの掛け声。",
        "context_en": "Effort shout during a power attack.",
        "mode": "private_dial",
        "subtype": "POAT",
        "dial_data": bytes.fromhex("00031500"),
        "sample_subtype": "POAT",
        "default_lines_ja": ["はぁっ！"],
    },
    {
        "id": "combat_bash",
        "tier": "recommended",
        "group": "combat",
        "label_ja": "戦闘：盾・武器で殴る",
        "label_en": "Combat: Bash",
        "context_ja": "盾や武器の柄で敵を弾くときの掛け声。",
        "context_en": "Effort shout when bashing.",
        "mode": "private_dial",
        "subtype": "BASH",
        "dial_data": bytes.fromhex("00031600"),
        "sample_subtype": "BASH",
        "default_lines_ja": ["っ！"],
    },
    {
        "id": "combat_hit",
        "tier": "recommended",
        "group": "combat",
        "label_ja": "戦闘：攻撃を受けたとき",
        "label_en": "Combat: Hit",
        "context_ja": "敵の攻撃を受けたときのうめき声や悔しがる台詞。",
        "context_en": "Reacting when hit by an enemy.",
        "mode": "private_dial",
        "subtype": "HIT_",
        "dial_data": bytes.fromhex("00031700"),
        "sample_subtype": "HIT_",
        "default_lines_ja": ["くっ…！", "その程度か！"],
    },
    {
        "id": "combat_block",
        "tier": "recommended",
        "group": "combat",
        "label_ja": "戦闘：防御したとき",
        "label_en": "Combat: Block",
        "context_ja": "敵の攻撃をガードしたときの反応。",
        "context_en": "Reacting when blocking an attack.",
        "mode": "private_dial",
        "subtype": "BLOC",
        "dial_data": bytes.fromhex("00031d00"),
        "sample_subtype": "BLOC",
        "default_lines_ja": ["甘い！"],
    },
    {
        "id": "combat_taunt",
        "tier": "recommended",
        "group": "combat",
        "label_ja": "戦闘：挑発",
        "label_en": "Combat: Taunt",
        "context_ja": "戦闘中に敵を煽る・威嚇するときの台詞。",
        "context_en": "Taunting enemies during combat.",
        "mode": "private_dial",
        "subtype": "TAUT",
        "dial_data": bytes.fromhex("00031e00"),
        "sample_subtype": "TAUT",
        "default_lines_ja": ["覚悟はできているか？"],
    },
    {
        "id": "combat_bleedout",
        "tier": "recommended",
        "group": "combat",
        "label_ja": "戦闘：瀕死（膝をつく）",
        "label_en": "Combat: Bleedout",
        "context_ja": "体力が尽きて膝をついたときの台詞。",
        "context_en": "Falling to a knee when critically wounded.",
        "mode": "private_dial",
        "subtype": "BLED",
        "dial_data": bytes.fromhex("00031900"),
        "sample_subtype": "BLED",
        "default_lines_ja": ["まだ…終わりじゃない…"],
    },
    {
        "id": "combat_death",
        "tier": "recommended",
        "group": "combat",
        "label_ja": "戦闘：倒れるとき",
        "label_en": "Combat: Death",
        "context_ja": "力尽きて倒れるときの最後の声。",
        "context_en": "Dying cry when defeated.",
        "mode": "private_dial",
        "subtype": "DETH",
        "dial_data": bytes.fromhex("00031b00"),
        "sample_subtype": "DETH",
        "default_lines_ja": ["うっ…"],
    },
    {
        "id": "combat_flee",
        "tier": "recommended",
        "group": "combat",
        "label_ja": "戦闘：逃げる・後退する",
        "label_en": "Combat: Flee",
        "context_ja": "危険を感じて後退・逃走するときの台詞。",
        "context_en": "Retreating or fleeing from combat.",
        "mode": "private_dial",
        "subtype": "FLEE",
        "dial_data": bytes.fromhex("00031800"),
        "sample_subtype": "FLEE",
        "default_lines_ja": ["いったん引く！"],
    },
    # --- Tier 3: optional (ambient / greeting / yield) ---
    {
        "id": "hello",
        "tier": "optional",
        "group": "ambient",
        "label_ja": "挨拶（同行していないとき）",
        "label_en": "Greeting (Not Following)",
        "context_ja": "雇っていない状態で近づいたり話しかけたときの挨拶。",
        "context_en": "Greeting when not currently following.",
        "mode": "private_dial",
        "subtype": "HELO",
        "dial_data": bytes.fromhex("00074f00"),
        "sample_subtype": "HELO",
        "default_lines_ja": [],
    },
    {
        "id": "goodbye",
        "tier": "optional",
        "group": "ambient",
        "label_ja": "別れ（同行していないとき）",
        "label_en": "Goodbye (Not Following)",
        "context_ja": "雇っていない状態で会話を終えるときの別れの挨拶。",
        "context_en": "Goodbye when not currently following.",
        "mode": "private_dial",
        "subtype": "GBYE",
        "dial_data": bytes.fromhex("00074e00"),
        "sample_subtype": "GBYE",
        "default_lines_ja": [],
    },
    {
        "id": "location_idle",
        "tier": "optional",
        "group": "ambient",
        "label_ja": "道中のひとこと",
        "label_en": "Idle / Exploration Comment",
        "context_ja": "探索中や待機中にふと漏らす独り言。",
        "context_en": "Occasional idle remark while exploring.",
        "mode": "private_dial",
        "subtype": "IDLE",
        "dial_data": bytes.fromhex("00075800"),
        "sample_subtype": "IDLE",
        "default_lines_ja": [],
    },
    {
        "id": "accept_yield",
        "tier": "optional",
        "group": "combat",
        "label_ja": "降参を受け入れる",
        "label_en": "Accept Yield",
        "context_ja": "敵や乱闘相手が降参したときに許すひとこと。",
        "context_en": "Accepting an opponent's surrender.",
        "mode": "private_dial",
        "subtype": "ACYI",
        "dial_data": bytes.fromhex("00032200"),
        "sample_subtype": "ACYI",
        "default_lines_ja": [],
    },
]

SCENE_BY_ID = {scene["id"]: scene for scene in VOICE_SCENES}
REQUIRED_SCENE_IDS = [scene["id"] for scene in VOICE_SCENES if scene["tier"] == "required"]


def voice_edid(settings) -> str:
    return f"{settings.prefix}Voice"


def voice_quest_edid(settings) -> str:
    return f"{settings.prefix}VoiceQuest"


def voice_reg_script_name(settings) -> str:
    return f"{settings.prefix}VoiceReg"


def fuz_stem(quest_edid: str, topic_edid: str, info_form_id: int) -> str:
    """Skyrim SE exact voice filename stem (verified against Skyrim - Voices_ja0.bsa).

    Whenever len(quest) + len(topic) > 25 (including when topic is empty),
    quest is truncated to 10 chars and topic to (25 - len(q_part)) chars.
    """
    low = info_form_id & 0xFFFFFF
    if len(quest_edid) + len(topic_edid) > 25:
        q_part = quest_edid[:10]
        t_part = topic_edid[: 25 - len(q_part)]
    else:
        q_part, t_part = quest_edid, topic_edid
    return f"{q_part}_{t_part}_{low:08x}_1"


def normalize_voice_lines(raw) -> dict[str, list[dict]]:
    """Validate and normalize custom_voice_lines into {scene_id: [{id, text, audio}]}."""
    if not raw:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("custom_voice_lines must be a JSON object keyed by scene ID")
    result = {}
    for scene_id, entries in raw.items():
        if scene_id not in SCENE_BY_ID:
            continue
        if not isinstance(entries, list):
            raise ValueError(f"Scene '{scene_id}' must be a list of lines")
        seen_ids = set()
        normalized = []
        next_num = 1
        for item in entries:
            if isinstance(item, str):
                text = item.strip()
                if not text:
                    continue
                while f"{next_num:02d}" in seen_ids:
                    next_num += 1
                line_id = f"{next_num:02d}"
                next_num += 1
                audio = ""
            elif isinstance(item, dict):
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                raw_id = str(item.get("id", "")).strip()
                if raw_id and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", raw_id) and raw_id not in seen_ids:
                    line_id = raw_id
                else:
                    while f"{next_num:02d}" in seen_ids:
                        next_num += 1
                    line_id = f"{next_num:02d}"
                    next_num += 1
                audio = str(item.get("audio", "")).strip()
            else:
                raise ValueError(f"Invalid line entry in scene '{scene_id}'")
            if len(text) > 250:
                raise ValueError(f"Dialogue line too long (>250 chars) in '{scene_id}/{line_id}'")
            seen_ids.add(line_id)
            entry = {"id": line_id, "text": text}
            if audio:
                entry["audio"] = Path(audio).name
            normalized.append(entry)
        if normalized:
            result[scene_id] = normalized
    return result


def validate_custom_voice_settings(settings):
    if settings.voice_mode == "official":
        return
    if settings.voice_mode != "custom":
        raise ValueError("Invalid voice_mode (must be 'official' or 'custom')")
    lines = normalize_voice_lines(settings.custom_voice_lines)
    missing = [sid for sid in REQUIRED_SCENE_IDS if not lines.get(sid)]
    if missing:
        labels = [SCENE_BY_ID[sid]["label_ja"] for sid in missing[:4]]
        raise ValueError(f"専用ボイスの必須セリフが未入力です: {', '.join(labels)}")


def default_voice_lines() -> dict[str, list[dict]]:
    result = {}
    for scene in VOICE_SCENES:
        defaults = scene.get("default_lines_ja") or []
        if defaults:
            result[scene["id"]] = [
                {"id": f"{i + 1:02d}", "text": txt}
                for i, txt in enumerate(defaults)
            ]
    return result


_AUDIO_EXT_RE = re.compile(r"\.(?:wav|ogg|mp3|flac|m4a)$", re.IGNORECASE)


def build_tts_batch_items(voice_lines: dict) -> list[dict[str, str]]:
    """Flatten custom_voice_lines into [{"filename": ..., "text": ...}] for batch TTS tools.

    Output matches SAIVerse saiverse-voice-tts batch JSON array format so that the
    generated WAV ZIP can be imported directly back into VRM2Skyrim.
    """
    normalized = normalize_voice_lines(voice_lines)
    items: list[dict[str, str]] = []
    for scene in VOICE_SCENES:
        sid = scene["id"]
        for entry in normalized.get(sid, []):
            raw_audio = entry.get("audio") or ""
            stem = _AUDIO_EXT_RE.sub("", Path(raw_audio).name) if raw_audio else f"{sid}_{entry['id']}"
            items.append({
                "filename": stem or f"{sid}_{entry['id']}",
                "text": entry["text"],
            })
    return items


# --- Sample extraction from Skyrim.esm + Interface.bsa ---
_SAMPLE_CACHE = {}


def _load_strings(game_data: Path, lang: str) -> dict[int, str]:
    """Load null-terminated .STRINGS table (used by DIAL FULL, etc.) from Skyrim - Interface.bsa."""
    from bsa import BSA
    bsa_path = Path(game_data) / "Skyrim - Interface.bsa"
    if not bsa_path.is_file():
        return {}
    key = f"strings/skyrim_{lang}.strings"
    bsa = BSA(bsa_path)
    if key not in bsa.entries:
        return {}
    blob = bsa.read(key)
    count, _ = struct.unpack_from("<II", blob)
    base = 8 + count * 8
    table = {}
    for i in range(count):
        sid, offset = struct.unpack_from("<II", blob, 8 + i * 8)
        start = base + offset
        end = blob.find(b"\0", start)
        if end == -1:
            end = len(blob)
        table[sid] = blob[start:end].decode("utf8", "replace")
    return table


def _load_ilstrings(game_data: Path, lang: str) -> dict[int, str]:
    from bsa import BSA
    bsa_path = Path(game_data) / "Skyrim - Interface.bsa"
    if not bsa_path.is_file():
        return {}
    key = f"strings/skyrim_{lang}.ilstrings"
    bsa = BSA(bsa_path)
    if key not in bsa.entries:
        return {}
    blob = bsa.read(key)
    count, _ = struct.unpack_from("<II", blob)
    base = 8 + count * 8
    table = {}
    for i in range(count):
        sid, offset = struct.unpack_from("<II", blob, 8 + i * 8)
        length = struct.unpack_from("<I", blob, base + offset)[0]
        table[sid] = blob[base + offset + 4 : base + offset + 4 + length].rstrip(b"\0").decode("utf8", "replace")
    return table


def _recorded_info_ids(game_data: Path, base_voice: str) -> set[int]:
    """Return low-24-bit Skyrim.esm INFO FormIDs that have recordings for base_voice."""
    from bsa import BSA
    voice_lower = base_voice.lower()
    recorded = set()
    for bsa_name in ("Skyrim - Voices_ja0.bsa", "Skyrim - Voices_en0.bsa"):
        bsa_path = Path(game_data) / bsa_name
        if not bsa_path.is_file():
            continue
        for key in BSA(bsa_path).entries:
            # sound/voice/skyrim.esm/<voice>/<prefix>_<hex8>_<resp>.fuz
            parts = key.split("/")
            if len(parts) == 5 and parts[0] == "sound" and parts[1] == "voice" and parts[2] == "skyrim.esm" and parts[3] == voice_lower and parts[4].endswith(".fuz"):
                m = re.search(r"_([0-9a-f]{8})_\d+\.fuz$", parts[4])
                if m:
                    recorded.add(int(m.group(1), 16) & 0xFFFFFF)
        if recorded:
            break
    return recorded


def extract_sample_lines(game_data: Path, base_voice: str = "FemaleEvenToned") -> dict[str, dict]:
    """Return {scene_id: {'ja': [...], 'en': [...]}} sampled from Skyrim.esm for the chosen base_voice."""
    game_data = Path(game_data).resolve()
    cache_key = (str(game_data), base_voice.lower())
    if cache_key in _SAMPLE_CACHE:
        return _SAMPLE_CACHE[cache_key]

    esm = game_data / "Skyrim.esm"
    if not esm.is_file():
        return {s["id"]: {"ja": s.get("default_lines_ja", []), "en": []} for s in VOICE_SCENES}

    il_ja = _load_ilstrings(game_data, "japanese")
    il_en = _load_ilstrings(game_data, "english")
    recorded = _recorded_info_ids(game_data, base_voice)

    from probe_follower_data import contextual_records

    # Pass 1: resolve base_voice VTYP FormID and all FLSTs containing it
    vtyp_id = None
    flst_members = {}
    for rec, _ in contextual_records(esm, {b"VTYP", b"FLST"}):
        if rec.kind == b"VTYP" and rec.editor_id.lower() == base_voice.lower():
            vtyp_id = rec.form_id
        elif rec.kind == b"FLST":
            flst_members[rec.form_id] = {struct.unpack("<I", v)[0] for v in rec.values(b"LNAM")}

    matching_voice_ids = set()
    if vtyp_id is not None:
        matching_voice_ids.add(vtyp_id)
        for fid, members in flst_members.items():
            if vtyp_id in members:
                matching_voice_ids.add(fid)

    # Map vanilla DIALs and DialogueGeneric combat/ambient DIALs
    vanilla_dial_ids = {s["vanilla_dial_id"] for s in VOICE_SCENES if s["mode"] == "vanilla_dial"}
    wanted_subtypes = {s["sample_subtype"] for s in VOICE_SCENES if s.get("sample_subtype")}
    generic_dials = {}  # dial_id -> subtype
    dial_infos = {did: [] for did in vanilla_dial_ids}
    subtype_infos = {st: [] for st in wanted_subtypes}

    for rec, groups in contextual_records(esm, {b"DIAL", b"INFO"}):
        if rec.kind == b"DIAL":
            qnam = rec.values(b"QNAM")
            snam = rec.values(b"SNAM")
            if qnam and struct.unpack("<I", qnam[0])[0] == 0x00013EB3 and snam:
                st = snam[0].decode("ascii", "replace")
                if st in wanted_subtypes:
                    generic_dials[rec.form_id] = st
        elif rec.kind == b"INFO":
            parent = next((struct.unpack("<I", label)[0] for label, kind in reversed(groups) if kind == 7), None)
            if parent not in dial_infos and parent not in generic_dials:
                continue
            nam1 = rec.values(b"NAM1")
            if not nam1 or len(nam1[0]) != 4:
                continue
            sid = struct.unpack("<I", nam1[0])[0]
            ja_txt = il_ja.get(sid, "").strip()
            en_txt = il_en.get(sid, "").strip()
            if not ja_txt and not en_txt:
                continue
            ctda = rec.values(b"CTDA")
            # Skip NPC-specific (GetIsID fn=72) lines so samples reflect generic voice type
            if any(len(c) >= 12 and struct.unpack_from("<H", c, 8)[0] == 72 for c in ctda):
                continue
            voice_conds = [struct.unpack_from("<I", c, 12)[0] for c in ctda if len(c) >= 16 and struct.unpack_from("<H", c, 8)[0] == 426]
            if voice_conds and matching_voice_ids and not (set(voice_conds) & matching_voice_ids):
                continue
            has_rec = (rec.form_id & 0xFFFFFF) in recorded
            has_vmad = bool(rec.values(b"VMAD"))
            entry = (has_rec, bool(voice_conds), has_vmad, rec.form_id, ja_txt, en_txt)
            if parent in dial_infos:
                dial_infos[parent].append(entry)
            else:
                subtype_infos[generic_dials[parent]].append(entry)

    result = {}
    for s in VOICE_SCENES:
        if s["mode"] == "vanilla_dial":
            candidates = list(dial_infos.get(s["vanilla_dial_id"], []))
            # recruit_accept has VMAD (SetPlayerTeammate), recruit_full has no VMAD
            if s["id"] == "recruit_accept":
                candidates = [c for c in candidates if c[2]]
            elif s["id"] == "recruit_full":
                candidates = [c for c in candidates if not c[2]]
        else:
            candidates = list(subtype_infos.get(s.get("sample_subtype", ""), []))
        # Prefer recorded lines for this voice, then explicit voice condition matches
        candidates.sort(key=lambda c: (not c[0], not c[1], c[3]))
        ja, en = [], []
        for _, _, _, _, j, e in candidates:
            if j and j not in ja and len(ja) < 4:
                ja.append(j)
            if e and e not in en and len(en) < 4:
                en.append(e)
            if len(ja) >= 4 and len(en) >= 4:
                break
        if not ja:
            ja = list(s.get("default_lines_ja", []))
        result[s["id"]] = {"ja": ja, "en": en}

    _SAMPLE_CACHE[cache_key] = result
    return result


def build_ai_prompt(npc_name: str, samples: dict, lang: str = "ja", sex: str = "female",
                    style: str = "", pronouns: str = "") -> str:
    """Generate a comprehensive, ready-to-paste prompt for an AI / persona to author dialogue JSON."""
    name = (npc_name or "").strip() or ("Avatar" if lang == "en" else "キャラクター")
    style = (style or "").strip()
    pronouns = (pronouns or "").strip()
    lines = []
    if lang == "en":
        sex_label = "Female" if sex == "female" else "Male"
        lines.extend([
            f"# Task: Write Skyrim SE Custom Follower Dialogue JSON for \"{name}\"",
            "",
            "Write in-character Skyrim SE follower voice lines for the scenes listed below.",
            "If you already have an established persona or speech style, prioritize your own voice and relationship.",
            "",
            "## Character Profile",
            f"- Name: {name}",
            f"- Sex: {sex_label}",
        ])
        if style:
            lines.append(f"- Personality / Speech style: {style}")
        if pronouns:
            lines.append(f"- Self-reference / How they address the player: {pronouns}")
        lines.extend([
            "",
            "## Strict Output Rules",
            "1. Output **ONLY** a single valid JSON object (no commentary before or after).",
            "2. Use ONLY the exact scene IDs listed below as top-level keys. Do not rename, nest, or invent keys.",
            "3. Each scene maps to an array of objects: `{\"id\": \"01\", \"text\": \"...\"}`.",
            "   - `id` starts at `\"01\"`, `\"02\"`, `\"03\"` per scene (two-digit strings).",
            "   - Do NOT include an `audio` field.",
            "4. Spoken text ONLY — no stage directions, no parentheses/asterisks like `(smiles)` or `*sighs*`, no emojis, no markdown.",
            "5. Keep each line under 250 characters:",
            "   - Dialogue scenes: 1–2 natural spoken sentences.",
            "   - Combat shouts/reactions (`combat_attack`, `combat_power_attack`, `combat_bash`, `combat_hit`, `combat_block`, `combat_death`): short, punchy shouts or 1-line reactions.",
            "6. **Required** scenes must have at least 1 line (1–3 variations recommended).",
            "   **Recommended** scenes should have 1–3 variations. **Optional** scenes may be `[]` or omitted.",
            "",
            "## Output Example",
            "```json",
            "{",
            "  \"recruit_accept\": [",
            "    { \"id\": \"01\", \"text\": \"Alright, lead the way.\" }",
            "  ],",
            "  \"follower_hello\": [",
            "    { \"id\": \"01\", \"text\": \"Need something?\" },",
            "    { \"id\": \"02\", \"text\": \"Right behind you.\" }",
            "  ],",
            "  \"combat_attack\": [",
            "    { \"id\": \"01\", \"text\": \"Take this!\" },",
            "    { \"id\": \"02\", \"text\": \"You're mine!\" }",
            "  ]",
            "}",
            "```",
            "",
            "## Scene List",
        ])
        for tier_key, tier_title in (
            ("required", "Required (Core Follower Dialogue — at least 1 line each)"),
            ("recommended", "Recommended (Favor Commands & Combat — 1–3 lines each)"),
            ("optional", "Optional (Greetings / Idle / Yield — 0–3 lines each)"),
        ):
            lines.append(f"### {tier_title}")
            for s in VOICE_SCENES:
                if s["tier"] != tier_key:
                    continue
                ex = " / ".join(samples.get(s["id"], {}).get("en", [])[:3])
                guide = "short shout/reaction" if s["group"] == "combat" and s["id"] != "accept_yield" else "1–2 sentences"
                lines.append(f"- `{s['id']}` ({s['label_en']} | {guide}): {s['context_en']}" + (f" [Vanilla: {ex}]" if ex else ""))
            lines.append("")
    else:
        sex_label = "女性" if sex == "female" else "男性"
        lines.extend([
            f"# 依頼: Skyrim SE フォロワー「{name}」の専用セリフ JSON 作成",
            "",
            f"Skyrim SE のフォロワー「{name}」がゲーム内で喋る専用セリフを、キャラクターの性格・口調になりきって作成してください。",
            "※あなた自身にすでにキャラクターの人格・口調が設定されている場合は、あなた本来の口調・関係性を優先して書いてください。",
            "",
            "## キャラクター設定",
            f"- 名前: {name}",
            f"- 性別: {sex_label}",
        ])
        if style:
            lines.append(f"- 性格・口調: {style}")
        if pronouns:
            lines.append(f"- 一人称 / プレイヤーの呼び方: {pronouns}")
        lines.extend([
            "",
            "## 厳守する出力ルール",
            "1. 出力は **有効な JSON オブジェクト1つのみ** にしてください（前後の挨拶・解説・補足は不要です）。",
            "2. トップレベルのキーは下記の **指定された場面IDのみ** をそのまま使ってください（勝手にネストしたりキー名を変えないでください）。",
            "3. 各場面の値は `{\"id\": \"01\", \"text\": \"セリフ本文\"}` の配列にしてください。",
            "   - `id` は場面ごとに `\"01\"`, `\"02\"`, `\"03\"` の2桁連番を振ってください。",
            "   - `audio` フィールドは不要です（出力しないでください）。",
            "4. **声に出して読み上げるセリフ本文のみ** を書いてください。",
            "   - ト書き・動作描写（例：`（微笑む）`、`*うなずく*`）、絵文字、顔文字、Markdown装飾は禁止です。",
            "5. 長さの目安（1セリフ最大250文字まで）：",
            "   - 会話・頼み事・挨拶：自然な話し言葉で1〜2文。",
            "   - 戦闘ボイス（攻撃・強攻撃・殴る・被弾・防御・倒れる等）：戦闘中にテンポよく鳴るよう、短い掛け声〜一言フレーズ。",
            "6. 本数の目安：",
            "   - **必須**（8場面）：各場面 **最低1本**（1〜3本推奨）。",
            "   - **推奨**（18場面）：各場面 1〜3本推奨（戦闘の攻撃・被弾は2〜3本あると自然）。",
            "   - **任意**（4場面）：書けば喋ります。不要なら空配列 `[]` または省略可。",
            "",
            "## 出力フォーマット例",
            "```json",
            "{",
            "  \"recruit_accept\": [",
            "    { \"id\": \"01\", \"text\": \"いいわ、ついて行ってあげる。\" }",
            "  ],",
            "  \"follower_hello\": [",
            "    { \"id\": \"01\", \"text\": \"準備はいい？\" },",
            "    { \"id\": \"02\", \"text\": \"すぐ後ろにいるから安心して。\" }",
            "  ],",
            "  \"combat_attack\": [",
            "    { \"id\": \"01\", \"text\": \"そこっ！\" },",
            "    { \"id\": \"02\", \"text\": \"逃がさないわよ！\" }",
            "  ]",
            "}",
            "```",
            "",
            "## 場面一覧（全30場面）",
        ])
        for tier_key, tier_title in (
            ("required", "必須（フォロワー基本会話 — 各1〜3本、最低1本必須）"),
            ("recommended", "推奨（頼み事・戦闘 — 各1〜3本）"),
            ("optional", "任意（挨拶・道中など — 0〜3本、省略可）"),
        ):
            lines.append(f"### {tier_title}")
            for s in VOICE_SCENES:
                if s["tier"] != tier_key:
                    continue
                ex = " ／ ".join(samples.get(s["id"], {}).get("ja", [])[:3])
                guide = "短い掛け声・一言" if s["group"] == "combat" and s["id"] != "accept_yield" else "1〜2文"
                lines.append(f"- `{s['id']}`（{s['label_ja']}｜{guide}）: {s['context_ja']}" + (f"【公式見本: {ex}】" if ex else ""))
            lines.append("")
    return "\n".join(lines)


# --- Japanese Kana -> Romaji for FaceFXWrapper lip sync ---
_KANA_DIGRAPHS = {
    "きゃ": "kya", "きゅ": "kyu", "きょ": "kyo", "しゃ": "sha", "しゅ": "shu", "しょ": "sho",
    "ちゃ": "cha", "ちゅ": "chu", "ちょ": "cho", "にゃ": "nya", "にゅ": "nyu", "にょ": "nyo",
    "ひゃ": "hya", "ひゅ": "hyu", "ひょ": "hyo", "みゃ": "mya", "みゅ": "myu", "みょ": "myo",
    "りゃ": "rya", "りゅ": "ryu", "りょ": "ryo", "ぎゃ": "gya", "ぎゅ": "gyu", "ぎょ": "gyo",
    "じゃ": "ja", "じゅ": "ju", "じょ": "jo", "びゃ": "bya", "びゅ": "byu", "びょ": "byo",
    "ぴゃ": "pya", "ぴゅ": "pyu", "ぴょ": "pyo", "ふぁ": "fa", "ふぃ": "fi", "ふぇ": "fe",
    "ふぉ": "fo", "てぃ": "ti", "でぃ": "di", "うぃ": "wi", "うぇ": "we", "うぉ": "wo",
    "ゔぁ": "va", "ゔぃ": "vi", "ゔぇ": "ve", "ゔぉ": "vo", "ちぇ": "che", "しぇ": "she",
    "じぇ": "je",
}
_KANA_SINGLE = {
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so",
    "た": "ta", "ち": "chi", "つ": "tsu", "て": "te", "と": "to",
    "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no",
    "は": "ha", "ひ": "hi", "ふ": "fu", "へ": "he", "ほ": "ho",
    "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo",
    "や": "ya", "ゆ": "yu", "よ": "yo",
    "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro",
    "わ": "wa", "を": "o", "ん": "n",
    "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go",
    "ざ": "za", "じ": "ji", "ず": "zu", "ぜ": "ze", "ぞ": "zo",
    "だ": "da", "ぢ": "ji", "づ": "zu", "づけ": "zuke", "で": "de", "ど": "do",
    "ば": "ba", "び": "bi", "ぶ": "bu", "べ": "be", "ぼ": "bo",
    "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po",
    "ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o",
    "ゃ": "ya", "ゅ": "yu", "ょ": "yo", "ゔ": "vu",
}


def text_to_lip_phonetics(text: str) -> str:
    """Convert Japanese kana to ASCII romaji for FaceFXWrapper; fall back to vowel syllables for kanji."""
    # Convert katakana to hiragana
    chars = []
    for ch in text:
        code = ord(ch)
        if 0x30A1 <= code <= 0x30F6:
            chars.append(chr(code - 0x60))
        else:
            chars.append(ch)
    s = "".join(chars)
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "っ":
            if i + 1 < len(s):
                nxt = _KANA_DIGRAPHS.get(s[i + 1 : i + 3]) or _KANA_SINGLE.get(s[i + 1], "")
                if nxt and nxt[0].isalpha():
                    out.append(nxt[0])
            i += 1
            continue
        if ch == "ー":
            if out and out[-1] and out[-1][-1] in "aeiou":
                out.append(out[-1][-1])
            i += 1
            continue
        dig = _KANA_DIGRAPHS.get(s[i : i + 2])
        if dig:
            out.append(dig)
            i += 2
            continue
        sg = _KANA_SINGLE.get(ch)
        if sg:
            out.append(sg)
            i += 1
            continue
        if ch.isascii() and (ch.isalnum() or ch in " ,.!?'-"):
            out.append(ch)
        elif ch in "、。！？…　":
            out.append(" ")
        elif 0x4E00 <= ord(ch) <= 0x9FFF:
            # Kanji fallback: emit a neutral 2-mora open syllable so FaceFX still animates mouth timing
            out.append("ka ")
        i += 1
    cleaned = re.sub(r"\s+", " ", "".join(out)).strip()
    return cleaned or "ah"


# --- Audio & Lip Sync Tools ---
def voice_tools_status(game_dir) -> dict:
    game = Path(game_dir).resolve() if game_dir else None
    xwma = (game / "Tools/Audio/xwmaencode.exe") if game else None
    facefx = (game / "Data/Sound/Voice/Processing/FaceFXWrapper.exe") if game else None
    fonix = (game / "Data/Sound/Voice/Processing/FonixData.cdf") if game else None
    ffmpeg = shutil.which("ffmpeg")
    return {
        "ffmpeg": ffmpeg or "",
        "xwmaencode": str(xwma) if xwma and xwma.is_file() else "",
        "facefx": str(facefx) if facefx and facefx.is_file() else "",
        "fonix": str(fonix) if fonix and fonix.is_file() else "",
        "can_fuz": bool(xwma and xwma.is_file()),
        "can_lip": bool(facefx and facefx.is_file() and fonix and fonix.is_file()),
    }


def write_silence_wav(path: Path, duration_sec: float, sample_rate: int = 44100):
    n = max(1, int(sample_rate * duration_sec))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * n)


def convert_to_pcm_wav(src: Path, dst: Path, ffmpeg_path: str):
    if src.suffix.lower() == ".wav":
        try:
            with wave.open(str(src), "rb") as w:
                if w.getnchannels() == 1 and w.getsampwidth() == 2 and w.getframerate() == 44100:
                    shutil.copy2(src, dst)
                    return
        except wave.Error:
            pass
    if not ffmpeg_path:
        raise ValueError(f"ffmpeg が見つからないため音声を変換できません: {src.name}")
    r = subprocess.run(
        [ffmpeg_path, "-y", "-i", str(src), "-ac", "1", "-ar", "44100", "-sample_fmt", "s16", str(dst)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not dst.is_file():
        raise RuntimeError(f"ffmpeg failed for {src.name}: {r.stderr.strip()}")


def pack_fuz(xwm_bytes: bytes, lip_bytes: bytes = b"") -> bytes:
    """Pack XWM audio and optional LIP data into a Skyrim SE .fuz container."""
    return b"FUZE" + struct.pack("<II", 1, len(lip_bytes)) + lip_bytes + xwm_bytes


# --- ESP Record Generation (VTYP, QUST, DIAL, INFO) ---
def _quest_vmad(settings) -> bytes:
    def pstr(value: str) -> bytes:
        raw = value.encode("utf8")
        return struct.pack("<H", len(raw)) + raw

    # TES5 Quest VMAD: version=5, objectFormat=2, scriptCount=1, 3 Object properties
    name = voice_reg_script_name(settings)
    payload = struct.pack("<hhh", 5, 2, 1) + pstr(name) + struct.pack("<BH", 0, 3)
    payload += pstr("VoicesFollowerAll") + bytes((1, 1)) + struct.pack("<HhI", 0, -1, VOICES_FOLLOWER_ALL_ID)
    payload += pstr("DefaultNPCVoiceTypes") + bytes((1, 1)) + struct.pack("<HhI", 0, -1, DEFAULT_NPC_VOICE_TYPES_ID)
    payload += pstr("CustomVoice") + bytes((1, 1)) + struct.pack("<HhI", 0, -1, CUSTOM_VOICE_ID)
    return payload


def _ctda_voice_type(vtyp_id: int) -> bytes:
    # CTDA (32 bytes): op=0x00 (==), comp=1.0, fn=426 (GetIsVoiceType), p1=vtyp_id, p2=0, runOn=0 (Subject), param3=-1
    return struct.pack("<B3xfH2xIIIIi", 0, 1.0, 426, vtyp_id, 0, 0, 0, -1)


def _strip_voice_and_id_conditions(ctda_list: list[bytes]) -> list[bytes]:
    kept = []
    for blob in ctda_list:
        if len(blob) >= 12:
            fn = struct.unpack_from("<H", blob, 8)[0]
            if fn in (72, 426):  # GetIsID, GetIsVoiceType
                continue
        kept.append(blob)
    return kept


def _build_info_record(info_id: int, text: str, conditions: list[bytes], *, vmad: bytes | None = None,
                       enam_flags: int = 0, emotion: int = 0, emotion_val: int = 50,
                       pnam: int = 0) -> Record:
    fields = []
    if vmad:
        fields.append((b"VMAD", vmad))
    if enam_flags:
        fields.append((b"ENAM", struct.pack("<HH", enam_flags, 0)))
    fields.append((b"PNAM", struct.pack("<I", pnam)))
    fields.append((b"CNAM", b"\x00"))
    # TRDT (24 bytes): emotionType, emotionValue, unknown(4), responseNumber(1), pad(3), sound(4), flags(1=UseEmotionAnim), pad(3)
    fields.append((b"TRDT", struct.pack("<IIIB3xIB3x", emotion, emotion_val, 0, 1, 0, 1)))
    fields.append((b"NAM1", text.encode("utf8") + b"\0"))
    fields.append((b"NAM2", b"\0"))
    fields.append((b"NAM3", b"\0"))
    for c in conditions:
        fields.append((b"CTDA", c))
    return Record(b"INFO", info_id, 0, fields)


_FALLBACK_SCENE_SOURCES = {"hello": "follower_hello", "goodbye": "follower_goodbye"}


def resolved_voice_lines(raw) -> dict[str, tuple[str, list[dict]]]:
    """Return {scene_id: (audio_source_scene_id, entries)} with hello/goodbye fallback applied."""
    lines_map = normalize_voice_lines(raw)
    out = {}
    for scene in VOICE_SCENES:
        sid = scene["id"]
        entries = lines_map.get(sid)
        src_sid = sid
        if not entries and sid in _FALLBACK_SCENE_SOURCES:
            fb_id = _FALLBACK_SCENE_SOURCES[sid]
            entries = lines_map.get(fb_id)
            src_sid = fb_id
        if entries:
            out[sid] = (src_sid, entries)
    return out


def voice_records(game_data: Path, settings):
    """Build VTYP, QUST, DIAL/INFO topics, and an audio manifest list for custom voice mode.

    Returns: (flat_records, dialogue_topics, audio_manifest)
    """
    if settings.voice_mode != "custom":
        return [], [], []

    lines_map = normalize_voice_lines(settings.custom_voice_lines)
    # Keep Allow Default Dialog (0x01) OFF so vanilla DialogueGeneric unvoiced fallback lines ("何だ？", "また今度", etc.) do not leak in
    vtyp_flag = 0x02 if settings.sex == "female" else 0x00
    vtyp = Record(b"VTYP", CUSTOM_VOICE_ID, 0, [
        (b"EDID", (voice_edid(settings) + "\0").encode("utf8")),
        (b"DNAM", bytes((vtyp_flag,))),
    ])

    q_edid = voice_quest_edid(settings)
    # QUST DNAM (12 bytes): flags=0x0011 (Start Game Enabled | Allow Repeated), priority=45
    # (below DialogueFollower=50 so follower lines win while following, above DialogueGeneric=0 so custom hello/goodbye/combat always win)
    qust = Record(b"QUST", VOICE_QUEST_ID, 0, [
        (b"EDID", (q_edid + "\0").encode("utf8")),
        (b"VMAD", _quest_vmad(settings)),
        (b"FULL", (settings.npc_name + " Voice\0").encode("utf8")),
        (b"DNAM", struct.pack("<HBBII", 0x0011, 45, 0, 0, 0)),
        (b"CTDA", _ctda_voice_type(CUSTOM_VOICE_ID)),
        (b"ANAM", struct.pack("<I", 0)),
    ])

    # Load vanilla template DIALs & INFOs from Skyrim.esm for follower/favor scenes
    esm = Path(game_data) / "Skyrim.esm"
    needed_dials = {s["vanilla_dial_id"] for s in VOICE_SCENES if s["mode"] == "vanilla_dial"}
    needed_infos = {s["template_info_id"] for s in VOICE_SCENES if s["mode"] == "vanilla_dial"}
    vanilla_dials = {}
    vanilla_infos = {}
    if esm.is_file():
        from probe_follower_data import contextual_records
        for rec, _ in contextual_records(esm, {b"DIAL", b"INFO"}):
            if rec.kind == b"DIAL" and rec.form_id in needed_dials:
                vanilla_dials[rec.form_id] = rec
            elif rec.kind == b"INFO" and rec.form_id in needed_infos:
                vanilla_infos[rec.form_id] = rec

    next_dial_id = VOICE_DIAL_BASE_ID
    next_info_id = VOICE_INFO_BASE_ID
    vanilla_topic_infos = {}  # vanilla_dial_id -> list[Record]
    vanilla_last_info = {}    # vanilla_dial_id -> last info_id for contiguous PNAM chain
    recruit_infos = []        # private top-level recruit DIAL INFOs (avoids DefaultNPCVoiceTypes / DialogueGeneric)
    recruit_last_info = 0
    recruit_topic_edid = f"{settings.prefix}RecruitTopic"
    recruit_branch_edid = f"{settings.prefix}RecruitBranch"
    private_topics = []
    audio_manifest = []

    resolved = resolved_voice_lines(settings.custom_voice_lines)

    for scene in VOICE_SCENES:
        if scene["id"] not in resolved:
            continue
        audio_scene_id, entries = resolved[scene["id"]]
        is_multi = len(entries) > 1
        if scene["mode"] == "vanilla_dial":
            vdial_id = scene["vanilla_dial_id"]
            is_recruit = vdial_id == RECRUIT_VANILLA_DIAL_ID
            tmpl = vanilla_infos.get(scene["template_info_id"])
            vmad = tmpl.values(b"VMAD")[0] if tmpl and tmpl.values(b"VMAD") else None
            base_enam = struct.unpack_from("<H", tmpl.values(b"ENAM")[0], 0)[0] if tmpl and tmpl.values(b"ENAM") else 0
            base_conds = _strip_voice_and_id_conditions(tmpl.values(b"CTDA")) if tmpl else []
            conds = [_ctda_voice_type(CUSTOM_VOICE_ID), *base_conds]
            built = []
            prev_id = recruit_last_info if is_recruit else vanilla_last_info.get(vdial_id, 0)
            for idx, entry in enumerate(entries):
                info_id = next_info_id
                next_info_id += 1
                flags = base_enam
                if is_multi:
                    flags |= 0x0002  # Random
                    if idx == len(entries) - 1:
                        flags |= 0x0080  # Random End
                built.append(_build_info_record(info_id, entry["text"], conds, vmad=vmad, enam_flags=flags, pnam=prev_id))
                prev_id = info_id
                if is_recruit:
                    stem = fuz_stem(q_edid, recruit_topic_edid, info_id)
                else:
                    stem = fuz_stem(scene["vanilla_quest"], scene["vanilla_topic_edid"], info_id)
                audio_manifest.append({
                    "scene_id": audio_scene_id,
                    "line_id": entry["id"],
                    "text": entry["text"],
                    "audio": entry.get("audio", ""),
                    "info_form_id": info_id,
                    "stem": stem,
                })
            if is_recruit:
                recruit_last_info = prev_id
                recruit_infos.extend(built)
            else:
                vanilla_last_info[vdial_id] = prev_id
                vanilla_topic_infos.setdefault(vdial_id, []).extend(built)
        else:
            dial_id = next_dial_id
            next_dial_id += 1
            conds = [_ctda_voice_type(CUSTOM_VOICE_ID)]
            built = []
            prev_id = 0
            for idx, entry in enumerate(entries):
                info_id = next_info_id
                next_info_id += 1
                flags = 0
                if is_multi:
                    flags |= 0x0002
                    if idx == len(entries) - 1:
                        flags |= 0x0080
                built.append(_build_info_record(info_id, entry["text"], conds, enam_flags=flags, pnam=prev_id))
                prev_id = info_id
                stem = fuz_stem(q_edid, "", info_id)
                audio_manifest.append({
                    "scene_id": audio_scene_id,
                    "line_id": entry["id"],
                    "text": entry["text"],
                    "audio": entry.get("audio", ""),
                    "info_form_id": info_id,
                    "stem": stem,
                })
            dial = Record(b"DIAL", dial_id, 0, [
                (b"PNAM", struct.pack("<f", 60.0)),
                (b"QNAM", struct.pack("<I", VOICE_QUEST_ID)),
                (b"DATA", scene["dial_data"]),
                (b"SNAM", scene["subtype"].encode("ascii")),
                (b"TIFC", struct.pack("<I", len(built))),
            ])
            private_topics.append((dial, built))

    # Resolve localized Skyrim.esm DIAL FULL (4-byte LSTRING ID) to plain UTF-8 strings for our non-localized ESP
    strings_table = _load_strings(game_data, "japanese") or _load_strings(game_data, "english")
    flat_records = [vtyp, qust]
    dialogue_topics = []
    if recruit_infos:
        recruit_prompt = "ついて来てくれ。手を貸してほしい"
        if RECRUIT_VANILLA_DIAL_ID in vanilla_dials:
            fvals = vanilla_dials[RECRUIT_VANILLA_DIAL_ID].values(b"FULL")
            if fvals and len(fvals[0]) == 4:
                sid = struct.unpack("<I", fvals[0])[0]
                if sid in strings_table:
                    recruit_prompt = strings_table[sid]
        dlbr = Record(b"DLBR", VOICE_RECRUIT_DLBR_ID, 0, [
            (b"EDID", (recruit_branch_edid + "\0").encode("utf8")),
            (b"QNAM", struct.pack("<I", VOICE_QUEST_ID)),
            (b"TNAM", struct.pack("<I", 0)),
            (b"DNAM", struct.pack("<I", 1)),  # Top-Level branch
            (b"SNAM", struct.pack("<I", VOICE_RECRUIT_DIAL_ID)),
        ])
        recruit_dial = Record(b"DIAL", VOICE_RECRUIT_DIAL_ID, 0, [
            (b"EDID", (recruit_topic_edid + "\0").encode("utf8")),
            (b"FULL", recruit_prompt.encode("utf8") + b"\0"),
            (b"PNAM", struct.pack("<f", 50.0)),
            (b"BNAM", struct.pack("<I", VOICE_RECRUIT_DLBR_ID)),
            (b"QNAM", struct.pack("<I", VOICE_QUEST_ID)),
            (b"DATA", b"\x00\x00\x00\x00"),
            (b"SNAM", b"CUST"),
            (b"TIFC", struct.pack("<I", len(recruit_infos))),
        ])
        flat_records.append(dlbr)
        dialogue_topics.append((recruit_dial, recruit_infos))

    for vdial_id, infos in vanilla_topic_infos.items():
        vdial = copy.deepcopy(vanilla_dials[vdial_id]) if vdial_id in vanilla_dials else Record(b"DIAL", vdial_id, 0, [])
        full_vals = vdial.values(b"FULL")
        if full_vals and len(full_vals[0]) == 4:
            sid = struct.unpack("<I", full_vals[0])[0]
            if sid in strings_table:
                vdial.replace(b"FULL", strings_table[sid].encode("utf8") + b"\0")
        # Keep vanilla DIAL header fields, updating TIFC to our added INFO count
        vdial.replace(b"TIFC", struct.pack("<I", len(infos)))
        dialogue_topics.append((vdial, infos))
    dialogue_topics.extend(private_topics)

    return flat_records, dialogue_topics, audio_manifest


def write_voice_seq(output: Path, settings, master_count: int):
    """Write Data/SEQ/<PluginStem>.seq for Start-Game-Enabled VOICE_QUEST_ID.

    Without a .seq file, Skyrim SE skips initializing dialogue topics on newly
    added Start-Game-Enabled quests until a save/reload cycle (the Skyrim Dialogue Bug).
    Verified against Skyrim - Misc.bsa and loose SE .seq files: raw array of 4-byte
    little-endian file-local quest FormIDs with no count header.
    """
    if settings.voice_mode != "custom":
        return None
    seq_dir = Path(output) / "mod/seq"
    seq_dir.mkdir(parents=True, exist_ok=True)
    seq_path = seq_dir / (Path(settings.plugin_name).stem + ".seq")
    file_quest_id = (master_count << 24) | (VOICE_QUEST_ID & 0xFFFFFF)
    seq_path.write_bytes(struct.pack("<I", file_quest_id))
    LOG.info("Wrote custom voice SEQ: %s (0x%08X)", seq_path.name, file_quest_id)
    return seq_path


def write_voice_runtime(output: Path, settings):
    if settings.voice_mode != "custom":
        return
    from equipment_runtime import rename_pex
    name = voice_reg_script_name(settings)
    data = (ROOT / "runtime" / (VOICE_REG_TEMPLATE + ".pex")).read_bytes()
    data = rename_pex(data, name, template_name=VOICE_REG_TEMPLATE)
    scripts_dir = Path(output) / "mod/scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / (name + ".pex")).write_bytes(data)
    src_dir = Path(output) / "mod/source/scripts"
    src_dir.mkdir(parents=True, exist_ok=True)
    src = (ROOT / "runtime" / (VOICE_REG_TEMPLATE + ".psc")).read_text(encoding="utf8").replace(VOICE_REG_TEMPLATE, name)
    (src_dir / (name + ".psc")).write_text(src, encoding="utf8")
    LOG.info("Private custom voice registration runtime: %s", name)


def build_voice_assets(output: Path, game_dir, settings, audio_manifest: list[dict], audio_files: dict[str, Path] | None = None):
    """Generate .fuz (or .wav fallback) voice assets in mod/sound/voice/<plugin>/<VTYP>/."""
    if settings.voice_mode != "custom" or not audio_manifest:
        return None
    output = Path(output)
    audio_files = {k.lower(): Path(v) for k, v in (audio_files or {}).items()}
    tools = voice_tools_status(game_dir)
    voice_dir = output / "mod/sound/voice" / settings.plugin_name / voice_edid(settings)
    voice_dir.mkdir(parents=True, exist_ok=True)

    stats = {"total": len(audio_manifest), "matched_audio": 0, "silence_generated": 0, "fuz": 0, "wav": 0, "lip": 0}
    with tempfile.TemporaryDirectory(prefix="v2s-voice-") as tmp_str:
        tmp = Path(tmp_str)
        for item in audio_manifest:
            # Resolve matching uploaded audio file
            candidates = []
            if item.get("audio"):
                candidates.append(item["audio"].lower())
            base = f"{item['scene_id']}_{item['line_id']}".lower()
            for ext in (".wav", ".ogg", ".mp3", ".flac", ".m4a"):
                candidates.append(base + ext)
            src_audio = next((audio_files[c] for c in candidates if c in audio_files and audio_files[c].is_file()), None)

            pcm_wav = tmp / f"{item['stem']}.wav"
            if src_audio is not None:
                convert_to_pcm_wav(src_audio, pcm_wav, tools["ffmpeg"])
                stats["matched_audio"] += 1
            else:
                dur = max(1.8, min(6.0, len(item["text"]) * 0.18))
                write_silence_wav(pcm_wav, dur)
                stats["silence_generated"] += 1

            lip_bytes = b""
            if tools["can_lip"] and src_audio is not None:
                resamp = tmp / f"{item['stem']}_resamp.wav"
                lip_path = tmp / f"{item['stem']}.lip"
                phonetics = text_to_lip_phonetics(item["text"])
                r = subprocess.run(
                    [tools["facefx"], "Skyrim", "USEnglish", tools["fonix"], str(pcm_wav), str(resamp), str(lip_path), phonetics],
                    capture_output=True,
                    text=True,
                )
                if r.returncode == 0 and lip_path.is_file() and lip_path.stat().st_size > 0:
                    lip_bytes = lip_path.read_bytes()
                    stats["lip"] += 1

            if tools["can_fuz"]:
                xwm_path = tmp / f"{item['stem']}.xwm"
                r = subprocess.run([tools["xwmaencode"], str(pcm_wav), str(xwm_path)], capture_output=True, text=True)
                if r.returncode != 0 or not xwm_path.is_file():
                    raise RuntimeError(f"xwmaencode failed for {item['stem']}: {r.stderr.strip()}")
                fuz_path = voice_dir / f"{item['stem']}.fuz"
                fuz_path.write_bytes(pack_fuz(xwm_path.read_bytes(), lip_bytes))
                item["output"] = fuz_path.relative_to(output / "mod").as_posix()
                stats["fuz"] += 1
            else:
                wav_out = voice_dir / f"{item['stem']}.wav"
                shutil.copy2(pcm_wav, wav_out)
                item["output"] = wav_out.relative_to(output / "mod").as_posix()
                if lip_bytes:
                    (voice_dir / f"{item['stem']}.lip").write_bytes(lip_bytes)
                stats["wav"] += 1

    report = {"voice_edid": voice_edid(settings), "tools": tools, "stats": stats, "lines": audio_manifest}
    (output / "custom-voice.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    LOG.info("Custom voice assets ready: %d lines (%d audio, %d silence, %d .fuz, %d .lip)",
             stats["total"], stats["matched_audio"], stats["silence_generated"], stats["fuz"], stats["lip"])
    return report


def validate_voice_assets(output: Path, settings):
    if settings.voice_mode != "custom":
        return None
    output = Path(output)
    mod = output / "mod"
    report_path = output / "custom-voice.json"
    if not report_path.is_file():
        raise ValueError("Custom voice manifest missing: custom-voice.json")
    report = json.loads(report_path.read_text(encoding="utf8"))
    pex_path = mod / "scripts" / (voice_reg_script_name(settings) + ".pex")
    if not pex_path.is_file():
        raise ValueError(f"Missing custom voice registration PEX: {pex_path.name}")
    seq_path = mod / "seq" / (Path(settings.plugin_name).stem + ".seq")
    if not seq_path.is_file() or seq_path.stat().st_size != 4:
        raise ValueError(f"Missing or invalid custom voice SEQ file: {seq_path.name}")
    for entry in report.get("lines", []):
        out_path = mod / entry["output"]
        if not out_path.is_file() or out_path.stat().st_size == 0:
            raise ValueError(f"Missing custom voice file: {entry['output']}")
        if out_path.suffix.lower() == ".fuz":
            header = out_path.read_bytes()[:4]
            if header != b"FUZE":
                raise ValueError(f"Invalid FUZ header in {out_path.name}")
    LOG.info("Validated custom voice: %d lines, registration PEX %s", len(report.get("lines", [])), pex_path.name)
    return report
