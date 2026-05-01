#!/usr/bin/env python3
"""Build a pasteable prompt for a contextless subagent audit."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import (  # noqa: E402
    canonical_stage_name,
    detect_flow,
    grounding_audit_relpath,
    grounding_readset_relpath,
    grounding_report_relpath,
    load_grounding_contract,
)
from toc.harness import append_state_snapshot, now_iso  # noqa: E402


def subagent_prompt_relpath(stage: str) -> Path:
    return Path("logs") / "grounding" / f"{stage}.subagent_prompt.md"


def subagent_prompt_path(run_dir: Path, stage: str) -> Path:
    return run_dir / subagent_prompt_relpath(stage)


def write_subagent_audit_prompt(*, run_dir: Path, stage: str, prompt: str) -> Path:
    path = subagent_prompt_path(run_dir, stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{prompt}\n", encoding="utf-8")
    return path


def build_subagent_audit_prompt(*, stage: str, run_dir: Path, flow: str | None = None) -> str:
    contract = load_grounding_contract()
    canonical_stage = canonical_stage_name(stage, contract)
    resolved_run_dir = run_dir.resolve()
    resolved_flow = flow or detect_flow(resolved_run_dir)

    report_path = resolved_run_dir / grounding_report_relpath(canonical_stage)
    readset_path = resolved_run_dir / grounding_readset_relpath(canonical_stage)
    audit_path = resolved_run_dir / grounding_audit_relpath(canonical_stage)
    state_path = resolved_run_dir / "state.txt"

    lines = [
        "You are a contextless, audit-only verification subagent.",
        "",
        f"Audit the completed ToC stage `{canonical_stage}` in run dir `{resolved_run_dir}`.",
        f"Flow: `{resolved_flow}`.",
        "",
        "Do not generate content and do not edit story, script, manifest, or other content artifacts.",
        "You may refresh grounding audit artifacts by rerunning the helper command below.",
        "Do not rely on parent conversation context.",
        "",
        "If the helper command exits nonzero or any expected artifact is missing, report the missing items and stop; do not repair anything.",
        "",
        "First run this command:",
        f"`python scripts/audit-stage-grounding.py --stage {canonical_stage} --run-dir {resolved_run_dir}`",
        "",
        "Then inspect these artifacts directly:",
        f"- `{report_path}`",
        f"- `{readset_path}`",
        f"- `{audit_path}`",
        f"- `{state_path}`",
        "",
        "Use those files to verify:",
        "- the grounding report is `ready`",
        "- the readset is marked `verified_before_edit: true`",
        "- the readset covers the required global docs, stage docs, templates, and inputs",
        "- the audit report is `passed`",
        "",
        "Return only a compact structured result with these keys:",
        "status: passed|failed",
        "missing_artifacts: [...]",
        "missing_reads: [...]",
        "notes: [...]",
    ]
    return dedent("\n".join(lines)).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a pasteable contextless subagent audit prompt.")
    parser.add_argument("--stage", required=True, help="Stage name (research, story, script, narration, asset, scene_implementation, video_generation).")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp> or a scene run directory.")
    parser.add_argument("--flow", choices=["toc-run", "scene-series", "immersive"], default=None)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        raise SystemExit(f"Run directory not found: {run_dir}")

    contract = load_grounding_contract()
    canonical_stage = canonical_stage_name(args.stage, contract)
    prompt = build_subagent_audit_prompt(stage=canonical_stage, run_dir=run_dir, flow=args.flow)
    prompt_path = write_subagent_audit_prompt(run_dir=run_dir.resolve(), stage=canonical_stage, prompt=prompt)
    append_state_snapshot(
        run_dir.resolve() / "state.txt",
        {
            f"stage.{canonical_stage}.subagent.prompt": str(prompt_path.relative_to(run_dir.resolve())),
            f"stage.{canonical_stage}.subagent.prompt.generated_at": now_iso(),
        },
    )
    print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
