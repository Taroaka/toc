from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import toc.p500_resume as p500_resume
from toc.harness import load_structured_document, parse_state_file
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

    def _write_create_input(
        self,
        run_dir: Path,
        *,
        topic: str = "sample",
        source: str = "exact source\nwith preserved newline\n",
        experience: str = "cinematic_story",
        source_run: str | None = None,
        target_duration_seconds: int = 300,
    ) -> Path:
        path = run_dir / "logs/orchestration/create_input.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": "toc.create_input.v1",
                    "topic": topic,
                    "source": source,
                    "source_sha256": hashlib.sha256(
                        source.encode("utf-8")
                    ).hexdigest(),
                    "experience": experience,
                    "source_run": source_run,
                    "target_duration_seconds": target_duration_seconds,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return path

    def _write_checkpoint_metadata(
        self,
        run_dir: Path,
        checkpoint: Path,
        *,
        state_before: dict[str, str] | None = None,
    ) -> Path:
        artifacts_root = checkpoint / "artifacts"
        fingerprints: dict[str, dict[str, object]] = {}
        if artifacts_root.is_dir() and not artifacts_root.is_symlink():
            for path in sorted(artifacts_root.rglob("*")):
                if not path.is_file() or path.is_symlink():
                    continue
                rel = path.relative_to(artifacts_root).as_posix()
                fingerprints[rel] = {
                    "exists": True,
                    "lexical_type": "regular_file",
                    "is_symlink": False,
                    "bytes_sha256": hashlib.sha256(
                        path.read_bytes()
                    ).hexdigest(),
                }
        checkpoint.mkdir(parents=True, exist_ok=True)
        downstream_files = tuple(sorted(fingerprints))
        upstream_sha256: dict[str, str] = {}
        state_fingerprint: dict[str, object] = {}
        index_fingerprint: dict[str, object] = {}
        optional_upstream_fingerprints: dict[
            str, dict[str, object]
        ] = {}
        canonical_state_before = dict(state_before or {})
        state_before_sha256 = (
            p500_resume.canonical_state_before_sha256(
                canonical_state_before
            )
        )
        metadata = {
            "run_dir": str(run_dir.absolute()),
            "checkpoint_id": checkpoint.name,
            "checkpoint_dir": str(checkpoint.absolute()),
            "upstream_sha256": upstream_sha256,
            "state_fingerprint": state_fingerprint,
            "index_fingerprint": index_fingerprint,
            "optional_upstream_fingerprints": (
                optional_upstream_fingerprints
            ),
            "state_before_sha256": state_before_sha256,
            "downstream_files": list(downstream_files),
            "downstream_fingerprints": fingerprints,
            "plan_token": p500_resume._plan_token(
                run_dir=run_dir.absolute(),
                checkpoint_id=checkpoint.name,
                upstream_sha256=upstream_sha256,
                state_fingerprint=state_fingerprint,
                index_fingerprint=index_fingerprint,
                optional_upstream_fingerprints=(
                    optional_upstream_fingerprints
                ),
                downstream_files=downstream_files,
                downstream_fingerprints=fingerprints,
                state_before_sha256=state_before_sha256,
            ),
            "state_before": canonical_state_before,
        }
        path = checkpoint / "checkpoint.json"
        path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

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
    def test_apply_rejects_state_bytes_changed_after_dry_run_before_writes(
        self,
        _readiness,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="state-mutated",
            )
            state_path = run_dir / "state.txt"
            state_path.write_text(
                state_path.read_text(encoding="utf-8")
                + "external.concurrent.change=true\n---\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                P500ResumeError,
                "state.txt changed after the resume plan was built",
            ):
                apply_resume_plan(plan)

            self.assertFalse(Path(plan.checkpoint_dir).exists())
            self.assertTrue((run_dir / "asset_plan.md").is_file())

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_apply_rejects_same_downstream_path_bytes_changed_after_dry_run(
        self,
        _readiness,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="downstream-mutated",
            )
            changed_path = run_dir / "asset_plan.md"
            changed_path.write_text(
                "changed in place after the inspected dry-run\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                P500ResumeError,
                "downstream artifact bytes or lexical type changed",
            ):
                apply_resume_plan(plan)

            self.assertFalse(Path(plan.checkpoint_dir).exists())
            self.assertEqual(
                changed_path.read_text(encoding="utf-8"),
                "changed in place after the inspected dry-run\n",
            )

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_apply_rejects_downstream_ancestor_swap_without_moving_outside_files(
        self,
        _readiness,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="downstream-ancestor-swap",
            )
            original_assets = run_dir / "assets-before-swap"
            outside_assets = root / "outside-assets"
            outside_hero = outside_assets / "characters/hero.png"
            outside_scene = outside_assets / "scenes/scene01_cut01.png"
            outside_hero.parent.mkdir(parents=True)
            outside_scene.parent.mkdir(parents=True)
            outside_hero.write_bytes(b"outside-hero-must-not-move")
            outside_scene.write_bytes(b"outside-scene-must-not-move")
            real_build = p500_resume.build_resume_plan
            swapped = False

            def build_then_swap(**kwargs):
                nonlocal swapped
                current = real_build(**kwargs)
                if not swapped:
                    swapped = True
                    (run_dir / "assets").rename(original_assets)
                    (run_dir / "assets").symlink_to(
                        outside_assets,
                        target_is_directory=True,
                    )
                return current

            with (
                patch.object(
                    p500_resume,
                    "build_resume_plan",
                    side_effect=build_then_swap,
                ),
                self.assertRaisesRegex(
                    P500ResumeError,
                    "directory identity changed|unsafe downstream",
                ),
            ):
                apply_resume_plan(plan)

            self.assertEqual(
                outside_hero.read_bytes(),
                b"outside-hero-must-not-move",
            )
            self.assertEqual(
                outside_scene.read_bytes(),
                b"outside-scene-must-not-move",
            )
            self.assertEqual(
                (original_assets / "characters/hero.png").read_bytes(),
                b"old image bytes\n",
            )
            self.assertEqual(
                (original_assets / "scenes/scene01_cut01.png").read_bytes(),
                b"old scene bytes\n",
            )

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_apply_rejects_run_root_replacement_bound_to_dry_run_identity(
        self,
        _readiness,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="run-root-replaced",
            )
            original_run = run_dir.with_name(f"{run_dir.name}-original")
            run_dir.rename(original_run)
            shutil.copytree(original_run, run_dir)

            with self.assertRaisesRegex(
                P500ResumeError,
                "run directory identity changed",
            ):
                apply_resume_plan(plan)

            self.assertEqual(
                (run_dir / "assets/characters/hero.png").read_bytes(),
                b"old image bytes\n",
            )
            self.assertFalse(Path(plan.checkpoint_dir).exists())

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_rollback_rejects_ancestor_swap_without_overwriting_outside_files(
        self,
        _readiness,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="rollback-ancestor-swap",
            )
            original_assets = run_dir / "assets-before-rollback"
            outside_assets = root / "outside-rollback-assets"
            outside_hero = outside_assets / "characters/hero.png"
            outside_scene = outside_assets / "scenes/scene01_cut01.png"
            outside_hero.parent.mkdir(parents=True)
            outside_scene.parent.mkdir(parents=True)
            outside_hero.write_bytes(b"outside-hero-must-not-overwrite")
            outside_scene.write_bytes(b"outside-scene-must-not-overwrite")

            def swap_then_fail(*_args, **_kwargs):
                (run_dir / "assets").rename(original_assets)
                (run_dir / "assets").symlink_to(
                    outside_assets,
                    target_is_directory=True,
                )
                raise RuntimeError("force rollback after ancestor swap")

            with (
                patch.object(
                    p500_resume,
                    "append_state_snapshot",
                    side_effect=swap_then_fail,
                ),
                self.assertRaises(Exception),
            ):
                apply_resume_plan(plan)

            self.assertEqual(
                outside_hero.read_bytes(),
                b"outside-hero-must-not-overwrite",
            )
            self.assertEqual(
                outside_scene.read_bytes(),
                b"outside-scene-must-not-overwrite",
            )
            checkpoint = Path(plan.checkpoint_dir)
            self.assertTrue(
                (
                    checkpoint
                    / "artifacts/assets/characters/hero.png"
                ).is_file()
            )
            self.assertTrue(
                (
                    checkpoint
                    / "artifacts/assets/scenes/scene01_cut01.png"
                ).is_file()
            )

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_stale_legacy_frontend_marker_does_not_block_p500_apply(
        self,
        _readiness,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            marker = run_dir / ".toc_frontend_create.lock"
            marker.write_text("pid=dead-owner\n", encoding="utf-8")
            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="stale-legacy-marker",
            )

            checkpoint = apply_resume_plan(plan)

            self.assertTrue((checkpoint / "checkpoint.json").is_file())
            self.assertEqual(
                marker.read_text(encoding="utf-8"),
                "pid=dead-owner\n",
            )

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_apply_rejects_p000_index_changed_after_dry_run_before_writes(
        self,
        _readiness,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="index-mutated",
            )
            index_path = run_dir / "p000_index.md"
            index_path.write_text(
                "concurrently rewritten navigation\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                P500ResumeError,
                "p000_index.md changed after the resume plan was built",
            ):
                apply_resume_plan(plan)

            self.assertFalse(Path(plan.checkpoint_dir).exists())
            self.assertTrue((run_dir / "asset_plan.md").is_file())

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_canonical_create_input_is_preserved_and_token_bound(
        self,
        _readiness,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            create_input = self._write_create_input(run_dir)
            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="create-input-mutated",
            )
            self.assertNotIn(
                "logs/orchestration/create_input.json",
                plan.downstream_files,
            )
            create_input.write_text(
                create_input.read_text(encoding="utf-8").replace(
                    "exact source",
                    "mutated source",
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                P500ResumeError,
                "create_input.json changed after the resume plan was built",
            ):
                apply_resume_plan(plan)

            self.assertTrue(create_input.is_file())
            self.assertFalse(Path(plan.checkpoint_dir).exists())

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_resume_plan_token_binds_canonical_state_before(
        self,
        _readiness,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            state_before = parse_state_file(run_dir / "state.txt")
            expected_digest = hashlib.sha256(
                json.dumps(
                    state_before,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()

            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="state-before-bound",
            )
            tampered_token = p500_resume._plan_token(
                run_dir=Path(plan.run_dir),
                checkpoint_id=plan.checkpoint_id,
                upstream_sha256=plan.upstream_sha256,
                state_fingerprint=plan.state_fingerprint,
                index_fingerprint=plan.index_fingerprint,
                optional_upstream_fingerprints=(
                    plan.optional_upstream_fingerprints
                ),
                downstream_files=plan.downstream_files,
                downstream_fingerprints=plan.downstream_fingerprints,
                resume_input_identity=plan.resume_input_identity,
                state_before_sha256="0" * 64,
            )

        self.assertEqual(plan.state_before_sha256, expected_digest)
        self.assertNotEqual(plan.plan_token, tampered_token)

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
            self.assertEqual(
                updates["immersive.experience"],
                "cinematic_story",
            )
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

    def test_resume_state_updates_preserve_world_walk_mode_and_source_contract(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "runtime.create_mode=world_walk",
                        "immersive.experience=world_walk",
                        "immersive.source_run=output/source_20260725_1200",
                        "immersive.source_reference_contract=preserved_v1",
                        "---",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "video_metadata:",
                        "  topic: sample",
                        "  experience: world_walk",
                        "  source_run: output/source_20260725_1200",
                        "  source_story: output/source_20260725_1200/story.md",
                        "  source_assets: output/source_20260725_1200/assets",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
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

            self.assertEqual(updates["runtime.create_mode"], "world_walk")
            self.assertEqual(updates["immersive.experience"], "world_walk")
            self.assertEqual(
                updates["immersive.source_run"],
                "output/source_20260725_1200",
            )
            self.assertEqual(
                updates["immersive.source_reference_contract"],
                "preserved_v1",
            )

    def test_resume_state_updates_reject_conflicting_experience_contracts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            (run_dir / "state.txt").write_text(
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/source_20260725_1200\n"
                "---\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "```yaml\n"
                "video_metadata:\n"
                "  topic: sample\n"
                "  experience: cinematic_story\n"
                "```\n",
                encoding="utf-8",
            )
            module = self._resume_cli_module()

            with self.assertRaisesRegex(
                P500ResumeError,
                "experience contract conflicts",
            ):
                module._resume_state_updates(
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

    def test_resume_recovers_mode_from_checkpoint_after_prior_bad_overwrite(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            checkpoint = run_dir / "logs/resume/p500/recover-mode"
            self._write_checkpoint_metadata(
                run_dir,
                checkpoint,
                state_before={
                    "runtime.create_mode": "world_walk",
                    "immersive.experience": "world_walk",
                    "immersive.source_run": "output/source_20260725_1200",
                },
            )
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint=logs/resume/p500/recover-mode\n"
                "runtime.create_mode=world_walk\n"
                "immersive.experience=cinematic_story\n"
                "immersive.source_run=output/source_20260725_1200\n"
                "---\n",
                encoding="utf-8",
            )
            manifest = {
                "video_metadata": {
                    "experience": "world_walk",
                    "source_run": "output/source_20260725_1200",
                }
            }
            module = self._resume_cli_module()

            contract = module._resolve_resume_mode_contract(
                run_dir=run_dir,
                manifest=manifest,
            )

            self.assertEqual(contract["experience"], "world_walk")
            self.assertEqual(contract["create_mode"], "world_walk")
            self.assertEqual(
                contract["source_run"],
                "output/source_20260725_1200",
            )

    def test_resume_rejects_authenticated_world_walk_storyboard_mode(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            checkpoint = run_dir / "logs/resume/p500/mode-conflict"
            self._write_checkpoint_metadata(
                run_dir,
                checkpoint,
                state_before={
                    "runtime.create_mode": "scene_storyboard",
                    "immersive.experience": "world_walk",
                    "immersive.source_run": "output/source",
                },
            )
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint="
                "logs/resume/p500/mode-conflict\n"
                "---\n",
                encoding="utf-8",
            )
            module = self._resume_cli_module()

            with self.assertRaisesRegex(
                P500ResumeError,
                "create_mode conflicts with world_walk",
            ):
                module._resolve_resume_mode_contract(
                    run_dir=run_dir,
                    manifest={
                        "video_metadata": {
                            "experience": "world_walk",
                            "source_run": "output/source",
                        }
                    },
                )

    def test_resume_never_injects_mode_from_post_checkpoint_state(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            checkpoint = run_dir / "logs/resume/p500/no-current-fallback"
            self._write_checkpoint_metadata(
                run_dir,
                checkpoint,
                state_before={"topic": "sample"},
            )
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint="
                "logs/resume/p500/no-current-fallback\n"
                "runtime.create_mode=scene_storyboard\n"
                "immersive.experience=cinematic_story\n"
                "---\n",
                encoding="utf-8",
            )
            module = self._resume_cli_module()

            contract = module._resolve_resume_mode_contract(
                run_dir=run_dir,
                manifest={
                    "video_metadata": {
                        "experience": "world_walk",
                        "source_run": "output/source",
                    }
                },
            )

            self.assertEqual(contract["experience"], "world_walk")
            self.assertEqual(contract["create_mode"], "world_walk")
            self.assertEqual(contract["source_run"], "output/source")

    def test_resume_rejects_tampered_checkpoint_state_before(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            checkpoint = run_dir / "logs/resume/p500/tampered-state"
            metadata_path = self._write_checkpoint_metadata(
                run_dir,
                checkpoint,
                state_before={
                    "runtime.create_mode": "world_walk",
                    "immersive.experience": "world_walk",
                    "immersive.source_run": "output/source_20260725_1200",
                },
            )
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            payload["state_before"]["immersive.experience"] = (
                "cinematic_story"
            )
            metadata_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint="
                "logs/resume/p500/tampered-state\n"
                "---\n",
                encoding="utf-8",
            )
            module = self._resume_cli_module()

            with self.assertRaisesRegex(
                P500ResumeError,
                "state_before digest does not match",
            ):
                module._checkpoint_state_before(run_dir)

    def test_resume_rejects_rehashed_state_before_without_new_plan_token(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            checkpoint = run_dir / "logs/resume/p500/rehashed-state"
            metadata_path = self._write_checkpoint_metadata(
                run_dir,
                checkpoint,
                state_before={
                    "runtime.create_mode": "world_walk",
                    "immersive.experience": "world_walk",
                },
            )
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            payload["state_before"]["immersive.experience"] = (
                "cinematic_story"
            )
            payload["state_before_sha256"] = (
                p500_resume.canonical_state_before_sha256(
                    payload["state_before"]
                )
            )
            metadata_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint="
                "logs/resume/p500/rehashed-state\n"
                "---\n",
                encoding="utf-8",
            )
            module = self._resume_cli_module()

            with self.assertRaisesRegex(
                P500ResumeError,
                "plan token does not match",
            ):
                module._checkpoint_state_before(run_dir)

    def test_legacy_checkpoint_blocks_unauthenticated_state_reconstruction(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            checkpoint = run_dir / "logs/resume/p500/legacy-state"
            metadata_path = self._write_checkpoint_metadata(
                run_dir,
                checkpoint,
                state_before={
                    "immersive.experience": "world_walk",
                },
            )
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
            payload.pop("state_before_sha256")
            payload["plan_token"] = p500_resume._plan_token(
                run_dir=Path(payload["run_dir"]),
                checkpoint_id=payload["checkpoint_id"],
                upstream_sha256=payload["upstream_sha256"],
                state_fingerprint=payload["state_fingerprint"],
                index_fingerprint=payload["index_fingerprint"],
                optional_upstream_fingerprints=(
                    payload["optional_upstream_fingerprints"]
                ),
                downstream_files=tuple(payload["downstream_files"]),
                downstream_fingerprints=(
                    payload["downstream_fingerprints"]
                ),
            )
            metadata_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint="
                "logs/resume/p500/legacy-state\n"
                "---\n",
                encoding="utf-8",
            )
            module = self._resume_cli_module()

            with self.assertRaisesRegex(
                P500ResumeError,
                "predates authenticated state_before",
            ):
                module._checkpoint_state_before(run_dir)

    def test_world_walk_resume_restores_checkpointed_source_references(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            checkpoint = run_dir / "logs/resume/p500/world-walk"
            reference = (
                checkpoint
                / "artifacts/assets/source_references/characters/hero.png"
            )
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"preserved-world-walk-reference")
            self._write_checkpoint_metadata(run_dir, checkpoint)
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint=logs/resume/p500/world-walk\n"
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/source_20260725_1200\n"
                "---\n",
                encoding="utf-8",
            )
            manifest = {
                "video_metadata": {
                    "experience": "world_walk",
                    "source_run": "output/source_20260725_1200",
                    "source_assets": "output/source_20260725_1200/assets",
                },
                "world_walk_contract": {
                    "source_references": [
                        "assets/source_references/characters/hero.png"
                    ]
                },
            }
            module = self._resume_cli_module()
            frontend = SimpleNamespace(
                _materialize_world_walk_source_references=lambda *_args: self.fail(
                    "checkpointed references should be preferred"
                )
            )

            restored = module._restore_world_walk_source_references(
                frontend,
                run_dir=run_dir,
                manifest=manifest,
                mode_contract=module._resolve_resume_mode_contract(
                    run_dir=run_dir,
                    manifest=manifest,
                ),
            )

            output = run_dir / "assets/source_references/characters/hero.png"
            self.assertEqual(
                output.read_bytes(),
                b"preserved-world-walk-reference",
            )
            self.assertEqual(
                restored,
                ["assets/source_references/characters/hero.png"],
            )
            self.assertEqual(
                module._resolve_resume_mode_contract(
                    run_dir=run_dir,
                    manifest=manifest,
                )["create_mode"],
                "world_walk",
            )

    @patch("toc.p500_resume._p400_readiness", return_value=("approved", ()))
    def test_world_walk_restore_accepts_real_apply_checkpoint_provenance(
        self,
        _readiness,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            reference_rel = (
                "assets/source_references/characters/hero.png"
            )
            reference = run_dir / reference_rel
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"real-checkpoint-reference")
            (run_dir / "state.txt").write_text(
                "topic=sample\n"
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/deleted-source\n"
                "eval.p400_readiness.status=approved\n"
                "---\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "```yaml\n"
                "video_metadata:\n"
                "  topic: sample\n"
                "  experience: world_walk\n"
                "  source_run: output/deleted-source\n"
                "world_walk_contract:\n"
                "  source_references:\n"
                f"    - {reference_rel}\n"
                "```\n",
                encoding="utf-8",
            )
            plan = build_resume_plan(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="real-world-walk",
            )
            apply_resume_plan(plan)
            self.assertFalse(reference.exists())
            module = self._resume_cli_module()
            manifest = load_structured_document(
                run_dir / "video_manifest.md"
            )[1]

            with patch.object(module, "REPO_ROOT", root):
                restored = module._restore_world_walk_source_references(
                    SimpleNamespace(
                        _materialize_world_walk_source_references=(
                            lambda *_args, **_kwargs: self.fail(
                                "verified checkpoint must avoid fallback"
                            )
                        )
                    ),
                    run_dir=run_dir,
                    manifest=manifest,
                    mode_contract=module._resolve_resume_mode_contract(
                        run_dir=run_dir,
                        manifest=manifest,
                    ),
                )

            self.assertEqual(restored, [reference_rel])
            self.assertEqual(
                reference.read_bytes(),
                b"real-checkpoint-reference",
            )

    def test_world_walk_resume_fallback_preserves_checkpointed_reference_bytes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_run = root / "output/source_20260725_1200"
            (source_run / "story.md").parent.mkdir(parents=True)
            (source_run / "story.md").write_text("source story\n", encoding="utf-8")
            source_hero = source_run / "assets/characters/hero.png"
            source_location = source_run / "assets/locations/village.png"
            source_hero.parent.mkdir(parents=True)
            source_location.parent.mkdir(parents=True)
            source_hero.write_bytes(b"changed-source-hero")
            source_location.write_bytes(b"source-location")

            run_dir = root / "output/target"
            checkpoint = run_dir / "logs/resume/p500/world-walk-partial"
            checkpoint_hero = (
                checkpoint
                / "artifacts/assets/source_references/characters/hero.png"
            )
            checkpoint_hero.parent.mkdir(parents=True)
            checkpoint_hero.write_bytes(b"checkpoint-hero")
            self._write_checkpoint_metadata(run_dir, checkpoint)
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint="
                "logs/resume/p500/world-walk-partial\n"
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/source_20260725_1200\n"
                "---\n",
                encoding="utf-8",
            )
            references = [
                "assets/source_references/characters/hero.png",
                "assets/source_references/locations/village.png",
            ]
            manifest = {
                "video_metadata": {
                    "experience": "world_walk",
                    "source_run": "output/source_20260725_1200",
                },
                "world_walk_contract": {
                    "source_references": references,
                },
            }
            module = self._resume_cli_module()
            frontend = module._load_frontend_runner()

            with patch.object(module, "REPO_ROOT", root):
                restored = module._restore_world_walk_source_references(
                    frontend,
                    run_dir=run_dir,
                    manifest=manifest,
                    mode_contract=module._resolve_resume_mode_contract(
                        run_dir=run_dir,
                        manifest=manifest,
                    ),
                )

            self.assertEqual(restored, references)
            self.assertEqual(
                (
                    run_dir
                    / "assets/source_references/characters/hero.png"
                ).read_bytes(),
                b"checkpoint-hero",
            )
            self.assertEqual(
                (
                    run_dir
                    / "assets/source_references/locations/village.png"
                ).read_bytes(),
                b"source-location",
            )

    def test_world_walk_resume_rejects_tampered_checkpoint_reference(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "output/target"
            checkpoint = run_dir / "logs/resume/p500/world-walk-tampered"
            reference_rel = (
                "assets/source_references/characters/hero.png"
            )
            reference = checkpoint / "artifacts" / reference_rel
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"checkpoint-original")
            self._write_checkpoint_metadata(run_dir, checkpoint)
            reference.write_bytes(b"checkpoint-tampered")
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint="
                "logs/resume/p500/world-walk-tampered\n"
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/deleted-source\n"
                "---\n",
                encoding="utf-8",
            )
            manifest = {
                "video_metadata": {
                    "experience": "world_walk",
                    "source_run": "output/deleted-source",
                },
                "world_walk_contract": {
                    "source_references": [reference_rel],
                },
            }
            module = self._resume_cli_module()

            with (
                patch.object(module, "REPO_ROOT", root),
                self.assertRaisesRegex(
                    P500ResumeError,
                    "sha256 mismatch",
                ),
            ):
                module._restore_world_walk_source_references(
                    SimpleNamespace(),
                    run_dir=run_dir,
                    manifest=manifest,
                    mode_contract=module._resolve_resume_mode_contract(
                        run_dir=run_dir,
                        manifest=manifest,
                    ),
                )

            self.assertFalse((run_dir / reference_rel).exists())

    def test_world_walk_resume_rejects_missing_declared_checkpoint_artifacts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_run = root / "output/source"
            live_reference = (
                source_run / "assets/characters/hero.png"
            )
            live_reference.parent.mkdir(parents=True)
            live_reference.write_bytes(b"changed-live-source")
            (source_run / "story.md").write_text(
                "source story\n",
                encoding="utf-8",
            )
            run_dir = root / "output/target"
            checkpoint = (
                run_dir / "logs/resume/p500/missing-artifacts"
            )
            reference_rel = (
                "assets/source_references/characters/hero.png"
            )
            checkpoint_reference = (
                checkpoint / "artifacts" / reference_rel
            )
            checkpoint_reference.parent.mkdir(parents=True)
            checkpoint_reference.write_bytes(b"checkpoint-source")
            self._write_checkpoint_metadata(run_dir, checkpoint)
            shutil.rmtree(checkpoint / "artifacts")
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint="
                "logs/resume/p500/missing-artifacts\n"
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/source\n"
                "---\n",
                encoding="utf-8",
            )
            manifest = {
                "video_metadata": {
                    "experience": "world_walk",
                    "source_run": "output/source",
                },
                "world_walk_contract": {
                    "source_references": [reference_rel],
                },
            }
            module = self._resume_cli_module()

            with (
                patch.object(module, "REPO_ROOT", root),
                self.assertRaisesRegex(
                    P500ResumeError,
                    "missing or unsafe",
                ),
            ):
                module._restore_world_walk_source_references(
                    SimpleNamespace(),
                    run_dir=run_dir,
                    manifest=manifest,
                    mode_contract=module._resolve_resume_mode_contract(
                        run_dir=run_dir,
                        manifest=manifest,
                    ),
                )

            self.assertFalse((run_dir / reference_rel).exists())

    def test_world_walk_resume_rejects_rewritten_checkpoint_provenance(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "output/target"
            checkpoint = (
                run_dir / "logs/resume/p500/world-walk-provenance"
            )
            reference_rel = (
                "assets/source_references/characters/hero.png"
            )
            reference = checkpoint / "artifacts" / reference_rel
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"checkpoint-original")
            metadata_path = self._write_checkpoint_metadata(
                run_dir,
                checkpoint,
            )
            reference.write_bytes(b"checkpoint-rewritten")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["downstream_fingerprints"][reference_rel][
                "bytes_sha256"
            ] = hashlib.sha256(reference.read_bytes()).hexdigest()
            metadata_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint="
                "logs/resume/p500/world-walk-provenance\n"
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/deleted-source\n"
                "---\n",
                encoding="utf-8",
            )
            manifest = {
                "video_metadata": {
                    "experience": "world_walk",
                    "source_run": "output/deleted-source",
                },
                "world_walk_contract": {
                    "source_references": [reference_rel],
                },
            }
            module = self._resume_cli_module()

            with (
                patch.object(module, "REPO_ROOT", root),
                self.assertRaisesRegex(
                    P500ResumeError,
                    "plan token does not match",
                ),
            ):
                module._restore_world_walk_source_references(
                    SimpleNamespace(),
                    run_dir=run_dir,
                    manifest=manifest,
                    mode_contract=module._resolve_resume_mode_contract(
                        run_dir=run_dir,
                        manifest=manifest,
                    ),
                )

            self.assertFalse((run_dir / reference_rel).exists())

    def test_world_walk_resume_rejects_symlink_checkpoint_metadata(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "output/target"
            checkpoint = run_dir / "logs/resume/p500/world-walk-metadata"
            checkpoint.mkdir(parents=True)
            outside_metadata = root / "outside-checkpoint.json"
            outside_metadata.write_text("{}\n", encoding="utf-8")
            (checkpoint / "checkpoint.json").symlink_to(outside_metadata)
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint="
                "logs/resume/p500/world-walk-metadata\n"
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/deleted-source\n"
                "---\n",
                encoding="utf-8",
            )
            module = self._resume_cli_module()

            with self.assertRaisesRegex(
                P500ResumeError,
                "checkpoint metadata is invalid",
            ):
                module._resolve_resume_mode_contract(run_dir=run_dir)

    def test_world_walk_resume_rejects_checkpoint_ancestor_swap(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "output/target"
            checkpoint = run_dir / "logs/resume/p500/ancestor-swap"
            metadata_path = self._write_checkpoint_metadata(
                run_dir,
                checkpoint,
            )
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint="
                "logs/resume/p500/ancestor-swap\n"
                "---\n",
                encoding="utf-8",
            )
            outside_p500 = root / "outside-p500"
            outside_checkpoint = outside_p500 / checkpoint.name
            outside_checkpoint.mkdir(parents=True)
            (outside_checkpoint / "checkpoint.json").write_bytes(
                metadata_path.read_bytes()
            )
            module = self._resume_cli_module()
            real_read = module.read_regular_file_nofollow
            swapped = False

            def swap_checkpoint_ancestor(*args, **kwargs):
                nonlocal swapped
                if not swapped:
                    swapped = True
                    p500_root = run_dir / "logs/resume/p500"
                    p500_root.rename(
                        run_dir / "logs/resume/p500-original"
                    )
                    p500_root.symlink_to(
                        outside_p500,
                        target_is_directory=True,
                    )
                return real_read(*args, **kwargs)

            with (
                patch.object(
                    module,
                    "read_regular_file_nofollow",
                    side_effect=swap_checkpoint_ancestor,
                ),
                self.assertRaisesRegex(
                    P500ResumeError,
                    "checkpoint metadata is invalid",
                ),
            ):
                module._resume_checkpoint_metadata(run_dir)

    def test_world_walk_resume_rejects_unsafe_source_with_complete_checkpoint(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "output/target"
            checkpoint = run_dir / "logs/resume/p500/world-walk-confined"
            reference_rel = (
                "assets/source_references/characters/hero.png"
            )
            reference = checkpoint / "artifacts" / reference_rel
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"checkpoint-reference")
            self._write_checkpoint_metadata(run_dir, checkpoint)
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint="
                "logs/resume/p500/world-walk-confined\n"
                "immersive.experience=world_walk\n"
                "immersive.source_run=../../outside\n"
                "---\n",
                encoding="utf-8",
            )
            manifest = {
                "video_metadata": {
                    "experience": "world_walk",
                    "source_run": "../../outside",
                },
                "world_walk_contract": {
                    "source_references": [reference_rel],
                },
            }
            module = self._resume_cli_module()

            with (
                patch.object(module, "REPO_ROOT", root),
                self.assertRaisesRegex(
                    P500ResumeError,
                    "unsafe world_walk source_run contract",
                ),
            ):
                module._restore_world_walk_source_references(
                    SimpleNamespace(),
                    run_dir=run_dir,
                    manifest=manifest,
                    mode_contract=module._resolve_resume_mode_contract(
                        run_dir=run_dir,
                        manifest=manifest,
                    ),
                )

            self.assertFalse((run_dir / reference_rel).exists())

    def test_fresh_world_walk_copy_rejects_destination_symlink_and_source_swap(
        self,
    ) -> None:
        module = self._resume_cli_module()._load_frontend_runner()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_run = root / "source"
            source_image = source_run / "assets/characters/hero.png"
            source_image.parent.mkdir(parents=True)
            source_image.write_bytes(b"source-original")
            run_dir = root / "target"
            destination = (
                run_dir
                / "assets/source_references/characters/hero.png"
            )
            destination.parent.mkdir(parents=True)
            outside = root / "outside.png"
            outside.write_bytes(b"outside")
            destination.symlink_to(outside)

            with self.assertRaisesRegex(
                ValueError,
                "destination already exists",
            ):
                module._materialize_world_walk_source_references(
                    source_run,
                    run_dir,
                )
            self.assertEqual(outside.read_bytes(), b"outside")

            destination.unlink()
            source_identity = module.directory_identity_nofollow(source_run)
            original_source = root / "source-original"
            source_run.rename(original_source)
            replacement_image = source_run / "assets/characters/hero.png"
            replacement_image.parent.mkdir(parents=True)
            replacement_image.write_bytes(b"source-replacement")

            with self.assertRaisesRegex(
                ValueError,
                "directory identity changed",
            ):
                module._materialize_world_walk_source_references(
                    source_run,
                    run_dir,
                    source_root_identity=source_identity,
                )
            self.assertFalse(destination.exists())

            destination_root_identity = (
                module.directory_identity_nofollow(run_dir)
            )
            original_run_dir = root / "target-original"
            run_dir.rename(original_run_dir)
            run_dir.mkdir()

            with self.assertRaisesRegex(
                ValueError,
                "directory identity changed",
            ):
                module._materialize_world_walk_source_references(
                    source_run,
                    run_dir,
                    destination_root_identity=destination_root_identity,
                )
            self.assertFalse(destination.exists())

    def test_world_walk_atomic_copy_never_clobbers_racing_destination(
        self,
    ) -> None:
        module = self._resume_cli_module()._load_frontend_runner()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_root = root / "source"
            source = source_root / "assets/characters/hero.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"trusted-source")
            destination_root = root / "target"
            destination_root.mkdir()
            destination_rel = Path(
                "assets/source_references/characters/hero.png"
            )
            original_link = os.link

            def race_destination(
                source_name: str,
                destination_name: str,
                *,
                src_dir_fd: int,
                dst_dir_fd: int,
                follow_symlinks: bool,
            ) -> None:
                descriptor = os.open(
                    destination_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=dst_dir_fd,
                )
                try:
                    os.write(descriptor, b"racing-destination")
                finally:
                    os.close(descriptor)
                original_link(
                    source_name,
                    destination_name,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                    follow_symlinks=follow_symlinks,
                )

            with (
                patch(
                    "scripts.world_walk_source.os.link",
                    side_effect=race_destination,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "destination appeared while copying",
                ),
            ):
                module.copy_regular_file_atomic_nofollow(
                    source_root=source_root,
                    source_relative="assets/characters/hero.png",
                    destination_root=destination_root,
                    destination_relative=destination_rel,
                )

            self.assertEqual(
                (destination_root / destination_rel).read_bytes(),
                b"racing-destination",
            )

    def test_world_walk_atomic_copy_rejects_temp_name_substitution(
        self,
    ) -> None:
        module = self._resume_cli_module()._load_frontend_runner()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_root = root / "source"
            source = source_root / "assets/characters/hero.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"trusted-source")
            destination_root = root / "target"
            destination_root.mkdir()
            destination_rel = Path(
                "assets/source_references/characters/hero.png"
            )
            original_link = os.link

            def substitute_temp_name(
                source_name: str,
                destination_name: str,
                *,
                src_dir_fd: int,
                dst_dir_fd: int,
                follow_symlinks: bool,
            ) -> None:
                os.unlink(source_name, dir_fd=src_dir_fd)
                descriptor = os.open(
                    source_name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=src_dir_fd,
                )
                try:
                    os.write(descriptor, b"substituted")
                finally:
                    os.close(descriptor)
                original_link(
                    source_name,
                    destination_name,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                    follow_symlinks=follow_symlinks,
                )

            with (
                patch(
                    "scripts.world_walk_source.os.link",
                    side_effect=substitute_temp_name,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "published destination identity mismatch",
                ),
            ):
                module.copy_regular_file_atomic_nofollow(
                    source_root=source_root,
                    source_relative="assets/characters/hero.png",
                    destination_root=destination_root,
                    destination_relative=destination_rel,
                )

    def test_world_walk_atomic_copy_rejects_parent_swap_after_publish(
        self,
    ) -> None:
        module = self._resume_cli_module()._load_frontend_runner()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_root = root / "source"
            source = source_root / "assets/characters/hero.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"trusted-source")
            destination_root = root / "target"
            destination_root.mkdir()
            destination_rel = Path(
                "assets/source_references/characters/hero.png"
            )
            destination_parent = (
                destination_root / destination_rel.parent
            )
            moved_parent = destination_parent.with_name(
                "characters-original"
            )
            original_link = os.link

            def swap_destination_parent(
                source_name: str,
                destination_name: str,
                *,
                src_dir_fd: int,
                dst_dir_fd: int,
                follow_symlinks: bool,
            ) -> None:
                destination_parent.rename(moved_parent)
                destination_parent.mkdir()
                (destination_parent / destination_name).write_bytes(
                    b"attacker"
                )
                original_link(
                    source_name,
                    destination_name,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                    follow_symlinks=follow_symlinks,
                )

            with (
                patch(
                    "scripts.world_walk_source.os.link",
                    side_effect=swap_destination_parent,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "parent identity changed after publish",
                ),
            ):
                module.copy_regular_file_atomic_nofollow(
                    source_root=source_root,
                    source_relative="assets/characters/hero.png",
                    destination_root=destination_root,
                    destination_relative=destination_rel,
                )

            self.assertEqual(
                (destination_root / destination_rel).read_bytes(),
                b"attacker",
            )
            self.assertFalse(
                (moved_parent / destination_rel.name).exists()
            )

    def test_world_walk_hash_rejects_path_substitution_after_read(
        self,
    ) -> None:
        module = self._resume_cli_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "assets/source_references/hero.png"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"trusted-reference")
            expected_root_identity = (
                module.directory_identity_nofollow(root)
            )
            original_parent = target.parent
            moved_parent = original_parent.with_name(
                "source_references-original"
            )
            original_read = os.read
            substituted = False

            def substitute_after_eof(
                descriptor: int,
                amount: int,
            ) -> bytes:
                nonlocal substituted
                chunk = original_read(descriptor, amount)
                if not chunk and not substituted:
                    substituted = True
                    original_parent.rename(moved_parent)
                    original_parent.mkdir()
                    target.write_bytes(b"attacker-reference")
                return chunk

            with (
                patch(
                    "scripts.world_walk_source.os.read",
                    side_effect=substitute_after_eof,
                ),
                self.assertRaisesRegex(
                    ValueError,
                    "identity changed after hashing",
                ),
            ):
                module.sha256_regular_file_nofollow(
                    root,
                    "assets/source_references/hero.png",
                    expected_root_identity=expected_root_identity,
                )

    def test_world_walk_restore_rejects_source_swap_after_preflight(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_run = root / "output/source"
            source_image = source_run / "assets/characters/hero.png"
            source_image.parent.mkdir(parents=True)
            source_image.write_bytes(b"preflight-source")
            (source_run / "story.md").write_text(
                "source story\n",
                encoding="utf-8",
            )
            run_dir = root / "output/target"
            run_dir.mkdir()
            (run_dir / "state.txt").write_text(
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/source\n"
                "---\n",
                encoding="utf-8",
            )
            reference_rel = (
                "assets/source_references/characters/hero.png"
            )
            manifest = {
                "video_metadata": {
                    "experience": "world_walk",
                    "source_run": "output/source",
                },
                "world_walk_contract": {
                    "source_references": [reference_rel],
                },
            }
            module = self._resume_cli_module()
            real_copy = module.copy_regular_file_atomic_nofollow
            swapped = False

            def swap_source_root(**kwargs):
                nonlocal swapped
                if not swapped:
                    swapped = True
                    active_source = kwargs["source_root"]
                    active_source.rename(
                        active_source.with_name("source-original")
                    )
                    replacement = (
                        active_source / "assets/characters/hero.png"
                    )
                    replacement.parent.mkdir(parents=True)
                    replacement.write_bytes(b"replacement-source")
                    (active_source / "story.md").write_text(
                        "replacement story\n",
                        encoding="utf-8",
                    )
                return real_copy(**kwargs)

            with (
                patch.object(module, "REPO_ROOT", root),
                patch.object(
                    module,
                    "copy_regular_file_atomic_nofollow",
                    side_effect=swap_source_root,
                ),
                self.assertRaisesRegex(
                    P500ResumeError,
                    "could not restore world_walk source reference",
                ),
            ):
                module._restore_world_walk_source_references(
                    SimpleNamespace(),
                    run_dir=run_dir,
                    manifest=manifest,
                    mode_contract=module._resolve_resume_mode_contract(
                        run_dir=run_dir,
                        manifest=manifest,
                    ),
                )

            self.assertFalse((run_dir / reference_rel).exists())

    def test_world_walk_restore_rolls_back_prior_reference_on_failure(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_run = root / "output/source"
            references = [
                "assets/source_references/characters/hero.png",
                "assets/source_references/locations/village.png",
            ]
            for rel, payload in zip(
                references,
                (b"hero", b"village"),
                strict=True,
            ):
                source_rel = Path("assets") / Path(rel).relative_to(
                    Path("assets/source_references")
                )
                path = source_run / source_rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)
            (source_run / "story.md").write_text(
                "source story\n",
                encoding="utf-8",
            )
            run_dir = root / "output/target"
            run_dir.mkdir()
            (run_dir / "state.txt").write_text(
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/source\n"
                "---\n",
                encoding="utf-8",
            )
            manifest = {
                "video_metadata": {
                    "experience": "world_walk",
                    "source_run": "output/source",
                },
                "world_walk_contract": {
                    "source_references": references,
                },
            }
            module = self._resume_cli_module()
            real_copy = module.copy_regular_file_atomic_nofollow
            call_count = 0

            def fail_second_copy(**kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    raise ValueError("injected second-copy failure")
                return real_copy(**kwargs)

            with (
                patch.object(module, "REPO_ROOT", root),
                patch.object(
                    module,
                    "copy_regular_file_atomic_nofollow",
                    side_effect=fail_second_copy,
                ),
                self.assertRaisesRegex(
                    P500ResumeError,
                    "injected second-copy failure",
                ),
            ):
                module._restore_world_walk_source_references(
                    SimpleNamespace(),
                    run_dir=run_dir,
                    manifest=manifest,
                    mode_contract=module._resolve_resume_mode_contract(
                        run_dir=run_dir,
                        manifest=manifest,
                    ),
                )

            self.assertTrue(
                all(not (run_dir / rel).exists() for rel in references)
            )

            with patch.object(module, "REPO_ROOT", root):
                restored = module._restore_world_walk_source_references(
                    SimpleNamespace(),
                    run_dir=run_dir,
                    manifest=manifest,
                    mode_contract=module._resolve_resume_mode_contract(
                        run_dir=run_dir,
                        manifest=manifest,
                    ),
                )
            self.assertEqual(restored, references)

    def test_world_walk_restore_rejects_post_copy_symlink_substitution(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_run = root / "output/source"
            source = source_run / "assets/characters/hero.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"trusted-reference")
            (source_run / "story.md").write_text(
                "source story\n",
                encoding="utf-8",
            )
            run_dir = root / "output/target"
            run_dir.mkdir()
            (run_dir / "state.txt").write_text(
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/source\n"
                "---\n",
                encoding="utf-8",
            )
            reference_rel = (
                "assets/source_references/characters/hero.png"
            )
            manifest = {
                "video_metadata": {
                    "experience": "world_walk",
                    "source_run": "output/source",
                },
                "world_walk_contract": {
                    "source_references": [reference_rel],
                },
            }
            outside = root / "outside.png"
            outside.write_bytes(b"trusted-reference")
            module = self._resume_cli_module()
            real_copy = module.copy_regular_file_atomic_nofollow

            def substitute_after_copy(**kwargs):
                digest = real_copy(**kwargs)
                destination = (
                    kwargs["destination_root"]
                    / kwargs["destination_relative"]
                )
                destination.unlink()
                destination.symlink_to(outside)
                return digest

            with (
                patch.object(module, "REPO_ROOT", root),
                patch.object(
                    module,
                    "copy_regular_file_atomic_nofollow",
                    side_effect=substitute_after_copy,
                ),
                self.assertRaisesRegex(
                    P500ResumeError,
                    "final verification",
                ),
            ):
                module._restore_world_walk_source_references(
                    SimpleNamespace(),
                    run_dir=run_dir,
                    manifest=manifest,
                    mode_contract=module._resolve_resume_mode_contract(
                        run_dir=run_dir,
                        manifest=manifest,
                    ),
                )

            self.assertTrue((run_dir / reference_rel).is_symlink())
            self.assertEqual(outside.read_bytes(), b"trusted-reference")

    def test_world_walk_preflight_requires_exact_fallback_reference(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source_run = root / "output/source"
            other = source_run / "assets/characters/other.png"
            other.parent.mkdir(parents=True)
            other.write_bytes(b"other")
            (source_run / "story.md").write_text(
                "source story\n",
                encoding="utf-8",
            )
            run_dir = root / "output/target"
            run_dir.mkdir()
            (run_dir / "video_manifest.md").write_text(
                "```yaml\n"
                "video_metadata:\n"
                "  experience: world_walk\n"
                "  source_run: output/source\n"
                "world_walk_contract:\n"
                "  source_references:\n"
                "    - assets/source_references/characters/missing.png\n"
                "```\n",
                encoding="utf-8",
            )
            module = self._resume_cli_module()

            with (
                patch.object(module, "REPO_ROOT", root),
                self.assertRaisesRegex(
                    P500ResumeError,
                    "cannot materialize required reference",
                ),
            ):
                module._preflight_world_walk_before_reset(
                    run_dir=run_dir,
                    mode_contract={
                        "experience": "world_walk",
                        "source_run": "output/source",
                    },
                )

    def test_world_walk_resume_rejects_symlink_reference_destination(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "run"
            checkpoint = run_dir / "logs/resume/p500/world-walk"
            reference = (
                checkpoint
                / "artifacts/assets/source_references/characters/hero.png"
            )
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"checkpoint-reference")
            self._write_checkpoint_metadata(run_dir, checkpoint)
            destination = (
                run_dir / "assets/source_references/characters/hero.png"
            )
            destination.parent.mkdir(parents=True)
            outside = root / "outside.png"
            outside.write_bytes(b"outside-must-not-change")
            destination.symlink_to(outside)
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint=logs/resume/p500/world-walk\n"
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/source_20260725_1200\n"
                "---\n",
                encoding="utf-8",
            )
            manifest = {
                "video_metadata": {
                    "experience": "world_walk",
                    "source_run": "output/source_20260725_1200",
                },
                "world_walk_contract": {
                    "source_references": [
                        "assets/source_references/characters/hero.png"
                    ]
                },
            }
            module = self._resume_cli_module()

            with self.assertRaisesRegex(
                P500ResumeError,
                "destination is unsafe",
            ):
                module._restore_world_walk_source_references(
                    SimpleNamespace(),
                    run_dir=run_dir,
                    manifest=manifest,
                    mode_contract=module._resolve_resume_mode_contract(
                        run_dir=run_dir,
                        manifest=manifest,
                    ),
                )

            self.assertEqual(outside.read_bytes(), b"outside-must-not-change")

    def test_world_walk_resume_rejects_symlink_checkpoint_artifacts_root(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "run"
            checkpoint = run_dir / "logs/resume/p500/world-walk"
            self._write_checkpoint_metadata(run_dir, checkpoint)
            outside_artifacts = root / "outside-artifacts"
            reference = (
                outside_artifacts
                / "assets/source_references/characters/hero.png"
            )
            reference.parent.mkdir(parents=True)
            reference.write_bytes(b"outside-reference")
            (checkpoint / "artifacts").symlink_to(
                outside_artifacts,
                target_is_directory=True,
            )
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint=logs/resume/p500/world-walk\n"
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/source_20260725_1200\n"
                "---\n",
                encoding="utf-8",
            )
            manifest = {
                "video_metadata": {
                    "experience": "world_walk",
                    "source_run": "output/source_20260725_1200",
                },
                "world_walk_contract": {
                    "source_references": [
                        "assets/source_references/characters/hero.png"
                    ]
                },
            }
            module = self._resume_cli_module()

            with self.assertRaisesRegex(
                P500ResumeError,
                "checkpoint artifacts directory is unsafe",
            ):
                module._restore_world_walk_source_references(
                    SimpleNamespace(),
                    run_dir=run_dir,
                    manifest=manifest,
                    mode_contract=module._resolve_resume_mode_contract(
                        run_dir=run_dir,
                        manifest=manifest,
                    ),
                )

    def test_world_walk_resume_wraps_missing_source_fallback_error(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "output/target"
            checkpoint = run_dir / "logs/resume/p500/world-walk"
            self._write_checkpoint_metadata(run_dir, checkpoint)
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint=logs/resume/p500/world-walk\n"
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/missing-source\n"
                "---\n",
                encoding="utf-8",
            )
            manifest = {
                "video_metadata": {
                    "experience": "world_walk",
                    "source_run": "output/missing-source",
                },
                "world_walk_contract": {
                    "source_references": [
                        "assets/source_references/characters/hero.png"
                    ]
                },
            }
            module = self._resume_cli_module()

            with (
                patch.object(module, "REPO_ROOT", root),
                self.assertRaisesRegex(
                    P500ResumeError,
                    "verified checkpoint does not contain every required",
                ),
            ):
                module._restore_world_walk_source_references(
                    SimpleNamespace(),
                    run_dir=run_dir,
                    manifest=manifest,
                    mode_contract=module._resolve_resume_mode_contract(
                        run_dir=run_dir,
                        manifest=manifest,
                    ),
                )

    def test_world_walk_resume_materializes_reference_bound_asset_requests(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            checkpoint = run_dir / "logs/resume/p500/world-walk-contract"
            reference_rels = [
                f"assets/source_references/characters/source_{index}.png"
                for index in range(1, 6)
            ]
            bound_references = reference_rels[:4]
            for reference_rel in reference_rels:
                checkpoint_reference = checkpoint / "artifacts" / reference_rel
                checkpoint_reference.parent.mkdir(parents=True, exist_ok=True)
                checkpoint_reference.write_bytes(b"world-walk-reference")
            self._write_checkpoint_metadata(run_dir, checkpoint)
            (run_dir / "state.txt").write_text(
                "runtime.resume.p500.checkpoint="
                "logs/resume/p500/world-walk-contract\n"
                "runtime.create_mode=world_walk\n"
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/source_20260725_1200\n"
                "---\n",
                encoding="utf-8",
            )
            manifest = {
                "video_metadata": {
                    "topic": "sample",
                    "experience": "world_walk",
                    "source_run": "output/source_20260725_1200",
                },
                "world_walk_contract": {
                    "viewpoint": "observer_pov",
                    "source_references": reference_rels,
                },
                "assets": {
                    "character_bible": [
                        {
                            "character_id": "hero",
                            "reference_images": [
                                "assets/characters/hero.png"
                            ],
                            "fixed_prompts": ["同じ人物の全身参照"],
                            "cinematic": {
                                "role": "遠景で観察される主人公",
                                "visual_subject": "旅装の人物の全身",
                            },
                        }
                    ],
                    "object_bible": [],
                    "location_bible": [],
                    "style_guide": {
                        "reference_images": reference_rels,
                    },
                },
                "scenes": [
                    {
                        "scene_id": 1,
                        "cuts": [
                            {
                                "cut_id": 1,
                                "selector": "scene1_cut1",
                                "image_generation": {
                                    "character_ids": ["hero"],
                                },
                            }
                        ],
                    }
                ],
            }
            profile = {
                "topic_label": "sample",
                "story_time": "",
                "artifact_name": "物語の証",
            }
            module = self._resume_cli_module()
            frontend = module._load_frontend_runner()

            with (
                patch.object(
                    module,
                    "_resume_profile",
                    return_value=(profile, manifest),
                ),
                patch.object(module, "_archive_p400_review_evidence"),
                patch.object(module, "_resume_state_updates", return_value={}),
                patch.object(frontend, "_prepare_authoring_grounding"),
                patch.object(frontend, "_refresh_p400_review_artifacts"),
                patch.object(frontend, "_require_fresh_p400_readiness"),
                patch.object(frontend, "_materialize_standard_request_files"),
            ):
                module.materialize_from_p500(
                    frontend,
                    run_dir=run_dir,
                    topic="sample",
                    source="sample",
                    stop_target="p650",
                )

            _text, asset_plan = load_structured_document(
                run_dir / "asset_plan.md"
            )
            entries = asset_plan["assets"]
            self.assertTrue(entries)
            for entry in entries:
                generation_plan = entry["generation_plan"]
                self.assertEqual(
                    generation_plan["reference_inputs"],
                    bound_references,
                )
                self.assertEqual(
                    generation_plan["execution_lane"],
                    "standard",
                )
                self.assertFalse(generation_plan["bootstrap_allowed"])
                self.assertIn(
                    frontend.WORLD_WALK_PROMPT_CONTRACT,
                    entry["fixed_prompts"],
                )

            _text, asset_stage_manifest = load_structured_document(
                run_dir / "asset_stage_manifest.md"
            )
            request_items = [
                scene["still_assets"][0]["image_generation"]
                for scene in asset_stage_manifest["scenes"]
            ]
            self.assertTrue(request_items)
            for item in request_items:
                self.assertEqual(item["references"], bound_references)
                self.assertEqual(item["execution_lane"], "standard")
                self.assertFalse(item["bootstrap_allowed"])
                self.assertIn("観察者POV", item["prompt"])

            request_text = (
                run_dir / "asset_generation_requests.md"
            ).read_text(encoding="utf-8")
            self.assertIn("- execution_lane: `standard`", request_text)
            self.assertIn("- bootstrap_allowed: `false`", request_text)
            for reference_rel in bound_references:
                self.assertIn(reference_rel, request_text)
            self.assertNotIn(reference_rels[4], request_text)
            self.assertIn("観察者POV", request_text)

            snapshot = json.loads(
                (
                    run_dir / "asset_generation_request_snapshot.json"
                ).read_text(encoding="utf-8")
            )
            self.assertTrue(snapshot["items"])
            for item in snapshot["items"]:
                self.assertEqual(
                    [
                        reference["path"]
                        for reference in item["references"]
                    ],
                    bound_references,
                )
                self.assertTrue(
                    all(
                        reference["deferred"] is False
                        and reference["sha256"]
                        for reference in item["references"]
                    )
                )
                self.assertIn("観察者POV", item["prompt"])

    def test_world_walk_resume_rejects_invalid_references_before_requests(
        self,
    ) -> None:
        for reference, source_run, expected_error in (
            (
                "../outside.png",
                "output/source_20260725_1200",
                "unsafe world_walk source reference",
            ),
            (
                "assets/source_references/characters/missing.png",
                "output/missing-source",
                "verified checkpoint does not contain every required",
            ),
        ):
            with self.subTest(reference=reference):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    run_dir = root / "output/target"
                    run_dir.mkdir(parents=True)
                    (run_dir / "state.txt").write_text(
                        "runtime.create_mode=world_walk\n"
                        "immersive.experience=world_walk\n"
                        f"immersive.source_run={source_run}\n"
                        "---\n",
                        encoding="utf-8",
                    )
                    state_before = (run_dir / "state.txt").read_bytes()
                    manifest = {
                        "video_metadata": {
                            "topic": "sample",
                            "experience": "world_walk",
                            "source_run": source_run,
                        },
                        "world_walk_contract": {
                            "source_references": [reference],
                        },
                    }
                    build_asset_artifacts = Mock()
                    write_asset_requests = Mock()
                    materialize_scene_requests = Mock()
                    frontend = SimpleNamespace(
                        _now_iso=lambda: "2026-07-25T12:00:00+09:00",
                        _materialize_world_walk_source_references=Mock(),
                        _build_asset_artifacts_from_manifest=(
                            build_asset_artifacts
                        ),
                        _write_asset_request_files=write_asset_requests,
                        _materialize_standard_request_files=(
                            materialize_scene_requests
                        ),
                    )
                    module = self._resume_cli_module()
                    archive_p400 = Mock()

                    with (
                        patch.object(module, "REPO_ROOT", root),
                        patch.object(
                            module,
                            "_resume_profile",
                            return_value=({}, manifest),
                        ),
                        patch.object(
                            module,
                            "_archive_p400_review_evidence",
                            archive_p400,
                        ),
                        self.assertRaisesRegex(
                            P500ResumeError,
                            expected_error,
                        ),
                    ):
                        module.materialize_from_p500(
                            frontend,
                            run_dir=run_dir,
                            topic="sample",
                            source="sample",
                            stop_target="p650",
                        )

                    build_asset_artifacts.assert_not_called()
                    write_asset_requests.assert_not_called()
                    materialize_scene_requests.assert_not_called()
                    archive_p400.assert_not_called()
                    self.assertEqual(
                        (run_dir / "state.txt").read_bytes(),
                        state_before,
                    )
                    self.assertFalse((run_dir / "assets").exists())

    def test_world_walk_resume_rejects_restored_reference_contract_mismatch(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            (run_dir / "state.txt").write_text(
                "runtime.create_mode=world_walk\n"
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/source_20260725_1200\n"
                "---\n",
                encoding="utf-8",
            )
            manifest = {
                "video_metadata": {
                    "topic": "sample",
                    "experience": "world_walk",
                    "source_run": "output/source_20260725_1200",
                },
                "world_walk_contract": {
                    "source_references": [
                        "assets/source_references/characters/hero.png"
                    ],
                },
            }
            build_asset_artifacts = Mock()
            frontend = SimpleNamespace(
                _now_iso=lambda: "2026-07-25T12:00:00+09:00",
                _build_asset_artifacts_from_manifest=build_asset_artifacts,
            )
            module = self._resume_cli_module()

            with (
                patch.object(
                    module,
                    "_resume_profile",
                    return_value=({}, manifest),
                ),
                patch.object(module, "_archive_p400_review_evidence"),
                patch.object(
                    module,
                    "_preflight_world_walk_reference_restore",
                    return_value=(
                        [
                            "assets/source_references/characters/hero.png"
                        ],
                        {},
                        None,
                    ),
                ),
                patch.object(
                    module,
                    "_restore_world_walk_source_references",
                    return_value=[
                        "assets/source_references/characters/other.png"
                    ],
                ),
                self.assertRaisesRegex(
                    P500ResumeError,
                    "restored source references do not match",
                ),
            ):
                module.materialize_from_p500(
                    frontend,
                    run_dir=run_dir,
                    topic="sample",
                    source="sample",
                    stop_target="p650",
                )

            build_asset_artifacts.assert_not_called()

    def test_materialize_refreshes_p400_grounding_before_snapshot_freeze(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text(
                "video_metadata:\n  topic: sample\n  revision: before_requests\n",
                encoding="utf-8",
            )
            (run_dir / "state.txt").write_text(
                "topic=sample\nimmersive.experience=cinematic_story\n---\n",
                encoding="utf-8",
            )
            module = self._resume_cli_module()
            events: list[str] = []
            grounding_revision = {"current": 0, "frozen": -1}

            def prepare_authoring_grounding(_run_dir: Path) -> None:
                grounding_revision["current"] += 1
                events.append("authoring_grounding")

            def legacy_prepare_stage_context(
                _run_dir: Path,
                stage: str,
            ) -> None:
                grounding_revision["current"] += 1
                events.append(f"legacy_grounding:{stage}")

            def freeze_reviews(_run_dir: Path) -> None:
                grounding_revision["frozen"] = grounding_revision["current"]
                events.append("freeze_p400_snapshots")
                manifest_sha = hashlib.sha256(
                    manifest_path.read_bytes()
                ).hexdigest()
                for stage in (
                    "scene_set",
                    "scene_detail",
                    "cut_blueprint",
                    "script",
                    "production_readiness",
                ):
                    snapshot = (
                        run_dir
                        / "logs/eval"
                        / stage
                        / "round_01/review_input_snapshot.json"
                    )
                    snapshot.parent.mkdir(parents=True, exist_ok=True)
                    snapshot.write_text(
                        json.dumps(
                            {
                                "source_artifacts": [
                                    {
                                        "path": "video_manifest.md",
                                        "sha256": manifest_sha,
                                    }
                                ]
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )

            def require_current_p400(_run_dir: Path) -> None:
                self.assertEqual(
                    grounding_revision["frozen"],
                    grounding_revision["current"],
                    "p400 snapshot must bind the current authoring readsets",
                )
                events.append("require_fresh_p400")

            def materialize_scene_requests(_run_dir: Path) -> None:
                events.append("scene_requests")
                manifest_path.write_text(
                    "video_metadata:\n"
                    "  topic: sample\n"
                    "  revision: final_post_request_projection\n",
                    encoding="utf-8",
                )

            normal_asset_plan = {
                "assets": [
                    {
                        "asset_id": "normal_seed",
                        "fixed_prompts": ["通常生成"],
                        "generation_plan": {
                            "reference_inputs": [],
                            "execution_lane": "bootstrap_builtin",
                            "bootstrap_allowed": True,
                            "output": "assets/characters/normal_seed.png",
                        },
                    }
                ]
            }
            frontend = SimpleNamespace(
                _now_iso=lambda: "2026-07-25T12:00:00+09:00",
                _prepare_authoring_grounding=prepare_authoring_grounding,
                _build_asset_artifacts_from_manifest=lambda **_kwargs: (
                    {"asset_inventory": {"items": []}},
                    normal_asset_plan,
                ),
                _md_yaml=lambda _title, _payload: "fixture\n",
                _refresh_p400_review_artifacts=freeze_reviews,
                _require_fresh_p400_readiness=require_current_p400,
                _write_asset_request_files=lambda *_args: events.append(
                    "asset_requests"
                ),
                _materialize_standard_request_files=materialize_scene_requests,
            )
            profile = {
                "duration_plan": {
                    "target_seconds": 300,
                    "minimum_effective_seconds": 240,
                    "minimum_scene_count": 8,
                    "minimum_narration_seconds": 180,
                }
            }
            manifest = {
                "video_metadata": {
                    "topic": "sample",
                    "experience": "cinematic_story",
                }
            }

            with (
                patch.object(
                    module,
                    "_resume_profile",
                    return_value=(profile, manifest),
                ),
                patch.object(module, "_archive_p400_review_evidence"),
                patch.object(
                    module,
                    "_prepare_stage_context",
                    side_effect=legacy_prepare_stage_context,
                ),
            ):
                module.materialize_from_p500(
                    frontend,
                    run_dir=run_dir,
                    topic="sample",
                    source="sample",
                    stop_target="p650",
                )

            self.assertEqual(
                events,
                [
                    "authoring_grounding",
                    "freeze_p400_snapshots",
                    "require_fresh_p400",
                    "asset_requests",
                    "scene_requests",
                    "authoring_grounding",
                    "freeze_p400_snapshots",
                    "require_fresh_p400",
                ],
            )
            self.assertEqual(
                normal_asset_plan,
                {
                    "assets": [
                        {
                            "asset_id": "normal_seed",
                            "fixed_prompts": ["通常生成"],
                            "generation_plan": {
                                "reference_inputs": [],
                                "execution_lane": "bootstrap_builtin",
                                "bootstrap_allowed": True,
                                "output": (
                                    "assets/characters/normal_seed.png"
                                ),
                            },
                        }
                    ]
                },
            )
            final_manifest_sha = hashlib.sha256(
                manifest_path.read_bytes()
            ).hexdigest()
            for stage in (
                "scene_set",
                "scene_detail",
                "cut_blueprint",
                "script",
                "production_readiness",
            ):
                snapshot = json.loads(
                    (
                        run_dir
                        / "logs/eval"
                        / stage
                        / "round_01/review_input_snapshot.json"
                    ).read_text(encoding="utf-8")
                )
                manifest_source = next(
                    item
                    for item in snapshot["source_artifacts"]
                    if item["path"] == "video_manifest.md"
                )
                self.assertEqual(
                    manifest_source["sha256"],
                    final_manifest_sha,
                    stage,
                )

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
                _refresh_downstream_review_artifacts=lambda _run_dir: None,
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

    def test_continue_run_keeps_downstream_grounding_after_request_materialization(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            (run_dir / "state.txt").write_text(
                "topic=sample\n---\n",
                encoding="utf-8",
            )
            module = self._resume_cli_module()
            events: list[str] = []

            async def generate_images(_run_dir: Path, _stop_target: str) -> None:
                events.append("generate_images")

            frontend = SimpleNamespace(
                _run_materialization_lock=lambda _run_dir: nullcontext(),
                generate_images=generate_images,
                write_run_index=lambda _run_dir: events.append("write_index"),
                validate=lambda *_args: None,
                _refresh_downstream_review_artifacts=lambda _run_dir: events.append(
                    "downstream_reviews"
                ),
            )
            with (
                patch.object(module, "_load_frontend_runner", return_value=frontend),
                patch.object(
                    module,
                    "materialize_from_p500",
                    side_effect=lambda *_args, **_kwargs: events.append(
                        "requests_materialized"
                    ),
                ),
                patch.object(
                    module,
                    "_prepare_resume_grounding",
                    side_effect=lambda *_args, **_kwargs: events.append(
                        "downstream_grounding"
                    ),
                ),
                patch.object(
                    module,
                    "_finalize_resume_orchestration",
                    return_value={},
                ),
                patch(
                    "server.image_gen_app._mark_asset_generation_handoff"
                ),
            ):
                module._continue_run(
                    run_dir=run_dir,
                    topic="sample",
                    source="sample",
                    stop_target="p650",
                    materialize_only=False,
                    skip_validation=True,
                )

            self.assertLess(
                events.index("requests_materialized"),
                events.index("downstream_grounding"),
            )
            self.assertLess(
                events.index("downstream_grounding"),
                events.index("downstream_reviews"),
            )
            self.assertLess(
                events.index("downstream_reviews"),
                events.index("generate_images"),
            )

    def test_scene_storyboard_p680_continuation_finalizes_after_images_before_validation(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            (run_dir / "state.txt").write_text(
                "topic=sample\nruntime.create_mode=scene_storyboard\n---\n",
                encoding="utf-8",
            )
            module = self._resume_cli_module()
            events: list[str] = []

            async def generate_images(
                _run_dir: Path,
                _stop_target: str,
            ) -> None:
                events.append("generate_images")

            frontend = SimpleNamespace(
                _run_materialization_lock=lambda _run_dir: nullcontext(),
                generate_images=generate_images,
                write_run_index=lambda _run_dir: events.append("write_index"),
                validate=lambda *_args: events.append("final_validation"),
                _refresh_downstream_review_artifacts=lambda _run_dir: events.append(
                    "downstream_reviews"
                ),
            )

            def resolve_mode(*_args, **_kwargs):
                events.append("resolve_mode")
                return {
                    "create_mode": "scene_storyboard",
                    "experience": "cinematic_story",
                    "source_run": "",
                    "state_updates": {
                        "runtime.create_mode": "scene_storyboard",
                    },
                }

            with (
                patch.object(
                    module,
                    "_load_frontend_runner",
                    return_value=frontend,
                ),
                patch.object(module, "materialize_from_p500"),
                patch.object(module, "_prepare_resume_grounding"),
                patch.object(
                    module,
                    "_resolve_resume_mode_contract",
                    side_effect=resolve_mode,
                ),
                patch.object(
                    module,
                    "_finalize_resume_orchestration",
                    return_value={},
                ),
                patch(
                    "server.image_gen_app._finalize_scene_storyboard_p680",
                    side_effect=lambda _run_id: events.append(
                        "storyboard_finalizer"
                    ),
                ),
            ):
                module._continue_run(
                    run_dir=run_dir,
                    topic="sample",
                    source="sample",
                    stop_target="p680",
                    materialize_only=False,
                    skip_validation=False,
                )

            self.assertLess(
                events.index("generate_images"),
                events.index("resolve_mode"),
            )
            self.assertLess(
                events.index("resolve_mode"),
                events.index("storyboard_finalizer"),
            )
            self.assertLess(
                events.index("storyboard_finalizer"),
                events.index("final_validation"),
            )

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

    def test_legacy_cli_missing_exact_source_fails_before_apply(self) -> None:
        module = self._resume_cli_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            with (
                patch.object(module, "REPO_ROOT", root),
                patch(
                    "toc.p500_resume._p400_readiness",
                    return_value=("approved", ()),
                ),
                patch.object(
                    sys,
                    "argv",
                    [
                        "resume-from-p500.py",
                        "--run-dir",
                        str(run_dir),
                        "--checkpoint-id",
                        "legacy-missing-source",
                    ],
                ),
                self.assertRaisesRegex(SystemExit, "1"),
            ):
                module.main()

        self.assertFalse(
            (run_dir / "logs/resume/p500/legacy-missing-source").exists()
        )

    def test_legacy_cli_plan_token_rejects_source_changed_after_dry_run(
        self,
    ) -> None:
        module = self._resume_cli_module()
        source_a = "exact legacy source A\n"
        source_b = "exact legacy source B\n"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            with (
                patch.object(module, "REPO_ROOT", root),
                patch(
                    "toc.p500_resume._p400_readiness",
                    return_value=("approved", ()),
                ),
                patch.object(
                    sys,
                    "argv",
                    [
                        "resume-from-p500.py",
                        "--run-dir",
                        str(run_dir),
                        "--checkpoint-id",
                        "legacy-source-bound",
                        "--source",
                        source_a,
                    ],
                ),
                patch("builtins.print") as dry_print,
            ):
                module.main()
            dry_payload = json.loads(dry_print.call_args.args[0])
            apply_resume = Mock()
            with (
                patch.object(module, "REPO_ROOT", root),
                patch(
                    "toc.p500_resume._p400_readiness",
                    return_value=("approved", ()),
                ),
                patch.object(module, "apply_resume_plan", apply_resume),
                patch.object(
                    sys,
                    "argv",
                    [
                        "resume-from-p500.py",
                        "--run-dir",
                        str(run_dir),
                        "--checkpoint-id",
                        "legacy-source-bound",
                        "--source",
                        source_b,
                        "--plan-token",
                        dry_payload["plan_token"],
                        "--apply",
                    ],
                ),
                self.assertRaisesRegex(SystemExit, "1"),
            ):
                module.main()

        apply_resume.assert_not_called()

    def test_legacy_cli_plan_token_rejects_resolved_topic_change(
        self,
    ) -> None:
        module = self._resume_cli_module()
        exact_source = "same exact legacy source\n"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            state_path = run_dir / "state.txt"
            state_path.write_text(
                state_path.read_text(encoding="utf-8").replace(
                    "topic=sample\n",
                    "",
                ),
                encoding="utf-8",
            )
            with (
                patch.object(module, "REPO_ROOT", root),
                patch(
                    "toc.p500_resume._p400_readiness",
                    return_value=("approved", ()),
                ),
                patch.object(
                    sys,
                    "argv",
                    [
                        "resume-from-p500.py",
                        "--run-dir",
                        str(run_dir),
                        "--topic",
                        "resolved topic A",
                        "--checkpoint-id",
                        "legacy-topic-bound",
                        "--source",
                        exact_source,
                    ],
                ),
                patch("builtins.print") as dry_print,
            ):
                module.main()
            dry_payload = json.loads(dry_print.call_args.args[0])
            apply_resume = Mock()
            with (
                patch.object(module, "REPO_ROOT", root),
                patch(
                    "toc.p500_resume._p400_readiness",
                    return_value=("approved", ()),
                ),
                patch.object(module, "apply_resume_plan", apply_resume),
                patch.object(
                    sys,
                    "argv",
                    [
                        "resume-from-p500.py",
                        "--run-dir",
                        str(run_dir),
                        "--topic",
                        "resolved topic B",
                        "--checkpoint-id",
                        "legacy-topic-bound",
                        "--source",
                        exact_source,
                        "--plan-token",
                        dry_payload["plan_token"],
                        "--apply",
                    ],
                ),
                self.assertRaisesRegex(SystemExit, "1"),
            ):
                module.main()

        apply_resume.assert_not_called()

    def test_legacy_cli_plan_token_accepts_same_source_without_raw_input(
        self,
    ) -> None:
        module = self._resume_cli_module()
        exact_source = "exact legacy multiline source\n\nsecond line\n"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            with (
                patch.object(module, "REPO_ROOT", root),
                patch(
                    "toc.p500_resume._p400_readiness",
                    return_value=("approved", ()),
                ),
                patch.object(
                    sys,
                    "argv",
                    [
                        "resume-from-p500.py",
                        "--run-dir",
                        str(run_dir),
                        "--checkpoint-id",
                        "legacy-source-same",
                        "--source",
                        exact_source,
                    ],
                ),
                patch("builtins.print") as dry_print,
            ):
                module.main()
            dry_json = dry_print.call_args.args[0]
            dry_payload = json.loads(dry_json)
            apply_resume = Mock(
                return_value=run_dir
                / "logs/resume/p500/legacy-source-same"
            )
            with (
                patch.object(module, "REPO_ROOT", root),
                patch(
                    "toc.p500_resume._p400_readiness",
                    return_value=("approved", ()),
                ),
                patch.object(module, "apply_resume_plan", apply_resume),
                patch.object(
                    sys,
                    "argv",
                    [
                        "resume-from-p500.py",
                        "--run-dir",
                        str(run_dir),
                        "--checkpoint-id",
                        "legacy-source-same",
                        "--source",
                        exact_source,
                        "--plan-token",
                        dry_payload["plan_token"],
                        "--apply",
                    ],
                ),
                patch("builtins.print"),
            ):
                module.main()

        self.assertNotIn(exact_source, dry_json)
        self.assertEqual(
            dry_payload["resume_input_identity"],
            {
                "schema_version": "toc.p500_resume.input_identity.v1",
                "source_sha256": hashlib.sha256(
                    exact_source.encode("utf-8")
                ).hexdigest(),
                "topic_sha256": hashlib.sha256(b"sample").hexdigest(),
            },
        )
        apply_resume.assert_called_once()

    def test_world_walk_cli_rejects_unsafe_contract_before_apply_mutation(
        self,
    ) -> None:
        module = self._resume_cli_module()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            source_run = root / "output/source_20260725_1200"
            (source_run / "story.md").parent.mkdir(parents=True)
            (source_run / "story.md").write_text(
                "source story\n",
                encoding="utf-8",
            )
            source_asset = source_run / "assets/characters/hero.png"
            source_asset.parent.mkdir(parents=True)
            source_asset.write_bytes(b"source")
            (run_dir / "state.txt").write_text(
                "topic=sample\n"
                "runtime.create_mode=world_walk\n"
                "immersive.experience=world_walk\n"
                "immersive.source_run=output/source_20260725_1200\n"
                "---\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "```yaml\n"
                "video_metadata:\n"
                "  topic: sample\n"
                "  experience: world_walk\n"
                "  source_run: output/source_20260725_1200\n"
                "world_walk_contract:\n"
                "  source_references:\n"
                "    - ../outside.png\n"
                "```\n",
                encoding="utf-8",
            )
            with patch(
                "toc.p500_resume._p400_readiness",
                return_value=("approved", ()),
            ):
                plan = build_resume_plan(
                    repo_root=root,
                    run_dir=run_dir,
                    checkpoint_id="unsafe-world-walk",
                )
            state_before = (run_dir / "state.txt").read_bytes()
            asset_plan_before = (run_dir / "asset_plan.md").read_bytes()

            with (
                patch.object(module, "REPO_ROOT", root),
                patch(
                    "toc.p500_resume._p400_readiness",
                    return_value=("approved", ()),
                ),
                patch.object(
                    sys,
                    "argv",
                    [
                        "resume-from-p500.py",
                        "--run-dir",
                        str(run_dir),
                        "--source",
                        "exact original source",
                        "--checkpoint-id",
                        "unsafe-world-walk",
                        "--plan-token",
                        plan.plan_token,
                        "--apply",
                    ],
                ),
                self.assertRaisesRegex(SystemExit, "1"),
            ):
                module.main()

            self.assertEqual((run_dir / "state.txt").read_bytes(), state_before)
            self.assertEqual(
                (run_dir / "asset_plan.md").read_bytes(),
                asset_plan_before,
            )
            self.assertFalse(Path(plan.checkpoint_dir).exists())

    def test_canonical_create_input_preserves_multiline_source_and_rejects_conflict(
        self,
    ) -> None:
        module = self._resume_cli_module()
        exact_source = "第一段落。  \n\n第二段落。末尾改行を保持。\n"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            self._write_create_input(run_dir, source=exact_source)
            (run_dir / "video_manifest.md").write_text(
                "```yaml\n"
                "video_metadata:\n"
                "  topic: sample\n"
                "  experience: cinematic_story\n"
                "  target_duration_seconds: 300\n"
                "```\n",
                encoding="utf-8",
            )
            mode_contract = {
                "experience": "cinematic_story",
                "source_run": "",
            }

            resolved = module._resolve_exact_resume_source(
                run_dir=run_dir,
                topic="sample",
                explicit_source="",
                mode_contract=mode_contract,
            )

            self.assertEqual(resolved, exact_source)
            with self.assertRaisesRegex(
                P500ResumeError,
                "conflicts with canonical create input",
            ):
                module._resolve_exact_resume_source(
                    run_dir=run_dir,
                    topic="sample",
                    explicit_source="different source",
                    mode_contract=mode_contract,
                )

    def test_future_world_walk_resume_uses_canonical_exact_story_source(
        self,
    ) -> None:
        module = self._resume_cli_module()
        exact_story = "# Reviewed Story\n\n世界観散歩に使った本文。  \n"
        source_run = "output/source_20990101_0000"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = self._run_fixture(root)
            self._write_create_input(
                run_dir,
                topic="世界観散歩",
                source=exact_story,
                experience="world_walk",
                source_run=source_run,
            )
            (run_dir / "state.txt").write_text(
                "topic=世界観散歩\n"
                "runtime.create_mode=world_walk\n"
                "immersive.experience=world_walk\n"
                f"immersive.source_run={source_run}\n"
                "runtime.target_video_seconds=300\n"
                "---\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "```yaml\n"
                "video_metadata:\n"
                "  topic: 世界観散歩\n"
                "  experience: world_walk\n"
                f"  source_run: {source_run}\n"
                "  target_duration_seconds: 300\n"
                "```\n",
                encoding="utf-8",
            )

            resolved = module._resolve_exact_resume_source(
                run_dir=run_dir,
                topic="世界観散歩",
                explicit_source="",
                mode_contract={
                    "experience": "world_walk",
                    "source_run": source_run,
                },
            )

        self.assertEqual(resolved, exact_story)

    def test_cli_re_resolves_topic_and_explicit_source_inside_apply_lease(
        self,
    ) -> None:
        module = self._resume_cli_module()
        lock_state = {"held": False}

        class FakeLock:
            def __enter__(self):
                lock_state["held"] = True
                return self

            def __exit__(self, *_args):
                lock_state["held"] = False
                return False

        def resolve_topic(_run_dir: Path, _explicit: str) -> str:
            self.assertTrue(lock_state["held"])
            return "fresh-topic"

        plan = SimpleNamespace(
            plan_token="a" * 64,
            downstream_files=(),
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "output/sample"
            run_dir.mkdir(parents=True)
            continue_run = Mock()
            with (
                patch.object(module, "REPO_ROOT", root),
                patch.object(module, "resolve_run_dir", return_value=run_dir),
                patch.object(module, "sync_file_lock", return_value=FakeLock()),
                patch.object(module, "_topic_for_run", side_effect=resolve_topic),
                patch.object(module, "build_resume_plan", return_value=plan),
                patch.object(
                    module,
                    "apply_resume_plan",
                    return_value=run_dir / "checkpoint",
                ),
                patch.object(module, "_continue_run", continue_run),
                patch.object(
                    sys,
                    "argv",
                    [
                        "resume-from-p500.py",
                        "--run-dir",
                        str(run_dir),
                        "--checkpoint-id",
                        "api-test",
                        "--source",
                        "exact legacy source",
                        "--plan-token",
                        "a" * 64,
                        "--apply",
                        "--continue-to",
                        "p680",
                    ],
                ),
            ):
                module.main()

        continue_run.assert_called_once_with(
            run_dir=run_dir,
            topic="fresh-topic",
            source="exact legacy source",
            stop_target="p680",
            materialize_only=False,
            skip_validation=False,
        )

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
