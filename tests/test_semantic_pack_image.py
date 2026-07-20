import json
import tempfile
import unittest
from pathlib import Path

from toc.semantic_pack_image import collect_entries, collect_image_prompt_entries, load_manifest


def write_manifest(run_dir: Path) -> None:
    (run_dir / "video_manifest.md").write_text(
        "\n".join(
            [
                "# Video Manifest",
                "",
                "```yaml",
                "video_metadata:",
                "  time: 17世紀フランス時代",
                "  scene_time_of_day_contract: required_v1",
                "scenes:",
                "  - scene_id: 10",
                "    time_of_day: 夜",
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
                "          cut_selector: scene10_cut01",
                "          obligation_id: scene_pressure",
                "          cut_function: pressure",
                "          source: dramatic_question",
                "          target_beat: 灰の台所の導入",
                "    scene_film_coverage_plan:",
                "      shot_mix:",
                "        actual_shots:",
                "          - selector: scene10_cut01",
                "            shot_role: character_action",
                "            shot_scale: medium",
                "        required_coverage:",
                "          action: [scene10_cut01]",
                "      action_reaction_pair: []",
                "    scene_shot_mix_plan:",
                "      policy_version: scene_shot_mix_v1",
                "      shots:",
                "        - selector: scene10_cut01",
                "          shot_role: character_action",
                "          shot_scale: medium",
                "    scene_state_progression_plan:",
                "      policy_version: scene_state_progression_v1",
                "      progression_mode: sequential_state_progression",
                "      mode_reason: 出発や移動のsceneでは各cutのfirst frameが前cutの結果を受ける",
                "      cut_progression_map:",
                "        - cut_selector: scene10_cut01",
                "          progression_position: early_progress",
                "          first_frame_temporal_role: progressed_state_after_previous_cut",
                "          state_after_previous_cut: 前cutで扉へ近づいた",
                "          state_visible_in_this_cut: 扉の前で手が上がっている",
                "          must_not_revert_to: scene開始前の立ち位置へ戻らない",
                "          must_not_advance_beyond: このcutの扉前状態を越えない",
                "    cuts:",
                "      - cut_id: '01'",
                "        selector: scene10_cut01",
                "        cut_contract:",
                "          schema_version: '3.0'",
                "          cut_state_progression:",
                "            policy_version: cut_state_progression_v1",
                "            progression_mode: sequential_state_progression",
                "            cut_selector: scene10_cut01",
                "            progression_position: early_progress",
                "            first_frame_temporal_role: progressed_state_after_previous_cut",
                "            state_after_previous_cut: 前cutで扉へ近づいた",
                "            state_visible_in_first_frame: 扉の前で手が上がっている",
                "            visible_state_delta_from_previous_cut: 立ち位置と手の高さが変わる",
                "            must_not_revert_to: scene開始前の立ち位置へ戻らない",
                "            must_not_advance_beyond: このcutの扉前状態を越えない",
                "            done_when: [前cutから進んだ状態が一枚で読める]",
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
                "          api_prompt_payload:",
                "            policy_version: image_api_prompt_v1",
                "            prompt: |",
                "              [shot / 画角]",
                "              shot_role: character_action",
                "              shot_scale: medium",
                "",
                "              [この1枚に写る瞬間]",
                "              cut_visible_moment: 灰の台所でシンデレラが立つ",
                "",
                "              [前cutからの変化]",
                "              this_cut_delta: 灰の台所の姿勢が新しく見える",
                "",
                "              [人物の状態と配置]",
                "              hand_position: 両手が灰のついた服の前にある",
                "",
                "              [場所の使い方]",
                "              location_zone: 灰の台所の床と作業台",
                "",
                "              [小道具 / 物体]",
                "              object_contact_state: visible_not_touched",
                "            negative_prompt: text, logo",
                "            reference_images: [assets/characters/cinderella.png, assets/locations/kitchen.png]",
                "            sha256: test-sha",
                "            shot_design_contract:",
                "              shot_role: character_action",
                "              shot_scale: medium",
                "            cut_visual_delta:",
                "              this_cut_new_information: 灰の台所の姿勢が新しく見える",
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
            self.assertIn("shot_role: character_action", entry["prompt"])
            self.assertEqual(entry["legacy_prompt"], "灰の台所でシンデレラが立つ。画面内テキストなし。")
            self.assertEqual(entry["api_prompt_policy_version"], "image_api_prompt_v1")
            self.assertEqual(entry["story_time"], "17世紀フランス時代")
            self.assertEqual(entry["time_of_day"], "夜")
            self.assertTrue(entry["time_of_day_contract_declared"])
            self.assertEqual(entry["time_of_day_status"], "valid")
            self.assertEqual(entry["api_prompt_payload"]["negative_prompt"], "text, logo")
            self.assertEqual(entry["shot_design_contract"]["shot_role"], "character_action")
            self.assertEqual(entry["cut_visual_delta"]["this_cut_new_information"], "灰の台所の姿勢が新しく見える")
            self.assertEqual(entry["cut_assignment"]["cut_function"], "pressure")
            self.assertEqual(entry["scene_shot_mix_plan"]["shots"][0]["shot_scale"], "medium")
            self.assertEqual(entry["scene_film_coverage_plan"]["shot_mix"]["actual_shots"][0]["selector"], "scene10_cut01")
            self.assertEqual(entry["scene_state_progression_plan"]["progression_mode"], "sequential_state_progression")
            self.assertEqual(entry["cut_state_progression"]["state_visible_in_first_frame"], "扉の前で手が上がっている")
            self.assertIn("prompt_blocks", entry)
            self.assertIn("shot / 画角", entry["prompt_blocks"])
            self.assertIn("image_prompt_gate_focus", entry)
            self.assertIn("設計上の絵としての役割", "\n".join(entry["image_prompt_gate_focus"]))
            self.assertIn("scene state progression", "\n".join(entry["image_prompt_gate_focus"]))
            self.assertIn("story_time", "\n".join(entry["image_prompt_gate_focus"]))
            self.assertIn("time_of_day", "\n".join(entry["image_prompt_gate_focus"]))
            self.assertIn("first_frame_visual_plan", entry)
            self.assertEqual(entry["first_frame_visual_plan"]["schema_version"], "first_frame_visual_plan_v1")
            self.assertFalse(entry["first_frame_visual_plan"]["editable"])
            self.assertEqual(
                entry["first_frame_visual_plan"]["source_grounding"]["source_event_beat_id"],
                "scene10_event_pressure",
            )
            self.assertIn("temporal_boundary", entry["first_frame_visual_plan"])
            self.assertIn("motion_affordance", entry["first_frame_visual_plan"])
            self.assertEqual(entry["first_frame_visual_plan"]["scene_material_pack"]["time_of_day"], "夜")
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
            self.assertEqual(entry["cut_context_packet"]["schema_version"], "cut_context_packet_v1")
            self.assertFalse(entry["cut_context_packet"]["editable"])
            self.assertEqual(entry["cut_context_packet"]["cut_selector"], "scene10_cut01")
            self.assertEqual(entry["cut_context_packet"]["source_event"]["primary_event_beat"]["beat_id"], "scene10_event_pressure")
            self.assertIn("cut_context_packet_diagnostics", entry)
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
            self.assertEqual(composite["story_time"], "17世紀フランス時代")
            self.assertEqual(composite["time_of_day"], "夜")
            self.assertTrue(composite["time_of_day_contract_declared"])
            self.assertEqual(composite["time_of_day_status"], "valid")
            self.assertEqual(composite["scene_contract"]["time_of_day"], "夜")
            self.assertEqual(composite["cut_count"], 2)
            self.assertEqual(composite["scene_cut_coverage_plan"]["selected_cut_count"], 2)
            self.assertEqual(composite["story_event_obligations"][0]["event_id"], "scene01_story_event")
            self.assertEqual(composite["role_coverage"]["required_roles"], ["protagonist", "opponent"])
            self.assertNotIn("scene_event", composite["scene_contract"])
            self.assertEqual(composite["scene_event"]["schema_version"], "scene_event_v1")
            self.assertEqual(composite["scene_state_progression_plan"]["progression_mode"], "sequential_state_progression")
            self.assertEqual(composite["cut_entries"][0]["event_context_for_cut"]["primary_event_beat"]["beat_id"], "scene10_event_pressure")
            self.assertEqual(composite["cut_entries"][0]["source_event_contract"]["primary_event_beat_id"], "scene10_event_pressure")
            self.assertEqual(composite["cut_entries"][0]["cut_state_progression"]["progression_position"], "early_progress")
            self.assertEqual(composite["cut_entries"][0]["cut_context_packet"]["schema_version"], "cut_context_packet_v1")
            self.assertIn("cut_context_packet_diagnostics", composite["cut_entries"][0])
            self.assertIn("shot_role: character_action", composite["cut_entries"][0]["prompt"])
            self.assertEqual(composite["cut_entries"][0]["api_prompt_policy_version"], "image_api_prompt_v1")
            self.assertEqual(composite["cut_entries"][0]["time_of_day"], "夜")
            self.assertIn("time_of_day", "\n".join(composite["scene_composite_gate"]["must_judge"]))
            self.assertIn("image_prompt_time_of_day_mismatch", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("scene_cut_prompt_too_similar", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("event_beat_reference_integrity", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("audience_knowledge_delta_missing", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("role_coverage_missing", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("cut_visual_role_not_rendered_in_api_prompt", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("scene_film_coverage_not_visible_across_api_prompts", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("insert_or_reaction_needed_but_prompt_stays_medium_action", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("scene_state_progression_mode_wrong", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("cut_first_frame_reverts_to_scene_start", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("scene_progression_not_visible_across_api_prompts", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("scene_cut_coverage_plan", composite["scene_composite_gate"]["must_judge"][0])

    def test_collect_image_prompt_entries_defaults_missing_agent_review_to_false(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_semantic_pack_image_") as td:
            run_dir = Path(td)
            write_manifest(run_dir)
            manifest = load_manifest(run_dir / "video_manifest.md")
            image_generation = manifest["scenes"][0]["cuts"][0]["image_generation"]
            image_generation.pop("review", None)

            entries = collect_image_prompt_entries(manifest)

        self.assertFalse(entries[0]["review"]["agent_review_ok"])

    def test_collect_image_prompt_entries_exposes_v2_drawable_dependencies(self) -> None:
        manifest = {
            "scenes": [
                {
                    "scene_id": 10,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "still_image_plan": {"mode": "generate_still"},
                            "image_generation": {
                                "output": "assets/scenes/scene10_cut01.png",
                                "character_ids": [],
                                "object_ids": ["glass_slipper"],
                                "location_ids": [],
                                "references": [],
                                "api_prompt_payload": {
                                    "policy_version": "image_api_prompt_v2",
                                    "prompt": "実写映画調。前景のガラスの靴を大きく捉える。文字やロゴは入れない。",
                                    "drawable_prompt_ir": {
                                        "schema_version": "drawable_prompt_ir_v1",
                                        "dependencies": {
                                            "character_ids": [],
                                            "object_ids": ["glass_slipper"],
                                            "location_ids": [],
                                            "references": [],
                                        },
                                        "included_fragments": [
                                            {"group": "style", "text": "実写映画調。"},
                                            {"group": "current_moment", "text": "前景のガラスの靴。"},
                                            {"group": "primary_subject", "text": "主役はガラスの靴。"},
                                            {"group": "composition", "text": "前景へ大きく置く。"},
                                            {"group": "objects", "text": "透明なガラスの靴。"},
                                            {"group": "constraints", "text": "文字やロゴは入れない。"},
                                        ],
                                    },
                                },
                            },
                        }
                    ],
                }
            ]
        }

        entries = collect_image_prompt_entries(manifest)

        self.assertEqual(entries[0]["drawable_prompt_dependencies"]["object_ids"], ["glass_slipper"])
        self.assertNotIn("time_of_day", entries[0])
        self.assertFalse(entries[0]["time_of_day_contract_declared"])
        self.assertEqual(entries[0]["time_of_day_status"], "missing")
        self.assertEqual(
            entries[0]["included_drawable_fragment_groups"],
            ["style", "current_moment", "primary_subject", "composition", "objects", "constraints"],
        )
        projection_contract = entries[0]["prompt_projection_review_contract"]
        active_groups = {
            item["target_group"] for item in projection_contract["active_rules"]
        }
        self.assertIn("objects", active_groups)
        self.assertIn("current_moment", active_groups)
        inactive_groups = {
            item["target_group"] for item in projection_contract["inactive_rules"]
        }
        self.assertIn("composition", inactive_groups)
        self.assertTrue(projection_contract["invariant_principles"])

    def test_canonical_stored_visual_plan_is_exposed_without_masking_daypart_mismatch(self) -> None:
        manifest = {
            "video_metadata": {
                "time": "17世紀フランス時代",
                "scene_time_of_day_contract": "required_v1",
            },
            "scenes": [
                {
                    "scene_id": 10,
                    "time_of_day": "夜",
                    "cuts": [
                        {
                            "cut_id": 1,
                            "still_image_plan": {"mode": "generate_still"},
                            "first_frame_visual_plan": {
                                "scene_material_pack": {"time_of_day": "夕方"},
                            },
                            "image_generation": {
                                "output": "assets/scenes/scene10_cut01.png",
                                "first_frame_visual_plan": {
                                    "scene_material_pack": {"time_of_day": "朝"},
                                },
                            },
                        }
                    ],
                }
            ],
        }

        entry = collect_image_prompt_entries(manifest)[0]

        self.assertEqual(entry["time_of_day"], "夜")
        self.assertEqual(entry["first_frame_visual_plan"]["scene_material_pack"]["time_of_day"], "朝")
        self.assertEqual(entry["first_frame_visual_plan_status"], "canonical_valid")

    def test_v2_missing_empty_or_invalid_canonical_visual_plan_is_not_synthesized(self) -> None:
        cases = (
            ("missing", None, "canonical_missing"),
            ("empty", {}, "canonical_empty"),
            ("invalid", ["not", "a", "mapping"], "canonical_invalid_type"),
        )
        for label, canonical_plan, expected_status in cases:
            with self.subTest(label=label):
                image_generation = {
                    "output": "assets/scenes/scene10_cut01.png",
                    "api_prompt_payload": {"policy_version": "image_api_prompt_v2"},
                }
                if canonical_plan is not None:
                    image_generation["first_frame_visual_plan"] = canonical_plan
                manifest = {
                    "video_metadata": {
                        "time": "17世紀フランス時代",
                        "scene_time_of_day_contract": "required_v1",
                    },
                    "scenes": [
                        {
                            "scene_id": 10,
                            "time_of_day": "夜",
                            "cuts": [
                                {
                                    "cut_id": 1,
                                    "still_image_plan": {"mode": "generate_still"},
                                    "image_generation": image_generation,
                                }
                            ],
                        }
                    ],
                }

                entry = collect_image_prompt_entries(manifest)[0]

                self.assertEqual(entry["first_frame_visual_plan"], {})
                self.assertEqual(entry["first_frame_visual_plan_status"], expected_status)

    def test_v2_missing_canonical_provider_prompt_does_not_fallback_to_legacy_prompt(self) -> None:
        manifest = {
            "scenes": [
                {
                    "scene_id": 10,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "still_image_plan": {"mode": "generate_still"},
                            "image_generation": {
                                "prompt": "古いlegacy promptを使わない",
                                "api_prompt_payload": {
                                    "policy_version": "image_api_prompt_v2",
                                },
                            },
                        }
                    ],
                }
            ]
        }

        entry = collect_image_prompt_entries(manifest)[0]

        self.assertEqual(entry["prompt"], "")
        self.assertEqual(entry["legacy_prompt"], "古いlegacy promptを使わない")

    def test_legacy_scene_daypart_does_not_declare_required_contract_without_marker(self) -> None:
        manifest = {
            "video_metadata": {"time": "17世紀フランス時代"},
            "scenes": [
                {
                    "scene_id": 10,
                    "time_of_day": "夜",
                    "cuts": [
                        {
                            "cut_id": 1,
                            "still_image_plan": {"mode": "generate_still"},
                            "image_generation": {"output": "assets/scenes/scene10_cut01.png"},
                        }
                    ],
                }
            ],
        }

        entry = collect_image_prompt_entries(manifest)[0]

        self.assertFalse(entry["time_of_day_contract_declared"])
        self.assertEqual(entry["time_of_day"], "夜")
        self.assertEqual(entry["time_of_day_status"], "valid")

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
