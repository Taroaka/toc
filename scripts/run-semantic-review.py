#!/usr/bin/env python3
"""Run contextless semantic review for one ToC stage."""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from contextlib import suppress
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.codex_app_server import create_codex_app_server_client, classify_codex_transport_error, is_codex_transport_error  # noqa: E402
from toc.harness import append_state_snapshot  # noqa: E402
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
            result_or_code = await _run_review_once(run_dir, stage, timeout_seconds=timeout_seconds, attempt=attempt, max_attempts=attempts, final_attempt=attempt >= attempts)
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
        await _run_producer_repair(
            run_dir,
            stage,
            round_number=attempt,
            max_attempts=attempts,
            errors=result.errors,
            repair_timeout_seconds=repair_timeout,
        )
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
