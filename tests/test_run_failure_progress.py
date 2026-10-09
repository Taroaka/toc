from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import image_gen, image_gen_app


INDEX = """# Run Index

## Stage Table

| P# | Stage | Current State |
| --- | --- | --- |
| `p000` | Run Entrance | `always_available` |
| `p100` | Research | `done` |
| `p200` | Story | `in_progress` |
| `p300` | Visual Planning | `done` |
| `p400` | Script | `failed` |
| `p600` | Scene | `pending` |

## Fixed Slot Contract

| Slot | Stage | Default Requirement | Purpose | Planned Artifacts |
| --- | --- | --- | --- | --- |
| `p220` | Story | `required` | Story Authoring | - |
| `p410` | Script | `required` | Cinematic Scene Authoring | - |
| `p420` | Script | `required` | Cut Blueprint | - |
| `p650` | Scene | `optional` | Generation Ready | - |
| `p660` | Scene | `optional` | Image Generation | - |
| `p670` | Scene | `optional` | Image QA | - |
| `p680` | Scene | `optional` | Image Handoff | - |

#### p220 Story Authoring

- status: `in_progress`

#### p410 Cinematic Scene Authoring

- status: `failed`

#### p420 Cut Blueprint

- status: `pending`

#### p650 Generation Ready

- status: `pending`

#### p660 Image Generation

- status: `pending`

#### p670 Image QA

- status: `pending`

#### p680 Image Handoff

- status: `pending`
"""


def _write_run(run_dir: Path, state: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.txt").write_text(state, encoding="utf-8")
    (run_dir / "p000_index.md").write_text(INDEX, encoding="utf-8")


def test_terminal_failure_overrides_stale_running_projection() -> None:
    with TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        _write_run(
            run_dir,
            "\n".join(
                [
                    "topic=Example",
                    "status=FAILED",
                    "runtime.stage=cinematic_authoring_failed",
                    "runtime.create_job.status=running",
                    "slot.p220.status=in_progress",
                    "slot.p410.status=failed",
                    "slot.p420.status=pending",
                    "last_error=authoring process exited with status 1",
                    "",
                ]
            ),
        )
        validation = run_dir / "logs/authoring/p400/validation.json"
        validation.parent.mkdir(parents=True)
        validation.write_text(
            json.dumps({"status": "failed", "error": "field_invalid:/cuts/1/allowed_new_reveal_elements/0"}),
            encoding="utf-8",
        )

        progress = image_gen.read_run_progress(run_dir, validate_request_outputs=False)

    assert progress["status"] == "FAILED"
    assert progress["failure"]["terminal"] is True
    assert progress["failure"]["stage"] == "p410"
    assert progress["failure"]["message"] == "field_invalid:/cuts/1/allowed_new_reveal_elements/0"
    assert progress["currentStage"] == {
        "code": "p410",
        "label": "Cinematic Scene Authoring",
        "state": "failed",
    }
    assert next(slot for slot in progress["slots"] if slot["code"] == "p220")["state"] == "blocked"


def test_active_repair_stays_running_until_terminal_failure_is_published() -> None:
    with TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        _write_run(
            run_dir,
            "\n".join(
                [
                    "topic=Example",
                    "status=AUTHORING",
                    "runtime.stage=cinematic_authoring",
                    "runtime.repair.phase=repairing",
                    "runtime.repair.stage=p420",
                    "runtime.repair.target=handoff",
                    "runtime.repair.reason=field_invalid:/cuts/1",
                    "slot.p220.status=done",
                    "slot.p410.status=in_progress",
                    "slot.p420.status=in_progress",
                    "",
                ]
            ),
        )

        progress = image_gen.read_run_progress(run_dir, validate_request_outputs=False)

    assert progress["failure"]["terminal"] is False
    assert progress["repair"]["phase"] == "repairing"
    assert progress["currentStage"]["code"] == "p420"
    assert progress["currentStage"]["state"] == "in_progress"


def test_active_repair_ignores_historical_failed_slot_marker() -> None:
    with TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        _write_run(
            run_dir,
            "\n".join(
                [
                    "topic=Example",
                    "status=AUTHORING",
                    "runtime.stage=cinematic_authoring",
                    "runtime.repair.phase=repairing",
                    "runtime.repair.stage=p420",
                    "slot.p410.status=failed",
                    "slot.p420.status=in_progress",
                    "",
                ]
            ),
        )

        progress = image_gen.read_run_progress(run_dir, validate_request_outputs=False)

    assert progress["failure"]["terminal"] is False
    assert progress["currentStage"]["code"] == "p420"


def test_failed_active_slot_is_terminal_when_repair_is_idle() -> None:
    with TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        _write_run(
            run_dir,
            "\n".join(
                [
                    "topic=Example",
                    "status=AUTHORING",
                    "runtime.stage=cinematic_authoring",
                    "runtime.repair.phase=idle",
                    "slot.p220.status=done",
                    "slot.p410.status=failed",
                    "",
                ]
            ),
        )

        progress = image_gen.read_run_progress(run_dir, validate_request_outputs=False)

    assert progress["failure"]["terminal"] is True
    assert progress["failure"]["stage"] == "p410"
    assert progress["currentStage"]["code"] == "p410"


def test_active_runtime_stage_mapping_uses_exact_downstream_slots() -> None:
    assert image_gen._active_slot_from_state({"runtime.stage": "cinematic_projection"}) == "p420"
    assert image_gen._active_slot_from_state({"runtime.stage": "render_inputs_frozen"}) == "p910"


def test_explicit_active_runtime_stage_overrides_stale_earlier_running_slot() -> None:
    with TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        _write_run(
            run_dir,
            "\n".join(
                [
                    "topic=Example",
                    "status=AUTHORING",
                    "runtime.stage=cinematic_authoring",
                    "slot.p220.status=in_progress",
                    "slot.p410.status=in_progress",
                    "",
                ]
            ),
        )

        progress = image_gen.read_run_progress(run_dir, validate_request_outputs=False)

    assert progress["failure"]["terminal"] is False
    assert progress["currentStage"]["code"] == "p410"
    assert next(slot for slot in progress["slots"] if slot["code"] == "p220")["state"] == "blocked"


def test_explicit_p680_failure_promotes_pending_handoff_to_failure() -> None:
    with TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        _write_run(
            run_dir,
            "\n".join(
                [
                    "topic=Example",
                    "status=P650",
                    "runtime.stage=p680_terminal_verification_failed",
                    "runtime.failure.stage=p680",
                    "runtime.failure.phase=terminal_verification",
                    "runtime.failure.error_kind=validation_failed",
                    "slot.p650.status=done",
                    "slot.p660.status=done",
                    "slot.p670.status=pending",
                    "slot.p680.status=pending",
                    "last_error=handoff validation failed",
                    "",
                ]
            ),
        )

        progress = image_gen.read_run_progress(run_dir, validate_request_outputs=False)

    assert progress["status"] == "FAILED"
    assert progress["failure"]["stage"] == "p680"
    assert progress["currentStage"]["code"] == "p680"
    assert progress["currentStage"]["state"] == "failed"


def test_create_job_status_reconciles_canonical_failure_when_memory_is_stale() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_id = "example_run"
        run_dir = root / "output" / run_id
        _write_run(
            run_dir,
            "\n".join(
                [
                    "topic=Example",
                    "status=FAILED",
                    "runtime.stage=cinematic_authoring_failed",
                    "slot.p410.status=failed",
                    "last_error=authoring process exited with status 1",
                    "",
                ]
            ),
        )
        job_id = "job-stale"
        image_gen_app._create_jobs[job_id] = {
            "jobId": job_id,
            "runId": run_id,
            "status": "running",
            "message": "作成中",
        }
        try:
            with patch.object(image_gen_app, "ROOT", root):
                job = asyncio.run(image_gen_app.api_create_run_status(job_id))
        finally:
            image_gen_app._create_jobs.pop(job_id, None)

    assert job["status"] == "failed"
    assert job["error"] == "authoring process exited with status 1"
    assert job["message"] == "作成失敗"


def test_process_status_falls_back_to_canonical_failure_when_store_is_unavailable() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_id = "example_run"
        run_dir = root / "output" / run_id
        _write_run(
            run_dir,
            "\n".join(
                [
                    "topic=Example",
                    "status=FAILED",
                    "runtime.stage=cinematic_authoring_failed",
                    "slot.p410.status=failed",
                    "last_error=authoring process exited with status 1",
                    "",
                ]
            ),
        )
        with (
            patch.object(image_gen_app, "ROOT", root),
            patch.object(
                image_gen_app.process_store,
                "get_process_run",
                side_effect=RuntimeError("psycopg is unavailable"),
            ),
        ):
            payload = asyncio.run(image_gen_app.api_run_process(run_id))

    assert payload["status"] == "failed"
    assert payload["currentProcess"] == "p410"
    assert payload["error"] == "authoring process exited with status 1"


def test_failure_diagnostic_uses_effective_stage_and_redacts_credentials() -> None:
    with TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        _write_run(
            run_dir,
            "\n".join(
                [
                    "topic=Example",
                    "status=P650",
                    "runtime.stage=cinematic_authoring_failed",
                    "runtime.failure.stage=p660",
                    "slot.p660.status=failed",
                    "image_generation.error=Authorization: Bearer sk-secret token another-secret access_token=url-secret",
                    "last_error=old cinematic authoring error",
                    "",
                ]
            ),
        )
        validation = run_dir / "logs/authoring/p400/validation.json"
        validation.parent.mkdir(parents=True)
        validation.write_text(json.dumps({"error": "old p400 error"}), encoding="utf-8")

        progress = image_gen.read_run_progress(run_dir, validate_request_outputs=False)

    assert progress["failure"]["stage"] == "p660"
    assert "old p400 error" not in progress["failure"]["message"]
    assert "sk-secret" not in progress["failure"]["message"]
    assert "another-secret" not in progress["failure"]["message"]
    assert "<redacted>" in progress["failure"]["message"]
    assert image_gen._redact_failure_secrets("Authorization: Basic encoded-secret") == "Authorization: <redacted>"
    assert image_gen._redact_failure_secrets("token sk-secret") == "token <redacted>"


def test_redaction_handles_spaced_and_json_token_values() -> None:
    assert image_gen._redact_failure_secrets("token: fake-credential") == "token: <redacted>"
    assert image_gen._redact_failure_secrets("token = fake-credential") == "token = <redacted>"
    assert image_gen._redact_failure_secrets('{"token": "fake-credential"}') == '{"token": <redacted>}'


def test_non_media_failure_prefers_current_last_error_over_stale_image_error() -> None:
    with TemporaryDirectory() as tmp:
        run_dir = Path(tmp)
        _write_run(
            run_dir,
            "\n".join(
                [
                    "topic=Example",
                    "status=FAILED",
                    "runtime.stage=cinematic_authoring_failed",
                    "slot.p410.status=failed",
                    "image_generation.error=stale image failure",
                    "last_error=current authoring failure",
                    "",
                ]
            ),
        )

        progress = image_gen.read_run_progress(run_dir, validate_request_outputs=False)

    assert progress["failure"]["message"] == "current authoring failure"


def test_resume_job_does_not_reconcile_the_failure_it_started_from() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_id = "example_run"
        run_dir = root / "output" / run_id
        _write_run(
            run_dir,
            "\n".join(
                [
                    "topic=Example",
                    "status=FAILED",
                    "runtime.stage=cinematic_authoring_failed",
                    "slot.p410.status=failed",
                    "last_error=authoring process exited with status 1",
                    "",
                ]
            ),
        )
        job = {
            "jobId": "resume-job",
            "runId": run_id,
            "status": "running",
            "message": "再開中",
        }
        progress = image_gen.read_run_progress(run_dir, validate_request_outputs=False)
        failure = progress["failure"]
        image_gen_app._create_job_failure_baselines["resume-job"] = (
            failure["stage"], failure["runtimeStage"], failure["message"],
        )
        image_gen_app._resume_tasks["resume-job"] = SimpleNamespace(done=lambda: False)
        try:
            with patch.object(image_gen_app, "ROOT", root):
                reconciled = image_gen_app._reconcile_create_job_with_run_state(job)
        finally:
            image_gen_app._create_job_failure_baselines.pop("resume-job", None)
            image_gen_app._resume_tasks.pop("resume-job", None)

    assert reconciled["status"] == "running"


def test_completed_job_is_not_overwritten_by_a_stale_run_failure() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_id = "example_run"
        run_dir = root / "output" / run_id
        _write_run(
            run_dir,
            "status=FAILED\nruntime.stage=cinematic_authoring_failed\nslot.p410.status=failed\n",
        )
        with patch.object(image_gen_app, "ROOT", root):
            reconciled = image_gen_app._reconcile_create_job_with_run_state(
                {"jobId": "completed-job", "runId": run_id, "status": "completed"}
            )

    assert reconciled["status"] == "completed"


def test_resume_baseline_is_reconciled_after_worker_task_finishes() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_id = "example_run"
        run_dir = root / "output" / run_id
        _write_run(
            run_dir,
            "status=FAILED\nruntime.stage=cinematic_authoring_failed\nslot.p410.status=failed\nlast_error=same failure\n",
        )
        job = {"jobId": "resume-job", "runId": run_id, "status": "running"}
        with patch.object(image_gen_app, "ROOT", root):
            progress = image_gen.read_run_progress(run_dir, validate_request_outputs=False)
            failure = progress["failure"]
            image_gen_app._create_job_failure_baselines["resume-job"] = (
                failure["stage"], failure["runtimeStage"], failure["message"],
            )
            try:
                reconciled = image_gen_app._reconcile_create_job_with_run_state(job)
            finally:
                image_gen_app._create_job_failure_baselines.pop("resume-job", None)

    assert reconciled["status"] == "failed"


def test_resume_task_cleanup_removes_failure_baseline() -> None:
    task = SimpleNamespace(done=lambda: True)
    image_gen_app._resume_tasks["resume-cleanup"] = task
    image_gen_app._create_job_failure_baselines["resume-cleanup"] = ("p410", "stage", "error")
    try:
        image_gen_app._cleanup_resume_task(task, "resume-cleanup")
    finally:
        image_gen_app._resume_tasks.pop("resume-cleanup", None)
        image_gen_app._create_job_failure_baselines.pop("resume-cleanup", None)

    assert "resume-cleanup" not in image_gen_app._resume_tasks
    assert "resume-cleanup" not in image_gen_app._create_job_failure_baselines
