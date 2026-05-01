#!/usr/bin/env python3
"""Migrate existing runs to the audio-first p-slot contract."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import StageGroundingError, detect_flow, run_stage_grounding  # noqa: E402
from toc.harness import append_state_snapshot, parse_state_file, sync_run_status  # noqa: E402


SLOT_REMAP = {
    "p510": "p610",
    "p520": "p620",
    "p530": "p630",
    "p540": "p640",
    "p550": "p650",
    "p560": "p660",
    "p570": "p670",
    "p580": "p680",
    "p610": "p710",
    "p620": "p720",
    "p630": "p730",
    "p640": "p740",
    "p650": "p750",
    "p660": "p760",
    "p670": "p770",
    "p710": "p810",
    "p720": "p820",
    "p730": "p830",
    "p740": "p840",
    "p750": "p850",
    "p810": "p520",
    "p820": "p530",
    "p830": "p540",
    "p840": "p550",
    "p850": "p560",
    "p860": "p570",
}

STATE_PREFIX_REMAP = {
    "stage.image_prompt.grounding.": "stage.scene_implementation.grounding.",
    "stage.image_prompt.readset.": "stage.scene_implementation.readset.",
    "stage.image_prompt.audit.": "stage.scene_implementation.audit.",
    "stage.image_prompt.subagent.": "stage.scene_implementation.subagent.",
    "stage.image_prompt.playbooks.": "stage.scene_implementation.playbooks.",
    "artifact.grounding.image_prompt": "artifact.grounding.scene_implementation",
    "artifact.grounding.playbooks.image_prompt": "artifact.grounding.playbooks.scene_implementation",
}

GROUNDING_FILE_REMAP = {
    "image_prompt.json": "scene_implementation.json",
    "image_prompt.readset.json": "scene_implementation.readset.json",
    "image_prompt.audit.json": "scene_implementation.audit.json",
    "image_prompt.playbooks.json": "scene_implementation.playbooks.json",
    "image_prompt.subagent_prompt.md": "scene_implementation.subagent_prompt.md",
}


def _iter_target_runs(run_dir: Path | None, output_root: Path) -> list[Path]:
    if run_dir is not None:
        return [run_dir.resolve()]
    found = {state_path.parent.resolve() for state_path in output_root.rglob("state.txt")}
    return sorted(found, key=lambda path: (len(path.parts), str(path)))


def _ensure_manifest_phase(manifest_path: Path) -> bool:
    if not manifest_path.exists():
        return False
    text = manifest_path.read_text(encoding="utf-8")
    if "manifest_phase:" in text:
        return False
    updated = text.replace("```yaml\n", "```yaml\nmanifest_phase: production\n", 1)
    manifest_path.write_text(updated, encoding="utf-8")
    return True


def _rename_grounding_files(run_dir: Path) -> bool:
    changed = False
    grounding_dir = run_dir / "logs" / "grounding"
    if not grounding_dir.exists():
        return False
    for old_name, new_name in GROUNDING_FILE_REMAP.items():
        old_path = grounding_dir / old_name
        new_path = grounding_dir / new_name
        if not old_path.exists():
            continue
        new_path.parent.mkdir(parents=True, exist_ok=True)
        if new_path.exists():
            continue
        old_path.replace(new_path)
        changed = True
    return changed


def _migrate_state_keys(state: dict[str, str], run_dir: Path) -> dict[str, str]:
    updates: dict[str, str] = {}
    for key, value in state.items():
        for old_slot, new_slot in SLOT_REMAP.items():
            prefix = f"slot.{old_slot}."
            if key.startswith(prefix):
                new_key = f"slot.{new_slot}.{key.removeprefix(prefix)}"
                if new_key not in state and new_key not in updates:
                    updates[new_key] = value
        for old_prefix, new_prefix in STATE_PREFIX_REMAP.items():
            if key.startswith(old_prefix):
                suffix = key.removeprefix(old_prefix)
                new_value = value.replace("image_prompt", "scene_implementation")
                new_key = f"{new_prefix}{suffix}"
                if new_key not in state and new_key not in updates:
                    updates[new_key] = new_value
    manifest_path = run_dir / "video_manifest.md"
    if manifest_path.exists():
        updates.setdefault("slot.p450.status", "done")
        updates.setdefault("slot.p450.requirement", "required")
        updates.setdefault("artifact.video_manifest", str(manifest_path.resolve()))
    return updates


def _refresh_grounding(run_dir: Path) -> None:
    flow = detect_flow(run_dir)
    candidate_stages = ["narration", "asset", "scene_implementation", "video_generation"]
    for stage in candidate_stages:
        try:
            run_stage_grounding(run_dir, stage, flow=flow, retries=0, mark_stage_failure=False)
        except StageGroundingError:
            continue


def migrate_run(run_dir: Path, *, refresh_grounding: bool) -> dict[str, bool]:
    manifest_changed = _ensure_manifest_phase(run_dir / "video_manifest.md")
    renamed = _rename_grounding_files(run_dir)
    state = parse_state_file(run_dir / "state.txt")
    updates = _migrate_state_keys(state, run_dir)
    if manifest_changed:
        updates["migration.audio_first.manifest_phase"] = "production"
    if renamed:
        updates["migration.audio_first.grounding_files_renamed"] = "true"
    if updates:
        append_state_snapshot(run_dir / "state.txt", updates)
    else:
        sync_run_status(run_dir)
    if refresh_grounding:
        _refresh_grounding(run_dir)
    sync_run_status(run_dir)
    return {
        "manifest_changed": manifest_changed,
        "renamed_grounding": renamed,
        "state_updated": bool(updates),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate runs to the audio-first p-slot contract.")
    parser.add_argument("--run-dir", default=None, help="Single run directory to migrate.")
    parser.add_argument("--output-root", default="output", help="Output root to scan when --run-dir is omitted.")
    parser.add_argument("--refresh-grounding", action="store_true", help="Regenerate narration/asset/scene/video grounding after migration.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve() if args.run_dir else None
    output_root = Path(args.output_root).resolve()
    targets = _iter_target_runs(run_dir, output_root)
    if not targets:
        raise SystemExit("No run directories found to migrate.")

    for target in targets:
        result = migrate_run(target, refresh_grounding=args.refresh_grounding)
        print(
            f"[migrated] {target} "
            f"manifest_phase={'yes' if result['manifest_changed'] else 'no'} "
            f"grounding_renamed={'yes' if result['renamed_grounding'] else 'no'} "
            f"state_updated={'yes' if result['state_updated'] else 'no'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
