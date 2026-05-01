from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from toc.harness import sync_run_status
from toc.run_index import classify_run_file


class TestRunIndex(unittest.TestCase):
    def test_sync_run_status_writes_p000_index_and_classifies_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_run_index_") as td:
            run_dir = Path(td) / "out" / "topic_20990101_0000"
            (run_dir / "assets" / "audio").mkdir(parents=True, exist_ok=True)
            (run_dir / "logs" / "providers").mkdir(parents=True, exist_ok=True)
            (run_dir / "scratch").mkdir(parents=True, exist_ok=True)

            (run_dir / "research.md").write_text("# research\n", encoding="utf-8")
            (run_dir / "story.md").write_text("# story\n", encoding="utf-8")
            (run_dir / "scene_outline_v3.md").write_text("# outline\n", encoding="utf-8")
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            (run_dir / "assets" / "audio" / "scene01_cut01.mp3").write_bytes(b"audio")
            (run_dir / "logs" / "providers" / "scene01_image.json").write_text("{}", encoding="utf-8")
            (run_dir / "scratch" / "note.txt").write_text("scratch", encoding="utf-8")
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "timestamp=2099-01-01T00:00:00+09:00",
                        "job_id=JOB_2099-01-01_000000",
                        "topic=同期テスト",
                        "status=SCRIPT",
                        "stage.research.status=done",
                        "stage.story.status=done",
                        "stage.script.status=awaiting_approval",
                        "gate.script_review=required",
                        "review.script.status=pending",
                        "---",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            sync_run_status(run_dir)

            index_text = (run_dir / "p000_index.md").read_text(encoding="utf-8")
            self.assertIn("current_position: `p400 Script / Narration Text / Human Changes / awaiting script human review`", index_text)
            self.assertIn("next_required_human_review: `script.md`", index_text)
            self.assertIn("`p540` | Narration / Audio Runtime Stage | `optional` | Duration Fit Gate", index_text)
            self.assertIn("#### p110 Research Grounding", index_text)
            self.assertIn("- requirement: `required`", index_text)
            self.assertIn("[transitional] `scene_outline_v3.md`", index_text)
            self.assertIn("[output] `assets/audio/scene01_cut01.mp3`", index_text)
            self.assertIn("[log] `logs/providers/scene01_image.json`", index_text)
            self.assertIn("[scratch] `scratch/note.txt`", index_text)

    def test_classify_scene_series_nested_files_with_scene_subrun_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_run_index_scene_series_") as td:
            run_dir = Path(td) / "out" / "series_20990101_0000"
            scene_dir = run_dir / "scenes" / "scene01"
            (scene_dir / "logs" / "grounding").mkdir(parents=True, exist_ok=True)
            (scene_dir / "video_manifest.md").write_text(
                "# Manifest\n\n```yaml\nmanifest_phase: skeleton\nscenes: []\n```\n",
                encoding="utf-8",
            )
            (scene_dir / "script.md").write_text("# scene script\n", encoding="utf-8")
            (scene_dir / "state.txt").write_text("topic=scene01\n---\n", encoding="utf-8")
            (scene_dir / "logs" / "grounding" / "narration.json").write_text("{}", encoding="utf-8")

            script_entry = classify_run_file("scenes/scene01/script.md", run_dir=run_dir)
            manifest_entry = classify_run_file("scenes/scene01/video_manifest.md", run_dir=run_dir)
            grounding_entry = classify_run_file("scenes/scene01/logs/grounding/narration.json", run_dir=run_dir)
            state_entry = classify_run_file("scenes/scene01/state.txt", run_dir=run_dir)

            self.assertEqual(script_entry.slot, "p420")
            self.assertEqual(manifest_entry.slot, "p450")
            self.assertEqual(grounding_entry.slot, "p510")
            self.assertEqual(state_entry.slot, "p930")
            self.assertIn("scene subrun", grounding_entry.note)
