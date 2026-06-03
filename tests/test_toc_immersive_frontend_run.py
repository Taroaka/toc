import subprocess
import sys
import tempfile
import unittest
import re
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


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
                "logs/review/semantic/asset_output.collection.md",
                "logs/review/semantic/image_prompt.collection.md",
                "logs/review/semantic/scene_image.collection.md",
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
            self.assertEqual(state["review.image_prompt.judgment.entry_count"], "58")
            self.assertEqual(state["review.semantic.asset_plan.entry_count"], "14")
            for stage in ("scene_set", "scene_detail", "cut_blueprint", "asset_plan", "asset_output", "image_prompt", "scene_image"):
                self.assertEqual(state[f"review.semantic.{stage}.status"], "pending")
                self.assertIn(f"review.semantic.{stage}.entry_count", state)
            scope = json.loads((run_dir / "logs/review/image_prompt.review_scope.json").read_text(encoding="utf-8"))
            self.assertEqual(scope["entry_count"], 58)
            generic_scope = json.loads((run_dir / "logs/review/semantic/image_prompt.scope.json").read_text(encoding="utf-8"))
            self.assertEqual(generic_scope["entry_count"], 58)

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
            self.assertIn("[cut契約からの可視要件]", scene_request_text)
            self.assertIn("初期状態:", scene_request_text)
            self.assertIn("観客理解の増分:", scene_request_text)
            self.assertIn("因果の証明:", scene_request_text)
            self.assertIn("画面に置く証拠:", scene_request_text)
            self.assertIn("必要な役割:", scene_request_text)
            self.assertIn("静止画ルール:", scene_request_text)
            self.assertNotIn("motion_brief:", scene_request_text)
            first_scene = scene_request_text.split("## scene10_cut2", 1)[0]
            self.assertIn("assets/characters/cinderella_fullbody.png", first_scene)
            self.assertIn("assets/locations/", first_scene)
            self.assertNotIn("glass_slipper", first_scene)
            self.assertNotIn("ガラスの靴", first_scene)
            manifest_text = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            self.assertIn("scene_cut_coverage_plan:", manifest_text)
            self.assertIn("scene_obligations:", manifest_text)
            self.assertIn("story_event_obligations:", manifest_text)
            self.assertIn("audience_knowledge_delta:", manifest_text)
            self.assertIn("causal_proof:", manifest_text)
            self.assertIn("role_coverage:", manifest_text)
            self.assertIn("visual_evidence:", manifest_text)
            self.assertIn("assigned_story_event_ids:", manifest_text)
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
            pre_loss_scene70 = scene_request_text.split("## scene70_cut5", 1)[1].split("## scene70_cut6", 1)[0]
            loss_scene70 = scene_request_text.split("## scene70_cut6", 1)[1].split("## scene70_cut7", 1)[0]
            post_loss_scene70 = scene_request_text.split("## scene70_cut7", 1)[1].split("## scene70_cut8", 1)[0]
            self.assertNotIn("階段に残るガラスの靴", pre_loss_scene70)
            self.assertIn("階段に残るガラスの靴", loss_scene70)
            self.assertIn("cinderella_post_midnight_fullbody", post_loss_scene70)
            self.assertIn("このsceneの前半6cutまでは舞踏会ドレス姿", pre_loss_scene70)
            self.assertIn("質素な服、普段着、魔法が解けた後の服を出さない", pre_loss_scene70)
            self.assertIn("後半の反応cut以降だけ、魔法が解けた後の質素な服へ変わる", post_loss_scene70)

            transformation_scene = scene_request_text.split("## scene30_cut1", 1)[1].split("## scene30_cut2", 1)[0]
            self.assertIn("reference_count: `2`", transformation_scene)
            self.assertNotIn("glass_slipper", transformation_scene)
            transformation_reveal = scene_request_text.split("## scene30_cut3", 1)[1].split("## scene30_cut4", 1)[0]
            self.assertIn("ガラスの靴の初出", transformation_reveal)
            self.assertIn("glass_slipper", transformation_reveal)
            self.assertIn("cinderella_transformed_fullbody", transformation_reveal)

            departure_scene = scene_request_text.split("## scene40_cut1", 1)[1].split("## scene50_cut1", 1)[0]
            self.assertIn("glass_slipper", departure_scene)
            self.assertIn("pumpkin_carriage", departure_scene)
            self.assertIn("馬車へ乗り込み", departure_scene)
            self.assertNotIn("ガラスの靴はこのsceneでは見せない", departure_scene)
            departure_pressure = scene_request_text.split("## scene40_cut1", 1)[1].split("## scene40_cut2", 1)[0]
            departure_proof = scene_request_text.split("## scene40_cut3", 1)[1].split("## scene40_cut4", 1)[0]
            self.assertNotIn("glass_slipper", departure_pressure)
            self.assertIn("glass_slipper", departure_proof)

            palace_stair_scene = scene_request_text.split("## scene50_cut3", 1)[1].split("## scene50_cut4", 1)[0]
            self.assertIn("宮殿の階段", palace_stair_scene)
            self.assertIn("location_05", palace_stair_scene)
            self.assertIn("glass_slipper", palace_stair_scene)
            self.assertNotIn("location_01", palace_stair_scene)
            palace_pressure = scene_request_text.split("## scene50_cut1", 1)[1].split("## scene50_cut2", 1)[0]
            self.assertNotIn("glass_slipper", palace_pressure)

            ballroom_scene = scene_request_text.split("## scene60_cut3", 1)[1].split("## scene60_cut4", 1)[0]
            self.assertIn("舞踏会の大広間", ballroom_scene)
            self.assertIn("location_06", ballroom_scene)
            self.assertIn("glass_slipper", ballroom_scene)
            self.assertIn("prince_dance_partner", ballroom_scene)
            self.assertNotIn("location_02", ballroom_scene)
            ballroom_pressure = scene_request_text.split("## scene60_cut1", 1)[1].split("## scene60_cut2", 1)[0]
            self.assertNotIn("glass_slipper", ballroom_pressure)

            final_scene_manifest = re.split(r"\n-\s+scene_id:\s+'?80'?", manifest_text, maxsplit=1)[1]
            self.assertIn("物語を閉じる", final_scene_manifest)
            self.assertIn("終結", final_scene_manifest)
            self.assertIn("靴合わせの動作", final_scene_manifest)
            self.assertIn("足に合うガラスの靴", final_scene_manifest)
            self.assertIn("出口ではなくシンデレラとガラスの靴へ収束する", final_scene_manifest)
            self.assertIn("carries_to_next_scene: []", final_scene_manifest)
            self.assertNotIn("次の場所へ進む証拠が生まれる", final_scene_manifest)
            self.assertNotIn("背景に次の場所へ続く導線", final_scene_manifest)

            final_scene_requests = scene_request_text.split("## scene80_cut1", 1)[1]
            self.assertIn("出口ではなくシンデレラとガラスの靴へ収束する", final_scene_requests)
            self.assertIn("cinderella_post_midnight_fullbody", final_scene_requests)
            self.assertNotIn("cinderella_transformed_fullbody", final_scene_requests)
            self.assertNotIn("背景に次の場所へ続く導線", final_scene_requests)
            self.assertIn("落ち着いた室内光", final_scene_requests)
            self.assertIn("椅子と床", final_scene_requests)
            self.assertIn("靴合わせの部屋では魔法が解けた後の質素な服", final_scene_requests)
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
            self.assertIn("first_frame_contract:", request_text)
            self.assertIn("motion_contract:", request_text)
            self.assertIn("story_event_obligations:", request_text)
            self.assertIn("audience_knowledge_delta:", request_text)
            self.assertIn("causal_proof:", request_text)
            self.assertIn("観客理解の増分:", request_text)
            self.assertIn("因果の証明:", request_text)
            self.assertIn("静止画ルール:", request_text)
            self.assertIn("桃太郎", request_text)
            self.assertNotIn("cinderella_fullbody", request_text)
            self.assertNotIn("glass_slipper", request_text)
            self.assertNotIn("シンデレラ", request_text)

            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["eval.p400_readiness.status"], "approved")
            self.assertEqual(state["stage.scene_implementation.grounding.status"], "ready")
