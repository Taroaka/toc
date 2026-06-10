import subprocess
import sys
import unittest
import json
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
            self.assertFalse((run_dir / "logs" / "grounding" / "asset.json").exists())
            self.assertFalse((run_dir / "logs" / "grounding" / "scene_implementation.json").exists())
            self.assertFalse((run_dir / "logs" / "grounding" / "narration.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "research.readset.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "research.audit.json").exists())
            scene_event_input = json.loads((run_dir / "logs" / "scene_design" / "scene_event_input.json").read_text(encoding="utf-8"))
            scene_event_output = json.loads((run_dir / "logs" / "scene_design" / "scene_event_output.json").read_text(encoding="utf-8"))
            latest_context = json.loads((run_dir / "logs" / "scene_design" / "latest_generation_context.json").read_text(encoding="utf-8"))
            self.assertEqual(scene_event_input["schema_version"], "scene_event_log_v1")
            self.assertEqual(scene_event_output["schema_version"], "scene_event_log_v1")
            self.assertEqual(latest_context["schema_version"], "cut_design_generation_context_v1")
            self.assertEqual(scene_event_input["flow"], "toc-run")
            self.assertEqual(scene_event_output["status"], "not_generated")
            self.assertEqual(latest_context["flow"], "toc-run")
            self.assertEqual(latest_context["status"], "not_generated")
            self.assertEqual(latest_context["phase"], "cut_design_not_started")
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertNotIn("eval.p400_readiness.status=approved", state)
            self.assertIn("runtime.cut_design.status=not_generated", state)
            self.assertIn("runtime.cut_design.latest_context=logs/scene_design/latest_generation_context.json", state)
            manifest = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            self.assertRegex(manifest, r'manifest_phase:\s*"?skeleton"?')


if __name__ == "__main__":
    unittest.main()
