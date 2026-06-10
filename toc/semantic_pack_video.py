from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

from toc.immersive_manifest import make_scene_cut_selector, normalize_dotted_id


VIDEO_STAGE_NAMES = {"video_motion"}
_YAML_BLOCK_RE = re.compile(r"```yaml\s*\n(.*?)\n```", re.DOTALL)
_MEDIA_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm", ".png", ".jpg", ".jpeg", ".webp"}
_MOTION_CONTRACT_FIELD_ALIASES = {
    "motion_intent": ("motion_intent", "intent", "motion_brief", "action_intent"),
    "must_preserve": ("must_preserve", "preserve", "continuity_must_preserve"),
    "must_not_add": ("must_not_add", "must_avoid", "must_not_invent", "forbidden_additions"),
    "handoff_state": ("handoff_state", "end_state", "handoff", "next_cut_handoff"),
}


def collect_entries(stage: str, run_dir: Path, manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if stage not in VIDEO_STAGE_NAMES:
        raise ValueError(f"unsupported video semantic pack stage: {stage}")
    data = manifest if manifest is not None else _load_manifest(run_dir)
    return _collect_video_motion_entries(run_dir, data)


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "video_manifest.md"
    if not manifest_path.exists():
        return {}
    if yaml is None:  # pragma: no cover
        raise RuntimeError("PyYAML is required to parse video_manifest.md")
    text = manifest_path.read_text(encoding="utf-8")
    match = _YAML_BLOCK_RE.search(text)
    yaml_text = match.group(1) if match else text
    data = yaml.safe_load(yaml_text) or {}
    return data if isinstance(data, dict) else {}


def _collect_video_motion_entries(run_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for scene in _iter_scenes(manifest):
        for cut in _iter_cuts(scene):
            if _is_deleted(cut):
                continue
            video_generation = _mapping(cut.get("video_generation"))
            if not video_generation:
                continue
            selector = _cut_selector(scene, cut)
            motion_contract = _motion_contract(cut, video_generation)
            missing_fields = _motion_contract_required_fields_missing(motion_contract)
            cut_contract = _mapping(cut.get("cut_contract"))
            entries.append(
                {
                    "stage": "video_motion",
                    "selector": selector,
                    "scene_id": scene.get("scene_id"),
                    "cut_id": cut.get("cut_id"),
                    "source": "video_manifest.md.scenes[].cuts[].video_generation",
                    "semantic_contract": _semantic_contract(cut, video_generation),
                    "source_event_contract": _mapping(cut_contract.get("source_event_contract")),
                    "event_context_for_cut": _mapping(cut_contract.get("event_context_for_cut")),
                    "motion_prompt": _first_text(video_generation, "motion_prompt", "prompt", "video_prompt"),
                    "motion_contract": motion_contract,
                    "motion_contract_missing": not bool(motion_contract),
                    "motion_contract_required_fields_missing": missing_fields,
                    "first_frame": _first_text(video_generation, "first_frame", "first_frame_image", "input_image"),
                    "last_frame": _first_text(video_generation, "last_frame", "last_frame_image"),
                    "duration_seconds": video_generation.get("duration_seconds"),
                    "tool": video_generation.get("tool"),
                    "output": _normalize_relpath(video_generation.get("output")),
                    "provider_history": _provider_history(video_generation),
                }
            )
        for unit in _iter_render_units(scene):
            if _is_deleted(unit):
                continue
            video_generation = _mapping(unit.get("video_generation"))
            selector = _render_unit_selector(scene, unit)
            motion_contract = _motion_contract(unit, video_generation)
            missing_fields = _motion_contract_required_fields_missing(motion_contract)
            entries.append(
                {
                    "stage": "video_motion",
                    "selector": selector,
                    "scene_id": scene.get("scene_id"),
                    "unit_id": unit.get("unit_id"),
                    "source": "video_manifest.md.scenes[].render_units[].video_generation",
                    "source_cut_ids": _list_values(unit.get("source_cut_ids")),
                    "semantic_contract": _semantic_contract(unit, video_generation),
                    "motion_prompt": _first_text(video_generation, "motion_prompt", "prompt", "video_prompt"),
                    "motion_contract": motion_contract,
                    "motion_contract_missing": not bool(motion_contract),
                    "motion_contract_required_fields_missing": missing_fields,
                    "first_frame": _first_text(video_generation, "first_frame", "first_frame_image", "input_image"),
                    "last_frame": _first_text(video_generation, "last_frame", "last_frame_image"),
                    "duration_seconds": video_generation.get("duration_seconds"),
                    "tool": video_generation.get("tool"),
                    "output": _normalize_relpath(video_generation.get("output")),
                    "provider_history": _provider_history(video_generation),
                }
            )
    return entries


def _collect_video_clip_entries(run_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for motion_entry in _collect_video_motion_entries(run_dir, manifest):
        output = _normalize_relpath(motion_entry.get("output"))
        video_generation = _video_generation_for_selector(manifest, motion_entry["selector"])
        sampled_frames = _sampled_frames(run_dir, video_generation, output)
        contact_sheet = _contact_sheet(run_dir, video_generation, output, motion_entry["selector"])
        entries.append(
            {
                "stage": "video_clip",
                "selector": motion_entry["selector"],
                "scene_id": motion_entry.get("scene_id"),
                "cut_id": motion_entry.get("cut_id"),
                "unit_id": motion_entry.get("unit_id"),
                "source": motion_entry["source"],
                "semantic_contract": motion_entry.get("semantic_contract"),
                "motion_prompt": motion_entry.get("motion_prompt"),
                "first_frame": motion_entry.get("first_frame"),
                "last_frame": motion_entry.get("last_frame"),
                "output": output,
                "output_exists": _path_exists(run_dir, output),
                "sampled_frames": sampled_frames,
                "contact_sheet": contact_sheet,
                "contact_sheet_required": True,
                "contact_sheet_missing": contact_sheet is None,
                "sampled_frames_missing": not bool(sampled_frames),
                "provider_status": _first_text(video_generation, "status", "provider_status", "generation_status"),
                "operation_id": _first_text(video_generation, "operation_id", "provider_job_id", "job_id"),
                "provider_history": _provider_history(video_generation),
            }
        )
    return entries


def _collect_render_entries(run_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    final_outputs = _existing_render_outputs(run_dir, manifest)
    return [
        {
            "stage": "render",
            "selector": "render",
            "source": "render outputs and concat lists",
            "semantic_contract": _render_contract(manifest),
            "final_outputs": final_outputs,
            "clip_list": _text_artifact(run_dir, "video_clips.txt"),
            "narration_list": _text_artifact(run_dir, "video_narration_list.txt"),
            "generation_exclusions": _text_artifact(run_dir, "video_generation_exclusions.md"),
            "render_order_materials": _render_order_materials(run_dir, manifest),
            "render_sample_refs": _render_sample_refs(run_dir, manifest, final_outputs),
            "render_logs": _render_logs(run_dir),
            "clip_entries": _collect_video_clip_entries(run_dir, manifest),
        }
    ]


def _iter_scenes(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    scenes = manifest.get("scenes")
    if not isinstance(scenes, list):
        return []
    return [scene for scene in scenes if isinstance(scene, dict)]


def _iter_cuts(scene: dict[str, Any]) -> list[dict[str, Any]]:
    cuts = scene.get("cuts")
    if not isinstance(cuts, list):
        return []
    return [cut for cut in cuts if isinstance(cut, dict)]


def _iter_render_units(scene: dict[str, Any]) -> list[dict[str, Any]]:
    units = scene.get("render_units")
    if not isinstance(units, list):
        return []
    return [unit for unit in units if isinstance(unit, dict)]


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _cut_selector(scene: dict[str, Any], cut: dict[str, Any]) -> str:
    return make_scene_cut_selector(scene.get("scene_id"), cut.get("cut_id"))


def _render_unit_selector(scene: dict[str, Any], unit: dict[str, Any]) -> str:
    scene_id = normalize_dotted_id(scene.get("scene_id")) or str(scene.get("scene_id") or "unknown").strip() or "unknown"
    unit_id = normalize_dotted_id(unit.get("unit_id")) or str(unit.get("unit_id") or "unknown").strip() or "unknown"
    return f"scene{scene_id}_unit{unit_id}"


def _is_deleted(item: dict[str, Any]) -> bool:
    return str(item.get("cut_status") or item.get("status") or "").strip().lower() == "deleted"


def _semantic_contract(item: dict[str, Any], video_generation: dict[str, Any]) -> Any:
    cut_contract = _mapping(item.get("cut_contract"))
    explicit = (
        _first_value(video_generation, "semantic_contract", "contract", "review_contract")
        or _first_value(item, "semantic_contract", "video_semantic_contract", "scene_contract", "review_contract")
    )
    if explicit:
        return explicit
    if cut_contract and not cut_contract.get("source_event_contract"):
        return cut_contract
    return {
        "source_event_contract": _mapping(cut_contract.get("source_event_contract")),
        "event_context_for_cut": _mapping(cut_contract.get("event_context_for_cut")),
        "motion_contract": _mapping(cut_contract.get("motion_contract")),
    }


def _render_contract(manifest: dict[str, Any]) -> Any:
    quality = _mapping(manifest.get("quality_check"))
    render = _mapping(manifest.get("render"))
    return (
        _first_value(render, "semantic_contract", "contract", "review_contract")
        or _first_value(quality, "review_contract", "semantic_contract", "contract")
        or _first_value(manifest, "semantic_contract", "review_contract")
    )


def _motion_contract(item: dict[str, Any], video_generation: dict[str, Any]) -> Any:
    cut_contract = _mapping(item.get("cut_contract"))
    return (
        _first_value(video_generation, "motion_contract", "video_motion_contract")
        or _first_value(item, "motion_contract", "video_motion_contract")
        or _first_value(cut_contract, "motion_contract")
        or _first_value(video_generation, "semantic_contract", "contract")
    )


def _motion_contract_required_fields_missing(contract: Any) -> list[str]:
    if not isinstance(contract, dict):
        return list(_MOTION_CONTRACT_FIELD_ALIASES.keys())
    if (
        _has_contract_value(contract, "source_event_beat_id")
        and _has_contract_value(contract, "starts_from_first_frame")
        and _has_contract_value(contract, "must_not_advance_to_event_beat_ids")
        and _has_contract_value(contract, "motion_brief")
        and _has_contract_value(contract, "end_state")
    ):
        return []
    missing: list[str] = []
    for canonical, aliases in _MOTION_CONTRACT_FIELD_ALIASES.items():
        if not any(_has_contract_value(contract, alias) for alias in aliases):
            missing.append(canonical)
    return missing


def _has_contract_value(contract: dict[str, Any], key: str) -> bool:
    value = contract.get(key)
    if value in (None, ""):
        return False
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return bool(value)
    return bool(str(value).strip())


def _provider_history(video_generation: dict[str, Any]) -> list[Any]:
    history: list[Any] = []
    for key in (
        "provider_history",
        "retry_history",
        "failure_history",
        "generation_history",
        "attempts",
        "retries",
        "failures",
    ):
        value = video_generation.get(key)
        if isinstance(value, list) and key in {"provider_history", "retry_history", "failure_history", "generation_history", "attempts"}:
            history.extend(value)
        elif isinstance(value, list):
            history.append({key: value})
        elif isinstance(value, dict):
            history.append({key: value})
        elif value not in (None, ""):
            history.append({key: value})

    summary: dict[str, Any] = {}
    for key in (
        "provider_status",
        "generation_status",
        "status",
        "retry_count",
        "failure_reason",
        "last_error",
        "operation_id",
        "provider_job_id",
        "job_id",
    ):
        value = video_generation.get(key)
        if value not in (None, ""):
            summary[key] = value
    if summary:
        history.append({"provider_summary": summary})
    return history


def _render_order_materials(run_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    expected_clip_order: list[dict[str, Any]] = []
    expected_narration_order: list[dict[str, Any]] = []

    for scene in _iter_scenes(manifest):
        render_units = _iter_render_units(scene)
        cuts = _iter_cuts(scene)
        cut_lookup = {
            normalize_dotted_id(cut.get("cut_id")): cut
            for cut in cuts
            if normalize_dotted_id(cut.get("cut_id")) and not _is_deleted(cut)
        }
        if render_units:
            for unit in render_units:
                if _is_deleted(unit):
                    continue
                video_generation = _mapping(unit.get("video_generation"))
                output = _normalize_relpath(video_generation.get("output"))
                expected_clip_order.append(
                    {
                        "selector": _render_unit_selector(scene, unit),
                        "source_cut_ids": _list_values(unit.get("source_cut_ids")),
                        "output": output,
                    }
                )
                for cut_id in _list_values(unit.get("source_cut_ids")):
                    normalized_cut_id = normalize_dotted_id(cut_id)
                    cut = cut_lookup.get(normalized_cut_id)
                    if cut:
                        expected_narration_order.extend(_narration_order_entries(scene, cut))
            continue

        for cut in cuts:
            if _is_deleted(cut):
                continue
            video_generation = _mapping(cut.get("video_generation"))
            output = _normalize_relpath(video_generation.get("output"))
            if output:
                expected_clip_order.append({"selector": _cut_selector(scene, cut), "output": output})
            expected_narration_order.extend(_narration_order_entries(scene, cut))

    return {
        "manifest_clip_order": expected_clip_order,
        "concat_clip_order": _concat_list_paths(run_dir / "video_clips.txt"),
        "manifest_narration_order": expected_narration_order,
        "concat_narration_order": _concat_list_paths(run_dir / "video_narration_list.txt"),
    }


def _narration_order_entries(scene: dict[str, Any], cut: dict[str, Any]) -> list[dict[str, Any]]:
    audio = _mapping(cut.get("audio"))
    narration = _mapping(audio.get("narration"))
    output = _normalize_relpath(narration.get("output"))
    if not output:
        return []
    return [{"selector": _cut_selector(scene, cut), "output": output}]


def _concat_list_paths(path: Path) -> list[str]:
    if not path.exists():
        return []
    entries: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        match = re.match(r"""file\s+['"](.+?)['"]\s*$""", line)
        entries.append(match.group(1) if match else line)
    return entries


def _render_sample_refs(run_dir: Path, manifest: dict[str, Any], final_outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    render = _mapping(manifest.get("render"))
    refs: list[dict[str, Any]] = []
    for item in final_outputs:
        output = _normalize_relpath(item.get("path"))
        sampled_frames = _sampled_frames(run_dir, render, output)
        contact_sheet = _contact_sheet(run_dir, render, output, "render")
        if sampled_frames or contact_sheet:
            refs.append(
                {
                    "output": output,
                    "sampled_frames": sampled_frames,
                    "sampled_frames_missing": not bool(sampled_frames),
                    "contact_sheet": contact_sheet,
                    "contact_sheet_missing": contact_sheet is None,
                }
            )
    explicit = _first_value(render, "render_sample_refs", "sample_refs")
    if isinstance(explicit, list):
        refs.extend(explicit)
    return refs


def _first_value(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def _first_text(mapping: dict[str, Any], *keys: str) -> str | None:
    value = _first_value(mapping, *keys)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _list_values(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _normalize_relpath(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _path_exists(run_dir: Path, relpath: str | None) -> bool:
    return bool(relpath and (run_dir / relpath).exists())


def _video_generation_for_selector(manifest: dict[str, Any], selector: str) -> dict[str, Any]:
    for scene in _iter_scenes(manifest):
        for cut in _iter_cuts(scene):
            if _cut_selector(scene, cut) == selector:
                return _mapping(cut.get("video_generation"))
        for unit in _iter_render_units(scene):
            if _render_unit_selector(scene, unit) == selector:
                return _mapping(unit.get("video_generation"))
    return {}


def _sampled_frames(run_dir: Path, video_generation: dict[str, Any], output: str | None) -> list[str]:
    explicit = _first_value(video_generation, "sampled_frames", "sample_frames", "frames", "sampled_frame_paths")
    frames = [_normalize_relpath(item) for item in explicit] if isinstance(explicit, list) else []
    frames = [frame for frame in frames if frame]
    if frames:
        return frames

    candidates: list[Path] = []
    if output:
        output_path = run_dir / output
        candidates.extend(
            [
                output_path.with_suffix("") / "frames",
                output_path.with_name(f"{output_path.stem}_frames"),
                run_dir / "assets" / "video_frames" / output_path.stem,
                run_dir / "logs" / "review" / "semantic" / f"{output_path.stem}_frames",
            ]
        )
    paths: list[str] = []
    for directory in candidates:
        if directory.exists() and directory.is_dir():
            for child in sorted(directory.iterdir()):
                if child.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    paths.append(_rel_to_run_dir(run_dir, child))
    return paths


def _contact_sheet(run_dir: Path, video_generation: dict[str, Any], output: str | None, selector: str) -> str | None:
    explicit = _first_text(video_generation, "contact_sheet", "contact_sheet_path", "sample_contact_sheet", "thumbnail")
    if explicit:
        return explicit

    candidates: list[Path] = []
    if output:
        output_path = run_dir / output
        for suffix in (".jpg", ".jpeg", ".png", ".webp"):
            candidates.append(output_path.with_name(f"{output_path.stem}_contact_sheet{suffix}"))
            candidates.append(run_dir / "logs" / "review" / "semantic" / f"{output_path.stem}_contact_sheet{suffix}")
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        candidates.append(run_dir / "logs" / "review" / "semantic" / f"{selector}_contact_sheet{suffix}")

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return _rel_to_run_dir(run_dir, candidate)
    return None


def _existing_render_outputs(run_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[str] = []
    render = _mapping(manifest.get("render"))
    for key in ("output", "final_output", "video_output"):
        value = _normalize_relpath(render.get(key))
        if value:
            candidates.append(value)
    for default in ("video.mp4", "final.mp4", "render.mp4", "output.mp4"):
        candidates.append(default)
    unique = list(dict.fromkeys(candidates))
    return [{"path": path, "exists": _path_exists(run_dir, path)} for path in unique if path]


def _text_artifact(run_dir: Path, relpath: str) -> dict[str, Any]:
    path = run_dir / relpath
    if not path.exists():
        return {"path": relpath, "exists": False, "entry_count": 0, "preview": ""}
    text = path.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.strip()]
    return {"path": relpath, "exists": True, "entry_count": len(lines), "preview": "\n".join(lines[:20])}


def _render_logs(run_dir: Path) -> list[str]:
    candidates: list[Path] = []
    for pattern in ("render*.log", "logs/render*.log", "logs/render/*.log", "logs/review/render*.md"):
        candidates.extend(sorted(run_dir.glob(pattern)))
    return [_rel_to_run_dir(run_dir, path) for path in candidates if path.is_file()]


def _rel_to_run_dir(run_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return path.as_posix()
