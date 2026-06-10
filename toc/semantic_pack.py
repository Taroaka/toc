from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from toc.harness import load_structured_document
from toc.semantic_review import SEMANTIC_REVIEW_STAGES


SPECIALIZED_COLLECTORS = {
    "scene_set": "toc.semantic_pack_scene",
    "scene_detail": "toc.semantic_pack_scene",
    "cut_blueprint": "toc.semantic_pack_scene",
    "asset_plan": "toc.semantic_pack_asset",
    "image_prompt": "toc.semantic_pack_image",
    "narration": "toc.semantic_pack_narration",
    "video_motion": "toc.semantic_pack_video",
}


def _data_at(data: dict[str, Any], *keys: str) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _selector(scene_id: Any, cut_id: Any) -> str:
    scene_digits = re.sub(r"\D+", "", str(scene_id))
    cut_token = str(cut_id).split("-")[-1]
    cut_digits = re.sub(r"\D+", "", cut_token)
    if not scene_digits or not cut_digits:
        return ""
    return f"scene{int(scene_digits):02d}_cut{int(cut_digits):02d}"


def load_optional_structured(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return load_structured_document(path)[1]


def load_manifest(run_dir: Path) -> dict[str, Any]:
    return load_optional_structured(run_dir / "video_manifest.md")


def _script_scenes(run_dir: Path) -> list[dict[str, Any]]:
    data = load_optional_structured(run_dir / "script.md")
    scenes = data.get("scenes") or _data_at(data, "script", "scenes") or _data_at(data, "screenplay", "scenes")
    return [scene for scene in _as_list(scenes) if isinstance(scene, dict)]


def _manifest_scenes(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [scene for scene in _as_list(manifest.get("scenes")) if isinstance(scene, dict)]


def _iter_manifest_cuts(manifest: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    cuts: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for scene in _manifest_scenes(manifest):
        for cut in _as_list(scene.get("cuts")):
            if isinstance(cut, dict):
                cuts.append((scene, cut))
    return cuts


def _first_existing(run_dir: Path, candidates: list[str]) -> str:
    for rel in candidates:
        if rel and (run_dir / rel).exists():
            return rel
    return candidates[0] if candidates else ""


def _contract_from(*blocks: Any) -> Any:
    for block in blocks:
        if isinstance(block, dict):
            for key in ("semantic_contract", "contract", "review_contract"):
                value = block.get(key)
                if value:
                    return value
            review = block.get("review")
            if isinstance(review, dict):
                value = review.get("contract") or review.get("semantic_contract")
                if value:
                    return value
    return ""


def _scene_entries(stage: str, run_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    manifest_by_id = {_as_str(scene.get("scene_id")): scene for scene in _manifest_scenes(manifest)}
    scenes = _script_scenes(run_dir) or _manifest_scenes(manifest)
    entries: list[dict[str, Any]] = []
    for index, scene in enumerate(scenes, start=1):
        scene_id = scene.get("scene_id") or scene.get("id") or index
        scene_digits = re.sub(r"\D+", "", str(scene_id))
        manifest_scene = manifest_by_id.get(_as_str(scene_id), {})
        cuts = _as_list(scene.get("cuts")) or _as_list(manifest_scene.get("cuts"))
        entry: dict[str, Any] = {
            "id": f"scene{int(scene_digits or index):02d}",
            "stage": stage,
            "source": "script.md",
            "scene_id": scene_id,
            "title": scene.get("title") or scene.get("scene_title") or manifest_scene.get("title"),
            "purpose": scene.get("purpose") or scene.get("intent") or scene.get("scene_intent"),
            "semantic_contract": _contract_from(scene, manifest_scene),
            "cut_count": len(cuts),
        }
        if stage == "scene_detail":
            entry["cuts"] = [
                {
                    "selector": _as_str(cut.get("selector")) or _selector(scene_id, cut.get("cut_id")),
                    "target_beat": cut.get("target_beat") or cut.get("beat") or cut.get("purpose"),
                    "semantic_contract": _contract_from(cut),
                }
                for cut in cuts
                if isinstance(cut, dict)
            ]
        entries.append(entry)
    return entries


def _cut_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for scene, cut in _iter_manifest_cuts(manifest):
        scene_id = scene.get("scene_id")
        cut_id = cut.get("cut_id")
        selector = _as_str(cut.get("selector")) or _selector(scene_id, cut_id)
        entries.append(
            {
                "id": selector,
                "stage": "cut_blueprint",
                "source": "video_manifest.md",
                "scene_id": scene_id,
                "cut_id": cut_id,
                "target_beat": cut.get("target_beat") or cut.get("beat") or cut.get("purpose"),
                "cut_blueprint": cut.get("cut_blueprint") or cut.get("blueprint") or cut.get("visual_plan"),
                "semantic_contract": _contract_from(cut, cut.get("image_generation"), cut.get("video_generation")),
            }
        )
    return entries


def _asset_entries(stage: str, run_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    plan = load_optional_structured(run_dir / "asset_plan.md")
    inventory = load_optional_structured(run_dir / "asset_inventory.md")
    assets = _as_list(plan.get("assets") or _data_at(plan, "asset_plan", "assets"))
    inventory_items = _as_list(_data_at(inventory, "asset_inventory", "items") or inventory.get("items"))
    inv_by_id = {_as_str(item.get("item_id") or item.get("asset_id")): item for item in inventory_items if isinstance(item, dict)}
    entries: list[dict[str, Any]] = []
    manifest_assets = _as_dict(manifest.get("assets"))
    for index, asset in enumerate([item for item in assets if isinstance(item, dict)], start=1):
        asset_id = _as_str(asset.get("asset_id") or asset.get("item_id") or f"asset_{index:02d}")
        generation_plan = _as_dict(asset.get("generation_plan"))
        output = _as_str(generation_plan.get("output") or asset.get("output"))
        entry = {
            "id": asset_id,
            "stage": stage,
            "source": "asset_plan.md",
            "category": asset.get("asset_type") or asset.get("category") or _as_dict(inv_by_id.get(asset_id)).get("category"),
            "story_purpose": asset.get("story_purpose") or _as_dict(inv_by_id.get(asset_id)).get("story_purpose"),
            "source_script_selectors": asset.get("source_script_selectors") or _as_dict(inv_by_id.get(asset_id)).get("source_script_selectors"),
            "semantic_contract": _contract_from(asset, _as_dict(asset.get("review"))),
            "output": output,
        }
        if stage == "asset_output":
            entry["output_exists"] = bool(output and (run_dir / output).exists())
            entry["contact_sheet"] = _first_existing(
                run_dir,
                [
                    "logs/review/semantic/asset_output.contact_sheet.jpg",
                    "logs/review/semantic/asset_output.contact_sheet.png",
                    "logs/review/asset_contact_sheet.jpg",
                ],
            )
            entry["manifest_asset_refs"] = json.loads(json.dumps(manifest_assets, ensure_ascii=False, default=str)) if manifest_assets else {}
        entries.append(entry)
    return entries


def _image_entries(stage: str, run_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for scene, cut in _iter_manifest_cuts(manifest):
        image_generation = _as_dict(cut.get("image_generation"))
        if not image_generation:
            continue
        selector = _as_str(cut.get("selector")) or _selector(scene.get("scene_id"), cut.get("cut_id"))
        output = _as_str(image_generation.get("output"))
        entry = {
            "id": selector,
            "stage": stage,
            "source": "video_manifest.md",
            "scene_id": scene.get("scene_id"),
            "cut_id": cut.get("cut_id"),
            "narration": _data_at(cut, "audio", "narration", "text") or _data_at(cut, "audio", "narration"),
            "prompt": image_generation.get("prompt"),
            "character_ids": image_generation.get("character_ids"),
            "object_ids": image_generation.get("object_ids"),
            "location_ids": image_generation.get("location_ids"),
            "semantic_contract": _contract_from(cut, image_generation, image_generation.get("review")),
            "output": output,
        }
        if stage == "scene_image":
            entry["output_exists"] = bool(output and (run_dir / output).exists())
            entry["contact_sheet"] = _first_existing(
                run_dir,
                [
                    "logs/review/semantic/scene_image.contact_sheet.jpg",
                    "logs/review/semantic/scene_image.contact_sheet.png",
                    "logs/review/scene_image_contact_sheet.jpg",
                ],
            )
        entries.append(entry)
    return entries


def _narration_entries(run_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    quality_report = _first_existing(
        run_dir,
        [
            "logs/review/narration_text_quality.json",
            "logs/review/narration_text_quality.md",
            "narration_text_quality_report.md",
        ],
    )
    entries: list[dict[str, Any]] = []
    for scene, cut in _iter_manifest_cuts(manifest):
        audio = _as_dict(cut.get("audio"))
        narration = _as_dict(audio.get("narration"))
        if not narration and not audio:
            continue
        selector = _as_str(cut.get("selector")) or _selector(scene.get("scene_id"), cut.get("cut_id"))
        entries.append(
            {
                "id": selector,
                "stage": "narration",
                "source": "video_manifest.md",
                "text": narration.get("text") or audio.get("narration"),
                "tts_text": narration.get("tts_text") or audio.get("tts_text"),
                "semantic_contract": _contract_from(narration, audio, cut),
                "quality_review": quality_report,
                "output": narration.get("output") or audio.get("output"),
            }
        )
    return entries


def _video_entries(stage: str, run_dir: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if stage == "render":
        outputs = [
            rel
            for rel in ("video.mp4", "final.mp4", "render.mp4", "output.mp4", "logs/render/render_report.json")
            if (run_dir / rel).exists()
        ]
        return [
            {
                "id": "render",
                "stage": "render",
                "source": "render outputs",
                "outputs": outputs,
                "clip_list": "video_clips.txt" if (run_dir / "video_clips.txt").exists() else "",
                "narration_list": "video_narration_list.txt" if (run_dir / "video_narration_list.txt").exists() else "",
                "semantic_contract": "final render should preserve approved scene/cut order, narration sync, and generated visual continuity",
            }
        ]
    entries: list[dict[str, Any]] = []
    for scene, cut in _iter_manifest_cuts(manifest):
        video_generation = _as_dict(cut.get("video_generation") or cut.get("video"))
        if not video_generation:
            continue
        selector = _as_str(cut.get("selector")) or _selector(scene.get("scene_id"), cut.get("cut_id"))
        output = _as_str(video_generation.get("output") or video_generation.get("clip_output"))
        entry = {
            "id": selector,
            "stage": stage,
            "source": "video_manifest.md",
            "motion_prompt": video_generation.get("motion_prompt") or video_generation.get("prompt"),
            "semantic_contract": _contract_from(cut, video_generation, video_generation.get("review")),
            "output": output,
        }
        if stage == "video_clip":
            entry["output_exists"] = bool(output and (run_dir / output).exists())
            entry["sampled_frames"] = [
                rel
                for rel in (
                    f"logs/review/semantic/video_clip/{selector}_frame_001.jpg",
                    f"logs/review/video_clip/{selector}_frame_001.jpg",
                )
                if (run_dir / rel).exists()
            ]
            entry["contact_sheet"] = _first_existing(
                run_dir,
                [
                    "logs/review/semantic/video_clip.contact_sheet.jpg",
                    "logs/review/semantic/video_clip.contact_sheet.png",
                ],
            )
        entries.append(entry)
    return entries


def collect_entries(stage: str, run_dir: Path, manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if stage not in SEMANTIC_REVIEW_STAGES:
        raise ValueError(f"unknown semantic review stage: {stage}")
    module_name = SPECIALIZED_COLLECTORS.get(stage)
    if module_name:
        try:
            module = __import__(module_name, fromlist=["collect_entries"])
            entries = module.collect_entries(stage, run_dir, manifest=manifest)
            if isinstance(entries, list) and (entries or stage != "cut_blueprint"):
                return entries
        except Exception:
            # Fall back to the conservative built-in collector so pack generation
            # stays available even when an optional specialized module is absent
            # or cannot parse an older run shape.
            pass
    manifest_data = manifest if manifest is not None else load_manifest(run_dir)
    if stage in {"scene_set", "scene_detail"}:
        return _scene_entries(stage, run_dir, manifest_data)
    if stage == "cut_blueprint":
        return _cut_entries(manifest_data)
    if stage == "asset_plan":
        return _asset_entries(stage, run_dir, manifest_data)
    if stage == "image_prompt":
        return _image_entries(stage, run_dir, manifest_data)
    if stage == "narration":
        return _narration_entries(run_dir, manifest_data)
    if stage == "video_motion":
        return _video_entries(stage, run_dir, manifest_data)
    return []
