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
                "    scene_cut_coverage_plan:",
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
                "        still_image_plan:",
                "          mode: generate_still",
                "          rationale: 導入の静止画",
                "        scene_contract:",
                "          target_beat: 灰の台所の導入",
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
            self.assertIn("scene_cut_prompt_too_similar", composite["scene_composite_gate"]["failure_reason_keys"])
            self.assertIn("scene_cut_coverage_plan", composite["scene_composite_gate"]["must_judge"][0])

    def test_collect_scene_image_entries_includes_outputs_logs_and_contact_sheet(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_semantic_pack_image_") as td:
            run_dir = Path(td)
            write_manifest(run_dir)
            write_asset_plan(run_dir)
            output_path = run_dir / "assets" / "scenes" / "scene10_cut01.png"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"\x89PNG\r\n\x1a\n")
            contact_sheet = run_dir / "logs" / "review" / "semantic" / "scene_image.contact_sheet.md"
            contact_sheet.parent.mkdir(parents=True, exist_ok=True)
            contact_sheet.write_text("# Contact Sheet\n", encoding="utf-8")
            log_path = run_dir / "logs" / "app_server" / "image_gen" / "scene10_cut01.json"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                json.dumps(
                    {
                        "destination": "assets/scenes/scene10_cut01.png",
                        "savedPath": "/tmp/generated/scene10_cut01.png",
                        "source": "codex_builtin_image",
                        "status": "completed",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            entries = collect_entries("scene_image", run_dir)

            self.assertEqual(len(entries), 3)
            first = entries[0]
            self.assertEqual(first["stage"], "scene_image")
            self.assertEqual(first["review_scope"], "all_entries")
            self.assertEqual(first["selector"], "scene10_cut01")
            self.assertTrue(first["output_exists"])
            self.assertEqual(
                first["final_output_provenance"],
                {
                    "declared_output": "assets/scenes/scene10_cut01.png",
                    "resolved_output_path": str(output_path.resolve()),
                    "output_exists": True,
                    "saved_path": "/tmp/generated/scene10_cut01.png",
                    "source": "codex_builtin_image",
                    "status": "completed",
                    "debug_log": "logs/app_server/image_gen/scene10_cut01.json",
                },
            )
            self.assertEqual(first["generated_image_path"], "/tmp/generated/scene10_cut01.png")
            self.assertEqual(first["generation_source"], "codex_builtin_image")
            self.assertEqual(first["debug_log"], "logs/app_server/image_gen/scene10_cut01.json")
            self.assertTrue(first["contact_sheet_required"])
            self.assertFalse(first["contact_sheet_missing"])
            self.assertEqual(first["contact_sheet_refs"], ["logs/review/semantic/scene_image.contact_sheet.md"])
            self.assertEqual(first["semantic_contract"]["must_include"], ["シンデレラ", "灰の台所"])
            self.assertFalse(first["semantic_contract_missing"])
            second = entries[1]
            self.assertEqual(second["selector"], "scene10_cut02")
            self.assertFalse(second["output_exists"])
            self.assertEqual(second["review_scope"], "all_entries")
            self.assertTrue(second["semantic_contract_missing"])
            self.assertEqual(second["contract_required_fields_missing"], ["target_focus", "must_include", "done_when"])
            composite = entries[2]
            self.assertEqual(composite["review_scope"], "scene_composite")
            self.assertEqual(composite["stage"], "scene_image")
            self.assertIn("scene_cut_coverage_plan", composite)
            self.assertEqual(composite["cut_entries"][0]["image_output_exists"], True)
            self.assertEqual(composite["cut_entries"][1]["image_output_exists"], False)

    def test_collect_scene_image_entries_marks_missing_contact_sheet(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_semantic_pack_image_") as td:
            run_dir = Path(td)
            write_manifest(run_dir)

            entries = collect_entries("scene_image", run_dir)

            self.assertTrue(entries[0]["contact_sheet_required"])
            self.assertTrue(entries[0]["contact_sheet_missing"])
            self.assertEqual(entries[0]["contact_sheet_refs"], [])

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
