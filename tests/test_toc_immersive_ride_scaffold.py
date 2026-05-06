import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "toc-immersive-ride.py"
SPEC = importlib.util.spec_from_file_location("toc_immersive_ride", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
TOC_IMMERSIVE_RIDE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOC_IMMERSIVE_RIDE)


def parse_state(state_path: Path) -> dict[str, str]:
    state: dict[str, str] = {}
    for raw in state_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line == "---" or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        state[key.strip()] = value.strip()
    return state


def markdown_section(text: str, heading: str) -> str:
    start = text.index(heading)
    next_heading = text.find("\n### ", start + len(heading))
    if next_heading == -1:
        return text[start:]
    return text[start:next_heading]


def markdown_subsection(text: str, heading: str) -> str:
    start = text.index(heading)
    next_heading = text.find("\n#### ", start + len(heading))
    next_stage = text.find("\n### ", start + len(heading))
    candidates = [index for index in (next_heading, next_stage) if index != -1]
    end = min(candidates) if candidates else len(text)
    return text[start:end]


class TestTocImmersiveRideScaffold(unittest.TestCase):
    def test_stage_target_contract_normalizes_big_stages_to_handoff_slots(self) -> None:
        cases = {
            "p100": "p130",
            "100": "p130",
            "p300": "p330",
            "300": "p330",
            "p400": "p450",
            "400": "p450",
            "p600": "p680",
            "600": "p680",
            "p700": "p750",
            "700": "p750",
            "p800": "p850",
            "800": "p850",
            "p900": "p930",
            "900": "p930",
        }

        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(TOC_IMMERSIVE_RIDE.normalize_stage_target(raw), expected)

    def test_stage_target_contract_keeps_fine_slots_exact(self) -> None:
        for slot in ("p110", "p130", "p310", "p320", "p330", "p450", "p570"):
            with self.subTest(slot=slot):
                self.assertEqual(TOC_IMMERSIVE_RIDE.normalize_stage_target(slot), slot)

    def test_scaffold_creates_expected_files(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--experience",
                    "cinematic_story",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "p000_index.md").exists())
            self.assertTrue((run_dir / "state.txt").exists())
            self.assertTrue((run_dir / "run_status.json").exists())
            self.assertTrue((run_dir / "research.md").exists())
            self.assertTrue((run_dir / "story.md").exists())
            self.assertTrue((run_dir / "visual_value.md").exists())
            self.assertTrue((run_dir / "script.md").exists())
            self.assertTrue((run_dir / "video_manifest.md").exists())
            self.assertTrue((run_dir / "assets" / "characters").is_dir())
            self.assertTrue((run_dir / "assets" / "objects").is_dir())
            self.assertTrue((run_dir / "assets" / "scenes").is_dir())
            self.assertTrue((run_dir / "assets" / "audio").is_dir())
            self.assertTrue((run_dir / "logs" / "grounding" / "research.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "story.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "script.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "narration.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "script.readset.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "script.audit.json").exists())
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertIn("status=DONE", state)
            self.assertIn("runtime.stage=immersive_ride_scaffolded", state)
            parsed_state = parse_state(run_dir / "state.txt")
            self.assertEqual(parsed_state["stage.narration.status"], "awaiting_approval")
            self.assertEqual(parsed_state["review.narration.status"], "pending")
            self.assertEqual(parsed_state["runtime.scaffold.narration_status"], "pending")
            self.assertEqual(parsed_state["runtime.scaffold.audio_status"], "pending")
            self.assertEqual(parsed_state["slot.p510.status"], "pending")
            self.assertEqual(parsed_state["slot.p530.status"], "pending")
            index_text = (run_dir / "p000_index.md").read_text(encoding="utf-8")
            p500_section = markdown_section(index_text, "### p500 Narration / Audio Runtime Stage")
            p510_section = markdown_subsection(index_text, "#### p510 Narration Grounding")
            self.assertIn("- current_state: `awaiting_approval (narration)`", p500_section)
            self.assertIn("- status: `pending`", p510_section)
            manifest = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            self.assertIn("manifest_phase: skeleton", manifest)
            self.assertIn('reference_id: "protagonist_front_ref"', manifest)
            self.assertIn("全身（頭からつま先まで）", manifest)
            self.assertIn("scene_id: 10", manifest)

    def test_scaffold_cloud_island_experience_uses_template(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--experience",
                    "cloud_island_walk",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            manifest_path = run_dir / "video_manifest.md"
            self.assertTrue(manifest_path.exists())
            manifest = manifest_path.read_text(encoding="utf-8")
            self.assertIn("manifest_phase: skeleton", manifest)
            self.assertIn('experience: "cloud_island_walk"', manifest)
            self.assertIn("一人称POVで前進しながら歩く", manifest)
            self.assertIn("画面内テキスト", manifest)

    def test_scaffold_accepts_numeric_p300_stage_target_as_visual_handoff(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "300",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "research.md").exists())
            self.assertTrue((run_dir / "story.md").exists())
            self.assertTrue((run_dir / "visual_value.md").exists())
            self.assertFalse((run_dir / "script.md").exists())
            self.assertFalse((run_dir / "video_manifest.md").exists())
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertIn("runtime.stage_target=p300", state)
            self.assertIn("runtime.stop_slot=p330", state)
            parsed_state = parse_state(run_dir / "state.txt")
            self.assertEqual(parsed_state["runtime.scaffold.status"], "draft")
            self.assertEqual(parsed_state["runtime.scaffold.content_status"], "placeholder")
            self.assertEqual(parsed_state["stage.research.status"], "pending")
            self.assertEqual(parsed_state["stage.story.status"], "pending")
            self.assertEqual(parsed_state["stage.visual_value.status"], "awaiting_approval")
            self.assertEqual(parsed_state["review.visual_value.status"], "pending")
            self.assertEqual(parsed_state["slot.p120.status"], "pending")
            self.assertEqual(parsed_state["slot.p220.status"], "pending")
            self.assertEqual(parsed_state["slot.p310.status"], "pending")
            self.assertEqual(parsed_state["slot.p320.status"], "pending")
            self.assertEqual(parsed_state["slot.p330.status"], "pending")
            self.assertEqual(parsed_state["artifact.visual_value.status"], "scaffold")
            self.assertEqual(parsed_state["eval.visual_value.loop.status"], "pending")
            self.assertEqual(parsed_state["eval.visual_value.loop.current_round"], "0")
            self.assertEqual(parsed_state["eval.visual_value.loop.max_rounds"], "5")
            self.assertTrue((run_dir / "logs" / "eval" / "visual_value" / "round_01" / "prompts" / "critic_1.prompt.md").exists())
            self.assertTrue((run_dir / "logs" / "eval" / "visual_value" / "round_01" / "prompts" / "aggregator.prompt.md").exists())
            index_text = (run_dir / "p000_index.md").read_text(encoding="utf-8")
            self.assertIn("next_required_human_review: `visual_value.md", index_text)
            self.assertIn("#### p310 Visual Value", index_text)
            self.assertIn("#### p320 Visual Planning Eval/Improve Loop", index_text)
            self.assertIn("#### p330 Visual Planning Appendix", index_text)

    def test_scaffold_accepts_prefixed_numeric_stage_target(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "p300",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "visual_value.md").exists())
            self.assertFalse((run_dir / "script.md").exists())
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertIn("runtime.stage_target=p300", state)
            self.assertIn("runtime.stop_slot=p330", state)

    def test_scaffold_stage_targets_record_placeholder_authoring_status(self) -> None:
        import tempfile

        expectations = {
            "100": {
                "stage.research.status": "awaiting_approval",
                "review.research.status": "pending",
                "slot.p120.status": "pending",
                "slot.p130.status": "pending",
                "artifact.research.status": "scaffold",
            },
            "200": {
                "stage.research.status": "pending",
                "stage.story.status": "awaiting_approval",
                "review.story.status": "pending",
                "slot.p120.status": "pending",
                "slot.p220.status": "pending",
                "slot.p230.status": "pending",
                "artifact.story.status": "scaffold",
            },
        }
        for stage, expected in expectations.items():
            with self.subTest(stage=stage):
                with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
                    base = Path(td) / "out"
                    base.mkdir(parents=True, exist_ok=True)

                    subprocess.run(
                        [
                            sys.executable,
                            "scripts/toc-immersive-ride.py",
                            "--topic",
                            "テスト トピック",
                            "--timestamp",
                            "20990101_0000",
                            "--base",
                            str(base),
                            "--stage",
                            stage,
                            "--force",
                            "--review-policy",
                            "drafts",
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )

                    run_dir = base / "テスト_トピック_20990101_0000"
                    state = parse_state(run_dir / "state.txt")
                    self.assertEqual(state["runtime.scaffold.status"], "draft")
                    self.assertEqual(state["runtime.scaffold.content_status"], "placeholder")
                    for key, value in expected.items():
                        self.assertEqual(state[key], value)

    def test_scaffold_numeric_p400_stops_at_script_handoff_slot(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "400",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "script.md").exists())
            self.assertTrue((run_dir / "video_manifest.md").exists())
            self.assertFalse((run_dir / "logs" / "grounding" / "narration.json").exists())
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertIn("runtime.stage_target=p400", state)
            self.assertIn("runtime.stop_slot=p450", state)

    def test_scaffold_script_stage_stops_before_narration(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "script",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "video_manifest.md").exists())
            self.assertFalse((run_dir / "logs" / "grounding" / "narration.json").exists())
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertIn("runtime.stage_target=p400", state)
            self.assertIn("runtime.stop_slot=p450", state)

    def test_scaffold_p500_records_pending_narration_and_audio_state(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-immersive-ride.py",
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--stage",
                    "p500",
                    "--force",
                    "--review-policy",
                    "drafts",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "logs" / "grounding" / "narration.json").exists())
            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["runtime.stage_target"], "p500")
            self.assertEqual(state["runtime.stop_slot"], "p570")
            self.assertEqual(state["stage.narration.status"], "awaiting_approval")
            self.assertEqual(state["review.narration.status"], "pending")
            self.assertEqual(state["runtime.scaffold.narration_status"], "pending")
            self.assertEqual(state["runtime.scaffold.audio_status"], "pending")
            self.assertEqual(state["slot.p510.status"], "pending")
            self.assertEqual(state["slot.p530.status"], "pending")
            index_text = (run_dir / "p000_index.md").read_text(encoding="utf-8")
            p500_section = markdown_section(index_text, "### p500 Narration / Audio Runtime Stage")
            p510_section = markdown_subsection(index_text, "#### p510 Narration Grounding")
            p530_section = markdown_subsection(index_text, "#### p530 TTS Request / Generation")
            self.assertIn("- current_state: `awaiting_approval (narration)`", p500_section)
            self.assertIn("- status: `pending`", p510_section)
            self.assertIn("- status: `pending`", p530_section)

    def test_later_coarse_targets_record_matching_handoff_state(self) -> None:
        import tempfile

        cases = {
            "p600": {
                "runtime.stage_target": "p600",
                "runtime.stop_slot": "p680",
                "stage.asset.status": "awaiting_approval",
                "review.asset.status": "pending",
                "gate.asset_review": "required",
                "slot.p680.status": "pending",
                "artifact": "asset_plan.md",
            },
            "p700": {
                "runtime.stage_target": "p700",
                "runtime.stop_slot": "p750",
                "stage.scene_implementation.status": "awaiting_approval",
                "review.image_prompt.status": "pending",
                "gate.image_prompt_review": "required",
                "slot.p750.status": "pending",
                "artifact": "image_generation_requests.md",
            },
            "p800": {
                "runtime.stage_target": "p800",
                "runtime.stop_slot": "p850",
                "stage.video_generation.status": "awaiting_approval",
                "review.video.status": "pending",
                "gate.video_review": "required",
                "slot.p850.status": "pending",
                "artifact": "video_generation_requests.md",
            },
            "p900": {
                "runtime.stage_target": "p900",
                "runtime.stop_slot": "p930",
                "stage.qa.status": "awaiting_approval",
                "review.video.status": "pending",
                "gate.video_review": "required",
                "slot.p930.status": "pending",
                "artifact": "run_report.md",
            },
        }

        for stage, expected in cases.items():
            with self.subTest(stage=stage), tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
                base = Path(td) / "out"
                base.mkdir(parents=True, exist_ok=True)

                subprocess.run(
                    [
                        sys.executable,
                        "scripts/toc-immersive-ride.py",
                        "--topic",
                        "テスト トピック",
                        "--timestamp",
                        "20990101_0000",
                        "--base",
                        str(base),
                        "--stage",
                        stage,
                        "--force",
                        "--review-policy",
                        "drafts",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )

                run_dir = base / "テスト_トピック_20990101_0000"
                state = parse_state(run_dir / "state.txt")
                for key, value in expected.items():
                    if key == "artifact":
                        continue
                    self.assertEqual(state[key], value)
                self.assertTrue((run_dir / expected["artifact"]).exists())


if __name__ == "__main__":
    unittest.main()
