#!/usr/bin/env python3
"""Validate p720 narration shape before audio generation.

The historical p720 entrypoint ran a critic loop and materialized review
reports. It remains as a compatibility command for older callers, but now
performs only deterministic authoring checks and records ordinary runtime
progress.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, load_structured_document, now_iso
from toc.runtime_locks import sync_file_lock


STAGE = "narration"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _narration_nodes(manifest: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    nodes: list[tuple[str, dict[str, Any]]] = []
    for scene in _list(manifest.get("scenes")):
        if not isinstance(scene, dict):
            continue
        scene_id = str(scene.get("scene_id") or "").strip()
        if not scene_id:
            continue
        cuts = scene.get("cuts") if isinstance(scene.get("cuts"), list) else []
        raw_nodes = cuts or [scene]
        for index, node in enumerate(raw_nodes, start=1):
            if not isinstance(node, dict):
                continue
            cut_id = str(node.get("cut_id") or "").strip()
            selector = f"scene{scene_id}_cut{cut_id}" if cut_id else f"scene{scene_id}"
            narration = _dict(_dict(node.get("audio")).get("narration"))
            if not narration:
                narration = _dict(node.get("narration"))
            nodes.append((selector or f"scene{scene_id}_node{index}", narration))
    return nodes


def validate_narration_contract(manifest: dict[str, Any]) -> list[str]:
    """Return malformed narration fields without semantic judgment."""

    issues: list[str] = []
    for selector, narration in _narration_nodes(manifest):
        tool = str(narration.get("tool") or "elevenlabs").strip().lower()
        if tool == "silent":
            continue
        if not str(narration.get("text") or "").strip():
            issues.append(f"{selector}: narration.text is required")
        if not str(narration.get("tts_text") or narration.get("text") or "").strip():
            issues.append(f"{selector}: narration.tts_text is required")
    return issues


def _run_p720_l3_unlocked(
    *,
    run_dir: Path,
    manifest_path: Path,
    script_path: Path,
    round_number: int = 1,
) -> str:
    del script_path, round_number  # retained for compatibility with old callers
    _text, manifest = load_structured_document(manifest_path)
    if not isinstance(manifest, dict):
        raise RuntimeError(f"manifest has no structured YAML: {manifest_path}")
    issues = validate_narration_contract(manifest)
    status = "failed" if issues else "passed"
    updates = {
        "runtime.stage": "narration_contract_validation",
        "runtime.narration.phase": "authoring",
        "slot.p720.status": "done" if not issues else "blocked",
        "slot.p720.note": (
            "narration shape and TTS fields are valid"
            if not issues
            else "; ".join(issues)
        ),
        "stage.narration.status": "ready" if not issues else "blocked",
        "runtime.duration_fit.at": now_iso(),
    }
    if issues:
        updates["last_error"] = "; ".join(issues)
    append_state_snapshot(run_dir / "state.txt", updates)
    return status


def run_p720_l3(
    *,
    run_dir: Path,
    manifest_path: Path,
    script_path: Path,
    round_number: int,
) -> str:
    with sync_file_lock(run_dir.resolve() / ".locks" / "run_artifacts.lock"):
        return _run_p720_l3_unlocked(
            run_dir=run_dir,
            manifest_path=manifest_path,
            script_path=script_path,
            round_number=round_number,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", default=None)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--script", default=None)
    parser.add_argument("--round", type=int, default=1, dest="round_number")
    # Kept for old automation; deterministic validation itself always reports
    # its status and never creates a review artifact.
    parser.add_argument("--fail-on-findings", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest).resolve() if args.manifest else None
    run_dir = Path(args.run_dir).resolve() if args.run_dir else (manifest_path.parent if manifest_path else None)
    if run_dir is None:
        raise SystemExit("one of --run-dir or --manifest is required")
    manifest_path = manifest_path or run_dir / "video_manifest.md"
    script_path = Path(args.script).resolve() if args.script else run_dir / "script.md"
    if not run_dir.is_dir():
        raise SystemExit(f"Run directory not found: {run_dir}")
    if not manifest_path.is_file():
        raise SystemExit(f"Manifest not found: {manifest_path}")
    if not script_path.is_file():
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
    print(f"p720 narration contract validation: {status}")
    return 1 if args.fail_on_findings and status != "passed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
