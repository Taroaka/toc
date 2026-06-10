#!/usr/bin/env python3
"""Run contextless semantic review for one ToC stage."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.codex_app_server import create_codex_app_server_client, classify_codex_transport_error, is_codex_transport_error  # noqa: E402
from toc.harness import append_state_snapshot, now_iso  # noqa: E402
from toc.semantic_review import (  # noqa: E402
    IMAGE_PROMPT_JUDGMENT_REPORT,
    SemanticReviewStatus,
    SEMANTIC_REVIEW_STAGES,
    check_image_prompt_judgment,
    check_semantic_review,
    parse_judgment_report_status,
    review_status_to_state,
    semantic_review_relpaths,
)
from toc.semantic_review_loop import (  # noqa: E402
    SEMANTIC_REVIEW_PRODUCER_TARGETS,
    semantic_loop_state_updates,
    semantic_repair_state_updates,
    semantic_repair_relpaths,
    semantic_repair_timeout_seconds,
    semantic_review_max_attempts,
    semantic_review_timeout_seconds,
    write_semantic_repair_prompt,
)


def _slot_for_stage(stage: str) -> str:
    target = SEMANTIC_REVIEW_PRODUCER_TARGETS.get(stage, {})
    slot = target.get("slot")
    return str(slot) if slot else ""


def _semantic_review_report_completed(report_path: Path) -> bool:
    if not report_path.exists():
        return False
    report_text = report_path.read_text(encoding="utf-8", errors="replace")
    if "`...`" in report_text or "- `...`" in report_text:
        return False
    status = parse_judgment_report_status(report_text)
    return bool(status and status != "pending")


def _semantic_repair_report_completed(report_path: Path) -> bool:
    if not report_path.exists():
        return False
    for raw in report_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip().lower()
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip(" `\"'") == "done"
    return False


SEMANTIC_TURN_ARTIFACT_POLL_SECONDS = 2.0
SEMANTIC_TURN_COMPLETION_GRACE_SECONDS = 15.0
_SEMANTIC_REPAIR_HASH_LIMIT_BYTES = 2_000_000


def _json_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _artifact_signature(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        stat = path.stat()
    except OSError as exc:
        return f"stat_error:{type(exc).__name__}"
    if not path.is_file():
        return f"not_file:{stat.st_size}:{stat.st_mtime_ns}"
    digest = ""
    if stat.st_size <= _SEMANTIC_REPAIR_HASH_LIMIT_BYTES:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            digest = f"read_error:{type(exc).__name__}"
    return f"file:{stat.st_size}:{stat.st_mtime_ns}:{digest}"


def _semantic_turn_activity_relpath(report_relpath: Path) -> Path:
    return report_relpath.with_name(f"{report_relpath.name}.app_server_activity.json")


def _write_semantic_turn_activity_marker(report_path: Path, notification: dict) -> None:
    path = report_path.with_name(f"{report_path.name}.app_server_activity.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": now_iso(),
        "method": str(notification.get("method") or ""),
    }
    params = notification.get("params")
    if isinstance(params, dict) and params.get("turnId"):
        payload["turn_id"] = str(params["turnId"])
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _review_progress_fingerprint(run_dir: Path, stage: str) -> dict[str, str]:
    relpaths = semantic_review_relpaths(stage)
    activity_relpath = _semantic_turn_activity_relpath(relpaths["report"])
    return {
        relpaths["report"].as_posix(): _artifact_signature(run_dir / relpaths["report"]),
        activity_relpath.as_posix(): _artifact_signature(run_dir / activity_relpath),
    }


def _scope_source_artifact_relpaths(run_dir: Path, stage: str) -> list[str]:
    paths = semantic_review_relpaths(stage)
    scope_path = run_dir / paths["scope"]
    if not scope_path.exists():
        return []
    try:
        scope = json.loads(scope_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_artifacts = scope.get("source_artifacts")
    source_artifacts = [item for item in raw_artifacts if isinstance(item, str) and item.strip()] if isinstance(raw_artifacts, list) else []
    run_root = run_dir.resolve()
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in source_artifacts:
        value = raw.strip().replace("\\", "/")
        if not value:
            continue
        candidates: list[Path]
        if any(char in value for char in "*?["):
            value_path = Path(value)
            if value_path.is_absolute() or ".." in value_path.parts:
                continue
            candidates = sorted(path for path in run_dir.glob(value) if path.is_file())
        else:
            value_path = Path(value)
            if value_path.is_absolute() or ".." in value_path.parts:
                continue
            candidates = [run_dir / value_path]
        for candidate in candidates:
            try:
                rel = candidate.resolve().relative_to(run_root).as_posix()
            except ValueError:
                continue
            if rel not in seen:
                seen.add(rel)
                normalized.append(rel)
    return normalized


def _source_artifact_fingerprint(run_dir: Path, stage: str) -> dict[str, str]:
    return {rel: _artifact_signature(run_dir / rel) for rel in _scope_source_artifact_relpaths(run_dir, stage)}


def _changed_artifacts(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(rel for rel in set(before) | set(after) if before.get(rel) != after.get(rel))


def _repair_progress_fingerprint(run_dir: Path, stage: str, round_number: int) -> dict[str, str]:
    fingerprint = _source_artifact_fingerprint(run_dir, stage)
    repair_paths = semantic_repair_relpaths(stage, round_number)
    activity_relpath = _semantic_turn_activity_relpath(repair_paths["report"])
    fingerprint[repair_paths["report"].as_posix()] = _artifact_signature(run_dir / repair_paths["report"])
    fingerprint[activity_relpath.as_posix()] = _artifact_signature(run_dir / activity_relpath)
    return fingerprint


async def _await_with_progress_watchdog(
    awaitable,
    *,
    run_dir: Path,
    stage: str,
    operation: str,
    timeout_seconds: float,
    fingerprint: Callable[[], dict[str, str]],
):
    task = asyncio.create_task(awaitable)
    last_fingerprint = fingerprint()
    last_progress_at = time.monotonic()
    append_state_snapshot(
        run_dir / "state.txt",
        {
            f"review.semantic.{stage}.watchdog.status": "monitoring",
            f"review.semantic.{stage}.watchdog.operation": operation,
            f"review.semantic.{stage}.watchdog.no_progress_timeout_seconds": f"{timeout_seconds:.0f}",
            f"review.semantic.{stage}.watchdog.started_at": now_iso(),
        },
    )
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=SEMANTIC_TURN_ARTIFACT_POLL_SECONDS)
            if task in done:
                result = await task
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        f"review.semantic.{stage}.watchdog.status": "completed",
                        f"review.semantic.{stage}.watchdog.operation": operation,
                        f"review.semantic.{stage}.watchdog.completed_at": now_iso(),
                    },
                )
                return result
            current_fingerprint = fingerprint()
            if current_fingerprint != last_fingerprint:
                last_fingerprint = current_fingerprint
                last_progress_at = time.monotonic()
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        f"review.semantic.{stage}.watchdog.status": "progress_observed",
                        f"review.semantic.{stage}.watchdog.operation": operation,
                        f"review.semantic.{stage}.watchdog.last_progress_at": now_iso(),
                        f"review.semantic.{stage}.watchdog.fingerprint": _json_hash(current_fingerprint),
                    },
                )
            if time.monotonic() - last_progress_at >= timeout_seconds:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        f"review.semantic.{stage}.watchdog.status": "no_progress_timeout",
                        f"review.semantic.{stage}.watchdog.operation": operation,
                        f"review.semantic.{stage}.watchdog.last_progress_at": now_iso(),
                        f"review.semantic.{stage}.watchdog.no_progress_timeout_seconds": f"{timeout_seconds:.0f}",
                    },
                )
                raise asyncio.TimeoutError
    except Exception:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        raise


async def _run_turn_until_semantic_artifact_completed(
    client,
    *,
    thread_id: str,
    text: str,
    cwd: Path,
    timeout_seconds: int,
    report_path: Path,
    is_completed,
) -> None:
    turn_task = asyncio.create_task(
        client.run_turn(
            thread_id=thread_id,
            text=text,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            reset_timeout_on_notification=True,
            progress_callback=lambda notification: _write_semantic_turn_activity_marker(report_path, notification),
        )
    )
    try:
        while True:
            done, _ = await asyncio.wait({turn_task}, timeout=SEMANTIC_TURN_ARTIFACT_POLL_SECONDS)
            if turn_task in done:
                await turn_task
                return
            if is_completed(report_path):
                try:
                    await asyncio.wait_for(turn_task, timeout=SEMANTIC_TURN_COMPLETION_GRACE_SECONDS)
                except asyncio.TimeoutError:
                    turn_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await turn_task
                except Exception as exc:
                    if not is_codex_transport_error(exc):
                        raise
                return
    except Exception:
        if not turn_task.done():
            turn_task.cancel()
            with suppress(asyncio.CancelledError):
                await turn_task
        raise


async def _run_review_once(run_dir: Path, stage: str, *, timeout_seconds: int, attempt: int, max_attempts: int, final_attempt: bool) -> SemanticReviewStatus | int:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build-semantic-review-pack.py"),
            "--run-dir",
            str(run_dir),
            "--stage",
            stage,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr or completed.stdout)
        return completed.returncode

    paths = semantic_review_relpaths(stage)
    prompt = (run_dir / paths["prompt"]).read_text(encoding="utf-8")
    report_path = run_dir / paths["report"]
    client = create_codex_app_server_client(cwd=REPO_ROOT)
    try:
        thread_id = await client.start_thread(cwd=REPO_ROOT, approval_policy="never")
        await _run_turn_until_semantic_artifact_completed(
            client,
            thread_id=thread_id,
            text=prompt,
            cwd=REPO_ROOT,
            timeout_seconds=timeout_seconds,
            report_path=report_path,
            is_completed=_semantic_review_report_completed,
        )
    except Exception as exc:
        if is_codex_transport_error(exc) and _semantic_review_report_completed(report_path):
            pass
        elif is_codex_transport_error(exc):
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    f"review.semantic.{stage}.transport.status": "failed",
                    f"review.semantic.{stage}.transport.error_kind": classify_codex_transport_error(str(exc)) or "unknown",
                    f"review.semantic.{stage}.transport.error": str(exc)[:2000],
                    f"review.semantic.{stage}.loop.status": "blocked_transport",
                },
            )
            raise
        else:
            raise
    finally:
        await client.stop()

    if stage == "image_prompt" and (run_dir / paths["report"]).exists():
        (run_dir / IMAGE_PROMPT_JUDGMENT_REPORT).write_text((run_dir / paths["report"]).read_text(encoding="utf-8"), encoding="utf-8")
    result = check_image_prompt_judgment(run_dir) if stage == "image_prompt" else check_semantic_review(run_dir, stage)
    updates = review_status_to_state(stage, result)
    slot = _slot_for_stage(stage)
    if slot:
        if result.passed:
            updates[f"slot.{slot}.status"] = "done"
            updates[f"slot.{slot}.note"] = f"contextless semantic {stage} review passed"
            updates[f"review.semantic.{stage}.transport.status"] = "passed"
            updates[f"review.semantic.{stage}.repair.active"] = "false"
        elif final_attempt:
            updates[f"slot.{slot}.status"] = "failed"
            updates[f"slot.{slot}.note"] = f"contextless semantic {stage} review failed after repair loop"
        else:
            updates[f"slot.{slot}.status"] = "in_progress"
            updates[f"slot.{slot}.note"] = f"contextless semantic {stage} review requested producer repair"
    if stage == "image_prompt":
        updates.update(
            {
                "review.image_prompt.judgment.status": result.status or "failed",
                "review.image_prompt.judgment.error_count": str(len(result.errors)),
            }
        )
    append_state_snapshot(run_dir / "state.txt", updates)
    return result


async def _run_producer_repair(
    run_dir: Path,
    stage: str,
    *,
    round_number: int,
    max_attempts: int,
    errors: tuple[str, ...],
    repair_timeout_seconds: int,
) -> None:
    paths = write_semantic_repair_prompt(run_dir, stage, round_number=round_number, max_attempts=max_attempts, errors=errors)
    updates = {}
    updates.update(semantic_loop_state_updates(stage, status="repairing", attempt=round_number, max_attempts=max_attempts, error_count=len(errors)))
    updates.update(semantic_repair_state_updates(stage, status="in_progress", round_number=round_number, max_attempts=max_attempts, error_count=len(errors)))
    slot = _slot_for_stage(stage)
    if slot:
        updates[f"slot.{slot}.status"] = "in_progress"
        updates[f"slot.{slot}.note"] = f"contextless semantic {stage} repair round {round_number} in progress"
    append_state_snapshot(run_dir / "state.txt", updates)

    client = create_codex_app_server_client(cwd=REPO_ROOT)
    try:
        thread_id = await client.start_thread(cwd=REPO_ROOT, approval_policy="never")
        await _run_turn_until_semantic_artifact_completed(
            client,
            thread_id=thread_id,
            text=paths["prompt"].read_text(encoding="utf-8"),
            cwd=REPO_ROOT,
            timeout_seconds=repair_timeout_seconds,
            report_path=paths["report"],
            is_completed=_semantic_repair_report_completed,
        )
    except Exception as exc:
        if is_codex_transport_error(exc):
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    f"review.semantic.{stage}.repair.transport.status": "failed",
                    f"review.semantic.{stage}.repair.transport.error_kind": classify_codex_transport_error(str(exc)) or "unknown",
                    f"review.semantic.{stage}.repair.transport.error": str(exc)[:2000],
                    f"review.semantic.{stage}.repair.status": "blocked_transport",
                },
            )
        raise
    finally:
        await client.stop()

    done_updates = semantic_repair_state_updates(stage, status="done", round_number=round_number, max_attempts=max_attempts, error_count=len(errors))
    if slot:
        done_updates[f"slot.{slot}.status"] = "in_progress"
        done_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} repair round {round_number} completed; rereview pending"
    append_state_snapshot(run_dir / "state.txt", done_updates)


async def run_review(
    run_dir: Path,
    stage: str,
    *,
    timeout_seconds: int,
    build_only: bool = False,
    max_attempts: int | None = None,
    repair_timeout_seconds: int | None = None,
    repair_loop: bool = True,
) -> int:
    if build_only:
        completed = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "build-semantic-review-pack.py"),
                "--run-dir",
                str(run_dir),
                "--stage",
                stage,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            sys.stderr.write(completed.stderr or completed.stdout)
        return completed.returncode

    attempts = max(1, max_attempts or semantic_review_max_attempts())
    if not repair_loop:
        attempts = 1
    repair_timeout = repair_timeout_seconds or semantic_repair_timeout_seconds()
    last_result: SemanticReviewStatus | None = None
    for attempt in range(1, attempts + 1):
        append_state_snapshot(run_dir / "state.txt", semantic_loop_state_updates(stage, status="reviewing", attempt=attempt, max_attempts=attempts))
        try:
            result_or_code = await _await_with_progress_watchdog(
                _run_review_once(
                    run_dir,
                    stage,
                    timeout_seconds=timeout_seconds,
                    attempt=attempt,
                    max_attempts=attempts,
                    final_attempt=attempt >= attempts,
                ),
                run_dir=run_dir,
                stage=stage,
                operation="review",
                timeout_seconds=timeout_seconds,
                fingerprint=lambda: _review_progress_fingerprint(run_dir, stage),
            )
        except asyncio.TimeoutError:
            slot = _slot_for_stage(stage)
            updates = semantic_loop_state_updates(stage, status="blocked_transport", attempt=attempt, max_attempts=attempts, error_count=1)
            updates.update(
                {
                    f"review.semantic.{stage}.transport.status": "failed",
                    f"review.semantic.{stage}.transport.error_kind": "timeout",
                    f"review.semantic.{stage}.transport.error": f"semantic review no-progress timeout after {timeout_seconds:.0f}s",
                }
            )
            if slot:
                updates[f"slot.{slot}.status"] = "failed"
                updates[f"slot.{slot}.note"] = f"contextless semantic {stage} review blocked by no-progress timeout"
            append_state_snapshot(run_dir / "state.txt", updates)
            sys.stderr.write(f"semantic review blocked by no-progress timeout for {stage}\n")
            return 2
        except Exception as exc:
            if is_codex_transport_error(exc):
                sys.stderr.write(f"semantic review blocked by Codex app-server transport failure for {stage}: {exc}\n")
                return 2
            raise
        if isinstance(result_or_code, int):
            return result_or_code
        result = result_or_code
        last_result = result
        if result.passed:
            append_state_snapshot(run_dir / "state.txt", semantic_loop_state_updates(stage, status="passed", attempt=attempt, max_attempts=attempts, error_count=0))
            return 0
        if attempt >= attempts:
            append_state_snapshot(run_dir / "state.txt", semantic_loop_state_updates(stage, status="failed", attempt=attempt, max_attempts=attempts, error_count=len(result.errors)))
            sys.stderr.write(f"semantic review failed for {stage} after {attempts} attempt(s): {'; '.join(result.errors)}\n")
            return 1
        repair_source_fingerprint_before = _source_artifact_fingerprint(run_dir, stage)
        try:
            await _await_with_progress_watchdog(
                _run_producer_repair(
                    run_dir,
                    stage,
                    round_number=attempt,
                    max_attempts=attempts,
                    errors=result.errors,
                    repair_timeout_seconds=repair_timeout,
                ),
                run_dir=run_dir,
                stage=stage,
                operation="producer_repair",
                timeout_seconds=repair_timeout,
                fingerprint=lambda: _repair_progress_fingerprint(run_dir, stage, attempt),
            )
        except asyncio.TimeoutError:
            repair_source_fingerprint_after = _source_artifact_fingerprint(run_dir, stage)
            changed_artifacts = _changed_artifacts(repair_source_fingerprint_before, repair_source_fingerprint_after)
            if changed_artifacts:
                repair_updates = semantic_repair_state_updates(
                    stage,
                    status="done",
                    round_number=attempt,
                    max_attempts=attempts,
                    error_count=len(result.errors),
                )
                repair_updates.update(
                    {
                        f"review.semantic.{stage}.repair.transport.status": "salvaged_after_source_artifact_change",
                        f"review.semantic.{stage}.repair.transport.error_kind": "timeout",
                        f"review.semantic.{stage}.repair.transport.error": f"semantic producer repair no-progress timeout after {repair_timeout:.0f}s",
                        f"review.semantic.{stage}.repair.changed_artifacts_detected": ", ".join(changed_artifacts)[:2000],
                    }
                )
                slot = _slot_for_stage(stage)
                if slot:
                    repair_updates[f"slot.{slot}.status"] = "in_progress"
                    repair_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} repair changed artifacts before timeout; rereview pending"
                append_state_snapshot(run_dir / "state.txt", repair_updates)
                continue
            slot = _slot_for_stage(stage)
            updates = semantic_loop_state_updates(stage, status="blocked_transport", attempt=attempt, max_attempts=attempts, error_count=len(result.errors))
            updates.update(semantic_repair_state_updates(stage, status="blocked_transport", round_number=attempt, max_attempts=attempts, error_count=len(result.errors)))
            updates.update(
                {
                    f"review.semantic.{stage}.transport.status": "failed",
                    f"review.semantic.{stage}.transport.error_kind": "timeout",
                    f"review.semantic.{stage}.transport.error": f"semantic producer repair no-progress timeout after {repair_timeout:.0f}s",
                    f"review.semantic.{stage}.repair.transport.status": "failed",
                    f"review.semantic.{stage}.repair.transport.error_kind": "timeout",
                }
            )
            if slot:
                updates[f"slot.{slot}.status"] = "failed"
                updates[f"slot.{slot}.note"] = f"contextless semantic {stage} producer repair blocked by no-progress timeout"
            append_state_snapshot(run_dir / "state.txt", updates)
            sys.stderr.write(f"semantic producer repair blocked by no-progress timeout for {stage}\n")
            return 2
        except Exception as exc:
            if is_codex_transport_error(exc):
                sys.stderr.write(f"semantic producer repair blocked by Codex app-server transport failure for {stage}: {exc}\n")
                return 2
            raise
    if last_result is not None and not last_result.passed:
        sys.stderr.write(f"semantic review failed for {stage}: {'; '.join(last_result.errors)}\n")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and run a contextless semantic review agent for one stage.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--stage", required=True, choices=sorted(SEMANTIC_REVIEW_STAGES))
    parser.add_argument("--timeout-seconds", type=int, default=semantic_review_timeout_seconds())
    parser.add_argument("--repair-timeout-seconds", type=int, default=semantic_repair_timeout_seconds())
    parser.add_argument("--max-attempts", type=int, default=semantic_review_max_attempts())
    parser.add_argument("--no-repair-loop", action="store_true", help="Run one semantic review pass and do not invoke the producer repair agent.")
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()
    return asyncio.run(
        run_review(
            Path(args.run_dir).resolve(),
            args.stage,
            timeout_seconds=args.timeout_seconds,
            build_only=args.build_only,
            max_attempts=args.max_attempts,
            repair_timeout_seconds=args.repair_timeout_seconds,
            repair_loop=not args.no_repair_loop,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
