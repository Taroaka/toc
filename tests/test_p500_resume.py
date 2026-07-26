from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import toc.p500_resume as p500_resume
from toc.harness import parse_state_file
from toc.p500_resume import (
    P500ResumeError,
    apply_resume_plan,
    build_resume_plan,
    resolve_run_dir,
)
from toc.runtime_locks import sync_file_lock


class P500ResumeTests(unittest.TestCase):
    def _resume_cli_module(self):
        path = Path(__file__).resolve().parents[1] / "scripts" / "resume-from-p500.py"
        spec = importlib.util.spec_from_file_location("resume_from_p500_test", path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _run_fixture(self, root: Path) -> Path:
        run_dir = root / "output" / "sample_20260725_1200"
        run_dir.mkdir(parents=True)
        canonical = {
            "research.md": "research-current\n",
            "story.md": "story-current\n",
            "visual_value.md": "visual-current\n",
            "script.md": "script-current\n",
            "video_manifest.md": "manifest-current\n",
            "p000_index.md": "index-current\n",
            "state.txt": "\n".join(
                [
                    "topic=sample",
                    "status=P680",
                    "eval.p400_readiness.status=approved",
                    "slot.p520.status=done",
                    "review.semantic.asset_plan.status=passed",
                    "runtime.create_job.status=failed",
                    "runtime.failure.stage=asset_plan",
                    "runtime.app_server.transport.status=failed",
                    "review.semantic.create_failure_count=2",
                    "artifact.asset_plan=asset_plan.md",
                    "---",
                    "",
                ]
            ),
        }
        for rel, text in canonical.items():
            (run_dir / rel).write_text(text, encoding="utf-8")

        downstream = {
            "asset_plan.md": "old asset plan\n",
            "asset_generation_request_snapshot.json": "{}\n",
            "image_generation_request_snapshot.json": "{}\n",
            "assets/characters/hero.png": "old image bytes\n",
            "assets/scenes/scene01_cut01.png": "old scene bytes\n",
            "logs/review/semantic/asset_plan.report.md": "old report\n",
            "logs/orchestration/p500.supervisor_result.json": "{}\n",
            "logs/image_generation_jobs/completed.json": (
                '{"jobId":"completed","status":"completed"}\n'
            ),
            "logs/image_generation_prompts.jsonl": "{}\n",
            "logs/app_server/semantic.log": "old runtime log\n",
            "logs/render/final.log": "old render log\n",
            "thumbnails/final.png": "old thumbnail\n",
            "final.mp4": "old render bytes\n",
            "run_report.md": "old report\n",
        }
        for rel, text in downstream.items():
            path = run_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        preserved = {
            "logs/review/semantic/scene_set.report.md": "p400 report\n",
            "codex_fix_notes.md": "unknown user artifact\n",
        }
        for rel, text in preserved.items():
            path = run_dir / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return run_dir

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_dry_run_selects_only_downstream_artifacts(self, _readiness) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)

            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="dry-run",
            )

            self.assertIn("asset_plan.md", plan.downstream_files)
            self.assertIn(
                "image_generation_request_snapshot.json",
                plan.downstream_files,
            )
            self.assertIn("assets/characters/hero.png", plan.downstream_files)
            self.assertIn(
                "logs/image_generation_jobs/completed.json",
                plan.downstream_files,
            )
            self.assertIn("logs/app_server/semantic.log", plan.downstream_files)
            self.assertIn("logs/render/final.log", plan.downstream_files)
            self.assertIn("thumbnails/final.png", plan.downstream_files)
            self.assertIn("final.mp4", plan.downstream_files)
            self.assertNotIn("video_manifest.md", plan.downstream_files)
            self.assertNotIn(
                "logs/review/semantic/scene_set.report.md",
                plan.downstream_files,
            )
            self.assertNotIn("codex_fix_notes.md", plan.downstream_files)
            self.assertFalse(Path(plan.checkpoint_dir).exists())

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_apply_quarantines_downstream_and_appends_pending_state(
        self,
        _readiness,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            upstream_before = {
                rel: (run_dir / rel).read_text(encoding="utf-8")
                for rel in (
                    "research.md",
                    "story.md",
                    "visual_value.md",
                    "script.md",
                    "video_manifest.md",
                )
            }
            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="apply",
            )

            checkpoint = apply_resume_plan(plan)

            self.assertTrue((checkpoint / "checkpoint.json").is_file())
            self.assertTrue(
                (
                    checkpoint
                    / "artifacts"
                    / "assets"
                    / "characters"
                    / "hero.png"
                ).is_file()
            )
            self.assertFalse((run_dir / "asset_plan.md").exists())
            self.assertFalse((run_dir / "assets/characters/hero.png").exists())
            self.assertTrue(
                (run_dir / "logs/review/semantic/scene_set.report.md").is_file()
            )
            self.assertTrue((run_dir / "codex_fix_notes.md").is_file())
            for rel, text in upstream_before.items():
                self.assertEqual((run_dir / rel).read_text(encoding="utf-8"), text)

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.p400_readiness.status"], "approved")
            self.assertEqual(state["slot.p520.status"], "pending")
            self.assertEqual(
                state["review.semantic.asset_plan.status"],
                "pending",
            )
            self.assertEqual(state["artifact.asset_plan"], "")
            self.assertEqual(state["runtime.resume.p500.status"], "prepared")
            self.assertEqual(state["runtime.create_job.status"], "pending")
            self.assertEqual(state["runtime.failure.stage"], "")
            self.assertEqual(state["runtime.app_server.transport.status"], "pending")
            self.assertEqual(state["review.semantic.create_failure_count"], "")

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_apply_fails_when_create_resume_lock_is_held(self, _readiness) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="locked",
            )

            with sync_file_lock(run_dir / ".locks/create_resume.lock", wait=False):
                with self.assertRaisesRegex(
                    P500ResumeError,
                    "another create/resume process owns",
                ):
                    apply_resume_plan(plan)

            self.assertTrue((run_dir / "asset_plan.md").is_file())
            self.assertFalse(Path(plan.checkpoint_dir).exists())

    def test_rejects_paths_outside_repo_output(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            outside = root / "elsewhere" / "run"
            outside.mkdir(parents=True)
            with self.assertRaisesRegex(P500ResumeError, "must be under"):
                resolve_run_dir(root, outside)

    def test_rejects_nested_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nested = root / "output" / "group" / "run"
            nested.mkdir(parents=True)
            with self.assertRaisesRegex(P500ResumeError, "direct child"):
                resolve_run_dir(root, nested)

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_rejects_checkpoint_path_traversal(self, _readiness) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            with self.assertRaisesRegex(P500ResumeError, "checkpoint id"):
                build_resume_plan(
                    repo_root=root,
                    run_dir=run_dir,
                    checkpoint_id="../../outside",
                )

    def test_resume_orchestration_appends_only_p500_and_p600(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            progress = run_dir / "logs/orchestration/l2_supervisor_progress.md"
            progress.parent.mkdir(parents=True)
            progress.write_text(
                "| timestamp | bucket | supervisor | event | stop_slot | result | note |\n"
                "|---|---|---|---|---|---|---|\n"
                "| old | p100 | p100 P-Bucket Supervisor | returned | p680 | old.json | done |\n",
                encoding="utf-8",
            )
            for rel in (
                "asset_inventory.md",
                "asset_plan.md",
                "asset_generation_requests.md",
                "asset_generation_manifest.md",
                "image_generation_requests.md",
            ):
                (run_dir / rel).write_text("fixture\n", encoding="utf-8")

            module = self._resume_cli_module()
            updates = module._write_resume_orchestration(
                run_dir=run_dir,
                stop_target="p680",
                now="2026-07-25T12:00:00+09:00",
            )

            text = progress.read_text(encoding="utf-8")
            self.assertIn("| old | p100 |", text)
            self.assertIn("| p500 | p500 P-Bucket Supervisor | invoked |", text)
            self.assertIn("| p600 | p600 P-Bucket Supervisor | returned |", text)
            self.assertNotIn("orchestration.p100.supervisor.status", updates)
            self.assertEqual(updates["orchestration.p500.supervisor.status"], "pending")
            self.assertEqual(updates["orchestration.p600.supervisor.status"], "pending")

    def test_resume_materialization_does_not_complete_generation_slots(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            module = self._resume_cli_module()
            updates = module._resume_state_updates(
                run_dir=run_dir,
                topic="sample",
                profile={
                    "duration_plan": {
                        "target_seconds": 300,
                        "minimum_effective_seconds": 240,
                        "minimum_scene_count": 8,
                        "minimum_narration_seconds": 180,
                    }
                },
                stop_target="p680",
                now="2026-07-25T12:00:00+09:00",
            )

            self.assertEqual(updates["slot.p520.status"], "done")
            self.assertEqual(updates["slot.p530.status"], "done")
            self.assertEqual(updates["slot.p620.status"], "done")
            for slot in (
                "p540",
                "p550",
                "p560",
                "p570",
                "p630",
                "p640",
                "p650",
                "p660",
                "p670",
                "p680",
            ):
                self.assertEqual(updates[f"slot.{slot}.status"], "pending")

    def test_p650_continuation_marks_asset_generation_before_validation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            (run_dir / "state.txt").write_text(
                "topic=sample\nslot.p550.status=pending\nslot.p560.status=pending\n"
                "slot.p570.status=pending\n---\n",
                encoding="utf-8",
            )
            module = self._resume_cli_module()
            observed: dict[str, str] = {}

            async def generate_images(_run_dir: Path, _stop_target: str) -> None:
                return None

            def validate(_run_dir: Path, _stop_target: str) -> None:
                observed.update(parse_state_file(run_dir / "state.txt"))

            frontend = SimpleNamespace(
                _run_materialization_lock=lambda _run_dir: nullcontext(),
                generate_images=generate_images,
                write_run_index=lambda _run_dir: None,
                validate=validate,
            )
            with (
                patch.object(module, "_load_frontend_runner", return_value=frontend),
                patch.object(module, "materialize_from_p500"),
                patch.object(module, "_prepare_resume_grounding"),
                patch.object(
                    module,
                    "_finalize_resume_orchestration",
                    return_value={},
                ),
            ):
                module._continue_run(
                    run_dir=run_dir,
                    topic="sample",
                    source="sample",
                    stop_target="p650",
                    materialize_only=False,
                    skip_validation=False,
                )

            self.assertEqual(observed["slot.p550.status"], "done")
            self.assertEqual(observed["slot.p560.status"], "done")
            self.assertEqual(observed["slot.p570.status"], "awaiting_approval")

    def test_materialize_only_keeps_unexecuted_media_pending(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            (run_dir / "state.txt").write_text(
                "topic=sample\nslot.p550.status=pending\nslot.p560.status=pending\n"
                "slot.p570.status=pending\n---\n",
                encoding="utf-8",
            )
            module = self._resume_cli_module()

            module._mark_materialized_asset_requests(run_dir)

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["slot.p550.status"], "done")
            self.assertEqual(state["slot.p560.status"], "pending")
            self.assertEqual(state["slot.p570.status"], "pending")
            self.assertEqual(state["stage.asset.status"], "in_progress")

    def test_cli_apply_requires_inspected_dry_run_token(self) -> None:
        module = self._resume_cli_module()
        with patch.object(
            sys,
            "argv",
            [
                "resume-from-p500.py",
                "--run-dir",
                "output/sample",
                "--apply",
            ],
        ):
            with self.assertRaisesRegex(SystemExit, "2"):
                module.main()

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_active_bulk_job_blocks_reset(self, _readiness) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            (run_dir / "logs/image_generation_jobs/completed.json").write_text(
                '{"jobId":"active","status":"running"}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(P500ResumeError, "still queued/running"):
                build_resume_plan(
                    repo_root=root,
                    run_dir=run_dir,
                    checkpoint_id="active-job",
                )

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_post_commit_failure_keeps_checkpoint_and_quarantine(
        self,
        _readiness,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="post-commit",
            )
            original_append = p500_resume.append_state_snapshot

            def append_then_fail(state_path, updates):
                original_append(state_path, updates)
                raise RuntimeError("derived rebuild failed after state commit")

            with patch(
                "toc.p500_resume.append_state_snapshot",
                side_effect=append_then_fail,
            ):
                with self.assertRaisesRegex(RuntimeError, "derived rebuild failed"):
                    apply_resume_plan(plan)

            checkpoint = Path(plan.checkpoint_dir)
            self.assertTrue((checkpoint / "checkpoint.json").is_file())
            self.assertTrue(
                (checkpoint / "artifacts/asset_plan.md").is_file()
            )
            self.assertFalse((run_dir / "asset_plan.md").exists())
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["runtime.resume.p500.status"], "prepared")

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_archives_p400_review_evidence_before_refresh(self, _readiness) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            (run_dir / "script_review.md").write_text(
                "old p400 script review\n",
                encoding="utf-8",
            )
            aggregate = (
                run_dir
                / "logs/eval/script/round_01/aggregated_review.md"
            )
            aggregate.parent.mkdir(parents=True)
            aggregate.write_text("old aggregate\n", encoding="utf-8")
            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="p400-evidence",
            )
            checkpoint = apply_resume_plan(plan)

            module = self._resume_cli_module()
            module._archive_p400_review_evidence(run_dir)

            self.assertEqual(
                (
                    checkpoint
                    / "p400_evidence"
                    / "script_review.md"
                ).read_text(encoding="utf-8"),
                "old p400 script review\n",
            )
            self.assertEqual(
                (
                    checkpoint
                    / "p400_evidence"
                    / "logs/eval/script/round_01/aggregated_review.md"
                ).read_text(encoding="utf-8"),
                "old aggregate\n",
            )


if __name__ == "__main__":
    unittest.main()
