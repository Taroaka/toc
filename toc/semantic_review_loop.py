from __future__ import annotations

import os
from pathlib import Path

from toc.harness import now_iso
from toc.semantic_review import semantic_review_relpaths


DEFAULT_SEMANTIC_REVIEW_MAX_ATTEMPTS = 1
DEFAULT_SEMANTIC_REVIEW_TIMEOUT_SECONDS = 1800
DEFAULT_SEMANTIC_REPAIR_TIMEOUT_SECONDS = 1800
DEFAULT_SCENE_DETAIL_REVIEW_CONCURRENCY = 6


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
    "image_prompt": {
        "slot": "p640",
        "owner": "image prompt producer",
        "artifacts": ["image_generation_requests.md", "video_manifest.md", "asset_plan.md"],
        "focus": "prompt-to-cut contract, reference choice, location/object/character correctness, and first-frame meaning",
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


def semantic_review_timeout_seconds() -> int:
    raw = os.environ.get("TOC_SEMANTIC_REVIEW_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_SEMANTIC_REVIEW_TIMEOUT_SECONDS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_SEMANTIC_REVIEW_TIMEOUT_SECONDS


def scene_detail_review_concurrency() -> int:
    raw = os.environ.get("TOC_SCENE_DETAIL_REVIEW_CONCURRENCY", "").strip()
    if not raw:
        return DEFAULT_SCENE_DETAIL_REVIEW_CONCURRENCY
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_SCENE_DETAIL_REVIEW_CONCURRENCY


def semantic_repair_relpaths(stage: str, round_number: int) -> dict[str, Path]:
    base = Path("logs/review/semantic")
    return {
        "prompt": base / f"{stage}.repair_round_{round_number:02d}.prompt.md",
        "report": base / f"{stage}.repair_round_{round_number:02d}.producer_report.md",
    }


def _semantic_review_failed_selectors(review_report: str) -> set[str]:
    selectors: set[str] = set()
    in_failed_list = False
    for raw in review_report.splitlines():
        stripped = raw.strip()
        if stripped.startswith("failed_selectors:") or stripped.startswith("blocked_entries:"):
            inline = stripped.split(":", 1)[1].strip()
            for value in _semantic_review_selector_values(inline):
                _add_semantic_review_selector_aliases(selectors, value)
            in_failed_list = inline in {"", "[]", "[ ]"}
            continue
        if in_failed_list and stripped and not stripped.startswith("-"):
            in_failed_list = False
        if in_failed_list and stripped.startswith("-"):
            value = _semantic_review_selector_scalar(stripped[1:])
            if value:
                _add_semantic_review_selector_aliases(selectors, value)
    return selectors


def _semantic_review_selector_values(raw: str) -> list[str]:
    value = raw.strip()
    if not value or value in {"[]", "[ ]"}:
        return []
    if value.startswith("[") and value.endswith("]"):
        return [
            cleaned
            for item in value[1:-1].split(",")
            if (cleaned := _semantic_review_selector_scalar(item))
        ]
    cleaned = _semantic_review_selector_scalar(value)
    return [cleaned] if cleaned else []


def _semantic_review_selector_scalar(raw: str) -> str:
    value = raw.strip().strip(",").strip().strip("`\"'")
    return "" if value in {"...", "[]"} else value


def _add_semantic_review_selector_aliases(selectors: set[str], value: str) -> None:
    selectors.add(value)
    if value.startswith("scene:"):
        selectors.add("scene" + value.split(":", 1)[1])
    elif value.startswith("scene") and value[5:].isdigit():
        selectors.add("scene:" + value[5:])


def _semantic_collection_excerpt(collection_text: str, review_report: str, *, max_chars: int = 14000) -> str:
    failed_selectors = _semantic_review_failed_selectors(review_report)
    if not failed_selectors:
        return collection_text[:max_chars]

    selected_sections: list[str] = []
    chunks = collection_text.split("\n## ")
    preamble = chunks[0].strip()
    for chunk in chunks[1:]:
        heading = chunk.splitlines()[0].strip().strip("`")
        if heading in failed_selectors:
            selected_sections.append("## " + chunk.strip())

    if not selected_sections:
        return collection_text[:max_chars]

    excerpt = "\n\n".join(section[:5000] for section in selected_sections)
    if preamble:
        excerpt = preamble + "\n\n" + excerpt
    return excerpt[:max_chars]


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
    collection_text = collection_path.read_text(encoding="utf-8", errors="replace") if collection_path.exists() else "(missing collection)"
    failed_selectors = sorted(_semantic_review_failed_selectors(review_report))
    failed_selector_text = "\n".join(f"- `{selector}`" for selector in failed_selectors) or "- `(not parsed; use failed report findings)`"
    collection_excerpt = _semantic_collection_excerpt(collection_text, review_report)
    target = SEMANTIC_REVIEW_PRODUCER_TARGETS.get(stage, {})
    owner = str(target.get("owner") or f"{stage} producer")
    slot = str(target.get("slot") or "")
    focus = str(target.get("focus") or "stage semantic contract")
    artifacts = [str(item) for item in target.get("artifacts", [])] if isinstance(target.get("artifacts"), list) else []
    error_text = "\n".join(f"- {error}" for error in errors) or "- semantic reviewer did not provide a specific error"
    stage_specific_repair = ""
    if stage == "image_prompt":
        stage_specific_repair = """
## Image Prompt Repair Boundary

- Repair `api_prompt_payload.prompt` and, when needed, the paired `shot_design_contract`, `cut_location_frame_plan`, and `cut_visual_delta` for the failed selector.
- Keep `scene_event` as the event canon. Do not change what happened in the story to make an image prompt pass.
- Align the API prompt with the cut's designed visual role: `scene_cut_coverage_plan.cut_assignments`, `scene_film_coverage_plan`, and `scene_shot_mix_plan` are the comparison targets.
- If the failure is film-role alignment, fix the visual implementation fields and API prompt together so `shot_role`, `shot_scale`, location zone, visible subject, object detail, reaction behavior, and handoff path agree.
"""

    prompt = f"""# Semantic QA Producer Repair: {stage}

You are the original production-side agent for `{stage}` in this ToC run.

The contextless semantic review agent rejected the current artifact. Use the review findings as improvement instructions, repair the production artifacts, and leave the process in semantic-QA repair state.

This is a real semantic repair, not a bypass. Do not advance the process slot to the next stage. Do not edit `state.txt`, `run_status.json`, or `p000_index.md`; the orchestrator is the only writer for process state. Do not edit any `logs/review/semantic/*` files except the producer repair report named below. In particular, do not edit the semantic review report, collection, scope, or prompt to fake a pass; the orchestrator will rebuild the pack and call the semantic reviewer again from the production artifacts.

- Run directory: `{run_dir}`
- Current semantic stage: `{stage}`
- Process slot kept in semantic QA: `{slot or "(stage-owned slot)"}`
- Repair round: `{round_number}` of `{max_attempts - 1}`
- Producing owner: `{owner}`
- Repair focus: {focus}
- Primary editable artifacts: {", ".join(artifacts) if artifacts else "(stage-owned artifacts)"}
- Non-editable state/navigation artifacts: `state.txt`, `run_status.json`, `p000_index.md`
- Non-editable review artifacts: `logs/review/semantic/{stage}.collection.md`, `logs/review/semantic/{stage}.scope.json`, `logs/review/semantic/{stage}.prompt.md`, `logs/review/semantic/{stage}.report.md`
- Producer repair report to write: `{relpaths["report"].as_posix()}`

## Reviewer Findings / Gate Errors

{error_text}

## Target Failed Selectors

{failed_selector_text}

## Failed Semantic Review Report

```text
{review_report[:16000]}
```

## Review Scope

- collection: `{review_paths["collection"].as_posix()}`
- scope: `{review_paths["scope"].as_posix()}`
- report: `{review_paths["report"].as_posix()}`

{stage_specific_repair}

## Collection Excerpt

```text
{collection_excerpt}
```

## Required Work

1. Treat every `blocked_entries`, `failed_selectors`, `findings`, and `reason_keys` item in the failed semantic report as a required fix.
2. Repair the production artifact(s) so the reviewed meaning is genuinely correct. If a previous repair only partially fixed the stage, focus on the remaining failed selectors rather than rewriting already-passed entries.
3. Preserve existing structure and paths unless a reviewer finding requires a targeted change.
4. If this stage owns generated media, update prompts/contracts and regenerate the affected media through the repository's canonical tooling when needed.
5. Before writing your report, inspect the edited production artifacts for the rejected meaning and remove contradictory language such as stale withheld/reveal/order/object continuity instructions.
6. Keep the stage visible as semantic-QA repair, not as approved or advanced.
7. Stay narrowly scoped: read only the listed run artifacts and the failed selectors unless a direct dependency is missing. Do not run repo-wide searches, do not print full artifact files to stdout, and do not run commands that can emit thousands of lines.
8. Do not edit passed selectors or unrelated scenes/cuts. For repeated generic wording, never use broad search-and-replace or a patch that can match the same phrase in multiple selectors. Anchor every edit to the failed selector id, scene id, cut id, asset id, or exact artifact section.
9. After editing, inspect the failed selectors and a small sample of neighboring passed selectors to ensure the repair did not move later-stage meaning into earlier scenes, change reveal order, or mutate unrelated semantic contracts.
10. Write `{relpaths["report"].as_posix()}` immediately after the targeted repair with:
   - `status: done`
   - changed artifacts
   - reviewer findings addressed
   - remaining risks, if any
   Do not include `state.txt`, `run_status.json`, `p000_index.md`, `logs/review/semantic/{stage}.collection.md`, `.scope.json`, `.prompt.md`, or `.report.md` as changed artifacts.

The next action after your repair will be a fresh contextless semantic review. Passing requires the reviewer report to say `status: passed`.
"""
    prompt_path.write_text(prompt + "\n", encoding="utf-8")
    report_path.write_text(
        f"# Semantic Producer Repair Report: {stage}\n\nstatus: pending\nround: {round_number}\ncreated_at: {now_iso()}\n\n",
        encoding="utf-8",
    )
    return {"prompt": prompt_path, "report": report_path}
