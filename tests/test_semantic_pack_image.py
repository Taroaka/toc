import json
import tempfile
import unittest
from pathlib import Path

from toc.semantic_pack_image import collect_entries


def write_manifest(run_dir: Path) -> None:
    (run_dir / "video_manifest.md").write_text(
        "\n".join(
            [
                "# Video Manifest",
                "",
                "```yaml",
                "scenes:",
                "  - scene_id: 10",
                "    scene_intent:",
                "      story_event_obligations:",
                "        - event_id: scene01_story_event",
                "          source_events: [灰の台所で名前を奪われる]",
                "          audience_knowledge_delta: 観客は名前を奪われた事実を理解する",
                "          causal_proof: 灰と台所の配置で原因と結果が読める",
                "          visual_evidence: [灰, 台所, 姿勢]",
                "          required_roles: [protagonist, opponent]",
                "    scene_event:",
                "      schema_version: scene_event_v1",
                "      event_logline: 灰の台所で名前を奪われる",
                "      start_situation: 灰の台所にいる",
                "      source_story_beat_ids: [story_scene10]",
                "      event_sequence:",
                "        - beat_id: scene10_event_setup",
                "          beat_function: setup",
                "          what_happens: 灰の台所に立つ",
                "        - beat_id: scene10_event_pressure",
                "          beat_function: pressure",
                "          what_happens: 名前を奪われる",
                "        - beat_id: scene10_event_turn",
                "          beat_function: turn",
                "          what_happens: 希望を保つ",
                "      forbidden_event_changes: [ガラスの靴を見せない]",
                "      role_coverage:",
                "        required_roles: [protagonist, opponent]",
                "      audience_knowledge_plan: [観客は名前を奪われた事実を理解する]",
                "      visual_proof_obligations:",
                "        - causal_proof: 灰と台所の配置で原因と結果が読める",
                "          visual_evidence: [灰, 台所, 姿勢]",
                "      anti_redundancy_policy:",
                "        rule: 同じ意味を繰り返さない",
                "      static_first_frame_rules: [静止画で証拠を見せる]",
                "    scene_cut_coverage_plan:",
                "      coverage_strategy: reverse_from_scene_event",
                "      source_schema_version: scene_event_v1",
                "      min_cut_count: {by_importance: 2, by_duration: 2, by_event_beats: 2, selected: 2}",
                "      minimum_cut_count: 2",
                "      selected_cut_count: 2",
                "      scene_obligations:",
                "        - source: dramatic_question",
                "          evidence: 灰の台所で何が始まるか",
                "      cut_assignments:",
                "        - cut_index: 1",
                "          obligation_id: scene_pressure",
                "          cut_function: pressure",
                "          source: dramatic_question",
                "          target_beat: 灰の台所の導入",
                "    cuts:",
                "      - cut_id: '01'",
                "        selector: scene10_cut01",
                "        cut_contract:",
                "          schema_version: '3.0'",
                "          source_event_contract:",
                "            primary_event_beat_id: scene10_event_pressure",
                "            source_event_beat_ids: [scene10_event_pressure]",
                "            event_beat_function: pressure",
                "            event_time_position: before_trigger",
                "            source_event_summary: 名前を奪われる",
                "            source_visible_action: 名前を奪われる姿勢が見える",
                "            source_visible_reaction: 顔が伏せられる",
                "            event_facts_to_preserve: [名前を奪われる]",
                "            event_facts_not_to_invent: [ガラスの靴を見せない]",
                "            allowed_reveal_info_ids: []",
                "            forbidden_reveal_info_ids: [ガラスの靴]",
                "          viewer_contract:",
                "            target_beat: 灰の台所の導入",
                "            audience_knowledge_delta: 観客は灰の台所で名前を奪われたことを理解する",
                "            causal_proof: 灰、台所、人物の姿勢で原因と結果が読める",
                "            visual_evidence: [灰, 台所, 姿勢]",
                "            required_roles: [protagonist, opponent]",
                "            anti_redundancy_key: dramatic_question:scene_pressure",
                "            visual_proof: 灰の台所の姿勢",
                "            must_show: [シンデレラ, 灰の台所]",
                "            must_avoid: [ロゴ]",
                "            done_when: [人物と場所が一枚で読める]",
                "          first_frame_contract:",
                "            source_event_beat_id: scene10_event_pressure",
                "            event_time_position: before_trigger",
                "            event_fact_visible_in_still: 名前を奪われる姿勢",
                "            not_yet_happened_in_still: [ガラスの靴]",
                "            first_frame_brief: 灰の台所でシンデレラが立つ",
                "            static_first_frame_rule: 動作ではなく静止した証拠として見せる",
                "          motion_contract:",
                "            source_event_beat_id: scene10_event_pressure",
                "            starts_from_first_frame: true",
                "            must_not_advance_to_event_beat_ids: [scene10_event_turn]",
                "            motion_brief: 伏せた顔が少し上がる",
                "          narration_contract:",
                "            source_event_beat_ids: [scene10_event_pressure]",
                "            allowed_info_ids: []",
                "            forbidden_info_ids: [ガラスの靴]",
                "            must_not_advance_to_event_beat_ids: [scene10_event_turn]",
                "            must_not_explain_visible_action_as_caption: true",
                "            narration_event_boundary: same_event_only",
                "          event_context_for_cut:",
                "            derived_from: [\"scene_event.event_sequence[]\", \"cut_contract.source_event_contract\"]",
                "            editable: false",
                "            primary_event_beat:",
                "              beat_id: scene10_event_pressure",
                "              beat_function: pressure",
                "              what_happens: 名前を奪われる",
                "            neighboring_event_beats: []",
                "            forbidden_event_changes: [ガラスの靴を見せない]",
                "            reveal_constraints_for_this_cut: []",
                "          viewer_contract:",
                "            target_beat: 灰の台所の導入",
                "            audience_knowledge_delta: 観客は灰の台所で名前を奪われたことを理解する",
                "            causal_proof: 灰、台所、人物の姿勢で原因と結果が読める",
                "            visual_evidence: [灰, 台所, 姿勢]",
                "            required_roles: [protagonist, opponent]",
                "            anti_redundancy_key: dramatic_question:scene_pressure",
                "            assigned_story_event_ids: [scene01_story_event]",
                "            visual_proof: 灰の台所の導入",
                "            must_show: [シンデレラ, 灰の台所]",
                "            must_avoid: [ロゴ]",
                "            done_when: [人物と場所が一枚で読める]",
                "          first_frame_contract:",
                "            static_first_frame_rule: 動作ではなく静止した証拠として見せる",
                "          continuity_contract:",
                "            start_state:",
                "              spatial_state: 灰の台所",
                "        still_image_plan:",
                "          mode: generate_still",
                "          rationale: 導入の静止画",
                "        scene_contract:",
                "          target_beat: 灰の台所の導入",
                "          audience_knowledge_delta: 観客は灰の台所で名前を奪われたことを理解する",
                "          causal_proof: 灰、台所、人物の姿勢で原因と結果が読める",
                "          visual_evidence: [灰, 台所, 姿勢]",
                "          required_roles: [protagonist, opponent]",
                "          anti_redundancy_key: dramatic_question:scene_pressure",
                "          assigned_story_event_ids: [scene01_story_event]",
                "          static_first_frame_rule: 動作ではなく静止した証拠として見せる",
                "          must_show: [シンデレラ, 灰の台所]",
                "          must_avoid: [ロゴ]",
                "          done_when: [人物と場所が一枚で読める]",
                "          not_yet_visible: [ガラスの靴]",
                "          only_after_scene: scene30",
                "          primary_location: 灰の台所",
                "          emotional_state: 孤独だが希望を失っていない",
                "          continuity_from_previous: 前のカットから灰の台所の光を維持する",
                "        image_generation:",
                "          output: assets/scenes/scene10_cut01.png",
                "          prompt: 灰の台所でシンデレラが立つ。画面内テキストなし。",
                "          references:",
                "            - assets/characters/cinderella.png",
                "            - assets/locations/kitchen.png",
                "          character_ids: [cinderella]",
                "          object_ids: []",
                "          location_ids: [kitchen]",
                "          reference_count: 2",
                "          review:",
                "            status: approved",
                "            agent_review_ok: true",
                "            human_review_ok: false",
                "            agent_review_reason_keys: []",
                "            agent_review_reason_messages: []",
                "            overall_score: 0.9",
                "        audio:",
                "          narration:",
                "            text: 灰の台所で物語が始まる。",
                "      - cut_id: '02'",
                "        selector: scene10_cut02",
                "        still_image_plan:",
                "          mode: skip",
                "        image_generation:",
                "          output: assets/scenes/scene10_cut02.png",
                "          prompt: これは画像プロンプトレビュー対象外。",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_asset_plan(run_dir: Path) -> None:
    (run_dir / "asset_plan.md").write_text(
        "\n".join(
            [
                "# Asset Plan",
                "",
                "```yaml",
                "assets:",
                "  - asset_id: cinderella",
                "    asset_type: character",
                "    story_purpose: 主人公の同一性を保つ",
                "    visual_spec:",
                "      face: 参照画像と同じ顔",
                "  - asset_id: kitchen",
                "    asset_type: character",
                "    story_purpose: 灰の台所の場所参照として使う",
                "    visual_spec: 人物ポートレートのように見える室内",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )


class TestSemanticPackImage(unittest.TestCase):
    def test_collect_image_prompt_entries_keeps_judgment_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_semantic_pack_image_") as td:
            run_dir = Path(td)
            write_manifest(run_dir)
            write_asset_plan(run_dir)

            entries = collect_entries("image_prompt", run_dir)

            self.assertEqual(len(entries), 2)
            entry = entries[0]
            self.assertEqual(entry["stage"], "image_prompt")
            self.assertEqual(entry["review_scope"], "all_entries")
            self.assertEqual(entry["selector"], "scene10_cut01")
            self.assertEqual(entry["output"], "assets/scenes/scene10_cut01.png")
            self.assertIn("prompt_blocks", entry)
            self.assertIn("image_prompt_gate_focus", entry)
            self.assertIn("first_frame_visual_plan", entry)
            self.assertEqual(entry["first_frame_visual_plan"]["schema_version"], "first_frame_visual_plan_v1")
            self.assertFalse(entry["first_frame_visual_plan"]["editable"])
            self.assertEqual(
                entry["first_frame_visual_plan"]["source_grounding"]["source_event_beat_id"],
                "scene10_event_pressure",
            )
            self.assertIn("temporal_boundary", entry["first_frame_visual_plan"])
            self.assertIn("motion_affordance", entry["first_frame_visual_plan"])
            self.assertEqual(entry["references"], ["assets/characters/cinderella.png", "assets/locations/kitchen.png"])
            self.assertEqual(entry["character_ids"], ["cinderella"])
            self.assertEqual(entry["location_ids"], ["kitchen"])
            self.assertEqual(entry["reference_count"], 2)
            self.assertEqual(entry["narration"], "灰の台所で物語が始まる。")
            self.assertEqual(entry["rationale"], "導入の静止画")
            self.assertEqual(entry["semantic_contract"]["target_focus"], "灰の台所の導入")
            self.assertEqual(entry["semantic_contract"]["must_include"], ["シンデレラ", "灰の台所"])
            self.assertEqual(entry["semantic_contract"]["not_yet_visible"], ["ガラスの靴"])
            self.assertEqual(entry["semantic_contract"]["only_after_scene"], "scene30")
            self.assertEqual(entry["semantic_contract"]["primary_location"], "灰の台所")
            self.assertEqual(entry["semantic_contract"]["emotional_state"], "孤独だが希望を失っていない")
            self.assertEqual(entry["semantic_contract"]["continuity_from_previous"], "前のカットから灰の台所の光を維持する")
            self.assertEqual(entry["semantic_contract"]["audience_knowledge_delta"], "観客は灰の台所で名前を奪われたことを理解する")
            self.assertEqual(entry["semantic_contract"]["causal_proof"], "灰、台所、人物の姿勢で原因と結果が読める")
            self.assertEqual(entry["semantic_contract"]["visual_evidence"], ["灰", "台所", "姿勢"])
            self.assertEqual(entry["semantic_contract"]["required_roles"], ["protagonist", "opponent"])
            self.assertEqual(entry["semantic_contract"]["static_first_frame_rule"], "動作ではなく静止した証拠として見せる")
            self.assertEqual(entry["semantic_contract"]["source_event_contract"]["primary_event_beat_id"], "scene10_event_pressure")
            self.assertEqual(entry["event_context_for_cut"]["primary_event_beat"]["beat_id"], "scene10_event_pressure")
            self.assertNotIn("scene_event", entry)
            self.assertFalse(entry["semantic_contract_missing"])
            self.assertEqual(entry["contract_required_fields_missing"], [])
            character_context = entry["asset_reference_context"]["character_ids"]["cinderella"]
            self.assertEqual(character_context["category"], "character")
            self.assertEqual(character_context["story_purpose"], "主人公の同一性を保つ")
            self.assertEqual(character_context["visual_spec"], {"face": "参照画像と同じ顔"})
            self.assertEqual(character_context["expected_reference_role"], "character")
            self.assertEqual(character_context["reference_role_mismatch_hints"], [])
            location_context = entry["asset_reference_context"]["location_ids"]["kitchen"]
            self.assertEqual(location_context["category"], "character")
            self.assertEqual(location_context["visual_spec"], "人物ポートレートのように見える室内")
            self.assertEqual(location_context["expected_reference_role"], "location")
            self.assertEqual(
                location_context["reference_role_mismatch_hints"],
                ["expected_reference_role=location but asset metadata suggests character"],
            )
            self.assertTrue(entry["review"]["agent_review_ok"])
            self.assertEqual(entry["review"]["overall_score"], 0.9)
            composite = entries[1]
            self.assertEqual(composite["review_scope"], "scene_composite")
            self.assertEqual(composite["stage"], "image_prompt")
            self.assertEqual(composite["cut_count"], 2)
            self.assertEqual(composite["scene_cut_coverage_plan"]["selected_cut_count"], 2)
            self.assertEqual(composite["story_event_obligations"][0]["event_id"], "scene01_story_event")
            self.assertEqual(composite["role_coverage"]["required_roles"], ["protagonist", "opponent"])
            self.assertNotIn("scene_event", composite["scene_contract"])
            self.assertEqual(composite["scene_event"]["schema_version"], "scene_event_v1")
            self.assertEqual(composite["cut_entries"][0]["event_context_for_cut"]["primary_event_beat"]["beat_id"], "scene10_event_pressure")
            self.assertEqual(composite["cut_entries"][0]["source_event_contract"]["primary_event_beat_id"], "scene10_event_pressure")
            self.assertIn("scene_cut_prompt_too_similar", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("event_beat_reference_integrity", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("audience_knowledge_delta_missing", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("role_coverage_missing", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("scene_cut_coverage_plan", composite["scene_composite_gate"]["must_judge"][0])

    def test_scene_image_semantic_stage_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_semantic_pack_image_") as td:
            run_dir = Path(td)
            write_manifest(run_dir)

            with self.assertRaisesRegex(ValueError, "unsupported image semantic stage"):
                collect_entries("scene_image", run_dir)

    def test_scene_image_stage_is_not_collected_for_missing_contact_sheet(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_semantic_pack_image_") as td:
            run_dir = Path(td)
            write_manifest(run_dir)

            with self.assertRaisesRegex(ValueError, "unsupported image semantic stage"):
                collect_entries("scene_image", run_dir)

    def test_grouped_asset_plan_shapes_feed_reference_context(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_semantic_pack_image_") as td:
            run_dir = Path(td)
            write_manifest(run_dir)
            (run_dir / "asset_plan.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "assets:",
                        "  characters:",
                        "    - asset_id: cinderella",
                        "      asset_type: character",
                        "      story_purpose: 主人公",
                        "      visual_spec:",
                        "        face: stable",
                        "  locations:",
                        "    - asset_id: kitchen",
                        "      asset_type: location",
                        "      story_purpose: 灰の台所",
                        "      visual_spec:",
                        "        room: stable",
                        "```",
                    ]
                ),
                encoding="utf-8",
            )

            entry = collect_entries("image_prompt", run_dir)[0]

            self.assertEqual(entry["asset_reference_context"]["character_ids"]["cinderella"]["category"], "character")
            self.assertEqual(entry["asset_reference_context"]["location_ids"]["kitchen"]["category"], "location")
            self.assertEqual(entry["asset_reference_context"]["location_ids"]["kitchen"]["reference_role_mismatch_hints"], [])

    def test_rejects_unknown_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_semantic_pack_image_") as td:
            with self.assertRaises(ValueError):
                collect_entries("asset_plan", Path(td), manifest={"scenes": []})


if __name__ == "__main__":
    unittest.main()
