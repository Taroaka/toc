import subprocess
import sys
import unittest
from pathlib import Path


class TestTocRunScaffold(unittest.TestCase):
    def test_scaffold_creates_expected_files(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_run_out_") as td:
            base = Path(td) / "out"
            base.mkdir(parents=True, exist_ok=True)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-run.py",
                    "テスト トピック",
                    "--dry-run",
                    "--timestamp",
                    "20990101_0000",
                    "--base",
                    str(base),
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
            self.assertTrue((run_dir / "assets" / "objects").is_dir())
            self.assertTrue((run_dir / "logs" / "grounding" / "research.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "story.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "script.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "image_prompt.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "video_generation.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "research.readset.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "research.audit.json").exists())


if __name__ == "__main__":
    unittest.main()
