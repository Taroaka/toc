from __future__ import annotations

import asyncio
import sys
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import image_gen_app
from toc.harness import parse_state_file


def _run_dir(root: Path, run_id: str = "resume_run") -> Path:
    run_dir = root / "output" / run_id
    (run_dir / ".locks").mkdir(parents=True)
    (run_dir / "state.txt").write_text(
        "status=P500\n"
        "runtime.stage=p500_resume_materializing\n"
        "runtime.resume.p500.status=materializing\n"
        "last_error=\n",
        encoding="utf-8",
    )
    return run_dir


def _bound_worker_patches(root: Path, *, subprocess_error: Exception):
    return (
        patch.object(image_gen_app, "ROOT", root),
        patch.object(image_gen_app, "_resume_create_mode_for_run", return_value=image_gen_app.CREATE_MODE_NORMAL),
        patch.object(image_gen_app, "_requires_authoring_resume", return_value=False),
        patch.object(
            image_gen_app,
            "_run_p500_resume_subprocess",
            AsyncMock(side_effect=subprocess_error),
        ),
        patch.object(image_gen_app, "_set_create_job", AsyncMock()),
        patch.object(image_gen_app, "_sync_process_current_process", AsyncMock()),
        patch.object(image_gen_app, "write_app_server_debug_log"),
        patch.object(image_gen_app, "_release_run_execution_lease", AsyncMock()),
    )


def test_p500_worker_failure_publishes_terminal_canonical_state() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_id = "resume_run"
        _run_dir(root, run_id)
        with ExitStack() as stack:
            for patcher in _bound_worker_patches(
                root,
                subprocess_error=RuntimeError("Manifest is still in skeleton phase"),
            ):
                stack.enter_context(patcher)
            try:
                asyncio.run(
                    image_gen_app._run_p500_resume_job_bound(
                        "resume-job",
                        run_id=run_id,
                        create_mode=image_gen_app.CREATE_MODE_NORMAL,
                    )
                )
            finally:
                pass

        state = parse_state_file(root / "output" / run_id / "state.txt")

    assert state["status"] == "FAILED"
    assert state["runtime.stage"] == "p500_resume_failed"
    assert state["runtime.resume.p500.status"] == "failed"
    assert state["last_error"]


def test_p500_worker_preserves_child_failure_stage_when_publishing_terminal_state() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_id = "resume_run"
        run_dir = _run_dir(root, run_id)
        (run_dir / "state.txt").write_text(
            "status=P500\n"
            "runtime.stage=semantic_review_failed_before_media_generation\n"
            "runtime.failure.stage=p570\n"
            "runtime.failure.phase=semantic_review\n"
            "runtime.resume.p500.status=materializing\n",
            encoding="utf-8",
        )
        with ExitStack() as stack:
            for patcher in _bound_worker_patches(root, subprocess_error=RuntimeError("child failed")):
                stack.enter_context(patcher)
            try:
                asyncio.run(
                    image_gen_app._run_p500_resume_job_bound(
                        "resume-job",
                        run_id=run_id,
                        create_mode=image_gen_app.CREATE_MODE_NORMAL,
                    )
                )
            finally:
                pass

        state = parse_state_file(run_dir / "state.txt")

    assert state["status"] == "FAILED"
    assert state["runtime.stage"] == "semantic_review_failed_before_media_generation"
    assert state["runtime.failure.stage"] == "p570"
    assert state["runtime.resume.p500.status"] == "failed"


def test_p500_wrapper_early_exception_publishes_failure_before_releasing_job() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_id = "resume_run"
        _run_dir(root, run_id)
        set_job = AsyncMock()
        with (
            patch.object(image_gen_app, "ROOT", root),
            patch.object(
                image_gen_app,
                "_run_p500_resume_job_bound",
                AsyncMock(side_effect=RuntimeError("resume setup failed")),
            ),
            patch.object(image_gen_app, "_set_create_job", set_job),
            patch.object(image_gen_app, "_release_run_execution_lease", AsyncMock()),
        ):
            asyncio.run(
                image_gen_app._run_p500_resume_job(
                    "resume-job",
                    run_id=run_id,
                    create_mode=image_gen_app.CREATE_MODE_NORMAL,
                )
            )

        state = parse_state_file(root / "output" / run_id / "state.txt")

    assert state["status"] == "FAILED"
    assert state["runtime.resume.p500.status"] == "failed"
    assert set_job.await_args_list[-1].args[1]["status"] == "failed"


def test_p500_worker_preserves_child_transport_block_without_failure_metadata() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_id = "resume_run"
        run_dir = _run_dir(root, run_id)
        (run_dir / "state.txt").write_text(
            "status=P500\n"
            "runtime.stage=semantic_review_blocked_transport\n"
            "runtime.resume.p500.status=materializing\n",
            encoding="utf-8",
        )
        with ExitStack() as stack:
            for patcher in _bound_worker_patches(root, subprocess_error=RuntimeError("child failed")):
                stack.enter_context(patcher)
            try:
                asyncio.run(
                    image_gen_app._run_p500_resume_job_bound(
                        "resume-job",
                        run_id=run_id,
                        create_mode=image_gen_app.CREATE_MODE_NORMAL,
                    )
                )
            finally:
                pass

        state = parse_state_file(run_dir / "state.txt")

    assert state["status"] == "FAILED"
    assert state["runtime.stage"] == "semantic_review_blocked_transport"
    assert state["runtime.resume.p500.status"] == "failed"

