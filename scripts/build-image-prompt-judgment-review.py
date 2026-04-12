#!/usr/bin/env python3
"""Build a deterministic prompt pack for contextless image prompt judgment review."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, now_iso  # noqa: E402


@dataclass(frozen=True)
class ReviewEntry:
    selector: str
    scene_id: int
    cut_id: int
    output: str
    narration: str
    rationale: str
    agent_review_ok: bool
    human_review_ok: bool
    agent_review_reason_keys: list[str]
    agent_review_reason_messages: list[str]
    target_focus: str
    must_include: list[str]
    must_avoid: list[str]
    done_when: list[str]
    overall_score: float
    prompt: str


def extract_yaml_block(text: str) -> str:
    match = re.search(r"```yaml\s*\n(.*?)\n```", text, re.S)
    if not match:
        raise SystemExit("YAML block not found in manifest markdown.")
    return match.group(1)


def load_manifest_yaml(path: Path) -> dict:
    if yaml is None:
        raise SystemExit("PyYAML is required for image prompt judgment review.")
    return yaml.safe_load(extract_yaml_block(path.read_text(encoding="utf-8"))) or {}


def _get_selector(scene_id: int, cut_id: int) -> str:
    return f"scene{scene_id:02d}_cut{cut_id:02d}"


def _review_block(review: dict[str, object] | None) -> dict[str, object]:
    return review if isinstance(review, dict) else {}


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
    return default


def _as_str(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _prompt_text(image_generation: dict[str, object]) -> str:
    return _as_str(image_generation.get("prompt"))


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def collect_review_entries(*, manifest: dict, mode_filter: str = "generate_still") -> list[ReviewEntry]:
    entries: list[ReviewEntry] = []
    for scene in manifest.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        scene_id = scene.get("scene_id")
        if not isinstance(scene_id, int) or scene_id <= 0:
            continue
        for cut in scene.get("cuts", []) or []:
            if not isinstance(cut, dict):
                continue
            cut_id = cut.get("cut_id")
            if not isinstance(cut_id, int) or cut_id <= 0:
                continue
            plan = cut.get("still_image_plan")
            if not isinstance(plan, dict) or _as_str(plan.get("mode")) != mode_filter:
                continue
            image_generation = cut.get("image_generation")
            if not isinstance(image_generation, dict):
                continue
            review = _review_block(image_generation.get("review"))
            contract = _review_block(review.get("contract")) or _review_block(image_generation.get("contract"))
            narration = _review_block(cut.get("audio")).get("narration")
            narration_text = ""
            if isinstance(narration, dict):
                narration_text = _as_str(narration.get("text"))
            entries.append(
                ReviewEntry(
                    selector=_get_selector(scene_id, cut_id),
                    scene_id=scene_id,
                    cut_id=cut_id,
                    output=_as_str(image_generation.get("output")),
                    narration=narration_text,
                    rationale=_as_str(plan.get("rationale")),
                    agent_review_ok=_as_bool(review.get("agent_review_ok"), True),
                    human_review_ok=_as_bool(review.get("human_review_ok"), False),
                    agent_review_reason_keys=_as_str_list(review.get("agent_review_reason_keys") or review.get("agent_review_reason_codes")),
                    agent_review_reason_messages=_as_str_list(review.get("agent_review_reason_messages")),
                    target_focus=_as_str(contract.get("target_focus")),
                    must_include=_as_str_list(contract.get("must_include")),
                    must_avoid=_as_str_list(contract.get("must_avoid")),
                    done_when=_as_str_list(contract.get("done_when")),
                    overall_score=_as_float(review.get("overall_score")),
                    prompt=_prompt_text(image_generation),
                )
            )
    return entries


def render_review_collection(entries: list[ReviewEntry], *, mode_filter: str) -> str:
    lines = [
        "# Image Prompt Judgment Review Collection",
        "",
        f"抽出対象: `still_image_plan.mode == {mode_filter}`",
        "",
        f"件数: `{len(entries)}`",
        "",
    ]
    for entry in entries:
        lines.extend(
            [
                f"## {entry.selector}",
                "",
                f"- output: `{entry.output}`",
                f"- narration: `{entry.narration}`" if entry.narration else "- narration: `(silent)`",
                f"- rationale: `{entry.rationale}`",
                f"- agent_review_ok: `{'true' if entry.agent_review_ok else 'false'}`",
                f"- human_review_ok: `{'true' if entry.human_review_ok else 'false'}`",
                f"- target_focus: `{entry.target_focus}`" if entry.target_focus else "- target_focus: ``",
                f"- must_include: `{', '.join(entry.must_include)}`" if entry.must_include else "- must_include: ``",
                f"- must_avoid: `{', '.join(entry.must_avoid)}`" if entry.must_avoid else "- must_avoid: ``",
                f"- done_when: `{', '.join(entry.done_when)}`" if entry.done_when else "- done_when: ``",
                f"- overall_score: `{entry.overall_score:.3f}`",
                f"- agent_review_reason_keys: `{', '.join(entry.agent_review_reason_keys)}`"
                if entry.agent_review_reason_keys
                else "- agent_review_reason_keys: ``",
                "- agent_review_reason_messages:",
            ]
        )
        if entry.agent_review_reason_messages:
            lines.extend(f"  - `{message}`" for message in entry.agent_review_reason_messages)
        else:
            lines.append("  - ``")
        lines.extend(
            [
                "",
                "```text",
                entry.prompt.rstrip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def render_scope_json(
    *,
    run_dir: Path,
    manifest_path: Path,
    collection_path: Path,
    prompt_path: Path,
    report_path: Path,
    entries: list[ReviewEntry],
    mode_filter: str,
) -> str:
    payload = {
        "run_dir": str(run_dir.resolve()),
        "manifest": str(manifest_path.resolve()),
        "mode_filter": mode_filter,
        "entry_count": len(entries),
        "selectors": [entry.selector for entry in entries],
        "artifacts": {
            "collection": str(collection_path.relative_to(run_dir.resolve())),
            "prompt": str(prompt_path.relative_to(run_dir.resolve())),
            "report": str(report_path.relative_to(run_dir.resolve())),
        },
        "generated_at": now_iso(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def render_judgment_template(*, run_dir: Path, manifest_path: Path, scope_path: Path, collection_path: Path) -> str:
    return dedent(
        f"""
        # Image Prompt Judgment Review

        - run_dir: `{run_dir.resolve()}`
        - manifest: `{manifest_path.resolve()}`
        - scope: `{scope_path}`
        - collection: `{collection_path}`
        - status: `pending`

        ## Reviewed Entries

        - `...`

        ## Blocked Entries

        - `...`

        ## Findings

        - `...`

        ## Notes

        - `...`
        """
    ).strip()


def build_judgment_prompt(
    *,
    run_dir: Path,
    manifest_path: Path,
    scope_path: Path,
    collection_path: Path,
    report_path: Path,
) -> str:
    lines = [
        "You are a contextless, judgment-review subagent for image prompt quality.",
        "",
        f"Review the frozen image prompt collection for run dir `{run_dir.resolve()}`.",
        "",
        "This review is separate from hard function checks.",
        "Do not edit `video_manifest.md`, do not rewrite `image_generation.review`, and do not repair prompt fields.",
        "Judge quality and reviewer readiness only.",
        "",
        "Read these artifacts in order:",
        f"1. `{manifest_path.resolve()}`",
        f"2. `{scope_path}`",
        f"3. `{collection_path}`",
        f"4. `{report_path}`",
        "",
        "Use the frozen review collection as the review target.",
        "For each entry, judge prompt clarity, self-containment, continuity readiness, and production readiness.",
        "If a prompt is weak, explain why; do not patch the manifest.",
        "",
        "Write or return a compact judgment report with these keys:",
        "status: passed|failed",
        "reviewed_entries: [...]",
        "blocked_entries: [...]",
        "findings: [...]",
        "notes: [...]",
    ]
    return dedent("\n".join(lines)).strip()


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic image prompt judgment-review prompt pack.")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp> or a scene run directory.")
    parser.add_argument("--manifest", default=None, help="Path to video_manifest.md (default: <run-dir>/video_manifest.md)")
    parser.add_argument("--mode", default="generate_still", help="still_image_plan.mode filter (default: generate_still)")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    if not run_dir.exists():
        raise SystemExit(f"Run directory not found: {run_dir}")

    manifest_path = Path(args.manifest).resolve() if args.manifest else (run_dir / "video_manifest.md").resolve()
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    manifest = load_manifest_yaml(manifest_path)
    entries = collect_review_entries(manifest=manifest, mode_filter=args.mode)

    review_dir = run_dir / "logs" / "review"
    collection_path = review_dir / "image_prompt.review_collection.md"
    scope_path = review_dir / "image_prompt.review_scope.json"
    prompt_path = review_dir / "image_prompt.judgment_prompt.md"
    report_path = review_dir / "image_prompt.judgment.md"

    write_text(collection_path, render_review_collection(entries, mode_filter=args.mode))
    write_text(scope_path, render_scope_json(
        run_dir=run_dir,
        manifest_path=manifest_path,
        collection_path=collection_path,
        prompt_path=prompt_path,
        report_path=report_path,
        entries=entries,
        mode_filter=args.mode,
    ))
    prompt = build_judgment_prompt(
        run_dir=run_dir,
        manifest_path=manifest_path,
        scope_path=scope_path,
        collection_path=collection_path,
        report_path=report_path,
    )
    write_text(prompt_path, f"{prompt}\n")
    write_text(report_path, render_judgment_template(
        run_dir=run_dir,
        manifest_path=manifest_path,
        scope_path=scope_path,
        collection_path=collection_path,
    ) + "\n")
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "review.image_prompt.judgment.collection": str(collection_path.relative_to(run_dir)),
            "review.image_prompt.judgment.scope": str(scope_path.relative_to(run_dir)),
            "review.image_prompt.judgment.prompt": str(prompt_path.relative_to(run_dir)),
            "review.image_prompt.judgment.report": str(report_path.relative_to(run_dir)),
            "review.image_prompt.judgment.status": "pending",
            "review.image_prompt.judgment.generated_at": now_iso(),
            "review.image_prompt.judgment.entry_count": str(len(entries)),
        },
    )
    print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
