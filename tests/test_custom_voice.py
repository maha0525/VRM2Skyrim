"""Tests for custom VoiceType (VTYP), dialogue topics (QUST/DIAL/INFO), and .fuz/.lip audio pipeline."""
import struct
import tempfile
import unittest
from pathlib import Path

from build_npc import NPC_ID, build_npc
from custom_voice import (
    CUSTOM_VOICE_ID,
    VOICE_QUEST_ID,
    VOICE_SCENES,
    build_ai_prompt,
    default_voice_lines,
    fuz_stem,
    normalize_voice_lines,
    pack_fuz,
    text_to_lip_phonetics,
    validate_voice_assets,
    voice_tools_status,
    write_silence_wav,
)
from follower_plugin import follower_records
from game_catalog import GameCatalog
from plugin_validation import validate_private_records
from settings import FollowerSettings
from converter import find_game


class CustomVoiceUnitTests(unittest.TestCase):
    def test_fuz_stem_matches_skyrim_truncation_rules(self):
        # Verified against Skyrim - Voices_ja0.bsa
        self.assertEqual(
            fuz_stem("DialogueFollower", "DialogueFollowerFollowTopic", 0x0107A1EB),
            "DialogueFo_DialogueFollowe_0007a1eb_1",
        )
        self.assertEqual(
            fuz_stem("DialogueFavorGeneric", "DialogueFavorGenericFollowBranchTopic", 0x010B0EE9),
            "DialogueFa_DialogueFavorGe_000b0ee9_1",
        )
        self.assertEqual(
            fuz_stem("DialogueFollower", "", 0x01026F4F),
            "DialogueFollower__00026f4f_1",
        )
        # Empty topic with quest <= 25 chars keeps full quest; > 25 chars truncates quest to 10 chars
        self.assertEqual(
            fuz_stem("RoriksteadSceneRorikErik1", "", 0x000A31D6),
            "RoriksteadSceneRorikErik1__000a31d6_1",
        )
        self.assertEqual(
            fuz_stem("DialogueGenericSceneSpecial01", "", 0x00016F98),
            "DialogueGe__00016f98_1",
        )
        self.assertEqual(
            fuz_stem("V2S_Air_SAIVerse_FollowerVoiceQuest", "", 0x01000941),
            "V2S_Air_SA__00000941_1",
        )

    def test_normalize_voice_lines_preserves_stable_ids_and_accepts_string_shorthand(self):
        raw = {
            "follow": [
                {"id": "01", "text": "いいわ、行くよ。", "audio": "dir/custom_follow.wav"},
                {"id": "03", "text": "さっさと行くわよ。"},  # gap preserved!
            ],
            "wait": ["ここで待ってる。", "遅れないでね。"],
            "unknown_scene": [{"id": "01", "text": "ignored"}],
        }
        norm = normalize_voice_lines(raw)
        self.assertNotIn("unknown_scene", norm)
        self.assertEqual([e["id"] for e in norm["follow"]], ["01", "03"])
        self.assertEqual(norm["follow"][0]["audio"], "custom_follow.wav")
        self.assertEqual([e["id"] for e in norm["wait"]], ["01", "02"])

    def test_kana_romaji_and_fuz_pack(self):
        romaji = text_to_lip_phonetics("いいわ、ついて行ってあげる。")
        self.assertIn("iiwa", romaji)
        self.assertIn("tsuite", romaji)
        fuz = pack_fuz(b"XWM_DATA", b"LIP_DATA")
        self.assertEqual(fuz[:4], b"FUZE")
        ver, lip_len = struct.unpack_from("<II", fuz, 4)
        self.assertEqual((ver, lip_len), (1, 8))
        self.assertEqual(fuz[12:20], b"LIP_DATA")
        self.assertEqual(fuz[20:], b"XWM_DATA")

    def test_ai_prompt_contains_all_required_scenes(self):
        prompt = build_ai_prompt("ルシア", {}, lang="ja")
        for s in VOICE_SCENES:
            self.assertIn(s["id"], prompt)


class CustomVoiceIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(find_game(), "Local Skyrim.esm required")
    def test_build_npc_generates_custom_voice_esp_and_fuz_assets(self):
        game = find_game()
        catalog = GameCatalog(game / "Data")
        lines = default_voice_lines()
        lines["hello"] = [{"id": "01", "text": "こんにちは、何か用？", "audio": "hello_custom.wav"}]
        settings = FollowerSettings(
            npc_name="ルシア",
            mod_name="LuciaVoiceTest",
            mod_id="LuciaVoiceTest",
            sex="female",
            voice_mode="custom",
            custom_voice_lines=lines,
            sitting_enabled=False,
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            sample_wav = tmp_path / "hello_custom.wav"
            write_silence_wav(sample_wav, 0.8)
            out = tmp_path / "build"
            out.mkdir()
            plugin = build_npc(game / "Data", out, settings, catalog, voice_audio={"hello_custom.wav": sample_wav})
            generated = follower_records(plugin)
            by_id = {r.form_id: r for r in generated}
            self.assertIn(CUSTOM_VOICE_ID, by_id)
            self.assertEqual(by_id[CUSTOM_VOICE_ID].kind, b"VTYP")
            # Allow Default Dialog (0x01) must be OFF for custom voice (female=0x02)
            self.assertEqual(by_id[CUSTOM_VOICE_ID].values(b"DNAM"), [b"\x02"])
            self.assertIn(VOICE_QUEST_ID, by_id)
            self.assertEqual(by_id[VOICE_QUEST_ID].kind, b"QUST")
            # Voice quest priority=45 (below DialogueFollower=50, above DialogueGeneric=0)
            q_flags, q_prio = struct.unpack_from("<HB", by_id[VOICE_QUEST_ID].values(b"DNAM")[0], 0)
            self.assertEqual(q_flags, 0x0011)
            self.assertEqual(q_prio, 45)
            # NPC VTCK points to custom voice
            self.assertEqual(by_id[NPC_ID].values(b"VTCK"), [struct.pack("<I", CUSTOM_VOICE_ID)])
            # QUST VMAD registers both VoicesFollowerAll and DefaultNPCVoiceTypes
            q_vmad = by_id[VOICE_QUEST_ID].values(b"VMAD")[0]
            self.assertIn(b"VoicesFollowerAll", q_vmad)
            self.assertIn(b"DefaultNPCVoiceTypes", q_vmad)
            # Recruit topic lives in private DLBR/DIAL (so custom voice never needs DefaultNPCVoiceTypes / DialogueGeneric)
            from custom_voice import VOICE_RECRUIT_DIAL_ID, VOICE_RECRUIT_DLBR_ID
            self.assertIn(VOICE_RECRUIT_DLBR_ID, by_id)
            self.assertEqual(by_id[VOICE_RECRUIT_DLBR_ID].kind, b"DLBR")
            dials_by_id = {r.form_id: r for r in generated if r.kind == b"DIAL"}
            recruit_dial = dials_by_id[VOICE_RECRUIT_DIAL_ID]
            recruit_full = recruit_dial.values(b"FULL")[0]
            self.assertGreater(len(recruit_full), 4)
            self.assertTrue(recruit_full.endswith(b"\0"))
            self.assertTrue(recruit_full[:-1].decode("utf8").strip())
            # Vanilla DIAL overrides (e.g. DialogueFollowerFollowTopic) must also have resolved UTF-8 FULL strings
            follow_full = dials_by_id[0x00075083].values(b"FULL")[0]
            self.assertGreater(len(follow_full), 4)
            self.assertTrue(follow_full.endswith(b"\0"))
            # All CTDA conditions must end with int32 -1 (0xFFFFFFFF), and PNAMs in same DIAL must not collide at 0
            for r in generated:
                if r.kind in (b"QUST", b"INFO"):
                    for ctda in r.values(b"CTDA"):
                        self.assertEqual(struct.unpack_from("<i", ctda, 28)[0], -1)
            # Validate plugin record counts and references
            validate_private_records(generated, settings, out, game / "Data")
            # Validate generated .fuz / .wav files, registration PEX, and .seq file
            report = validate_voice_assets(out, settings)
            seq_path = out / "mod/seq" / (Path(settings.plugin_name).stem + ".seq")
            self.assertEqual(seq_path.read_bytes(), struct.pack("<I", 0x010008E1))
            self.assertEqual(report["stats"]["matched_audio"], 1)
            self.assertGreater(report["stats"]["total"], 20)
            tools = voice_tools_status(game)
            if tools["can_fuz"]:
                self.assertEqual(report["stats"]["fuz"], report["stats"]["total"])

    def test_wizard_voice_upload_audio_and_zip(self):
        import io, json, zipfile
        from wizard import WizardApplication

        with tempfile.TemporaryDirectory() as tmp:
            app = WizardApplication(workspace=tmp)
            try:
                wav_path = Path(tmp) / "one.wav"
                write_silence_wav(wav_path, 0.3)
                wav_bytes = wav_path.read_bytes()
                res1 = app.upload_voice_audio("follow_01.wav", wav_bytes)
                self.assertEqual(res1["filename"], "follow_01.wav")
                self.assertIn("follow_01.wav", res1["files"])

                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as zf:
                    zf.writestr("sub/wait_01.wav", wav_bytes)
                    zf.writestr("sub/dismiss_01.wav", wav_bytes)
                    zf.writestr("readme.txt", b"ignored")
                res2 = app.upload_voice_zip(buf.getvalue())
                self.assertEqual(res2["count"], 2)
                self.assertIn("wait_01.wav", res2["files"])
                self.assertIn("dismiss_01.wav", res2["files"])

                scenes = app.voice_scenes("", "FemaleEvenToned")
                self.assertEqual(len(scenes["scenes"]), len(VOICE_SCENES))
                self.assertIn("wait_01.wav", scenes["uploaded_files"])
            finally:
                app.close()

            # Restarting the wizard against the same workspace must restore uploaded voice files
            app2 = WizardApplication(workspace=tmp)
            try:
                scenes2 = app2.voice_scenes("", "FemaleEvenToned")
                self.assertIn("wait_01.wav", scenes2["uploaded_files"])
                self.assertIn("dismiss_01.wav", scenes2["uploaded_files"])
                self.assertIn("follow_01.wav", scenes2["uploaded_files"])
            finally:
                app2.close()

    @unittest.skipUnless(find_game(), "Local Skyrim.esm required")
    def test_extract_sample_lines_varies_by_base_voice(self):
        from custom_voice import extract_sample_lines
        data = find_game() / "Data"
        even = extract_sample_lines(data, "FemaleEvenToned")
        cmd = extract_sample_lines(data, "FemaleCommander")
        khajiit = extract_sample_lines(data, "MaleKhajiit")
        self.assertNotEqual(even["recruit_accept"]["ja"], cmd["recruit_accept"]["ja"])
        self.assertNotEqual(even["follower_hello"]["ja"], khajiit["follower_hello"]["ja"])

    def test_tts_batch_items_and_zip_roundtrip(self):
        import io, json, zipfile
        from custom_voice import build_tts_batch_items
        from wizard import WizardApplication

        lines = {
            "recruit_accept": [
                {"id": "01", "text": "いいわ、ついて行ってあげる。"},
                {"id": "03", "text": "さっさと行くわよ。", "audio": "custom_accept.wav"},
            ],
            "wait": [
                {"id": "01", "text": "ここで待ってるね。"},
            ],
        }
        batch = build_tts_batch_items(lines)
        self.assertEqual(batch, [
            {"filename": "recruit_accept_01", "text": "いいわ、ついて行ってあげる。"},
            {"filename": "custom_accept", "text": "さっさと行くわよ。"},
            {"filename": "wait_01", "text": "ここで待ってるね。"},
        ])

        # Simulate saiverse-voice-tts batch ZIP output (WAVs + manifest.json)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for item in batch:
                zf.writestr(f"{item['filename']}.wav", b"RIFF\x24\x00\x00\x00WAVEfmt ")
            zf.writestr("manifest.json", json.dumps({"total": len(batch), "succeeded": len(batch)}))

        with tempfile.TemporaryDirectory() as tmp:
            app = WizardApplication(Path(tmp))
            try:
                res = app.upload_voice_zip(buf.getvalue())
            finally:
                app.executor.shutdown(wait=False)
            self.assertEqual(res["count"], 3)
            self.assertEqual(set(res["files"]), {
                "recruit_accept_01.wav",
                "custom_accept.wav",
                "wait_01.wav",
            })


if __name__ == "__main__":
    unittest.main()
