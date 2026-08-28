from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toc.semantic_pack_scene import collect_entries


BUILD_PACK_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build-semantic-review-pack.py"


def load_pack_builder():
    spec = importlib.util.spec_from_file_location("build_semantic_review_pack_time_of_day", BUILD_PACK_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {BUILD_PACK_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT_FIXTURE = """# Script

```yaml
script_metadata:
  topic: "シンデレラ"
  time: "17世紀フランス時代"
  scene_time_of_day_contract: required_v1
scenes:
  - scene_id: 10
    time_of_day: 朝
    phase: opening
    importance: high
    handoff_to_next_scene: "灰の台所から舞踏会の予感へつなぐ"
    scene_intent:
      dramatic_question: "シンデレラは灰の中で希望を保てるか"
      value_shift: "抑圧から希望へ"
      causal_turn: "小さな光が次の行動を促す"
    scene_generation:
      schema_version: "scene_generation_v1"
      scene_authoring_context:
        schema_version: "scene_authoring_context_v1"
        source_beats:
          - source_story_beat_id: "cinderella_ash_beat"
            summary: "灰の中で希望を保つ"
      scene_prompt_payload:
        schema_version: "scene_prompt_payload_v1"
        prompt: "灰の台所のsceneが物語内で何を成立させるかを設計する。"
        input_refs: ["story.md"]
        required_outputs: ["scene_intent", "scene_event", "scene_character_state_timeline", "scene_film_coverage_plan", "scene_cut_coverage_plan", "forbidden_event_changes"]
        constraints: ["後段実行情報を含めない"]
      scene_debug_prompt_source:
        schema_version: "scene_debug_prompt_source_v1"
        not_sent_to_agent: true
        source_story_beat_ids: ["cinderella_ash_beat"]
        source_beats: ["灰の中で希望を保つ"]
        adaptation_choices: ["source beatを具体化する"]
        excluded_from_payload: ["後段実行情報"]
      scene_generation_contract:
        schema_version: "scene_generation_contract_v1"
        required_outputs: ["scene_intent", "scene_event", "scene_character_state_timeline", "scene_film_coverage_plan", "scene_cut_coverage_plan", "forbidden_event_changes"]
        scene_event_schema_version: "scene_event_v1"
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
    time_of_day: 夜
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


def _count_dict_key(value: object, target: str) -> int:
    if isinstance(value, dict):
        return sum((key == target) + _count_dict_key(item, target) for key, item in value.items())
    if isinstance(value, list):
        return sum(_count_dict_key(item, target) for item in value)
    return 0


def _serialized_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


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
        self.assertEqual(entries[0]["time_of_day"], "朝")
        self.assertEqual(entries[1]["time_of_day"], "夜")
        self.assertTrue(entries[0]["time_of_day_contract_declared"])
        self.assertEqual(entries[0]["time_of_day_status"], "valid")
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
        self.assertNotIn("scene_generation", entries[0])
        self.assertNotIn("scene_character_state_timeline", entries[0])
        self.assertNotIn("scene_film_coverage_plan", entries[0])

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
        self.assertNotIn("time_of_day", entries[0])
        self.assertFalse(entries[0]["time_of_day_contract_declared"])
        self.assertEqual(entries[0]["time_of_day_status"], "missing")
        self.assertEqual(entries[0]["semantic_contract"]["done_when"], ["scene全体の完了条件"])
        self.assertEqual(entries[0]["normalized_semantic_contract"]["done_when"], ["scene全体の完了条件"])

    def test_collects_scene_detail_with_cut_summaries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_") as td:
            run_dir = Path(td)
            (run_dir / "script.md").write_text(SCRIPT_FIXTURE, encoding="utf-8")

            entries = collect_entries("scene_detail", run_dir)

        self.assertEqual(entries[0]["cut_count"], 2)
        self.assertEqual(entries[0]["cut_summaries"][0]["selector"], "scene10_cut01")
        self.assertEqual(entries[0]["time_of_day"], "朝")
        self.assertEqual(entries[0]["cut_summaries"][1]["selector"], "scene10_cut02")
        self.assertEqual(entries[0]["scene_generation"]["scene_prompt_payload"]["schema_version"], "scene_prompt_payload_v1")
        self.assertEqual(entries[0]["cut_summaries"][0]["must_show"], ["シンデレラ", "灰の台所"])
        self.assertEqual(entries[0]["handoff_to_next_scene"], "灰の台所から舞踏会の予感へつなぐ")

    def test_scene_set_is_compact_and_keeps_scene_event_once(self) -> None:
        scene_event = {
            "schema_version": "scene_event_v1",
            "event_sequence": [
                {
                    "beat_id": f"scene42_event_{index:02d}",
                    "beat_function": "pressure" if index % 2 else "threshold",
                    "what_happens": f"出来事 {index} が起きる",
                    "concrete_event": "主人公が封印された扉の前で証拠を突きつけられる",
                    "story_grounding": "原典の約束と代償をこの場面の選択へ接続する",
                    "visible_action": "手を伸ばし、ためらい、扉を開く",
                    "visible_reaction": "仲間が息をのみ、主人公の決断を見守る",
                    "must_be_seen": True,
                }
                for index in range(12)
            ],
            "turning_event_ref": "scene42_event_07",
            "end_situation_ref": "scene42_event_11",
            "forbidden_event_changes": ["結末の先取り", "未承認の正体開示"],
        }
        scene = {
            "scene_id": 42,
            "phase": "ordeal",
            "importance": "high",
            "time_of_day": "夜",
            "location_mode": "sequence",
            "location_sequence": ["封印回廊", "扉の間"],
            "location_segments": [
                {
                    "location": "封印回廊",
                    "responsibility": "証拠を受け取り退路を断たれる",
                    "primary_subject": "主人公",
                    "visible_action": "証拠を握って扉へ進む",
                    "visible_reaction": "仲間が回廊の入口で足を止める",
                    "required_visual_evidence": ["封印", "証拠"],
                    "required_roles": ["protagonist", "witness"],
                },
                {
                    "location": "扉の間",
                    "responsibility": "主人公が扉を開く決断をする",
                    "primary_subject": "主人公",
                    "visible_action": "封印扉へ手をかける",
                    "visible_reaction": "門番が道を譲る",
                    "required_visual_evidence": ["封印扉", "門番"],
                    "required_roles": ["protagonist", "authority_or_community"],
                },
            ],
            "scene_intent": {
                "dramatic_question": "主人公は代償を受け入れて扉を開くか",
                "value_shift": "ためらいから決断へ",
                "causal_turn": "証拠を突きつけられたことで扉を開く理由が生まれる",
                "done_when": ["決断と次の危機への理由が読める"],
                "role_coverage": {
                    "required_roles": [
                        "protagonist",
                        "witness",
                        "authority_or_community",
                    ],
                    "must_not_collapse_to_protagonist_only": True,
                },
                "story_event_obligations": [
                    {
                        "event_id": "scene42_event_turn",
                        "required_roles": ["protagonist", "witness"],
                        "visual_evidence": ["証拠", "封印扉"],
                    }
                ],
            },
            "scene_event": scene_event,
            "semantic_contract": {
                "scene_event": scene_event,
                "dramatic_question": "主人公は代償を受け入れて扉を開くか",
                "value_shift": "ためらいから決断へ",
                "causal_turn": "証拠を突きつけられたことで扉を開く理由が生まれる",
                "done_when": ["決断と次の危機への理由が読める"],
            },
            "scene_generation": {
                "schema_version": "scene_generation_v1",
                "scene_authoring_context": {"source_beats": ["原典の重要出来事"] * 40},
                "scene_prompt_payload": {"prompt": "scene prompt payload " * 500},
                "scene_debug_prompt_source": {"source_beats": ["debug source"] * 40},
                "scene_generation_contract": {"required_outputs": ["scene_event"] * 40},
            },
            "scene_character_state_timeline": {
                "characters": [
                    {
                        "character_id": f"character_{index:02d}",
                        "character_name": f"登場人物 {index}",
                        "scene_role": (
                            "protagonist" if index == 0 else "witness"
                        ),
                        "appearance_asset_ids": [
                            f"character_{index:02d}_default"
                        ],
                        "state_before": "秘密を隠している",
                        "state_after": "決断を共有する",
                        "transition": "証拠によって選択を迫られる",
                        "evidence": ["視線", "手の震え", "扉の音"] * 20,
                    }
                    for index in range(8)
                ]
            },
            "scene_film_coverage_plan": {
                "shot_mix": {
                    "required_coverage": [
                        {
                            "coverage_id": f"coverage_{index:02d}",
                            "shot_role": "decision",
                            "shot_scale": "medium close-up",
                            "composition": "人物と封印扉を同一画面に置く",
                            "rationale": "選択の因果を視覚的に読ませる",
                        }
                        for index in range(12)
                    ]
                },
                "continuity_rules": ["扉の位置", "手元の証拠", "夜の光"] * 30,
            },
            "coverage_review": {"audience_information_covered": True, "visualizable_action_covered": True},
            "handoff_to_next_scene": "開いた扉の先で代償の正体が明らかになる",
            "terminal_resolution": "決断は成立するが、代償は未解決のまま次へ渡る",
            "cuts": [{"cut_id": "01", "cut_blueprint": {"target_beat": "扉を開く"}}],
        }
        source = {
            "script_metadata": {"scene_time_of_day_contract": "required_v1"},
            "canonical_event_coverage_matrix": {
                "policy_version": "canonical_event_coverage_matrix_v1",
                "assignments": [{"event_id": f"event_{index}", "scene_id": 42} for index in range(8)],
            },
            "scenes": [scene],
        }

        scene_set_entries = collect_entries(
            "scene_set",
            Path("."),
            source_document=("script.md", source),
        )
        scene_detail_entries = collect_entries(
            "scene_detail",
            Path("."),
            source_document=("script.md", source),
        )

        scene_set_entry = scene_set_entries[0]
        scene_detail_entry = scene_detail_entries[0]
        self.assertEqual(_count_dict_key(scene_set_entry, "scene_event"), 1)
        self.assertNotIn("scene_event", scene_set_entry["semantic_contract"])
        self.assertNotIn("scene_event", scene_set_entry["normalized_semantic_contract"])
        self.assertEqual(scene_set_entry["scene_event"], scene_event)
        self.assertEqual(
            scene_set_entry["location_sequence"],
            ["封印回廊", "扉の間"],
        )
        self.assertEqual(
            scene_set_entry["location_segments"],
            scene["location_segments"],
        )
        self.assertEqual(scene_set_entry["location_mode"], "sequence")
        self.assertEqual(
            scene_set_entry["participants"][0],
            {
                "character_id": "character_00",
                "character_name": "登場人物 0",
                "scene_role": "protagonist",
                "appearance_asset_ids": ["character_00_default"],
            },
        )
        self.assertEqual(
            scene_set_entry["role_coverage"]["required_roles"],
            ["protagonist", "witness", "authority_or_community"],
        )
        self.assertEqual(
            scene_set_entry["scene_intent"]["role_coverage"]["required_roles"],
            ["protagonist", "witness", "authority_or_community"],
        )
        self.assertEqual(
            scene_set_entry["scene_intent"]["story_event_obligations"][0][
                "required_roles"
            ],
            ["protagonist", "witness"],
        )
        for field in ("scene_generation", "scene_character_state_timeline", "scene_film_coverage_plan"):
            self.assertNotIn(field, scene_set_entry)
        for field in (
            "scene_intent",
            "coverage_review",
            "handoff_to_next_scene",
            "terminal_resolution",
            "time_of_day",
            "time_of_day_contract_declared",
            "canonical_event_coverage_matrix",
            "phase",
            "importance",
            "summary",
        ):
            self.assertIn(field, scene_set_entry)

        self.assertEqual(scene_detail_entry["scene_event"], scene_event)
        self.assertIn("scene_event", scene_detail_entry["semantic_contract"])
        self.assertIn("scene_event", scene_detail_entry["normalized_semantic_contract"])
        for field in ("scene_generation", "scene_character_state_timeline", "scene_film_coverage_plan"):
            self.assertIn(field, scene_detail_entry)

        scene_set_size = _serialized_size(scene_set_entry)
        scene_detail_size = _serialized_size(scene_detail_entry)
        self.assertLess(scene_set_size, scene_detail_size * 0.4)

    def test_collects_cut_blueprint_entries_from_script(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_") as td:
            run_dir = Path(td)
            (run_dir / "script.md").write_text(SCRIPT_FIXTURE, encoding="utf-8")

            entries = collect_entries("cut_blueprint", run_dir)

        self.assertEqual([entry["selector"] for entry in entries], ["scene10_cut01", "scene10_cut02", "scene20_cut01"])
        self.assertEqual(entries[0]["semantic_contract"]["target_beat"], "灰の台所でシンデレラが立ち上がる")
        self.assertEqual(entries[0]["source_json_pointer"], "/scenes/0/cuts/0")
        self.assertEqual(entries[0]["time_of_day"], "朝")
        self.assertEqual(entries[2]["time_of_day"], "夜")
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

    def test_scene_pack_batch_parses_script_once_for_all_three_stages(self) -> None:
        builder = load_pack_builder()
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_batch_") as td:
            run_dir = Path(td)
            (run_dir / "script.md").write_text(
                SCRIPT_FIXTURE,
                encoding="utf-8",
            )
            (run_dir / "story.md").write_text(
                "# Story\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                MANIFEST_FIXTURE,
                encoding="utf-8",
            )

            with (
                patch.object(
                    builder,
                    "load_structured_document",
                    wraps=builder.load_structured_document,
                ) as loader,
                patch.object(
                    builder,
                    "review_source_fingerprint",
                    wraps=builder.review_source_fingerprint,
                ) as fingerprint,
            ):
                results = builder.build_packs(
                    run_dir,
                    ("scene_set", "scene_detail", "cut_blueprint"),
                )

            self.assertEqual(len(results), 3)
            self.assertEqual(loader.call_count, 1)
            self.assertEqual(fingerprint.call_count, 3)
            self.assertTrue(
                (run_dir / "logs/review/semantic/scene_set.scope.json").exists()
            )
            self.assertTrue(
                (run_dir / "logs/review/semantic/scene_detail.scope.json").exists()
            )
            self.assertTrue(
                (run_dir / "logs/review/semantic/cut_blueprint.scope.json").exists()
            )

    def test_scene_pack_batch_preserves_manifest_fallback_source_label(self) -> None:
        builder = load_pack_builder()
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_batch_manifest_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(
                MANIFEST_FIXTURE,
                encoding="utf-8",
            )

            builder.build_packs(
                run_dir,
                ("scene_set", "scene_detail", "cut_blueprint"),
            )

            scene_collection = (
                run_dir / "logs/review/semantic/scene_set.collection.md"
            ).read_text(encoding="utf-8")
            cut_collection = (
                run_dir / "logs/review/semantic/cut_blueprint.collection.md"
            ).read_text(encoding="utf-8")
            self.assertIn('"source_path": "manifest"', scene_collection)
            self.assertIn('"source_path": "manifest"', cut_collection)

    def test_non_scene_pack_batch_parses_shared_manifest_once(self) -> None:
        builder = load_pack_builder()
        with tempfile.TemporaryDirectory(prefix="toc_downstream_pack_batch_") as td:
            run_dir = Path(td)
            (run_dir / "story.md").write_text("# Story\n", encoding="utf-8")
            (run_dir / "script.md").write_text("# Script\n", encoding="utf-8")
            (run_dir / "video_manifest.md").write_text(
                MANIFEST_FIXTURE,
                encoding="utf-8",
            )

            with patch.object(
                builder,
                "load_manifest",
                wraps=builder.load_manifest,
            ) as manifest_loader:
                builder.build_packs(
                    run_dir,
                    ("asset_plan", "image_prompt"),
                )

            self.assertEqual(manifest_loader.call_count, 1)

    def test_declared_contract_exposes_missing_and_invalid_time_of_day_without_stringifying(self) -> None:
        fixture = """# Script

```yaml
script_metadata:
  time: "17世紀フランス時代"
  scene_time_of_day_contract: required_v1
scenes:
  - scene_id: 10
    scene_intent: {dramatic_question: "問い", value_shift: "変化", causal_turn: "因果", done_when: ["完了"]}
    cuts: []
  - scene_id: 20
    time_of_day: [夜]
    scene_intent: {dramatic_question: "問い", value_shift: "変化", causal_turn: "因果", done_when: ["完了"]}
    cuts: []
```
"""
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_") as td:
            run_dir = Path(td)
            (run_dir / "script.md").write_text(fixture, encoding="utf-8")

            entries = collect_entries("scene_set", run_dir)

        self.assertTrue(entries[0]["time_of_day_contract_declared"])
        self.assertEqual(entries[0]["time_of_day_status"], "missing")
        self.assertNotIn("time_of_day", entries[0])
        self.assertEqual(entries[1]["time_of_day_status"], "invalid_type")
        self.assertEqual(entries[1]["time_of_day_raw"], ["夜"])
        self.assertNotIn("time_of_day", entries[1])

    def test_legacy_partial_daypart_values_do_not_declare_the_required_contract(self) -> None:
        fixture = """# Script

```yaml
script_metadata:
  topic: legacy
scenes:
  - scene_id: 10
    time_of_day: "夜"
    scene_intent: {dramatic_question: "問い", value_shift: "変化", causal_turn: "因果", done_when: ["完了"]}
    cuts: []
  - scene_id: 20
    time_of_day: ""
    scene_intent: {dramatic_question: "問い", value_shift: "変化", causal_turn: "因果", done_when: ["完了"]}
    cuts: []
  - scene_id: 30
    scene_intent: {dramatic_question: "問い", value_shift: "変化", causal_turn: "因果", done_when: ["完了"]}
    cuts: []
```
"""
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_") as td:
            run_dir = Path(td)
            (run_dir / "script.md").write_text(fixture, encoding="utf-8")

            entries = collect_entries("scene_set", run_dir)

        self.assertEqual([entry["time_of_day_contract_declared"] for entry in entries], [False, False, False])
        self.assertEqual([entry["time_of_day_status"] for entry in entries], ["valid", "blank", "missing"])

    def test_scene_review_guidance_covers_all_scene_stages_and_legacy_status(self) -> None:
        builder = load_pack_builder()

        for stage in ("scene_set", "scene_detail", "cut_blueprint"):
            guidance = "\n".join(builder._stage_specific_review_instructions(stage))
            self.assertIn("time_of_day_contract_declared", guidance)
            self.assertIn("time_of_day_status", guidance)
            self.assertIn("undeclared legacy omission", guidance)
            self.assertIn("invalid_type", guidance)
            self.assertIn("script_metadata.time", guidance)
        self.assertIn(
            "producer-facing repair example",
            "\n".join(builder._stage_specific_review_instructions("cut_blueprint")),
        )
        story_guidance = "\n".join(builder._stage_specific_review_instructions("story"))
        self.assertIn("scene_time_of_day_statuses[].status", story_guidance)
        self.assertIn("time_of_day_contract_declared", story_guidance)

    def test_semantic_prompt_reviews_exact_authored_event_inventory_without_fixed_ladder(self) -> None:
        builder = load_pack_builder()
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_prompt_") as td:
            run_dir = Path(td)
            prompt = builder.render_prompt(
                stage="cut_blueprint",
                run_dir=run_dir,
                collection_path=run_dir / "collection.md",
                scope_path=run_dir / "scope.json",
                report_path=run_dir / "report.md",
            )

        self.assertIn("exact authored `event_beat_inventory`", prompt)
        self.assertIn("mirrors every ordered nonblank beat ID", prompt)
        self.assertIn("matches its corresponding source beat whether assigned or not", prompt)
        self.assertIn("must_be_seen != false", prompt)
        self.assertIn("arbitrary nonblank `beat_function`", prompt)
        self.assertIn("valid one-beat scene", prompt)
        self.assertIn("Recommend more cuts only when a distinct authored beat or semantic obligation is uncovered", prompt)
        self.assertNotIn("event_sequence setup/pressure/turn/payoff beats", prompt)

    def test_scene_pack_does_not_parse_unused_video_manifest(self) -> None:
        builder = load_pack_builder()
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_build_") as td:
            run_dir = Path(td)
            (run_dir / "script.md").write_text(SCRIPT_FIXTURE, encoding="utf-8")
            (run_dir / "video_manifest.md").write_text(
                "```yaml\nvideo_metadata: {topic: test}\nscenes: []\n```\n",
                encoding="utf-8",
            )

            with patch.object(
                builder,
                "load_manifest",
                side_effect=AssertionError("unused manifest was parsed"),
            ):
                _collection, _scope, _prompt, _report, count = builder.build_pack(
                    run_dir,
                    "scene_set",
                )

        self.assertEqual(count, 2)

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
          event_context_for_cut:
            duplicate_marker: "review pack must not carry this nested duplicate"
```
"""
        with tempfile.TemporaryDirectory(prefix="toc_scene_pack_") as td:
            run_dir = Path(td)
            (run_dir / "script.md").write_text(fixture, encoding="utf-8")

            entries = collect_entries("cut_blueprint", run_dir)

        self.assertNotIn("scene_event", entries[0])
        self.assertNotIn("scene_generation", entries[0])
        context = entries[0]["event_context_for_cut"]
        self.assertEqual(context["primary_event_beat"]["beat_id"], "scene10_event_pressure")
        self.assertEqual([beat["beat_id"] for beat in context["neighboring_event_beats"]], ["scene10_event_setup", "scene10_event_turn"])
        self.assertEqual(context["forbidden_event_changes"], ["future_reveal"])
        self.assertEqual(context["reveal_constraints_for_this_cut"], ["future_reveal"])
        self.assertNotIn("event_context_for_cut", entries[0]["cut_contract"])
        self.assertNotIn("source_event_contract", entries[0]["semantic_contract"])
        self.assertEqual(
            entries[0]["semantic_contract"],
            {
                "target_beat": "圧力を見せる",
                "must_show": ["圧力"],
                "done_when": ["圧力が見える"],
            },
        )
        packet = entries[0]["cut_context_packet"]
        self.assertEqual(packet["schema_version"], "cut_context_packet_v1")
        self.assertFalse(packet["editable"])
        self.assertEqual(packet["cut_selector"], "scene10_cut01")
        self.assertEqual(packet["source_event"]["primary_event_beat"]["beat_id"], "scene10_event_pressure")
        self.assertIn("cut_context_packet_diagnostics", entries[0])
        self.assertIn("warning_keys", entries[0]["cut_context_packet_diagnostics"])

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
