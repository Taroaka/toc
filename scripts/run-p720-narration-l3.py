#!/usr/bin/env python3
"""Run the p720 narration L3 review loop and write gate artifacts."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, now_iso
from toc.review_loop import (
    REVIEW_LOOP_CRITIC_COUNT,
    aggregated_review_relpath,
    critic_relpath,
    final_review_relpath,
    loop_state_updates,
)
from toc.review_loop_runner import materialize_review_loop_round


STAGE = "narration"
CANONICAL_FINDING_CODES = {
    "ai_thin_abstract_wording",
    "missing_pause_punctuation",
    "narration_contains_meta_marker",
    "narration_contract_missing",
    "narration_contract_must_avoid_violated",
    "narration_contract_must_cover_unmet",
    "narration_contract_target_function_unmet",
    "narration_empty",
    "narration_pacing_mismatch",
    "narration_spoken_japanese_weak",
    "narration_story_role_mismatch",
    "narration_too_visual_redundant",
    "narration_tts_text_missing",
    "needs_text_normalization",
    "sentence_too_long_for_tts",
    "tts_unfriendly_literal",
    "visual_direction_leaked_into_narration",
}


@dataclass(frozen=True)
class Finding:
    selector: str
    code: str
    message: str
    human_review_ok: bool = False


@dataclass(frozen=True)
class CriticProfile:
    title: str
    focus: tuple[str, ...]


CRITIC_PROFILES: tuple[CriticProfile, ...] = (
    CriticProfile(
        title="TTS readiness and pronunciation payload",
        focus=(
            "narration_empty",
            "narration_tts_text_missing",
            "tts_unfriendly_literal",
            "needs_text_normalization",
            "missing_pause_punctuation",
        ),
    ),
    CriticProfile(
        title="Narration contract and story role",
        focus=(
            "narration_contract_missing",
            "narration_contract_must_cover_unmet",
            "narration_contract_must_avoid_violated",
            "narration_contract_target_function_unmet",
            "narration_story_role_mismatch",
        ),
    ),
    CriticProfile(
        title="Visual redundancy and leakage",
        focus=(
            "visual_direction_leaked_into_narration",
            "narration_too_visual_redundant",
        ),
    ),
    CriticProfile(
        title="Pacing and spoken timing",
        focus=(
            "sentence_too_long_for_tts",
            "missing_pause_punctuation",
            "narration_pacing_mismatch",
        ),
    ),
    CriticProfile(
        title="Spoken Japanese and thin wording",
        focus=(
            "ai_thin_abstract_wording",
            "narration_spoken_japanese_weak",
        ),
    ),
)


def _relative(run_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(run_dir.resolve()).as_posix()
    except ValueError:
        return str(path)


def _parse_int_bullet(text: str, key: str) -> int:
    pattern = rf"^- {re.escape(key)}: `?(\d+)`?"
    for line in text.splitlines():
        match = re.match(pattern, line.strip())
        if match:
            return int(match.group(1))
    return 0


def _parse_status(text: str) -> str:
    for line in text.splitlines():
        match = re.match(r"^- status: `?([A-Z]+|passed|changes_requested)`?", line.strip())
        if match:
            return match.group(1).lower()
    return "fail"


def _parse_findings(text: str) -> list[Finding]:
    findings: list[Finding] = []
    selector = "(run)"
    human_review_ok = False
    for raw in text.splitlines():
        line = raw.strip()
        heading = re.match(r"^##\s+(.+)$", line)
        if heading:
            selector = heading.group(1).strip()
            human_review_ok = False
            continue
        human_match = re.match(r"^- human_review_ok:\s+`?(true|false)`?", line)
        if human_match:
            human_review_ok = human_match.group(1) == "true"
            continue
        match = re.match(r"^- ([a-z0-9_]+):\s+(.+)$", line)
        if match and selector != "(run)" and match.group(1) in CANONICAL_FINDING_CODES:
            findings.append(
                Finding(
                    selector=selector,
                    code=match.group(1),
                    message=match.group(2).strip(),
                    human_review_ok=human_review_ok,
                )
            )
    return findings


def _root_cause_for(finding: Finding) -> str:
    if finding.code in {"missing_pause_punctuation", "sentence_too_long_for_tts", "narration_pacing_mismatch"}:
        return "The narration line does not expose enough spoken breakpoints for stable TTS pacing."
    if finding.code.startswith("narration_contract"):
        return "The narration text is not anchored tightly enough to its audio.narration.contract."
    if finding.code in {"needs_text_normalization", "tts_unfriendly_literal", "narration_tts_text_missing"}:
        return "The final ElevenLabs payload is not fully normalized for speech."
    if finding.code in {"visual_direction_leaked_into_narration", "narration_too_visual_redundant"}:
        return "The narration is carrying visual prompt work instead of voiceover meaning."
    if finding.code == "ai_thin_abstract_wording":
        return "The wording leans on repeated abstract process terms instead of concrete people, actions, places, or objects."
    if finding.code == "narration_spoken_japanese_weak":
        return "The line does not yet read like natural spoken Japanese."
    return "The narration node violates the p720 TTS readiness contract."


def _fix_direction_for(finding: Finding) -> str:
    if finding.code == "ai_thin_abstract_wording":
        return "Replace repeated abstract process words, or follow each needed abstract term with a concrete person, action, place, or object."
    if finding.code in {"missing_pause_punctuation", "sentence_too_long_for_tts"}:
        return "Split the line and add Japanese punctuation at semantic breathing points."
    if finding.code.startswith("narration_contract"):
        return "Patch audio.narration.text and tts_text so the contract target_function, must_cover, and must_avoid fields are satisfied."
    if finding.code in {"needs_text_normalization", "tts_unfriendly_literal", "narration_tts_text_missing"}:
        return "Rewrite tts_text as the exact ElevenLabs payload with speech-friendly readings and no raw literals."
    if finding.code in {"visual_direction_leaked_into_narration", "narration_too_visual_redundant"}:
        return "Move camera or visual description back to visual prompts and leave narration to causal, emotional, or meaning-layer information."
    return "Patch the narration node, then rerun p720 before p730 TTS generation."


def _render_critic_report(
    *,
    index: int,
    profile: CriticProfile,
    findings: list[Finding],
    accepted_findings: list[Finding],
    deterministic_report: Path,
    run_dir: Path,
) -> str:
    status = "changes_requested" if findings else "passed"
    lines = [
        f"# L3 Narration Critic {index}: {profile.title}",
        "",
        f"- status: {status}",
        f"- deterministic_gate_report: `{_relative(run_dir, deterministic_report)}`",
        f"- focus_codes: `{', '.join(profile.focus)}`",
        "",
        "## Blocking Findings",
        "",
    ]
    if not findings:
        lines.append("- []")
    for item_no, finding in enumerate(findings, start=1):
        lines.extend(
            [
                f"- id: `{finding.selector}.{finding.code}.{item_no}`",
                "  severity: blocker",
                f"  evidence: `{finding.selector}` raised `{finding.code}`: {finding.message}",
                f"  root_cause: {_root_cause_for(finding)}",
                "  downstream_impact: p730 must not send this line to ElevenLabs until p720 is clean.",
                f"  fix_direction: {_fix_direction_for(finding)}",
                "  acceptance_condition: rerun p720 and this finding no longer appears in the deterministic gate report.",
            ]
        )
    lines.extend(["", "## Human-Accepted Findings", ""])
    if not accepted_findings:
        lines.append("- []")
    for finding in accepted_findings:
        lines.append(f"- `{finding.selector}` `{finding.code}`: {finding.message}")
    lines.extend(
        [
            "",
            "## Recommended Changes",
            "",
            "- Keep audio.narration.text and audio.narration.tts_text aligned unless the tts_text divergence is explicitly for pronunciation or delivery.",
            "",
            "## Rejected Suggestions",
            "",
            "- []",
            "",
            "## Generator Patch Brief",
            "",
        ]
    )
    if not findings:
        lines.append("- No blocking patch needed for this critic focus.")
    for finding in findings:
        lines.append(f"- `{finding.selector}`: {_fix_direction_for(finding)}")
    lines.extend(["", "## Round Summary", "", f"{profile.title} completed with status `{status}`."])
    return "\n".join(lines).rstrip() + "\n"


def _render_aggregate_report(
    *,
    critic_reports: list[str],
    blocking_findings: list[Finding],
    accepted_findings: list[Finding],
    status: str,
    round_number: int,
    deterministic_report: Path,
    run_dir: Path,
) -> str:
    lines = [
        "# Narration Text Eval/Improve Loop",
        "",
        f"- status: {status}",
        f"- round: {round_number}/5",
        f"- critic_count: {REVIEW_LOOP_CRITIC_COUNT}",
        f"- deterministic_gate_report: `{_relative(run_dir, deterministic_report)}`",
        "",
        "## Blocking Findings",
        "",
    ]
    if not blocking_findings:
        lines.append("- []")
    for item_no, finding in enumerate(blocking_findings, start=1):
        lines.extend(
            [
                f"- id: `{finding.selector}.{finding.code}.{item_no}`",
                "  severity: blocker",
                f"  evidence: `{finding.selector}` raised `{finding.code}`: {finding.message}",
                f"  root_cause: {_root_cause_for(finding)}",
                "  downstream_impact: p730 TTS generation is blocked until this narration node passes p720.",
                f"  adopted_fix_plan: {_fix_direction_for(finding)}",
                "  acceptance_condition: rerun p720 and the deterministic gate reports no unresolved entry for this selector.",
            ]
        )
    lines.extend(["", "## Human-Accepted Findings", ""])
    if not accepted_findings:
        lines.append("- []")
    for finding in accepted_findings:
        lines.append(
            f"- `{finding.selector}` raised `{finding.code}` but is already marked `human_review_ok: true`: {finding.message}"
        )
    lines.extend(
        [
            "",
            "## Recommended Changes",
            "",
            "- Use v-dict or ElevenLabs pronunciation dictionary locators for names or terms that are likely to be misread.",
            "- Keep punctuation in tts_text where the intended voice needs a pause.",
            "",
            "## Rejected Suggestions",
            "",
            "- []",
            "",
            "## Generator Patch Brief",
            "",
        ]
    )
    if not blocking_findings:
        lines.append("- No patch needed. p720 may advance to p730.")
    for finding in blocking_findings:
        lines.append(f"- `{finding.selector}`: {_fix_direction_for(finding)}")
    lines.extend(
        [
            "",
            "## Round Summary",
            "",
            f"p720 automatic L3 review finished with status `{status}`.",
        ]
    )
    for idx, report in enumerate(critic_reports, start=1):
        lines.extend(["", f"## Critic {idx} Input", "", report.strip()])
    return "\n".join(lines).rstrip() + "\n"


def run_p720_l3(
    *,
    run_dir: Path,
    manifest_path: Path,
    script_path: Path,
    round_number: int,
) -> str:
    run_dir = run_dir.resolve()
    manifest_path = manifest_path.resolve()
    script_path = script_path.resolve()
    materialize_review_loop_round(run_dir=run_dir, stage=STAGE, round_number=round_number)

    round_dir = run_dir / aggregated_review_relpath(STAGE, round_number).parent
    deterministic_report = round_dir / "deterministic_gate_report.md"
    review_cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "review-narration-text-quality.py"),
        "--manifest",
        str(manifest_path),
        "--script",
        str(script_path),
        "--out",
        str(deterministic_report),
    ]
    result = subprocess.run(review_cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or "deterministic narration review failed"
        updates = loop_state_updates(stage=STAGE, status="failed", current_round=round_number)
        updates.update(
            {
                f"eval.{STAGE}.loop.round_{round_number:02d}.failed_at": now_iso(),
                f"eval.{STAGE}.loop.round_{round_number:02d}.error": error,
                "slot.p720.status": "blocked",
                "slot.p720.review_loop.status": "failed",
                "slot.p720.review_loop.current_round": str(round_number),
                "review.narration.status": "changes_requested",
                "review.narration.note": error,
            }
        )
        append_state_snapshot(run_dir / "state.txt", updates)
        raise RuntimeError(error)

    report_text = deterministic_report.read_text(encoding="utf-8")
    unresolved_entries = _parse_int_bullet(report_text, "unresolved_entries")
    findings = _parse_findings(report_text)
    blocking_findings = [finding for finding in findings if not finding.human_review_ok]
    accepted_findings = [finding for finding in findings if finding.human_review_ok]
    status = "changes_requested" if unresolved_entries else "passed"

    unmatched = list(blocking_findings)
    critic_reports: list[str] = []
    for idx, profile in enumerate(CRITIC_PROFILES, start=1):
        focused = [finding for finding in blocking_findings if finding.code in profile.focus]
        accepted_focused = [finding for finding in accepted_findings if finding.code in profile.focus]
        if idx == 1:
            focused.extend(finding for finding in blocking_findings if all(finding.code not in p.focus for p in CRITIC_PROFILES))
            accepted_focused.extend(
                finding for finding in accepted_findings if all(finding.code not in p.focus for p in CRITIC_PROFILES)
            )
        for finding in focused:
            if finding in unmatched:
                unmatched.remove(finding)
        critic_report = _render_critic_report(
            index=idx,
            profile=profile,
            findings=focused,
            accepted_findings=accepted_focused,
            deterministic_report=deterministic_report,
            run_dir=run_dir,
        )
        critic_reports.append(critic_report)
        (run_dir / critic_relpath(STAGE, round_number, idx)).write_text(critic_report, encoding="utf-8")

    if unmatched:
        fallback = (run_dir / critic_relpath(STAGE, round_number, 1)).read_text(encoding="utf-8")
        fallback += "\n## Additional Unclassified Findings\n\n"
        for finding in unmatched:
            fallback += f"- `{finding.selector}` `{finding.code}`: {finding.message}\n"
        (run_dir / critic_relpath(STAGE, round_number, 1)).write_text(fallback, encoding="utf-8")
        critic_reports[0] = fallback

    aggregate_report = _render_aggregate_report(
        critic_reports=critic_reports,
        blocking_findings=blocking_findings,
        accepted_findings=accepted_findings,
        status=status,
        round_number=round_number,
        deterministic_report=deterministic_report,
        run_dir=run_dir,
    )
    aggregate_path = run_dir / aggregated_review_relpath(STAGE, round_number)
    aggregate_path.write_text(aggregate_report, encoding="utf-8")
    final_path = run_dir / final_review_relpath(STAGE)
    final_path.write_text(aggregate_report, encoding="utf-8")

    updates = loop_state_updates(stage=STAGE, status=status, current_round=round_number)
    updates.update(
        {
            f"eval.{STAGE}.loop.round_{round_number:02d}.completed_at": now_iso(),
            f"eval.{STAGE}.loop.round_{round_number:02d}.aggregated_review": str(
                aggregated_review_relpath(STAGE, round_number)
            ),
            f"eval.{STAGE}.loop.round_{round_number:02d}.deterministic_gate_report": _relative(run_dir, deterministic_report),
            "slot.p720.status": "done" if status == "passed" else "blocked",
            "slot.p720.review_loop.status": status,
            "slot.p720.review_loop.current_round": str(round_number),
            "review.narration.status": "approved" if status == "passed" else "changes_requested",
            "review.narration.report": str(final_review_relpath(STAGE)),
        }
    )
    append_state_snapshot(run_dir / "state.txt", updates)
    return status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run automatic p720 narration L3 review before p730 TTS.")
    parser.add_argument("--run-dir", default=None, help="Path to output/<topic>_<timestamp>")
    parser.add_argument("--manifest", default=None, help="Path to video_manifest.md. Defaults to <run-dir>/video_manifest.md.")
    parser.add_argument("--script", default=None, help="Path to script.md. Defaults to <run-dir>/script.md.")
    parser.add_argument("--round", type=int, default=1, dest="round_number", help="Review round number, 1-5.")
    parser.add_argument("--fail-on-findings", action="store_true", help="Exit non-zero if p720 status is changes_requested.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).resolve() if args.manifest else None
    run_dir = Path(args.run_dir).resolve() if args.run_dir else (manifest_path.parent if manifest_path else None)
    if run_dir is None:
        raise SystemExit("one of --run-dir or --manifest is required")
    if not run_dir.exists():
        raise SystemExit(f"Run directory not found: {run_dir}")
    manifest_path = manifest_path or run_dir / "video_manifest.md"
    script_path = Path(args.script).resolve() if args.script else run_dir / "script.md"
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")
    if not script_path.exists():
        raise SystemExit(f"Script not found: {script_path}")

    try:
        status = run_p720_l3(
            run_dir=run_dir,
            manifest_path=manifest_path,
            script_path=script_path,
            round_number=args.round_number,
        )
    except Exception as exc:
        raise SystemExit(str(exc)) from exc
    print(f"p720 narration L3 review: {status}")
    if args.fail_on_findings and status != "passed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
