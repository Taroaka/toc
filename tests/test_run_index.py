from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import subprocess
import sys

from toc.harness import sync_run_status
from toc.run_index import SLOT_BY_CODE, build_run_index_markdown, classify_run_file


REPO_ROOT = Path(__file__).resolve().parents[1]


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
            self.assertIn("current_position: `status=SCRIPT`", index_text)
            self.assertIn("next_required_human_review: `script.md`", index_text)
            self.assertIn("pending_gates: `script_review`", index_text)
            self.assertIn("`p740` | Narration / Audio Runtime Stage | `optional` | Duration Fit Gate", index_text)
            self.assertIn("#### p110 Research Grounding", index_text)
            self.assertIn("- requirement: `required`", index_text)
            self.assertIn("[transitional] `scene_outline_v3.md`", index_text)
            self.assertIn("[output] `assets/audio/scene01_cut01.mp3`", index_text)
            self.assertIn("[log] `logs/providers/scene01_image.json`", index_text)
            self.assertIn("[scratch] `scratch/note.txt`", index_text)

    def test_record_l2_supervisor_progress_updates_output_progress_only_for_l2(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_l2_progress_") as td:
            run_dir = Path(td) / "out" / "topic_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=進捗テスト\nstatus=INIT\n---\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "record-l2-supervisor-progress.py"),
                    "--run-dir",
                    str(run_dir),
                    "--bucket",
                    "p600",
                    "--event",
                    "invoked",
                    "--stop-slot",
                    "p680",
                    "--note",
                    "scene/image supervisor started",
                    "--at",
                    "2099-01-01T00:00:00+09:00",
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            progress_path = run_dir / "logs" / "orchestration" / "l2_supervisor_progress.md"
            result_path = run_dir / "logs" / "orchestration" / "p600.supervisor_result.json"
            result_path.write_text('{"bucket":"p600","status":"done"}\n', encoding="utf-8")

            returned = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "record-l2-supervisor-progress.py"),
                    "--run-dir",
                    str(run_dir),
                    "--bucket",
                    "p600",
                    "--event",
                    "returned",
                    "--stop-slot",
                    "p680",
                    "--result",
                    "logs/orchestration/p600.supervisor_result.json",
                    "--note",
                    "scene/image supervisor completed",
                    "--at",
                    "2099-01-01T00:01:00+09:00",
                ],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(returned.returncode, 0, msg=returned.stderr)
            progress_text = progress_path.read_text(encoding="utf-8")
            self.assertIn("Only L2 P-Bucket Supervisor invocations are recorded here", progress_text)
            self.assertIn("| 2099-01-01T00:00:00+09:00 | p600 | p600 P-Bucket Supervisor | invoked | p680 | - | scene/image supervisor started |", progress_text)
            self.assertIn(
                "| 2099-01-01T00:01:00+09:00 | p600 | p600 P-Bucket Supervisor | returned | p680 | logs/orchestration/p600.supervisor_result.json | scene/image supervisor completed |",
                progress_text,
            )
            state_text = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertIn("orchestration.p600.supervisor.call_status=returned", state_text)
            self.assertIn("orchestration.p600.supervisor.status=done", state_text)
            self.assertIn("orchestration.p600.supervisor.finished_at=2099-01-01T00:01:00+09:00", state_text)
            self.assertIn("orchestration.p600.supervisor.result=logs/orchestration/p600.supervisor_result.json", state_text)
            self.assertIn("orchestration.p600.supervisor.progress=logs/orchestration/l2_supervisor_progress.md", state_text)
            index_text = (run_dir / "p000_index.md").read_text(encoding="utf-8")
            self.assertIn("[log] `logs/orchestration/l2_supervisor_progress.md`", index_text)
            self.assertIn("[log] `logs/orchestration/p600.supervisor_result.json`", index_text)

            entry = classify_run_file("logs/orchestration/l2_supervisor_progress.md", run_dir=run_dir)
            self.assertEqual(entry.slot, "p010")
            self.assertEqual(entry.role, "log")
            result_entry = classify_run_file("logs/orchestration/p600.supervisor_result.json", run_dir=run_dir)
            self.assertEqual(result_entry.slot, "p600")
            self.assertEqual(result_entry.role, "log")

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
            self.assertEqual(grounding_entry.slot, "p710")
            self.assertEqual(state_entry.slot, "p930")
            self.assertIn("scene subrun", grounding_entry.note)

    def test_current_position_uses_runtime_progress_before_pending_review_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_run_index_position_") as td:
            run_dir = Path(td) / "out" / "topic_20990101_0000"
            run_dir.mkdir(parents=True)
            (run_dir / "story.md").write_text("# story\n", encoding="utf-8")
            (run_dir / "visual_value.md").write_text("# visual\n", encoding="utf-8")

            index_text = build_run_index_markdown(
                run_dir,
                state={
                    "runtime.stage": "P300",
                    "status": "P300",
                    "stage.story.status": "awaiting_approval",
                    "gate.story_review": "required",
                    "review.story.status": "pending",
                },
            )

            self.assertIn("current_position: `runtime.stage=P300`", index_text)
            self.assertIn("next_required_human_review: `story.md`", index_text)
            self.assertIn("pending_gates: `story_review`", index_text)

    def test_review_slot_labels_mention_improvement_loop(self) -> None:
        review_slots = ("p130", "p230", "p320", "p430", "p540", "p630", "p640", "p720", "p820", "p850", "p930")

        for slot_code in review_slots:
            with self.subTest(slot=slot_code):
                self.assertIn("Improve Loop", SLOT_BY_CODE[slot_code].title)
