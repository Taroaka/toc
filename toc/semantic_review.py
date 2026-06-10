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
    "scene_set",
    "scene_detail",
    "cut_blueprint",
    "asset_plan",
    "image_prompt",
    "narration",
    "video_motion",
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


def _check_review_artifacts(
    run_dir: Path,
    *,
    artifacts: dict[str, Path],
    require_entries: bool,
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

    return SemanticReviewStatus(status=status, entry_count=entry_count, errors=tuple(errors))


def check_semantic_review(run_dir: Path, stage: str, *, require_entries: bool = True) -> SemanticReviewStatus:
    return _check_review_artifacts(
        run_dir,
        artifacts=semantic_review_relpaths(stage),
        require_entries=require_entries,
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
