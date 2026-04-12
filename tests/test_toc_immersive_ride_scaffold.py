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
            self.assertTrue((run_dir / "logs" / "grounding" / "image_prompt.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "video_generation.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "script.readset.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "script.audit.json").exists())
            manifest = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
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
            self.assertIn('experience: "cloud_island_walk"', manifest)
            self.assertIn("一人称POVで前進しながら歩く", manifest)
            self.assertIn("画面内テキスト", manifest)


if __name__ == "__main__":
    unittest.main()
