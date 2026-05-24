import tempfile
import unittest
from pathlib import Path

from toc.semantic_pack_narration import collect_entries


class TestSemanticPackNarration(unittest.TestCase):
    def test_collects_cut_narration_contract_review_and_audio_refs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_narration_") as td:
            run_dir = Path(td)
            (run_dir / "assets/audio").mkdir(parents=True)
            (run_dir / "assets/audio/scene01_cut01_narration.mp3").write_bytes(b"fake")
            (run_dir / "video_manifest.md").write_text(
                """# Manifest

```yaml
scenes:
  - scene_id: 1
    title: "浜辺"
    story_role: "opening"
    cuts:
      - cut_id: 1
        cut_role: "causal beat"
        visual_beat: "太郎が亀を助け、亀が海へ向く。"
        duration_seconds: 6
        audio:
          narration:
            tool: "elevenlabs"
            text: "亀を助けた太郎は、海へ導かれます。"
            tts_text: "亀を助けた太郎は、海へ導かれます。"
            output: "assets/audio/scene01_cut01_narration.mp3"
            contract:
              target_function: "causality"
              must_cover:
                - "助けた行為が次の誘いにつながる"
              must_avoid:
                - "映像指示を読まない"
              done_when:
                - "助けた結果として海へ導かれる因果が伝わる"
      - cut_id: 2
        cut_role: "reaction"
        visual_beat: "太郎が海を見つめる。"
        audio:
          narration:
            tool: "silent"
            text: ""
            silence_contract:
              intentional: true
              confirmed_by_human: true
              kind: "visual_value_hold"
              reason: "視線だけで余韻を作る"
            contract:
              target_function: "silence"
              must_cover: ["余韻"]
              must_avoid: ["説明過多"]
              done_when: ["映像のみで間が成立する"]
```
""",
                encoding="utf-8",
            )
            (run_dir / "narration_text_review.md").write_text(
                """# Narration Text Review

## scene01_cut01

- tool: `elevenlabs`
- output: `assets/audio/scene01_cut01_narration.mp3`
- review: `PASS`
- agent_review_ok: `true`
- human_review_ok: `false`
- agent_review_reason_keys: ``
""",
                encoding="utf-8",
            )

            entries = collect_entries("narration", run_dir)

            self.assertEqual(len(entries), 2)
            entry = entries[0]
            self.assertEqual(entry["selector"], "scene01_cut01")
            self.assertEqual(entry["semantic_contract"]["target_function"], "causality")
            self.assertFalse(entry["semantic_contract_missing"])
            self.assertEqual(entry["contract_required_fields_missing"], [])
            self.assertEqual(entry["cut_role"], "causal beat")
            self.assertEqual(entry["visual_beat"], "太郎が亀を助け、亀が海へ向く。")
            self.assertEqual(entry["next_cut_summary"], "太郎が海を見つめる。")
            self.assertEqual(entry["narration"]["text"], "亀を助けた太郎は、海へ導かれます。")
            self.assertTrue(entry["narration"]["output_exists"])
            self.assertEqual(entry["audio_output_refs"], ["assets/audio/scene01_cut01_narration.mp3"])
            self.assertEqual(entry["text_quality_review"]["status"], "pass")
            self.assertTrue(entry["text_quality_review"]["agent_review_ok"])
            self.assertEqual(entry["quality_review"], entry["text_quality_review"])
            self.assertIn("review_question", entry["too_visual_redundant_check"])
            self.assertEqual(entry["audio_output_check"]["path"], "assets/audio/scene01_cut01_narration.mp3")
            self.assertTrue(entry["audio_output_check"]["exists"])
            self.assertEqual(entry["audio_output_check"]["expected_duration_seconds"], 6)
            self.assertEqual(entry["audio_output_check"]["duration_source"], "not_measured")

            silent_entry = entries[1]
            self.assertFalse(silent_entry["silence_contract_missing"])
            self.assertEqual(silent_entry["silence_contract_reason"], "visual_value_hold: 視線だけで余韻を作る")
            self.assertTrue(silent_entry["semantic_review_inputs"]["silent_narration"])

    def test_collects_legacy_direct_narration_and_scene_level_narration(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_narration_") as td:
            run_dir = Path(td)
            manifest = {
                "scenes": [
                    {
                        "scene_id": "2",
                        "cuts": [
                            {
                                "selector": "scene02_cut_custom",
                                "cut_id": "2-a",
                                "narration": {
                                    "tool": "silent",
                                    "text": "",
                                    "silence_contract": {
                                        "intentional": True,
                                        "confirmed_by_human": True,
                                        "kind": "visual_value_hold",
                                    },
                                },
                                "narration_contract": {"target_function": "silence"},
                            }
                        ],
                    },
                    {
                        "scene_id": 3,
                        "audio": {
                            "narration": {
                                "tool": "macos_say",
                                "text": "場面全体を語ります。",
                                "output": "assets/audio/scene03.mp3",
                            }
                        },
                    },
                ]
            }

            entries = collect_entries("narration", run_dir, manifest)

            self.assertEqual([entry["selector"] for entry in entries], ["scene02_cut_custom", "scene03"])
            self.assertEqual(entries[0]["semantic_contract"]["target_function"], "silence")
            self.assertEqual(entries[0]["narration"]["silence_contract"]["kind"], "visual_value_hold")
            self.assertTrue(entries[0]["silence_contract_missing"])
            self.assertEqual(entries[0]["silence_contract_reason"], "visual_value_hold")
            self.assertEqual(entries[1]["source"], "video_manifest.md:scenes[].audio.narration")
            self.assertTrue(entries[1]["semantic_contract_missing"])
            self.assertEqual(
                entries[1]["contract_required_fields_missing"],
                ["target_function", "must_cover", "must_avoid", "done_when"],
            )

    def test_rejects_non_narration_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_narration_") as td:
            with self.assertRaises(ValueError):
                collect_entries("asset_plan", Path(td), {"scenes": []})


if __name__ == "__main__":
    unittest.main()
