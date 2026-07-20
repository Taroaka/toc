from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


IMAGE_PROMPT_JUDGMENT_COLLECTION = Path("logs/review/image_prompt.review_collection.md")
IMAGE_PROMPT_JUDGMENT_SCOPE = Path("logs/review/image_prompt.review_scope.json")
IMAGE_PROMPT_JUDGMENT_PROMPT = Path("logs/review/image_prompt.judgment_prompt.md")
IMAGE_PROMPT_JUDGMENT_REPORT = Path("logs/review/image_prompt.judgment.md")
PASSING_JUDGMENT_STATUSES = {"passed"}
SEMANTIC_REVIEW_STAGES = {
    "research",
    "story",
    "scene_set",
    "scene_detail",
    "cut_blueprint",
    "asset_plan",
    "image_prompt",
    "narration",
    "video_motion",
}
FOUNDATION_SEMANTIC_REVIEW_STAGES = {"research", "story"}
FOUNDATION_SEMANTIC_CRITERIA = {
    "research": (
        "baseline",
        "chronology",
        "principal_characters",
        "central_conflict_resolution",
        "downstream_handoff",
    ),
    "story": (
        "research_event_allocation",
        "chronology_causality",
        "character_continuity",
        "conflict_resolution",
        "historical_time_context",
        "scene_time_of_day_continuity",
        "duration_scene_readiness",
    ),
}


def semantic_review_relpaths(stage: str) -> dict[str, Path]:
    normalized = stage.strip()
    if normalized not in SEMANTIC_REVIEW_STAGES:
        raise ValueError(f"unknown semantic review stage: {stage}")
    base = Path("logs/review/semantic")
    return {
        "collection": base / f"{normalized}.collection.md",
        "scope": base / f"{normalized}.scope.json",
        "prompt": base / f"{normalized}.prompt.md",
        "report": base / f"{normalized}.report.md",
    }


def semantic_state_updates(
    stage: str,
    *,
    status: str,
    entry_count: int | None,
    error_count: int | None = None,
    generated_at: str | None = None,
) -> dict[str, str]:
    relpaths = semantic_review_relpaths(stage)
    updates = {
        f"review.semantic.{stage}.collection": relpaths["collection"].as_posix(),
        f"review.semantic.{stage}.scope": relpaths["scope"].as_posix(),
        f"review.semantic.{stage}.prompt": relpaths["prompt"].as_posix(),
        f"review.semantic.{stage}.report": relpaths["report"].as_posix(),
        f"review.semantic.{stage}.status": status,
    }
    if entry_count is not None:
        updates[f"review.semantic.{stage}.entry_count"] = str(entry_count)
    if error_count is not None:
        updates[f"review.semantic.{stage}.error_count"] = str(error_count)
    if generated_at:
        updates[f"review.semantic.{stage}.generated_at"] = generated_at
    return updates


@dataclass(frozen=True)
class SemanticReviewStatus:
    status: str
    entry_count: int | None
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors and self.status in PASSING_JUDGMENT_STATUSES


def parse_judgment_report_status(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        match = re.match(r"^-?\s*status\s*:\s*`?([A-Za-z_ -]+)`?\s*$", line)
        if match:
            return match.group(1).strip().lower().replace(" ", "_")
    return ""


def _scope_entry_count(scope_path: Path, *, rel_scope: Path | None = None) -> tuple[int | None, str | None]:
    if not scope_path.exists():
        rel = rel_scope or scope_path
        return None, f"missing semantic review scope: {rel.as_posix()}"
    try:
        data = json.loads(scope_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, f"invalid semantic review scope JSON: {exc}"
    raw = data.get("entry_count")
    if isinstance(raw, int):
        return raw, None
    return None, "semantic review scope is missing integer entry_count"


def _scope_entry_ids(scope_path: Path) -> tuple[list[str], str | None]:
    if not scope_path.exists():
        return [], f"missing semantic review scope: {scope_path.as_posix()}"
    try:
        data = json.loads(scope_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], f"invalid semantic review scope JSON: {exc}"
    raw = data.get("entry_ids")
    if not isinstance(raw, list):
        return [], "semantic review scope is missing entry_ids"
    entry_ids = [str(value).strip() for value in raw if str(value).strip()]
    if len(entry_ids) != len(raw):
        return entry_ids, "semantic review scope contains blank entry_ids"
    if len(set(entry_ids)) != len(entry_ids):
        return entry_ids, "semantic review scope contains duplicate entry_ids"
    return entry_ids, None


def _report_list_values(text: str, key: str) -> list[str]:
    values: list[str] = []
    collecting = False
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith(f"{key}:") or stripped.startswith(f"- {key}:"):
            inline = stripped.split(":", 1)[1].strip()
            if inline.startswith("[") and inline.endswith("]"):
                body = inline[1:-1].strip()
                return [
                    value.strip().strip("`\"'")
                    for value in body.split(",")
                    if value.strip().strip("`\"'")
                ]
            if inline:
                scalar = inline.strip("`\"'")
                return [] if scalar in {"[]", "..."} else [scalar]
            collecting = True
            continue
        if collecting:
            if not stripped:
                continue
            if not stripped.startswith("-"):
                break
            value = stripped[1:].strip().strip("`\"'")
            if value and value not in {"[]", "..."}:
                values.append(value)
    return values


def _report_json_value(text: str, key: str) -> tuple[Any | None, str | None]:
    match = re.search(rf"(?m)^-?\s*{re.escape(key)}\s*:\s*", text)
    if not match:
        return None, f"semantic review report is missing {key}"
    remainder = text[match.end() :].lstrip()
    try:
        value, _end = json.JSONDecoder().raw_decode(remainder)
    except json.JSONDecodeError as exc:
        return None, f"semantic review report has invalid {key} JSON: {exc}"
    return value, None


def _foundation_criteria_errors(report_text: str, stage: str, overall_status: str) -> list[str]:
    expected_ids = list(FOUNDATION_SEMANTIC_CRITERIA[stage])
    raw_results, parse_error = _report_json_value(report_text, "criteria_results_json")
    if parse_error:
        return [parse_error]
    if not isinstance(raw_results, list):
        return ["semantic review criteria_results_json must be a JSON array"]

    errors: list[str] = []
    result_ids: list[str] = []
    statuses: dict[str, str] = {}
    for index, raw_result in enumerate(raw_results, start=1):
        if not isinstance(raw_result, dict):
            errors.append(f"semantic review criterion result {index} must be an object")
            continue
        criterion_id = str(raw_result.get("criterion_id") or "").strip()
        result_ids.append(criterion_id)
        status = str(raw_result.get("status") or "").strip().lower()
        if status not in {"passed", "failed"}:
            errors.append(
                f"semantic review criterion {criterion_id or index} status must be passed or failed"
            )
        elif criterion_id:
            statuses[criterion_id] = status
        evidence = raw_result.get("evidence")
        if isinstance(evidence, list):
            evidence_values = [str(value).strip() for value in evidence if str(value).strip()]
        else:
            evidence_values = [str(evidence).strip()] if evidence is not None and str(evidence).strip() else []
        if not evidence_values or any(value in {"...", "pending"} for value in evidence_values):
            errors.append(
                f"semantic review criterion {criterion_id or index} requires non-empty evidence"
            )

    if result_ids != expected_ids:
        errors.append(
            "semantic review criterion_ids must exactly match the required ordered criteria "
            f"(expected={expected_ids}, got={result_ids})"
        )
    if overall_status in PASSING_JUDGMENT_STATUSES and any(
        statuses.get(criterion_id) != "passed" for criterion_id in expected_ids
    ):
        errors.append("passed foundation semantic review requires every criterion status to be passed")
    return errors


def _check_review_artifacts(
    run_dir: Path,
    *,
    artifacts: dict[str, Path],
    require_entries: bool,
    require_exact_entry_coverage: bool = False,
) -> SemanticReviewStatus:
    errors: list[str] = []
    for rel in artifacts.values():
        if not (run_dir / rel).exists():
            errors.append(f"missing semantic review artifact: {rel.as_posix()}")

    entry_count, scope_error = _scope_entry_count(run_dir / artifacts["scope"], rel_scope=artifacts["scope"])
    if scope_error:
        errors.append(scope_error)
    if require_entries and entry_count == 0:
        errors.append("semantic review scope has zero entries")

    report_path = run_dir / artifacts["report"]
    status = ""
    if report_path.exists():
        report_text = report_path.read_text(encoding="utf-8")
        status = parse_judgment_report_status(report_text)
        if "`...`" in report_text or "- `...`" in report_text:
            errors.append("semantic review report still contains template placeholder entries")
        if status not in PASSING_JUDGMENT_STATUSES:
            errors.append(f"semantic review status must be passed, got {status or '(missing)'}")
        if require_exact_entry_coverage:
            expected_entry_ids, entry_ids_error = _scope_entry_ids(run_dir / artifacts["scope"])
            if entry_ids_error:
                errors.append(entry_ids_error)
            reviewed_entries = _report_list_values(report_text, "reviewed_entries")
            if reviewed_entries != expected_entry_ids:
                errors.append(
                    "semantic review reviewed_entries coverage must exactly match scope entry_ids "
                    f"(expected={expected_entry_ids}, got={reviewed_entries})"
                )
            blocked_entries = _report_list_values(report_text, "blocked_entries")
            failed_selectors = _report_list_values(report_text, "failed_selectors")
            if status in PASSING_JUDGMENT_STATUSES and blocked_entries:
                errors.append("passed semantic review must have empty blocked_entries")
            if status in PASSING_JUDGMENT_STATUSES and failed_selectors:
                errors.append("passed semantic review must have empty failed_selectors")
            stage = artifacts["report"].name.split(".", 1)[0]
            if stage in FOUNDATION_SEMANTIC_REVIEW_STAGES:
                errors.extend(_foundation_criteria_errors(report_text, stage, status))

    return SemanticReviewStatus(status=status, entry_count=entry_count, errors=tuple(errors))


def check_semantic_review(run_dir: Path, stage: str, *, require_entries: bool = True) -> SemanticReviewStatus:
    return _check_review_artifacts(
        run_dir,
        artifacts=semantic_review_relpaths(stage),
        require_entries=require_entries,
        require_exact_entry_coverage=stage in FOUNDATION_SEMANTIC_REVIEW_STAGES,
    )


def check_image_prompt_judgment(run_dir: Path, *, require_entries: bool = True) -> SemanticReviewStatus:
    generic_paths = semantic_review_relpaths("image_prompt")
    legacy_status = _check_review_artifacts(
        run_dir,
        artifacts={
            "collection": IMAGE_PROMPT_JUDGMENT_COLLECTION,
            "scope": IMAGE_PROMPT_JUDGMENT_SCOPE,
            "prompt": IMAGE_PROMPT_JUDGMENT_PROMPT,
            "report": IMAGE_PROMPT_JUDGMENT_REPORT,
        },
        require_entries=require_entries,
    )
    if all((run_dir / rel).exists() for rel in generic_paths.values()):
        generic_status = check_semantic_review(run_dir, "image_prompt", require_entries=require_entries)
        if generic_status.passed or not legacy_status.passed:
            return generic_status
        return legacy_status
    return legacy_status


def review_status_to_state(stage: str, result: SemanticReviewStatus) -> dict[str, str]:
    return semantic_state_updates(
        stage,
        status=result.status or "failed",
        entry_count=result.entry_count,
        error_count=len(result.errors),
    )
