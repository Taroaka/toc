from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from toc.semantic_pack import collect_entries
from toc.semantic_review import FOUNDATION_SEMANTIC_CRITERIA


REPO_ROOT = Path(__file__).resolve().parents[1]
BUILD_PACK_PATH = REPO_ROOT / "scripts" / "build-semantic-review-pack.py"
SPEC = importlib.util.spec_from_file_location("build_semantic_review_pack_foundation_test", BUILD_PACK_PATH)
assert SPEC is not None and SPEC.loader is not None
BUILD_PACK = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BUILD_PACK
SPEC.loader.exec_module(BUILD_PACK)


RESEARCH = """# Research

```yaml
topic: "桃太郎"
story_materials:
  canonical_story_dump: "桃から生まれた桃太郎が仲間を得て鬼ヶ島へ向かい、村へ帰還する。"
  chronological_events:
    - event_id: E01
      event: "桃太郎が桃から生まれる"
    - event_id: E02
      event: "犬たちと鬼ヶ島へ向かう"
    - event_id: E03
      event: "鬼を退けて村へ戻る"
  characters:
    - character_id: protagonist
      name: "桃太郎"
      role: "主人公"
      motivations: ["村を守る"]
conflicts:
  - conflict_id: C1
    topic: "鬼との対立"
    impact_on_story: "旅と対決を駆動する"
    selection_notes:
      recommended_choice: A
handoff_to_story:
  must_preserve: ["仲間を得る", "鬼ヶ島", "帰還"]
metadata:
  target_duration_seconds: 600
```
"""


STORY = """# Story

```yaml
story_metadata:
  target_duration_seconds: 600
story_structure:
  protagonist: {name: "桃太郎", role: "主人公"}
  journey:
    ordinary_world: {description: "村で育つ"}
    ordeal: {challenge: "鬼ヶ島で対峙する"}
    transformation: {before: "一人", after: "仲間を率いる"}
    return: {resolution: "村へ帰る"}
story_decomposition:
  source_material_refs: ["research.story_materials.chronological_events[E01]", "research.story_materials.chronological_events[E02]", "research.story_materials.chronological_events[E03]"]
script:
  scenes:
    - scene_id: 1
      phase: opening
      purpose: "誕生と村の期待を置く"
      conflict: "まだ役割を持たない"
      turn: "旅立ちを選ぶ"
      affect: {label_hint: curiosity, audience_job: hook}
      visualizable_action: "桃太郎が旗を持って門を出る"
      grounding_note: "E01を起点にする"
      research_refs: ["research.story_materials.chronological_events[E01]"]
    - scene_id: 2
      phase: ordeal
      purpose: "仲間と鬼ヶ島へ渡る"
      conflict: "荒波と鬼の守り"
      turn: "仲間が突破口を開く"
      affect: {label_hint: strain, audience_job: strain}
      visualizable_action: "犬たちが門を押し開く"
      grounding_note: "E02を使う"
      research_refs: ["research.story_materials.chronological_events[E02]"]
    - scene_id: 3
      phase: ending
      purpose: "帰還で物語を閉じる"
      conflict: "勝利を村へどう返すか"
      turn: "宝を共同体へ渡す"
      affect: {label_hint: relief, audience_job: release}
      visualizable_action: "桃太郎が村人へ荷を下ろす"
      grounding_note: "E03を結末に使う"
      research_refs: ["research.story_materials.chronological_events[E03]"]
```
"""


class TestSemanticPackFoundation(unittest.TestCase):
    def test_foundation_pack_rejects_invalid_structured_artifact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_foundation_pack_") as td:
            run_dir = Path(td)
            (run_dir / "research.md").write_text(
                "# Research\n\n```yaml\nstory_materials:\n  canonical_story_dump: invalid: unquoted\n```\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "research.md.*structured"):
                collect_entries("research", run_dir)

    def test_research_stage_collects_internal_story_foundation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_foundation_pack_") as td:
            run_dir = Path(td)
            (run_dir / "research.md").write_text(RESEARCH, encoding="utf-8")

            entries = collect_entries("research", run_dir)

        self.assertEqual([entry["id"] for entry in entries], ["research:foundation"])
        foundation = entries[0]
        self.assertIn("canonical_story_dump", foundation)
        self.assertEqual([item["event_id"] for item in foundation["chronological_events"]], ["E01", "E02", "E03"])
        self.assertEqual(foundation["characters"][0]["name"], "桃太郎")
        self.assertEqual(foundation["conflicts"][0]["conflict_id"], "C1")

    def test_story_stage_collects_research_baseline_and_scene_allocation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_foundation_pack_") as td:
            run_dir = Path(td)
            (run_dir / "research.md").write_text(RESEARCH, encoding="utf-8")
            (run_dir / "story.md").write_text(STORY, encoding="utf-8")

            entries = collect_entries("story", run_dir)

        self.assertEqual([entry["id"] for entry in entries], ["story:foundation"])
        foundation = entries[0]
        self.assertEqual(foundation["target_duration_seconds"], 600)
        self.assertEqual(len(foundation["scenes"]), 3)
        self.assertEqual(
            [item["event_id"] for item in foundation["research_baseline"]["chronological_events"]],
            ["E01", "E02", "E03"],
        )
        self.assertEqual(foundation["scenes"][1]["research_refs"], ["research.story_materials.chronological_events[E02]"])

    def test_foundation_pack_scope_and_prompt_are_auditable_and_internal_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_foundation_pack_") as td:
            run_dir = Path(td)
            (run_dir / "research.md").write_text(RESEARCH, encoding="utf-8")
            (run_dir / "story.md").write_text(STORY, encoding="utf-8")

            for stage, expected_sources in (
                ("research", ["research.md"]),
                ("story", ["research.md", "story.md"]),
            ):
                _collection, scope_path, prompt_path, report_path, entry_count = BUILD_PACK.build_pack(run_dir, stage)
                scope = json.loads(scope_path.read_text(encoding="utf-8"))
                prompt = prompt_path.read_text(encoding="utf-8")
                report = report_path.read_text(encoding="utf-8")

                self.assertEqual(entry_count, 1)
                self.assertEqual(scope["entry_ids"], [f"{stage}:foundation"])
                self.assertEqual(scope["source_artifacts"], expected_sources)
                self.assertIn("Do not browse or validate external URLs, editions, translations, rights, or factual fidelity", prompt)
                self.assertIn("timeline", prompt)
                self.assertIn("characters", prompt)
                self.assertIn("conflict", prompt)
                self.assertIn("MUST edit exactly one file", prompt)
                self.assertIn("Do not return the verdict only in chat", prompt)
                for criterion_id in FOUNDATION_SEMANTIC_CRITERIA[stage]:
                    self.assertIn(f"`{criterion_id}`", prompt)
                self.assertIn("criteria_results_json: []", report)


if __name__ == "__main__":
    unittest.main()
