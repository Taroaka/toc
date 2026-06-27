from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from toc.harness import append_state_snapshot


def scene_design_log_relpath(filename: str) -> str:
    return f"logs/scene_design/{filename}"


SCENE_GENERATION_PROMPTS_FILENAME = "scene_generation_prompts.json"


def write_scene_design_json(run_dir: Path, filename: str, payload: dict[str, Any]) -> None:
    log_dir = run_dir / "logs" / "scene_design"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_scene_design_json(run_dir: Path, filename: str) -> dict[str, Any]:
    path = run_dir / scene_design_log_relpath(filename)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def profile_failure_summary(profile: dict[str, Any]) -> dict[str, Any]:
    scene_titles = profile.get("scene_titles")
    return {
        "slug": profile.get("slug"),
        "topic_label": profile.get("topic_label"),
        "protagonist_name": profile.get("protagonist_name"),
        "artifact_name": profile.get("artifact_name"),
        "scene_title_count": len(scene_titles) if isinstance(scene_titles, list) else None,
    }


def write_cut_design_context(
    run_dir: Path,
    *,
    now: str,
    topic: str,
    phase: str,
    profile: dict[str, Any] | None = None,
    scene_context: dict[str, Any] | None = None,
    cut_context: dict[str, Any] | None = None,
    partial_counts: dict[str, Any] | None = None,
    flow: str | None = None,
    status: str | None = None,
    reason: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": "cut_design_generation_context_v1",
        "updated_at": now,
        "topic": topic,
        "phase": phase,
        "profile_summary": profile_failure_summary(profile or {}),
        "scene_context": scene_context or {},
        "cut_context": cut_context or {},
        "partial_counts": partial_counts or {},
    }
    if flow:
        payload["flow"] = flow
    if status:
        payload["status"] = status
    if reason:
        payload["reason"] = reason
    write_scene_design_json(run_dir, "latest_generation_context.json", payload)


def write_cut_design_failure_log(
    run_dir: Path,
    *,
    now: str,
    topic: str,
    phase: str,
    profile: dict[str, Any] | None,
    exc: BaseException,
) -> None:
    latest_context = read_scene_design_json(run_dir, "latest_generation_context.json")
    scene_event_input = read_scene_design_json(run_dir, "scene_event_input.json")
    scene_event_output = read_scene_design_json(run_dir, "scene_event_output.json")
    scene_generation_prompts = read_scene_design_json(run_dir, SCENE_GENERATION_PROMPTS_FILENAME)
    payload = {
        "schema_version": "cut_design_failure_v1",
        "created_at": now,
        "topic": topic,
        "phase": phase,
        "profile_summary": profile_failure_summary(profile or {}),
        "latest_generation_context": latest_context,
        "partial_artifacts": {
            "scene_event_input": {
                "path": scene_design_log_relpath("scene_event_input.json"),
                "scene_count": scene_event_input.get("scene_count"),
            },
            "scene_event_output": {
                "path": scene_design_log_relpath("scene_event_output.json"),
                "scene_count": scene_event_output.get("scene_count"),
            },
            "scene_generation_prompts": {
                "path": scene_design_log_relpath(SCENE_GENERATION_PROMPTS_FILENAME),
                "scene_count": scene_generation_prompts.get("scene_count"),
            },
        },
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exception(type(exc), exc, exc.__traceback__),
        },
    }
    write_scene_design_json(run_dir, "cut_contract_failure.json", payload)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "runtime.stage": "cut_design_failed",
            "runtime.cut_design.status": "failed",
            "runtime.cut_design.phase": phase,
            "runtime.cut_design.error_type": type(exc).__name__,
            "runtime.cut_design.error": str(exc)[:2000],
            "runtime.cut_design.latest_context": scene_design_log_relpath("latest_generation_context.json"),
            "runtime.cut_design.failure_log": scene_design_log_relpath("cut_contract_failure.json"),
            "slot.p420.status": "failed",
            "slot.p420.note": "cut design failed before frontend handoff",
            "eval.cut_blueprint.status": "changes_requested",
        },
    )


def write_scene_design_placeholder(run_dir: Path, *, topic: str, flow: str, now: str, reason: str) -> None:
    base_payload = {
        "schema_version": "scene_event_log_v1",
        "flow": flow,
        "status": "not_generated",
        "reason": reason,
        "topic": topic,
        "scene_count": 0,
        "scenes": [],
    }
    for filename in ("scene_event_input.json", "scene_event_output.json"):
        write_scene_design_json(run_dir, filename, base_payload)
    write_scene_design_json(
        run_dir,
        SCENE_GENERATION_PROMPTS_FILENAME,
        {
            "schema_version": "scene_generation_prompt_log_v1",
            "flow": flow,
            "status": "not_generated",
            "reason": reason,
            "topic": topic,
            "scene_count": 0,
            "scenes": [],
        },
    )
    write_cut_design_context(
        run_dir,
        now=now,
        topic=topic,
        phase="cut_design_not_started",
        profile={},
        partial_counts={"scene_event_inputs": 0, "scene_event_outputs": 0, "selectors": 0},
        flow=flow,
        status="not_generated",
        reason=reason,
    )
