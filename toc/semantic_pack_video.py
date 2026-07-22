from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

from toc.immersive_manifest import make_scene_cut_selector, normalize_dotted_id
from toc.video_prompt_compiler import (
    VIDEO_API_PROMPT_POLICY_VERSION,
    VIDEO_PROMPT_COMPILER_VERSION,
    compile_video_api_prompt_v1,
    compose_video_render_unit_contract,
)
from toc.video_prompt_projection_registry import VIDEO_PROMPT_PROJECTION_REGISTRY_VERSION


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
        render_units = _iter_render_units(scene)
        if not render_units:
            for cut in _iter_cuts(scene):
                if _is_deleted(cut):
                    continue
                video_generation = _mapping(cut.get("video_generation"))
                if not video_generation:
                    continue
                selector = _cut_selector(scene, cut)
                effective_cut_contract = _effective_video_item_contract(scene, cut)
                motion_contract = _motion_contract(
                    cut,
                    video_generation,
                    cut_contract=effective_cut_contract,
                )
                missing_fields = _motion_contract_required_fields_missing(motion_contract)
                cut_contract = _mapping(cut.get("cut_contract"))
                provider_prompt_payload = _provider_prompt_payload(
                    run_dir=run_dir,
                    manifest=manifest,
                    scene=scene,
                    item=cut,
                    video_generation=video_generation,
                    cut_contract=effective_cut_contract,
                )
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
                        "source_motion_prompt": _first_text(
                            video_generation,
                            "prompt_authoring_source",
                            "source_motion_prompt",
                            "motion_prompt",
                            "prompt",
                            "video_prompt",
                        ),
                        "provider_prompt": provider_prompt_payload["prompt"],
                        "provider_prompt_payload": provider_prompt_payload,
                        "quality_issues": provider_prompt_payload.get(
                            "quality_issues"
                        )
                        or [],
                        "video_prompt_projection": _compact_video_projection(
                            provider_prompt_payload.get("projection_review_contract")
                        ),
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
        for unit in render_units:
            if _is_deleted(unit):
                continue
            video_generation = _mapping(unit.get("video_generation"))
            selector = _render_unit_selector(scene, unit)
            effective_cut_contract = _effective_video_item_contract(scene, unit)
            motion_contract = _motion_contract(
                unit,
                video_generation,
                cut_contract=effective_cut_contract,
            )
            missing_fields = _motion_contract_required_fields_missing(motion_contract)
            provider_prompt_payload = _provider_prompt_payload(
                run_dir=run_dir,
                manifest=manifest,
                scene=scene,
                item=unit,
                video_generation=video_generation,
                cut_contract=effective_cut_contract,
            )
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
                    "source_motion_prompt": _first_text(
                        video_generation,
                        "prompt_authoring_source",
                        "source_motion_prompt",
                        "motion_prompt",
                        "prompt",
                        "video_prompt",
                    ),
                    "provider_prompt": provider_prompt_payload["prompt"],
                    "provider_prompt_payload": provider_prompt_payload,
                    "quality_issues": provider_prompt_payload.get(
                        "quality_issues"
                    )
                    or [],
                    "video_prompt_projection": _compact_video_projection(
                        provider_prompt_payload.get("projection_review_contract")
                    ),
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


def _scene_visualizable_action(scene: dict[str, Any]) -> Any:
    action = scene.get("visualizable_action")
    if action not in (None, "", [], {}):
        return action
    return _mapping(scene.get("scene_intent")).get(
        "review_only_visualizable_action"
    )


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


def _motion_contract(
    item: dict[str, Any],
    video_generation: dict[str, Any],
    *,
    cut_contract: dict[str, Any] | None = None,
) -> Any:
    canonical_contract = cut_contract or _mapping(item.get("cut_contract"))
    return (
        _first_value(canonical_contract, "motion_contract")
        or _first_value(item, "motion_contract", "video_motion_contract")
        or _first_value(video_generation, "motion_contract", "video_motion_contract")
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


def _provider_prompt_payload(
    *,
    run_dir: Path,
    manifest: dict[str, Any],
    scene: dict[str, Any],
    item: dict[str, Any],
    video_generation: dict[str, Any],
    cut_contract: dict[str, Any],
) -> dict[str, Any]:
    materialized = _mapping(video_generation.get("api_prompt_payload"))
    materialized_prompt = str(materialized.get("prompt") or "").strip()
    metadata = _mapping(manifest.get("video_metadata"))
    scene_contract = _mapping(item.get("scene_contract"))
    source_prompt_fields = ["prompt_authoring_source", "source_motion_prompt"]
    if not materialized_prompt:
        # Legacy manifests without a compiled payload may use these fields as
        # authoring prose. Once a payload exists, ``motion_prompt`` is the
        # compiled provider prompt and must not be fed back into the compiler.
        source_prompt_fields.extend(["motion_prompt", "prompt", "video_prompt"])
    source_prompt = _first_text(video_generation, *source_prompt_fields)
    execution_options = _mapping(
        _mapping(materialized.get("provider_request_binding")).get(
            "execution_options"
        )
    )
    current = compile_video_api_prompt_v1(
        cut_contract=cut_contract,
        scene_contract=scene_contract,
        video_generation=video_generation,
        source_prompt=source_prompt,
        story_time=str(metadata.get("time") or "").strip(),
        time_of_day=str(scene.get("time_of_day") or "").strip(),
        tool=str(video_generation.get("tool") or "kling_3_0").strip(),
        first_frame=_first_text(
            video_generation,
            "first_frame",
            "first_frame_image",
            "input_image",
        ),
        last_frame=_first_text(video_generation, "last_frame", "last_frame_image"),
        duration_seconds=video_generation.get("duration_seconds"),
        references=_list_values(video_generation.get("references")),
        reference_roles=[
            dict(value)
            for value in (
                _mapping(item.get("video_input_contract")).get(
                    "reference_roles"
                )
                or video_generation.get("reference_roles")
                or []
            )
            if isinstance(value, dict)
        ]
        or None,
        quality=str(video_generation.get("quality") or "").strip(),
        aspect_ratio=str(video_generation.get("aspect_ratio") or "").strip(),
        execution_options=execution_options,
        additional_negative_prompt=str(
            video_generation.get("negative_prompt") or ""
        ).strip(),
        direction_notes=_list_values(video_generation.get("direction_notes")),
        continuity_notes=_list_values(video_generation.get("continuity_notes")),
        first_frame_visual_plan=_first_frame_visual_plan(scene, item),
        review_only_dependencies=_video_item_review_dependencies(scene, item),
        scene_time_of_day_visual_basis=scene.get(
            "time_of_day_visual_basis"
        ),
        scene_location_mode=str(scene.get("location_mode") or "").strip(),
        scene_location_sequence=(
            scene.get("location_sequence")
            if isinstance(scene.get("location_sequence"), list)
            else []
        ),
        scene_location_segments=[
            dict(value)
            for value in (
                scene.get("location_segments")
                if isinstance(scene.get("location_segments"), list)
                else []
            )
            if isinstance(value, dict)
        ],
        scene_visualizable_action=_scene_visualizable_action(scene),
    )
    if not materialized_prompt:
        return current

    version_mismatches = [
        field
        for field, expected in (
            ("policy_version", VIDEO_API_PROMPT_POLICY_VERSION),
            ("compiler_version", VIDEO_PROMPT_COMPILER_VERSION),
            (
                "projection_registry_version",
                VIDEO_PROMPT_PROJECTION_REGISTRY_VERSION,
            ),
        )
        if str(materialized.get(field) or "") != expected
    ]
    if version_mismatches:
        raise ValueError(
            "materialized video prompt uses an obsolete projection: "
            + ", ".join(version_mismatches)
        )

    exact_sha256 = hashlib.sha256(materialized_prompt.encode("utf-8")).hexdigest()
    if str(materialized.get("sha256") or "") != exact_sha256:
        raise ValueError("materialized video prompt hash does not match its exact prompt")

    _validate_materialized_reference_content(
        run_dir=run_dir,
        execution_options=execution_options,
    )
    # Every field emitted by the compiler is canonical review evidence.  A
    # persisted payload may carry additional runtime metadata, but it must not
    # replace or alter any compiler-owned field while leaving only the provider
    # prompt/hash intact.  Compare against an independent recompile and expose
    # that recompile to the reviewer so noncanonical persisted keys cannot
    # influence the semantic decision.
    stale_fields = [
        field
        for field, expected in current.items()
        if materialized.get(field) != expected
    ]
    if stale_fields:
        raise ValueError(
            "materialized video prompt is stale for semantic review: "
            + ", ".join(stale_fields)
        )
    return dict(current)


def _first_frame_visual_plan(
    scene: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
    own_plan = _mapping(
        _mapping(item.get("image_generation")).get("first_frame_visual_plan")
    )
    if own_plan:
        return dict(own_plan)

    raw_source_ids = item.get("source_cut_ids")
    if not isinstance(raw_source_ids, list) or not raw_source_ids:
        return {}
    first_source_id = normalize_dotted_id(raw_source_ids[0])
    for index, cut in enumerate(_iter_cuts(scene), start=1):
        if _is_deleted(cut):
            continue
        cut_id = normalize_dotted_id(cut.get("cut_id")) or str(index)
        if cut_id != first_source_id:
            continue
        plan = _mapping(
            _mapping(cut.get("image_generation")).get("first_frame_visual_plan")
        )
        return dict(plan)
    return {}


def _effective_video_item_contract(
    scene: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any]:
    explicit = _mapping(item.get("cut_contract"))
    raw_source_ids = item.get("source_cut_ids")
    if not isinstance(raw_source_ids, list) or not raw_source_ids:
        return dict(explicit)

    source_ids = [normalize_dotted_id(value) for value in raw_source_ids]
    cuts_by_id: dict[str, dict[str, Any]] = {}
    for index, cut in enumerate(_iter_cuts(scene), start=1):
        if _is_deleted(cut):
            continue
        cut_id = normalize_dotted_id(cut.get("cut_id")) or str(index)
        cuts_by_id[cut_id] = cut
    unresolved_source_ids = [
        str(raw_source_id)
        for raw_source_id, source_id in zip(raw_source_ids, source_ids)
        if not source_id or source_id not in cuts_by_id
    ]
    if unresolved_source_ids:
        raise ValueError(
            "video_render_unit_source_cut_ids_unresolved: "
            + ", ".join(unresolved_source_ids)
        )
    resolved_source_ids = [
        source_id for source_id in source_ids if source_id is not None
    ]
    source_contracts = [
        _mapping(cuts_by_id[source_id].get("cut_contract"))
        for source_id in resolved_source_ids
    ]
    return compose_video_render_unit_contract(
        source_contracts,
        unit_contract=explicit,
    )


def _video_item_review_dependencies(
    scene: dict[str, Any],
    item: dict[str, Any],
) -> dict[str, Any] | None:
    raw_source_ids = item.get("source_cut_ids")
    if not isinstance(raw_source_ids, list) or not raw_source_ids:
        return None
    source_ids = [normalize_dotted_id(value) for value in raw_source_ids]
    cuts_by_id: dict[str, dict[str, Any]] = {}
    for index, cut in enumerate(_iter_cuts(scene), start=1):
        if _is_deleted(cut):
            continue
        cut_id = normalize_dotted_id(cut.get("cut_id")) or str(index)
        cuts_by_id[cut_id] = cut
    return {
        "render_unit_source_cut_ids": [
            source_id for source_id in source_ids if source_id
        ],
        "render_unit_source_cut_contracts": [
            _mapping(cuts_by_id[source_id].get("cut_contract"))
            for source_id in source_ids
            if source_id and source_id in cuts_by_id
        ],
    }


def _validate_materialized_reference_content(
    *,
    run_dir: Path,
    execution_options: dict[str, Any],
) -> None:
    expected_by_path = _mapping(execution_options.get("reference_content_sha256"))
    for raw_path, raw_expected in expected_by_path.items():
        relative_path = str(raw_path or "").strip()
        expected = str(raw_expected or "").strip()
        candidate = run_dir / relative_path
        if not relative_path or not expected or not candidate.is_file():
            raise ValueError(
                "materialized video reference content is missing for semantic review"
            )
        digest = hashlib.sha256()
        with candidate.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(
                "materialized video reference content changed before semantic review"
            )


def _compact_video_projection(value: Any) -> dict[str, Any]:
    projection = _mapping(value)
    active_rules: list[dict[str, Any]] = []
    for raw in projection.get("active_rules") or []:
        if not isinstance(raw, dict):
            continue
        active_rules.append(
            {
                key: raw[key]
                for key in (
                    "source_key",
                    "source_keys",
                    "target_group",
                    "authoring_relevance",
                    "provider_projection",
                    "review_visibility",
                    "value",
                )
                if key in raw
            }
        )
    excluded: list[dict[str, Any]] = []
    for raw in projection.get("excluded") or []:
        if not isinstance(raw, dict):
            continue
        excluded.append(
            {
                key: raw[key]
                for key in (
                    "source_keys",
                    "provider_projection",
                    "review_visibility",
                    "exclusion_reason",
                )
                if key in raw
            }
        )
    return {
        "registry_version": projection.get("registry_version"),
        "provider": projection.get("provider"),
        "mode": projection.get("mode"),
        "groups": projection.get("groups") or {},
        "active_rules": active_rules,
        "shadowed_sources": projection.get("shadowed_sources") or [],
        "excluded": excluded,
        "review_only_sources": projection.get("review_only_sources") or [],
        "review_only_dependencies": projection.get(
            "review_only_dependencies"
        )
        or {},
    }


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
