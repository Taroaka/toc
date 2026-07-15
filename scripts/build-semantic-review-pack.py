#!/usr/bin/env python3
"""Build a deterministic prompt pack for contextless semantic review."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, now_iso  # noqa: E402
from toc.semantic_pack import collect_entries, load_manifest  # noqa: E402
from toc.semantic_review import (  # noqa: E402
    FOUNDATION_SEMANTIC_CRITERIA,
    IMAGE_PROMPT_JUDGMENT_COLLECTION,
    IMAGE_PROMPT_JUDGMENT_PROMPT,
    IMAGE_PROMPT_JUDGMENT_REPORT,
    IMAGE_PROMPT_JUDGMENT_SCOPE,
    SEMANTIC_REVIEW_STAGES,
    semantic_review_relpaths,
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


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


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
    payload = {
        "stage": stage,
        "run_dir": str(run_dir.resolve()),
        "entry_count": len(entries),
        "entry_ids": [str(entry.get("id") or entry.get("selector") or "") for entry in entries],
        "review_scope": "all_entries",
        "diagnostics": diagnostics,
        "source_artifacts": _source_artifacts(run_dir, stage),
        "artifacts": {
            "collection": str(collection_path.relative_to(run_dir)),
            "scope": str(scope_path.relative_to(run_dir)),
            "prompt": str(prompt_path.relative_to(run_dir)),
            "report": str(report_path.relative_to(run_dir)),
        },
        "generated_at": now_iso(),
    }
    if shard_plan:
        payload.update(
            {
                "review_scope": shard_plan.get("review_scope", payload["review_scope"]),
                "shards": shard_plan.get("shards", []),
                "coverage": shard_plan.get("coverage", {}),
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _entry_id(entry: dict[str, object], index: int) -> str:
    return str(entry.get("id") or entry.get("selector") or f"entry_{index:03d}").strip()


def _image_prompt_scene_token(entry: dict[str, object], entry_id: str) -> str:
    raw_scene_id = str(entry.get("scene_id") or "").strip()
    for candidate in (raw_scene_id, entry_id):
        match = re.search(r"scene[_:\s-]*(\d+)", candidate, re.I)
        if match:
            return str(int(match.group(1)))
    if raw_scene_id:
        label = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw_scene_id).strip("._-").lower()
        if label:
            return label
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
        base = shard_root / f"{index:03d}_{shard_id}"
        collection_path = base.with_suffix(".collection.md")
        scope_path = base.with_suffix(".scope.json")
        prompt_path = base.with_suffix(".prompt.md")
        report_path = base.with_suffix(".report.md")
        write_text(collection_path, render_collection("image_prompt", shard_entries))
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
            "source_artifacts": _source_artifacts(run_dir, "image_prompt"),
            "artifacts": {
                "collection": str(collection_path.relative_to(run_dir)),
                "scope": str(scope_path.relative_to(run_dir)),
                "prompt": str(prompt_path.relative_to(run_dir)),
                "report": str(report_path.relative_to(run_dir)),
            },
            "generated_at": now_iso(),
        }
        write_text(scope_path, json.dumps(shard_scope, ensure_ascii=False, indent=2) + "\n")
        shard_prompt = render_prompt(
            stage="image_prompt",
            run_dir=run_dir,
            collection_path=collection_path,
            scope_path=scope_path,
            report_path=report_path,
        )
        write_text(
            prompt_path,
            shard_prompt.rstrip()
            + "\n\n"
            + f"Review only image_prompt scene shard `{shard_id}`.\n"
            + "Expected reviewed_entries exactly once: "
            + json.dumps(entry_ids, ensure_ascii=False)
            + "\n",
        )
        write_text(
            report_path,
            render_report_template(
                stage="image_prompt",
                run_dir=run_dir,
                scope_path=scope_path,
                collection_path=collection_path,
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
    for index, entry in enumerate(entries, start=1):
        entry_id = str(entry.get("id") or entry.get("selector") or f"entry_{index:03d}")
        if _truthy(entry.get("semantic_contract_missing")) or _truthy(entry.get("motion_contract_missing")):
            missing_contract_entries.append(entry_id)
            failed_selectors.append(entry_id)
        if _truthy(entry.get("contact_sheet_missing")):
            missing_contact_sheet_entries.append(entry_id)
        if _truthy(entry.get("sampled_frames_missing")):
            missing_sampled_frame_entries.append(entry_id)
    return {
        "missing_semantic_contract_count": len(missing_contract_entries),
        "missing_semantic_contract_entries": missing_contract_entries,
        "missing_contact_sheet_count": len(missing_contact_sheet_entries),
        "missing_contact_sheet_entries": missing_contact_sheet_entries,
        "missing_sampled_frame_count": len(missing_sampled_frame_entries),
        "missing_sampled_frame_entries": missing_sampled_frame_entries,
        "failed_selectors": sorted(set(failed_selectors)),
    }


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
        "asset_plan": ["asset_inventory.md", "asset_plan.md"],
        "image_prompt": ["asset_inventory.md", "asset_plan.md", "image_generation_requests.md", "image_prompt_story_review.md"],
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


def render_report_template(*, stage: str, run_dir: Path, scope_path: Path, collection_path: Path) -> str:
    lines = [
        f"# Semantic Review Report: {stage}",
        "",
        f"- run_dir: `{run_dir.resolve()}`",
        f"- stage: `{stage}`",
        f"- scope: `{scope_path}`",
        f"- collection: `{collection_path}`",
        "- status: `pending`",
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
            "Check timeline, characters and motivations, conflict escalation/resolution, important-event coverage, distinct scene responsibility, internal research_refs, and duration-aware scene allocation.",
            "Fail if story order contradicts research, character state changes without cause, every scene repeats the same conflict or turn, important events are unassigned, internal refs do not resolve, or scenes are too generic/duplicative to split into cuts.",
            "Do not impose a fixed scene count. Judge semantic coverage against target_duration_seconds and the story's own meaningful scene responsibilities.",
            "Do not browse or validate external URLs, editions, translations, rights, or factual fidelity. External source authenticity is outside this gate.",
            "Use reason keys such as story_baseline_mismatch, story_timeline_mismatch, story_character_continuity_mismatch, story_conflict_progression_weak, story_event_unassigned, story_scene_allocation_generic, story_scene_duplicate_responsibility, or internal_reference_unresolved.",
        ]
    if stage != "cut_blueprint":
        return []
    return [
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
            "You do semantic judgment only. Do not edit source artifacts and do not repair outputs.",
            f"You MUST edit exactly one file: `{report_path}`. This report is not a source artifact; replacing its pending template is required.",
            "Do not spawn or delegate to another agent. Read the listed artifacts and make the judgment yourself.",
            "Do not return the verdict only in chat. The task is incomplete until the report file contains the final machine-readable verdict.",
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
            f"Write the final report to `{report_path}` and replace the pending template.",
            "",
            "Judge whether each entry preserves the intended story/source meaning and is usable by the next downstream stage.",
            "Check subject identity, location, object/setpiece visibility, timeline, reveal order, continuity, narration alignment, and output-media suitability when those fields exist.",
            "For planning stages (`research`, `story`, `scene_set`, `scene_detail`, `cut_blueprint`, `asset_plan`, `image_prompt`, `narration`, `video_motion`), do not fail solely because referenced media files such as scene stills, videos, audio, or asset images do not exist yet; those files are generated and judged by frontend human review or deterministic output validators.",
            "Flag round-robin references, always-on story objects in unrelated entries, mismatched location/character/object references, missing semantic contracts, and outputs that do not support the contract.",
            "For entries whose review_scope is `scene_composite`, this is a gate, not advice: judge the scene as a whole across its split cuts.",
            "A scene_composite passes only when scene_cut_coverage_plan.scene_obligations and scene_event.event_sequence setup/pressure/turn/payoff beats are assigned to cut_entries via cut_contract.source_event_contract, event_context_for_cut is a derived downstream projection rather than an authoring source, story_event_obligations remain legacy projection only, each cut has a concrete audience_knowledge_delta and causal_proof where required, role_coverage is not collapsed into protagonist-only imagery, no cut invents source_event_contract.event_facts_not_to_invent, the cut prompts collectively visualize the scene's intended question/value shift/causal turn/handoff, and the planned videos can connect into one meaningful scene.",
            "Do not require a fixed setup/turn/handoff order or a fixed cut count; judge whether the cuts were reverse-designed from the scene's actual visual obligations.",
            "If the scene meaning cannot be conveyed by the listed cuts, fail the gate and state whether it needs more cuts, stronger per-cut prompts, or a different scene split.",
            *stage_specific_instructions,
            *foundation_criteria_lines,
            "",
            "Report format:",
            "status: passed|failed",
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
            "reason_keys: [research_baseline_too_thin|research_timeline_incoherent|research_character_model_incomplete|research_conflict_unresolved_for_story|story_baseline_mismatch|story_timeline_mismatch|story_character_continuity_mismatch|story_conflict_progression_weak|story_event_unassigned|story_scene_allocation_generic|story_scene_duplicate_responsibility|internal_reference_unresolved|semantic_contract_missing|semantic_subject_mismatch|semantic_location_mismatch|semantic_object_mismatch|semantic_reference_mismatch|semantic_timeline_mismatch|semantic_reveal_order_mismatch|semantic_output_mismatch|scene_cut_coverage_insufficient|scene_cut_prompt_too_similar|scene_meaning_not_visualized_across_cuts|scene_video_handoff_weak|scene_requires_more_cuts|cut_prompt_requires_reinforcement|story_event_obligation_unassigned|audience_knowledge_delta_missing|causal_proof_weak|role_coverage_missing|static_first_frame_not_imageable|scene_cut_redundancy_excessive|...]",
            "notes: [...]",
            "",
            f"Run dir: `{run_dir.resolve()}`",
        ]
    )


def write_legacy_image_prompt_aliases(run_dir: Path, paths: dict[str, Path], *, entries: list[dict[str, object]], prompt: str) -> None:
    write_text(run_dir / IMAGE_PROMPT_JUDGMENT_COLLECTION, (run_dir / paths["collection"]).read_text(encoding="utf-8"))
    write_text(run_dir / IMAGE_PROMPT_JUDGMENT_SCOPE, (run_dir / paths["scope"]).read_text(encoding="utf-8"))
    write_text(run_dir / IMAGE_PROMPT_JUDGMENT_PROMPT, prompt + "\n")
    write_text(
        run_dir / IMAGE_PROMPT_JUDGMENT_REPORT,
        render_report_template(
            stage="image_prompt",
            run_dir=run_dir,
            scope_path=run_dir / IMAGE_PROMPT_JUDGMENT_SCOPE,
            collection_path=run_dir / IMAGE_PROMPT_JUDGMENT_COLLECTION,
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

    write_text(collection_path, render_collection(stage, entries))
    write_text(
        scope_path,
        render_scope_json(
            stage=stage,
            run_dir=run_dir,
            entries=entries,
            collection_path=collection_path,
            scope_path=scope_path,
            prompt_path=prompt_path,
            report_path=report_path,
            shard_plan=shard_plan,
        ),
    )
    prompt = render_prompt(stage=stage, run_dir=run_dir, collection_path=collection_path, scope_path=scope_path, report_path=report_path)
    write_text(prompt_path, prompt + "\n")
    write_text(report_path, render_report_template(stage=stage, run_dir=run_dir, scope_path=scope_path, collection_path=collection_path) + "\n")
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
