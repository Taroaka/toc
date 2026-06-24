import subprocess
import sys
import tempfile
import unittest
import re
import json
import importlib.util
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_frontend_run_module():
    spec = importlib.util.spec_from_file_location(
        "toc_immersive_frontend_run_under_test",
        REPO_ROOT / "scripts" / "toc-immersive-frontend-run.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_state(path: Path) -> dict[str, str]:
    state: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line == "---" or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        state[key.strip()] = value.strip()
    return state


class TestTocImmersiveFrontendRun(unittest.TestCase):
    def test_same_topic_runs_do_not_reuse_cinderella_scaffold_or_identical_prompts(self) -> None:
        module = load_frontend_run_module()
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="frontend_run_repeat_a_", dir=output_root) as tmp_a, tempfile.TemporaryDirectory(prefix="frontend_run_repeat_b_", dir=output_root) as tmp_b:
            run_a = Path(tmp_a)
            run_b = Path(tmp_b)

            module.materialize_run("シンデレラ", "シンデレラ", run_a, "p650")
            module.materialize_run("シンデレラ", "シンデレラ", run_b, "p650")

            request_a = (run_a / "image_generation_requests.md").read_text(encoding="utf-8")
            request_b = (run_b / "image_generation_requests.md").read_text(encoding="utf-8")
            manifest_a = (run_a / "video_manifest.md").read_text(encoding="utf-8")
            manifest_b = (run_b / "video_manifest.md").read_text(encoding="utf-8")
            combined = "\n".join(
                [
                    request_a,
                    request_b,
                    manifest_a,
                    manifest_b,
                    (run_a / "research.md").read_text(encoding="utf-8"),
                    (run_a / "story.md").read_text(encoding="utf-8"),
                    (run_a / "asset_generation_requests.md").read_text(encoding="utf-8"),
                    (run_b / "research.md").read_text(encoding="utf-8"),
                    (run_b / "story.md").read_text(encoding="utf-8"),
                    (run_b / "asset_generation_requests.md").read_text(encoding="utf-8"),
                ]
            )

        self.assertNotIn("cinderella_fullbody", combined)
        self.assertNotIn("cinderella_transformed_fullbody", combined)
        self.assertNotIn("cinderella_post_midnight_fullbody", combined)
        self.assertNotIn("glass_slipper", combined)
        self.assertNotIn("pumpkin_carriage", combined)
        self.assertNotIn("prince_dance_partner", combined)
        self.assertNotIn("ガラスの靴", combined)
        self.assertNotIn("靴合わせ", combined)
        self.assertNotIn("舞踏会", combined)
        self.assertNotIn("王子", combined)
        self.assertNotEqual(request_a, request_b)
        self.assertNotEqual(manifest_a, manifest_b)
        self.assertIn("run_variant:", manifest_a)
        self.assertIn("run_variant:", manifest_b)

    def test_cut_design_failure_writes_context_log_and_state(self) -> None:
        module = load_frontend_run_module()
        original_coverage_plan = module._scene_cut_coverage_plan
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="frontend_run_failure_", dir=output_root) as tmp:
            run_dir = Path(tmp)

            def fail_coverage_plan(*args, **kwargs):
                raise RuntimeError("synthetic cut design failure")

            module._scene_cut_coverage_plan = fail_coverage_plan
            try:
                with self.assertRaisesRegex(RuntimeError, "synthetic cut design failure"):
                    module.materialize_run("シンデレラ", "シンデレラ", run_dir, "p650")
            finally:
                module._scene_cut_coverage_plan = original_coverage_plan

            latest_context_path = run_dir / "logs" / "scene_design" / "latest_generation_context.json"
            failure_path = run_dir / "logs" / "scene_design" / "cut_contract_failure.json"
            self.assertTrue(latest_context_path.exists())
            self.assertTrue(failure_path.exists())
            latest_context = json.loads(latest_context_path.read_text(encoding="utf-8"))
            failure = json.loads(failure_path.read_text(encoding="utf-8"))
            self.assertEqual(latest_context["schema_version"], "cut_design_generation_context_v1")
            self.assertEqual(latest_context["phase"], "scene_cut_coverage_planning")
            self.assertEqual(latest_context["scene_context"]["scene_id"], 10)
            self.assertEqual(failure["schema_version"], "cut_design_failure_v1")
            self.assertEqual(failure["phase"], "build_script_and_manifest")
            self.assertEqual(failure["error"]["type"], "RuntimeError")
            self.assertIn("synthetic cut design failure", failure["error"]["message"])
            self.assertIn("scene_event_input", failure["partial_artifacts"])

            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["runtime.stage"], "cut_design_failed")
            self.assertEqual(state["runtime.cut_design.status"], "failed")
            self.assertEqual(state["runtime.cut_design.failure_log"], "logs/scene_design/cut_contract_failure.json")
            self.assertEqual(state["slot.p420.status"], "failed")

    def test_materialize_only_reaches_frontend_p680_text_contract(self) -> None:
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="frontend_run_", dir=output_root) as tmp:
            run_dir = Path(tmp)

            completed = subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-frontend-run.py",
                    "--topic",
                    "シンデレラ",
                    "--source",
                    "シンデレラ",
                    "--run-dir",
                    str(run_dir),
                    "--stop-target",
                    "p680",
                    "--materialize-only",
                    "--skip-validation",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                env={**os.environ, "TOC_ENABLE_LEGACY_CINDERELLA_PROFILE": "1"},
                check=True,
            )

            self.assertIn("Stop target: p680", completed.stdout)
            for name in (
                "research.md",
                "story.md",
                "visual_value.md",
                "script.md",
                "video_manifest.md",
                "image_prompt_story_review.md",
                "logs/review/image_prompt.review_collection.md",
                "logs/review/image_prompt.review_scope.json",
                "logs/review/image_prompt.judgment_prompt.md",
                "logs/review/image_prompt.judgment.md",
                "logs/review/semantic/scene_set.collection.md",
                "logs/review/semantic/scene_detail.collection.md",
                "logs/review/semantic/cut_blueprint.collection.md",
                "logs/review/semantic/asset_plan.collection.md",
                "logs/review/semantic/image_prompt.collection.md",
                "logs/scene_design/scene_event_input.json",
                "logs/scene_design/scene_event_output.json",
                "asset_generation_requests.md",
                "asset_generation_manifest.md",
                "image_generation_requests.md",
                "video_generation_requests.md",
                "p000_index.md",
            ):
                self.assertGreater((run_dir / name).stat().st_size, 80, name)
            self.assertIn(
                "除外対象はありません。",
                (run_dir / "generation_exclusion_report.md").read_text(encoding="utf-8"),
            )

            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["eval.p400_readiness.status"], "approved")
            self.assertEqual(state["stage.asset.grounding.status"], "ready")
            self.assertEqual(state["stage.scene_implementation.grounding.status"], "ready")
            self.assertEqual(state["slot.p650.status"], "done")
            self.assertNotIn("slot.p660.status", state)
            self.assertNotIn("slot.p680.status", state)
            self.assertEqual(state["review.image.status"], "pending")
            self.assertEqual(state["gate.image_review"], "required")
            self.assertEqual(state["review.image_prompt.judgment.status"], "pending")
            self.assertEqual(state["review.semantic.asset_plan.entry_count"], "14")
            for stage in ("scene_set", "scene_detail", "cut_blueprint", "asset_plan", "image_prompt"):
                self.assertEqual(state[f"review.semantic.{stage}.status"], "pending")
                self.assertIn(f"review.semantic.{stage}.entry_count", state)
            self.assertNotIn("review.semantic.asset_output.status", state)
            self.assertNotIn("review.semantic.scene_image.status", state)
            scope = json.loads((run_dir / "logs/review/image_prompt.review_scope.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(scope["entry_count"], 40)
            self.assertEqual(state["review.image_prompt.judgment.entry_count"], str(scope["entry_count"]))
            generic_scope = json.loads((run_dir / "logs/review/semantic/image_prompt.scope.json").read_text(encoding="utf-8"))
            self.assertEqual(generic_scope["entry_count"], scope["entry_count"])
            scene_event_input = json.loads((run_dir / "logs/scene_design/scene_event_input.json").read_text(encoding="utf-8"))
            scene_event_output = json.loads((run_dir / "logs/scene_design/scene_event_output.json").read_text(encoding="utf-8"))
            self.assertEqual(scene_event_input["schema_version"], "scene_event_log_v1")
            self.assertEqual(scene_event_output["schema_version"], "scene_event_log_v1")
            self.assertEqual(scene_event_input["scene_count"], scene_event_output["scene_count"])
            self.assertEqual(scene_event_output["scenes"][0]["scene_event"]["schema_version"], "scene_event_v1")
            self.assertIn("source_event_contract", scene_event_output["scenes"][0]["cut_contracts"][0])
            self.assertIn("event_context_for_cut", scene_event_output["scenes"][0]["cut_contracts"][0])
            self.assertIn("cut_context_packet", scene_event_output["scenes"][0]["cut_contracts"][0])
            self.assertEqual(scene_event_output["scenes"][0]["cut_contracts"][0]["cut_context_packet"]["schema_version"], "cut_context_packet_v1")
            self.assertFalse(scene_event_output["scenes"][0]["cut_contracts"][0]["cut_context_packet"]["editable"])

            asset_request_text = (run_dir / "asset_generation_requests.md").read_text(encoding="utf-8")
            self.assertGreaterEqual(len(re.findall(r"^##\s+", asset_request_text, flags=re.MULTILINE)), 10)
            self.assertIn("location_reference", asset_request_text)
            self.assertIn("人物なし、空の部屋、場所だけ", asset_request_text)
            self.assertIn("主要人物、全身ポートレート", asset_request_text)
            self.assertIn("pumpkin_carriage", asset_request_text)
            self.assertIn("prince_dance_partner", asset_request_text)
            self.assertIn("cinderella_transformed_fullbody", asset_request_text)
            self.assertIn("cinderella_post_midnight_fullbody", asset_request_text)
            self.assertIn("参照画像が渡される場合は、その人物の顔・髪・体格・年齢感を同一人物として維持", asset_request_text)
            transformed_asset_section = re.search(
                r"## scene\d+\n(?:(?!\n## scene).)*asset_id: `cinderella_transformed_fullbody`(?:(?!\n## scene).)*",
                asset_request_text,
                re.DOTALL,
            ).group(0)
            post_midnight_asset_section = re.search(
                r"## scene\d+\n(?:(?!\n## scene).)*asset_id: `cinderella_post_midnight_fullbody`(?:(?!\n## scene).)*",
                asset_request_text,
                re.DOTALL,
            ).group(0)
            self.assertIn("assets/characters/cinderella_fullbody.png", transformed_asset_section)
            self.assertIn("assets/characters/cinderella_fullbody.png", post_midnight_asset_section)
            self.assertIn("舞踏会ドレスではない質素な衣装だけに戻す", post_midnight_asset_section)
            gate_road_section = re.search(
                r"## scene\d+\n(?:(?!\n## scene).)*asset_id: `location_04_location_04_78c27f`(?:(?!\n## scene).)*",
                asset_request_text,
                re.DOTALL,
            ).group(0)
            self.assertIn("深夜のみ", gate_road_section)
            self.assertIn("昼光なし", gate_road_section)
            self.assertIn("太陽なし", gate_road_section)
            self.assertIn("明るい青空", gate_road_section)
            midnight_stair_section = re.search(
                r"## scene\d+\n(?:(?!\n## scene).)*asset_id: `location_07_location_07_def6a5`(?:(?!\n## scene).)*",
                asset_request_text,
                re.DOTALL,
            ).group(0)
            self.assertIn("ガラスの靴なし", midnight_stair_section)
            self.assertIn("物語固有の小道具", midnight_stair_section)
            self.assertIn("ロゴ、マーク、署名、ウォーターマーク", midnight_stair_section)

            scene_request_text = (run_dir / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertNotIn("[cut契約からの可視要件]", scene_request_text)
            self.assertIn("- prompt_policy_version: `image_api_prompt_v1`", scene_request_text)
            self.assertIn("```debug_prompt_source", scene_request_text)
            self.assertIn("```api_prompt", scene_request_text)
            self.assertNotIn("```text\n[参照画像の使い方]", scene_request_text)
            self.assertIn("[shot / 画角]", scene_request_text)
            self.assertIn("shot_role:", scene_request_text)
            self.assertIn("location_zone:", scene_request_text)
            self.assertIn("this_cut_delta:", scene_request_text)
            self.assertIn("[動画開始に向いた静止状態]", scene_request_text)
            self.assertNotIn("観客理解の増分:", scene_request_text)
            self.assertNotIn("因果の証明:", scene_request_text)
            self.assertNotIn("必要な役割:", scene_request_text)
            self.assertNotIn("motion_brief:", scene_request_text)
            first_scene = scene_request_text.split("## scene10_cut2", 1)[0]
            first_api_prompt = re.search(r"```api_prompt\n(?P<body>.*?)\n```", first_scene, re.DOTALL).group("body")
            self.assertIn("assets/characters/cinderella_fullbody.png", first_scene)
            self.assertIn("assets/locations/", first_scene)
            self.assertNotIn("glass_slipper", first_api_prompt)
            self.assertNotIn("event_time_position:", first_api_prompt)
            self.assertNotIn("not_yet_happened_in_still:", first_api_prompt)
            self.assertNotIn("first_frame_visual_plan", first_api_prompt)
            self.assertIn("[禁止]", first_api_prompt)
            self.assertIn("ガラスの靴", first_scene)
            self.assertNotRegex(first_api_prompt, r"^.*ガラスの靴.*$", re.MULTILINE)
            manifest_text = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            self.assertIn("scene_cut_coverage_plan:", manifest_text)
            self.assertIn("scene_shot_mix_plan:", manifest_text)
            self.assertIn("api_prompt_payload:", manifest_text)
            self.assertIn("scene_obligations:", manifest_text)
            self.assertIn("story_event_obligations:", manifest_text)
            self.assertIn("audience_knowledge_delta:", manifest_text)
            self.assertIn("causal_proof:", manifest_text)
            self.assertIn("role_coverage:", manifest_text)
            self.assertIn("visual_evidence:", manifest_text)
            self.assertIn("source_event_contract:", manifest_text)
            self.assertIn("event_context_for_cut:", manifest_text)
            self.assertIn("cut_context_packet:", manifest_text)
            self.assertIn("schema_version: cut_context_packet_v1", manifest_text)
            self.assertIn("editable: false", manifest_text)
            self.assertIn("scene_state_progression_plan:", manifest_text)
            self.assertIn("cut_state_progression:", manifest_text)
            self.assertNotIn("assigned_story_event_ids:", manifest_text)
            self.assertIn("static_first_frame_rule:", manifest_text)
            self.assertIn("must_be_static_evidence_not_motion: true", manifest_text)
            self.assertIn("coverage_obligation_id:", manifest_text)
            self.assertIn("scene10_cut04", scene_request_text)
            self.assertNotIn("scene10_cut05", scene_request_text)
            self.assertIn("scene30_cut06", scene_request_text)
            self.assertIn("scene70_cut08", scene_request_text)
            self.assertIn("symbolic_proof", manifest_text)
            self.assertIn("reaction_after_change", manifest_text)
            self.assertNotIn("reveal_protection", manifest_text)
            self.assertIn("time_or_deadline_pressure", manifest_text)
            scene70_text = scene_request_text.split("## scene70_cut1", 1)[1].split("## scene80_cut1", 1)[0]
            post_loss_scene70 = scene_request_text.split("## scene70_cut8", 1)[1].split("## scene80_cut1", 1)[0]
            self.assertIn("ガラスの靴", scene70_text)
            self.assertIn("脱げて階段に残", scene70_text)
            self.assertIn("逃走", scene70_text)
            self.assertIn("cinderella_post_midnight_fullbody", post_loss_scene70)
            pre_loss_scene70 = scene_request_text.split("## scene70_cut5", 1)[1].split("## scene70_cut6", 1)[0]
            self.assertIn("cinderella_transformed_fullbody", pre_loss_scene70)
            self.assertIn("costume: 舞踏会ドレス姿を維持し、質素な普段着へ戻さない。", pre_loss_scene70)
            self.assertIn("costume: 魔法が解けた後の質素な衣装を維持し、舞踏会ドレスへ戻さない。", post_loss_scene70)
            scene70_manifest = manifest_text.split("scene_id: 70", 1)[1].split("scene_id: 80", 1)[0]
            self.assertIn("source_event_contract:", scene70_manifest)
            self.assertIn("event_context_for_cut:", scene70_manifest)
            self.assertIn("cut_contract.source_event_contract", scene70_manifest)

            transformation_scene = scene_request_text.split("## scene30_cut1", 1)[1].split("## scene30_cut2", 1)[0]
            self.assertIn("reference_count: `2`", transformation_scene)
            self.assertNotIn("glass_slipper", transformation_scene)
            transformation_reveal = scene_request_text.split("## scene30_cut3", 1)[1].split("## scene30_cut4", 1)[0]
            self.assertIn("glass_slipper", transformation_reveal)
            self.assertIn("object_visibility: ガラスの靴", transformation_reveal)
            self.assertIn("cinderella_transformed_fullbody", transformation_reveal)

            departure_scene = scene_request_text.split("## scene40_cut1", 1)[1].split("## scene50_cut1", 1)[0]
            self.assertIn("pumpkin_carriage", departure_scene)
            self.assertIn("馬車", departure_scene)
            self.assertNotIn("ガラスの靴はこのsceneでは見せない", departure_scene)
            scene40_manifest = manifest_text.split("scene_id: 40", 1)[1].split("scene_id: 50", 1)[0]
            self.assertIn("progression_mode: sequential_state_progression", scene40_manifest)
            self.assertIn("first_frame_temporal_role: progressed_state_after_previous_cut", scene40_manifest)
            self.assertNotIn("not_yet_happened_in_still:\n                  - scene04_event_turn", scene40_manifest)
            departure_pressure = scene_request_text.split("## scene40_cut1", 1)[1].split("## scene40_cut2", 1)[0]
            departure_proof = scene_request_text.split("## scene40_cut3", 1)[1].split("## scene40_cut4", 1)[0]
            departure_late = scene_request_text.split("## scene40_cut4", 1)[1].split("## scene40_cut5", 1)[0]
            self.assertNotIn("glass_slipper", departure_pressure)
            self.assertIn("pumpkin_carriage", departure_proof)
            self.assertIn("馬車", departure_late)
            self.assertIn("progressed_state", departure_late)
            self.assertNotIn("still_must_not_show: 行為完了後、後続reveal、次場面の結果。", departure_late)

            palace_stair_scene = scene_request_text.split("## scene50_cut3", 1)[1].split("## scene50_cut4", 1)[0]
            self.assertIn("宮殿の階段", palace_stair_scene)
            self.assertIn("location_05", palace_stair_scene)
            self.assertNotIn("location_01", palace_stair_scene)
            palace_pressure = scene_request_text.split("## scene50_cut1", 1)[1].split("## scene50_cut2", 1)[0]
            self.assertNotIn("glass_slipper", palace_pressure)

            ballroom_scene = scene_request_text.split("## scene60_cut3", 1)[1].split("## scene60_cut4", 1)[0]
            self.assertIn("舞踏会の大広間", ballroom_scene)
            self.assertIn("location_06", ballroom_scene)
            self.assertIn("prince_dance_partner", ballroom_scene)
            self.assertNotIn("location_02", ballroom_scene)
            ballroom_pressure = scene_request_text.split("## scene60_cut1", 1)[1].split("## scene60_cut2", 1)[0]
            self.assertNotIn("glass_slipper", ballroom_pressure)

            final_scene_manifest = re.split(r"\n-\s+scene_id:\s+'?80'?", manifest_text, maxsplit=1)[1]
            self.assertIn("物語を閉じる", final_scene_manifest)
            self.assertIn("終結", final_scene_manifest)
            self.assertIn("靴合わせが行われる部屋", final_scene_manifest)
            self.assertIn("ガラスの靴", final_scene_manifest)
            self.assertIn("主人公の価値を証明", final_scene_manifest)
            self.assertIn("出口ではなくシンデレラとガラスの靴へ収束する", final_scene_manifest)
            self.assertIn("carries_to_next_scene: []", final_scene_manifest)
            self.assertNotIn("次の場所へ進む証拠が生まれる", final_scene_manifest)
            self.assertNotIn("背景に次の場所へ続く導線", final_scene_manifest)

            final_scene_requests = scene_request_text.split("## scene80_cut1", 1)[1]
            self.assertIn("cinderella_post_midnight_fullbody", final_scene_requests)
            self.assertNotIn("cinderella_transformed_fullbody", final_scene_requests)
            self.assertNotIn("背景に次の場所へ続く導線", final_scene_requests)
            self.assertIn("costume: 魔法が解けた後の質素な衣装を維持し、舞踏会ドレスへ戻さない。", final_scene_requests)
            self.assertIn("object_visibility: ガラスの靴", final_scene_requests)
            self.assertIn("靴合わせが行われる部屋", final_scene_requests)
            self.assertNotIn("月光、ガラス、階段", final_scene_requests)

            video_request_text = (run_dir / "video_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("cut_contract:", video_request_text)
            self.assertIn("motion_brief:", video_request_text)

            prompt_text = (run_dir / "logs/eval/asset/round_01/prompts/critic_1.prompt.md").read_text(encoding="utf-8")
            self.assertIn("You are critic_1 in the ToC Asset Eval/Improve Loop", prompt_text)
            aggregate_text = (run_dir / "logs/eval/asset/round_01/aggregated_review.md").read_text(encoding="utf-8")
            self.assertIn("## Blocking Findings", aggregate_text)
            self.assertIn("Root Cause Review", aggregate_text)

            forbidden = ("TODO", "TBD", "REPLACE_ME", "placeholder")
            for name in (
                "research.md",
                "story.md",
                "script.md",
                "asset_generation_requests.md",
                "image_generation_requests.md",
                "video_generation_requests.md",
            ):
                text = (run_dir / name).read_text(encoding="utf-8")
                self.assertFalse(any(marker in text for marker in forbidden), name)

    def test_materialize_only_uses_topic_profile_instead_of_cinderella_scaffold(self) -> None:
        output_root = REPO_ROOT / "output"
        output_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="frontend_run_generic_", dir=output_root) as tmp:
            run_dir = Path(tmp)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-frontend-run.py",
                    "--topic",
                    "桃太郎",
                    "--source",
                    "桃から生まれた主人公が仲間と鬼のいる島へ向かう民話。",
                    "--run-dir",
                    str(run_dir),
                    "--stop-target",
                    "p680",
                    "--materialize-only",
                    "--skip-validation",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=True,
            )

            request_text = "\n".join(
                [
                    (run_dir / "asset_generation_requests.md").read_text(encoding="utf-8"),
                    (run_dir / "image_generation_requests.md").read_text(encoding="utf-8"),
                    (run_dir / "video_generation_requests.md").read_text(encoding="utf-8"),
                    (run_dir / "video_manifest.md").read_text(encoding="utf-8"),
                ]
            )
            self.assertIn("cut_contract:", request_text)
            self.assertIn("source_event_contract:", request_text)
            self.assertIn("event_context_for_cut:", request_text)
            self.assertIn("first_frame_contract:", request_text)
            self.assertIn("motion_contract:", request_text)
            self.assertIn("story_event_obligations:", request_text)
            self.assertIn("audience_knowledge_delta:", request_text)
            self.assertIn("causal_proof:", request_text)
            self.assertIn("scene_character_state_timeline:", request_text)
            self.assertIn("scene_film_coverage_plan:", request_text)
            self.assertIn("scene_state_progression_plan:", request_text)
            self.assertIn("cut_character_emotion_transition:", request_text)
            self.assertIn("cut_film_grammar_contract:", request_text)
            self.assertIn("cut_state_progression:", request_text)
            self.assertIn("[人物の見える演技]", request_text)
            self.assertIn("表情は、", request_text)
            self.assertIn("視線は、", request_text)
            self.assertIn("姿勢は、", request_text)
            self.assertIn("人物と圧力源の距離は、", request_text)
            self.assertNotIn("観客理解の増分:", request_text)
            self.assertNotIn("因果の証明:", request_text)
            self.assertNotIn("静止画ルール:", request_text)
            self.assertIn("桃太郎", request_text)
            self.assertNotIn("cinderella_fullbody", request_text)
            self.assertNotIn("glass_slipper", request_text)
            self.assertNotIn("シンデレラ", request_text)

            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["eval.p400_readiness.status"], "approved")
            self.assertEqual(state["stage.scene_implementation.grounding.status"], "ready")
