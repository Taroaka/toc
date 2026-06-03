#!/usr/bin/env python3
"""Build a deterministic prompt pack for contextless semantic review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, now_iso  # noqa: E402
from toc.semantic_pack import collect_entries, load_manifest  # noqa: E402
from toc.semantic_review import (  # noqa: E402
    IMAGE_PROMPT_JUDGMENT_COLLECTION,
    IMAGE_PROMPT_JUDGMENT_PROMPT,
    IMAGE_PROMPT_JUDGMENT_REPORT,
    IMAGE_PROMPT_JUDGMENT_SCOPE,
    SEMANTIC_REVIEW_STAGES,
    semantic_review_relpaths,
    semantic_state_updates,
)


STAGE_LABELS = {
    "scene_set": "scene set design",
    "scene_detail": "scene detail design",
    "cut_blueprint": "cut blueprint design",
    "asset_plan": "asset planning",
    "asset_output": "generated asset output",
    "image_prompt": "scene image prompt",
    "scene_image": "generated scene image output",
    "narration": "narration text and audio handoff",
    "video_motion": "video motion prompt",
    "video_clip": "generated video clip output",
    "render": "final render output",
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
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


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
    common = ["story.md", "script.md", "video_manifest.md"]
    by_stage = {
        "asset_plan": ["asset_inventory.md", "asset_plan.md"],
        "asset_output": ["asset_inventory.md", "asset_plan.md", "asset_generation_requests.md", "asset_generation_manifest.md", "location_asset_generation_manifest.md"],
        "image_prompt": ["asset_inventory.md", "asset_plan.md", "image_generation_requests.md", "image_prompt_story_review.md"],
        "scene_image": ["asset_inventory.md", "asset_plan.md", "image_generation_requests.md", "logs/review/semantic/scene_image.contact_sheet.png", "logs/review/semantic/scene_image.contact_sheet.jpg"],
        "narration": ["narration_text_review.md", "logs/review/narration_text_quality.md"],
        "video_motion": ["video_generation_requests.md"],
        "video_clip": ["video_generation_requests.md", "logs/review/semantic/video_clip.contact_sheet.png", "logs/review/semantic/video_clip.contact_sheet.jpg"],
        "render": ["video_clips.txt", "video_narration_list.txt", "run_report.md", "eval_report.json"],
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
    return dedent(
        f"""
        # Semantic Review Report: {stage}

        - run_dir: `{run_dir.resolve()}`
        - stage: `{stage}`
        - scope: `{scope_path}`
        - collection: `{collection_path}`
        - status: `pending`

        ## Reviewed Entries

        - `...`

        ## Blocked Entries

        - `...`

        ## Findings

        - `...`

        ## Reason Keys

        - `...`

        ## Notes

        - `...`
        """
    ).strip()


def render_prompt(*, stage: str, run_dir: Path, collection_path: Path, scope_path: Path, report_path: Path) -> str:
    source_artifacts = _source_artifacts(run_dir, stage)
    source_lines = [f"- `{(run_dir / rel).resolve()}`" for rel in source_artifacts]
    return "\n".join(
        [
            f"You are a contextless semantic review agent for ToC `{stage}` artifacts.",
            "",
            "You do semantic judgment only. Do not edit source artifacts and do not repair outputs.",
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
            "For upstream planning stages (`scene_set`, `scene_detail`, `cut_blueprint`, `asset_plan`, `image_prompt`), do not fail solely because referenced media files such as scene stills, videos, audio, or asset images do not exist yet; those files are generated and judged by later output stages. In upstream stages, judge whether the declared outputs/prompts/contracts would be meaningful if generated.",
            "For output stages (`asset_output`, `scene_image`, `video_clip`, `render`), generated file existence and semantic match are hard gates.",
            "Flag round-robin references, always-on story objects in unrelated entries, mismatched location/character/object references, missing semantic contracts, and outputs that do not support the contract.",
            "For entries whose review_scope is `scene_composite`, this is a gate, not advice: judge the scene as a whole across its split cuts.",
            "A scene_composite passes only when scene_cut_coverage_plan.scene_obligations and story_event_obligations are assigned to cut_entries, each cut has a concrete audience_knowledge_delta and causal_proof where required, role_coverage is not collapsed into protagonist-only imagery, the cut prompts collectively visualize the scene's intended question/value shift/causal turn/handoff, and the planned videos can connect into one meaningful scene.",
            "Do not require a fixed setup/turn/handoff order or a fixed cut count; judge whether the cuts were reverse-designed from the scene's actual visual obligations.",
            "If the scene meaning cannot be conveyed by the listed cuts, fail the gate and state whether it needs more cuts, stronger per-cut prompts, or a different scene split.",
            "",
            "Report format:",
            "status: passed|failed",
            "reviewed_entries: [...]",
            "blocked_entries: [...]",
            "findings: [...]",
            "failed_selectors: [...]",
            "reason_keys: [semantic_contract_missing|semantic_subject_mismatch|semantic_location_mismatch|semantic_object_mismatch|semantic_reference_mismatch|semantic_timeline_mismatch|semantic_reveal_order_mismatch|semantic_output_mismatch|scene_cut_coverage_insufficient|scene_cut_prompt_too_similar|scene_meaning_not_visualized_across_cuts|scene_video_handoff_weak|scene_requires_more_cuts|cut_prompt_requires_reinforcement|story_event_obligation_unassigned|audience_knowledge_delta_missing|causal_proof_weak|role_coverage_missing|static_first_frame_not_imageable|scene_cut_redundancy_excessive|...]",
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
