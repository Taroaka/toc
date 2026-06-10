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

    def test_cut_blueprint_entry_uses_event_context_without_full_scene_event(self) -> None:
        fixture = """# Script

```yaml
scenes:
  - scene_id: 10
    scene_intent:
      dramatic_question: "問い"
      value_shift: "変化"
      causal_turn: "因果"
      reveal_constraints:
        - "future_reveal"
    scene_event:
      schema_version: "scene_event_v1"
      event_sequence:
        - beat_id: "scene10_event_setup"
          beat_function: "setup"
          what_happens: "開始"
        - beat_id: "scene10_event_pressure"
          beat_function: "pressure"
          what_happens: "圧力"
        - beat_id: "scene10_event_turn"
          beat_function: "turn"
          what_happens: "転換"
      forbidden_event_changes: ["future_reveal"]
    cuts:
      - cut_id: "01"
        cut_contract:
          schema_version: "3.0"
          source_event_contract:
            primary_event_beat_id: "scene10_event_pressure"
            source_event_beat_ids: ["scene10_event_pressure"]
            event_beat_function: "pressure"
            event_time_position: "before_trigger"
            source_event_summary: "圧力"
            source_visible_action: "圧力が見える"
            source_visible_reaction: "表情が変わる"
            event_facts_to_preserve: ["圧力"]
            event_facts_not_to_invent: ["future_reveal"]
            allowed_reveal_info_ids: []
            forbidden_reveal_info_ids: ["future_reveal"]
          viewer_contract:
            target_beat: "圧力を見せる"
            must_show: ["圧力"]
            must_avoid: []
            done_when: ["圧力が見える"]
          first_frame_contract:
            source_event_beat_id: "scene10_event_pressure"
            event_time_position: "before_trigger"
            event_fact_visible_in_still: "圧力"
          motion_contract:
            source_event_beat_id: "scene10_event_pressure"
            starts_from_first_frame: true
            must_not_advance_to_event_beat_ids: ["scene10_event_turn"]
          narration_contract:
            source_event_beat_ids: ["scene10_event_pressure"]
            forbidden_info_ids: ["future_reveal"]
            must_not_explain_visible_action_as_caption: true
            narration_event_boundary: "same_event_only"
```
"""
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_") as td:
            run_dir = Path(td)
            (run_dir / "script.md").write_text(fixture, encoding="utf-8")

            entries = collect_entries("cut_blueprint", run_dir)

        self.assertNotIn("scene_event", entries[0])
        context = entries[0]["event_context_for_cut"]
        self.assertEqual(context["primary_event_beat"]["beat_id"], "scene10_event_pressure")
        self.assertEqual([beat["beat_id"] for beat in context["neighboring_event_beats"]], ["scene10_event_setup", "scene10_event_turn"])
        self.assertEqual(context["forbidden_event_changes"], ["future_reveal"])
        self.assertEqual(context["reveal_constraints_for_this_cut"], ["future_reveal"])

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
