from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from toc.harness import sync_run_status


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
            self.assertIn("`p630` | Image Stage | `optional` | Hard Image Review", index_text)
            self.assertIn("#### p110 Research Grounding", index_text)
            self.assertIn("- requirement: `required`", index_text)
            self.assertIn("[transitional] `scene_outline_v3.md`", index_text)
            self.assertIn("[output] `assets/audio/scene01_cut01.mp3`", index_text)
            self.assertIn("[log] `logs/providers/scene01_image.json`", index_text)
            self.assertIn("[scratch] `scratch/note.txt`", index_text)
