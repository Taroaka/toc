#!/usr/bin/env python3
"""
Generate assets (image/video/audio) from a `video_manifest.md`.

- Image: Google Gemini Image (default: gemini-3.1-flash-image-preview)
- Video: Kling (kling_3_0 / kling_3_0_omni) or BytePlus ModelArk Seedance. Any Veo tool names are treated as Kling for safety.

Audio (TTS):
- ElevenLabs Text-to-Speech API
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.env import load_env_files
from toc.harness import load_structured_document
from toc.http import HttpError, request_bytes
from toc.immersive_manifest import (
    dotted_id_slug,
    make_scene_cut_selector,
    normalize_dotted_id,
    parse_scene_selectors,
    scene_selector_tokens,
    selector_matches,
)
from toc.providers.elevenlabs import DEFAULT_ELEVENLABS_VOICE_ID, ElevenLabsClient, ElevenLabsConfig
from toc.providers.evolink import EvoLinkClient, EvoLinkConfig
from toc.providers.gemini import GeminiClient, GeminiConfig
from toc.providers.kling import KlingClient, KlingConfig
from toc.providers.seedance import SeedanceClient, SeedanceConfig
from toc.providers.seadream import SeaDreamClient, SeaDreamConfig
from toc.run_index import write_run_index


ALLOWED_VEO_DURATIONS = (4, 6, 8)


@dataclass
class SceneSpec:
    scene_id: str
    manifest_scene_id: str
    selector: str
    kind: str | None
    reference_id: str | None
    timestamp: str | None
    duration_seconds: int | None
    still_image_plan_mode: str | None
    image_tool: str | None
    image_prompt: str | None
    image_output: str | None
    image_references: list[str]
    image_character_ids: list[str]
    image_character_ids_present: bool
    image_character_variant_ids: list[str]
    image_character_variant_ids_present: bool
    image_object_ids: list[str]
    image_object_ids_present: bool
    image_object_variant_ids: list[str]
    image_object_variant_ids_present: bool
    image_location_ids: list[str]
    image_location_ids_present: bool
    image_location_variant_ids: list[str]
    image_location_variant_ids_present: bool
    image_aspect_ratio: str | None
    image_size: str | None
    image_applied_request_ids: list[str]
    video_tool: str | None
    video_input_image: str | None
    video_first_frame: str | None
    video_last_frame: str | None
    video_motion_prompt: str | None
    video_output: str | None
    video_applied_request_ids: list[str]
    narration_tool: str | None
    narration_text: str | None
    narration_tts_text: str | None
    narration_output: str | None
    narration_normalize_to_scene_duration: bool
    narration_silence_intentional: bool
    narration_silence_confirmed_by_human: bool
    narration_silence_kind: str | None
    narration_silence_reason: str | None
    still_assets: list[dict[str, Any]]
    still_image_generation_status: str | None = None
    still_image_plan_source: str | None = None
    cut_status: str | None = None
    deletion_reason: str | None = None


@dataclass(frozen=True)
class ReferenceVariantSpec:
    variant_id: str | None
    reference_images: list[str]
    fixed_prompts: list[str]
    notes: str | None


@dataclass(frozen=True)
class PhysicalScaleSpec:
    height_cm: int | None
    body_length_cm: int | None
    shell_length_cm: int | None
    shoulder_height_cm: int | None
    silhouette_notes: list[str]


@dataclass(frozen=True)
class CharacterBibleEntry:
    character_id: str | None
    reference_images: list[str]
    reference_variants: list[ReferenceVariantSpec]
    fixed_prompts: list[str]
    physical_scale: PhysicalScaleSpec | None
    relative_scale_rules: list[str]
    review_aliases: list[str]
    notes: str | None


@dataclass(frozen=True)
class StyleGuideSpec:
    visual_style: str | None
    forbidden: list[str]
    reference_images: list[str]


@dataclass(frozen=True)
class ObjectBibleEntry:
    object_id: str | None
    kind: str | None  # setpiece|artifact|phenomenon (soft-validated)
    reference_images: list[str]
    reference_variants: list[ReferenceVariantSpec]
    fixed_prompts: list[str]
    cinematic_role: str | None
    cinematic_visual_takeaways: list[str]
    cinematic_spectacle_details: list[str]
    notes: str | None


@dataclass(frozen=True)
class LocationBibleEntry:
    location_id: str | None
    reference_images: list[str]
    reference_variants: list[ReferenceVariantSpec]
    fixed_prompts: list[str]
    review_aliases: list[str]
    notes: str | None


@dataclass(frozen=True)
class AssetGuides:
    character_bible: list[CharacterBibleEntry]
    style_guide: StyleGuideSpec | None
    object_bible: list[ObjectBibleEntry]
    location_bible: list[LocationBibleEntry]


def _as_script_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_script_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _preferred_script_visual_beat(cut: dict[str, Any]) -> str:
    review = _as_script_dict(cut.get("human_review"))
    approved = str(review.get("approved_visual_beat") or "").strip()
    visual_beat = str(cut.get("visual_beat") or "").strip()
    return approved or visual_beat


def _build_script_visual_beat_map(script_data: dict[str, Any]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for scene in _as_script_list(script_data.get("scenes")):
        if not isinstance(scene, dict):
            continue
        scene_id = normalize_dotted_id(scene.get("scene_id"))
        if not scene_id:
            continue
        for cut in _as_script_list(scene.get("cuts")):
            if not isinstance(cut, dict):
                continue
            cut_id = normalize_dotted_id(cut.get("cut_id"))
            if not cut_id:
                continue
            visual_beat = _preferred_script_visual_beat(cut)
            if visual_beat:
                mapped[make_scene_cut_selector(scene_id, cut_id)] = visual_beat
    return mapped


def _scene_request_should_prefer_script_visual_beat(scene: SceneSpec) -> bool:
    output = (scene.image_output or "").replace("\\", "/")
    if "/assets/scenes/" not in f"/{output}":
        return False
    scene_id = normalize_dotted_id(scene.manifest_scene_id or scene.scene_id or "")
    if not scene_id:
        return False
    try:
        return int(scene_id.split(".", 1)[0]) >= 7
    except ValueError:
        return False




def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


def extract_yaml_block(text: str) -> str:
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not m:
        raise SystemExit("No ```yaml ... ``` block found in manifest markdown.")
    return m.group(1)


def parse_timecode(s: str) -> int:
    s = s.strip()
    parts = s.split(":")
    if len(parts) == 2:
        mm, ss = parts
        return int(mm) * 60 + int(ss)
    if len(parts) == 3:
        hh, mm, ss = parts
        return int(hh) * 3600 + int(mm) * 60 + int(ss)
    raise ValueError(f"Unsupported timecode: {s}")


def duration_from_timestamp_range(ts_range: str | None, default_seconds: int) -> int:
    if not ts_range:
        return default_seconds
    raw = ts_range.strip().strip('"').strip("'")
    if "-" not in raw:
        return default_seconds
    start_s, end_s = raw.split("-", 1)
    try:
        start = parse_timecode(start_s)
        end = parse_timecode(end_s)
    except ValueError:
        return default_seconds
    if end <= start:
        return default_seconds
    return end - start


def _parse_yaml_scalar(value: str) -> str | None:
    v = value.strip()
    if v == "" or v.lower() == "null":
        return None
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    return v


def _ensure_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            s = str(item).strip()
            if not s:
                continue
            out.append(s)
        return out
    s = str(value).strip()
    return [s] if s else []


def _parse_inline_yaml_list(value: str) -> list[str]:
    raw = str(value).strip()
    if not raw.startswith("[") or not raw.endswith("]"):
        return []
    inner = raw[1:-1].strip()
    if not inner:
        return []
    return [x for x in [part.strip().strip('"').strip("'") for part in inner.split(",")] if x]


def _as_opt_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s.lower() in {"null", "none"}:
        return None
    return s


def _parse_reference_variants(raw_variants: Any) -> list[ReferenceVariantSpec]:
    variants: list[ReferenceVariantSpec] = []
    if not isinstance(raw_variants, list):
        return variants
    for item in raw_variants:
        if not isinstance(item, dict):
            continue
        variants.append(
            ReferenceVariantSpec(
                variant_id=_as_opt_str(item.get("variant_id")) or _as_opt_str(item.get("reference_id")),
                reference_images=_ensure_str_list(item.get("reference_images")),
                fixed_prompts=_ensure_str_list(item.get("fixed_prompts")),
                notes=_as_opt_str(item.get("notes")),
            )
        )
    return variants


def _as_opt_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _parse_physical_scale_spec(raw_scale: Any) -> PhysicalScaleSpec | None:
    if not isinstance(raw_scale, dict):
        return None
    return PhysicalScaleSpec(
        height_cm=_as_opt_int(raw_scale.get("height_cm")),
        body_length_cm=_as_opt_int(raw_scale.get("body_length_cm")),
        shell_length_cm=_as_opt_int(raw_scale.get("shell_length_cm")),
        shoulder_height_cm=_as_opt_int(raw_scale.get("shoulder_height_cm")),
        silhouette_notes=_ensure_str_list(raw_scale.get("silhouette_notes")),
    )


def _parse_assets_spec(assets: Any) -> AssetGuides:
    if not isinstance(assets, dict):
        return AssetGuides(character_bible=[], style_guide=None, object_bible=[], location_bible=[])

    # character bible
    character_bible: list[CharacterBibleEntry] = []
    raw_cb = assets.get("character_bible")
    if isinstance(raw_cb, list):
        for item in raw_cb:
            if not isinstance(item, dict):
                continue
            character_bible.append(
                CharacterBibleEntry(
                    character_id=_as_opt_str(item.get("character_id")),
                    reference_images=_ensure_str_list(item.get("reference_images")),
                    reference_variants=_parse_reference_variants(item.get("reference_variants") or item.get("variants")),
                    fixed_prompts=_ensure_str_list(item.get("fixed_prompts")),
                    physical_scale=_parse_physical_scale_spec(item.get("physical_scale")),
                    relative_scale_rules=_ensure_str_list(item.get("relative_scale_rules")),
                    review_aliases=_ensure_str_list(item.get("review_aliases")),
                    notes=_as_opt_str(item.get("notes")),
                )
            )

    # style guide
    style_guide = None
    raw_sg = assets.get("style_guide")
    if isinstance(raw_sg, dict):
        style_guide = StyleGuideSpec(
            visual_style=_as_opt_str(raw_sg.get("visual_style")),
            forbidden=_ensure_str_list(raw_sg.get("forbidden")),
            reference_images=_ensure_str_list(raw_sg.get("reference_images")),
        )

    # object / setpiece bible (optional)
    object_bible: list[ObjectBibleEntry] = []
    raw_ob = assets.get("object_bible")
    if isinstance(raw_ob, list):
        for item in raw_ob:
            if not isinstance(item, dict):
                continue
            cinematic = item.get("cinematic") if isinstance(item.get("cinematic"), dict) else {}

            role = (
                _as_opt_str(cinematic.get("role"))
                or _as_opt_str(item.get("cinematic_role"))
                or _as_opt_str(item.get("role_in_film"))
            )
            visual = _ensure_str_list(cinematic.get("visual_takeaways")) or _ensure_str_list(item.get("visual_information"))
            spectacle = _ensure_str_list(cinematic.get("spectacle_details")) or _ensure_str_list(item.get("spectacle_details"))

            object_bible.append(
                ObjectBibleEntry(
                    object_id=_as_opt_str(item.get("object_id")),
                    kind=_as_opt_str(item.get("kind")),
                    reference_images=_ensure_str_list(item.get("reference_images")),
                    reference_variants=_parse_reference_variants(item.get("reference_variants") or item.get("variants")),
                    fixed_prompts=_ensure_str_list(item.get("fixed_prompts")),
                    cinematic_role=role,
                    cinematic_visual_takeaways=visual,
                    cinematic_spectacle_details=spectacle,
                    notes=_as_opt_str(item.get("notes")),
                )
            )

    location_bible: list[LocationBibleEntry] = []
    raw_lb = assets.get("location_bible")
    if isinstance(raw_lb, list):
        for item in raw_lb:
            if not isinstance(item, dict):
                continue
            location_bible.append(
                LocationBibleEntry(
                    location_id=_as_opt_str(item.get("location_id")),
                    reference_images=_ensure_str_list(item.get("reference_images")),
                    reference_variants=_parse_reference_variants(item.get("reference_variants") or item.get("variants")),
                    fixed_prompts=_ensure_str_list(item.get("fixed_prompts")),
                    review_aliases=_ensure_str_list(item.get("review_aliases")),
                    notes=_as_opt_str(item.get("notes")),
                )
            )

    return AssetGuides(
        character_bible=character_bible,
        style_guide=style_guide,
        object_bible=object_bible,
        location_bible=location_bible,
    )


def _coerce_still_assets(raw_node: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_node, dict):
        return []
    raw_assets = raw_node.get("still_assets")
    if not isinstance(raw_assets, list):
        return []
    return [item for item in raw_assets if isinstance(item, dict)]


def _select_primary_still_asset(still_assets: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not still_assets:
        return None
    for preferred_role in ("primary", "first_frame", "reference_anchor"):
        for item in still_assets:
            if str(item.get("role") or "").strip() == preferred_role:
                return item
    return still_assets[0]


def _effective_image_generation(raw_node: dict[str, Any], still_assets: list[dict[str, Any]]) -> tuple[dict[str, Any], str | None]:
    image_generation = raw_node.get("image_generation") if isinstance(raw_node.get("image_generation"), dict) else {}
    output = _as_opt_str((image_generation or {}).get("output"))
    if image_generation:
        return image_generation, output
    primary_still = _select_primary_still_asset(still_assets)
    if not primary_still:
        return {}, None
    derived = primary_still.get("image_generation") if isinstance(primary_still.get("image_generation"), dict) else {}
    return derived, _as_opt_str(primary_still.get("output"))


def _build_human_change_request_lookup(manifest: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw_requests = manifest.get("human_change_requests")
    if not isinstance(raw_requests, list):
        return {}

    lookup: dict[str, dict[str, str]] = {}
    for raw in raw_requests:
        if not isinstance(raw, dict):
            continue
        request_id = str(raw.get("request_id") or "").strip()
        if not request_id:
            continue
        lookup[request_id] = {
            "request_id": request_id,
            "raw_request": str(raw.get("raw_request") or "").strip(),
            "resolution_notes": str(raw.get("resolution_notes") or "").strip(),
        }
    return lookup


def _resolve_source_requests(
    *,
    request_ids: list[str],
    request_lookup: dict[str, dict[str, str]],
    selector: str,
    section_name: str,
) -> list[dict[str, str]]:
    request_ids = _dedupe_keep_order(request_ids)
    resolved: list[dict[str, str]] = []
    missing: list[str] = []
    for request_id in request_ids:
        request = request_lookup.get(request_id)
        if request is None:
            missing.append(request_id)
            continue
        resolved.append(request)
    if missing:
        raise SystemExit(
            f"{selector}: unknown human change request ids in {section_name}: " + ", ".join(missing)
        )
    return resolved


def _scene_log_slug(scene: SceneSpec) -> str:
    base = scene.selector or scene.scene_id or scene.manifest_scene_id
    return dotted_id_slug(base)


def _parse_manifest_yaml_minimal(yaml_text: str) -> tuple[dict, list[SceneSpec]]:
    metadata: dict = {}
    scenes: list[SceneSpec] = []
    current: SceneSpec | None = None

    stack: list[tuple[int, str]] = []

    def push(indent: int, key: str, *, is_list_item: bool) -> None:
        nonlocal stack
        # Support both styles:
        #   scenes:
        #     - scene_id: 1   (indented sequence)
        #   scenes:
        #   - scene_id: 1     (indentless sequence; keep parent key on stack)
        while stack and (indent < stack[-1][0] or (not is_list_item and indent <= stack[-1][0])):
            stack.pop()
        stack.append((indent, key))

    lines = yaml_text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i].rstrip("\n")
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        is_list_item = stripped.startswith("- ")
        if is_list_item:
            stripped = stripped[2:].strip()

        if ":" not in stripped:
            i += 1
            continue

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        push(indent, key, is_list_item=is_list_item)
        context_keys = [k for _, k in stack]

        # Block scalar (| / >)
        if value in {"|", "|-", "|+", ">", ">-", ">+"}:
            block_lines: list[str] = []
            j = i + 1
            block_indent: int | None = None
            while j < len(lines):
                nxt = lines[j].rstrip("\n")
                if block_indent is None:
                    if nxt.strip() == "":
                        block_lines.append("")
                        j += 1
                        continue
                    block_indent = len(nxt) - len(nxt.lstrip(" "))

                nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                if nxt.strip() != "" and nxt_indent < block_indent:
                    break
                if nxt.strip() == "" and nxt_indent < block_indent:
                    break

                if nxt.strip() == "":
                    block_lines.append("")
                else:
                    block_lines.append(nxt[block_indent:])
                j += 1

            value = "\n".join(block_lines).rstrip()
            i = j
        else:
            i += 1

        # metadata
        if "video_metadata" in context_keys:
            if key in {"topic", "aspect_ratio", "resolution"}:
                metadata[key] = _parse_yaml_scalar(value)
            continue

        # new scene
        if key == "scene_id" and "scenes" in context_keys:
            if current:
                scenes.append(current)
            scene_id = normalize_dotted_id(_parse_yaml_scalar(value)) or str(len(scenes) + 1)
            current = SceneSpec(
                scene_id=scene_id,
                manifest_scene_id=scene_id,
                selector=make_scene_cut_selector(scene_id),
                kind=None,
                reference_id=None,
                timestamp=None,
                duration_seconds=None,
                still_image_plan_mode=None,
                image_tool=None,
                image_prompt=None,
                image_output=None,
                image_references=[],
                image_character_ids=[],
                image_character_ids_present=False,
                image_character_variant_ids=[],
                image_character_variant_ids_present=False,
                image_object_ids=[],
                image_object_ids_present=False,
                image_object_variant_ids=[],
                image_object_variant_ids_present=False,
                image_location_ids=[],
                image_location_ids_present=False,
                image_location_variant_ids=[],
                image_location_variant_ids_present=False,
                image_aspect_ratio=None,
                image_size=None,
                image_applied_request_ids=[],
                video_tool=None,
                video_input_image=None,
                video_first_frame=None,
                video_last_frame=None,
                video_motion_prompt=None,
                video_output=None,
                video_applied_request_ids=[],
                narration_tool=None,
                narration_text=None,
                narration_tts_text=None,
                narration_output=None,
                narration_normalize_to_scene_duration=True,
                narration_silence_intentional=False,
                narration_silence_confirmed_by_human=False,
                narration_silence_kind=None,
                narration_silence_reason=None,
                still_assets=[],
                still_image_generation_status=None,
                still_image_plan_source=None,
                cut_status=None,
                deletion_reason=None,
            )
            continue

        if not current:
            continue

        # per-scene fields
        if key == "timestamp" and "scenes" in context_keys:
            current.timestamp = _parse_yaml_scalar(value)
            continue
        if key == "kind" and "scenes" in context_keys:
            current.kind = _parse_yaml_scalar(value)
            continue
        if key in {"reference_id", "character_reference_id"} and "scenes" in context_keys:
            current.reference_id = _parse_yaml_scalar(value)
            continue
        if key == "duration_seconds" and "scenes" in context_keys:
            raw_dur = (_parse_yaml_scalar(value) or "").strip()
            if raw_dur:
                try:
                    current.duration_seconds = int(raw_dur)
                except ValueError:
                    current.duration_seconds = None
            continue
        if key == "cut_status" and "scenes" in context_keys:
            current.cut_status = _parse_yaml_scalar(value)
            continue
        if key == "deletion_reason" and "scenes" in context_keys:
            current.deletion_reason = _parse_yaml_scalar(value)
            continue

        # image generation
        if "image_generation" in context_keys:
            if key == "tool":
                current.image_tool = _parse_yaml_scalar(value)
            elif key == "prompt":
                current.image_prompt = value if "\n" in value else (_parse_yaml_scalar(value) or value)
            elif key == "output":
                current.image_output = _parse_yaml_scalar(value)
            elif key == "references":
                current.image_references = _parse_inline_yaml_list(value)
            elif key == "aspect_ratio":
                current.image_aspect_ratio = _parse_yaml_scalar(value)
            elif key == "image_size":
                current.image_size = _parse_yaml_scalar(value)
            elif key == "applied_request_ids":
                current.image_applied_request_ids = _parse_inline_yaml_list(value)
            elif key == "character_ids":
                current.image_character_ids_present = True
                current.image_character_ids = _parse_inline_yaml_list(value)
            elif key == "character_variant_ids":
                current.image_character_variant_ids_present = True
                current.image_character_variant_ids = _parse_inline_yaml_list(value)
            elif key == "object_ids":
                current.image_object_ids_present = True
                current.image_object_ids = _parse_inline_yaml_list(value)
            elif key == "object_variant_ids":
                current.image_object_variant_ids_present = True
                current.image_object_variant_ids = _parse_inline_yaml_list(value)
            elif key == "location_ids":
                current.image_location_ids_present = True
                current.image_location_ids = _parse_inline_yaml_list(value)
            elif key == "location_variant_ids":
                current.image_location_variant_ids_present = True
                current.image_location_variant_ids = _parse_inline_yaml_list(value)
            continue

        # video generation
        if "video_generation" in context_keys:
            if key == "tool":
                current.video_tool = _parse_yaml_scalar(value)
            elif key == "input_image":
                current.video_input_image = _parse_yaml_scalar(value)
            elif key == "first_frame":
                current.video_first_frame = _parse_yaml_scalar(value)
            elif key == "last_frame":
                current.video_last_frame = _parse_yaml_scalar(value)
            elif key == "duration_seconds":
                raw_dur = (_parse_yaml_scalar(value) or "").strip()
                if raw_dur:
                    try:
                        current.duration_seconds = int(raw_dur)
                    except ValueError:
                        current.duration_seconds = None
            elif key == "motion_prompt":
                current.video_motion_prompt = value if "\n" in value else (_parse_yaml_scalar(value) or value)
            elif key == "output":
                current.video_output = _parse_yaml_scalar(value)
            elif key == "applied_request_ids":
                current.video_applied_request_ids = _parse_inline_yaml_list(value)
            continue

        # narration
        if "narration" in context_keys:
            if key == "tool":
                current.narration_tool = _parse_yaml_scalar(value)
            elif key == "text":
                current.narration_text = value if "\n" in value else (_parse_yaml_scalar(value) or value)
            elif key == "tts_text":
                current.narration_tts_text = value if "\n" in value else (_parse_yaml_scalar(value) or value)
            elif key == "output":
                current.narration_output = _parse_yaml_scalar(value)
            elif key == "normalize_to_scene_duration":
                raw = (_parse_yaml_scalar(value) or "").strip().lower()
                if raw in {"false", "no", "0"}:
                    current.narration_normalize_to_scene_duration = False
            continue

    if current:
        scenes.append(current)

    return metadata, scenes


def _parse_manifest_yaml_pyyaml(yaml_text: str) -> tuple[dict, AssetGuides, list[SceneSpec]]:
    if yaml is None:  # pragma: no cover
        raise RuntimeError("PyYAML is not installed.")

    data = yaml.safe_load(yaml_text)
    if not isinstance(data, dict):
        raise ValueError("Manifest YAML must be a mapping at the root.")

    vm = data.get("video_metadata")
    metadata = {}
    if isinstance(vm, dict):
        for key in ("topic", "experience", "aspect_ratio", "resolution"):
            if key in vm:
                metadata[key] = _as_opt_str(vm.get(key))

    assets = _parse_assets_spec(data.get("assets"))

    scenes: list[SceneSpec] = []
    raw_scenes = data.get("scenes") or []
    if not isinstance(raw_scenes, list):
        raise ValueError("Manifest YAML scenes must be a list.")
    for raw_scene in raw_scenes:
        if not isinstance(raw_scene, dict):
            continue

        scene_id = normalize_dotted_id(raw_scene.get("scene_id"))
        if scene_id is None:
            continue

        timestamp = _as_opt_str(raw_scene.get("timestamp"))
        scene_kind = _as_opt_str(raw_scene.get("kind"))
        reference_id = _as_opt_str(raw_scene.get("reference_id")) or _as_opt_str(raw_scene.get("character_reference_id"))
        scene_duration_seconds: int | None = None
        duration_raw = raw_scene.get("duration_seconds")
        if duration_raw is not None:
            try:
                scene_duration_seconds = int(duration_raw)
            except Exception:
                scene_duration_seconds = None

        scene_still_assets = _coerce_still_assets(raw_scene)
        raw_cuts = raw_scene.get("cuts")
        if isinstance(raw_cuts, list) and raw_cuts:
            for idx, raw_cut in enumerate(raw_cuts, start=1):
                if not isinstance(raw_cut, dict):
                    continue

                cut_id = normalize_dotted_id(raw_cut.get("cut_id")) or str(idx)
                selector = make_scene_cut_selector(scene_id, cut_id)
                cut_still_assets = _coerce_still_assets(raw_cut)
                ig, image_output = _effective_image_generation(raw_cut, cut_still_assets)
                vg = raw_cut.get("video_generation") if isinstance(raw_cut.get("video_generation"), dict) else {}
                cut_duration_seconds: int | None = None
                cut_duration_raw = raw_cut.get("duration_seconds")
                if cut_duration_raw is not None:
                    try:
                        cut_duration_seconds = int(cut_duration_raw)
                    except Exception:
                        cut_duration_seconds = None
                if cut_duration_seconds is None and isinstance(vg, dict) and ("duration_seconds" in vg):
                    try:
                        cut_duration_seconds = int(vg.get("duration_seconds"))
                    except Exception:
                        cut_duration_seconds = None
                image_tool = _as_opt_str(ig.get("tool")) if isinstance(ig, dict) else None
                image_prompt = _as_opt_str(ig.get("prompt")) if isinstance(ig, dict) else None
                cut_still_plan = raw_cut.get("still_image_plan") if isinstance(raw_cut.get("still_image_plan"), dict) else {}
                still_image_plan_mode = _as_opt_str(cut_still_plan.get("mode")) if isinstance(cut_still_plan, dict) else None
                still_image_generation_status = _normalize_generation_status(cut_still_plan.get("generation_status")) if isinstance(cut_still_plan, dict) else None
                still_image_plan_source = _as_opt_str(cut_still_plan.get("source")) if isinstance(cut_still_plan, dict) else None
                cut_status = _as_opt_str(raw_cut.get("cut_status"))
                deletion_reason = _as_opt_str(raw_cut.get("deletion_reason"))
                image_references = _ensure_str_list(ig.get("references")) if isinstance(ig, dict) else []
                image_character_ids_present = isinstance(ig, dict) and ("character_ids" in ig)
                image_character_ids = _ensure_str_list(ig.get("character_ids")) if isinstance(ig, dict) else []
                image_character_variant_ids_present = isinstance(ig, dict) and ("character_variant_ids" in ig)
                image_character_variant_ids = _ensure_str_list(ig.get("character_variant_ids")) if isinstance(ig, dict) else []
                image_object_ids_present = isinstance(ig, dict) and ("object_ids" in ig)
                image_object_ids = _ensure_str_list(ig.get("object_ids")) if isinstance(ig, dict) else []
                image_object_variant_ids_present = isinstance(ig, dict) and ("object_variant_ids" in ig)
                image_object_variant_ids = _ensure_str_list(ig.get("object_variant_ids")) if isinstance(ig, dict) else []
                image_location_ids_present = isinstance(ig, dict) and ("location_ids" in ig)
                image_location_ids = _ensure_str_list(ig.get("location_ids")) if isinstance(ig, dict) else []
                image_location_variant_ids_present = isinstance(ig, dict) and ("location_variant_ids" in ig)
                image_location_variant_ids = _ensure_str_list(ig.get("location_variant_ids")) if isinstance(ig, dict) else []
                image_aspect_ratio = _as_opt_str(ig.get("aspect_ratio")) if isinstance(ig, dict) else None
                image_size = _as_opt_str(ig.get("image_size")) if isinstance(ig, dict) else None
                image_applied_request_ids = _ensure_str_list(ig.get("applied_request_ids")) if isinstance(ig, dict) else []

                video_tool = _as_opt_str(vg.get("tool")) if isinstance(vg, dict) else None
                video_input_image = _as_opt_str(vg.get("input_image")) if isinstance(vg, dict) else None
                video_first_frame = _as_opt_str(vg.get("first_frame")) if isinstance(vg, dict) else None
                video_last_frame = _as_opt_str(vg.get("last_frame")) if isinstance(vg, dict) else None
                video_motion_prompt = _as_opt_str(vg.get("motion_prompt")) if isinstance(vg, dict) else None
                video_output = _as_opt_str(vg.get("output")) if isinstance(vg, dict) else None
                video_applied_request_ids = _ensure_str_list(vg.get("applied_request_ids")) if isinstance(vg, dict) else []

                narration_tool = None
                narration_text = None
                narration_tts_text = None
                narration_output = None
                narration_normalize = True
                narration_silence_intentional = False
                narration_silence_confirmed_by_human = False
                narration_silence_kind = None
                narration_silence_reason = None

                audio = raw_cut.get("audio")
                narration = None
                if isinstance(audio, dict):
                    narration = audio.get("narration")
                if narration is None:
                    narration = raw_cut.get("narration")
                if isinstance(narration, dict):
                    narration_tool = _as_opt_str(narration.get("tool"))
                    narration_text = _as_opt_str(narration.get("text"))
                    narration_tts_text = _as_opt_str(narration.get("tts_text"))
                    narration_output = _as_opt_str(narration.get("output"))
                    (
                        narration_silence_intentional,
                        narration_silence_confirmed_by_human,
                        narration_silence_kind,
                        narration_silence_reason,
                    ) = _silence_contract_fields(narration)
                    normalize_raw = narration.get("normalize_to_scene_duration")
                    if isinstance(normalize_raw, bool):
                        narration_normalize = bool(normalize_raw)
                    else:
                        normalize_s = _as_opt_str(normalize_raw)
                        if normalize_s and normalize_s.strip().lower() in {"false", "no", "0"}:
                            narration_normalize = False

                scenes.append(
                    SceneSpec(
                        scene_id=selector,
                        manifest_scene_id=scene_id,
                        selector=selector,
                        kind=scene_kind,
                        reference_id=reference_id,
                        timestamp=timestamp,
                        duration_seconds=cut_duration_seconds if cut_duration_seconds is not None else scene_duration_seconds,
                        still_image_plan_mode=still_image_plan_mode,
                        image_tool=image_tool,
                        image_prompt=image_prompt,
                        image_output=image_output,
                        image_references=image_references,
                        image_character_ids=image_character_ids,
                        image_character_ids_present=image_character_ids_present,
                        image_character_variant_ids=image_character_variant_ids,
                        image_character_variant_ids_present=image_character_variant_ids_present,
                        image_object_ids=image_object_ids,
                        image_object_ids_present=image_object_ids_present,
                        image_object_variant_ids=image_object_variant_ids,
                        image_object_variant_ids_present=image_object_variant_ids_present,
                        image_location_ids=image_location_ids,
                        image_location_ids_present=image_location_ids_present,
                        image_location_variant_ids=image_location_variant_ids,
                        image_location_variant_ids_present=image_location_variant_ids_present,
                        image_aspect_ratio=image_aspect_ratio,
                        image_size=image_size,
                        image_applied_request_ids=image_applied_request_ids,
                        video_tool=video_tool,
                        video_input_image=video_input_image,
                        video_first_frame=video_first_frame,
                        video_last_frame=video_last_frame,
                        video_motion_prompt=video_motion_prompt,
                        video_output=video_output,
                        video_applied_request_ids=video_applied_request_ids,
                        narration_tool=narration_tool,
                        narration_text=narration_text,
                        narration_tts_text=narration_tts_text,
                        narration_output=narration_output,
                        narration_normalize_to_scene_duration=narration_normalize,
                        narration_silence_intentional=narration_silence_intentional,
                        narration_silence_confirmed_by_human=narration_silence_confirmed_by_human,
                        narration_silence_kind=narration_silence_kind,
                        narration_silence_reason=narration_silence_reason,
                        still_assets=cut_still_assets,
                        still_image_generation_status=still_image_generation_status,
                        still_image_plan_source=still_image_plan_source,
                        cut_status=cut_status,
                        deletion_reason=deletion_reason,
                    )
                )
            continue

        ig, image_output = _effective_image_generation(raw_scene, scene_still_assets)
        vg = raw_scene.get("video_generation") if isinstance(raw_scene.get("video_generation"), dict) else {}
        if scene_duration_seconds is None and isinstance(vg, dict) and ("duration_seconds" in vg):
            try:
                scene_duration_seconds = int(vg.get("duration_seconds"))
            except Exception:
                scene_duration_seconds = None

        image_tool = _as_opt_str(ig.get("tool")) if isinstance(ig, dict) else None
        image_prompt = _as_opt_str(ig.get("prompt")) if isinstance(ig, dict) else None
        scene_still_plan = raw_scene.get("still_image_plan") if isinstance(raw_scene.get("still_image_plan"), dict) else {}
        still_image_plan_mode = _as_opt_str(scene_still_plan.get("mode")) if isinstance(scene_still_plan, dict) else None
        still_image_generation_status = _normalize_generation_status(scene_still_plan.get("generation_status")) if isinstance(scene_still_plan, dict) else None
        still_image_plan_source = _as_opt_str(scene_still_plan.get("source")) if isinstance(scene_still_plan, dict) else None
        cut_status = _as_opt_str(raw_scene.get("cut_status"))
        deletion_reason = _as_opt_str(raw_scene.get("deletion_reason"))
        image_references = _ensure_str_list(ig.get("references")) if isinstance(ig, dict) else []
        image_character_ids_present = isinstance(ig, dict) and ("character_ids" in ig)
        image_character_ids = _ensure_str_list(ig.get("character_ids")) if isinstance(ig, dict) else []
        image_character_variant_ids_present = isinstance(ig, dict) and ("character_variant_ids" in ig)
        image_character_variant_ids = _ensure_str_list(ig.get("character_variant_ids")) if isinstance(ig, dict) else []
        image_object_ids_present = isinstance(ig, dict) and ("object_ids" in ig)
        image_object_ids = _ensure_str_list(ig.get("object_ids")) if isinstance(ig, dict) else []
        image_object_variant_ids_present = isinstance(ig, dict) and ("object_variant_ids" in ig)
        image_object_variant_ids = _ensure_str_list(ig.get("object_variant_ids")) if isinstance(ig, dict) else []
        image_location_ids_present = isinstance(ig, dict) and ("location_ids" in ig)
        image_location_ids = _ensure_str_list(ig.get("location_ids")) if isinstance(ig, dict) else []
        image_location_variant_ids_present = isinstance(ig, dict) and ("location_variant_ids" in ig)
        image_location_variant_ids = _ensure_str_list(ig.get("location_variant_ids")) if isinstance(ig, dict) else []
        image_aspect_ratio = _as_opt_str(ig.get("aspect_ratio")) if isinstance(ig, dict) else None
        image_size = _as_opt_str(ig.get("image_size")) if isinstance(ig, dict) else None
        image_applied_request_ids = _ensure_str_list(ig.get("applied_request_ids")) if isinstance(ig, dict) else []

        video_tool = _as_opt_str(vg.get("tool")) if isinstance(vg, dict) else None
        video_input_image = _as_opt_str(vg.get("input_image")) if isinstance(vg, dict) else None
        video_first_frame = _as_opt_str(vg.get("first_frame")) if isinstance(vg, dict) else None
        video_last_frame = _as_opt_str(vg.get("last_frame")) if isinstance(vg, dict) else None
        video_motion_prompt = _as_opt_str(vg.get("motion_prompt")) if isinstance(vg, dict) else None
        video_output = _as_opt_str(vg.get("output")) if isinstance(vg, dict) else None
        video_applied_request_ids = _ensure_str_list(vg.get("applied_request_ids")) if isinstance(vg, dict) else []

        # narration can be nested under audio.narration or directly under narration (legacy)
        narration_tool = None
        narration_text = None
        narration_tts_text = None
        narration_output = None
        narration_normalize = True
        narration_silence_intentional = False
        narration_silence_confirmed_by_human = False
        narration_silence_kind = None
        narration_silence_reason = None

        audio = raw_scene.get("audio")
        narration = None
        if isinstance(audio, dict):
            narration = audio.get("narration")
        if narration is None:
            narration = raw_scene.get("narration")
        if isinstance(narration, dict):
            narration_tool = _as_opt_str(narration.get("tool"))
            narration_text = _as_opt_str(narration.get("text"))
            narration_tts_text = _as_opt_str(narration.get("tts_text"))
            narration_output = _as_opt_str(narration.get("output"))
            (
                narration_silence_intentional,
                narration_silence_confirmed_by_human,
                narration_silence_kind,
                narration_silence_reason,
            ) = _silence_contract_fields(narration)
            normalize_raw = narration.get("normalize_to_scene_duration")
            if isinstance(normalize_raw, bool):
                narration_normalize = bool(normalize_raw)
            else:
                normalize_s = _as_opt_str(normalize_raw)
                if normalize_s and normalize_s.strip().lower() in {"false", "no", "0"}:
                    narration_normalize = False

        scenes.append(
            SceneSpec(
                scene_id=scene_id,
                manifest_scene_id=scene_id,
                selector=make_scene_cut_selector(scene_id),
                kind=scene_kind,
                reference_id=reference_id,
                timestamp=timestamp,
                duration_seconds=scene_duration_seconds,
                still_image_plan_mode=still_image_plan_mode,
                image_tool=image_tool,
                image_prompt=image_prompt,
                image_output=image_output,
                image_references=image_references,
                image_character_ids=image_character_ids,
                image_character_ids_present=image_character_ids_present,
                image_character_variant_ids=image_character_variant_ids,
                image_character_variant_ids_present=image_character_variant_ids_present,
                image_object_ids=image_object_ids,
                image_object_ids_present=image_object_ids_present,
                image_object_variant_ids=image_object_variant_ids,
                image_object_variant_ids_present=image_object_variant_ids_present,
                image_location_ids=image_location_ids,
                image_location_ids_present=image_location_ids_present,
                image_location_variant_ids=image_location_variant_ids,
                image_location_variant_ids_present=image_location_variant_ids_present,
                image_aspect_ratio=image_aspect_ratio,
                image_size=image_size,
                image_applied_request_ids=image_applied_request_ids,
                video_tool=video_tool,
                video_input_image=video_input_image,
                video_first_frame=video_first_frame,
                video_last_frame=video_last_frame,
                video_motion_prompt=video_motion_prompt,
                video_output=video_output,
                video_applied_request_ids=video_applied_request_ids,
                narration_tool=narration_tool,
                narration_text=narration_text,
                narration_tts_text=narration_tts_text,
                narration_output=narration_output,
                narration_normalize_to_scene_duration=narration_normalize,
                narration_silence_intentional=narration_silence_intentional,
                narration_silence_confirmed_by_human=narration_silence_confirmed_by_human,
                narration_silence_kind=narration_silence_kind,
                narration_silence_reason=narration_silence_reason,
                still_assets=scene_still_assets,
                still_image_generation_status=still_image_generation_status,
                still_image_plan_source=still_image_plan_source,
                cut_status=cut_status,
                deletion_reason=deletion_reason,
            )
        )

    return metadata, assets, scenes


def parse_manifest_yaml_full(yaml_text: str) -> tuple[dict, AssetGuides, list[SceneSpec]]:
    try:
        return _parse_manifest_yaml_pyyaml(yaml_text)
    except Exception:
        metadata, scenes = _parse_manifest_yaml_minimal(yaml_text)
        return metadata, AssetGuides(character_bible=[], style_guide=None, object_bible=[], location_bible=[]), scenes


def parse_manifest_yaml(yaml_text: str) -> tuple[dict, list[SceneSpec]]:
    metadata, _, scenes = parse_manifest_yaml_full(yaml_text)
    return metadata, scenes


def _scene_matches_filter(scene: SceneSpec, scene_filter: set[str] | None) -> bool:
    return selector_matches(
        scene_selector_tokens(
            operational_scene_id=scene.scene_id,
            manifest_scene_id=scene.manifest_scene_id,
            reference_id=scene.reference_id,
        ),
        scene_filter,
    )


def _scene_is_deleted(scene: SceneSpec) -> bool:
    return (scene.cut_status or "").strip().lower() == "deleted"


def _should_generate_story_still_by_plan(scene: SceneSpec, allowed_modes: set[str]) -> bool:
    mode = (scene.still_image_plan_mode or "").strip().lower()
    if not mode:
        return False
    return mode in allowed_modes


def _normalize_generation_status(value: Any) -> str | None:
    raw = _as_opt_str(value)
    if not raw:
        return None
    normalized = raw.strip().lower()
    if normalized in {"missing", "created", "recreate"}:
        return normalized
    return None


def _effective_still_generation_status(scene: SceneSpec, *, base_dir: Path) -> str:
    explicit = _normalize_generation_status(scene.still_image_generation_status)
    if explicit:
        return explicit
    outp = resolve_path(base_dir, scene.image_output) if scene.image_output else None
    if outp and outp.exists():
        return "created"
    if (scene.still_image_plan_mode or "").strip().lower() == "no_dedicated_still":
        return "created"
    return "missing"


def _should_generate_image_scene(scene: SceneSpec, *, allowed_story_modes: set[str], base_dir: Path) -> bool:
    if not scene.image_output or not scene.image_prompt:
        return False
    outp = resolve_path(base_dir, scene.image_output)
    if outp and (_is_character_ref_path(outp) or _is_object_ref_path(outp)):
        return True
    explicit_status = _normalize_generation_status(scene.still_image_generation_status)
    if explicit_status == "created":
        return False
    if explicit_status in {"missing", "recreate"}:
        return True
    return _should_generate_story_still_by_plan(scene, allowed_story_modes)


def _archive_existing_image_for_recreate(*, out_path: Path, base_dir: Path, test_image_dir: str) -> Path | None:
    if not out_path.exists():
        return None
    archive_dir = resolve_path(base_dir, test_image_dir) or (base_dir / "assets/test")
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    archived = archive_dir / f"{out_path.stem}__recreate_backup_{timestamp}{out_path.suffix}"
    shutil.move(str(out_path), str(archived))
    return archived


def _dedupe_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        s = str(item).strip()
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _scene_selector(scene: SceneSpec) -> str:
    return str(scene.selector or make_scene_cut_selector(scene.scene_id))


def _normalized_ref_key(value: str | None) -> str:
    return str(value or "").replace("\\", "/").strip()


def _build_image_scene_dependencies(scenes: list[SceneSpec]) -> dict[str, set[str]]:
    output_to_selector: dict[str, str] = {}
    for scene in scenes:
        output_key = _normalized_ref_key(scene.image_output)
        if output_key:
            output_to_selector[output_key] = _scene_selector(scene)

    deps: dict[str, set[str]] = {}
    for scene in scenes:
        selector = _scene_selector(scene)
        scene_output_key = _normalized_ref_key(scene.image_output)
        scene_deps: set[str] = set()
        for ref in scene.image_references or []:
            ref_key = _normalized_ref_key(ref)
            if not ref_key or ref_key == scene_output_key:
                continue
            dep_selector = output_to_selector.get(ref_key)
            if dep_selector:
                scene_deps.add(dep_selector)
        deps[selector] = scene_deps
    return deps


def _resolve_image_reference_paths(
    *,
    base_dir: Path,
    reference_strings: list[str],
    output_ref: str | None,
    archived_self_reference_path: Path | None,
    test_image_dir: str | None,
    dry_run: bool,
    scene_selector: str,
) -> list[Path]:
    refs: list[Path] = []
    output_ref_norm = str(output_ref or "").strip()
    for ref_str in reference_strings or []:
        ref_norm = str(ref_str or "").strip()
        if not ref_norm:
            continue
        ref_path = resolve_path(base_dir, ref_norm)
        if not ref_path:
            continue
        if not dry_run and not ref_path.exists():
            if archived_self_reference_path and output_ref_norm and ref_norm == output_ref_norm:
                refs.append(archived_self_reference_path)
                continue
            if output_ref_norm and ref_norm == output_ref_norm:
                archive_dir = resolve_path(base_dir, test_image_dir or "assets/test") or (base_dir / "assets/test")
                candidates = sorted(archive_dir.glob(f"{Path(output_ref_norm).stem}__recreate_backup_*{Path(output_ref_norm).suffix}"))
                if candidates:
                    refs.append(candidates[-1])
                    continue
            raise SystemExit(f"{scene_selector}: reference image not found: {ref_path}")
        refs.append(ref_path)
    return refs


def _generate_single_image_scene(
    *,
    scene: SceneSpec,
    base_dir: Path,
    aspect_ratio: str,
    args: Any,
    char_views: set[str],
    log_dir: Path,
    gemini_client: GeminiClient | None,
    seadream_client: SeaDreamClient | None,
) -> None:
    tool = normalize_tool_name(scene.image_tool)
    out_path = resolve_path(base_dir, scene.image_output)
    if not out_path:
        raise SystemExit(f"scene{scene.scene_id}: missing image output path")
    generation_status = _effective_still_generation_status(scene, base_dir=base_dir)
    archived_self_reference_path: Path | None = None
    if generation_status == "recreate" and args.force and not args.dry_run:
        archived_self_reference_path = _archive_existing_image_for_recreate(
            out_path=out_path,
            base_dir=base_dir,
            test_image_dir=args.test_image_dir,
        )

    scene_aspect_ratio = scene.image_aspect_ratio or aspect_ratio
    scene_image_size = scene.image_size or args.image_size

    refs = _resolve_image_reference_paths(
        base_dir=base_dir,
        reference_strings=list(scene.image_references or []),
        output_ref=scene.image_output,
        archived_self_reference_path=archived_self_reference_path,
        test_image_dir=args.test_image_dir,
        dry_run=bool(args.dry_run),
        scene_selector=str(scene.selector or scene.scene_id),
    )

    is_char_ref = bool(out_path and _is_character_ref_path(out_path))

    if tool in {"google_nanobanana_2", "nanobanana_2"}:
        prefix = (args.image_prompt_prefix or "").strip()
        suffix = (args.image_prompt_suffix or "").strip()
        prompt = scene.image_prompt.strip()
        if prefix:
            prompt = prefix + "\n\n" + prompt
        if suffix:
            prompt = prompt + "\n\n" + suffix

        if is_char_ref and (char_views or args.character_reference_strip):
            views_to_generate = [v for v in ("front", "side", "back") if (v == "front" or v in char_views)]
            if "front" not in views_to_generate:
                views_to_generate.insert(0, "front")

            view_paths: dict[str, Path] = {"front": out_path}
            for v in ("side", "back"):
                if v in views_to_generate:
                    view_paths[v] = _derive_character_view_path(out_path, v)

            front_prompt = _character_view_prompt(prompt, "front")
            if args.log_prompts:
                log_dir.mkdir(parents=True, exist_ok=True)
                (log_dir / f"scene{scene.scene_id}_image_prompt.txt").write_text(front_prompt + "\n", encoding="utf-8")
            generate_gemini_image(
                client=gemini_client,
                model=args.gemini_image_model,
                prompt=front_prompt,
                aspect_ratio=scene_aspect_ratio,
                image_size=scene_image_size,
                reference_images=refs,
                out_path=view_paths["front"],
                force=args.force,
                log_path=log_dir / f"scene{scene.scene_id}_image.json",
                dry_run=args.dry_run,
            )

            conditioned_refs = list(refs)
            if view_paths["front"] not in conditioned_refs:
                conditioned_refs.append(view_paths["front"])

            for v in ("side", "back"):
                if v not in view_paths:
                    continue
                vprompt = _character_view_prompt(prompt, v)
                if args.log_prompts:
                    log_dir.mkdir(parents=True, exist_ok=True)
                    (log_dir / f"scene{scene.scene_id}_image_prompt_{v}.txt").write_text(vprompt + "\n", encoding="utf-8")
                generate_gemini_image(
                    client=gemini_client,
                    model=args.gemini_image_model,
                    prompt=vprompt,
                    aspect_ratio=scene_aspect_ratio,
                    image_size=scene_image_size,
                    reference_images=conditioned_refs,
                    out_path=view_paths[v],
                    force=args.force,
                    log_path=log_dir / f"scene{scene.scene_id}_image_{v}.json",
                    dry_run=args.dry_run,
                )

            if args.character_reference_strip and all(k in view_paths for k in ("front", "side", "back")):
                strip_path = _derive_character_refstrip_path(out_path, args.character_reference_strip_suffix)
                if not args.dry_run:
                    _ffmpeg_hstack_images(
                        [view_paths["front"], view_paths["side"], view_paths["back"]],
                        strip_path,
                        force=args.force,
                    )
                else:
                    print(f"[dry-run] IMAGE {strip_path} <- hstack(front,side,back)")
            return

        if args.log_prompts:
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / f"scene{scene.scene_id}_image_prompt.txt").write_text(prompt + "\n", encoding="utf-8")
        generate_gemini_image(
            client=gemini_client,
            model=args.gemini_image_model,
            prompt=prompt,
            aspect_ratio=scene_aspect_ratio,
            image_size=scene_image_size,
            reference_images=refs,
            out_path=out_path,
            force=args.force,
            log_path=log_dir / f"scene{scene.scene_id}_image.json",
            dry_run=args.dry_run,
        )
        if args.test_image_variants > 0:
            for variant_index in range(1, args.test_image_variants + 1):
                variant_out = _derive_test_variant_output_path(
                    base_dir,
                    scene.image_output,
                    variant_index,
                    args.test_image_dir,
                )
                if variant_out is None:
                    continue
                if args.log_prompts:
                    log_dir.mkdir(parents=True, exist_ok=True)
                    (log_dir / f"scene{scene.scene_id}_image_prompt_test_v{variant_index:02d}.txt").write_text(
                        prompt + "\n",
                        encoding="utf-8",
                    )
                generate_gemini_image(
                    client=gemini_client,
                    model=args.gemini_image_model,
                    prompt=prompt,
                    aspect_ratio=scene_aspect_ratio,
                    image_size=scene_image_size,
                    reference_images=refs,
                    out_path=variant_out,
                    force=args.force,
                    log_path=log_dir / f"scene{scene.scene_id}_image_test_v{variant_index:02d}.json",
                    dry_run=args.dry_run,
                )
        return

    if tool in {"seadream", "seedream", "seedream_4_5", "byteplus_seedream_4_5"}:
        base_prompt = scene.image_prompt.strip()
        if is_char_ref and (char_views or args.character_reference_strip):
            views_to_generate = [v for v in ("front", "side", "back") if (v == "front" or v in char_views)]
            if "front" not in views_to_generate:
                views_to_generate.insert(0, "front")
            view_paths: dict[str, Path] = {"front": out_path}
            for v in ("side", "back"):
                if v in views_to_generate:
                    view_paths[v] = _derive_character_view_path(out_path, v)

            for v in views_to_generate:
                vprompt = _character_view_prompt(base_prompt, v)
                if args.log_prompts:
                    log_dir.mkdir(parents=True, exist_ok=True)
                    suffix_name = "" if v == "front" else f"_{v}"
                    (log_dir / f"scene{scene.scene_id}_image_prompt{suffix_name}.txt").write_text(vprompt + "\n", encoding="utf-8")
                generate_seadream_image(
                    client=seadream_client,
                    model=args.seadream_model,
                    prompt=vprompt,
                    size=args.seadream_size,
                    out_path=view_paths[v],
                    force=args.force,
                    log_path=log_dir / f"scene{scene.scene_id}_image{'' if v == 'front' else '_' + v}.json",
                    dry_run=args.dry_run,
                )

            if args.character_reference_strip and all(k in view_paths for k in ("front", "side", "back")):
                strip_path = _derive_character_refstrip_path(out_path, args.character_reference_strip_suffix)
                if not args.dry_run:
                    _ffmpeg_hstack_images(
                        [view_paths["front"], view_paths["side"], view_paths["back"]],
                        strip_path,
                        force=args.force,
                    )
                else:
                    print(f"[dry-run] IMAGE {strip_path} <- hstack(front,side,back)")
            return

        if args.log_prompts:
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / f"scene{scene.scene_id}_image_prompt.txt").write_text(base_prompt + "\n", encoding="utf-8")
        generate_seadream_image(
            client=seadream_client,
            model=args.seadream_model,
            prompt=base_prompt,
            size=args.seadream_size,
            out_path=out_path,
            force=args.force,
            log_path=log_dir / f"scene{scene.scene_id}_image.json",
            dry_run=args.dry_run,
        )
        if args.test_image_variants > 0:
            for variant_index in range(1, args.test_image_variants + 1):
                variant_out = _derive_test_variant_output_path(
                    base_dir,
                    scene.image_output,
                    variant_index,
                    args.test_image_dir,
                )
                if variant_out is None:
                    continue
                if args.log_prompts:
                    log_dir.mkdir(parents=True, exist_ok=True)
                    (log_dir / f"scene{scene.scene_id}_image_prompt_test_v{variant_index:02d}.txt").write_text(
                        base_prompt + "\n",
                        encoding="utf-8",
                    )
                generate_seadream_image(
                    client=seadream_client,
                    model=args.seadream_model,
                    prompt=base_prompt,
                    size=args.seadream_size,
                    out_path=variant_out,
                    force=args.force,
                    log_path=log_dir / f"scene{scene.scene_id}_image_test_v{variant_index:02d}.json",
                    dry_run=args.dry_run,
                )
        return

    raise SystemExit(f"scene{scene.scene_id}: unsupported image tool: {scene.image_tool}")


def _generate_image_scenes_with_dependencies(
    *,
    image_scenes: list[SceneSpec],
    image_max_concurrency: int,
    base_dir: Path,
    aspect_ratio: str,
    args: Any,
    char_views: set[str],
    log_dir: Path,
    gemini_client: GeminiClient | None,
    seadream_client: SeaDreamClient | None,
) -> None:
    if not image_scenes:
        return
    deps = _build_image_scene_dependencies(image_scenes)
    pending: dict[str, SceneSpec] = { _scene_selector(scene): scene for scene in image_scenes }
    completed: set[str] = set()
    in_flight: dict[Any, str] = {}

    with ThreadPoolExecutor(max_workers=image_max_concurrency) as executor:
        while pending or in_flight:
            ready = [
                (selector, scene)
                for selector, scene in pending.items()
                if deps.get(selector, set()).issubset(completed)
            ]
            while ready and len(in_flight) < image_max_concurrency:
                selector, scene = ready.pop(0)
                future = executor.submit(
                    _generate_single_image_scene,
                    scene=scene,
                    base_dir=base_dir,
                    aspect_ratio=aspect_ratio,
                    args=args,
                    char_views=char_views,
                    log_dir=log_dir,
                    gemini_client=gemini_client,
                    seadream_client=seadream_client,
                )
                in_flight[future] = selector
                pending.pop(selector, None)

            if not in_flight:
                blocked = {
                    selector: sorted(deps.get(selector, set()) - completed)
                    for selector in pending
                }
                raise SystemExit(
                    "image generation dependency cycle or unresolved selected references:\n- "
                    + "\n- ".join(f"{selector}: waits for {waiting}" for selector, waiting in blocked.items())
                )

            done, _ = wait(list(in_flight.keys()), return_when=FIRST_COMPLETED)
            for future in done:
                selector = in_flight.pop(future)
                future.result()
                completed.add(selector)


def _merge_refs(existing: list[str], extra: list[str], *, exclude: str | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def add_one(v: str) -> None:
        s = str(v).strip()
        if not s:
            return
        if exclude and s == exclude:
            return
        if s in seen:
            return
        seen.add(s)
        out.append(s)

    for v in existing or []:
        add_one(v)
    for v in extra or []:
        add_one(v)
    return out


_HEADING_ALIASES: dict[str, list[str]] = {
    # Keep canonical English keys for code, but accept Japanese headings in prompts/templates.
    "GLOBAL / INVARIANTS": ["GLOBAL / INVARIANTS", "全体 / 不変条件", "全体/不変条件", "グローバル / 不変条件"],
    "CHARACTERS": ["CHARACTERS", "登場人物", "キャラクター"],
    "PROPS / SETPIECES": ["PROPS / SETPIECES", "小道具 / 舞台装置", "小道具/舞台装置", "プロップ / 舞台装置"],
    "SCENE": ["SCENE", "シーン", "場面"],
    "CONTINUITY": ["CONTINUITY", "連続性", "つながり"],
    "AVOID": ["AVOID", "禁止", "避けること", "NG"],
}

_HEADING_JA_LABEL: dict[str, str] = {
    "GLOBAL / INVARIANTS": "全体 / 不変条件",
    "CHARACTERS": "登場人物",
    "PROPS / SETPIECES": "小道具 / 舞台装置",
    "SCENE": "シーン",
    "CONTINUITY": "連続性",
    "AVOID": "禁止",
}


def _find_heading_line_index(lines: list[str], heading: str) -> int | None:
    candidates = _HEADING_ALIASES.get(heading, [heading])
    targets = {f"[{h}]" for h in candidates}
    for i, line in enumerate(lines):
        if line.strip() in targets:
            return i
    return None


def _inject_lines_under_heading(prompt: str, heading: str, lines_to_add: list[str]) -> str:
    if not prompt:
        prompt = ""
    lines = prompt.splitlines()
    existing = {ln.strip() for ln in lines}
    to_add = [ln.strip() for ln in lines_to_add if str(ln).strip() and str(ln).strip() not in existing]
    if not to_add:
        return prompt

    idx = _find_heading_line_index(lines, heading)
    if idx is None:
        # No structured heading: append a new section at the end.
        label = _HEADING_JA_LABEL.get(heading, heading)
        suffix = "\n".join([f"[{label}]", *to_add])
        if prompt.strip() == "":
            return suffix
        return (prompt.rstrip() + "\n\n" + suffix).rstrip()

    insert_at = idx + 1
    lines[insert_at:insert_at] = to_add
    return "\n".join(lines).rstrip()


def _asset_guides_character_refs_to_add(guides: AssetGuides, mode: str) -> list[str]:
    mode_norm = (mode or "").strip().lower()
    if mode_norm == "none":
        return []
    if mode_norm == "scene":
        return []
    if mode_norm == "all":
        refs: list[str] = []
        for entry in guides.character_bible:
            refs.extend(_default_reference_images(entry.reference_images, entry.reference_variants))
        return _dedupe_keep_order(refs)

    # auto: only apply when there's exactly one character entry (avoids accidentally mixing multiple identities)
    if len(guides.character_bible) == 1:
        entry = guides.character_bible[0]
        return _dedupe_keep_order(_default_reference_images(entry.reference_images, entry.reference_variants))
    return []


def _selected_reference_variants(
    reference_variants: list[ReferenceVariantSpec], selected_variant_ids: set[str]
) -> list[ReferenceVariantSpec]:
    if not selected_variant_ids:
        return []
    return [variant for variant in (reference_variants or []) if variant.variant_id in selected_variant_ids]


def _default_reference_images(reference_images: list[str], reference_variants: list[ReferenceVariantSpec]) -> list[str]:
    if reference_images:
        return list(reference_images)
    if len(reference_variants or []) == 1:
        return list(reference_variants[0].reference_images or [])
    return []


def _default_active_reference_variants(reference_images: list[str], reference_variants: list[ReferenceVariantSpec]) -> list[ReferenceVariantSpec]:
    if reference_images:
        return []
    if len(reference_variants or []) == 1:
        return [reference_variants[0]]
    return []


def _all_reference_images(reference_images: list[str], reference_variants: list[ReferenceVariantSpec]) -> list[str]:
    refs = list(reference_images or [])
    for variant in reference_variants or []:
        refs.extend(variant.reference_images or [])
    return _dedupe_keep_order(refs)


def _format_physical_scale_lines(entry: CharacterBibleEntry) -> list[str]:
    scale = entry.physical_scale
    if not scale:
        return []

    subject = entry.character_id or "character"
    dims: list[str] = []
    if scale.height_cm is not None:
        dims.append(f"身長約{scale.height_cm}cm")
    if scale.body_length_cm is not None:
        dims.append(f"全長約{scale.body_length_cm}cm")
    if scale.shell_length_cm is not None:
        dims.append(f"甲長約{scale.shell_length_cm}cm")
    if scale.shoulder_height_cm is not None:
        dims.append(f"肩高約{scale.shoulder_height_cm}cm")

    lines: list[str] = []
    if dims:
        lines.append(f"{subject} の体格固定: " + "、".join(dims) + "。")
    for note in scale.silhouette_notes or []:
        lines.append(f"{subject} の体格補足: {note}")
    return lines


def _expand_character_bible_with_existing_refstrips(
    *,
    guides: AssetGuides,
    base_dir: Path,
    strip_suffix: str,
) -> AssetGuides:
    expanded_cb: list[CharacterBibleEntry] = []
    for entry in guides.character_bible or []:
        refs = _dedupe_keep_order(list(entry.reference_images or []))
        extra: list[str] = []
        for ref in refs:
            ref_p = Path(ref)
            if "assets" not in ref_p.parts or "characters" not in ref_p.parts:
                continue
            strip_rel = _derive_character_refstrip_path(ref_p, strip_suffix)
            strip_abs = resolve_path(base_dir, str(strip_rel))
            if strip_abs and strip_abs.exists():
                extra.append(str(strip_rel))

        expanded_variants: list[ReferenceVariantSpec] = []
        for variant in entry.reference_variants or []:
            variant_refs = _dedupe_keep_order(list(variant.reference_images or []))
            variant_extra: list[str] = []
            for ref in variant_refs:
                ref_p = Path(ref)
                if "assets" not in ref_p.parts or "characters" not in ref_p.parts:
                    continue
                strip_rel = _derive_character_refstrip_path(ref_p, strip_suffix)
                strip_abs = resolve_path(base_dir, str(strip_rel))
                if strip_abs and strip_abs.exists():
                    variant_extra.append(str(strip_rel))
            expanded_variants.append(
                ReferenceVariantSpec(
                    variant_id=variant.variant_id,
                    reference_images=_dedupe_keep_order(variant_refs + variant_extra),
                    fixed_prompts=list(variant.fixed_prompts or []),
                    notes=variant.notes,
                )
            )

        expanded_cb.append(
            CharacterBibleEntry(
                character_id=entry.character_id,
                reference_images=_dedupe_keep_order(refs + extra),
                reference_variants=expanded_variants,
                fixed_prompts=list(entry.fixed_prompts or []),
                physical_scale=entry.physical_scale,
                relative_scale_rules=list(entry.relative_scale_rules or []),
                review_aliases=list(entry.review_aliases or []),
                notes=entry.notes,
            )
        )
    return AssetGuides(
        character_bible=expanded_cb,
        style_guide=guides.style_guide,
        object_bible=guides.object_bible,
        location_bible=guides.location_bible,
    )


def merge_asset_references_into_scene(*, scene: SceneSpec, guides: AssetGuides, character_refs_mode: str) -> None:
    style_refs = guides.style_guide.reference_images if guides.style_guide else []
    # Preserve explicit scene references as-authored, including self-references used for edit-style regeneration.
    explicit_refs = _dedupe_keep_order(list(scene.image_references or []))
    merged_refs = list(explicit_refs)
    merged_refs = _merge_refs(merged_refs, _merge_refs([], style_refs, exclude=scene.image_output))

    mode_norm = (character_refs_mode or "").strip().lower()
    selected_character_variant_ids = set(scene.image_character_variant_ids or [])
    selected_object_variant_ids = set(scene.image_object_variant_ids or [])
    selected_location_variant_ids = set(scene.image_location_variant_ids or [])

    if mode_norm == "scene":
        chosen_character_ids = set(scene.image_character_ids or [])
        char_refs: list[str] = []
        for entry in guides.character_bible or []:
            selected_variants = _selected_reference_variants(entry.reference_variants, selected_character_variant_ids)
            if selected_variants:
                for variant in selected_variants:
                    char_refs.extend(variant.reference_images or [])
                continue
            if chosen_character_ids and entry.character_id in chosen_character_ids:
                char_refs.extend(_default_reference_images(entry.reference_images, entry.reference_variants))
        merged_refs = _merge_refs(merged_refs, _merge_refs([], _dedupe_keep_order(char_refs), exclude=scene.image_output))
    else:
        merged_refs = _merge_refs(
            merged_refs,
            _merge_refs([], _asset_guides_character_refs_to_add(guides, character_refs_mode), exclude=scene.image_output),
        )

    chosen_object_ids = set(scene.image_object_ids or [])
    obj_refs: list[str] = []
    if chosen_object_ids or selected_object_variant_ids:
        for entry in (guides.object_bible or []):
            selected_variants = _selected_reference_variants(entry.reference_variants, selected_object_variant_ids)
            if selected_variants:
                for variant in selected_variants:
                    obj_refs.extend(variant.reference_images or [])
                continue
            if chosen_object_ids and entry.object_id in chosen_object_ids:
                obj_refs.extend(_default_reference_images(entry.reference_images, entry.reference_variants))
    merged_refs = _merge_refs(merged_refs, _merge_refs([], _dedupe_keep_order(obj_refs), exclude=scene.image_output))

    chosen_location_ids = set(scene.image_location_ids or [])
    location_refs: list[str] = []
    if chosen_location_ids or selected_location_variant_ids:
        for entry in (guides.location_bible or []):
            selected_variants = _selected_reference_variants(entry.reference_variants, selected_location_variant_ids)
            if selected_variants:
                for variant in selected_variants:
                    location_refs.extend(variant.reference_images or [])
                continue
            if chosen_location_ids and entry.location_id in chosen_location_ids:
                location_refs.extend(_default_reference_images(entry.reference_images, entry.reference_variants))
    scene.image_references = _merge_refs(
        merged_refs,
        _merge_refs([], _dedupe_keep_order(location_refs), exclude=scene.image_output),
    )


def apply_asset_guides_to_scene(*, scene: SceneSpec, guides: AssetGuides, character_refs_mode: str) -> None:
    """
    Mutates scene in-place:
    - merges assets.* reference images into scene.image_references
    - injects assets.* prompt lines into scene.image_prompt (best-effort; uses headings when present)

    This is an opt-in helper intended to reduce per-scene copy/paste while keeping prompts structured.
    """

    merge_asset_references_into_scene(scene=scene, guides=guides, character_refs_mode=character_refs_mode)

    # prompt injection
    if not scene.image_prompt:
        return

    prompt = scene.image_prompt
    merged_refs = list(scene.image_references or [])
    mode_norm = (character_refs_mode or "").strip().lower()
    selected_character_variant_ids = set(scene.image_character_variant_ids or [])
    selected_object_variant_ids = set(scene.image_object_variant_ids or [])

    global_lines: list[str] = []
    if guides.style_guide and guides.style_guide.visual_style:
        global_lines.append(guides.style_guide.visual_style)

    avoid_lines: list[str] = []
    if guides.style_guide and guides.style_guide.forbidden:
        avoid_lines.extend(guides.style_guide.forbidden)

    # Inject character fixed prompts only when that character is "active" for the scene:
    # - either its reference images are used, or this scene is generating that reference image.
    char_lines: list[str] = []
    active_character_entries: list[CharacterBibleEntry] = []
    ref_set = set(merged_refs)
    chosen_ids = set(scene.image_character_ids or [])
    for entry in guides.character_bible or []:
        selected_variants = _selected_reference_variants(entry.reference_variants, selected_character_variant_ids)
        if mode_norm == "scene" and chosen_ids:
            is_active = entry.character_id in chosen_ids
        else:
            is_active = any(ref in ref_set for ref in _all_reference_images(entry.reference_images, entry.reference_variants))
        if not is_active and selected_variants:
            is_active = True
        if not is_active and scene.image_output and scene.image_output in _all_reference_images(
            entry.reference_images, entry.reference_variants
        ):
            is_active = True
        if is_active:
            active_character_entries.append(entry)
        if is_active and entry.fixed_prompts:
            char_lines.extend(entry.fixed_prompts)
        active_variants = selected_variants or _default_active_reference_variants(entry.reference_images, entry.reference_variants)
        if is_active:
            for variant in active_variants:
                char_lines.extend(variant.fixed_prompts or [])
            char_lines.extend(_format_physical_scale_lines(entry))

    if len(active_character_entries) >= 2:
        for entry in active_character_entries:
            char_lines.extend(entry.relative_scale_rules or [])

    # Inject object/setpiece prompts only when that object is active for the scene.
    prop_lines: list[str] = []
    for entry in guides.object_bible or []:
        selected_variants = _selected_reference_variants(entry.reference_variants, selected_object_variant_ids)
        is_active = entry.object_id in chosen_object_ids
        if not is_active:
            is_active = any(ref in ref_set for ref in _all_reference_images(entry.reference_images, entry.reference_variants))
        if not is_active and selected_variants:
            is_active = True
        if not is_active and scene.image_output and scene.image_output in _all_reference_images(
            entry.reference_images, entry.reference_variants
        ):
            is_active = True
        if not is_active:
            continue

        if entry.fixed_prompts:
            prop_lines.extend(entry.fixed_prompts)
        active_variants = selected_variants or _default_active_reference_variants(entry.reference_images, entry.reference_variants)
        for variant in active_variants:
            prop_lines.extend(variant.fixed_prompts or [])
        if entry.cinematic_role:
            prop_lines.append(f"映画での役割: {entry.cinematic_role}")
        for v in entry.cinematic_visual_takeaways or []:
            prop_lines.append(f"映像から伝える情報: {v}")
        for s in entry.cinematic_spectacle_details or []:
            prop_lines.append(f"見せ場ディテール: {s}")

    if global_lines:
        prompt = _inject_lines_under_heading(prompt, "GLOBAL / INVARIANTS", global_lines)
    if char_lines:
        prompt = _inject_lines_under_heading(prompt, "CHARACTERS", char_lines)
    if prop_lines:
        prompt = _inject_lines_under_heading(prompt, "PROPS / SETPIECES", prop_lines)
    if avoid_lines:
        prompt = _inject_lines_under_heading(prompt, "AVOID", avoid_lines)

    scene.image_prompt = prompt


def validate_scene_character_ids(
    *, scenes: list[SceneSpec], require: bool, mode: str, scene_filter: set[str] | None
) -> None:
    if not require:
        return
    if (mode or "").strip().lower() != "scene":
        return
    for scene in scenes:
        if not _scene_matches_filter(scene, scene_filter):
            continue
        if not scene.image_output or not scene.image_prompt:
            continue
        if not scene.image_character_ids_present:
            raise SystemExit(
                f"scene{scene.scene_id}: missing image_generation.character_ids. "
                "For B-roll scenes, set an explicit empty list: character_ids: []."
            )


def validate_scene_object_ids(
    *, scenes: list[SceneSpec], guides: AssetGuides, require: bool, scene_filter: set[str] | None
) -> None:
    if not require:
        return
    if not guides.object_bible:
        return
    for scene in scenes:
        if not _scene_matches_filter(scene, scene_filter):
            continue
        if not scene.image_output or not scene.image_prompt:
            continue
        if not scene.image_object_ids_present:
            raise SystemExit(
                f"scene{scene.scene_id}: missing image_generation.object_ids. "
                "For scenes with no props/setpieces, set an explicit empty list: object_ids: []."
            )


def _build_reference_variant_index(
    entries: list[Any], *, entry_kind: str, entry_id_attr: str
) -> dict[str, str | None]:
    issues: list[str] = []
    index: dict[str, str | None] = {}
    for entry in entries:
        entry_id = getattr(entry, entry_id_attr, None)
        for variant in getattr(entry, "reference_variants", []) or []:
            variant_id = _as_opt_str(getattr(variant, "variant_id", None))
            if not variant_id:
                issues.append(f"{entry_kind} {entry_id or '<unknown>'}: reference_variants[].variant_id is required.")
                continue
            if not getattr(variant, "reference_images", None):
                issues.append(f"{entry_kind} {entry_id or '<unknown>'}:{variant_id}: reference_images is required and must be non-empty.")
            if variant_id in index:
                issues.append(f"{entry_kind} variant_id must be unique across assets.{entry_kind}_bible: {variant_id}")
                continue
            index[variant_id] = entry_id
    if issues:
        raise SystemExit(f"assets.{entry_kind}_bible invalid:\n- " + "\n- ".join(issues))
    return index


def validate_character_bible(*, guides: AssetGuides) -> None:
    issues: list[str] = []
    for entry in guides.character_bible or []:
        entry_id = entry.character_id or "<unknown>"
        scale = entry.physical_scale
        if scale is None:
            continue
        if (
            scale.height_cm is None
            and scale.body_length_cm is None
            and scale.shell_length_cm is None
            and scale.shoulder_height_cm is None
            and not (scale.silhouette_notes or [])
        ):
            issues.append(
                f"{entry_id}: physical_scale must include at least one measurement or silhouette_notes."
            )
    if issues:
        raise SystemExit("assets.character_bible invalid:\n- " + "\n- ".join(issues))


def validate_scene_reference_variant_ids(
    *, scenes: list[SceneSpec], guides: AssetGuides, require: bool, scene_filter: set[str] | None
) -> None:
    if not require:
        return

    character_variant_index = _build_reference_variant_index(
        guides.character_bible, entry_kind="character", entry_id_attr="character_id"
    )
    object_variant_index = _build_reference_variant_index(
        guides.object_bible, entry_kind="object", entry_id_attr="object_id"
    )

    for scene in scenes:
        if not _scene_matches_filter(scene, scene_filter):
            continue

        unknown_character_variants = [
            variant_id for variant_id in (scene.image_character_variant_ids or []) if variant_id not in character_variant_index
        ]
        if unknown_character_variants:
            raise SystemExit(
                f"scene{scene.scene_id}: unknown character_variant_ids: {sorted(set(unknown_character_variants))}"
            )

        unknown_object_variants = [
            variant_id for variant_id in (scene.image_object_variant_ids or []) if variant_id not in object_variant_index
        ]
        if unknown_object_variants:
            raise SystemExit(f"scene{scene.scene_id}: unknown object_variant_ids: {sorted(set(unknown_object_variants))}")

        chosen_character_ids = set(scene.image_character_ids or [])
        if chosen_character_ids:
            mismatched_character_variants = sorted(
                {
                    variant_id
                    for variant_id in (scene.image_character_variant_ids or [])
                    if character_variant_index.get(variant_id) not in chosen_character_ids
                }
            )
            if mismatched_character_variants:
                raise SystemExit(
                    f"scene{scene.scene_id}: character_variant_ids do not match image_generation.character_ids: "
                    f"{mismatched_character_variants}"
                )

        chosen_object_ids = set(scene.image_object_ids or [])
        if chosen_object_ids:
            mismatched_object_variants = sorted(
                {
                    variant_id
                    for variant_id in (scene.image_object_variant_ids or [])
                    if object_variant_index.get(variant_id) not in chosen_object_ids
                }
            )
            if mismatched_object_variants:
                raise SystemExit(
                    f"scene{scene.scene_id}: object_variant_ids do not match image_generation.object_ids: "
                    f"{mismatched_object_variants}"
                )


def validate_scene_narration(
    *, scenes: list[SceneSpec], require: bool, scene_filter: set[str] | None
) -> None:
    if not require:
        return
    for scene in scenes:
        if not _scene_matches_filter(scene, scene_filter):
            continue
        if _scene_is_deleted(scene):
            continue
        # Narration is required only for scenes/cuts that participate in video generation.
        if not scene.video_tool and not scene.video_output:
            continue

        if not scene.narration_output:
            raise SystemExit(
                f"scene{scene.scene_id}: missing audio.narration.output (required). "
                "To intentionally generate assets without narration, pass --skip-audio."
            )

        tool = normalize_tool_name(scene.narration_tool)
        if not tool:
            raise SystemExit(
                f"scene{scene.scene_id}: missing audio.narration.tool (required). "
                "To intentionally generate assets without narration, pass --skip-audio."
            )

        narration_source = scene.narration_tts_text or scene.narration_text
        if tool == "silent":
            if not scene.narration_silence_intentional or not scene.narration_silence_confirmed_by_human:
                raise SystemExit(
                    f"scene{scene.scene_id}: silent narration requires "
                    "audio.narration.silence_contract.intentional=true and confirmed_by_human=true."
                )
            if not scene.narration_silence_kind or not scene.narration_silence_reason:
                raise SystemExit(
                    f"scene{scene.scene_id}: silent narration requires "
                    "audio.narration.silence_contract.kind and reason."
                )
            continue
        if tool == "elevenlabs" and not (narration_source and narration_source.strip()):
            raise SystemExit(
                f"scene{scene.scene_id}: missing audio.narration.tts_text/text for ElevenLabs (required). "
                'For intentionally silent cuts, use audio.narration.tool: "silent" with text: "".'
            )


def validate_object_reference_scenes(*, scenes: list[SceneSpec], guides: AssetGuides, require: bool) -> None:
    if not require:
        return
    if not guides.object_bible:
        return

    outputs = {str(s.image_output) for s in scenes if s.image_output}

    missing_required: list[str] = []
    missing_outputs: list[str] = []
    for entry in guides.object_bible or []:
        if not entry.object_id:
            missing_required.append("object_id is required (found null/empty).")
            continue
        all_refs = _all_reference_images(entry.reference_images, entry.reference_variants)
        if not all_refs:
            missing_required.append(
                f"{entry.object_id}: reference_images or reference_variants[].reference_images is required and must be non-empty."
            )
        has_any_fixed_prompts = bool(entry.fixed_prompts) or any(variant.fixed_prompts for variant in entry.reference_variants or [])
        if not has_any_fixed_prompts:
            missing_required.append(
                f"{entry.object_id}: fixed_prompts or reference_variants[].fixed_prompts is required and must be non-empty."
            )

        for ref in all_refs:
            if ref not in outputs:
                missing_outputs.append(f"{entry.object_id}:{ref}")

    if missing_required:
        raise SystemExit("assets.object_bible invalid:\n- " + "\n- ".join(missing_required))
    if missing_outputs:
        raise SystemExit(
            "Missing object reference scenes: each assets.object_bible[].reference_images path must be generated "
            "by some scenes[].image_generation.output.\n- " + "\n- ".join(missing_outputs)
        )


def _guess_image_suffix(mime_type: str | None) -> str:
    if not mime_type:
        return ".bin"
    mt = mime_type.lower()
    if mt == "image/png":
        return ".png"
    if mt == "image/jpeg":
        return ".jpg"
    if mt == "image/webp":
        return ".webp"
    return ".bin"


def generate_macos_say_tts(
    *,
    text: str,
    out_path: Path,
    voice: str | None,
    force: bool,
    dry_run: bool,
) -> None:
    if out_path.exists() and not force:
        return
    if dry_run:
        v = f" voice={voice}" if (voice or "").strip() else ""
        print(f"[dry-run] AUDIO {out_path} <- macos_say{v}")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="toc_say_") as td:
        td_p = Path(td)
        aiff = td_p / "tts.aiff"
        cmd = ["say", "-o", str(aiff)]
        if (voice or "").strip():
            cmd += ["-v", str(voice).strip()]
        cmd.append(text)
        try:
            subprocess.run(cmd, check=True)
        except FileNotFoundError as e:  # pragma: no cover
            raise SystemExit("macOS 'say' command not found (this tool is macOS-only).") from e

        # Convert to mp3 for downstream compatibility (render-video.sh expects mp3 by default).
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y" if force else "-n",
                    "-i",
                    str(aiff),
                    "-vn",
                    "-ar",
                    "44100",
                    "-b:a",
                    "128k",
                    str(out_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError as e:  # pragma: no cover
            raise SystemExit("ffmpeg not found (required to convert macos_say output to mp3).") from e


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _parse_csv_set(value: str | None) -> set[str]:
    if not value:
        return set()
    items = []
    for part in str(value).split(","):
        s = part.strip().lower()
        if not s:
            continue
        items.append(s)
    return set(items)


def _is_character_ref_path(path: Path) -> bool:
    try:
        return path.parent.name == "characters" and path.parent.parent.name == "assets"
    except Exception:
        return False


def _is_object_ref_path(path: Path) -> bool:
    try:
        return path.parent.name == "objects" and path.parent.parent.name == "assets"
    except Exception:
        return False


def _derive_character_view_path(front_path: Path, view: str) -> Path:
    """
    Derive a sibling filename for a character reference view.

    Supports both:
    - protagonist.png -> protagonist_side.png / protagonist_back.png
    - protagonist_front.png -> protagonist_side.png / protagonist_back.png
    """
    view = (view or "").strip().lower()
    if view == "front":
        return front_path

    suffix = front_path.suffix or ".png"
    stem = front_path.stem
    if stem.endswith("_front"):
        root = stem[: -len("_front")]
        return front_path.with_name(f"{root}_{view}{suffix}")
    if stem.endswith(f"_{view}"):
        return front_path
    return front_path.with_name(f"{stem}_{view}{suffix}")


def _derive_character_refstrip_path(front_path: Path, strip_suffix: str) -> Path:
    suffix = front_path.suffix or ".png"
    stem = front_path.stem
    root = stem
    for v in ("_front", "_side", "_back"):
        if root.endswith(v):
            root = root[: -len(v)]
            break
    return front_path.with_name(f"{root}{strip_suffix}{suffix}")


def _is_character_refstrip_path(path: Path, strip_suffix: str) -> bool:
    if not _is_character_ref_path(path):
        return False
    suff = (strip_suffix or "").strip()
    if not suff:
        return False
    return path.stem.endswith(suff)


def _ffmpeg_hstack_images(inputs: list[Path], out_path: Path, *, force: bool) -> None:
    if out_path.exists() and not force:
        return
    if len(inputs) < 2:
        raise ValueError("hstack requires at least 2 inputs")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-hide_banner", "-y"]
    for p in inputs:
        cmd += ["-i", str(p)]
    cmd += [
        "-filter_complex",
        f"hstack=inputs={len(inputs)}",
        "-frames:v",
        "1",
        "-update",
        "1",
        str(out_path),
    ]
    _run(cmd)


def _character_view_prompt(base_prompt: str, view: str) -> str:
    view_norm = (view or "").strip().lower()
    if view_norm not in {"front", "side", "back"}:
        return base_prompt

    if view_norm == "front":
        view_lines = [
            "キャラクター参照画像: 正面（FRONT）ビュー。",
            "全身（頭からつま先まで）を入れる。足先が切れない（クロップしない）。",
            "ニュートラルな姿勢。腕は自然に下ろす。中央構図。背景はクリーンで無地。",
        ]
    elif view_norm == "side":
        view_lines = [
            "キャラクター参照画像: 左側面（LEFT SIDE）ビュー。",
            "全身（頭からつま先まで）を入れる。足先が切れない（クロップしない）。",
            "ニュートラルな姿勢。中央構図。背景はクリーンで無地。",
        ]
    else:  # back
        view_lines = [
            "キャラクター参照画像: 背面（BACK）ビュー。",
            "全身（頭からつま先まで）を入れる。足先が切れない（クロップしない）。",
            "ニュートラルな姿勢。中央構図。背景はクリーンで無地。",
        ]

    # Prefer structured injection under [SCENE]; fall back to appending.
    return _inject_lines_under_heading(base_prompt, "SCENE", view_lines)


def _ffmpeg_write_silence_mp3(out_path: Path, duration_seconds: int, force: bool) -> None:
    if out_path.exists() and not force:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            str(duration_seconds),
            "-q:a",
            "9",
            "-acodec",
            "libmp3lame",
            str(out_path),
        ]
    )


def _ffmpeg_normalize_mp3(src_path: Path, out_path: Path, duration_seconds: int | None, force: bool) -> None:
    if out_path.exists() and not force:
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(src_path),
        "-ar",
        "44100",
        "-ac",
        "1",
        "-b:a",
        "128k",
        "-codec:a",
        "libmp3lame",
    ]
    if duration_seconds is not None:
        cmd += ["-af", "apad", "-t", str(duration_seconds)]
    cmd.append(str(out_path))
    _run(cmd)


def generate_elevenlabs_tts(
    *,
    client: ElevenLabsClient | None,
    voice_id: str,
    model_id: str,
    output_format: str,
    text: str,
    out_path: Path,
    duration_seconds: int | None,
    force: bool,
    request_log_path: Path | None,
    dry_run: bool,
) -> None:
    if out_path.exists() and not force:
        return

    payload: dict = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.35,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }

    if request_log_path:
        request_log_path.parent.mkdir(parents=True, exist_ok=True)
        request_log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if dry_run:
        print(f"[dry-run] AUDIO {out_path} <- elevenlabs voice={voice_id} model={model_id} fmt={output_format}")
        return

    if client is None:
        raise SystemExit("ElevenLabs client not configured (missing ELEVENLABS_API_KEY).")

    try:
        audio = client.tts(
            text=text,
            voice_id=voice_id,
            model_id=model_id,
            output_format=output_format,
            voice_settings=payload["voice_settings"],
        )
    except HttpError as e:
        raise SystemExit(str(e)) from e

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(audio)

    try:
        try:
            _ffmpeg_normalize_mp3(tmp_path, out_path, duration_seconds, force=True)
        except FileNotFoundError:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(audio)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def _plan_veo_segments(desired_seconds: int) -> tuple[list[int], int | None]:
    """
    Return (segments, trim_to_seconds).

    Veo only supports a small discrete set of durations per request; if the desired duration
    isn't directly supported, we generate multiple segments and trim the concatenation.
    """
    if desired_seconds <= 0:
        return [6], 6

    if desired_seconds in ALLOWED_VEO_DURATIONS:
        return [desired_seconds], None

    limit = desired_seconds + max(ALLOWED_VEO_DURATIONS)
    best: dict[int, list[int]] = {0: []}
    for total in range(limit + 1):
        if total not in best:
            continue
        for d in ALLOWED_VEO_DURATIONS:
            nxt = total + d
            if nxt > limit:
                continue
            cand = best[total] + [d]
            if nxt not in best or len(cand) < len(best[nxt]):
                best[nxt] = cand

    best_total = None
    best_segments: list[int] | None = None
    for total in range(desired_seconds, limit + 1):
        segs = best.get(total)
        if not segs:
            continue
        if best_total is None:
            best_total = total
            best_segments = segs
            continue
        overshoot = total - desired_seconds
        best_overshoot = best_total - desired_seconds
        if overshoot < best_overshoot:
            best_total = total
            best_segments = segs
        elif overshoot == best_overshoot and best_segments is not None and len(segs) < len(best_segments):
            best_total = total
            best_segments = segs

    if not best_segments:
        return [6], desired_seconds

    if best_total == desired_seconds:
        return best_segments, None
    return best_segments, desired_seconds


def _ffmpeg_concat_videos(inputs: list[Path], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        list_path = Path(tmpdir) / "concat.txt"
        lines = [f"file '{p.as_posix()}'" for p in inputs]
        list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-c",
                "copy",
                str(out_path),
            ]
        )


def _ffmpeg_trim_video(src: Path, out_path: Path, duration_seconds: int) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(src),
            "-t",
            str(duration_seconds),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(out_path),
        ]
    )


def _ffmpeg_extract_frame_from_end(src: Path, out_path: Path, *, seconds_from_end: float, force: bool) -> None:
    if out_path.exists() and not force:
        return
    # ffmpeg can fail to output any frame if we seek *too* close to EOF.
    # For 24fps content, 1 frame ~= 0.0417s; treat that as "last frame" in practice.
    min_seek = 1.0 / 24.0
    if seconds_from_end <= 0:
        seconds_from_end = min_seek
    if seconds_from_end < min_seek:
        seconds_from_end = min_seek
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-sseof",
            f"-{seconds_from_end}",
            "-i",
            str(src),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(out_path),
        ]
    )


def _ffmpeg_extract_frame_from_end_best_effort(
    src: Path, out_path: Path, *, seconds_from_end: float, force: bool
) -> Path:
    """
    Extract a "near end" frame reliably.

    ffmpeg can exit 0 but still write an empty file if the seek is too close to EOF.
    We retry with progressively larger offsets.
    """
    if out_path.exists() and not force and out_path.stat().st_size > 0:
        return out_path

    min_seek = 1.0 / 24.0
    candidates: list[float] = [max(float(seconds_from_end), min_seek)]
    candidates += [min_seek, 0.05, 0.1, 0.25, 0.5, 1.0]

    last_err: Exception | None = None
    for sec in candidates:
        try:
            _ffmpeg_extract_frame_from_end(src, out_path, seconds_from_end=sec, force=True)
            if out_path.exists() and out_path.stat().st_size > 0:
                return out_path
            try:
                out_path.unlink(missing_ok=True)
            except Exception:
                pass
        except Exception as e:
            last_err = e
            try:
                out_path.unlink(missing_ok=True)
            except Exception:
                pass
            continue

    if last_err:
        raise last_err
    raise SystemExit(f"Failed to extract chaining frame from: {src}")


def generate_gemini_image(
    *,
    client: GeminiClient | None,
    model: str,
    prompt: str,
    aspect_ratio: str,
    image_size: str,
    reference_images: list[Path] | None,
    out_path: Path,
    force: bool,
    log_path: Path | None,
    dry_run: bool,
) -> None:
    if out_path.exists() and not force:
        return

    if dry_run:
        print(f"[dry-run] IMAGE {out_path} <- {model} ({aspect_ratio}, {image_size})")
        return

    if client is None:
        raise SystemExit("Gemini client not configured (missing GEMINI_API_KEY).")

    try:
        image_bytes, mime_type, resp = client.generate_image(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            image_size=image_size,
            reference_images=reference_images,
            model=model,
        )
    except (HttpError, ValueError) as e:
        raise SystemExit(str(e)) from e

    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        redacted = json.loads(json.dumps(resp))
        # redact base64 payloads
        for cand in redacted.get("candidates", []) or []:
            for part in (cand.get("content", {}) or {}).get("parts", []) or []:
                inline = part.get("inlineData") or part.get("inline_data")
                if inline and "data" in inline:
                    inline["data"] = f"<redacted {len(inline['data'])} chars>"
        log_path.write_text(json.dumps(redacted, ensure_ascii=False, indent=2), encoding="utf-8")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = _guess_image_suffix(mime_type)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(image_bytes)

    try:
        try:
            _run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-y",
                    "-i",
                    str(tmp_path),
                    "-frames:v",
                    "1",
                    "-update",
                    "1",
                    str(out_path),
                ]
            )
        except FileNotFoundError:
            out_path.write_bytes(image_bytes)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def generate_seadream_image(
    *,
    client: SeaDreamClient | None,
    model: str,
    prompt: str,
    size: str,
    out_path: Path,
    force: bool,
    log_path: Path | None,
    dry_run: bool,
) -> None:
    if out_path.exists() and not force:
        return

    if dry_run:
        print(f"[dry-run] IMAGE {out_path} <- {model} (size={size})")
        return

    if client is None:
        raise SystemExit("SeaDream client not configured (missing SEADREAM_API_KEY).")

    try:
        image_bytes, mime_type, resp = client.generate_image(prompt=prompt, size=size, model=model)
    except (HttpError, ValueError) as e:
        raise SystemExit(str(e)) from e

    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        redacted = json.loads(json.dumps(resp))
        for item in redacted.get("data", []) or []:
            if isinstance(item, dict) and "b64_json" in item:
                item["b64_json"] = "<redacted>"
        log_path.write_text(json.dumps(redacted, ensure_ascii=False, indent=2), encoding="utf-8")

    out_path.parent.mkdir(parents=True, exist_ok=True)

    mime_type = mime_type or "image/png"
    suffix = _guess_image_suffix(mime_type)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(image_bytes)

    try:
        try:
            _run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-y",
                    "-i",
                    str(tmp_path),
                    "-frames:v",
                    "1",
                    "-update",
                    "1",
                    str(out_path),
                ]
            )
        except FileNotFoundError:
            out_path.write_bytes(image_bytes)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


def generate_veo_video(
    *,
    client: GeminiClient | None,
    model: str,
    prompt: str,
    negative_prompt: str,
    duration_seconds: int,
    aspect_ratio: str,
    resolution: str,
    input_image: Path | None,
    last_frame_image: Path | None,
    reference_images: list[Path] | None,
    out_path: Path,
    poll_every: float,
    timeout_seconds: float,
    force: bool,
    log_path: Path | None,
    dry_run: bool,
) -> None:
    if out_path.exists() and not force:
        return

    if dry_run:
        kind = "F2F" if (input_image and last_frame_image) else ("I2V" if input_image else "T2V")
        print(f"[dry-run] VIDEO({kind}) {out_path} <- {model} ({duration_seconds}s, {aspect_ratio}, {resolution})")
        return
    raise SystemExit(
        "Veo video generation is disabled in this repo for safety. "
        "Use Kling instead (set scenes[].video_generation.tool to kling_3_0 or kling_3_0_omni)."
    )


def generate_kling_video(
    *,
    client: KlingClient | None,
    model: str,
    prompt: str,
    negative_prompt: str,
    duration_seconds: int,
    aspect_ratio: str,
    resolution: str,
    input_image: Path | None,
    last_frame_image: Path | None,
    extra_payload: dict[str, Any] | None,
    out_path: Path,
    poll_every: float,
    timeout_seconds: float,
    force: bool,
    log_path: Path | None,
    dry_run: bool,
) -> None:
    if out_path.exists() and not force:
        return

    if dry_run:
        kind = "F2F" if (input_image and last_frame_image) else ("I2V" if input_image else "T2V")
        print(f"[dry-run] VIDEO({kind}) {out_path} <- {model} ({duration_seconds}s, {aspect_ratio}, {resolution})")
        return

    if client is None:
        raise SystemExit("Kling client not configured (missing KLING_API_KEY).")

    try:
        submit = client.start_video_generation(
            prompt=prompt,
            duration_seconds=int(duration_seconds),
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            input_image=input_image,
            last_frame_image=last_frame_image,
            negative_prompt=(negative_prompt.strip() or None),
            model=model,
            extra_payload=extra_payload,
            timeout_seconds=180.0,
        )
        operation_id = client.extract_operation_id(submit)
        op = client.poll_operation(
            operation_id_or_url=operation_id,
            poll_every_seconds=float(poll_every),
            timeout_seconds=float(timeout_seconds),
        )
    except (HttpError, TimeoutError, ValueError) as e:
        raise SystemExit(str(e)) from e

    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps({"submit": submit, "operation": op}, ensure_ascii=False, indent=2), encoding="utf-8")

    if client.is_failed_operation(op):
        raise SystemExit(f"Kling operation failed: {json.dumps(op, ensure_ascii=False)}")

    try:
        video_uri = client.extract_video_uri(op)
        client.download_to_file(uri=video_uri, out_path=out_path)
    except (HttpError, ValueError) as e:
        raise SystemExit(str(e)) from e


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def generate_evolink_video(
    *,
    client: EvoLinkClient | None,
    model: str,
    prompt: str,
    negative_prompt: str,
    duration_seconds: int,
    aspect_ratio: str,
    resolution: str,
    input_image: Path | None,
    last_frame_image: Path | None,
    extra_payload: dict[str, Any] | None,
    out_path: Path,
    poll_every: float,
    timeout_seconds: float,
    force: bool,
    log_path: Path | None,
    dry_run: bool,
) -> None:
    if out_path.exists() and not force:
        return

    if dry_run:
        kind = "I2V" if input_image else "T2V"
        print(f"[dry-run] VIDEO({kind}) {out_path} <- {model} ({duration_seconds}s, {aspect_ratio}, {resolution})")
        return

    if client is None:
        raise SystemExit("EvoLink client not configured (missing EVOLINK_API_KEY).")

    quality = resolution if resolution in {"720p", "1080p"} else "720p"
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "duration": int(duration_seconds),
        "aspect_ratio": aspect_ratio,
        "quality": quality,
        # Safety default: no audio unless explicitly enabled via extra_payload override.
        "sound": False,
    }
    if negative_prompt and negative_prompt.strip():
        payload["negative_prompt"] = negative_prompt.strip()

    if input_image is not None:
        payload["image_start"] = client.upload_image_base64(path=input_image)
    if last_frame_image is not None:
        payload["image_end"] = client.upload_image_base64(path=last_frame_image)

    if extra_payload:
        payload = _deep_merge_dict(payload, extra_payload)

    try:
        submit = client.submit_video_task(payload=payload)
        task_id = client.extract_task_id(submit)
        task = client.poll_task(task_id=task_id, poll_every_seconds=float(poll_every), timeout_seconds=float(timeout_seconds))
    except (HttpError, TimeoutError, ValueError) as e:
        raise SystemExit(str(e)) from e

    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps({"submit": submit, "task": task}, ensure_ascii=False, indent=2), encoding="utf-8")

    status = str(task.get("status") or "").strip().lower()
    if status in {"failed", "error", "canceled", "cancelled", "rejected"}:
        raise SystemExit(f"EvoLink task failed: {json.dumps(task, ensure_ascii=False)}")

    try:
        video_url = client.extract_video_url(task)
        client.download_to_file(url=video_url, out_path=out_path)
    except (HttpError, ValueError) as e:
        raise SystemExit(str(e)) from e


def generate_seedance_video(
    *,
    client: SeedanceClient | None,
    model: str,
    prompt: str,
    duration_seconds: int,
    aspect_ratio: str,
    resolution: str,
    input_image: Path | None,
    last_frame_image: Path | None,
    reference_images: list[Path] | None,
    generate_audio: bool,
    extra_payload: dict[str, Any] | None,
    out_path: Path,
    poll_every: float,
    timeout_seconds: float,
    force: bool,
    log_path: Path | None,
    dry_run: bool,
) -> None:
    if out_path.exists() and not force:
        return

    if dry_run:
        kind = "F2F" if (input_image and last_frame_image) else ("I2V" if input_image else "T2V")
        print(f"[dry-run] VIDEO({kind}) {out_path} <- {model} ({duration_seconds}s, {aspect_ratio}, {resolution})")
        return

    if client is None:
        raise SystemExit("Seedance client not configured (missing ARK_API_KEY or SEADREAM_API_KEY).")

    payload = client.build_video_payload(
        model=model,
        prompt=prompt,
        duration_seconds=int(duration_seconds),
        ratio=aspect_ratio,
        resolution=resolution,
        input_image=input_image,
        last_frame_image=last_frame_image,
        reference_images=reference_images,
        generate_audio=bool(generate_audio),
        watermark=False,
        extra_payload=extra_payload,
    )

    try:
        submit = client.create_task(payload=payload)
        task_id = client.extract_task_id(submit)
        task = client.poll_task(task_id=task_id, poll_every_seconds=float(poll_every), timeout_seconds=float(timeout_seconds))
    except (HttpError, TimeoutError, ValueError) as e:
        raise SystemExit(str(e)) from e

    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps({"submit": submit, "task": task}, ensure_ascii=False, indent=2), encoding="utf-8")

    if client.is_failed_task(task):
        raise SystemExit(f"Seedance task failed: {json.dumps(task, ensure_ascii=False)}")

    try:
        video_url = client.extract_video_url(task)
        client.download_to_file(url=video_url, out_path=out_path)
    except (HttpError, ValueError) as e:
        raise SystemExit(str(e)) from e


def normalize_tool_name(tool: str | None) -> str:
    if not tool:
        return ""
    normalized = tool.strip().lower().replace(" ", "_")
    # Safety: treat Veo tool names as Kling to avoid accidental paid Google video calls.
    if normalized in {"google_veo_3_1", "veo", "veo_3_1", "veo3", "veo_3"}:
        return "kling_3_0_omni"
    if normalized in {"google_nanobanana_pro", "nanobanana_pro", "google_nanobanana_2", "nanobanana_2"}:
        return "google_nanobanana_2"
    return normalized


def _silence_contract_fields(narration: dict[str, Any] | None) -> tuple[bool, bool, str | None, str | None]:
    if not isinstance(narration, dict):
        return False, False, None, None
    raw = narration.get("silence_contract")
    if not isinstance(raw, dict):
        return False, False, None, None
    intentional = bool(raw.get("intentional"))
    confirmed = bool(raw.get("confirmed_by_human"))
    kind = _as_opt_str(raw.get("kind"))
    reason = _as_opt_str(raw.get("reason"))
    return intentional, confirmed, kind, reason


def _node_selector(scene_id: Any, cut_id: Any | None = None) -> str:
    return make_scene_cut_selector(scene_id, cut_id)


def validate_human_change_requests(*, manifest: dict[str, Any], scene_filter: set[str] | None) -> None:
    raw_requests = manifest.get("human_change_requests")
    if not isinstance(raw_requests, list):
        raw_requests = []

    known_request_ids: set[str] = set()

    unresolved: list[str] = []
    for raw in raw_requests:
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status") or "").strip().lower()
        request_id = str(raw.get("request_id") or "<unknown>").strip()
        if request_id and request_id != "<unknown>":
            known_request_ids.add(request_id)
        if status not in {"verified", "waived"}:
            unresolved.append(request_id)
    if unresolved:
        raise SystemExit(
            "Unresolved human change requests remain. Resolve or waive them before generation: "
            + ", ".join(unresolved)
        )

    scenes = manifest.get("scenes")
    if not isinstance(scenes, list):
        return

    issues: list[str] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_id = normalize_dotted_id(scene.get("scene_id"))
        if scene_id is None:
            issues.append("dotted_selector_invalid: scene_id is missing or invalid.")
            continue
        cuts = scene.get("cuts")
        nodes = cuts if isinstance(cuts, list) and cuts else [scene]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            cut_id = normalize_dotted_id(node.get("cut_id")) if node is not scene else None
            selector = _node_selector(scene_id, cut_id)
            if scene_filter and selector not in scene_filter and scene_id not in scene_filter:
                continue

            impl = node.get("implementation_trace") if isinstance(node.get("implementation_trace"), dict) else {}
            source_request_ids = _ensure_str_list(impl.get("source_request_ids")) if isinstance(impl, dict) else []
            trace_status = str(impl.get("status") or "").strip().lower() if isinstance(impl, dict) else ""
            unknown_source_ids = [request_id for request_id in source_request_ids if request_id not in known_request_ids]
            if unknown_source_ids:
                issues.append(
                    f"{selector}: unknown human_change_request id(s) in implementation_trace: "
                    + ", ".join(unknown_source_ids)
                )
            if source_request_ids and trace_status not in {"implemented", "verified", "waived"}:
                issues.append(f"{selector}: human_change_request_trace_missing")

            for section_key, id_path in (
                ("audio", ("narration", "applied_request_ids")),
                ("image_generation", ("applied_request_ids",)),
                ("video_generation", ("applied_request_ids",)),
            ):
                section = node.get(section_key) if isinstance(node.get(section_key), dict) else {}
                if not section:
                    continue
                cur: Any = section
                for key in id_path:
                    if not isinstance(cur, dict):
                        cur = None
                        break
                    cur = cur.get(key)
                applied = _ensure_str_list(cur)
                unknown_applied = [request_id for request_id in applied if request_id not in known_request_ids]
                if unknown_applied:
                    issues.append(
                        f"{selector}: unknown human_change_request id(s) in {section_key}: "
                        + ", ".join(unknown_applied)
                    )
                if source_request_ids and not set(source_request_ids).issubset(set(applied)):
                    issues.append(f"{selector}: human_change_request_trace_missing in {section_key}")

            still_assets = _coerce_still_assets(node)
            known_asset_ids = {
                str(item.get("asset_id") or "").strip()
                for item in still_assets
                if str(item.get("asset_id") or "").strip()
            }
            for asset in still_assets:
                asset_id = str(asset.get("asset_id") or "<unknown>").strip()
                for dep_key, reason_key in (
                    ("derived_from_asset_ids", "still_asset_dependency_missing"),
                    ("reference_asset_ids", "still_asset_dependency_missing"),
                ):
                    for dep in _ensure_str_list(asset.get(dep_key)):
                        if dep not in known_asset_ids:
                            issues.append(f"{selector}:{asset_id}: {reason_key}")
                for usage in asset.get("reference_usage") if isinstance(asset.get("reference_usage"), list) else []:
                    if not isinstance(usage, dict):
                        continue
                    target_asset_id = str(usage.get("asset_id") or "").strip()
                    if target_asset_id and target_asset_id not in known_asset_ids:
                        issues.append(f"{selector}:{asset_id}: reference_usage_target_missing")

    if issues:
        raise SystemExit("Human review contract validation failed:\n- " + "\n- ".join(issues))


def resolve_path(base_dir: Path, maybe_path: str | None) -> Path | None:
    if not maybe_path:
        return None
    p = Path(maybe_path)
    return p if p.is_absolute() else (base_dir / p)


def _derive_test_variant_output_path(base_dir: Path, source_output: str | None, variant_index: int, test_dir: str) -> Path | None:
    out_path = resolve_path(base_dir, source_output)
    if out_path is None:
        return None
    stem = out_path.stem
    suffix = out_path.suffix or ".png"
    target_dir = resolve_path(base_dir, test_dir)
    if target_dir is None:
        return None
    return target_dir / f"{stem}__test_v{variant_index:02d}{suffix}"


def _compose_final_image_prompt(
    scene: SceneSpec,
    *,
    prefix: str,
    suffix: str,
    request_visual_beat: str | None = None,
) -> str:
    prompt = (scene.image_prompt or "").strip()
    visual_beat = (request_visual_beat or "").strip()
    if visual_beat and visual_beat not in prompt:
        prompt = f"[場面の核]\n{visual_beat}\n\n{prompt}".strip()
    if prefix:
        prompt = prefix + "\n\n" + prompt if prompt else prefix
    if suffix:
        prompt = prompt + "\n\n" + suffix if prompt else suffix
    return prompt.strip()


def _compose_final_video_prompt(scene: SceneSpec, *, prefix: str, suffix: str) -> str:
    prompt_parts: list[str] = []
    if scene.video_motion_prompt:
        prompt_parts.append(scene.video_motion_prompt.strip())
    if scene.image_prompt:
        prompt_parts.append("シーン説明:\n" + scene.image_prompt.strip())
    prompt = "\n\n".join(prompt_parts).strip()
    if prefix:
        prompt = prefix + "\n\n" + prompt if prompt else prefix
    if suffix:
        prompt = prompt + "\n\n" + suffix if prompt else suffix
    return prompt.strip()


def _write_request_preview_md(
    *,
    out_path: Path,
    title: str,
    entries: list[dict[str, Any]],
    topic: str = "",
) -> None:
    lines: list[str] = [f"# {title}", ""]
    if not entries:
        lines.extend(["該当エントリはありません。", ""])
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return
    for entry in entries:
        lines.append(f"## {entry['selector']}")
        lines.append("")
        lines.append(f"- tool: `{entry['tool']}`")
        if entry.get("still_mode"):
            lines.append(f"- still_mode: `{entry['still_mode']}`")
        if entry.get("generation_status"):
            lines.append(f"- generation_status: `{entry['generation_status']}`")
        if entry.get("plan_source"):
            lines.append(f"- plan_source: `{entry['plan_source']}`")
        lines.append(f"- output: `{entry['output']}`")
        if entry.get("first_frame"):
            lines.append(f"- first_frame: `{entry['first_frame']}`")
        if entry.get("last_frame"):
            lines.append(f"- last_frame: `{entry['last_frame']}`")
        source_requests = entry.get("source_requests") or []
        if source_requests:
            lines.append("- source_requests:")
            for request in source_requests:
                request_id = str(request.get("request_id") or "").strip()
                raw_request = str(request.get("raw_request") or "").strip() or "(raw_request missing)"
                resolution_notes = str(request.get("resolution_notes") or "").strip()
                suffix = f" (resolution_notes: {resolution_notes})" if resolution_notes else ""
                lines.append(f"  - `{request_id}`: {raw_request}{suffix}")
        refs = entry.get("references") or []
        if refs:
            lines.append("- references:")
            for item in _label_reference_paths(list(refs)):
                lines.append(f"  - `{item['label']}`: `{item['path']}`")
        else:
            lines.append("- references: `[]`")
        lines.append("")
        lines.append("```text")
        lines.append(
            _rewrite_request_prompt_for_review(
                prompt=entry.get("prompt") or "",
                output=entry.get("output") or "",
                references=list(entry.get("references") or []),
                topic=topic,
            ).rstrip()
        )
        lines.append("```")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _label_reference_paths(references: list[str]) -> list[dict[str, str]]:
    counters = {
        "character": 0,
        "location": 0,
        "object": 0,
        "generic": 0,
    }
    labeled: list[dict[str, str]] = []
    for ref in references:
        norm = str(ref or "").replace("\\", "/")
        if "/assets/characters/" in f"/{norm}":
            counters["character"] += 1
            label = f"人物参照画像{counters['character']}"
        elif "/assets/locations/" in f"/{norm}":
            counters["location"] += 1
            label = f"場所参照画像{counters['location']}"
        elif "/assets/objects/" in f"/{norm}":
            counters["object"] += 1
            label = f"小道具参照画像{counters['object']}"
        else:
            counters["generic"] += 1
            label = f"参照画像{counters['generic']}"
        labeled.append({"label": label, "path": norm})
    return labeled


def _write_generation_exclusion_report_md(*, out_path: Path, scenes: list[SceneSpec]) -> None:
    deleted_scenes = [scene for scene in scenes if _scene_is_deleted(scene)]
    lines: list[str] = ["# Generation Exclusion Report", ""]
    if not deleted_scenes:
        lines.extend(["除外対象はありません。", ""])
        out_path.write_text("\n".join(lines), encoding="utf-8")
        return
    for scene in deleted_scenes:
        lines.append(f"## {scene.selector or make_scene_cut_selector(scene.scene_id)}")
        lines.append("")
        lines.append("- status: `deleted`")
        if scene.deletion_reason:
            lines.append(f"- reason: {scene.deletion_reason}")
        skipped: list[str] = []
        if scene.image_output:
            skipped.append(f"`{scene.image_output}`")
        if scene.video_output:
            skipped.append(f"`{scene.video_output}`")
        if scene.narration_output:
            skipped.append(f"`{scene.narration_output}`")
        if skipped:
            lines.append("- skipped_outputs:")
            for item in skipped:
                lines.append(f"  - {item}")
        else:
            lines.append("- skipped_outputs: `[]`")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _rewrite_request_prompt_for_review(*, prompt: str, output: str, references: list[str], topic: str = "") -> str:
    text = (prompt or "").strip()
    if not text:
        return ""

    has_refs = bool(references)
    output_norm = (output or "").replace("\\", "/")
    is_character_asset = "/assets/characters/" in f"/{output_norm}"
    is_object_asset = "/assets/objects/" in f"/{output_norm}"
    is_location_asset = "/assets/locations/" in f"/{output_norm}"
    is_story_scene = "/assets/scenes/" in f"/{output_norm}"
    topic_norm = (topic or "").strip()
    labeled_refs = _label_reference_paths(list(references))
    path_to_label = {item["path"]: item["label"] for item in labeled_refs}

    text = text.replace("（以後のsceneで一貫性を保つため）", "")
    text = text.replace("（連続性アンカー）", "")
    text = re.sub(r"[ \t]{2,}", " ", text)

    if is_character_asset:
        text = text.replace("の参照画像。", "のキャラクター基準画像。")
        text = text.replace("参照画像のため", "基準画像のため")
    elif is_object_asset:
        text = text.replace("の参照画像。", "の小道具基準画像。")
        text = text.replace("参照画像のため", "基準画像のため")

    if has_refs:
        text = re.sub(
            r"参照画像と完全一致（(.+?)）",
            r"参照画像に写っている\1をこの cut でも維持する",
            text,
        )
        text = re.sub(
            r"後続sceneでも(.+?)を変えないための基準画像にする。",
            r"参照画像に写っている\1を読み取れる基準画像にする。",
            text,
        )
        text = re.sub(
            r"連続性アンカー:\s*(.+?)。",
            r"参照画像に写っている\1を、この cut の画面内でも維持する。",
            text,
        )
    else:
        text = re.sub(
            r"参照画像と完全一致（(.+?)）",
            r"\1をこの cut でも維持する",
            text,
        )
        text = re.sub(
            r"後続sceneでも(.+?)を変えないための基準画像にする。",
            r"\1を読み取れる基準画像にする。",
            text,
        )
        text = re.sub(
            r"連続性アンカー:\s*(.+?)。",
            r"\1を、この cut の画面内でも維持する。",
            text,
        )
        text = text.replace("参照画像のため", "この画像では")

    text = text.replace("以後のscene", "この画像")
    text = text.replace("後続scene", "この場面")
    text = text.replace("この cut", "この場面")
    text = text.replace("1カット内で", "この画像内で")
    text = text.replace("カット目的:", "場面の目的:")
    text = text.replace("カットしない", "途中で途切れさせない")
    text = text.replace("入口カット", "入口場面")
    text = text.replace("基準カット", "基準場面")
    text = text.replace("この場面 単体", "この画像だけで")
    text = re.sub(r"次の\s*cut\s*で.+?(。|$)", "", text)
    text = re.sub(r"前の\s*cut\s*の.+?(。|$)", "", text)
    text = re.sub(r"次の\s*場面\s*で.+?(。|$)", "", text)
    text = re.sub(r"前の\s*場面\s*の.+?(。|$)", "", text)
    text = re.sub(r"次scene.+?(。|$)", "", text)
    text = re.sub(r"前scene.+?(。|$)", "", text)
    if topic_norm:
        if is_character_asset:
            text = re.sub(
                r"(?m)^([^\n]+のキャラクター基準画像。)",
                rf"物語「{topic_norm}」に出てくる\1",
                text,
                count=1,
            )
        elif is_story_scene:
            if "[物語の文脈]" not in text:
                text = "[物語の文脈]\n" + f"この画像は物語「{topic_norm}」の一場面を視覚化する。\n\n" + text
        elif is_location_asset:
            basename = Path(output_norm).stem
            synthetic_location_ids = {"sea_temple_interior", "clock_museum"}
            if basename not in synthetic_location_ids and "[物語の文脈]" not in text:
                text = "[物語の文脈]\n" + f"この画像は物語「{topic_norm}」に出てくる場所を表す。\n\n" + text
    text = re.sub(r"この場面\s+でも", "この場面でも", text)
    text = re.sub(r"この場面\s+の", "この場面の", text)
    text = re.sub(r"この場面\s+単体", "この画像だけで", text)
    text = text.replace("この画像だけでで", "この画像だけで")

    for path, label in path_to_label.items():
        text = text.replace(f"`{path}`", label)
        text = text.replace(path, label)

    text = re.sub(
        r"(?ms)\n?\[参照画像の使い方\]\n参照画像は使わない。\n?",
        "\n",
        text,
    )
    if not has_refs:
        text = re.sub(
            r"(?ms)\n?\[参照画像の使い方\]\n.*?(?=\n\[[^\n]+\]|\Z)",
            "\n",
            text,
        )

    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text.strip()


def main() -> None:
    load_env_files(repo_root=REPO_ROOT)

    parser = argparse.ArgumentParser(description="Generate assets from a video manifest.")
    parser.add_argument("--manifest", required=True, help="Path to video_manifest.md")
    parser.add_argument("--base-dir", default=None, help="Resolve relative paths from this dir (default: manifest dir).")
    parser.add_argument("--force", action="store_true", help="Overwrite existing outputs.")
    parser.add_argument("--dry-run", action="store_true", help="Plan only (no API calls).")
    parser.add_argument(
        "--materialize-request-files-only",
        action="store_true",
        help="Write final asset/image/video request files and exit without calling provider APIs.",
    )
    parser.add_argument(
        "--test-image-variants",
        type=int,
        default=0,
        help="On forced reruns only, also generate N exploratory image variants into assets/test for each selected image scene.",
    )
    parser.add_argument(
        "--test-image-dir",
        default="assets/test",
        help='Output directory for --test-image-variants (default: "assets/test").',
    )

    parser.add_argument("--skip-images", action="store_true")
    parser.add_argument("--skip-videos", action="store_true")
    parser.add_argument("--skip-audio", action="store_true")
    parser.add_argument(
        "--skip-image-prompt-review",
        action="store_true",
        help="Skip the pre-image-generation story consistency review gate.",
    )
    parser.add_argument(
        "--skip-narration-review",
        action="store_true",
        help="Skip the pre-audio-generation narration text review gate.",
    )
    parser.add_argument(
        "--image-prompt-review-fix-character-ids",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Before image generation, auto-add missing character_ids inferred by the review script.",
    )

    parser.add_argument("--scene-ids", default=None, help='Comma-separated list like "1,3,5" (default: all).')

    # Gemini Image
    parser.add_argument("--gemini-api-base", default=_env("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"))
    parser.add_argument("--gemini-api-key", default=_env("GEMINI_API_KEY"))
    parser.add_argument("--gemini-image-model", default=_env("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview"))
    parser.add_argument("--image-size", default="1K")
    parser.add_argument("--image-aspect-ratio", default=None)
    parser.add_argument("--image-prompt-prefix", default="", help="Optional text prepended to every image prompt.")
    parser.add_argument("--image-prompt-suffix", default="", help="Optional text appended to every image prompt.")
    parser.add_argument(
        "--apply-asset-guides",
        action="store_true",
        help="Merge manifest assets.character_bible/style_guide into per-scene prompts/references (best-effort).",
    )
    parser.add_argument(
        "--asset-guides-character-refs",
        choices=["scene", "auto", "all", "none"],
        default="auto",
        help='When applying asset guides, how to add character_bible.reference_images to each scene ("auto"=only if exactly 1 character).',
    )
    parser.add_argument(
        "--log-prompts",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write the final prompts to the provider log dir for reproducibility.",
    )
    parser.add_argument(
        "--require-character-ids",
        action="store_true",
        help="When using --apply-asset-guides with --asset-guides-character-refs scene, require explicit character_ids per scene (use [] for B-roll).",
    )
    parser.add_argument(
        "--require-object-ids",
        action="store_true",
        help="When using --apply-asset-guides with assets.object_bible, require explicit object_ids per scene (use [] when none).",
    )
    parser.add_argument(
        "--require-object-reference-scenes",
        action="store_true",
        help="When assets.object_bible is present, require that each reference_images path is generated by some scene output.",
    )
    parser.add_argument(
        "--character-reference-views",
        default="",
        help='For character reference scenes (assets/characters/*.png), also generate additional view images. Comma-separated: "front,side,back". Default: disabled.',
    )
    parser.add_argument(
        "--character-reference-strip",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="When generating character reference views, also create a single horizontal strip image (front|side|back) for video references.",
    )
    parser.add_argument(
        "--character-reference-strip-suffix",
        default="_refstrip",
        help='Suffix for the strip image filename (default: "_refstrip").',
    )
    parser.add_argument(
        "--video-reference-prefer-character-refstrips",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When generating videos, prefer the combined character ref strip images (if present) over individual character view refs.",
    )
    parser.add_argument(
        "--image-batch-size",
        type=int,
        default=0,
        help="Generate image scenes in batches of N (story scenes only; character ref scenes may be included automatically).",
    )
    parser.add_argument(
        "--image-batch-index",
        type=int,
        default=1,
        help="1-based batch index for --image-batch-size (e.g., size=10 index=1 generates the first 10 story scenes).",
    )
    parser.add_argument(
        "--image-batch-include-character-refs",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="When using --image-batch-size, also generate missing character reference images (assets/characters/*) in the same run.",
    )
    parser.add_argument(
        "--image-plan-modes",
        default="generate_still",
        help="Comma-separated still_image_plan.mode values that are allowed for story image generation (default: generate_still). Character/object reference images are always eligible.",
    )
    parser.add_argument(
        "--image-max-concurrency",
        type=int,
        default=10,
        help="Maximum number of image generation tasks to run in parallel after dependency filtering (capped at 10).",
    )

    # SeaDream (Seedream 4.5, OpenAI Images compatible)
    parser.add_argument("--seadream-api-base", default=_env("SEADREAM_API_BASE", "https://ark.ap-southeast.bytepluses.com/api/v3"))
    parser.add_argument("--seadream-api-key", default=_env("SEADREAM_API_KEY"))
    parser.add_argument("--seadream-model", default=_env("SEADREAM_MODEL", "seedream-4-5-251128"))
    parser.add_argument("--seadream-size", default=_env("SEADREAM_SIZE", "1024x1536"))

    # Veo
    parser.add_argument("--gemini-video-model", default=_env("GEMINI_VIDEO_MODEL", "veo-3.1-fast-generate-preview"))
    parser.add_argument("--video-resolution", default="1080p")
    parser.add_argument("--video-aspect-ratio", default=None)
    parser.add_argument("--default-scene-seconds", type=int, default=6)
    parser.add_argument("--video-prompt-prefix", default="", help="Optional text prepended to every video prompt.")
    parser.add_argument("--video-prompt-suffix", default="", help="Optional text appended to every video prompt.")
    parser.add_argument(
        "--video-negative-prompt",
        default="",
        help="Negative prompt for video generation (provider-dependent).",
    )
    parser.add_argument("--poll-every", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument(
        "--enable-last-frame",
        action="store_true",
        help="Try to pass last-frame conditioning using manifest last_frame (best-effort; provider-dependent).",
    )
    parser.add_argument(
        "--chain-first-frame-from-prev-video",
        action="store_true",
        help="Use a frame extracted from the previous scene's video as the next video's first frame (improves seamless joins).",
    )
    parser.add_argument(
        "--chain-first-frame-seconds-from-end",
        type=float,
        default=1.0,
        help="When chaining, extract the first frame from this many seconds before the end of the previous video.",
    )

    # Kling
    parser.add_argument("--kling-api-base", default=_env("KLING_API_BASE", "https://api.klingai.com"))
    parser.add_argument("--kling-api-key", default=_env("KLING_API_KEY"), help="Gateway-style API key (optional).")
    parser.add_argument("--kling-access-key", default=_env("KLING_ACCESS_KEY"), help="Official Kling AccessKey (recommended).")
    parser.add_argument("--kling-secret-key", default=_env("KLING_SECRET_KEY"), help="Official Kling SecretKey (recommended).")
    parser.add_argument("--kling-video-model", default=_env("KLING_VIDEO_MODEL", "kling-3.0"))
    parser.add_argument("--kling-extra-json", default=_env("KLING_EXTRA_JSON", None), help="Optional JSON object merged into Kling request payload.")
    parser.add_argument(
        "--kling-omni-video-model",
        default=_env("KLING_OMNI_VIDEO_MODEL", "kling-3.0-omni"),
        help='Model used when manifest tool is "kling_3_0_omni" (default can be overridden via KLING_OMNI_VIDEO_MODEL).',
    )
    parser.add_argument(
        "--kling-omni-extra-json",
        default=_env("KLING_OMNI_EXTRA_JSON", None),
        help="Optional JSON object merged into Kling request payload when using kling_3_0_omni.",
    )

    # EvoLink (Kling gateway)
    parser.add_argument("--evolink-api-key", default=_env("EVOLINK_API_KEY"), help="EvoLink API key (optional).")
    parser.add_argument("--evolink-api-base", default=_env("EVOLINK_API_BASE", "https://api.evolink.ai"))
    parser.add_argument("--evolink-files-api-base", default=_env("EVOLINK_FILES_API_BASE", "https://files-api.evolink.ai"))
    parser.add_argument(
        "--evolink-video-submit-path",
        default=_env("EVOLINK_VIDEO_SUBMIT_PATH", "/v1/videos/generations"),
        help='Override submit path (useful when EVOLINK_API_BASE already includes "/v1").',
    )
    parser.add_argument(
        "--evolink-task-status-path-template",
        default=_env("EVOLINK_TASK_STATUS_PATH_TEMPLATE", "/v1/tasks/{task_id}"),
        help='Override task status path template (useful when EVOLINK_API_BASE already includes "/v1").',
    )
    parser.add_argument(
        "--evolink-file-upload-base64-path",
        default=_env("EVOLINK_FILE_UPLOAD_BASE64_PATH", "/api/v1/files/upload/base64"),
        help='Override file upload path for images (default: "/api/v1/files/upload/base64").',
    )
    parser.add_argument("--evolink-kling-v3-i2v-model", default=_env("EVOLINK_KLING_V3_I2V_MODEL", "kling-v3-image-to-video"))
    parser.add_argument("--evolink-kling-v3-t2v-model", default=_env("EVOLINK_KLING_V3_T2V_MODEL", "kling-v3-text-to-video"))
    parser.add_argument("--evolink-kling-o3-i2v-model", default=_env("EVOLINK_KLING_O3_I2V_MODEL", "kling-v3-image-to-video"))
    parser.add_argument("--evolink-kling-o3-t2v-model", default=_env("EVOLINK_KLING_O3_T2V_MODEL", "kling-o3-text-to-video"))

    # BytePlus ModelArk (Seedance video generation)
    parser.add_argument(
        "--ark-api-base",
        default=_env("ARK_API_BASE") or _env("SEADREAM_API_BASE", "https://ark.ap-southeast.bytepluses.com/api/v3"),
        help="ModelArk API base (default: ARK_API_BASE, fallback: SEADREAM_API_BASE).",
    )
    parser.add_argument(
        "--ark-api-key",
        default=_env("ARK_API_KEY") or _env("SEADREAM_API_KEY"),
        help="ModelArk API key (default: ARK_API_KEY, fallback: SEADREAM_API_KEY).",
    )
    parser.add_argument(
        "--ark-seedance-i2v-model",
        default=_env("ARK_SEEDANCE_I2V_MODEL") or _env("SEEDANCE_I2V_MODEL", "seedance-1-0-lite-i2v-250428"),
        help="Seedance model ID for image-to-video.",
    )
    parser.add_argument(
        "--ark-seedance-t2v-model",
        default=_env("ARK_SEEDANCE_T2V_MODEL") or _env("SEEDANCE_T2V_MODEL", "seedance-1-0-pro-250528"),
        help="Seedance model ID for text-to-video.",
    )
    parser.add_argument(
        "--ark-generate-audio",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable Seedance generate_audio (default: disabled).",
    )
    parser.add_argument(
        "--ark-extra-json",
        default=_env("ARK_EXTRA_JSON", None),
        help="Optional JSON object merged into Seedance request payload.",
    )

    # logging
    parser.add_argument("--log-dir", default=None, help="Directory to write provider logs (default: <base>/logs/providers).")

    # ElevenLabs
    parser.add_argument("--elevenlabs-api-key", default=_env("ELEVENLABS_API_KEY"))
    parser.add_argument("--elevenlabs-api-base", default=_env("ELEVENLABS_API_BASE", "https://api.elevenlabs.io/v1"))
    parser.add_argument("--elevenlabs-voice-id", default=_env("ELEVENLABS_VOICE_ID", DEFAULT_ELEVENLABS_VOICE_ID))
    parser.add_argument("--elevenlabs-model-id", default=_env("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2"))
    parser.add_argument("--elevenlabs-output-format", default=_env("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128"))
    parser.add_argument("--tts-prompt-prefix", default="", help="Optional text prepended to every TTS input.")
    parser.add_argument("--tts-prompt-suffix", default="", help="Optional text appended to every TTS input.")
    parser.add_argument("--macos-say-voice", default=_env("MACOS_SAY_VOICE", ""), help="Voice name for macos_say TTS (macOS only).")
    parser.add_argument(
        "--override-narration-tool",
        default="",
        help='Force narration tool for all scenes (e.g. "macos_say") for testing/ops. Empty = use manifest value.',
    )

    args = parser.parse_args()
    if args.test_image_variants < 0:
        raise SystemExit("--test-image-variants must be >= 0")
    if args.test_image_variants and not args.force:
        raise SystemExit("--test-image-variants requires --force")

    def _parse_optional_json_object(value: str | None, *, flag_name: str) -> dict[str, Any] | None:
        if value is None:
            return None
        raw = value.strip()
        if raw == "":
            return None
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as e:
            raise SystemExit(f"{flag_name} is not valid JSON: {e}") from e
        if not isinstance(loaded, dict):
            raise SystemExit(f"{flag_name} must be a JSON object.")
        return loaded

    kling_extra_payload = _parse_optional_json_object(args.kling_extra_json, flag_name="--kling-extra-json")
    kling_omni_extra_payload = _parse_optional_json_object(args.kling_omni_extra_json, flag_name="--kling-omni-extra-json")
    ark_extra_payload = _parse_optional_json_object(args.ark_extra_json, flag_name="--ark-extra-json")

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    base_dir = Path(args.base_dir) if args.base_dir else manifest_path.parent
    allowed_image_plan_modes = _parse_csv_set(args.image_plan_modes)

    if not args.skip_images and not args.skip_image_prompt_review:
        review_cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts/review-image-prompt-story-consistency.py"),
            "--manifest",
            str(manifest_path),
            "--story",
            str(base_dir / "story.md"),
            "--script",
            str(base_dir / "script.md"),
            "--image-plan-modes",
            args.image_plan_modes,
            "--fail-on-findings",
        ]
        if args.image_prompt_review_fix_character_ids:
            review_cmd.append("--fix-character-ids")
        subprocess.run(review_cmd, check=True)

    if not args.skip_audio and not args.skip_narration_review:
        review_cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts/review-narration-text-quality.py"),
            "--manifest",
            str(manifest_path),
            "--fail-on-findings",
        ]
        subprocess.run(review_cmd, check=True)

    md = manifest_path.read_text(encoding="utf-8")
    yaml_text = extract_yaml_block(md)
    manifest_data = yaml.safe_load(yaml_text) if yaml is not None else {}
    if not isinstance(manifest_data, dict):
        manifest_data = {}
    metadata, guides, scenes = parse_manifest_yaml_full(yaml_text)
    script_visual_beat_map: dict[str, str] = {}
    script_path = base_dir / "script.md"
    if script_path.exists():
        _, script_data = load_structured_document(script_path)
        if isinstance(script_data, dict):
            script_visual_beat_map = _build_script_visual_beat_map(script_data)

    char_views = sorted(_parse_csv_set(args.character_reference_views))
    allowed_views = {"front", "side", "back"}
    unknown = [v for v in char_views if v not in allowed_views]
    if unknown:
        raise SystemExit(f"Unknown --character-reference-views values: {unknown}. Allowed: front,side,back")
    # If the user asks for a ref strip, we must have all three views.
    if args.character_reference_strip:
        char_views = sorted(set(char_views) | {"front", "side", "back"})

    # Always include existing refstrip siblings for character still generation when present.
    # This keeps character consistency stronger for image generation without requiring extra flags.
    guides = _expand_character_bible_with_existing_refstrips(
        guides=guides,
        base_dir=base_dir,
        strip_suffix=args.character_reference_strip_suffix,
    )

    # Expand character_bible reference_images to include derived view/strip filenames (opt-in).
    # This keeps existing manifests compatible while letting story scenes automatically reference
    # the additional turnaround views when using --apply-asset-guides.
    if args.apply_asset_guides and (char_views or args.character_reference_strip):
        expanded_cb: list[CharacterBibleEntry] = []
        for entry in guides.character_bible or []:
            refs = _dedupe_keep_order(list(entry.reference_images or []))
            extra: list[str] = []
            for ref in refs:
                ref_p = Path(ref)
                # only expand for assets/characters/* references
                if "assets" not in ref_p.parts or "characters" not in ref_p.parts:
                    continue
                # derive views
                for v in char_views:
                    if v == "front":
                        continue
                    extra.append(str(_derive_character_view_path(ref_p, v)))
                if args.character_reference_strip:
                    extra.append(str(_derive_character_refstrip_path(ref_p, args.character_reference_strip_suffix)))
            expanded = _dedupe_keep_order(refs + extra)
            expanded_variants: list[ReferenceVariantSpec] = []
            for variant in entry.reference_variants or []:
                variant_refs = _dedupe_keep_order(list(variant.reference_images or []))
                variant_extra: list[str] = []
                for ref in variant_refs:
                    ref_p = Path(ref)
                    if "assets" not in ref_p.parts or "characters" not in ref_p.parts:
                        continue
                    for v in char_views:
                        if v == "front":
                            continue
                        variant_extra.append(str(_derive_character_view_path(ref_p, v)))
                    if args.character_reference_strip:
                        variant_extra.append(str(_derive_character_refstrip_path(ref_p, args.character_reference_strip_suffix)))
                expanded_variants.append(
                    ReferenceVariantSpec(
                        variant_id=variant.variant_id,
                        reference_images=_dedupe_keep_order(variant_refs + variant_extra),
                        fixed_prompts=list(variant.fixed_prompts or []),
                        notes=variant.notes,
                    )
                )
                expanded_cb.append(
                    CharacterBibleEntry(
                        character_id=entry.character_id,
                        reference_images=expanded,
                        reference_variants=expanded_variants,
                        fixed_prompts=list(entry.fixed_prompts or []),
                        physical_scale=entry.physical_scale,
                        relative_scale_rules=list(entry.relative_scale_rules or []),
                        review_aliases=list(entry.review_aliases or []),
                        notes=entry.notes,
                    )
                )
        guides = AssetGuides(
            character_bible=expanded_cb,
            style_guide=guides.style_guide,
            object_bible=guides.object_bible,
            location_bible=guides.location_bible,
        )

    if args.apply_asset_guides:
        if yaml is None:
            raise SystemExit("PyYAML is required for --apply-asset-guides (dependency: pyyaml).")
        validate_character_bible(guides=guides)
        if not guides.character_bible and guides.style_guide is None:
            print("[warn] --apply-asset-guides: no assets.character_bible/style_guide found in manifest.")
        if len(guides.character_bible) > 1 and str(args.asset_guides_character_refs).strip().lower() == "auto":
            print(
                "[warn] --apply-asset-guides: assets.character_bible has multiple entries; "
                "character refs will not be auto-added in 'auto' mode. "
                "Use --asset-guides-character-refs all to force."
            )
        for scene in scenes:
            apply_asset_guides_to_scene(scene=scene, guides=guides, character_refs_mode=args.asset_guides_character_refs)
    else:
        for scene in scenes:
            merge_asset_references_into_scene(scene=scene, guides=guides, character_refs_mode="scene")

    if not scenes:
        raise SystemExit("No scenes found in manifest YAML.")

    scene_filter = parse_scene_selectors(args.scene_ids)
    validate_human_change_requests(
        manifest=manifest_data,
        scene_filter=scene_filter,
    )
    human_change_request_lookup = _build_human_change_request_lookup(manifest_data)

    validate_scene_character_ids(
        scenes=scenes,
        require=bool(args.require_character_ids),
        mode=args.asset_guides_character_refs,
        scene_filter=scene_filter,
    )
    validate_scene_object_ids(
        scenes=scenes,
        guides=guides,
        require=bool(args.require_object_ids),
        scene_filter=scene_filter,
    )
    validate_scene_reference_variant_ids(
        scenes=scenes,
        guides=guides,
        require=bool(args.apply_asset_guides),
        scene_filter=scene_filter,
    )
    validate_object_reference_scenes(
        scenes=scenes,
        guides=guides,
        require=bool(args.require_object_reference_scenes),
    )
    validate_scene_narration(
        scenes=scenes,
        require=not bool(args.skip_audio),
        scene_filter=scene_filter,
    )

    aspect_ratio = (
        args.image_aspect_ratio
        or args.video_aspect_ratio
        or (metadata.get("aspect_ratio") if isinstance(metadata.get("aspect_ratio"), str) else None)
        or "9:16"
    )

    experience = str(metadata.get("experience") or "").strip().lower()
    image_request_filename = "asset_generation_requests.md" if experience.startswith("asset_stage") else "image_generation_requests.md"

    log_dir = Path(args.log_dir) if args.log_dir else (base_dir / "logs/providers")

    def _scene_uses_tool(scene: Scene, tools: set[str]) -> bool:
        return normalize_tool_name(scene.image_tool) in tools

    needs_gemini_image = (
        not args.skip_images
        and any(
            _scene_uses_tool(scene, {"google_nanobanana_2", "nanobanana_2"})
            and scene.image_output
            and scene.image_prompt
            and _scene_matches_filter(scene, scene_filter)
            for scene in scenes
        )
    )
    needs_seadream_image = (
        not args.skip_images
        and any(
            _scene_uses_tool(scene, {"seadream", "seedream", "seedream_4_5", "byteplus_seedream_4_5"})
            and scene.image_output
            and scene.image_prompt
            and _scene_matches_filter(scene, scene_filter)
            for scene in scenes
        )
    )
    needs_gemini_video = (
        not args.skip_videos
        and any(
            normalize_tool_name(scene.video_tool) == "google_veo_3_1"
            and scene.video_output
            and _scene_matches_filter(scene, scene_filter)
            for scene in scenes
        )
    )
    needs_kling_video = (
        not args.skip_videos
        and any(
            normalize_tool_name(scene.video_tool) in {"kling_3_0", "kling", "kling_3_0_omni", "kling_omni", "kling-omni"}
            and scene.video_output
            and _scene_matches_filter(scene, scene_filter)
            for scene in scenes
        )
    )
    needs_seedance_video = (
        not args.skip_videos
        and any(
            normalize_tool_name(scene.video_tool)
            in {
                "seedance",
                "byteplus_seedance",
                "bytedance_seedance",
                "ark_seedance",
                "seadream_video",
                "seedream_video",
                "see_dream",
            }
            and scene.video_output
            and _scene_matches_filter(scene, scene_filter)
            for scene in scenes
        )
    )

    gemini_client: GeminiClient | None = None
    if not args.dry_run and (needs_gemini_image or needs_gemini_video):
        if not args.gemini_api_key:
            raise SystemExit("Missing GEMINI_API_KEY (required for Gemini image/video).")
        gemini_client = GeminiClient(
            GeminiConfig(
                api_key=args.gemini_api_key,
                api_base=args.gemini_api_base,
                image_model=args.gemini_image_model,
                video_model=args.gemini_video_model,
            )
        )

    evolink_client: EvoLinkClient | None = None
    evolink_enabled = bool((args.evolink_api_key or "").strip())
    if not args.dry_run and needs_kling_video and evolink_enabled:
        evolink_client = EvoLinkClient(
            EvoLinkConfig.from_env(
                api_key=args.evolink_api_key,
                api_base=args.evolink_api_base,
                files_api_base=args.evolink_files_api_base,
                video_submit_path=args.evolink_video_submit_path,
                task_status_path_template=args.evolink_task_status_path_template,
                file_upload_base64_path=args.evolink_file_upload_base64_path,
            )
        )

    kling_client: KlingClient | None = None
    if not args.dry_run and needs_kling_video and not evolink_enabled:
        has_gateway_key = bool((args.kling_api_key or "").strip())
        has_official_keys = bool((args.kling_access_key or "").strip()) and bool((args.kling_secret_key or "").strip())
        if not (has_gateway_key or has_official_keys):
            raise SystemExit("Missing Kling credentials (set KLING_API_KEY or KLING_ACCESS_KEY+KLING_SECRET_KEY).")
        kling_client = KlingClient(
            KlingConfig.from_env(
                api_key=args.kling_api_key,
                access_key=args.kling_access_key,
                secret_key=args.kling_secret_key,
                api_base=args.kling_api_base,
                video_model=args.kling_video_model,
            )
        )

    seedance_client: SeedanceClient | None = None
    if not args.dry_run and needs_seedance_video:
        if not args.ark_api_key:
            raise SystemExit("Missing ARK_API_KEY (required for Seedance video generation).")
        seedance_client = SeedanceClient(
            SeedanceConfig.from_env(
                api_key=args.ark_api_key,
                api_base=args.ark_api_base,
            )
        )

    seadream_client: SeaDreamClient | None = None
    if not args.dry_run and needs_seadream_image:
        if not args.seadream_api_key:
            raise SystemExit("Missing SEADREAM_API_KEY (required for SeaDream image generation).")
        seadream_client = SeaDreamClient(
            SeaDreamConfig(
                api_key=args.seadream_api_key,
                api_base=args.seadream_api_base,
                image_model=args.seadream_model,
            )
        )

    elevenlabs_client: ElevenLabsClient | None = None
    if not args.dry_run and not args.skip_audio:
        needs_elevenlabs = any(
            normalize_tool_name(scene.narration_tool) == "elevenlabs"
            and scene.narration_output
            and _scene_matches_filter(scene, scene_filter)
            for scene in scenes
        )
        if needs_elevenlabs:
            if not args.elevenlabs_api_key:
                raise SystemExit("Missing ELEVENLABS_API_KEY (required for ElevenLabs TTS).")
            voice_id = str(args.elevenlabs_voice_id or "").strip()
            if not voice_id:
                voice_id = DEFAULT_ELEVENLABS_VOICE_ID
            if voice_id.lower() in {"your_voice_id", "voice_id_tbd", "tbd"}:
                print(
                    "[warn] ELEVENLABS_VOICE_ID looks like a placeholder; falling back to default voice_id "
                    f"({DEFAULT_ELEVENLABS_VOICE_ID})."
                )
                voice_id = DEFAULT_ELEVENLABS_VOICE_ID
            args.elevenlabs_voice_id = voice_id
            elevenlabs_client = ElevenLabsClient(
                ElevenLabsConfig(
                    api_key=args.elevenlabs_api_key,
                    api_base=args.elevenlabs_api_base,
                    voice_id=voice_id,
                    model_id=args.elevenlabs_model_id,
                    output_format=args.elevenlabs_output_format,
                )
            )

    # Pass 1: images (allows later videos to reference other scene images, e.g. first/last frame conditioning).
    image_scenes: list[SceneSpec] = []
    for scene in scenes:
        if not _scene_matches_filter(scene, scene_filter):
            continue
        if args.skip_images:
            continue
        if not _should_generate_image_scene(
            scene,
            allowed_story_modes=allowed_image_plan_modes,
            base_dir=base_dir,
        ):
            continue
        image_scenes.append(scene)

    # Ensure reference images are generated first so later scenes can safely reference them.
    def _image_scene_sort_key(s: SceneSpec) -> int:
        outp = resolve_path(base_dir, s.image_output) if s.image_output else None
        if outp and _is_character_ref_path(outp):
            return 0
        if outp and _is_object_ref_path(outp):
            return 1
        return 2

    image_scenes.sort(key=_image_scene_sort_key)

    if args.image_batch_size:
        if int(args.image_batch_size) <= 0:
            raise SystemExit("--image-batch-size must be a positive integer.")
        if int(args.image_batch_index) <= 0:
            raise SystemExit("--image-batch-index must be >= 1.")

        char_ref_scenes: list[SceneSpec] = []
        obj_ref_scenes: list[SceneSpec] = []
        story_scenes: list[SceneSpec] = []
        for s in image_scenes:
            outp = resolve_path(base_dir, s.image_output) if s.image_output else None
            if outp and _is_character_ref_path(outp):
                char_ref_scenes.append(s)
            elif outp and _is_object_ref_path(outp):
                obj_ref_scenes.append(s)
            else:
                story_scenes.append(s)

        start = (int(args.image_batch_index) - 1) * int(args.image_batch_size)
        end = start + int(args.image_batch_size)
        selected_story = story_scenes[start:end]

        selected: list[SceneSpec] = []
        if args.image_batch_include_character_refs:
            for s in char_ref_scenes:
                outp = resolve_path(base_dir, s.image_output) if s.image_output else None
                if not outp:
                    continue
                # Avoid re-calling paid APIs unnecessarily; include only missing refs unless --force.
                if args.force or args.dry_run or (not outp.exists()):
                    selected.append(s)
            for s in obj_ref_scenes:
                outp = resolve_path(base_dir, s.image_output) if s.image_output else None
                if not outp:
                    continue
                if args.force or args.dry_run or (not outp.exists()):
                    selected.append(s)
        selected.extend(selected_story)
        image_scenes = selected

    image_preview_entries: list[dict[str, Any]] = []
    image_prefix = (args.image_prompt_prefix or "").strip()
    image_suffix = (args.image_prompt_suffix or "").strip()
    include_image_source_requests = image_request_filename == "image_generation_requests.md"
    image_request_scenes: list[SceneSpec] = []
    for scene in scenes:
        if not _scene_matches_filter(scene, scene_filter):
            continue
        if _scene_is_deleted(scene):
            continue
        if not scene.image_output or not scene.image_prompt:
            continue
        image_request_scenes.append(scene)
    for scene in image_request_scenes:
        out_path = resolve_path(base_dir, scene.image_output)
        selector = scene.selector or make_scene_cut_selector(scene.scene_id)
        request_visual_beat = ""
        if _scene_request_should_prefer_script_visual_beat(scene):
            request_visual_beat = script_visual_beat_map.get(selector, "")
        source_requests: list[dict[str, str]] = []
        if include_image_source_requests and scene.image_applied_request_ids:
            source_requests = _resolve_source_requests(
                request_ids=list(scene.image_applied_request_ids),
                request_lookup=human_change_request_lookup,
                selector=selector,
                section_name="image_generation.applied_request_ids",
            )
        image_preview_entries.append(
            {
                "selector": selector,
                "tool": normalize_tool_name(scene.image_tool) or "",
                "still_mode": scene.still_image_plan_mode or "",
                "generation_status": _effective_still_generation_status(scene, base_dir=base_dir),
                "plan_source": scene.still_image_plan_source or "",
                "output": str(out_path.relative_to(base_dir)) if out_path is not None else "",
                "source_requests": source_requests,
                "references": list(scene.image_references or []),
                "prompt": _compose_final_image_prompt(
                    scene,
                    prefix=image_prefix,
                    suffix=image_suffix,
                    request_visual_beat=request_visual_beat,
                ),
            }
        )
    _write_request_preview_md(
        out_path=base_dir / image_request_filename,
        title="Asset Generation Requests" if image_request_filename == "asset_generation_requests.md" else "Image Generation Requests",
        entries=image_preview_entries,
        topic=str(metadata.get("topic") or ""),
    )

    video_scenes_preview: list[SceneSpec] = []
    for s in scenes:
        if not _scene_matches_filter(s, scene_filter):
            continue
        if _scene_is_deleted(s):
            continue
        if args.skip_videos or not s.video_output or not (s.video_motion_prompt or s.image_prompt):
            continue
        video_scenes_preview.append(s)

    video_prefix = (args.video_prompt_prefix or "").strip()
    video_suffix = (args.video_prompt_suffix or "").strip()
    video_preview_entries: list[dict[str, Any]] = []
    for scene in video_scenes_preview:
        out_path = resolve_path(base_dir, scene.video_output)
        first_frame = resolve_path(base_dir, scene.video_first_frame or scene.video_input_image)
        if first_frame is None and scene.image_output:
            first_frame = resolve_path(base_dir, scene.image_output)
        last_frame = resolve_path(base_dir, scene.video_last_frame)
        source_requests: list[dict[str, str]] = []
        if scene.video_applied_request_ids:
            source_requests = _resolve_source_requests(
                request_ids=list(scene.video_applied_request_ids),
                request_lookup=human_change_request_lookup,
                selector=scene.selector or make_scene_cut_selector(scene.scene_id),
                section_name="video_generation.applied_request_ids",
            )
        video_preview_entries.append(
            {
                "selector": scene.selector or make_scene_cut_selector(scene.scene_id),
                "tool": normalize_tool_name(scene.video_tool) or "",
                "output": str(out_path.relative_to(base_dir)) if out_path is not None else "",
                "first_frame": str(first_frame.relative_to(base_dir)) if first_frame is not None else "",
                "last_frame": str(last_frame.relative_to(base_dir)) if last_frame is not None else "",
                "source_requests": source_requests,
                "references": list(scene.image_references or []),
                "prompt": _compose_final_video_prompt(scene, prefix=video_prefix, suffix=video_suffix),
            }
        )
    _write_request_preview_md(
        out_path=base_dir / "video_generation_requests.md",
        title="Video Generation Requests",
        entries=video_preview_entries,
        topic=str(metadata.get("topic") or ""),
    )
    _write_generation_exclusion_report_md(
        out_path=base_dir / "generation_exclusion_report.md",
        scenes=scenes,
    )

    if args.materialize_request_files_only:
        write_run_index(base_dir)
        print(f"[materialized] {base_dir / image_request_filename}")
        print(f"[materialized] {base_dir / 'video_generation_requests.md'}")
        print(f"[materialized] {base_dir / 'generation_exclusion_report.md'}")
        return

    image_max_concurrency = max(1, min(int(args.image_max_concurrency or 1), 10))
    _generate_image_scenes_with_dependencies(
        image_scenes=image_scenes,
        image_max_concurrency=image_max_concurrency,
        base_dir=base_dir,
        aspect_ratio=aspect_ratio,
        args=args,
        char_views=char_views,
        log_dir=log_dir,
        gemini_client=gemini_client,
        seadream_client=seadream_client,
    )

    # Pass 2: videos
    video_scenes_in_order: list[SceneSpec] = []
    for s in scenes:
        if not _scene_matches_filter(s, scene_filter):
            continue
        if _scene_is_deleted(s):
            continue
        if args.skip_videos or not s.video_output or not (s.video_motion_prompt or s.image_prompt):
            continue
        video_scenes_in_order.append(s)

    video_prefix = (args.video_prompt_prefix or "").strip()
    video_suffix = (args.video_prompt_suffix or "").strip()
    video_preview_entries: list[dict[str, Any]] = []
    for scene in video_scenes_in_order:
        out_path = resolve_path(base_dir, scene.video_output)
        first_frame = resolve_path(base_dir, scene.video_first_frame or scene.video_input_image)
        if first_frame is None and scene.image_output:
            first_frame = resolve_path(base_dir, scene.image_output)
        last_frame = resolve_path(base_dir, scene.video_last_frame)
        video_preview_entries.append(
            {
                "selector": scene.selector or make_scene_cut_selector(scene.scene_id),
                "tool": normalize_tool_name(scene.video_tool) or "",
                "output": str(out_path.relative_to(base_dir)) if out_path is not None else "",
                "first_frame": str(first_frame.relative_to(base_dir)) if first_frame is not None else "",
                "last_frame": str(last_frame.relative_to(base_dir)) if last_frame is not None else "",
                "references": list(scene.image_references or []),
                "prompt": _compose_final_video_prompt(scene, prefix=video_prefix, suffix=video_suffix),
            }
        )
    _write_request_preview_md(
        out_path=base_dir / "video_generation_requests.md",
        title="Video Generation Requests",
        entries=video_preview_entries,
    )

    if args.materialize_request_files_only:
        write_run_index(base_dir)
        print(f"[materialized] {base_dir / image_request_filename}")
        print(f"[materialized] {base_dir / 'video_generation_requests.md'}")
        return

    video_scene_index_by_id: dict[str, int] = {str(s.scene_id): idx for idx, s in enumerate(video_scenes_in_order)}

    prev_chain_first_frame: Path | None = None
    for scene in scenes:
        if not _scene_matches_filter(scene, scene_filter):
            continue
        if _scene_is_deleted(scene):
            continue

        if args.skip_videos or not scene.video_output or not (scene.video_motion_prompt or scene.image_prompt):
            continue

        tool = normalize_tool_name(scene.video_tool)
        out_path = resolve_path(base_dir, scene.video_output)
        if not out_path:
            raise SystemExit(f"scene{scene.scene_id}: missing video output path")

        dur = int(scene.duration_seconds) if scene.duration_seconds is not None else duration_from_timestamp_range(scene.timestamp, args.default_scene_seconds)

        input_image = resolve_path(base_dir, scene.video_first_frame or scene.video_input_image)
        if input_image is None and scene.image_output:
            input_image = resolve_path(base_dir, scene.image_output)
        if args.chain_first_frame_from_prev_video and prev_chain_first_frame is not None:
            # Best-effort: override the provided first_frame so the new clip starts
            # exactly where the previous clip ended (improves mp4 concat continuity).
            input_image = prev_chain_first_frame
        elif args.chain_first_frame_from_prev_video and prev_chain_first_frame is None:
            # If the user is regenerating only later scenes, we may have skipped the previous video generation.
            # Don't assume contiguous numeric IDs; use manifest order to find the previous video scene.
            idx = video_scene_index_by_id.get(str(scene.scene_id))
            if idx is not None and idx > 0:
                prev_scene = video_scenes_in_order[idx - 1]
                prev_video = resolve_path(base_dir, prev_scene.video_output)
                if prev_video and prev_video.exists() and not args.dry_run:
                    chain_frame = prev_video.with_name(prev_video.stem + "_chain_first_frame.png")
                    try:
                        prev_chain_first_frame = _ffmpeg_extract_frame_from_end_best_effort(
                            prev_video,
                            chain_frame,
                            seconds_from_end=float(args.chain_first_frame_seconds_from_end),
                            force=True,
                        )
                        input_image = prev_chain_first_frame
                    except FileNotFoundError:
                        prev_chain_first_frame = None
        if input_image and not args.dry_run and not input_image.exists():
            raise SystemExit(f"scene{scene.scene_id}: first frame image not found: {input_image}")

        last_image: Path | None = None
        if args.enable_last_frame:
            last_image = resolve_path(base_dir, scene.video_last_frame)
            if last_image and not args.dry_run and not last_image.exists():
                raise SystemExit(f"scene{scene.scene_id}: last frame image not found: {last_image}")

        prompt_parts: list[str] = []
        if scene.video_motion_prompt:
            prompt_parts.append(scene.video_motion_prompt.strip())
        if scene.image_prompt:
            prompt_parts.append("シーン説明:\n" + scene.image_prompt.strip())
        prompt = "\n\n".join(prompt_parts).strip()
        vprefix = (args.video_prompt_prefix or "").strip()
        vsuffix = (args.video_prompt_suffix or "").strip()
        if vprefix:
            prompt = vprefix + "\n\n" + prompt
        if vsuffix:
            prompt = prompt + "\n\n" + vsuffix
        if args.log_prompts:
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / f"scene{scene.scene_id}_video_prompt.txt").write_text(prompt + "\n", encoding="utf-8")

        video_ref_paths: list[Path] = []
        for ref_str in scene.image_references or []:
            ref_path = resolve_path(base_dir, ref_str)
            if not ref_path:
                continue
            if not args.dry_run and not ref_path.exists():
                raise SystemExit(f"scene{scene.scene_id}: reference image not found: {ref_path}")
            video_ref_paths.append(ref_path)

        if args.video_reference_prefer_character_refstrips:
            non_char = [p for p in video_ref_paths if not _is_character_ref_path(p)]
            char = [p for p in video_ref_paths if _is_character_ref_path(p)]
            strips = [p for p in char if _is_character_refstrip_path(p, args.character_reference_strip_suffix)]
            # If any strips are available, keep only strips for character references (reduces token/bandwidth and
            # matches the intended "turnaround strip for video" workflow). Keep other non-character refs intact.
            if strips:
                video_ref_paths = non_char + strips

        if tool == "google_veo_3_1":
            segs, trim_to = _plan_veo_segments(dur)
            if len(segs) == 1:
                generate_veo_video(
                    client=gemini_client,
                    model=args.gemini_video_model,
                    prompt=prompt,
                    negative_prompt=args.video_negative_prompt or "",
                    duration_seconds=segs[0],
                    aspect_ratio=aspect_ratio,
                    resolution=args.video_resolution,
                    input_image=input_image,
                    last_frame_image=last_image,
                    reference_images=video_ref_paths,
                    out_path=out_path,
                    poll_every=args.poll_every,
                    timeout_seconds=args.timeout_seconds,
                    force=args.force,
                    log_path=log_dir / f"scene{scene.scene_id}_video.json",
                    dry_run=args.dry_run,
                )
            else:
                if args.dry_run:
                    print(f"[dry-run] VIDEO scene{scene.scene_id}: segments={segs} then trim_to={trim_to}")
                else:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        tmpdir_path = Path(tmpdir)
                        seg_paths: list[Path] = []
                        for idx, seg_dur in enumerate(segs, start=1):
                            seg_out = tmpdir_path / f"scene{scene.scene_id}_seg{idx}.mp4"
                            generate_veo_video(
                                client=gemini_client,
                                model=args.gemini_video_model,
                                prompt=prompt,
                                negative_prompt=args.video_negative_prompt or "",
                                duration_seconds=seg_dur,
                                aspect_ratio=aspect_ratio,
                                resolution=args.video_resolution,
                                input_image=input_image,
                                last_frame_image=last_image,
                                reference_images=video_ref_paths,
                                out_path=seg_out,
                                poll_every=args.poll_every,
                                timeout_seconds=args.timeout_seconds,
                                force=True,
                                log_path=log_dir / f"scene{scene.scene_id}_video_seg{idx}.json",
                                dry_run=False,
                            )
                            seg_paths.append(seg_out)

                        concat_path = tmpdir_path / f"scene{scene.scene_id}_concat.mp4"
                        _ffmpeg_concat_videos(seg_paths, concat_path)
                        if trim_to:
                            _ffmpeg_trim_video(concat_path, out_path, int(trim_to))
                        else:
                            out_path.parent.mkdir(parents=True, exist_ok=True)
                            out_path.write_bytes(concat_path.read_bytes())
        elif tool in {"kling_3_0", "kling", "kling_3_0_omni", "kling_omni", "kling-omni"}:
            if evolink_client is not None:
                if tool in {"kling_3_0_omni", "kling_omni", "kling-omni"}:
                    evolink_model = (
                        args.evolink_kling_o3_i2v_model if input_image is not None else args.evolink_kling_o3_t2v_model
                    )
                    evolink_payload = kling_omni_extra_payload or kling_extra_payload
                else:
                    evolink_model = (
                        args.evolink_kling_v3_i2v_model if input_image is not None else args.evolink_kling_v3_t2v_model
                    )
                    evolink_payload = kling_extra_payload

                generate_evolink_video(
                    client=evolink_client,
                    model=str(evolink_model),
                    prompt=prompt,
                    negative_prompt=args.video_negative_prompt or "",
                    duration_seconds=int(dur),
                    aspect_ratio=aspect_ratio,
                    resolution=args.video_resolution,
                    input_image=input_image,
                    last_frame_image=last_image,
                    extra_payload=evolink_payload,
                    out_path=out_path,
                    poll_every=args.poll_every,
                    timeout_seconds=args.timeout_seconds,
                    force=args.force,
                    log_path=log_dir / f"scene{scene.scene_id}_video.json",
                    dry_run=args.dry_run,
                )
            else:
                kling_model = args.kling_video_model
                kling_payload = kling_extra_payload
                if tool in {"kling_3_0_omni", "kling_omni", "kling-omni"}:
                    kling_model = args.kling_omni_video_model
                    kling_payload = kling_omni_extra_payload or kling_extra_payload
                generate_kling_video(
                    client=kling_client,
                    model=kling_model,
                    prompt=prompt,
                    negative_prompt=args.video_negative_prompt or "",
                    duration_seconds=int(dur),
                    aspect_ratio=aspect_ratio,
                    resolution=args.video_resolution,
                    input_image=input_image,
                    last_frame_image=last_image,
                    extra_payload=kling_payload,
                    out_path=out_path,
                    poll_every=args.poll_every,
                    timeout_seconds=args.timeout_seconds,
                    force=args.force,
                    log_path=log_dir / f"scene{scene.scene_id}_video.json",
                    dry_run=args.dry_run,
                )
        elif tool in {
            "seedance",
            "byteplus_seedance",
            "bytedance_seedance",
            "ark_seedance",
            "seadream_video",
            "seedream_video",
            "see_dream",
        }:
            seedance_model = str(args.ark_seedance_i2v_model if input_image is not None else args.ark_seedance_t2v_model)
            generate_seedance_video(
                client=seedance_client,
                model=seedance_model,
                prompt=prompt,
                duration_seconds=int(dur),
                aspect_ratio=aspect_ratio,
                resolution=args.video_resolution,
                input_image=input_image,
                last_frame_image=last_image,
                reference_images=video_ref_paths,
                generate_audio=bool(args.ark_generate_audio),
                extra_payload=ark_extra_payload,
                out_path=out_path,
                poll_every=args.poll_every,
                timeout_seconds=args.timeout_seconds,
                force=args.force,
                log_path=log_dir / f"scene{scene.scene_id}_video.json",
                dry_run=args.dry_run,
            )
        else:
            raise SystemExit(f"scene{scene.scene_id}: unsupported video tool: {scene.video_tool}")

        if args.chain_first_frame_from_prev_video:
            if args.dry_run:
                prev_chain_first_frame = out_path.with_name(out_path.stem + "_chain_first_frame.png")
            else:
                chain_frame = out_path.with_name(out_path.stem + "_chain_first_frame.png")
                try:
                    _ffmpeg_extract_frame_from_end_best_effort(
                        out_path,
                        chain_frame,
                        seconds_from_end=float(args.chain_first_frame_seconds_from_end),
                        force=args.force,
                    )
                    prev_chain_first_frame = chain_frame
                except FileNotFoundError:
                    # ffmpeg missing; chaining can't proceed.
                    prev_chain_first_frame = None

    # Pass 3: audio (TTS)
    for scene in scenes:
        if not _scene_matches_filter(scene, scene_filter):
            continue
        if _scene_is_deleted(scene):
            continue

        if args.skip_audio or not scene.narration_output:
            continue

        dur = int(scene.duration_seconds) if scene.duration_seconds is not None else duration_from_timestamp_range(scene.timestamp, args.default_scene_seconds)
        out_path = resolve_path(base_dir, scene.narration_output)
        if not out_path:
            raise SystemExit(f"scene{scene.scene_id}: missing narration output path")

        tool = normalize_tool_name((args.override_narration_tool or "").strip() or scene.narration_tool)
        if tool == "elevenlabs":
            narration_source = scene.narration_tts_text or scene.narration_text
            if not narration_source:
                raise SystemExit(f"scene{scene.scene_id}: missing narration text for ElevenLabs TTS")
            tts_text = narration_source.strip()
            tprefix = (args.tts_prompt_prefix or "").strip()
            tsuffix = (args.tts_prompt_suffix or "").strip()
            if tprefix:
                tts_text = tprefix + "\n\n" + tts_text
            if tsuffix:
                tts_text = tts_text + "\n\n" + tsuffix
            normalize_dur = dur if scene.narration_normalize_to_scene_duration else None
            generate_elevenlabs_tts(
                client=elevenlabs_client,
                voice_id=str((args.elevenlabs_voice_id or DEFAULT_ELEVENLABS_VOICE_ID)),
                model_id=args.elevenlabs_model_id or "eleven_multilingual_v2",
                output_format=args.elevenlabs_output_format or "mp3_44100_128",
                text=tts_text,
                out_path=out_path,
                duration_seconds=normalize_dur,
                force=args.force,
                request_log_path=log_dir / f"scene{scene.scene_id}_tts_request.json",
                dry_run=args.dry_run,
            )
        elif tool in {"macos_say", "say"}:
            narration_source = scene.narration_tts_text or scene.narration_text
            if not narration_source:
                raise SystemExit(f"scene{scene.scene_id}: missing narration text for macos_say TTS")
            tts_text = narration_source.strip()
            tprefix = (args.tts_prompt_prefix or "").strip()
            tsuffix = (args.tts_prompt_suffix or "").strip()
            if tprefix:
                tts_text = tprefix + "\n\n" + tts_text
            if tsuffix:
                tts_text = tts_text + "\n\n" + tsuffix
            generate_macos_say_tts(
                text=tts_text,
                out_path=out_path,
                voice=(args.macos_say_voice or "").strip() or None,
                force=args.force,
                dry_run=args.dry_run,
            )
        elif tool in {"silent", "tbd", ""}:
            if args.dry_run:
                print(f"[dry-run] AUDIO {out_path} <- placeholder (tool={scene.narration_tool})")
            else:
                _ffmpeg_write_silence_mp3(out_path, dur, args.force)
        else:
            raise SystemExit(f"scene{scene.scene_id}: unsupported narration tool: {scene.narration_tool}")

    write_run_index(base_dir)
    print("Done.")


if __name__ == "__main__":
    main()
