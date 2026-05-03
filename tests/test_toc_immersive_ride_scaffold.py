import subprocess
import sys
import unittest
from pathlib import Path


class TestTocImmersiveRideScaffold(unittest.TestCase):
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

    def test_scaffold_accepts_numeric_stage_target(self) -> None:
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

    def test_scaffold_numeric_p400_stops_after_script(self) -> None:
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
            self.assertFalse((run_dir / "video_manifest.md").exists())
            self.assertFalse((run_dir / "logs" / "grounding" / "narration.json").exists())
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertIn("runtime.stage_target=p400", state)

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
            self.assertIn("runtime.stage_target=p450", state)


if __name__ == "__main__":
    unittest.main()
