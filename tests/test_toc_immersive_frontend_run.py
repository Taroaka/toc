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
            self.assertEqual(state["review.image_prompt.judgment.entry_count"], "24")
            for stage in ("scene_set", "scene_detail", "cut_blueprint", "asset_plan", "asset_output", "image_prompt", "scene_image"):
                self.assertEqual(state[f"review.semantic.{stage}.status"], "pending")
                self.assertIn(f"review.semantic.{stage}.entry_count", state)
            scope = json.loads((run_dir / "logs/review/image_prompt.review_scope.json").read_text(encoding="utf-8"))
            self.assertEqual(scope["entry_count"], 24)
            generic_scope = json.loads((run_dir / "logs/review/semantic/image_prompt.scope.json").read_text(encoding="utf-8"))
            self.assertEqual(generic_scope["entry_count"], 24)

            asset_request_text = (run_dir / "asset_generation_requests.md").read_text(encoding="utf-8")
            self.assertGreaterEqual(len(re.findall(r"^##\s+", asset_request_text, flags=re.MULTILINE)), 10)
            self.assertIn("location_reference", asset_request_text)
            self.assertIn("人物なし、空の部屋、場所だけ", asset_request_text)
            self.assertIn("主要人物、全身ポートレート", asset_request_text)

            scene_request_text = (run_dir / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("[cut契約からの可視要件]", scene_request_text)
            self.assertIn("初期状態:", scene_request_text)
            self.assertNotIn("motion_brief:", scene_request_text)
            first_scene = scene_request_text.split("## scene10_cut2", 1)[0]
            self.assertIn("assets/characters/cinderella_fullbody.png", first_scene)
            self.assertIn("assets/locations/", first_scene)
            self.assertNotIn("glass_slipper", first_scene)
            self.assertNotIn("ガラスの靴", first_scene)

            transformation_scene = scene_request_text.split("## scene30_cut1", 1)[1].split("## scene30_cut2", 1)[0]
            self.assertIn("reference_count: `3`", transformation_scene)
            self.assertIn("glass_slipper", transformation_scene)

            palace_stair_scene = scene_request_text.split("## scene50_cut1", 1)[1].split("## scene50_cut2", 1)[0]
            self.assertIn("宮殿の階段", palace_stair_scene)
            self.assertIn("location_05", palace_stair_scene)
            self.assertNotIn("location_01", palace_stair_scene)

            ballroom_scene = scene_request_text.split("## scene60_cut1", 1)[1].split("## scene60_cut2", 1)[0]
            self.assertIn("舞踏会の大広間", ballroom_scene)
            self.assertIn("location_06", ballroom_scene)
            self.assertNotIn("location_02", ballroom_scene)

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
            self.assertIn("桃太郎", request_text)
            self.assertNotIn("cinderella_fullbody", request_text)
            self.assertNotIn("glass_slipper", request_text)
            self.assertNotIn("シンデレラ", request_text)

            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["eval.p400_readiness.status"], "approved")
            self.assertEqual(state["stage.scene_implementation.grounding.status"], "ready")
