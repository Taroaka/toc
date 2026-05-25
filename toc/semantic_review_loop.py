from __future__ import annotations

import os
from pathlib import Path

from toc.harness import now_iso
from toc.semantic_review import semantic_review_relpaths


DEFAULT_SEMANTIC_REVIEW_MAX_ATTEMPTS = 3
DEFAULT_SEMANTIC_REPAIR_TIMEOUT_SECONDS = 900


SEMANTIC_REVIEW_PRODUCER_TARGETS: dict[str, dict[str, object]] = {
    "scene_set": {
        "slot": "p410",
        "owner": "scene design producer",
        "artifacts": ["story.md", "script.md", "video_manifest.md"],
        "focus": "scene purpose, causal order, location/time continuity, and story meaning",
    },
    "scene_detail": {
        "slot": "p410",
        "owner": "scene detail producer",
        "artifacts": ["script.md", "video_manifest.md"],
        "focus": "scene detail, visual beats, character state, and handoff meaning",
    },
    "cut_blueprint": {
        "slot": "p420",
        "owner": "cut blueprint producer",
        "artifacts": ["script.md", "video_manifest.md"],
        "focus": "cut function, must-show contract, reveal order, and downstream handoff",
    },
    "asset_plan": {
        "slot": "p540",
        "owner": "asset planning producer",
        "artifacts": ["asset_inventory.md", "asset_plan.md", "asset_generation_requests.md", "video_manifest.md"],
        "focus": "character/object/location coverage, asset category, story purpose, and prompt contract",
    },
    "asset_output": {
        "slot": "p570",
        "owner": "asset output producer",
        "artifacts": ["asset_inventory.md", "asset_plan.md", "asset_generation_requests.md", "assets/**"],
        "focus": "generated asset subject, category, story role, contact sheet evidence, and reusable reference quality",
    },
    "image_prompt": {
        "slot": "p640",
        "owner": "image prompt producer",
        "artifacts": ["image_generation_requests.md", "video_manifest.md", "asset_plan.md"],
        "focus": "prompt-to-cut contract, reference choice, location/object/character correctness, and first-frame meaning",
    },
    "scene_image": {
        "slot": "p670",
        "owner": "scene image producer",
        "artifacts": ["image_generation_requests.md", "assets/scenes/**", "video_manifest.md"],
        "focus": "generated scene stills, referenced assets, cut meaning, location/time state, and contact sheet evidence",
    },
    "narration": {
        "slot": "p720",
        "owner": "narration producer",
        "artifacts": ["video_manifest.md", "narration_text_review.md", "assets/audio/**"],
        "focus": "narration role, non-redundant emotional meaning, TTS text, timing, and continuity",
    },
    "video_motion": {
        "slot": "p820",
        "owner": "video motion producer",
        "artifacts": ["video_generation_requests.md", "video_manifest.md"],
        "focus": "motion prompt, first-frame contract, subject/environment movement, and end state",
    },
    "video_clip": {
        "slot": "p850",
        "owner": "video clip producer",
        "artifacts": ["video_generation_requests.md", "assets/scenes/**/*.mp4", "video_manifest.md"],
        "focus": "generated clip frames, motion continuity, no unintended additions, and cut end state",
    },
    "render": {
        "slot": "p930",
        "owner": "render producer",
        "artifacts": ["video.mp4", "run_report.md", "eval_report.json", "video_manifest.md"],
        "focus": "final render continuity, narration/video alignment, scene ordering, and approved upstream meaning",
    },
}


def semantic_review_max_attempts() -> int:
    raw = os.environ.get("TOC_SEMANTIC_REVIEW_MAX_ATTEMPTS", "").strip()
    if not raw:
        return DEFAULT_SEMANTIC_REVIEW_MAX_ATTEMPTS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_SEMANTIC_REVIEW_MAX_ATTEMPTS


def semantic_repair_timeout_seconds() -> int:
    raw = os.environ.get("TOC_SEMANTIC_REPAIR_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_SEMANTIC_REPAIR_TIMEOUT_SECONDS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_SEMANTIC_REPAIR_TIMEOUT_SECONDS


def semantic_repair_relpaths(stage: str, round_number: int) -> dict[str, Path]:
    base = Path("logs/review/semantic")
    return {
        "prompt": base / f"{stage}.repair_round_{round_number:02d}.prompt.md",
        "report": base / f"{stage}.repair_round_{round_number:02d}.producer_report.md",
    }


def semantic_loop_state_updates(
    stage: str,
    *,
    status: str,
    attempt: int,
    max_attempts: int,
    error_count: int | None = None,
) -> dict[str, str]:
    updates = {
        f"review.semantic.{stage}.loop.status": status,
        f"review.semantic.{stage}.loop.attempt": str(attempt),
        f"review.semantic.{stage}.loop.max_attempts": str(max_attempts),
        f"review.semantic.{stage}.loop.updated_at": now_iso(),
    }
    if error_count is not None:
        updates[f"review.semantic.{stage}.loop.error_count"] = str(error_count)
    return updates


def semantic_repair_state_updates(
    stage: str,
    *,
    status: str,
    round_number: int,
    max_attempts: int,
    error_count: int | None = None,
) -> dict[str, str]:
    relpaths = semantic_repair_relpaths(stage, round_number)
    updates = {
        f"review.semantic.{stage}.repair.status": status,
        f"review.semantic.{stage}.repair.round": str(round_number),
        f"review.semantic.{stage}.repair.max_attempts": str(max_attempts),
        f"review.semantic.{stage}.repair.prompt": relpaths["prompt"].as_posix(),
        f"review.semantic.{stage}.repair.report": relpaths["report"].as_posix(),
        f"review.semantic.{stage}.repair.updated_at": now_iso(),
    }
    if error_count is not None:
        updates[f"review.semantic.{stage}.repair.error_count"] = str(error_count)
    return updates


def write_semantic_repair_prompt(
    run_dir: Path,
    stage: str,
    *,
    round_number: int,
    max_attempts: int,
    errors: list[str] | tuple[str, ...],
) -> dict[str, Path]:
    relpaths = semantic_repair_relpaths(stage, round_number)
    prompt_path = run_dir / relpaths["prompt"]
    report_path = run_dir / relpaths["report"]
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    review_paths = semantic_review_relpaths(stage)
    review_report_path = run_dir / review_paths["report"]
    collection_path = run_dir / review_paths["collection"]
    scope_path = run_dir / review_paths["scope"]
    review_report = review_report_path.read_text(encoding="utf-8", errors="replace") if review_report_path.exists() else "(missing semantic report)"
    collection_excerpt = collection_path.read_text(encoding="utf-8", errors="replace")[:12000] if collection_path.exists() else "(missing collection)"
    target = SEMANTIC_REVIEW_PRODUCER_TARGETS.get(stage, {})
    owner = str(target.get("owner") or f"{stage} producer")
    slot = str(target.get("slot") or "")
    focus = str(target.get("focus") or "stage semantic contract")
    artifacts = [str(item) for item in target.get("artifacts", [])] if isinstance(target.get("artifacts"), list) else []
    error_text = "\n".join(f"- {error}" for error in errors) or "- semantic reviewer did not provide a specific error"

    prompt = f"""# Semantic QA Producer Repair: {stage}

You are the original production-side agent for `{stage}` in this ToC run.

The contextless semantic review agent rejected the current artifact. Use the review findings as improvement instructions, repair the production artifacts, and leave the process in semantic-QA repair state. Do not advance the process slot to the next stage. Do not edit the semantic review report to fake a pass; the orchestrator will rebuild the pack and call the semantic reviewer again.

- Run directory: `{run_dir}`
- Current semantic stage: `{stage}`
- Process slot kept in semantic QA: `{slot or "(stage-owned slot)"}`
- Repair round: `{round_number}` of `{max_attempts - 1}`
- Producing owner: `{owner}`
- Repair focus: {focus}
- Primary editable artifacts: {", ".join(artifacts) if artifacts else "(stage-owned artifacts)"}
- Producer repair report to write: `{relpaths["report"].as_posix()}`

## Reviewer Findings / Gate Errors

{error_text}

## Failed Semantic Review Report

```text
{review_report[:16000]}
```

## Review Scope

- collection: `{review_paths["collection"].as_posix()}`
- scope: `{review_paths["scope"].as_posix()}`
- report: `{review_paths["report"].as_posix()}`

## Collection Excerpt

```text
{collection_excerpt}
```

## Required Work

1. Repair the production artifact(s) so the reviewed meaning is genuinely correct.
2. Preserve existing structure and paths unless a reviewer finding requires a targeted change.
3. If this stage owns generated media, update prompts/contracts and regenerate the affected media through the repository's canonical tooling when needed.
4. Keep the stage visible as semantic-QA repair, not as approved or advanced.
5. Write `{relpaths["report"].as_posix()}` with:
   - `status: done`
   - changed artifacts
   - reviewer findings addressed
   - remaining risks, if any

The next action after your repair will be a fresh contextless semantic review. Passing requires the reviewer report to say `status: passed`.
"""
    prompt_path.write_text(prompt + "\n", encoding="utf-8")
    report_path.write_text(
        f"# Semantic Producer Repair Report: {stage}\n\nstatus: pending\nround: {round_number}\ncreated_at: {now_iso()}\n\n",
        encoding="utf-8",
    )
    return {"prompt": prompt_path, "report": report_path}
