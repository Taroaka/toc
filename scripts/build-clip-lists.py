#!/usr/bin/env python3
"""
Build ffmpeg concat lists from a video manifest.

Outputs:
- <base>_clips.txt
- <base>_narration_list.txt
- <base>_generation_exclusions.md
"""
from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    yaml = None


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.run_index import write_run_index
from toc.immersive_manifest import make_scene_cut_selector, normalize_dotted_id


def extract_yaml_block(text: str) -> str:
    match = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not match:
        raise SystemExit("No ```yaml ... ``` block found in manifest markdown.")
    return match.group(1)


def _normalize_status(value: object) -> str:
    return str(value or "").strip().lower()


def _selector(scene_id: object, cut_id: object | None = None) -> str:
    if cut_id in {None, ""}:
        return f"scene{scene_id}"
    return f"scene{scene_id}_cut{cut_id}"


def _render_unit_selector(scene_id: object, unit_id: object | None = None) -> str:
    return f"scene{scene_id}_unit{unit_id}"


def _non_deleted_cut_lookup(raw_cuts: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    lookup: dict[str, dict[str, object]] = {}
    for raw_cut in raw_cuts:
        cut_id = normalize_dotted_id(raw_cut.get("cut_id"))
        if cut_id is None:
            continue
        if _normalize_status(raw_cut.get("cut_status")) == "deleted":
            continue
        lookup[cut_id] = raw_cut
    return lookup


def _append_render_unit_outputs(
    *,
    scene_id: str,
    raw_scene: dict[str, object],
    raw_cuts: list[dict[str, object]],
    clips: list[str],
    narrations: list[str],
) -> None:
    render_units = raw_scene.get("render_units")
    if not isinstance(render_units, list) or not render_units:
        return

    non_deleted_cut_lookup = _non_deleted_cut_lookup(raw_cuts)
    ownership: dict[str, str] = {}
    missing: list[str] = []
    duplicate: list[str] = []

    for raw_unit in render_units:
        if not isinstance(raw_unit, dict):
            raise SystemExit(f"scene{scene_id}: render_units[] must be mappings.")
        unit_id = normalize_dotted_id(raw_unit.get("unit_id"))
        if unit_id is None:
            raise SystemExit(f"scene{scene_id}: render_units[].unit_id is required.")
        selector = _render_unit_selector(scene_id, unit_id)
        source_cut_ids_raw = raw_unit.get("source_cut_ids")
        if not isinstance(source_cut_ids_raw, list) or not source_cut_ids_raw:
            raise SystemExit(f"{selector}: source_cut_ids must be a non-empty list.")

        source_cut_ids: list[str] = []
        seen_within_unit: set[str] = set()
        for raw_cut_id in source_cut_ids_raw:
            cut_id = normalize_dotted_id(raw_cut_id)
            if cut_id is None:
                raise SystemExit(f"{selector}: invalid source_cut_id: {raw_cut_id!r}")
            if cut_id in seen_within_unit:
                raise SystemExit(f"{selector}: duplicate source_cut_id within render unit: {cut_id}")
            seen_within_unit.add(cut_id)
            source_cut_ids.append(cut_id)

        video_generation = raw_unit.get("video_generation")
        if not isinstance(video_generation, dict):
            raise SystemExit(f"{selector}: video_generation is required.")
        video_output = str(video_generation.get("output") or "").strip()
        if video_output:
            clips.append(video_output)

        for cut_id in source_cut_ids:
            raw_cut = non_deleted_cut_lookup.get(cut_id)
            if raw_cut is None:
                missing.append(cut_id)
                continue
            previous_owner = ownership.get(cut_id)
            if previous_owner is not None:
                duplicate.append(f"{cut_id} -> {previous_owner}, {selector}")
                continue
            ownership[cut_id] = selector
            audio = raw_cut.get("audio") if isinstance(raw_cut.get("audio"), dict) else {}
            narration = audio.get("narration") if isinstance(audio.get("narration"), dict) else {}
            narration_output = narration.get("output")
            if isinstance(narration_output, str) and narration_output.strip():
                narrations.append(narration_output.strip())

    if missing:
        raise SystemExit(f"scene{scene_id}: render_units reference non-deleted cuts that do not exist: {sorted(set(missing))}")
    if duplicate:
        raise SystemExit(f"scene{scene_id}: cuts assigned to multiple render_units: {duplicate}")
    missing_coverage = sorted(set(non_deleted_cut_lookup.keys()) - set(ownership.keys()))
    if missing_coverage:
        raise SystemExit(f"scene{scene_id}: non-deleted cuts missing from render_units: {missing_coverage}")


def parse_manifest(path: Path) -> tuple[list[str], list[str], list[dict[str, object]]]:
    if yaml is None:  # pragma: no cover
        raise SystemExit("PyYAML is required for scripts/build-clip-lists.py")

    raw_text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(extract_yaml_block(raw_text))
    if not isinstance(data, dict):
        raise SystemExit(f"Manifest root must be a mapping: {path}")

    clips: list[str] = []
    narrations: list[str] = []
    exclusions: list[dict[str, object]] = []

    for raw_scene in data.get("scenes") or []:
        if not isinstance(raw_scene, dict):
            continue
        scene_id = raw_scene.get("scene_id")
        raw_cuts = raw_scene.get("cuts")
        if isinstance(raw_cuts, list) and raw_cuts:
            normalized_scene_id = normalize_dotted_id(scene_id) or str(scene_id or "").strip()
            if isinstance(raw_scene.get("render_units"), list) and raw_scene.get("render_units"):
                _append_render_unit_outputs(
                    scene_id=normalized_scene_id,
                    raw_scene=raw_scene,
                    raw_cuts=[cut for cut in raw_cuts if isinstance(cut, dict)],
                    clips=clips,
                    narrations=narrations,
                )
            for raw_cut in raw_cuts:
                if not isinstance(raw_cut, dict):
                    continue
                cut_id = raw_cut.get("cut_id")
                selector = _selector(scene_id, cut_id)
                cut_status = _normalize_status(raw_cut.get("cut_status"))
                image_generation = raw_cut.get("image_generation") if isinstance(raw_cut.get("image_generation"), dict) else {}
                video_generation = raw_cut.get("video_generation") if isinstance(raw_cut.get("video_generation"), dict) else {}
                audio = raw_cut.get("audio") if isinstance(raw_cut.get("audio"), dict) else {}
                narration = audio.get("narration") if isinstance(audio.get("narration"), dict) else {}
                skipped_outputs: list[str] = []
                for maybe_output in (
                    image_generation.get("output"),
                    video_generation.get("output"),
                    narration.get("output"),
                ):
                    if isinstance(maybe_output, str) and maybe_output.strip():
                        skipped_outputs.append(maybe_output.strip())
                if cut_status == "deleted":
                    exclusions.append(
                        {
                            "selector": selector,
                            "reason": str(raw_cut.get("deletion_reason") or "").strip(),
                            "skipped_outputs": skipped_outputs,
                        }
                    )
                    continue
                if isinstance(raw_scene.get("render_units"), list) and raw_scene.get("render_units"):
                    continue
                video_output = video_generation.get("output")
                if isinstance(video_output, str) and video_output.strip():
                    clips.append(video_output.strip())
                narration_output = narration.get("output")
                if isinstance(narration_output, str) and narration_output.strip():
                    narrations.append(narration_output.strip())
            continue

        selector = _selector(scene_id)
        scene_status = _normalize_status(raw_scene.get("cut_status"))
        image_generation = raw_scene.get("image_generation") if isinstance(raw_scene.get("image_generation"), dict) else {}
        video_generation = raw_scene.get("video_generation") if isinstance(raw_scene.get("video_generation"), dict) else {}
        audio = raw_scene.get("audio") if isinstance(raw_scene.get("audio"), dict) else {}
        narration = audio.get("narration") if isinstance(audio.get("narration"), dict) else {}
        skipped_outputs = []
        for maybe_output in (
            image_generation.get("output"),
            video_generation.get("output"),
            narration.get("output"),
        ):
            if isinstance(maybe_output, str) and maybe_output.strip():
                skipped_outputs.append(maybe_output.strip())
        if scene_status == "deleted":
            exclusions.append(
                {
                    "selector": selector,
                    "reason": str(raw_scene.get("deletion_reason") or "").strip(),
                    "skipped_outputs": skipped_outputs,
                }
            )
            continue
        video_output = video_generation.get("output")
        if isinstance(video_output, str) and video_output.strip():
            clips.append(video_output.strip())
        narration_output = narration.get("output")
        if isinstance(narration_output, str) and narration_output.strip():
            narrations.append(narration_output.strip())

    return clips, narrations, exclusions


def write_concat_list(paths: list[str], out_path: Path, dry_run: bool) -> None:
    lines = [f"file '{p}'" for p in paths]
    if dry_run:
        return
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def write_exclusion_report(exclusions: list[dict[str, object]], out_path: Path, dry_run: bool) -> None:
    lines = ["# Generation Exclusion Report", ""]
    if not exclusions:
        lines.extend(["除外対象はありません。", ""])
    else:
        for entry in exclusions:
            lines.append(f"## {entry['selector']}")
            lines.append("")
            lines.append("- status: `deleted`")
            reason = str(entry.get("reason") or "").strip()
            if reason:
                lines.append(f"- reason: {reason}")
            skipped_outputs = list(entry.get("skipped_outputs") or [])
            if skipped_outputs:
                lines.append("- skipped_outputs:")
                for item in skipped_outputs:
                    lines.append(f"  - `{item}`")
            else:
                lines.append("- skipped_outputs: `[]`")
            lines.append("")
    if dry_run:
        return
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ffmpeg concat lists from manifest(s).")
    parser.add_argument("--manifest", action="append", default=[], help="Manifest file path. Can be used multiple times.")
    parser.add_argument("--dir", default=None, help="Directory to search for manifests.")
    parser.add_argument("--story-dir", default=None, help="Story folder containing a single manifest.")
    parser.add_argument("--pattern", default="*_manifest.md", help="Glob pattern for manifest search.")
    parser.add_argument("--out-dir", default=None, help="Directory to write output lists (default: manifest dir).")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, no files written.")
    args = parser.parse_args()

    manifest_paths = [Path(p) for p in args.manifest]

    if args.story_dir:
        story_dir = Path(args.story_dir)
        matches = list(story_dir.glob(args.pattern))
        if len(matches) == 0:
            raise SystemExit(f"No manifest found in {story_dir} with pattern {args.pattern}.")
        if len(matches) > 1:
            names = ", ".join(str(p) for p in matches)
            raise SystemExit(f"Multiple manifests found in {story_dir}. Use --manifest to pick one. Found: {names}")
        manifest_paths.append(matches[0])

    if args.dir:
        manifest_paths.extend(Path(p) for p in glob.glob(str(Path(args.dir) / args.pattern)))

    manifest_paths = list(dict.fromkeys(manifest_paths))
    if not manifest_paths:
        raise SystemExit("No manifest files found. Use --manifest, --story-dir, or --dir.")

    for manifest in manifest_paths:
        clips, narrations, exclusions = parse_manifest(manifest)

        base = manifest.stem
        if base.endswith("_manifest"):
            base = base[: -len("_manifest")]

        out_dir = Path(args.out_dir) if args.out_dir else manifest.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        clips_path = out_dir / f"{base}_clips.txt"
        narration_path = out_dir / f"{base}_narration_list.txt"
        exclusions_path = out_dir / f"{base}_generation_exclusions.md"

        write_concat_list(clips, clips_path, args.dry_run)
        write_concat_list(narrations, narration_path, args.dry_run)
        write_exclusion_report(exclusions, exclusions_path, args.dry_run)
        if not args.dry_run:
            write_run_index(out_dir)

        print(f"Manifest: {manifest}")
        print(f"  clips: {clips_path} ({len(clips)} entries)")
        print(f"  narration: {narration_path} ({len(narrations)} entries)")
        print(f"  exclusions: {exclusions_path} ({len(exclusions)} entries)")


if __name__ == "__main__":
    main()
