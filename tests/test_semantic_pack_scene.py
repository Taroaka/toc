from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from toc.semantic_pack_scene import collect_entries


SCRIPT_FIXTURE = """# Script

```yaml
script_metadata:
  topic: "シンデレラ"
scenes:
  - scene_id: 10
    phase: opening
    importance: high
    handoff_to_next_scene: "灰の台所から舞踏会の予感へつなぐ"
    scene_intent:
      dramatic_question: "シンデレラは灰の中で希望を保てるか"
      value_shift: "抑圧から希望へ"
      causal_turn: "小さな光が次の行動を促す"
    done_when: ["次の行動の理由が見える"]
    coverage_review:
      audience_information_covered: true
      visualizable_action_covered: true
    cuts:
      - cut_id: "01"
        selector: scene10_cut01
        cut_blueprint:
          cut_role: "opening image"
          target_beat: "灰の台所でシンデレラが立ち上がる"
          must_show: ["シンデレラ", "灰の台所"]
          must_avoid: ["画面内テキスト"]
          done_when: ["人物と場所が一枚で読める"]
          visual_beat: "灰と月光の中の横顔"
          narration_role: "内面だけを示す"
      - cut_id: "2"
        cut_blueprint:
          target_beat: "扉の向こうに次の場所を感じる"
          must_show: ["扉", "光"]
  - scene_id: 20
    phase: development
    semantic_contract:
      dramatic_question: "魔法は時間制限に勝てるか"
      value_shift: "停滞から変身へ"
      causal_turn: "魔法が期限付きの機会を作る"
      done_when: ["時間制限と証拠が物語上読める"]
      must_preserve: ["時間制限", "ガラスの靴の意味"]
    cuts:
      - cut_id: "01"
        selector: scene20_cut01
        semantic_contract:
          target_beat: "ガラスの靴が証拠になる"
          must_show: ["ガラスの靴"]
          must_avoid: ["画面内テキスト"]
          done_when: ["靴が証拠として読める"]
        cut_blueprint:
          target_beat: "ガラスの靴を見せる"
          must_show: ["ガラスの靴"]
```
"""


MANIFEST_FIXTURE = """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 3.7
    cuts:
      - cut_id: "1"
        scene_contract:
          target_beat: "海底神殿の奥に砂時計がある"
          must_show: ["海底神殿", "巨大な砂時計"]
          done_when: ["神殿と砂時計が読める"]
```
"""


class TestSemanticPackScene(unittest.TestCase):
    def test_collects_scene_set_entries_from_script(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_") as td:
            run_dir = Path(td)
            (run_dir / "script.md").write_text(SCRIPT_FIXTURE, encoding="utf-8")

            entries = collect_entries("scene_set", run_dir)

        self.assertEqual([entry["id"] for entry in entries], ["scene:10", "scene:20"])
        self.assertEqual(entries[0]["selector"], "scene10")
        self.assertEqual(entries[0]["source_path"], "script.md")
        self.assertEqual(entries[0]["source_json_pointer"], "/scenes/0")
        self.assertIn("シンデレラは灰の中で希望を保てるか", entries[0]["summary"])
        self.assertEqual(entries[0]["semantic_contract"]["dramatic_question"], "シンデレラは灰の中で希望を保てるか")
        self.assertTrue(entries[0]["semantic_contract_present"])
        self.assertFalse(entries[0]["semantic_contract_missing"])
        self.assertEqual(
            entries[0]["normalized_semantic_contract"],
            {
                "dramatic_question": "シンデレラは灰の中で希望を保てるか",
                "value_shift": "抑圧から希望へ",
                "causal_turn": "小さな光が次の行動を促す",
                "done_when": ["次の行動の理由が見える"],
            },
        )
        self.assertNotIn("contract_required_fields_missing", entries[0])
        self.assertEqual(entries[1]["semantic_contract"]["must_preserve"], ["時間制限", "ガラスの靴の意味"])

    def test_scene_intent_done_when_satisfies_scene_contract(self) -> None:
        fixture = """# Script

```yaml
scenes:
  - scene_id: 10
    scene_intent:
      dramatic_question: "問い"
      value_shift: "変化"
      causal_turn: "因果"
      done_when: ["scene全体の完了条件"]
    cuts: []
```
"""
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_") as td:
            run_dir = Path(td)
            (run_dir / "script.md").write_text(fixture, encoding="utf-8")

            entries = collect_entries("scene_set", run_dir)

        self.assertFalse(entries[0]["semantic_contract_missing"])
        self.assertEqual(entries[0]["semantic_contract"]["done_when"], ["scene全体の完了条件"])
        self.assertEqual(entries[0]["normalized_semantic_contract"]["done_when"], ["scene全体の完了条件"])

    def test_collects_scene_detail_with_cut_summaries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_") as td:
            run_dir = Path(td)
            (run_dir / "script.md").write_text(SCRIPT_FIXTURE, encoding="utf-8")

            entries = collect_entries("scene_detail", run_dir)

        self.assertEqual(entries[0]["cut_count"], 2)
        self.assertEqual(entries[0]["cut_summaries"][0]["selector"], "scene10_cut01")
        self.assertEqual(entries[0]["cut_summaries"][1]["selector"], "scene10_cut02")
        self.assertEqual(entries[0]["cut_summaries"][0]["must_show"], ["シンデレラ", "灰の台所"])
        self.assertEqual(entries[0]["handoff_to_next_scene"], "灰の台所から舞踏会の予感へつなぐ")

    def test_collects_cut_blueprint_entries_from_script(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_") as td:
            run_dir = Path(td)
            (run_dir / "script.md").write_text(SCRIPT_FIXTURE, encoding="utf-8")

            entries = collect_entries("cut_blueprint", run_dir)

        self.assertEqual([entry["selector"] for entry in entries], ["scene10_cut01", "scene10_cut02", "scene20_cut01"])
        self.assertEqual(entries[0]["semantic_contract"]["target_beat"], "灰の台所でシンデレラが立ち上がる")
        self.assertEqual(entries[0]["source_json_pointer"], "/scenes/0/cuts/0")
        self.assertTrue(entries[0]["semantic_contract_present"])
        self.assertFalse(entries[0]["semantic_contract_missing"])
        self.assertEqual(
            entries[0]["normalized_semantic_contract"],
            {
                "target_beat": "灰の台所でシンデレラが立ち上がる",
                "must_show": ["シンデレラ", "灰の台所"],
                "must_avoid": ["画面内テキスト"],
                "done_when": ["人物と場所が一枚で読める"],
            },
        )
        self.assertEqual(entries[0]["next_cut_summary"]["selector"], "scene10_cut02")
        self.assertNotIn("previous_cut_summary", entries[0])
        self.assertEqual(entries[1]["previous_cut_summary"]["selector"], "scene10_cut01")
        self.assertNotIn("next_cut_summary", entries[1])
        self.assertTrue(entries[1]["semantic_contract_missing"])
        self.assertEqual(entries[1]["contract_required_fields_missing"], ["must_avoid", "done_when"])
        self.assertEqual(entries[0]["asset_dependency_hint"] if "asset_dependency_hint" in entries[0] else None, None)
        self.assertEqual(entries[2]["semantic_contract"]["target_beat"], "ガラスの靴が証拠になる")
        self.assertFalse(entries[2]["semantic_contract_missing"])

    def test_falls_back_to_video_manifest_when_script_is_absent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(MANIFEST_FIXTURE, encoding="utf-8")

            entries = collect_entries("cut_blueprint", run_dir)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["source_path"], "video_manifest.md")
        self.assertEqual(entries[0]["source_json_pointer"], "/scenes/0/cuts/0")
        self.assertEqual(entries[0]["selector"], "scene3.7_cut01")
        self.assertEqual(entries[0]["semantic_contract"]["must_show"], ["海底神殿", "巨大な砂時計"])
        self.assertTrue(entries[0]["semantic_contract_missing"])
        self.assertEqual(entries[0]["contract_required_fields_missing"], ["must_avoid"])

    def test_rejects_unknown_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_") as td:
            with self.assertRaises(ValueError):
                collect_entries("asset_plan", Path(td))


if __name__ == "__main__":
    unittest.main()
