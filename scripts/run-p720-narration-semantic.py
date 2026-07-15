#!/usr/bin/env python3
"""Run and persist the five independent p720 full-run narration critics."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import sys
import uuid

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, load_structured_document, now_iso, parse_state_file
from toc.narration_arc import narration_text_set_hash
from toc.narration_semantic_review import (
    build_narration_semantic_review_pack,
    run_narration_semantic_critics,
    validate_narration_semantic_aggregate,
)
from toc.narration_review_gate import deterministic_narration_review_is_current
from toc.runtime_locks import sync_file_lock


def _replace_yaml_block(original: str, data: dict) -> str:
    dumped = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000)
    match = re.search(r"```yaml\s*\n(.*?)\n```", original, flags=re.DOTALL)
    if not match:
        return f"```yaml\n{dumped}```\n"
    start, end = match.span(1)
    return original[:start] + dumped.rstrip("\n") + original[end:]


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write(path: Path, content: str) -> None:
    _atomic_write_bytes(path, content.encode("utf-8"))


def _semantic_record(aggregate: dict, *, report_path: str, json_path: str) -> dict:
    return {
        "schema_version": str(aggregate.get("schema_version") or ""),
        "status": str(aggregate.get("status") or "changes_requested"),
        "narration_text_set_hash": str(aggregate.get("narration_text_set_hash") or ""),
        "semantic_review_input_hash": str(aggregate.get("semantic_review_input_hash") or ""),
        "reviewed_at": str(aggregate.get("reviewed_at") or now_iso()),
        "critics": aggregate.get("critics") if isinstance(aggregate.get("critics"), list) else [],
        "findings": aggregate.get("findings") if isinstance(aggregate.get("findings"), list) else [],
        "report": report_path,
        "json": json_path,
    }


async def run_semantic_review(
    *,
    run_dir: Path,
    manifest_path: Path,
    timeout_seconds: int,
    max_concurrency: int,
) -> str:
    lock_path = run_dir / ".locks" / "run_artifacts.lock"
    review_run_id = uuid.uuid4().hex
    with sync_file_lock(lock_path):
        _original, snapshot = load_structured_document(manifest_path)
        if not snapshot:
            raise ValueError(f"manifest has no structured YAML: {manifest_path}")
        expected_hash = narration_text_set_hash(snapshot)
        expected_input_hash = str(
            build_narration_semantic_review_pack(
                snapshot,
                text_set_hash=expected_hash,
            )["semantic_review_input_hash"]
        )
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "runtime.stage": "narration_semantic_critics_running",
                "runtime.narration.phase": "review",
                "slot.p720.status": "in_progress",
                "slot.p720.note": "five independent full-run semantic critics are reviewing one frozen text set",
                "review.narration.semantic_critics.status": "in_progress",
                "review.narration.semantic_critics.text_set_hash": expected_hash,
                "review.narration.semantic_critics.input_hash": expected_input_hash,
                "review.narration.semantic_critics.review_run_id": review_run_id,
                "gate.narration_review": "required",
            },
        )

    aggregate = await run_narration_semantic_critics(
        run_dir,
        snapshot,
        expected_narration_text_set_hash=expected_hash,
        expected_semantic_review_input_hash=expected_input_hash,
        timeout_seconds=timeout_seconds,
        max_concurrency=max_concurrency,
    )

    with sync_file_lock(lock_path):
        original, current = load_structured_document(manifest_path)
        active_review_run_id = str(
            parse_state_file(run_dir / "state.txt").get(
                "review.narration.semantic_critics.review_run_id"
            )
            or ""
        )
        if active_review_run_id != review_run_id:
            return "stale"
        current_hash = narration_text_set_hash(current)
        current_input_hash = str(
            build_narration_semantic_review_pack(
                current,
                text_set_hash=current_hash,
            )["semantic_review_input_hash"]
        )
        if current_hash != expected_hash or current_input_hash != expected_input_hash:
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    "runtime.stage": "narration_semantic_critics_stale",
                    "slot.p720.status": "in_progress",
                    "slot.p720.note": "narration or critic-visible context changed during semantic review; rerun p720",
                    "review.narration.semantic_critics.status": "stale",
                    "review.narration.semantic_critics.text_set_hash": expected_hash,
                    "review.narration.semantic_critics.input_hash": expected_input_hash,
                },
            )
            return "stale"
        if str(aggregate.get("narration_text_set_hash") or "") != current_hash:
            raise ValueError("semantic critic aggregate is not bound to the current narration text set")
        if str(aggregate.get("semantic_review_input_hash") or "") != current_input_hash:
            raise ValueError("semantic critic aggregate is not bound to the current semantic review input")
        validate_narration_semantic_aggregate(
            aggregate,
            expected_text_set_hash=current_hash,
            expected_semantic_review_input_hash=current_input_hash,
        )

        review_dir = run_dir / "logs" / "eval" / "narration" / "semantic_critics"
        stamp = now_iso().replace(":", "").replace("-", "").replace("+", "_") + f"_{uuid.uuid4().hex[:8]}"
        report = review_dir / f"{stamp}_review.md"
        json_report = review_dir / f"{stamp}_review.json"
        report_text = str(aggregate.get("report") or "").rstrip() + "\n"
        json_text = json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        artifact_writes = (
            (report, report_text),
            (json_report, json_text),
            (review_dir / "latest.md", report_text),
            (review_dir / "latest.json", json_text),
        )

        workflow = current.get("narration_workflow") if isinstance(current.get("narration_workflow"), dict) else {}
        workflow["schema_version"] = "narration_run_workflow_v1"
        workflow["semantic_critic_review"] = _semantic_record(
            aggregate,
            report_path=report.relative_to(run_dir).as_posix(),
            json_path=json_report.relative_to(run_dir).as_posix(),
        )
        current["narration_workflow"] = workflow
        semantic_passed = str(aggregate.get("status") or "") == "passed"
        overall_passed = semantic_passed and deterministic_narration_review_is_current(current)
        status = "passed" if overall_passed else "changes_requested"
        if not overall_passed:
            final_review = (
                workflow.get("final_audio_review")
                if isinstance(workflow.get("final_audio_review"), dict)
                else {}
            )
            final_review.update(
                {
                    "status": "stale" if final_review.get("status") == "approved" else "pending",
                    "approved_audio_set_hash": "",
                    "approved_timeline_hash": "",
                    "invalidated_at": now_iso(),
                    "invalidation_reason": "p720 semantic narration review requested changes",
                }
            )
            workflow["final_audio_review"] = final_review
            current["narration_workflow"] = workflow
        updates = {
            "runtime.stage": (
                "narration_text_semantic_review_passed"
                if overall_passed
                else "narration_text_semantic_review_changes_requested"
            ),
            "runtime.narration.phase": "review",
            "slot.p720.status": "done" if overall_passed else "blocked",
            "slot.p720.note": (
                "deterministic checks and five independent full-run semantic critics passed"
                if overall_passed
                else "p720 full-run narration review has unresolved findings"
            ),
            "review.narration.status": "approved" if overall_passed else "changes_requested",
            "review.narration.semantic_critics.status": str(aggregate.get("status") or "changes_requested"),
            "review.narration.semantic_critics.text_set_hash": current_hash,
            "review.narration.semantic_critics.input_hash": current_input_hash,
            "review.narration.semantic_critics.review_run_id": review_run_id,
            "artifact.narration_semantic_review": report.relative_to(run_dir).as_posix(),
            "artifact.narration_semantic_review_json": json_report.relative_to(run_dir).as_posix(),
            "gate.narration_review": "required",
        }
        if not overall_passed:
            updates.update(
                {
                    "slot.p730.status": "blocked",
                    "slot.p740.status": "blocked",
                    "slot.p750.status": "blocked",
                    "stage.narration.status": "in_progress",
                }
            )
        transaction_paths = [
            manifest_path,
            run_dir / "state.txt",
            run_dir / "run_status.json",
            run_dir / "p000_index.md",
            *(path for path, _content in artifact_writes),
        ]
        before_transaction = {
            path: path.read_bytes() if path.is_file() else None
            for path in transaction_paths
        }
        try:
            for path, content in artifact_writes:
                _atomic_write(path, content)
            _atomic_write(manifest_path, _replace_yaml_block(original, current))
            append_state_snapshot(run_dir / "state.txt", updates)
        except Exception:
            for path, previous_content in before_transaction.items():
                if previous_content is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_write_bytes(path, previous_content)
            raise
        return status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--max-concurrency", type=int, default=3)
    parser.add_argument("--fail-on-findings", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = Path(args.run_dir).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve() if args.manifest else run_dir / "video_manifest.md"
    if not manifest_path.is_file():
        raise SystemExit(f"Manifest not found: {manifest_path}")
    try:
        status = asyncio.run(
            run_semantic_review(
                run_dir=run_dir,
                manifest_path=manifest_path,
                timeout_seconds=args.timeout_seconds,
                max_concurrency=args.max_concurrency,
            )
        )
    except Exception as exc:
        raise SystemExit(str(exc)) from exc
    print(f"p720 narration semantic review: {status}")
    if args.fail_on_findings and status != "passed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
