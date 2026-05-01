#!/usr/bin/env python3
"""Sync reviewed script fields and human change requests into video_manifest.md."""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
import sys
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import load_structured_document
from toc.immersive_manifest import dotted_id_sort_key, dotted_id_slug, make_scene_cut_selector, normalize_dotted_id
from toc.script_narration import resolve_script_cut_tts_text


def replace_yaml_block(text: str, new_yaml: str) -> str:
    start = text.find("```yaml")
    if start < 0:
        return f"```yaml\n{new_yaml}```\n"
    body_start = text.find("\n", start)
    if body_start < 0:
        return f"```yaml\n{new_yaml}```\n"
    end = text.find("\n```", body_start)
    if end < 0:
        return f"```yaml\n{new_yaml}```\n"
    return text[: body_start + 1] + new_yaml + text[end + 1 :]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalized_id(value: Any) -> str | None:
    return normalize_dotted_id(value)


def _sorted_scenes(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: dotted_id_sort_key(item.get("scene_id")))


def _sorted_cuts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: dotted_id_sort_key(item.get("cut_id")))


def preferred_text(cut: dict[str, Any]) -> str:
    review = _as_dict(cut.get("human_review"))
    approved = str(review.get("approved_narration") or "").strip()
    narration = str(cut.get("narration") or "").strip()
    return approved or narration


def preferred_tts_text(cut: dict[str, Any]) -> str:
    return resolve_script_cut_tts_text(cut)


def preferred_visual_beat(cut: dict[str, Any]) -> str:
    review = _as_dict(cut.get("human_review"))
    approved = str(review.get("approved_visual_beat") or "").strip()
    visual_beat = str(cut.get("visual_beat") or "").strip()
    return approved or visual_beat


def _build_request_map(script_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapped: dict[str, dict[str, Any]] = {}
    for request in _as_list(script_data.get("human_change_requests")):
        if not isinstance(request, dict):
            continue
        request_id = str(request.get("request_id") or "").strip()
        if request_id:
            mapped[request_id] = request
    return mapped


def build_script_maps(script_data: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    scene_map: dict[str, dict[str, Any]] = {}
    cut_map: dict[str, dict[str, Any]] = {}
    for scene in _as_list(script_data.get("scenes")):
        if not isinstance(scene, dict):
            continue
        scene_id = _normalized_id(scene.get("scene_id"))
        if not scene_id:
            continue
        scene_map[scene_id] = scene
        for cut in _as_list(scene.get("cuts")):
            if not isinstance(cut, dict):
                continue
            cut_id = _normalized_id(cut.get("cut_id"))
            if not cut_id:
                continue
            cut_map[make_scene_cut_selector(scene_id, cut_id)] = cut
    return scene_map, cut_map


def _ensure_manifest_assets(manifest_data: dict[str, Any]) -> dict[str, Any]:
    assets = manifest_data.get("assets")
    if not isinstance(assets, dict):
        assets = {}
        manifest_data["assets"] = assets
    assets.setdefault("location_bible", [])
    assets.setdefault("object_bible", [])
    assets.setdefault("character_bible", [])
    return assets


def _ensure_scene(scene: dict[str, Any]) -> dict[str, Any]:
    scene.setdefault("cuts", [])
    return scene


def _find_scene(manifest_data: dict[str, Any], scene_id: str) -> dict[str, Any] | None:
    for scene in _as_list(manifest_data.get("scenes")):
        if isinstance(scene, dict) and _normalized_id(scene.get("scene_id")) == scene_id:
            return scene
    return None


def _find_cut(scene: dict[str, Any], cut_id: str) -> dict[str, Any] | None:
    for cut in _as_list(scene.get("cuts")):
        if isinstance(cut, dict) and _normalized_id(cut.get("cut_id")) == cut_id:
            return cut
    return None


def _ensure_audio_narration(cut: dict[str, Any]) -> dict[str, Any]:
    audio = cut.get("audio")
    if not isinstance(audio, dict):
        audio = {}
        cut["audio"] = audio
    narration = audio.get("narration")
    if not isinstance(narration, dict):
        narration = {}
        audio["narration"] = narration
    return narration


def _ensure_image_generation(cut: dict[str, Any]) -> dict[str, Any]:
    image_generation = cut.get("image_generation")
    if not isinstance(image_generation, dict):
        image_generation = {}
        cut["image_generation"] = image_generation
    image_generation.setdefault("character_ids", [])
    image_generation.setdefault("object_ids", [])
    image_generation.setdefault("location_ids", [])
    image_generation.setdefault("location_variant_ids", [])
    return image_generation


def _ensure_video_generation(cut: dict[str, Any]) -> dict[str, Any]:
    video_generation = cut.get("video_generation")
    if not isinstance(video_generation, dict):
        video_generation = {}
        cut["video_generation"] = video_generation
    return video_generation


def _default_video_output(scene_id: str, cut_id: str) -> str:
    try:
        scene_label = f"{int(scene_id):02d}"
    except Exception:
        scene_label = dotted_id_slug(scene_id)
    try:
        cut_label = f"{int(cut_id):02d}"
    except Exception:
        cut_label = dotted_id_slug(cut_id)
    return f"assets/videos/scene{scene_label}_cut{cut_label}.mp4"


def _cut_image_output(cut: dict[str, Any]) -> str:
    image_generation = _as_dict(cut.get("image_generation"))
    output = str(image_generation.get("output") or cut.get("output") or "").strip()
    return output


def _cut_visual_hint(cut: dict[str, Any], script_cut: dict[str, Any]) -> str:
    review = _as_dict(script_cut.get("human_review"))
    approved_visual = str(review.get("approved_visual_beat") or "").strip()
    if approved_visual:
        return approved_visual
    image_generation = _as_dict(cut.get("image_generation"))
    rationale = str(image_generation.get("rationale") or "").strip()
    if rationale:
        return rationale
    return str(script_cut.get("visual_beat") or "").strip()


def _ensure_story_cut_video_defaults(cut: dict[str, Any], *, scene_id: str, cut_id: str, script_cut: dict[str, Any]) -> bool:
    image_output = _cut_image_output(cut)
    if not image_output:
        return False

    video_generation = _ensure_video_generation(cut)
    changed = False

    if not str(video_generation.get("tool") or "").strip():
        video_generation["tool"] = "kling_3_0_omni"
        changed = True
    if not str(video_generation.get("output") or "").strip():
        video_generation["output"] = _default_video_output(scene_id, cut_id)
        changed = True
    if not str(video_generation.get("first_frame") or video_generation.get("input_image") or "").strip():
        video_generation["first_frame"] = image_output
        changed = True
    if "duration_seconds" not in video_generation:
        video_generation["duration_seconds"] = 4
        changed = True
    if not str(video_generation.get("motion_prompt") or "").strip():
        visual_hint = _cut_visual_hint(cut, script_cut)
        if visual_hint:
            video_generation["motion_prompt"] = (
                f"{visual_hint} を主題に、被写体と空間の連続性を保ちつつ、"
                "微速ドリーまたは穏やかな視差移動で見せる。水平と視点を安定させる。"
            )
        else:
            video_generation["motion_prompt"] = (
                "被写体と空間の連続性を保ちつつ、微速ドリーまたは穏やかな視差移動で見せる。"
                "水平と視点を安定させる。"
            )
        changed = True

    request_ids: list[str] = []
    review = _as_dict(script_cut.get("human_review"))
    request_ids.extend(str(v).strip() for v in _as_list(review.get("change_request_ids")) if str(v).strip())
    if not request_ids:
        trace = _as_dict(cut.get("implementation_trace"))
        request_ids.extend(str(v).strip() for v in _as_list(trace.get("source_request_ids")) if str(v).strip())
    if request_ids:
        existing = _as_list(video_generation.get("applied_request_ids"))
        merged: list[str] = []
        for value in [*existing, *request_ids]:
            text = str(value).strip()
            if text and text not in merged:
                merged.append(text)
        if merged != existing:
            video_generation["applied_request_ids"] = merged
            changed = True

    return changed


def _scene_has_render_units(scene: dict[str, Any]) -> bool:
    render_units = scene.get("render_units")
    return isinstance(render_units, list) and bool(render_units)


def _ensure_story_cut_image_plan_defaults(cut: dict[str, Any]) -> bool:
    image_output = _cut_image_output(cut)
    image_prompt = str(_as_dict(cut.get("image_generation")).get("prompt") or "").strip()
    if not image_output or not image_prompt:
        return False
    still_image_plan = cut.get("still_image_plan")
    if not isinstance(still_image_plan, dict):
        still_image_plan = {}
        cut["still_image_plan"] = still_image_plan
    if str(still_image_plan.get("mode") or "").strip():
        return False
    still_image_plan["mode"] = "generate_still"
    return True


def _backfill_video_request_ids_from_trace(cut: dict[str, Any]) -> bool:
    video_generation = cut.get("video_generation")
    if not isinstance(video_generation, dict):
        return False
    trace = _as_dict(cut.get("implementation_trace"))
    request_ids = [str(v).strip() for v in _as_list(trace.get("source_request_ids")) if str(v).strip()]
    if not request_ids:
        return False
    existing = _as_list(video_generation.get("applied_request_ids"))
    merged: list[str] = []
    for value in [*existing, *request_ids]:
        text = str(value).strip()
        if text and text not in merged:
            merged.append(text)
    if merged == existing:
        return False
    video_generation["applied_request_ids"] = merged
    return True


def _ensure_trace(node: dict[str, Any], *, request_ids: list[str]) -> dict[str, Any]:
    trace = node.get("implementation_trace")
    if not isinstance(trace, dict):
        trace = {}
        node["implementation_trace"] = trace
    trace["source_request_ids"] = request_ids
    trace.setdefault("status", "implemented")
    trace.setdefault("notes", "")
    return trace


def _rewrite_nested_strings(value: Any, replacers: list[tuple[str, str]]) -> Any:
    if isinstance(value, str):
        out = value
        for old, new in replacers:
            out = out.replace(old, new)
        return out
    if isinstance(value, list):
        return [_rewrite_nested_strings(item, replacers) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_nested_strings(item, replacers) for key, item in value.items()}
    return value


def _rewrite_scene_identifiers(node: dict[str, Any], *, old_scene_id: str, new_scene_id: str) -> None:
    old_selector = f"scene{old_scene_id}"
    new_selector = f"scene{new_scene_id}"
    old_slug = f"scene{dotted_id_slug(old_scene_id)}"
    new_slug = f"scene{dotted_id_slug(new_scene_id)}"
    replacers = [
        (old_selector + "_cut", new_selector + "_cut"),
        (old_slug + "_cut", new_slug + "_cut"),
        (old_selector, new_selector),
        (old_slug, new_slug),
    ]
    rewritten = _rewrite_nested_strings(node, replacers)
    node.clear()
    node.update(rewritten)


def _rewrite_cut_identifiers(node: dict[str, Any], *, old_cut_id: str, new_cut_id: str) -> None:
    old_selector = f"_cut{old_cut_id}"
    new_selector = f"_cut{new_cut_id}"
    old_slug = f"_cut{dotted_id_slug(old_cut_id)}"
    new_slug = f"_cut{dotted_id_slug(new_cut_id)}"
    replacers = [
        (old_selector, new_selector),
        (old_slug, new_slug),
    ]
    rewritten = _rewrite_nested_strings(node, replacers)
    node.clear()
    node.update(rewritten)


def _sync_human_fields_to_manifest_cut(
    cut: dict[str, Any], script_cut: dict[str, Any], *, scene_has_render_units: bool = False
) -> bool:
    changed = False
    narration = _ensure_audio_narration(cut)
    tool = str(narration.get("tool") or "").strip().lower()

    new_text = preferred_tts_text(script_cut)
    new_tts_text = preferred_tts_text(script_cut)
    if tool != "silent":
        if narration.get("text") != new_text:
            narration["text"] = new_text
            changed = True
        if narration.get("tts_text") != new_tts_text:
            narration["tts_text"] = new_tts_text
            changed = True

    image_generation = _ensure_image_generation(cut)
    visual_beat = preferred_visual_beat(script_cut)
    if visual_beat and image_generation.get("rationale") != visual_beat:
        image_generation["rationale"] = visual_beat
        changed = True

    review = _as_dict(script_cut.get("human_review"))
    image_notes = [str(v).strip() for v in _as_list(review.get("approved_image_notes")) if str(v).strip()]
    video_notes = [str(v).strip() for v in _as_list(review.get("approved_video_notes")) if str(v).strip()]
    request_ids = [str(v).strip() for v in _as_list(review.get("change_request_ids")) if str(v).strip()]
    if image_notes:
        image_generation["direction_notes"] = image_notes
        changed = True
    if video_notes and not scene_has_render_units:
        video_generation = _ensure_video_generation(cut)
        video_generation["direction_notes"] = video_notes
        changed = True
    if request_ids:
        narration["applied_request_ids"] = request_ids
        image_generation["applied_request_ids"] = request_ids
        if not scene_has_render_units:
            _ensure_video_generation(cut)["applied_request_ids"] = request_ids
        _ensure_trace(cut, request_ids=request_ids)
        changed = True
    return changed


def _materialize_location_bible(manifest_data: dict[str, Any], request_map: dict[str, dict[str, Any]]) -> int:
    assets = _ensure_manifest_assets(manifest_data)
    location_bible = _as_list(assets.get("location_bible"))
    existing_ids = {str(entry.get("location_id") or "").strip() for entry in location_bible if isinstance(entry, dict)}
    changed = 0
    for request in request_map.values():
        for action in _as_list(request.get("normalized_actions")):
            if not isinstance(action, dict) or str(action.get("action") or "") != "add_location_asset":
                continue
            payload = deepcopy(_as_dict(action.get("payload")))
            location_id = str(payload.get("location_id") or "").strip()
            if not location_id or location_id in existing_ids:
                continue
            location_bible.append(payload)
            existing_ids.add(location_id)
            changed += 1
    assets["location_bible"] = location_bible
    return changed


def _apply_scene_action(manifest_data: dict[str, Any], action: dict[str, Any]) -> bool:
    changed = False
    action_name = str(action.get("action") or "")
    target = _as_dict(action.get("target"))
    payload = deepcopy(_as_dict(action.get("payload")))
    scene_id = _normalized_id(target.get("scene_id") or payload.get("scene_id"))

    if action_name == "add_scene" and scene_id:
        if _find_scene(manifest_data, scene_id) is None:
            payload["scene_id"] = scene_id
            manifest_data.setdefault("scenes", []).append(payload)
            manifest_data["scenes"] = _sorted_scenes(_as_list(manifest_data.get("scenes")))
            changed = True
        return changed

    scene = _find_scene(manifest_data, scene_id or "")
    if scene is None:
        return False

    if action_name == "delete_scene":
        manifest_data["scenes"] = [item for item in _as_list(manifest_data.get("scenes")) if _normalized_id(_as_dict(item).get("scene_id")) != scene_id]
        return True
    if action_name == "renumber_scene":
        new_scene_id = _normalized_id(payload.get("new_scene_id"))
        if new_scene_id and scene.get("scene_id") != new_scene_id:
            _rewrite_scene_identifiers(scene, old_scene_id=scene_id, new_scene_id=new_scene_id)
            scene["scene_id"] = new_scene_id
            manifest_data["scenes"] = _sorted_scenes(_as_list(manifest_data.get("scenes")))
            return True
    if action_name == "update_scene_summary":
        summary = str(payload.get("scene_summary") or "").strip()
        if summary:
            scene["scene_summary"] = summary
            return True
    if action_name == "update_story_visual":
        visual = str(payload.get("story_visual") or "").strip()
        if visual:
            scene["story_visual"] = visual
            return True
    return False


def _default_still_output(scene_id: str, cut_id: str, asset_id: str) -> str:
    return f"assets/scenes/scene{dotted_id_slug(scene_id)}_cut{dotted_id_slug(cut_id)}_{asset_id}.png"


def _materialize_still_asset(cut: dict[str, Any], payload: dict[str, Any]) -> bool:
    still_assets = _as_list(cut.get("still_assets"))
    cut["still_assets"] = still_assets
    asset_id = str(payload.get("asset_id") or "").strip()
    if not asset_id:
        return False
    for existing in still_assets:
        if isinstance(existing, dict) and str(existing.get("asset_id") or "").strip() == asset_id:
            existing.update(deepcopy(payload))
            return True
    still_assets.append(deepcopy(payload))
    return True


def _sync_primary_image_generation_from_still_assets(cut: dict[str, Any]) -> None:
    still_assets = [item for item in _as_list(cut.get("still_assets")) if isinstance(item, dict)]
    if not still_assets:
        return
    primary = next((item for item in still_assets if str(item.get("role") or "") == "primary"), still_assets[0])
    image_generation = _ensure_image_generation(cut)
    src = _as_dict(primary.get("image_generation"))
    if src:
        for key, value in src.items():
            image_generation[key] = deepcopy(value)
    if primary.get("output"):
        image_generation["output"] = primary.get("output")
    if primary.get("reference_asset_ids"):
        image_generation["reference_asset_ids"] = deepcopy(primary.get("reference_asset_ids"))
    if primary.get("reference_usage"):
        image_generation["reference_usage"] = deepcopy(primary.get("reference_usage"))
    if primary.get("direction_notes"):
        image_generation["direction_notes"] = deepcopy(primary.get("direction_notes"))


def _apply_cut_action(manifest_data: dict[str, Any], action: dict[str, Any], request_id: str) -> bool:
    changed = False
    action_name = str(action.get("action") or "")
    target = _as_dict(action.get("target"))
    payload = deepcopy(_as_dict(action.get("payload")))
    scene_id = _normalized_id(target.get("scene_id") or payload.get("scene_id"))
    cut_id = _normalized_id(target.get("cut_id") or payload.get("cut_id"))
    if not scene_id:
        return False
    scene = _find_scene(manifest_data, scene_id)
    if scene is None:
        return False
    _ensure_scene(scene)
    scene_has_render_units = _scene_has_render_units(scene)

    if action_name == "add_cut" and cut_id:
        if _find_cut(scene, cut_id) is None:
            payload["cut_id"] = cut_id
            scene["cuts"].append(payload)
            scene["cuts"] = _sorted_cuts(_as_list(scene.get("cuts")))
            return True
        return False

    cut = _find_cut(scene, cut_id or "")
    if cut is None:
        return False

    if action_name == "delete_cut":
        scene["cuts"] = [item for item in _as_list(scene.get("cuts")) if _normalized_id(_as_dict(item).get("cut_id")) != cut_id]
        return True
    if action_name == "renumber_cut":
        new_cut_id = _normalized_id(payload.get("new_cut_id"))
        if new_cut_id and cut.get("cut_id") != new_cut_id:
            _rewrite_cut_identifiers(cut, old_cut_id=cut_id or "", new_cut_id=new_cut_id)
            cut["cut_id"] = new_cut_id
            scene["cuts"] = _sorted_cuts(_as_list(scene.get("cuts")))
            return True
        return False
    if action_name == "update_narration":
        narration = _ensure_audio_narration(cut)
        text = str(payload.get("text") or "").strip()
        tts_text = str(payload.get("tts_text") or text).strip()
        if text:
            narration["text"] = text
            narration["tts_text"] = tts_text
            changed = True
    if action_name == "clear_narration":
        narration = _ensure_audio_narration(cut)
        narration["text"] = ""
        narration["tts_text"] = ""
        changed = True
    if action_name == "set_silent_cut":
        narration = _ensure_audio_narration(cut)
        narration["tool"] = "silent"
        narration["text"] = ""
        narration["tts_text"] = ""
        narration["silence_contract"] = {
            "intentional": True,
            "kind": str(payload.get("kind") or "visual_value_hold"),
            "confirmed_by_human": True,
            "reason": str(payload.get("reason") or "human requested silent cut"),
        }
        changed = True
    if action_name == "update_visual_beat":
        image_generation = _ensure_image_generation(cut)
        value = str(payload.get("visual_beat") or "").strip()
        if value:
            image_generation["rationale"] = value
            changed = True
    if action_name == "update_scene_contract":
        current = cut.get("scene_contract")
        contract = current if isinstance(current, dict) else {}
        target_beat = str(payload.get("target_beat") or "").strip()
        must_show = payload.get("must_show")
        must_avoid = payload.get("must_avoid")
        done_when = payload.get("done_when")
        if target_beat:
            contract["target_beat"] = target_beat
            changed = True
        if isinstance(must_show, list):
            contract["must_show"] = [str(v).strip() for v in must_show if str(v).strip()]
            changed = True
        if isinstance(must_avoid, list):
            contract["must_avoid"] = [str(v).strip() for v in must_avoid if str(v).strip()]
            changed = True
        if isinstance(done_when, list):
            contract["done_when"] = [str(v).strip() for v in done_when if str(v).strip()]
            changed = True
        if contract:
            cut["scene_contract"] = contract
    if action_name in {"create_still_asset", "derive_still_asset"}:
        if "asset_id" not in payload:
            payload["asset_id"] = f"still_{dotted_id_slug(scene_id)}_{dotted_id_slug(cut_id or '0')}"
        payload.setdefault("role", "supporting" if action_name == "derive_still_asset" else "primary")
        payload.setdefault("output", _default_still_output(scene_id, cut_id or "0", str(payload["asset_id"])))
        payload.setdefault("derived_from_asset_ids", [])
        payload.setdefault("reference_asset_ids", [])
        payload.setdefault("reference_usage", [])
        payload.setdefault("direction_notes", [])
        payload.setdefault("applied_request_ids", [request_id])
        changed = _materialize_still_asset(cut, payload) or changed
        _sync_primary_image_generation_from_still_assets(cut)
    if action_name == "reference_asset":
        ref_usage = {
            "asset_id": str(payload.get("asset_id") or ""),
            "mode": str(payload.get("mode") or "same_subject"),
            "placement": str(payload.get("placement") or "midground"),
            "keep": deepcopy(_as_list(payload.get("keep"))),
            "change": deepcopy(_as_list(payload.get("change"))),
            "notes": str(payload.get("notes") or ""),
        }
        image_generation = _ensure_image_generation(cut)
        image_generation.setdefault("reference_usage", [])
        image_generation["reference_usage"].append(ref_usage)
        image_generation.setdefault("reference_asset_ids", [])
        if ref_usage["asset_id"] and ref_usage["asset_id"] not in image_generation["reference_asset_ids"]:
            image_generation["reference_asset_ids"].append(ref_usage["asset_id"])
        changed = True
    if action_name == "set_image_direction":
        image_generation = _ensure_image_generation(cut)
        notes = [str(v).strip() for v in _as_list(payload.get("notes")) if str(v).strip()]
        image_generation["direction_notes"] = notes
        changed = True
    if action_name == "set_video_direction":
        if not scene_has_render_units:
            video_generation = _ensure_video_generation(cut)
            notes = [str(v).strip() for v in _as_list(payload.get("notes")) if str(v).strip()]
            video_generation["direction_notes"] = notes
            changed = True
    if action_name == "add_object_asset":
        assets = _ensure_manifest_assets(manifest_data)
        assets.setdefault("object_bible", [])
        assets["object_bible"].append(payload)
        changed = True
    if action_name == "add_character_variant":
        assets = _ensure_manifest_assets(manifest_data)
        character_id = str(payload.get("character_id") or "")
        for entry in _as_list(assets.get("character_bible")):
            if isinstance(entry, dict) and str(entry.get("character_id") or "") == character_id:
                entry.setdefault("reference_variants", [])
                entry["reference_variants"].append(deepcopy(_as_dict(payload.get("variant"))))
                changed = True
                break

    if changed:
        narration = _ensure_audio_narration(cut)
        image_generation = _ensure_image_generation(cut)
        video_generation = cut.get("video_generation") if isinstance(cut.get("video_generation"), dict) else None
        trace_nodes: list[dict[str, Any]] = [narration, image_generation, cut]
        if video_generation is not None:
            trace_nodes.append(video_generation)
        for node in trace_nodes:
            if isinstance(node, dict):
                _ensure_trace(node, request_ids=[request_id])
        narration.setdefault("applied_request_ids", []).append(request_id)
        image_generation.setdefault("applied_request_ids", []).append(request_id)
        if video_generation is not None:
            video_generation.setdefault("applied_request_ids", []).append(request_id)
    return changed


def apply_human_change_requests(*, script_data: dict[str, Any], manifest_data: dict[str, Any]) -> int:
    request_map = _build_request_map(script_data)
    changed = 0
    changed += _materialize_location_bible(manifest_data, request_map)

    for request_id, request in request_map.items():
        for action in _as_list(request.get("normalized_actions")):
            if not isinstance(action, dict):
                continue
            action_name = str(action.get("action") or "")
            if action_name in {"add_scene", "delete_scene", "renumber_scene", "update_scene_summary", "update_story_visual"}:
                changed += int(_apply_scene_action(manifest_data, action))
            else:
                changed += int(_apply_cut_action(manifest_data, action, request_id))
    return changed


def sync_narration(*, script_path: Path, manifest_path: Path) -> tuple[int, int]:
    if yaml is None:
        raise SystemExit("PyYAML is required.")
    script_text, script_data = load_structured_document(script_path)
    manifest_text, manifest_data = load_structured_document(manifest_path)
    if not script_data or not manifest_data:
        raise SystemExit("Failed to parse script or manifest YAML.")
    if not isinstance(script_data, dict) or not isinstance(manifest_data, dict):
        raise SystemExit("Script and manifest must parse as mappings.")

    script_scene_map, script_cut_map = build_script_maps(script_data)
    updated = apply_human_change_requests(script_data=script_data, manifest_data=manifest_data)
    skipped = 0

    for scene in _as_list(manifest_data.get("scenes")):
        if not isinstance(scene, dict):
            continue
        scene_id = _normalized_id(scene.get("scene_id"))
        if not scene_id:
            continue
        script_scene = script_scene_map.get(scene_id)
        if isinstance(script_scene, dict):
            scene_review = _as_dict(script_scene.get("human_review"))
            if str(scene_review.get("approved_scene_summary") or "").strip():
                scene["scene_summary"] = str(scene_review.get("approved_scene_summary") or "").strip()
            if str(scene_review.get("approved_story_visual") or "").strip():
                scene["story_visual"] = str(scene_review.get("approved_story_visual") or "").strip()
            request_ids = [str(v).strip() for v in _as_list(scene_review.get("change_request_ids")) if str(v).strip()]
            if request_ids:
                _ensure_trace(scene, request_ids=request_ids)

        for cut in _as_list(scene.get("cuts")):
            if not isinstance(cut, dict):
                continue
            cut_id = _normalized_id(cut.get("cut_id"))
            if not cut_id:
                continue
            if _backfill_video_request_ids_from_trace(cut):
                updated += 1
            script_cut = script_cut_map.get(make_scene_cut_selector(scene_id, cut_id))
            if not isinstance(script_cut, dict):
                skipped += 1
                continue
            if _sync_human_fields_to_manifest_cut(cut, script_cut, scene_has_render_units=_scene_has_render_units(scene)):
                updated += 1
            _sync_primary_image_generation_from_still_assets(cut)
            if _ensure_story_cut_image_plan_defaults(cut):
                updated += 1
            if not _scene_has_render_units(scene) and _ensure_story_cut_video_defaults(cut, scene_id=scene_id, cut_id=cut_id, script_cut=script_cut):
                updated += 1

    manifest_data["human_change_requests"] = deepcopy(_as_list(script_data.get("human_change_requests")))
    manifest_data["scenes"] = _sorted_scenes([scene for scene in _as_list(manifest_data.get("scenes")) if isinstance(scene, dict)])
    for scene in manifest_data["scenes"]:
        scene["cuts"] = _sorted_cuts([cut for cut in _as_list(scene.get("cuts")) if isinstance(cut, dict)])

    new_yaml = yaml.safe_dump(manifest_data, allow_unicode=True, sort_keys=False, width=1000)
    manifest_path.write_text(replace_yaml_block(manifest_text, new_yaml), encoding="utf-8")
    return updated, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync script review fields and human change requests into video_manifest.md.")
    parser.add_argument("--script", required=True, help="Path to script.md")
    parser.add_argument("--manifest", required=True, help="Path to video_manifest.md")
    args = parser.parse_args()

    updated, skipped = sync_narration(script_path=Path(args.script), manifest_path=Path(args.manifest))
    print(f"updated={updated} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
