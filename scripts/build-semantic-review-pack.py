#!/usr/bin/env python3
"""Build a deterministic prompt pack for contextless semantic review."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, now_iso  # noqa: E402
from toc.review_projection import (  # noqa: E402
    REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD,
    review_source_fingerprint,
)
from toc.semantic_pack import collect_entries, load_manifest  # noqa: E402
from toc.semantic_review import (  # noqa: E402
    FOUNDATION_SEMANTIC_CRITERIA,
    IMAGE_PROMPT_JUDGMENT_COLLECTION,
    IMAGE_PROMPT_JUDGMENT_PROMPT,
    IMAGE_PROMPT_JUDGMENT_REPORT,
    IMAGE_PROMPT_JUDGMENT_SCOPE,
    SEMANTIC_REVIEW_INPUT_SCHEMA,
    SEMANTIC_REVIEW_STAGES,
    safe_semantic_write_text,
    semantic_review_file_sha256,
    semantic_review_input_digest,
    semantic_review_relpaths,
    semantic_review_scope_binding_sha256,
    semantic_state_updates,
)


STAGE_LABELS = {
    "research": "research story foundation",
    "story": "story skeleton and scene allocation",
    "scene_set": "scene set design",
    "scene_detail": "scene detail design",
    "cut_blueprint": "cut blueprint design",
    "asset_plan": "asset planning",
    "image_prompt": "scene image prompt",
    "narration": "narration text and audio handoff",
    "video_motion": "video motion prompt",
}


def write_text(run_dir: Path, path: Path, text: str) -> Path:
    return safe_semantic_write_text(run_dir, path, text)


def _json_block(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def render_collection(stage: str, entries: list[dict[str, object]]) -> str:
    lines = [
        f"# Semantic Review Collection: {stage}",
        "",
        f"対象工程: `{STAGE_LABELS.get(stage, stage)}`",
        "",
        f"件数: `{len(entries)}`",
        "",
    ]
    for index, entry in enumerate(entries, start=1):
        entry_id = str(entry.get("id") or entry.get("selector") or f"entry_{index:03d}")
        lines.extend(
            [
                f"## {entry_id}",
                "",
                "```json",
                _json_block(entry),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def render_scope_json(
    *,
    stage: str,
    run_dir: Path,
    entries: list[dict[str, object]],
    collection_path: Path,
    scope_path: Path,
    prompt_path: Path,
    report_path: Path,
    shard_plan: dict[str, object] | None = None,
) -> str:
    diagnostics = entry_diagnostics(entries)
    entry_ids = [str(entry.get("id") or entry.get("selector") or "") for entry in entries]
    source_artifacts = _source_artifacts(run_dir, stage)
    source_artifact_digests = _source_artifact_digest_records(
        run_dir,
        source_artifacts,
        stage=stage,
    )
    collection_sha256 = semantic_review_file_sha256(collection_path)
    prompt_sha256 = semantic_review_file_sha256(prompt_path)
    request_revision = _semantic_review_request_revision(
        run_dir,
        stage,
        source_artifacts,
    )
    payload = {
        "stage": stage,
        "run_dir": str(run_dir.resolve()),
        "entry_count": len(entries),
        "entry_ids": entry_ids,
        "review_scope": "all_entries",
        "diagnostics": diagnostics,
        "source_artifacts": source_artifacts,
        "semantic_review_input_schema": SEMANTIC_REVIEW_INPUT_SCHEMA,
        "source_artifact_digests": source_artifact_digests,
        "collection_sha256": collection_sha256,
        "prompt_sha256": prompt_sha256,
        "artifacts": {
            "collection": str(collection_path.relative_to(run_dir)),
            "scope": str(scope_path.relative_to(run_dir)),
            "prompt": str(prompt_path.relative_to(run_dir)),
            "report": str(report_path.relative_to(run_dir)),
        },
        "generated_at": now_iso(),
    }
    if request_revision:
        payload["request_revision"] = request_revision
    if shard_plan:
        payload.update(
            {
                "review_scope": shard_plan.get("review_scope", payload["review_scope"]),
                "shards": shard_plan.get("shards", []),
                "coverage": shard_plan.get("coverage", {}),
            }
        )
    scope_binding_sha256 = semantic_review_scope_binding_sha256(payload)
    input_digest = semantic_review_input_digest(
        stage=stage,
        entry_ids=entry_ids,
        collection_sha256=collection_sha256,
        prompt_sha256=prompt_sha256,
        source_artifact_digests=source_artifact_digests,
        request_revision=request_revision,
        scope_binding_sha256=scope_binding_sha256,
    )
    payload["scope_binding_sha256"] = scope_binding_sha256
    payload["semantic_review_input_digest"] = input_digest
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _entry_id(entry: dict[str, object], index: int) -> str:
    return str(entry.get("id") or entry.get("selector") or f"entry_{index:03d}").strip()


def _image_prompt_scene_token(entry: dict[str, object], entry_id: str) -> str:
    raw_scene_id = str(entry.get("scene_id") or "").strip()
    if raw_scene_id:
        match = re.search(r"scene[_:\s-]*(\d+)", raw_scene_id, re.I)
        if match:
            return str(int(match.group(1)))
        label = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_scene_id).strip("._-").lower()
        if label:
            return label
    match = re.search(r"scene[_:\s-]*(\d+)", entry_id, re.I)
    if match:
        return str(int(match.group(1)))
    return ""


def _scene_token_sort_key(token: str) -> tuple[int, object, str]:
    if token.isdigit():
        return (0, int(token), token)
    return (1, token, token)


def image_prompt_scene_shard_plan(entries: list[dict[str, object]]) -> dict[str, object]:
    """Return a deterministic per-scene plan with exact selector coverage.

    Every image-prompt entry, including the scene-composite gate, must belong to
    exactly one scene shard. Invalid plans raise instead of silently producing a
    partial semantic review.
    """

    if not entries:
        raise ValueError("image_prompt semantic review has zero entries")
    entry_ids = [_entry_id(entry, index) for index, entry in enumerate(entries, start=1)]
    duplicates = sorted(entry_id for entry_id, count in Counter(entry_ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"image_prompt semantic review has duplicate entry ids: {', '.join(duplicates)}")

    grouped: dict[str, list[str]] = {}
    for entry, entry_id in zip(entries, entry_ids):
        scene_token = _image_prompt_scene_token(entry, entry_id)
        if not scene_token:
            raise ValueError(f"cannot assign entry to image_prompt scene shard: {entry_id}")
        grouped.setdefault(scene_token, []).append(entry_id)

    shards = [
        {
            "shard_id": f"scene_{scene_token}",
            "scene_id": scene_token,
            "entry_count": len(grouped[scene_token]),
            "entry_ids": list(grouped[scene_token]),
        }
        for scene_token in sorted(grouped, key=_scene_token_sort_key)
    ]
    assigned_entry_ids = [entry_id for shard in shards for entry_id in shard["entry_ids"]]
    return {
        "review_scope": "per_scene_shards",
        "shards": shards,
        "coverage": {
            "status": "valid",
            "expected_entry_count": len(entry_ids),
            "assigned_entry_count": len(assigned_entry_ids),
            "expected_entry_ids": entry_ids,
            "assigned_entry_ids": assigned_entry_ids,
            "missing_entry_ids": [],
            "duplicate_entry_ids": [],
        },
    }


def _invalid_image_prompt_scene_shard_plan(entries: list[dict[str, object]], error: ValueError) -> dict[str, object]:
    entry_ids = [_entry_id(entry, index) for index, entry in enumerate(entries, start=1)]
    duplicates = sorted(entry_id for entry_id, count in Counter(entry_ids).items() if count > 1)
    return {
        "review_scope": "per_scene_shards",
        "shards": [],
        "coverage": {
            "status": "invalid",
            "expected_entry_count": len(entry_ids),
            "assigned_entry_count": 0,
            "expected_entry_ids": entry_ids,
            "assigned_entry_ids": [],
            "missing_entry_ids": entry_ids,
            "duplicate_entry_ids": duplicates,
            "errors": [str(error)],
        },
    }


def materialize_image_prompt_scene_shards(
    *,
    run_dir: Path,
    entries: list[dict[str, object]],
    canonical_scope_path: Path,
    canonical_report_path: Path,
) -> dict[str, object]:
    """Write stable scene-local review packs and return their scope manifest."""

    plan = image_prompt_scene_shard_plan(entries)
    entries_by_id = {
        _entry_id(entry, index): entry
        for index, entry in enumerate(entries, start=1)
    }
    shard_root = run_dir / "logs" / "review" / "semantic" / "image_prompt_shards" / "pack"
    for index, shard in enumerate(plan["shards"], start=1):
        shard_id = str(shard["shard_id"])
        entry_ids = [str(item) for item in shard["entry_ids"]]
        shard_entries = [entries_by_id[entry_id] for entry_id in entry_ids]
        safe_shard_id = re.sub(r"[^A-Za-z0-9_-]+", "_", shard_id).strip("_")[:48] or "shard"
        shard_hash = hashlib.sha256(shard_id.encode("utf-8")).hexdigest()[:12]
        base = shard_root / f"{index:03d}_{safe_shard_id}_{shard_hash}"
        collection_path = Path(f"{base}.collection.md")
        scope_path = Path(f"{base}.scope.json")
        prompt_path = Path(f"{base}.prompt.md")
        report_path = Path(f"{base}.report.md")
        write_text(run_dir, collection_path, render_collection("image_prompt", shard_entries))
        shard_prompt = render_prompt(
            stage="image_prompt",
            run_dir=run_dir,
            collection_path=collection_path,
            scope_path=scope_path,
            report_path=report_path,
        )
        write_text(
            run_dir,
            prompt_path,
            shard_prompt.rstrip()
            + "\n\n"
            + f"Review only image_prompt scene shard `{shard_id}`.\n"
            + "Expected reviewed_entries exactly once: "
            + json.dumps(entry_ids, ensure_ascii=False)
            + "\n",
        )
        source_artifacts = _source_artifacts(run_dir, "image_prompt")
        source_artifact_digests = _source_artifact_digest_records(
            run_dir,
            source_artifacts,
            stage="image_prompt",
        )
        collection_sha256 = semantic_review_file_sha256(collection_path)
        prompt_sha256 = semantic_review_file_sha256(prompt_path)
        request_revision = _semantic_review_request_revision(
            run_dir,
            "image_prompt",
            source_artifacts,
        )
        shard_scope = {
            "stage": "image_prompt",
            "run_dir": str(run_dir.resolve()),
            "entry_count": len(entry_ids),
            "entry_ids": entry_ids,
            "review_scope": "single_scene_image_prompt_shard",
            "shard_id": shard_id,
            "scene_id": str(shard["scene_id"]),
            "canonical_scope": str(canonical_scope_path.relative_to(run_dir)),
            "canonical_report": str(canonical_report_path.relative_to(run_dir)),
            "source_artifacts": source_artifacts,
            "semantic_review_input_schema": SEMANTIC_REVIEW_INPUT_SCHEMA,
            "source_artifact_digests": source_artifact_digests,
            "collection_sha256": collection_sha256,
            "prompt_sha256": prompt_sha256,
            "artifacts": {
                "collection": str(collection_path.relative_to(run_dir)),
                "scope": str(scope_path.relative_to(run_dir)),
                "prompt": str(prompt_path.relative_to(run_dir)),
                "report": str(report_path.relative_to(run_dir)),
            },
            "generated_at": now_iso(),
        }
        if request_revision:
            shard_scope["request_revision"] = request_revision
        scope_binding_sha256 = semantic_review_scope_binding_sha256(shard_scope)
        input_digest = semantic_review_input_digest(
            stage="image_prompt",
            entry_ids=entry_ids,
            collection_sha256=collection_sha256,
            prompt_sha256=prompt_sha256,
            source_artifact_digests=source_artifact_digests,
            request_revision=request_revision,
            scope_binding_sha256=scope_binding_sha256,
        )
        shard_scope["scope_binding_sha256"] = scope_binding_sha256
        shard_scope["semantic_review_input_digest"] = input_digest
        write_text(run_dir, scope_path, json.dumps(shard_scope, ensure_ascii=False, indent=2) + "\n")
        write_text(
            run_dir,
            report_path,
            render_report_template(
                stage="image_prompt",
                run_dir=run_dir,
                scope_path=scope_path,
                collection_path=collection_path,
                semantic_review_input_digest_value=input_digest,
            )
            + "\n",
        )
        shard["artifacts"] = shard_scope["artifacts"]
    return plan


def entry_diagnostics(entries: list[dict[str, object]]) -> dict[str, object]:
    missing_contract_entries: list[str] = []
    missing_contact_sheet_entries: list[str] = []
    missing_sampled_frame_entries: list[str] = []
    failed_selectors: list[str] = []
    blocking_quality_issue_entries: list[str] = []
    blocking_quality_issue_codes: list[str] = []
    blocking_quality_issue_count = 0
    for index, entry in enumerate(entries, start=1):
        entry_id = str(entry.get("id") or entry.get("selector") or f"entry_{index:03d}")
        if _truthy(entry.get("semantic_contract_missing")) or _truthy(entry.get("motion_contract_missing")):
            missing_contract_entries.append(entry_id)
            failed_selectors.append(entry_id)
        if _truthy(entry.get("contact_sheet_missing")):
            missing_contact_sheet_entries.append(entry_id)
        if _truthy(entry.get("sampled_frames_missing")):
            missing_sampled_frame_entries.append(entry_id)
        blocking_issues = _blocking_quality_issues(entry)
        if blocking_issues:
            blocking_quality_issue_entries.append(entry_id)
            failed_selectors.append(entry_id)
            blocking_quality_issue_count += len(blocking_issues)
            blocking_quality_issue_codes.extend(
                (
                    str(issue.get("code") or "").strip()
                    or "video_motion_blocking_quality_issue"
                )
                for issue in blocking_issues
            )
    return {
        "missing_semantic_contract_count": len(missing_contract_entries),
        "missing_semantic_contract_entries": missing_contract_entries,
        "missing_contact_sheet_count": len(missing_contact_sheet_entries),
        "missing_contact_sheet_entries": missing_contact_sheet_entries,
        "missing_sampled_frame_count": len(missing_sampled_frame_entries),
        "missing_sampled_frame_entries": missing_sampled_frame_entries,
        "blocking_quality_issue_count": blocking_quality_issue_count,
        "blocking_quality_issue_entries": blocking_quality_issue_entries,
        "blocking_quality_issue_codes": sorted(
            set(blocking_quality_issue_codes)
        ),
        "failed_selectors": sorted(set(failed_selectors)),
    }


def _blocking_quality_issues(entry: dict[str, object]) -> list[dict[str, object]]:
    provider_payload = entry.get("provider_prompt_payload")
    video_prompt_ir = (
        provider_payload.get("video_prompt_ir")
        if isinstance(provider_payload, dict)
        else None
    )
    sources = [
        entry.get("quality_issues"),
        (
            provider_payload.get("quality_issues")
            if isinstance(provider_payload, dict)
            else None
        ),
        (
            video_prompt_ir.get("quality_issues")
            if isinstance(video_prompt_ir, dict)
            else None
        ),
    ]
    issues: list[dict[str, object]] = []
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, list):
            continue
        for raw_issue in source:
            if not isinstance(raw_issue, dict) or raw_issue.get("blocking") is not True:
                continue
            issue = {str(key): value for key, value in raw_issue.items()}
            fingerprint = json.dumps(
                issue,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            issues.append(issue)
    return issues


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def _source_artifacts(run_dir: Path, stage: str) -> list[str]:
    foundation_sources = {
        "research": ["research.md"],
        "story": ["research.md", "story.md"],
    }
    if stage in foundation_sources:
        return [rel for rel in foundation_sources[stage] if (run_dir / rel).exists()]
    common = ["story.md", "script.md", "video_manifest.md"]
    by_stage = {
        "asset_plan": [
            "asset_inventory.md",
            "asset_plan.md",
            "asset_generation_requests.md",
            "asset_generation_request_snapshot.json",
        ],
        "image_prompt": [
            "asset_inventory.md",
            "asset_plan.md",
            "image_generation_requests.md",
            "image_generation_request_snapshot.json",
            "image_prompt_story_review.md",
        ],
        "narration": ["narration_text_review.md", "logs/review/narration_text_quality.md"],
        "video_motion": ["video_generation_requests.md"],
    }
    candidates = common + by_stage.get(stage, [])
    seen: set[str] = set()
    artifacts: list[str] = []
    for rel in candidates:
        if rel in seen:
            continue
        seen.add(rel)
        if (run_dir / rel).exists():
            artifacts.append(rel)
    return artifacts


def _source_artifact_digest_records(
    run_dir: Path,
    source_artifacts: list[str],
    *,
    stage: str,
) -> list[dict[str, str]]:
    run_root = run_dir.resolve(strict=True)
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for rel in source_artifacts:
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts or rel_path.as_posix() != rel:
            raise ValueError(f"semantic review source artifact is not a safe run-relative path: {rel}")
        try:
            source_path = (run_root / rel_path).resolve(strict=True)
            source_path.relative_to(run_root)
        except (OSError, ValueError) as exc:
            raise ValueError(f"semantic review source artifact escapes or is missing: {rel}") from exc
        if not source_path.is_file():
            raise ValueError(f"semantic review source artifact is not a file: {rel}")
        if rel in seen:
            raise ValueError(f"semantic review source artifact is duplicated: {rel}")
        seen.add(rel)
        fingerprint = review_source_fingerprint(
            source_path,
            artifact_relpath=rel,
            review_kind="semantic",
            stage=stage,
        )
        records.append(
            {
                "path": rel,
                "sha256": fingerprint.sha256,
                REVIEW_SOURCE_FINGERPRINT_POLICY_FIELD: (
                    fingerprint.policy
                ),
            }
        )
    return records


def _semantic_review_request_revision(
    run_dir: Path,
    stage: str,
    source_artifacts: list[str],
) -> str | None:
    if stage != "image_prompt":
        return None
    snapshot_rel = "image_generation_request_snapshot.json"
    if snapshot_rel not in source_artifacts:
        return None
    try:
        snapshot = json.loads((run_dir / snapshot_rel).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(snapshot, dict):
        return None
    request_revision = snapshot.get("request_revision")
    if isinstance(request_revision, str) and request_revision.strip():
        return request_revision.strip()
    return None


def render_report_template(
    *,
    stage: str,
    run_dir: Path,
    scope_path: Path,
    collection_path: Path,
    semantic_review_input_digest_value: str | None = None,
) -> str:
    lines = [
        f"# Semantic Review Report: {stage}",
        "",
        f"- run_dir: `{run_dir.resolve()}`",
        f"- stage: `{stage}`",
        f"- scope: `{scope_path}`",
        f"- collection: `{collection_path}`",
        "- status: `pending`",
        *(
            [f"- semantic_review_input_digest: `{semantic_review_input_digest_value}`"]
            if semantic_review_input_digest_value
            else []
        ),
        "",
        "## Reviewed Entries",
        "",
        "- `...`",
        "",
        "## Blocked Entries",
        "",
        "- `...`",
    ]
    if stage in FOUNDATION_SEMANTIC_CRITERIA:
        lines.extend(["", "## Criterion Results", "", "criteria_results_json: []"])
    lines.extend(
        [
            "",
            "## Findings",
            "",
            "- `...`",
            "",
            "## Reason Keys",
            "",
            "- `...`",
            "",
            "## Notes",
            "",
            "- `...`",
        ]
    )
    return "\n".join(lines)


def _stage_specific_review_instructions(stage: str) -> list[str]:
    scene_time_of_day_instructions = [
        "Treat each scene-level `time_of_day` as an open string daypart (for example 朝, 昼, 夕方, 夜, 夜明け前, or 真夜中), separate from the story's historical `story_metadata.time` / `script_metadata.time` / `video_metadata.time`.",
        "Use `time_of_day_contract_declared` and `time_of_day_status` from each review entry. The required contract is declared only by metadata marker `scene_time_of_day_contract: required_v1`; a scene key by itself does not declare it. Fail missing or blank values only when declared; do not fail an undeclared legacy omission solely for lacking this newer key. Always fail `invalid_type` because the authored value must be a string.",
        "When valid, fail if the daypart contradicts causal scene order, changes between projections without an authored transition, or cannot support concrete sky brightness, natural/artificial light, shadow, and color-temperature choices.",
        "Use reason keys such as scene_time_of_day_missing, scene_time_of_day_invalid_type, scene_time_of_day_continuity_mismatch, or scene_time_of_day_not_visualizable.",
    ]
    if stage == "research":
        return [
            "Treat `research.md` as the run-local provisional baseline; judge whether it is internally sufficient for story authoring.",
            "Review canonical_story_dump, chronological_events, characters/motivations/relationships, conflicts/selection cues, and handoff_to_story together.",
            "Fail when the baseline is too thin to recover a beginning, pressure, causal turns, and resolution; events contradict their declared order; principal characters have no usable role or motivation; or conflicts cannot guide a coherent story choice.",
            "Do not browse or validate external URLs, editions, translations, rights, or factual fidelity. External source authenticity is outside this gate.",
            "Use reason keys such as research_baseline_too_thin, research_timeline_incoherent, research_character_model_incomplete, or research_conflict_unresolved_for_story.",
        ]
    if stage == "story":
        return [
            "Treat approved `research.md` as immutable upstream baseline and review the complete story-to-scene allocation before any cut is authored.",
            "Treat scene `time_of_day` as an open string daypart, separate from historical `story_metadata.time`. The required contract is declared only by `story_metadata.scene_time_of_day_contract: required_v1`. Read the aggregate story entry's `time_of_day_contract_declared` and each `scene_time_of_day_statuses[].status`; do not look for a top-level per-scene `time_of_day_status` in this entry.",
            "When the contract is declared, fail a scene_time_of_day_statuses item whose status is missing, blank, or invalid_type. Do not fail an undeclared legacy story solely for this newer key.",
            "When valid, require causal daypart progression and a visualizable basis for sky brightness, natural/artificial light, shadow, and color temperature without changing historical clothing, architecture, materials, or technology.",
            "Review every `scene_location_route_statuses[]` item. `undeclared` is legacy/no-route evidence, but an authored `location.mode: sequence` must be `valid`: its ordered `location.sequence[]` must be covered exactly once and in the same order by `location.segments[]`, and every segment must contain drawable responsibility, primary subject, visible action, evidence/roles, motion brief, and motion end state.",
            "Fail an `invalid` route instead of inferring a missing transition from scene-wide prose. A semantic story review must not pass when the later cut compiler would have to invent which action occurs at which location.",
            "Check timeline, characters and motivations, conflict escalation/resolution, important-event coverage, distinct scene responsibility, internal research_refs, historical time context, and duration-aware scene allocation.",
            "For `historical_time_context`, require `story_metadata.time` to be a string. Existing classics, folklore, legends, and adaptations must use a concrete `〇〇時代` value supported by the run-local research/story context; user-created original stories may use an empty string.",
            "Fail if story order contradicts research, character state changes without cause, a current-contract scene lacks a valid time_of_day or its daypart progression contradicts the events, a declared multi-location route is incomplete or unordered, every scene repeats the same conflict or turn, important events are unassigned, internal refs do not resolve, a non-original story lacks its historical time, or scenes are too generic/duplicative to split into cuts.",
            "Do not impose a fixed scene count. Judge semantic coverage against target_duration_seconds and the story's own meaningful scene responsibilities.",
            "Do not browse or validate external URLs, editions, translations, rights, or factual fidelity. External source authenticity is outside this gate.",
            "Use reason keys such as story_baseline_mismatch, story_timeline_mismatch, story_character_continuity_mismatch, story_conflict_progression_weak, story_historical_time_missing, scene_time_of_day_missing, scene_time_of_day_invalid_type, scene_time_of_day_continuity_mismatch, scene_location_route_incomplete, scene_location_route_order_mismatch, scene_location_segment_not_drawable, story_event_unassigned, story_scene_allocation_generic, story_scene_duplicate_responsibility, or internal_reference_unresolved.",
        ]
    if stage in {"scene_set", "scene_detail"}:
        return scene_time_of_day_instructions
    if stage == "asset_plan":
        return [
            "Review the compiled final asset-generation request as well as the asset plan; approving an abstract plan while its provider prompt is wrong is a failure.",
            "For every character, require subject_contract to preserve the intended cardinality. An ensemble must name and retain each distinct member; a plural role must not compile to one person.",
            "Require appearance_contract to make social position, role, occasion/state, silhouette, materials, condition, palette, and exclusions concrete enough to draw. Reject generic lifestyle clothing that does not distinguish the role.",
            "For every reusable asset, require reuse_contract. A neutral_anchor must contain no scene-specific morning/day/evening/night sky, moonlight, sunlight, shadows, or color temperature. A time_variant must name its daypart and derived neutral asset; a state_variant must name its derived asset.",
            "Use reason keys such as asset_subject_cardinality_mismatch, asset_appearance_contract_missing, asset_appearance_too_generic, asset_reuse_contract_missing, asset_neutral_time_leak, or asset_variant_source_missing.",
        ]
    if stage == "image_prompt":
        return [
            "Treat api_prompt_payload.prompt as a candidate provider prompt and first_frame_visual_plan / source contracts as review evidence; do not assume every upstream key belongs in the final prompt.",
            "For every cut make an explicit include / omit / add / replace judgment: include cut-local drawable facts, omit future motion/internal metadata/unneeded references, add visible behavior or period detail needed for imageability, and replace abstract or contradictory wording without changing the story event.",
            "Fail positive/negative polarity conflicts, especially when a must-show/current-state person, object, location, or state is also listed under not_yet or constraints.",
            "When story_time is non-empty, require period-consistent clothing, hair, architecture, everyday objects, materials, and technology; fail missing or contradictory historical grounding.",
            "Use time_of_day_contract_declared and time_of_day_status to distinguish current-contract omissions from undeclared legacy data. The contract is declared only by `video_metadata.scene_time_of_day_contract: required_v1`, not by a scene key alone. Fail missing/blank only when declared, always fail invalid_type, and do not reject a legacy omission solely for this newer key.",
            "When time_of_day is valid, require the provider prompt and drawable dependencies to preserve that exact scene daypart through sky brightness, natural-light direction/intensity, shadows, color temperature, and artificial lighting. Judge this separately from story_time and do not let either field overwrite the other.",
            "Use first_frame_visual_plan_status to fail canonical_missing, canonical_empty, or canonical_invalid_type for image_api_prompt_v2. Do not accept a synthesized legacy plan as evidence for a malformed or absent canonical v2 plan.",
            "Require every visibly important character/object/location to have the correct dependency and reference context. Do not require offscreen, merely mentioned, or future subjects, and reject scene-wide references copied into cuts where they are not visible.",
            "Fail Japanese scaffold residue or production meta such as 画面上の状態差として確定する, 次区間へ渡す, 後続場面へ観客を運ぶ, 視覚証拠:, or malformed/truncated prose.",
            "Compare all cuts in the scene composite. Exact or near-duplicate prompts pass only when an explicit reuse contract justifies them; otherwise each anti_redundancy_key and visual role must create a meaningful visible difference.",
            "Use reason keys such as image_prompt_temporal_polarity_conflict, image_prompt_period_mismatch, image_prompt_time_of_day_mismatch, api_prompt_drawable_dependency_missing, semantic_reference_mismatch, api_prompt_design_meta_leak, or scene_cut_prompt_too_similar.",
        ]
    if stage == "video_motion":
        return [
            "Treat provider_prompt_payload.prompt and provider_prompt_payload.negative_prompt as the exact reviewed provider text. Read projection_review_contract and video_prompt_ir as the trace back to canonical story, scene, cut, frame-boundary, and provider inputs; do not approve raw motion_prompt prose independently of that compiled payload.",
            "Fail immediately when provider_prompt_payload.quality_issues or video_prompt_ir.quality_issues contains any item with blocking=true. Repair the canonical motion fields and recompile; never approve by deleting the diagnostic or editing compiled prose.",
            "Pass only when the clip departs naturally from the approved first-frame visible state, has one primary motion, and reaches the declared end_state, handoff_state, or last-frame boundary without inventing an intervening cut, fade, dissolve, or different shot.",
            "Require the primary motion to name a concrete visible subject and one observable action. Require the end state to say who or what stops where and in which physical pose, position, or object state. Reject unresolved alternatives such as または, もしくは, あるいは, or or.",
            "Fail when subject, environment, emotion, and camera instructions compete. For Kling, require a maximum of two camera operations and one continuous shot; camera wording hidden in another fragment still counts toward that limit.",
            "Environment and emotion must add independent visible information rather than restating the primary motion. Compare every cut in the scene and reject exact or near-duplicate primary motions or end states unless an explicit reuse contract justifies them.",
            "Use source_event_contract and review-only dependencies to fail motion that crosses its assigned event or reveal boundary, adds a new character or important object, exposes withheld information, or advances into a later cut even when the prose is visually plausible.",
            "Require the primary motion to visibly perform the source causal action assigned to this cut; naming a reaction, atmosphere, or generic change without enacting that cause must fail.",
            "The start state must remain strictly before the primary motion and must not pre-consume or already complete that action in the first frame.",
            "For adjacent cuts in the same location, compare the previous end state with the next start state and fail any unexplained reset of pose, blocking, object position, light, or progress.",
            "Track prop possession causally across cuts: a prop must be visibly acquired before any later possession state, and the sequence must not jump from absent or untouched to already held.",
            "When historical time or scene time_of_day is present, require continuity of clothing, hair, architecture, everyday objects, materials, technology, sky brightness, natural/artificial light, shadow, and color temperature. Do not turn continuity metadata into an unauthored time-lapse or lighting transition.",
            "Require every active provider-projected group in projection_review_contract to have one matching non-empty included fragment rendered in the exact provider prompt. Reject missing, duplicated, shadowed-source, untraced, or contradictory fragments and any internal IDs, paths, hashes, design key labels, image prompt, or narration prose leaking into provider text.",
            "Validate every reference role against ordered references and the visible use described in continuity. Reject missing, reordered, duplicated, path-leaking, or semantically mismatched reference-role bindings.",
            "Fail if negative constraints, provider_request_binding, duration, quality, aspect ratio, first/last frame, ordered references, reference-content hashes, model, backend, or execution options are absent, stale, contradicted by the entry, or approved for a channel the selected provider adapter does not transmit.",
            "Use reason keys such as video_prompt_start_boundary_mismatch, video_prompt_multiple_primary_motions, video_prompt_unresolved_alternative, video_prompt_abstract_primary_motion, video_prompt_abstract_end_state, video_prompt_duplicate_secondary_motion, video_prompt_cross_cut_motion_duplicate, video_prompt_reference_role_mismatch, video_prompt_camera_conflict, video_prompt_end_boundary_mismatch, video_prompt_event_boundary_violation, video_prompt_invented_subject, video_prompt_source_causal_action_missing, video_prompt_start_preconsumes_primary_motion, video_prompt_adjacent_cut_state_reset, video_prompt_prop_possession_jump, video_prompt_period_continuity_mismatch, video_prompt_time_of_day_mismatch, video_prompt_projection_trace_mismatch, or video_prompt_provider_binding_stale.",
        ]
    if stage != "cut_blueprint":
        return []
    return [
        *scene_time_of_day_instructions,
        "For `cut_blueprint` failures, each blocked finding must include a concrete producer-facing repair example.",
        "The example should say what to add, remove, or strengthen in the affected cut contract / viewer contract / first-frame visual plan / downstream prompt requirements.",
        "Use cut_context_packet and cut_context_packet_diagnostics as repair input when present: if a packet diagnostic reports missing roles, visual proof, event beat, reveal boundary, or previous/next delta, state which packet field and source contract field should be reinforced.",
        "Prefer compact examples such as: `Add messenger and two witnesses as visible public-proof roles in scene80_cut01; require slipper in messenger hand, Cinderella watching, and no fitted-foot payoff yet.`",
        "Do not rewrite the artifact yourself and do not invent a different story. The example is guidance for the producer repair agent, not a patch applied by the reviewer.",
    ]


def render_prompt(*, stage: str, run_dir: Path, collection_path: Path, scope_path: Path, report_path: Path) -> str:
    source_artifacts = _source_artifacts(run_dir, stage)
    source_lines = [f"- `{(run_dir / rel).resolve()}`" for rel in source_artifacts]
    stage_specific_instructions = _stage_specific_review_instructions(stage)
    foundation_criteria_lines: list[str] = []
    if stage in FOUNDATION_SEMANTIC_CRITERIA:
        criterion_ids = list(FOUNDATION_SEMANTIC_CRITERIA[stage])
        foundation_criteria_lines = [
            "Evaluate every required foundation criterion below in this exact order:",
            *[f"- `{criterion_id}`" for criterion_id in criterion_ids],
            "For each criterion, record `criterion_id`, `status` (`passed` or `failed`), and non-empty artifact-local `evidence` naming the source artifact and field/scene that supports the result.",
            "Write all criterion objects on one `criteria_results_json:` line as a valid JSON array, preserving the exact criterion order with no missing, duplicate, or extra IDs.",
            "The overall status may be `passed` only when every criterion status is `passed`.",
            "Example: criteria_results_json: "
            + json.dumps(
                [
                    {
                        "criterion_id": criterion_id,
                        "status": "passed",
                        "evidence": f"{stage}.md:<field or scene-specific evidence>",
                    }
                    for criterion_id in criterion_ids
                ],
                ensure_ascii=False,
            ),
        ]
    return "\n".join(
        [
            f"You are a contextless semantic review agent for ToC `{stage}` artifacts.",
            "",
            "You do semantic judgment only. The workspace is read-only: do not edit any artifact and do not repair outputs.",
            "Do not spawn or delegate to another agent. Read the listed artifacts and make the judgment yourself.",
            "Return the complete machine-readable report as your final response. The trusted orchestrator will validate and save it.",
            "Structural completeness is checked by deterministic functions elsewhere; your job is to catch meaning errors that structurally valid data can hide.",
            "",
            "Read these artifacts in order:",
            f"1. `{scope_path}`",
            f"2. `{collection_path}`",
            f"3. `{report_path}`",
            "",
            "Use these source artifacts as cross-check context when present:",
            *(source_lines or ["- `(none discovered)`"]),
            "",
            f"The pending report path is `{report_path}`; do not write it yourself.",
            "",
            "Judge whether each entry preserves the intended story/source meaning and is usable by the next downstream stage.",
            "Check subject identity, location, object/setpiece visibility, timeline, scene time-of-day continuity, reveal order, continuity, narration alignment, and output-media suitability when those fields exist.",
            "For planning stages (`research`, `story`, `scene_set`, `scene_detail`, `cut_blueprint`, `asset_plan`, `image_prompt`, `narration`, `video_motion`), do not fail solely because referenced media files such as scene stills, videos, audio, or asset images do not exist yet; those files are generated and judged by frontend human review or deterministic output validators.",
            "Flag round-robin references, always-on story objects in unrelated entries, mismatched location/character/object references, missing semantic contracts, and outputs that do not support the contract.",
            "For entries whose review_scope is `scene_composite`, this is a gate, not advice: judge the scene as a whole across its split cuts.",
            "A scene_composite passes only when the exact authored `event_beat_inventory` mirrors every ordered nonblank beat ID from `scene_event.event_sequence`, including every authored entry with `must_be_seen: false`; every inventory beat's arbitrary nonblank `beat_function` matches its corresponding source beat whether assigned or not. Only inventory beats with `must_be_seen != false`, plus every required scene_cut_coverage_plan.scene_obligation, must be assigned to cut_entries via cut_contract.source_event_contract. event_context_for_cut is a derived downstream projection rather than an authoring source, story_event_obligations remain legacy projection only, each cut has a concrete audience_knowledge_delta and causal_proof where required, role_coverage is not collapsed into protagonist-only imagery, no cut invents source_event_contract.event_facts_not_to_invent, the cut prompts collectively visualize the scene's intended question/value shift/causal turn/handoff, and the planned videos can connect into one meaningful scene.",
            "Do not require a fixed beat-function vocabulary, ladder, order, or cut count. A valid one-beat scene with any authored nonblank function must not fail because a predefined function name is absent; judge whether the cuts were reverse-designed from the scene's exact authored beats and actual visual obligations.",
            "If the scene meaning cannot be conveyed by the listed cuts, fail the gate. Recommend more cuts only when a distinct authored beat or semantic obligation is uncovered: the authored beat must be required (`must_be_seen != false`), while the distinct obligation must be unable to fit an existing one-intent cut. Otherwise require a stronger existing per-cut prompt or a different scene split without duplicating an obligation.",
            *stage_specific_instructions,
            *foundation_criteria_lines,
            "",
            "Report format:",
            "status: passed|failed",
            "semantic_review_input_digest: copy the exact semantic_review_input_digest from the scope",
            "reviewed_entries: [...]",
            "blocked_entries: [...]",
            "findings: [...]",
            "failed_selectors: [...]",
            *(
                [
                    'criteria_results_json: [{"criterion_id": "...", "status": "passed|failed", '
                    '"evidence": "research.md/story.md:<field or scene>"}, ...]'
                ]
                if stage in FOUNDATION_SEMANTIC_CRITERIA
                else []
            ),
            "reason_keys: [research_baseline_too_thin|research_timeline_incoherent|research_character_model_incomplete|research_conflict_unresolved_for_story|story_baseline_mismatch|story_timeline_mismatch|story_character_continuity_mismatch|story_conflict_progression_weak|story_event_unassigned|story_scene_allocation_generic|story_scene_duplicate_responsibility|internal_reference_unresolved|semantic_contract_missing|semantic_subject_mismatch|semantic_location_mismatch|semantic_object_mismatch|semantic_reference_mismatch|semantic_timeline_mismatch|scene_time_of_day_missing|scene_time_of_day_invalid_type|scene_time_of_day_continuity_mismatch|scene_location_route_incomplete|scene_location_route_order_mismatch|scene_location_segment_not_drawable|image_prompt_time_of_day_mismatch|semantic_reveal_order_mismatch|semantic_output_mismatch|scene_cut_coverage_insufficient|scene_cut_prompt_too_similar|scene_meaning_not_visualized_across_cuts|scene_video_handoff_weak|scene_requires_more_cuts|cut_prompt_requires_reinforcement|story_event_obligation_unassigned|audience_knowledge_delta_missing|causal_proof_weak|role_coverage_missing|static_first_frame_not_imageable|scene_cut_redundancy_excessive|...]",
            "notes: [...]",
            "",
            f"Run dir: `{run_dir.resolve()}`",
        ]
    )


def write_legacy_image_prompt_aliases(run_dir: Path, paths: dict[str, Path], *, entries: list[dict[str, object]], prompt: str) -> None:
    write_text(run_dir, run_dir / IMAGE_PROMPT_JUDGMENT_COLLECTION, (run_dir / paths["collection"]).read_text(encoding="utf-8"))
    scope_text = (run_dir / paths["scope"]).read_text(encoding="utf-8")
    write_text(run_dir, run_dir / IMAGE_PROMPT_JUDGMENT_SCOPE, scope_text)
    write_text(run_dir, run_dir / IMAGE_PROMPT_JUDGMENT_PROMPT, prompt + "\n")
    scope = json.loads(scope_text)
    input_digest = str(scope.get("semantic_review_input_digest") or "")
    write_text(
        run_dir,
        run_dir / IMAGE_PROMPT_JUDGMENT_REPORT,
        render_report_template(
            stage="image_prompt",
            run_dir=run_dir,
            scope_path=run_dir / IMAGE_PROMPT_JUDGMENT_SCOPE,
            collection_path=run_dir / IMAGE_PROMPT_JUDGMENT_COLLECTION,
            semantic_review_input_digest_value=input_digest or None,
        )
        + "\n",
    )
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "review.image_prompt.judgment.collection": IMAGE_PROMPT_JUDGMENT_COLLECTION.as_posix(),
            "review.image_prompt.judgment.scope": IMAGE_PROMPT_JUDGMENT_SCOPE.as_posix(),
            "review.image_prompt.judgment.prompt": IMAGE_PROMPT_JUDGMENT_PROMPT.as_posix(),
            "review.image_prompt.judgment.report": IMAGE_PROMPT_JUDGMENT_REPORT.as_posix(),
            "review.image_prompt.judgment.status": "pending",
            "review.image_prompt.judgment.generated_at": now_iso(),
            "review.image_prompt.judgment.entry_count": str(len(entries)),
        },
    )


def build_pack(run_dir: Path, stage: str) -> tuple[Path, Path, Path, Path, int]:
    manifest = load_manifest(run_dir)
    entries = collect_entries(stage, run_dir, manifest=manifest)
    paths = semantic_review_relpaths(stage)
    collection_path = run_dir / paths["collection"]
    scope_path = run_dir / paths["scope"]
    prompt_path = run_dir / paths["prompt"]
    report_path = run_dir / paths["report"]
    shard_plan: dict[str, object] | None = None

    if stage == "image_prompt":
        try:
            shard_plan = materialize_image_prompt_scene_shards(
                run_dir=run_dir,
                entries=entries,
                canonical_scope_path=scope_path,
                canonical_report_path=report_path,
            )
        except ValueError as exc:
            # Keep a canonical, inspectable fail-closed scope so the server can
            # report the coverage defect without starting an unscoped review.
            shard_plan = _invalid_image_prompt_scene_shard_plan(entries, exc)

    write_text(run_dir, collection_path, render_collection(stage, entries))
    prompt = render_prompt(stage=stage, run_dir=run_dir, collection_path=collection_path, scope_path=scope_path, report_path=report_path)
    write_text(run_dir, prompt_path, prompt + "\n")
    scope_text = render_scope_json(
        stage=stage,
        run_dir=run_dir,
        entries=entries,
        collection_path=collection_path,
        scope_path=scope_path,
        prompt_path=prompt_path,
        report_path=report_path,
        shard_plan=shard_plan,
    )
    write_text(
        run_dir,
        scope_path,
        scope_text,
    )
    input_digest = str(json.loads(scope_text).get("semantic_review_input_digest") or "")
    write_text(
        run_dir,
        report_path,
        render_report_template(
            stage=stage,
            run_dir=run_dir,
            scope_path=scope_path,
            collection_path=collection_path,
            semantic_review_input_digest_value=input_digest or None,
        )
        + "\n",
    )
    append_state_snapshot(
        run_dir / "state.txt",
        semantic_state_updates(stage, status="pending", entry_count=len(entries), generated_at=now_iso()),
    )
    if stage == "image_prompt":
        write_legacy_image_prompt_aliases(run_dir, paths, entries=entries, prompt=prompt)
    return collection_path, scope_path, prompt_path, report_path, len(entries)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic contextless semantic review pack.")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp> or a scene run directory.")
    parser.add_argument("--stage", required=True, choices=sorted(SEMANTIC_REVIEW_STAGES))
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        raise SystemExit(f"Run directory not found: {run_dir}")
    _, _, prompt_path, _, entry_count = build_pack(run_dir, args.stage)
    print((prompt_path).read_text(encoding="utf-8"))
    print(f"\n[semantic-review-pack] stage={args.stage} entries={entry_count}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
