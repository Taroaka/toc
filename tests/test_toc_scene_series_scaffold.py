import subprocess
import sys
import unittest
from pathlib import Path


class TestTocSceneSeriesScaffold(unittest.TestCase):
    def test_scaffold_creates_root_and_scene_grounding_artifacts(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_scene_series_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-scene-series.py",
                    "テスト トピック",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
                    "--dry-run",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            run_dir = base / "テスト_トピック_20990101_0000"
            self.assertTrue((run_dir / "state.txt").exists())
            self.assertTrue((run_dir / "series_plan.md").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "research.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "story.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "story.readset.json").exists())
            self.assertFalse((run_dir / "logs" / "grounding" / "story.audit.json").exists())
            self.assertTrue((run_dir / "scenes" / "scene01" / "evidence.md").exists())
            self.assertTrue((run_dir / "scenes" / "scene01" / "script.md").exists())
            self.assertTrue((run_dir / "scenes" / "scene01" / "video_manifest.md").exists())
            self.assertFalse((run_dir / "scenes" / "scene01" / "logs" / "grounding" / "narration.json").exists())
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertNotIn("review.", state)
            self.assertNotIn("eval.", state)
            self.assertNotIn("gate.video_review", state)


if __name__ == "__main__":
    unittest.main()
