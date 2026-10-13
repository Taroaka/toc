"""Shared structural contracts for source-grounded visual state variants."""

from __future__ import annotations

from copy import deepcopy
from pathlib import PurePosixPath
from typing import Any, Mapping

from toc.immersive_manifest import make_scene_cut_selector, normalize_dotted_id
from toc.video_provider_capabilities import resolve_video_provider_capabilities


_ENTITY_TYPES = {
    "character": ("character_bible", "character_id", "character_reference", "character_ids", "character_variant_ids"),
    "object": ("object_bible", "object_id", "object_reference", "object_ids", "object_variant_ids"),
    "location": ("location_bible", "location_id", "location_reference", "location_ids", "location_variant_ids"),
}


def state_variant_output_path(entity_type: str, asset_id: str, variant_id: str) -> str:
    """Return a stable asset-stage path without embedding a run or story title."""

    normalized_type = str(entity_type or "").strip()
    normalized_asset = str(asset_id or "").strip()
    normalized_variant = str(variant_id or "").strip()
    if normalized_type not in _ENTITY_TYPES:
        raise AssetStateVariantError(f"asset_state_variant_entity_type_invalid:{normalized_type or '<missing>'}")
    if not normalized_asset or not normalized_asset.replace("-", "").replace("_", "").replace(".", "").isalnum():
        raise AssetStateVariantError("asset_state_variant_asset_id_invalid")
    if not normalized_variant or not normalized_variant.replace("-", "").replace("_", "").isalnum():
        raise AssetStateVariantError("asset_state_variant_id_invalid")
    directory = {"character": "characters", "object": "objects", "location": "locations"}[normalized_type]
    return f"assets/{directory}/{normalized_asset}__{normalized_variant}.png"


class AssetStateVariantError(ValueError):
    """A required state asset or result frame cannot be safely materialized."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str) and item.strip()]


def normalize_state_variant_bindings(value: Any, *, strict: bool = False) -> list[dict[str, Any]]:
    """Normalize one legacy state binding or a multi-asset state binding list."""

    mapping = _mapping(value)
    rows = mapping.get("state_variant_refs")
    if isinstance(rows, list):
        if strict and any(not isinstance(row, Mapping) for row in rows):
            raise AssetStateVariantError("asset_state_variant_binding_entry_invalid")
        return [dict(row) for row in rows if isinstance(row, Mapping)]
    if all(str(mapping.get(key) or "").strip() for key in ("entity_type", "asset_id", "variant_id")):
        return [mapping]
    return []


def _manifest_cuts(manifest: Mapping[str, Any]):
    for raw_scene in manifest.get("scenes") or []:
        if not isinstance(raw_scene, Mapping):
            continue
        scene_id = normalize_dotted_id(raw_scene.get("scene_id"))
        if scene_id is None:
            continue
        cuts = raw_scene.get("cuts")
        nodes = cuts if isinstance(cuts, list) and cuts else [raw_scene]
        for index, raw_cut in enumerate(nodes, start=1):
            if not isinstance(raw_cut, Mapping):
                continue
            cut_id = normalize_dotted_id(raw_cut.get("cut_id")) or str(index)
            selector = str(raw_cut.get("selector") or make_scene_cut_selector(scene_id, cut_id)).strip()
            if _mapping(raw_cut.get('shot_plan')).get('schema_version') == 'shot_direction_v1':
                for shot in raw_cut.get('shots') or []:
                    if not isinstance(shot, Mapping):
                        raise AssetStateVariantError(f'{selector}: shot must be an object')
                    shot_selector = f"{selector}_shot{shot.get('shot_id', '')}"
                    yield str(scene_id), str(cut_id), shot_selector, raw_scene, shot
                continue
            yield str(scene_id), str(cut_id), selector, raw_scene, raw_cut


def _variant_index(manifest: Mapping[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    assets = _mapping(manifest.get("assets"))
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entity_type, (bible_key, id_key, asset_type, _, _) in _ENTITY_TYPES.items():
        for raw_entry in assets.get(bible_key) or []:
            if not isinstance(raw_entry, Mapping):
                continue
            parent_id = str(raw_entry.get(id_key) or "").strip()
            if not parent_id:
                continue
            variants = raw_entry.get("reference_variants") or raw_entry.get("variants") or []
            if not isinstance(variants, list):
                continue
            for raw_variant in variants:
                if not isinstance(raw_variant, Mapping):
                    continue
                variant_id = str(raw_variant.get("variant_id") or raw_variant.get("reference_id") or "").strip()
                if not variant_id:
                    continue
                key = (entity_type, parent_id, variant_id)
                if key in index:
                    raise AssetStateVariantError(f"asset_state_variant_duplicate:{entity_type}:{parent_id}:{variant_id}")
                index[key] = {
                    "entity_type": entity_type,
                    "asset_type": asset_type,
                    "asset_id": parent_id,
                    "variant_id": variant_id,
                    "variant": dict(raw_variant),
                    "parent": dict(raw_entry),
                }
    return index


def _required_state_transition(record: Mapping[str, Any], *, selector: str) -> dict[str, Any] | None:
    variant = _mapping(record.get("variant"))
    transition = _mapping(variant.get("state_transition"))
    if not transition:
        return None
    variant_id = str(record.get("variant_id") or "<missing>")
    asset_id = str(record.get("asset_id") or "<missing>")
    required_fields = ("transition_id", "from_state", "to_state")
    missing = [key for key in required_fields if not str(transition.get(key) or "").strip()]
    source_event_ids = _strings(transition.get("source_event_beat_ids"))
    if missing or not source_event_ids:
        detail = ", ".join([*missing, *(["source_event_beat_ids"] if not source_event_ids else [])])
        raise AssetStateVariantError(
            f"{selector}: asset state variant {asset_id}/{variant_id} has incomplete state_transition: {detail}"
        )
    prompt = str(variant.get("generation_prompt") or "").strip()
    if not prompt:
        raise AssetStateVariantError(
            f"{selector}: asset state variant {asset_id}/{variant_id} requires an authored generation_prompt"
        )
    outputs = _strings(variant.get("reference_images"))
    if len(outputs) != 1:
        raise AssetStateVariantError(
            f"{selector}: asset state variant {asset_id}/{variant_id} requires exactly one planned reference_images output"
        )
    path = PurePosixPath(outputs[0])
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "assets":
        raise AssetStateVariantError(
            f"{selector}: asset state variant {asset_id}/{variant_id} output must be run-relative under assets/"
        )
    return transition


def _selector_usage(manifest: Mapping[str, Any]) -> dict[tuple[str, str, str], list[str]]:
    variant_index = _variant_index(manifest)
    usage: dict[tuple[str, str, str], list[str]] = {}

    def add_selected(entity_type: str, asset_ids: list[str], variant_ids: list[str], selector: str) -> None:
        for asset_id in asset_ids:
            for variant_id in variant_ids:
                key = (entity_type, asset_id, variant_id)
                record = variant_index.get(key)
                if record is not None and _mapping(record["variant"].get("state_transition")) and selector:
                    usage.setdefault(key, []).append(selector)

    for _scene_id, _cut_id, selector, _raw_scene, cut in _manifest_cuts(manifest):
        image = _mapping(cut.get("image_generation"))
        for entity_type, (_, _, _, asset_key, variant_key) in _ENTITY_TYPES.items():
            add_selected(entity_type, _strings(image.get(asset_key)), _strings(image.get(variant_key)), selector)
        video = _mapping(cut.get("video_generation"))
        result_ref = _mapping(video.get("result_state_reference"))
        if result_ref.get("required") is True:
            for state_ref in normalize_state_variant_bindings(result_ref, strict=True):
                variant_id = str(state_ref.get("variant_id") or "").strip()
                entity_type = str(state_ref.get("entity_type") or "").strip()
                if variant_id and entity_type in _ENTITY_TYPES:
                    key = (entity_type, str(state_ref.get("asset_id") or "").strip(), variant_id)
                    if key in variant_index:
                        usage.setdefault(key, []).append(selector)
            result_frame = _mapping(video.get("result_frame"))
            result_image = _mapping(result_frame.get("image_generation"))
            for entity_type, (_, _, _, asset_key, variant_key) in _ENTITY_TYPES.items():
                add_selected(entity_type, _strings(result_image.get(asset_key)), _strings(result_image.get(variant_key)), selector)
    return {key: list(dict.fromkeys(values)) for key, values in usage.items()}


def _source_event_beat_ids(manifest: Mapping[str, Any]) -> set[str]:
    known: set[str] = set()
    for raw_scene in manifest.get("scenes") or []:
        if not isinstance(raw_scene, Mapping):
            continue
        event = _mapping(raw_scene.get("scene_event"))
        for beat in event.get("event_sequence") or []:
            if isinstance(beat, Mapping) and str(beat.get("beat_id") or "").strip():
                known.add(str(beat["beat_id"]).strip())
        cuts = raw_scene.get("cuts") if isinstance(raw_scene.get("cuts"), list) else [raw_scene]
        for cut in cuts:
            if not isinstance(cut, Mapping):
                continue
            contract = _mapping(cut.get("cut_contract")) or _mapping(cut.get("scene_contract"))
            event_contract = _mapping(contract.get("source_event_contract"))
            known.update(_strings(event_contract.get("source_event_beat_ids")))
            known.update(_strings(event_contract.get("source_event_beat_id") and [event_contract.get("source_event_beat_id")]))
    return known


def required_state_variant_plan_entries(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Project authored state variants into p500 requests, preserving parent lineage."""

    assets = _mapping(manifest.get("assets"))
    usage = _selector_usage(manifest)
    known_event_ids = _source_event_beat_ids(manifest)
    entries: list[dict[str, Any]] = []
    for entity_type, (bible_key, id_key, asset_type, _, _) in _ENTITY_TYPES.items():
        for raw_entry in assets.get(bible_key) or []:
            if not isinstance(raw_entry, Mapping):
                continue
            parent_id = str(raw_entry.get(id_key) or "").strip()
            if not parent_id:
                continue
            parent_refs = _strings(raw_entry.get("reference_images"))
            variants = raw_entry.get("reference_variants") or raw_entry.get("variants") or []
            if not isinstance(variants, list):
                continue
            for raw_variant in variants:
                if not isinstance(raw_variant, Mapping) or not _mapping(raw_variant.get("state_transition")):
                    continue
                variant_id = str(raw_variant.get("variant_id") or raw_variant.get("reference_id") or "").strip()
                selector_list = usage.get((entity_type, parent_id, variant_id), [])
                selector = selector_list[0] if selector_list else f"asset_state:{parent_id}:{variant_id or '<missing>'}"
                record = {"entity_type": entity_type, "asset_type": asset_type, "asset_id": parent_id,
                          "variant_id": variant_id, "variant": dict(raw_variant), "parent": dict(raw_entry)}
                transition = _required_state_transition(record, selector=selector)
                if not variant_id:
                    raise AssetStateVariantError(f"{selector}: asset state variant requires variant_id")
                if not selector_list:
                    raise AssetStateVariantError(
                        f"asset state variant {parent_id}/{variant_id} is not selected by any scene image or required video result frame"
                    )
                if not parent_refs:
                    raise AssetStateVariantError(
                        f"{selector}: asset state variant {parent_id}/{variant_id} has no parent identity reference to derive from"
                    )
                unknown_event_ids = sorted(set(_strings(transition.get("source_event_beat_ids"))) - known_event_ids)
                if unknown_event_ids:
                    raise AssetStateVariantError(
                        f"{selector}: asset state variant {parent_id}/{variant_id} references unknown source event beat IDs: {', '.join(unknown_event_ids)}"
                    )
                variant = dict(raw_variant)
                output = _strings(variant.get("reference_images"))[0]
                references = _strings(variant.get("generation_references")) or parent_refs
                transition_id = str(transition.get("transition_id") or "")
                plan_id = f"{parent_id}__state__{variant_id}"
                entries.append({
                    "asset_id": plan_id,
                    "parent_asset_id": parent_id,
                    "reference_variant_id": variant_id,
                    "asset_type": asset_type,
                    "source_script_selectors": selector_list,
                    "story_purpose": f"{str(transition.get('from_state') or '').strip()} → {str(transition.get('to_state') or '').strip()}",
                    "fixed_prompts": _strings(variant.get("fixed_prompts")),
                    "generation_prompt": str(variant.get("generation_prompt") or "").strip(),
                    "subject_contract": deepcopy(raw_entry.get("subject_contract") or {}),
                    "appearance_contract": deepcopy(raw_entry.get("appearance_contract") or {}),
                    "reuse_contract": {"mode": "state_variant", "derived_from_asset_id": parent_id},
                    "state_transition": dict(transition),
                    "generation_plan": {
                        "execution_lane": "standard",
                        "bootstrap_allowed": False,
                        "required_views": ["single"],
                        "reference_inputs": references,
                        "derived_from_asset_id": parent_id,
                        "output": output,
                    },
                })
    return entries


def validate_result_state_references(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Bind required result frames to scene-specific p600 end-frame requests.

    The state asset is only a visual identity anchor. `last_frame` must point to the
    separate scene-compositional result image declared under `result_frame`.
    """

    variants = _variant_index(manifest)
    frame_specs: list[dict[str, Any]] = []
    for raw_scene in manifest.get("scenes") or []:
        if not isinstance(raw_scene, Mapping):
            continue
        for unit in raw_scene.get("render_units") or []:
            if not isinstance(unit, Mapping):
                continue
            unit_video = _mapping(unit.get("video_generation"))
            if _mapping(unit_video.get("result_state_reference")).get("required") is True:
                unit_id = str(unit.get("unit_id") or "<unknown>").strip()
                raise AssetStateVariantError(
                    f"scene{normalize_dotted_id(raw_scene.get('scene_id')) or '<unknown>'}_unit{unit_id}: required result-frame conditioning is not supported for render-unit video requests"
                )
    for _scene_id, _cut_id, selector, _raw_scene, cut in _manifest_cuts(manifest):
        video = cut.get("video_generation")
        if not isinstance(video, dict):
            continue
        binding = _mapping(video.get("result_state_reference"))
        directed_end = (_mapping(_mapping(cut.get('cut_contract')).get('shot_direction')).get('schema_version') == 'shot_direction_v1'
                        and isinstance(video.get('result_frame'), dict))
        if binding.get("required") is not True and not directed_end:
            continue
        state_refs = normalize_state_variant_bindings(binding, strict=True)
        if not state_refs and not directed_end:
            raise AssetStateVariantError(
                f"{selector}: result_state_reference requires one or more entity_type/asset_id/variant_id bindings"
            )
        result_frame = video.get("result_frame")
        if not isinstance(result_frame, dict):
            raise AssetStateVariantError(
                f"{selector}: required result_state_reference is missing its scene-specific result_frame image request"
            )
        image = result_frame.get("image_generation")
        if not isinstance(image, dict):
            raise AssetStateVariantError(
                f"{selector}: required result_frame is missing image_generation"
            )
        visual_plan = _mapping(image.get("first_frame_visual_plan"))
        payload = _mapping(image.get("api_prompt_payload"))
        if not visual_plan or str(payload.get("policy_version") or "") != "image_api_prompt_v2":
            raise AssetStateVariantError(
                f"{selector}: result_frame requires a materialized image_api_prompt_v2 visual plan"
            )
        state_variant_references = []
        cut_contract = _mapping(cut.get("cut_contract")) or _mapping(cut.get("scene_contract"))
        source_event_contract = _mapping(cut_contract.get("source_event_contract"))
        cut_source_event_ids = set(_strings(source_event_contract.get("source_event_beat_ids")))
        primary_source_id = str(source_event_contract.get("primary_event_beat_id") or "").strip()
        if primary_source_id:
            cut_source_event_ids.add(primary_source_id)
        for state_ref in state_refs:
            entity_type = str(state_ref.get("entity_type") or "").strip()
            asset_id = str(state_ref.get("asset_id") or "").strip()
            variant_id = str(state_ref.get("variant_id") or "").strip()
            transition_id = str(state_ref.get("transition_id") or "").strip()
            if entity_type not in _ENTITY_TYPES or not asset_id or not variant_id:
                raise AssetStateVariantError(
                    f"{selector}: result_state_reference entry requires entity_type, asset_id, and variant_id"
                )
            record = variants.get((entity_type, asset_id, variant_id))
            if record is None:
                raise AssetStateVariantError(
                    f"{selector}: result_state_reference does not resolve to an asset bible state variant: {entity_type}/{asset_id}/{variant_id}"
                )
            transition = _required_state_transition(record, selector=selector)
            if not transition_id or transition_id != str(transition.get("transition_id") or ""):
                raise AssetStateVariantError(
                    f"{selector}: result_state_reference transition_id does not match its authored asset state variant"
                )
            consumer_event_ids = _strings(state_ref.get("consumer_source_event_beat_ids"))
            if not consumer_event_ids or not set(consumer_event_ids) <= cut_source_event_ids:
                raise AssetStateVariantError(
                    f"{selector}: result_state_reference must bind its visible state to source event beat IDs owned by this cut"
                )
            _, _, _, id_list_key, variant_list_key = _ENTITY_TYPES[entity_type]
            if asset_id not in _strings(image.get(id_list_key)) or variant_id not in _strings(image.get(variant_list_key)):
                raise AssetStateVariantError(
                    f"{selector}: result_frame image_generation must select the declared {entity_type} asset and state variant"
                )
            outputs = _strings(record["variant"].get("reference_images"))
            if len(outputs) != 1 or outputs[0] not in _strings(image.get("references")):
                raise AssetStateVariantError(
                    f"{selector}: result_frame must reference the generated state-variant image"
                )
            state_variant_references.extend(outputs)
        output = str(result_frame.get("output") or image.get("output") or "").strip()
        image_output = str(image.get("output") or "").strip()
        if not output or output != image_output:
            raise AssetStateVariantError(
                f"{selector}: result_frame output must match its image_generation.output"
            )
        path = PurePosixPath(output)
        if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "assets":
            raise AssetStateVariantError(f"{selector}: result_frame output must be run-relative under assets/")
        first_frame = str(video.get("first_frame") or video.get("input_image") or _mapping(cut.get("image_generation")).get("output") or "").strip()
        if not first_frame or first_frame == output:
            raise AssetStateVariantError(
                f"{selector}: required result_frame needs a distinct first-frame image"
            )
        if first_frame not in _strings(image.get("references")):
            raise AssetStateVariantError(
                f"{selector}: scene-specific result_frame must reference the primary first-frame image as a layout anchor"
            )
        if video.get("references") or str(video.get("input_mode") or video.get("mode") or "").strip().lower() in {
            "reference_images", "reference_to_video"
        }:
            raise AssetStateVariantError(
                f"{selector}: result-frame conditioning cannot combine with reference-image video mode"
            )
        input_contract = _mapping(cut.get("video_input_contract"))
        if str(input_contract.get("input_mode") or "").strip().lower() == "reference_images":
            raise AssetStateVariantError(
                f"{selector}: result-frame conditioning cannot combine with a reference-image video input contract"
            )
        tool = str(video.get("tool") or "kling_3_0").strip()
        payload = _mapping(video.get("api_prompt_payload"))
        binding_payload = _mapping(payload.get("provider_request_binding"))
        options = _mapping(binding_payload.get("execution_options"))
        model = str(options.get("model") or video.get("model") or "").strip()
        capability = resolve_video_provider_capabilities(
            tool=tool,
            model=model,
            input_mode="first_last_frame",
        )
        if not capability.supported or not capability.first_last_frame_supported:
            reason = capability.unsupported_reason or f"{tool} does not support first/last-frame conditioning"
            raise AssetStateVariantError(f"{selector}: required result-frame conditioning is unsupported: {reason}")
        existing_last = str(video.get("last_frame") or "").strip()
        if existing_last and existing_last != output:
            raise AssetStateVariantError(
                f"{selector}: video_generation.last_frame conflicts with the required result_frame output"
            )
        video["last_frame"] = output
        frame_specs.append({
            "selector": selector,
            "output": output,
            "state_variant_references": list(dict.fromkeys(state_variant_references)),
            "image_generation": dict(image),
            "source_node": cut,
        })
    return frame_specs
