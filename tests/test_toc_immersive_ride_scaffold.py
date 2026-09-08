from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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


class TestTocImmersiveRideScaffold(unittest.TestCase):
    def run_scaffold(
        self,
        base: Path,
        stage: str,
        *,
        experience: str = "cloud_island_walk",
        source_run: Path | None = None,
        force: bool = True,
        skip_grounding: bool = False,
    ) -> Path:
        command = [
            sys.executable,
            str(SCRIPT_PATH),
            "--topic",
            "テスト トピック",
            "--timestamp",
            "20990101_0000",
            "--base",
            str(base),
            "--stage",
            stage,
            "--experience",
            experience,
        ]
        if source_run is not None:
            command.extend(["--source-run", str(source_run)])
        if force:
            command.append("--force")
        if skip_grounding:
            with mock.patch.object(sys, "argv", [command[1], *command[2:]]), mock.patch.object(
                TOC_IMMERSIVE_RIDE, "maybe_run_stage_grounding"
            ):
                TOC_IMMERSIVE_RIDE.main()
        else:
            subprocess.run(command, cwd=REPO_ROOT, check=True, capture_output=True, text=True)
        return base / "テスト_トピック_20990101_0000"

    def assert_no_review_state(self, run_dir: Path) -> None:
        state = parse_state(run_dir / "state.txt")
        self.assertFalse([key for key in state if key.startswith("review.")])
        self.assertFalse([key for key in state if key.startswith("eval.")])
        self.assertFalse(
            [key for key in state if key.startswith("gate.") and "review" in key]
        )
        self.assertFalse((run_dir / "logs" / "review").exists())
        self.assertFalse((run_dir / "logs" / "eval").exists())

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

    def test_scaffold_creates_expected_files_without_review_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            run_dir = self.run_scaffold(
                Path(td) / "out",
                "p400",
                experience="cinematic_story",
                skip_grounding=True,
            )
            for relative in (
                "p000_index.md",
                "state.txt",
                "run_status.json",
                "research.md",
                "story.md",
                "visual_value.md",
                "script.md",
                "video_manifest.md",
            ):
                self.assertTrue((run_dir / relative).exists(), relative)
            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["status"], "P400")
            self.assertEqual(state["runtime.stop_slot"], "p450")
            self.assertEqual(state["stage.script.status"], "pending")
            self.assertEqual(state["slot.p450.status"], "pending")
            self.assertIn("manifest_phase: skeleton", (run_dir / "video_manifest.md").read_text(encoding="utf-8"))
            self.assert_no_review_state(run_dir)

    def test_early_authoring_targets_do_not_materialize_review_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            run_dir = self.run_scaffold(Path(td) / "out", "p100", experience="cinematic_story")
            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["status"], "P100")
            self.assertEqual(state["slot.p120.status"], "pending")
            self.assertNotIn("slot.p130.status", state)
            self.assertTrue((run_dir / "research.md").is_file())
            self.assert_no_review_state(run_dir)

    def test_scaffold_world_walk_requires_source_run(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--topic",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(Path(td) / "out"),
                    "--experience",
                    "world_walk",
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--source-run", result.stderr)

    def test_scaffold_world_walk_binds_source_receipt(self) -> None:
        output_root = REPO_ROOT / "output"
        output_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="toc_world_walk_source_", dir=output_root) as source_td, tempfile.TemporaryDirectory(prefix="toc_test_out_") as td:
            root = Path(td)
            source_run = Path(source_td)
            (source_run / "story.md").write_text("# source\n", encoding="utf-8")
            (source_run / "assets" / "characters").mkdir(parents=True)
            output = root / "out"
            run_dir = self.run_scaffold(
                output,
                "p100",
                experience="world_walk",
                source_run=source_run,
            )
            state = parse_state(run_dir / "state.txt")
            self.assertEqual(state["immersive.experience"], "world_walk")
            self.assertTrue((run_dir / "logs" / "provenance" / "world_walk_source_receipt.json").is_file())
            self.assert_no_review_state(run_dir)

    def test_scaffold_rejects_timestamp_traversal_without_writing_outside_base(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_ride_timestamp_") as td:
            root = Path(td)
            base = root / "output"
            base.mkdir()
            escaped = root / "escaped"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--topic",
                    "test",
                    "--timestamp",
                    "../../../escaped",
                    "--base",
                    str(base),
                    "--stage",
                    "p100",
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("timestamp", result.stderr.lower())
            self.assertFalse(escaped.exists())
            self.assertEqual(list(base.iterdir()), [])

    def test_scaffold_rejects_run_dir_outside_base(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_ride_run_dir_") as td:
            root = Path(td)
            base = root / "output"
            base.mkdir()
            escaped = root / "escaped"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--topic",
                    "test",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--run-dir",
                    str(escaped),
                    "--stage",
                    "p100",
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--run-dir", result.stderr)
            self.assertFalse(escaped.exists())
            self.assertEqual(list(base.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
