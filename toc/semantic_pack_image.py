"""Image-stage semantic review collection helpers.

These collectors are intentionally side-effect free so a generic semantic pack
builder can call them before deciding where to render collection/scope/prompt
artifacts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from toc.harness import load_structured_document

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - exercised only in minimal envs
    yaml = None


IMAGE_STAGES = {"image_prompt", "scene_image"}
DEFAULT_MODE_FILTER = "generate_still"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
EXPECTED_ROLE_BY_ID_GROUP = {
    "character_ids": "character",
    "object_ids": "object",
    "location_ids": "location",
}


def collect_entries(stage: str, run_dir: Path, manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Collect image semantic review entries for a generic dispatcher."""

    if stage not in IMAGE_STAGES:
        raise ValueError(f"unsupported image semantic stage: {stage}")
    resolved_run_dir = Path(run_dir).resolve()
    data = manifest if isinstance(manifest, dict) else load_manifest(resolved_run_dir / "video_manifest.md")
    asset_context = asset_context_by_id(resolved_run_dir)
    if stage == "image_prompt":
        entries = collect_image_prompt_entries(data, asset_context=asset_context)
        return entries + collect_scene_composite_entries(data, stage=stage)
    entries = collect_scene_image_entries(resolved_run_dir, data, asset_context=asset_context)
    return entries + collect_scene_composite_entries(data, stage=stage, run_dir=resolved_run_dir)


def load_manifest(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to collect image semantic review entries.")
    return yaml.safe_load(extract_yaml_block(path.read_text(encoding="utf-8"))) or {}


def extract_yaml_block(text: str) -> str:
    match = re.search(r"```yaml\s*\n(.*?)\n```", text, re.S)
    if not match:
        raise ValueError("YAML block not found in video_manifest.md")
    return match.group(1)


def collect_image_prompt_entries(
    manifest: dict[str, Any],
    *,
    mode_filter: str = DEFAULT_MODE_FILTER,
    asset_context: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    asset_context = asset_context or {}
    for scene, cut in iter_scene_cuts(manifest):
        image_generation = _dict(cut.get("image_generation"))
        if not image_generation:
            continue
        plan = _dict(cut.get("still_image_plan"))
        plan_mode = _as_str(plan.get("mode"))
        if plan_mode and plan_mode != mode_filter:
            continue
        review = _dict(image_generation.get("review"))
        contract = _cut_semantic_contract(cut, image_generation=image_generation, review=review)
        semantic_contract = semantic_contract_payload(contract)
        ids = {
            "character_ids": _as_str_list(image_generation.get("character_ids")),
            "object_ids": _as_str_list(image_generation.get("object_ids")),
            "location_ids": _as_str_list(image_generation.get("location_ids")),
        }
        entries.append(
            {
                "stage": "image_prompt",
                "review_scope": "all_entries",
                "selector": cut_selector(scene, cut),
                "scene_id": scene.get("scene_id"),
                "cut_id": cut.get("cut_id"),
                "output": _as_str(image_generation.get("output")),
                "prompt": _as_str(image_generation.get("prompt")),
                "references": _as_str_list(image_generation.get("references")),
                **ids,
                "asset_reference_context": reference_context(ids, asset_context),
                "reference_count": _as_int(image_generation.get("reference_count")),
                "narration": narration_text(cut),
                "rationale": _as_str(plan.get("rationale")),
                "semantic_contract": semantic_contract,
                "semantic_contract_missing": semantic_contract_missing(semantic_contract),
                "contract_required_fields_missing": missing_contract_fields(semantic_contract),
                "review": {
                    "status": _as_str(review.get("status")),
                    "agent_review_ok": _as_bool(review.get("agent_review_ok"), True),
                    "human_review_ok": _as_bool(review.get("human_review_ok"), False),
                    "agent_review_reason_keys": _as_str_list(
                        review.get("agent_review_reason_keys") or review.get("agent_review_reason_codes")
                    ),
                    "agent_review_reason_messages": _as_str_list(review.get("agent_review_reason_messages")),
                    "overall_score": _as_float(review.get("overall_score")),
                },
            }
        )
    return entries


def collect_scene_image_entries(
    run_dir: Path,
    manifest: dict[str, Any],
    *,
    asset_context: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    provenance = image_generation_provenance_by_destination(run_dir)
    contact_sheet_refs = discover_contact_sheet_refs(run_dir)
    contact_sheet_missing = not contact_sheet_refs
    asset_context = asset_context or {}
    entries: list[dict[str, Any]] = []
    for scene, cut in iter_scene_cuts(manifest):
        image_generation = _dict(cut.get("image_generation"))
        output = _as_str(image_generation.get("output"))
        if not output:
            continue
        output_path = resolve_run_path(run_dir, output)
        selector = cut_selector(scene, cut)
        matched_provenance = provenance.get(output) or provenance.get(output_path.as_posix())
        final_output_provenance = normalize_final_output_provenance(
            output=output,
            output_path=output_path,
            provenance=matched_provenance,
        )
        ids = {
            "character_ids": _as_str_list(image_generation.get("character_ids")),
            "object_ids": _as_str_list(image_generation.get("object_ids")),
            "location_ids": _as_str_list(image_generation.get("location_ids")),
        }
        semantic_contract = semantic_contract_payload(_cut_semantic_contract(cut, image_generation=image_generation))
        entries.append(
            {
                "stage": "scene_image",
                "review_scope": "all_entries",
                "selector": selector,
                "scene_id": scene.get("scene_id"),
                "cut_id": cut.get("cut_id"),
                "output": output,
                "output_exists": output_path.exists() and output_path.is_file(),
                "output_path": output_path.as_posix(),
                "final_output_provenance": final_output_provenance,
                "generated_image_path": _as_str((matched_provenance or {}).get("savedPath")),
                "generation_source": _as_str((matched_provenance or {}).get("source")),
                "debug_log": _as_str((matched_provenance or {}).get("debug_log")),
                "prompt": _as_str(image_generation.get("prompt")),
                "references": _as_str_list(image_generation.get("references")),
                **ids,
                "asset_reference_context": reference_context(ids, asset_context),
                "reference_count": _as_int(image_generation.get("reference_count")),
                "semantic_contract": semantic_contract,
                "semantic_contract_missing": semantic_contract_missing(semantic_contract),
                "contract_required_fields_missing": missing_contract_fields(semantic_contract),
                "narration": narration_text(cut),
                "contact_sheet_required": True,
                "contact_sheet_missing": contact_sheet_missing,
                "contact_sheet_refs": contact_sheet_refs,
            }
        )
    return entries


def collect_scene_composite_entries(
    manifest: dict[str, Any],
    *,
    stage: str,
    run_dir: Path | None = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    scenes = manifest.get("scenes")
    if not isinstance(scenes, list):
        return entries
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        cuts = [cut for cut in _list(scene.get("cuts")) if isinstance(cut, dict)]
        if not cuts:
            continue
        cut_entries: list[dict[str, Any]] = []
        for cut in cuts:
            image_generation = _dict(cut.get("image_generation"))
            video_generation = _dict(cut.get("video_generation"))
            contract = _cut_semantic_contract(cut, image_generation=image_generation)
            semantic_contract = semantic_contract_payload(contract)
            output = _as_str(image_generation.get("output"))
            output_exists = None
            if run_dir is not None and output:
                output_exists = resolve_run_path(run_dir, output).exists()
            cut_entries.append(
                {
                    "selector": cut_selector(scene, cut),
                    "cut_function": _as_str(contract.get("cut_function")),
                    "target_focus": semantic_contract.get("target_focus", ""),
                    "screen_question": _as_str(contract.get("screen_question")),
                    "dramatic_job": _as_str(contract.get("dramatic_job")),
                    "visual_proof": _as_str(contract.get("visual_beat") or contract.get("visual_proof")),
                    "first_frame_brief": _as_str(contract.get("first_frame_brief")),
                    "prompt": _as_str(image_generation.get("prompt")),
                    "image_output": output,
                    "image_output_exists": output_exists,
                    "video_motion_prompt": _as_str(video_generation.get("motion_prompt")),
                    "motion_brief": _as_str(contract.get("motion_brief")),
                    "narration": narration_text(cut),
                    "semantic_contract": semantic_contract,
                }
            )
        scene_contract = {
            "scene_id": scene.get("scene_id"),
            "scene_intent": _dict(scene.get("scene_intent")),
            "scene_cut_coverage_plan": _dict(scene.get("scene_cut_coverage_plan")),
            "handoff_to_next_scene": _as_str(scene.get("handoff_to_next_scene")),
            "terminal_resolution": _as_str(scene.get("terminal_resolution")),
            "target_duration_seconds": scene.get("target_duration_seconds"),
            "estimated_duration_seconds": scene.get("estimated_duration_seconds"),
            "cut_count": len(cut_entries),
        }
        entries.append(
            {
                "stage": stage,
                "review_scope": "scene_composite",
                "selector": f"scene{scene.get('scene_id')}",
                "scene_id": scene.get("scene_id"),
                "scene_contract": scene_contract,
                "scene_cut_coverage_plan": _dict(scene.get("scene_cut_coverage_plan")),
                "cut_count": len(cut_entries),
                "cut_entries": cut_entries,
                "scene_composite_gate": {
                    "required": True,
                    "minimum_cut_count": _as_int(_dict(scene.get("scene_cut_coverage_plan")).get("minimum_cut_count")) or 2,
                    "must_judge": [
                        "scene_cut_coverage_plan の scene_obligations が cut_entries に割り当てられているか",
                        "cutごとの差異が番号差分や同義反復ではなく、sceneを再現するために必要な視覚要件の分担になっているか",
                        "各cutの画像promptが、動画として接続した時にscene設計の問い、価値変化、因果転換、handoffを伝えられるか",
                        "不足時は scene_requires_more_cuts、絵の具体性不足は cut_prompt_requires_reinforcement、重複過多は scene_cut_prompt_too_similar として判定する",
                    ],
                    "failure_reason_keys": [
                        "scene_cut_coverage_insufficient",
                        "scene_cut_prompt_too_similar",
                        "scene_meaning_not_visualized_across_cuts",
                        "scene_video_handoff_weak",
                        "scene_requires_more_cuts",
                        "cut_prompt_requires_reinforcement",
                    ],
                },
            }
        )
    return entries


def asset_context_by_id(run_dir: Path) -> dict[str, dict[str, Any]]:
    context: dict[str, dict[str, Any]] = {}
    for rel in ("asset_inventory.md", "asset_plan.md"):
        path = run_dir / rel
        if not path.exists():
            continue
        _, data = load_structured_document(path)
        if rel == "asset_inventory.md":
            root = data.get("asset_inventory") if isinstance(data.get("asset_inventory"), dict) else data
            for item in _list(root.get("items") if isinstance(root, dict) else []):
                if not isinstance(item, dict):
                    continue
                asset_id = _as_str(item.get("item_id") or item.get("asset_id"))
                if not asset_id:
                    continue
                context.setdefault(asset_id, {}).update(
                    {
                        "inventory_category": _as_str(item.get("category")),
                        "inventory_story_purpose": _as_str(item.get("story_purpose")),
                        "reusable_reason": _as_str(item.get("reusable_reason")),
                        "recommended_asset_type": _as_str(item.get("recommended_asset_type")),
                    }
                )
        else:
            for item in asset_plan_items(data):
                if not isinstance(item, dict):
                    continue
                asset_id = _as_str(item.get("asset_id") or item.get("item_id"))
                if not asset_id:
                    continue
                context.setdefault(asset_id, {}).update(
                    {
                        "asset_type": _as_str(item.get("asset_type")),
                        "story_purpose": _as_str(item.get("story_purpose")),
                        "source_script_selectors": _as_str_list(item.get("source_script_selectors")),
                        "visual_spec": item.get("visual_spec") if item.get("visual_spec") is not None else {},
                    }
                )
    return {asset_id: payload for asset_id, payload in context.items() if any(value not in ("", [], {}) for value in payload.values())}


def asset_plan_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    assets = data.get("assets")
    if isinstance(assets, list):
        return [item for item in assets if isinstance(item, dict)]
    if not isinstance(assets, dict):
        return []
    out: list[dict[str, Any]] = []
    for category in ("characters", "objects", "locations", "setpieces", "reusable_stills"):
        for item in _list(assets.get(category)):
            if isinstance(item, dict):
                copied = dict(item)
                copied.setdefault("_category", category)
                out.append(copied)
    return out


def reference_context(ids: dict[str, list[str]], asset_context: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for group, values in ids.items():
        expected_role = EXPECTED_ROLE_BY_ID_GROUP.get(group, "")
        matched = {
            asset_id: normalize_asset_reference_context(asset_context.get(asset_id, {}), expected_role=expected_role)
            for asset_id in values
            if asset_context.get(asset_id)
        }
        if matched:
            payload[group] = matched
    return payload


def normalize_asset_reference_context(context: dict[str, Any], *, expected_role: str) -> dict[str, Any]:
    category = _as_str(context.get("category") or context.get("inventory_category") or context.get("asset_type") or context.get("recommended_asset_type"))
    story_purpose = _as_str(context.get("story_purpose") or context.get("inventory_story_purpose") or context.get("reusable_reason"))
    visual_spec = context.get("visual_spec") if context.get("visual_spec") is not None else {}
    return {
        "category": category,
        "story_purpose": story_purpose,
        "visual_spec": visual_spec,
        "expected_reference_role": expected_role,
        "reference_role_mismatch_hints": reference_role_mismatch_hints(context, expected_role=expected_role),
    }


def reference_role_mismatch_hints(context: dict[str, Any], *, expected_role: str) -> list[str]:
    if not expected_role:
        return []
    actual_roles = infer_reference_roles(context)
    if not actual_roles or expected_role in actual_roles:
        return []
    sorted_actual_roles = sorted(actual_roles)
    return [
        "expected_reference_role="
        f"{expected_role} but asset metadata suggests {','.join(sorted_actual_roles)}"
    ]


def infer_reference_roles(context: dict[str, Any]) -> set[str]:
    values = [
        context.get("category"),
        context.get("inventory_category"),
        context.get("asset_type"),
        context.get("recommended_asset_type"),
    ]
    combined = " ".join(_as_str(value).lower() for value in values if _as_str(value))
    roles: set[str] = set()
    if any(token in combined for token in ("character", "person", "people", "人物", "キャラクター")):
        roles.add("character")
    if any(token in combined for token in ("object", "artifact", "prop", "item", "小道具", "物", "舞台装置")):
        roles.add("object")
    if any(token in combined for token in ("location", "place", "setting", "background", "場所", "舞台", "背景")):
        roles.add("location")
    return roles


def iter_scene_cuts(manifest: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    scenes = manifest.get("scenes")
    if not isinstance(scenes, list):
        return pairs
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        cuts = scene.get("cuts")
        if not isinstance(cuts, list):
            continue
        for cut in cuts:
            if isinstance(cut, dict):
                pairs.append((scene, cut))
    return pairs


def cut_selector(scene: dict[str, Any], cut: dict[str, Any]) -> str:
    explicit = _as_str(cut.get("selector"))
    if explicit:
        return explicit
    scene_digits = re.sub(r"\D+", "", str(scene.get("scene_id") or ""))
    cut_raw = str(cut.get("cut_id") or "")
    cut_digits = re.sub(r"\D+", "", cut_raw.split("-")[-1])
    if scene_digits and cut_digits:
        return f"scene{int(scene_digits):02d}_cut{int(cut_digits):02d}"
    return ""


def narration_text(cut: dict[str, Any]) -> str:
    audio = _dict(cut.get("audio"))
    narration = _dict(audio.get("narration"))
    return _as_str(narration.get("text") or narration.get("tts_text"))


def _cut_semantic_contract(
    cut: dict[str, Any],
    *,
    image_generation: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    image_generation = image_generation or _dict(cut.get("image_generation"))
    review = review or _dict(image_generation.get("review"))
    explicit = _dict(review.get("contract")) or _dict(image_generation.get("contract"))
    if explicit:
        return explicit
    cut_contract = _dict(cut.get("cut_contract"))
    if cut_contract:
        viewer = _dict(cut_contract.get("viewer_contract"))
        first_frame = _dict(cut_contract.get("first_frame_contract"))
        motion = _dict(cut_contract.get("motion_contract"))
        cinematic = _dict(cut_contract.get("cinematic_contract"))
        geography = _dict(cinematic.get("screen_geography"))
        continuity = _dict(cut_contract.get("continuity_contract"))
        location_ids = _as_str_list(continuity.get("location_ids"))
        start_state = _dict(continuity.get("start_state"))
        return {
            "cut_function": _as_str(cut_contract.get("cut_function")),
            "target_focus": _as_str(viewer.get("target_beat") or cut_contract.get("target_beat")),
            "target_beat": _as_str(viewer.get("target_beat") or cut_contract.get("target_beat")),
            "screen_question": _as_str(viewer.get("screen_question")),
            "dramatic_job": _as_str(viewer.get("dramatic_job")),
            "visual_beat": _as_str(viewer.get("visual_proof") or cut_contract.get("visual_beat")),
            "must_include": _as_str_list(viewer.get("must_show") or first_frame.get("must_include")),
            "must_show": _as_str_list(viewer.get("must_show") or first_frame.get("must_include")),
            "must_avoid": _as_str_list(viewer.get("must_avoid") or first_frame.get("must_avoid")),
            "done_when": _as_str_list(viewer.get("done_when")),
            "first_frame_brief": _as_str(first_frame.get("first_frame_brief")),
            "motion_brief": _as_str(motion.get("motion_brief")),
            "primary_location": _as_str(geography.get("background") or (location_ids[0] if location_ids else "")),
            "continuity_from_previous": _as_str(start_state.get("spatial_state") or start_state.get("character_state")),
        }
    return _dict(cut.get("scene_contract"))


def semantic_contract_payload(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_focus": _as_str(contract.get("target_focus") or contract.get("target_beat")),
        "must_include": _as_str_list(contract.get("must_include") or contract.get("must_show")),
        "must_avoid": _as_str_list(contract.get("must_avoid")),
        "done_when": _as_str_list(contract.get("done_when")),
        "not_yet_visible": _as_str_list(contract.get("not_yet_visible")),
        "only_after_scene": _as_str(contract.get("only_after_scene")),
        "primary_location": _as_str(contract.get("primary_location")),
        "emotional_state": _as_str(contract.get("emotional_state")),
        "continuity_from_previous": _as_str(contract.get("continuity_from_previous")),
    }


def semantic_contract_missing(contract: dict[str, Any]) -> bool:
    return bool(missing_contract_fields(contract))


def missing_contract_fields(contract: dict[str, Any]) -> list[str]:
    required = ("target_focus", "must_include", "done_when")
    return [key for key in required if contract.get(key) in ("", [], {})]


def normalize_final_output_provenance(
    *,
    output: str,
    output_path: Path,
    provenance: dict[str, Any] | None,
) -> dict[str, Any]:
    provenance = provenance or {}
    return {
        "declared_output": output,
        "resolved_output_path": output_path.as_posix(),
        "output_exists": output_path.exists() and output_path.is_file(),
        "saved_path": _as_str(provenance.get("savedPath")),
        "source": _as_str(provenance.get("source")),
        "status": _as_str(provenance.get("status")),
        "debug_log": _as_str(provenance.get("debug_log")),
    }


def discover_contact_sheet_refs(run_dir: Path) -> list[str]:
    candidates = [
        run_dir / "logs" / "review" / "semantic" / "scene_image.contact_sheet.md",
        run_dir / "logs" / "review" / "semantic" / "scene_image.contact_sheet.png",
        run_dir / "logs" / "review" / "semantic" / "scene_image.samples.json",
        run_dir / "logs" / "review" / "scene_image.contact_sheet.md",
        run_dir / "logs" / "review" / "scene_image.contact_sheet.png",
        run_dir / "logs" / "review" / "scene_image.samples.json",
    ]
    refs: list[str] = []
    for path in candidates:
        if path.exists():
            refs.append(_relpath(run_dir, path))
    return refs


def image_generation_provenance_by_destination(run_dir: Path) -> dict[str, dict[str, Any]]:
    by_destination: dict[str, dict[str, Any]] = {}
    for log_dir in (run_dir / "logs" / "app_server" / "image_gen", run_dir / "logs" / "app_server" / "request_item_generation"):
        if not log_dir.exists():
            continue
        for path in sorted(log_dir.glob("*.json")):
            record = load_json(path)
            if not isinstance(record, dict):
                continue
            destination = _as_str(record.get("destination"))
            response = _dict(record.get("response"))
            request = _dict(record.get("request"))
            if not destination:
                destination = _as_str(request.get("output"))
            if not destination:
                continue
            payload = {
                "debug_log": _relpath(run_dir, path),
                "savedPath": _as_str(record.get("savedPath") or response.get("savedPath")),
                "source": _as_str(record.get("source") or response.get("source")),
                "status": _as_str(record.get("status") or response.get("status")),
            }
            by_destination[destination] = payload
            by_destination[resolve_run_path(run_dir, destination).as_posix()] = payload
    return by_destination


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def resolve_run_path(run_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (run_dir / path).resolve()


def _relpath(run_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(run_dir.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    return default


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
