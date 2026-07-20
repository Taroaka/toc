#!/usr/bin/env python3
"""
Generate assets (image/video/audio) from a `video_manifest.md`.

- Image: Codex built-in image generation (gpt-image-2 via the Codex app-server)
- Video: Kling (kling_3_0 / kling_3_0_omni) or BytePlus ModelArk Seedance. Any Veo tool names are treated as Kling for safety.

Audio (TTS):
- ElevenLabs Text-to-Speech API
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

try:
    import yaml  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.env import load_env_files
from toc.asset_prompt_compiler import ASSET_PROMPT_COMPILER_VERSION
from toc.harness import append_state_snapshot, load_structured_document, parse_state_file
from toc.http import HttpError, request_bytes
from toc.image_prompt_compiler import (
    IMAGE_API_PROMPT_POLICY_VERSION as IMAGE_API_PROMPT_POLICY_VERSION_V2,
    compile_image_api_prompt_v2,
)
from toc.video_prompt_compiler import (
    VIDEO_API_PROMPT_POLICY_VERSION,
    VIDEO_REFERENCE_ROLE_INSTRUCTIONS,
    compile_video_api_prompt_v1,
    compose_video_render_unit_contract,
)
from toc.video_prompt_projection_registry import resolve_video_prompt_contract
from toc.video_provider_capabilities import resolve_video_provider_capabilities
from toc.image_request_snapshot import (
    ImageRequestSnapshotError,
    load_request_snapshot,
    match_output_provenance,
    materialize_request_snapshot,
    sha256_file,
    sha256_text,
    sha256_canonical_json,
    write_request_snapshot_atomic,
)
from toc.immersive_manifest import (
    dotted_id_slug,
    is_non_renderable_manifest_node,
    make_scene_cut_selector,
    normalize_dotted_id,
    parse_scene_selectors,
    scene_selector_tokens,
    selector_matches,
)
from toc.providers.elevenlabs import (
    DEFAULT_ELEVENLABS_LANGUAGE_CODE,
    DEFAULT_ELEVENLABS_VOICE_ID,
    ElevenLabsClient,
    ElevenLabsConfig,
    parse_pronunciation_dictionary_locators,
)
from toc.providers.evolink import EvoLinkClient, EvoLinkConfig
from toc.providers.gemini import GeminiClient, GeminiConfig
from toc.providers.kling import KlingClient, KlingConfig
from toc.providers.seedance import SeedanceClient, SeedanceConfig
from toc.providers.seadream import SeaDreamClient, SeaDreamConfig
from toc.narration_revision import REVISION_SCHEMA_VERSION
from toc.run_index import write_run_index
from toc.runtime_locks import async_file_lock, async_file_slot
from toc.stage_evaluator import check_manifest_single
from toc.tts_text import load_pronunciation_aliases, prepare_elevenlabs_tts_text
from server.codex_app_server import (
    create_codex_app_server_client,
    app_server_disabled,
    reject_local_raster_image_result,
)
from server.image_gen import copy_saved_image, write_app_server_image_debug_log


ALLOWED_VEO_DURATIONS = (4, 6, 8)
VIDEO_GENERATION_DURATION_MAX_SECONDS = 60
RENDER_UNIT_VIDEO_INPUT_CONTRACT_VERSION = "render_unit_video_input_v1"
VIDEO_OUTPUT_PROVENANCE_SCHEMA_VERSION = "video_output_provenance_v1"
CODEX_BUILTIN_IMAGE_TOOL = "codex_builtin_image"
CODEX_BUILTIN_IMAGE_TOOL_ALIASES = {
    CODEX_BUILTIN_IMAGE_TOOL,
    "codex_app_server",
    "gpt_image_2",
    "gpt-image-2",
    "openai_gpt_image_2",
    "openai_gpt-image-2",
}


def _manifest_has_revision_aware_narration(yaml_text: str) -> bool:
    """Return whether audio must use the candidate/CAS frontend lifecycle."""

    data = yaml.safe_load(yaml_text) if yaml is not None else None
    if not isinstance(data, dict):
        return False
    for scene in data.get("scenes") or []:
        if not isinstance(scene, dict) or is_non_renderable_manifest_node(scene):
            continue
        declared_cuts = scene.get("cuts")
        nodes = declared_cuts if isinstance(declared_cuts, list) and declared_cuts else [scene]
        for node in nodes:
            if not isinstance(node, dict) or is_non_renderable_manifest_node(node):
                continue
            audio = node.get("audio") if isinstance(node.get("audio"), dict) else {}
            narration = audio.get("narration") if isinstance(audio.get("narration"), dict) else {}
            revision = narration.get("revision") if isinstance(narration.get("revision"), dict) else {}
            if str(revision.get("schema_version") or "") == REVISION_SCHEMA_VERSION:
                return True
    return False


IMAGE_API_PROMPT_POLICY_VERSION = "image_api_prompt_v1"
SUPPORTED_IMAGE_API_PROMPT_POLICY_VERSIONS = {
    IMAGE_API_PROMPT_POLICY_VERSION,
    IMAGE_API_PROMPT_POLICY_VERSION_V2,
}
NO_REFERENCE_IMAGE_EXECUTION_LANE = "bootstrap_builtin"
NO_REFERENCE_IMAGE_EXECUTION_LANE_ALIASES = {"bootstrap_builtin", "no_reference_builtin"}
DEPRECATED_EXTERNAL_IMAGE_TOOLS = {
    "google_nanobanana_2",
    "nanobanana_2",
    "gemini_3_1_flash_image",
    "gemini3_1_flash_image",
    "gemini_3.1_flash_image",
    "gemini-3.1-flash-image",
    "seadream",
    "seedream",
    "seedream_4_5",
    "byteplus_seedream_4_5",
}
REFERENCE_DRIVEN_IMAGE_TOOLS = CODEX_BUILTIN_IMAGE_TOOL_ALIASES | DEPRECATED_EXTERNAL_IMAGE_TOOLS
_UNSET = object()


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
    video_tool: str | None
    video_input_image: str | None
    video_first_frame: str | None
    video_last_frame: str | None
    video_motion_prompt: str | None
    video_output: str | None
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
    image_asset_id: str | None = None
    image_asset_type: str | None = None
    image_execution_lane: str | None = None
    image_bootstrap_allowed: bool = False
    image_bootstrap_reason: str | None = None
    image_review_status: str | None = None
    still_image_generation_status: str | None = None
    still_image_plan_source: str | None = None
    cut_status: str | None = None
    deletion_reason: str | None = None
    manifest_cut_id: str | None = None
    cut_contract: dict[str, Any] = field(default_factory=dict)
    image_api_prompt_payload: dict[str, Any] = field(default_factory=dict)
    image_applied_request_ids: list[str] = field(default_factory=list)
    video_applied_request_ids: list[str] = field(default_factory=list)
    image_first_frame_visual_plan: dict[str, Any] = field(default_factory=dict)
    story_time: str = ""
    scene_time_of_day: str = ""
    scene_time_of_day_visual_basis: Any = None
    scene_location_mode: str = ""
    scene_location_sequence: list[Any] = field(default_factory=list)
    scene_location_segments: list[dict[str, Any]] = field(default_factory=list)
    video_prompt_authoring_source: str | None = None
    video_api_prompt_payload: dict[str, Any] = field(default_factory=dict)
    video_references: list[str] = field(default_factory=list)
    video_generation_contract: dict[str, Any] = field(default_factory=dict)
    video_quality: str | None = None
    video_aspect_ratio: str | None = None
    video_reference_roles: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class VideoRenderTargetSpec:
    selector: str
    manifest_scene_id: str
    unit_id: str | None
    source_cut_ids: list[str]
    source_selectors: list[str]
    source_scenes: list[SceneSpec]
    video_tool: str | None
    video_input_image: str | None
    video_first_frame: str | None
    video_last_frame: str | None
    video_motion_prompt: str | None
    video_output: str | None
    video_applied_request_ids: list[str]
    duration_seconds: int | None
    timestamp: str | None
    reference_id: str | None = None
    video_cut_contract: dict[str, Any] = field(default_factory=dict)
    video_prompt_authoring_source: str | None = None
    video_api_prompt_payload: dict[str, Any] = field(default_factory=dict)
    video_references: list[str] = field(default_factory=list)
    video_generation_contract: dict[str, Any] = field(default_factory=dict)
    video_quality: str | None = None
    video_aspect_ratio: str | None = None
    video_input_mode: str | None = None
    video_reference_roles: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ReferenceVariantSpec:
    variant_id: str | None
    reference_images: list[str]
    fixed_prompts: list[str]
    appearance_continuity: dict[str, Any]
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
    appearance_continuity: dict[str, Any]
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


def _as_opt_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in {"true", "yes", "1", "on"}:
        return True
    if s in {"false", "no", "0", "off"}:
        return False
    return None


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _node_cut_contract(node: dict[str, Any]) -> dict[str, Any]:
    for key in ("cut_contract", "scene_contract", "cut_blueprint"):
        value = node.get(key) if isinstance(node, dict) else None
        if isinstance(value, dict) and value:
            return dict(value)
    return {}


def _contract_value(contract: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        cur: Any = contract
        ok = True
        for key in path.split("."):
            if not isinstance(cur, dict) or key not in cur:
                ok = False
                break
            cur = cur[key]
        if ok and cur not in (None, "", [], {}):
            return cur
    return None


def _contract_text(contract: dict[str, Any], *paths: str) -> str:
    value = _contract_value(contract, *paths)
    return str(value).strip() if value is not None else ""


def _contract_list(contract: dict[str, Any], *paths: str) -> list[str]:
    for path in paths:
        value = _contract_value(contract, path)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
    return []


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
                appearance_continuity=_parse_appearance_continuity(
                    item.get("appearance_continuity")
                ),
                notes=_as_opt_str(item.get("notes")),
            )
        )
    return variants


def _parse_appearance_continuity(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    costume_state = _as_opt_str(value.get("costume_state"))
    forbidden_costume_states = _ensure_str_list(
        value.get("forbidden_costume_states")
    )
    if not costume_state:
        return {}
    return {
        "costume_state": costume_state,
        "forbidden_costume_states": forbidden_costume_states,
    }


def _as_opt_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def _canonical_video_duration_seconds(node: dict[str, Any]) -> int | None:
    render = _dict_value(node.get("render"))
    video_generation = _dict_value(node.get("video_generation"))
    for value in (
        render.get("video_duration_seconds"),
        video_generation.get("duration_seconds"),
        node.get("duration_seconds"),
    ):
        parsed = _as_opt_int(value)
        if parsed is not None:
            return parsed
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
                    appearance_continuity=_parse_appearance_continuity(
                        item.get("appearance_continuity")
                    ),
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


def _derive_asset_type_from_output(image_output: str | None) -> str | None:
    norm = str(image_output or "").replace("\\", "/")
    if "/assets/characters/" in f"/{norm}":
        return "character_reference"
    if "/assets/objects/" in f"/{norm}":
        return "object_reference"
    if "/assets/locations/" in f"/{norm}":
        return "location_anchor"
    if "/assets/scenes/" in f"/{norm}":
        return "reusable_still"
    return None


def _extract_asset_stage_image_metadata(
    *,
    raw_node: dict[str, Any],
    still_assets: list[dict[str, Any]],
    image_output: str | None,
) -> dict[str, Any]:
    primary_still = _select_primary_still_asset(still_assets)
    primary_ig = primary_still.get("image_generation") if isinstance(primary_still, dict) and isinstance(primary_still.get("image_generation"), dict) else {}
    scene_ig = raw_node.get("image_generation") if isinstance(raw_node.get("image_generation"), dict) else {}

    asset_id = None
    asset_type = None
    review_status = None
    execution_lane = None
    bootstrap_allowed = None
    bootstrap_reason = None

    if isinstance(primary_still, dict):
        asset_id = _as_opt_str(primary_still.get("asset_id"))
        asset_type = _as_opt_str(primary_still.get("asset_type"))
        review = primary_still.get("review") if isinstance(primary_still.get("review"), dict) else {}
        review_status = _as_opt_str(review.get("status"))
        execution_lane = _as_opt_str(primary_still.get("execution_lane")) or _as_opt_str(primary_ig.get("execution_lane"))
        bootstrap_allowed = _as_opt_bool(primary_still.get("bootstrap_allowed"))
        if bootstrap_allowed is None:
            bootstrap_allowed = _as_opt_bool(primary_ig.get("bootstrap_allowed"))
        bootstrap_reason = _as_opt_str(primary_still.get("bootstrap_reason")) or _as_opt_str(primary_ig.get("bootstrap_reason"))

    scene_review = scene_ig.get("review") if isinstance(scene_ig.get("review"), dict) else {}
    asset_type = asset_type or _derive_asset_type_from_output(image_output)
    review_status = review_status or _as_opt_str(scene_review.get("status"))
    execution_lane = execution_lane or _as_opt_str(scene_ig.get("execution_lane"))
    if bootstrap_allowed is None:
        bootstrap_allowed = _as_opt_bool(scene_ig.get("bootstrap_allowed"))
    bootstrap_reason = bootstrap_reason or _as_opt_str(scene_ig.get("bootstrap_reason"))

    return {
        "asset_id": asset_id,
        "asset_type": asset_type,
        "execution_lane": execution_lane,
        "bootstrap_allowed": bool(bootstrap_allowed) if bootstrap_allowed is not None else False,
        "bootstrap_reason": bootstrap_reason,
        "review_status": review_status,
    }


def _normalize_execution_lane(execution_lane: str | None) -> str | None:
    normalized = str(execution_lane or "").strip().lower().replace(" ", "_")
    if not normalized:
        return None
    if normalized in NO_REFERENCE_IMAGE_EXECUTION_LANE_ALIASES:
        return NO_REFERENCE_IMAGE_EXECUTION_LANE
    return normalized


def _infer_image_execution_lane(*, references: list[str] | None) -> str:
    if list(references or []):
        return "standard"
    return NO_REFERENCE_IMAGE_EXECUTION_LANE


def _effective_image_execution_lane(scene: SceneSpec) -> str:
    return _infer_image_execution_lane(references=scene.image_references)


def _validate_image_execution_lane(scene: SceneSpec) -> None:
    explicit_lane = _normalize_execution_lane(scene.image_execution_lane)
    if explicit_lane is None:
        return
    expected_lane = _effective_image_execution_lane(scene)
    if explicit_lane == expected_lane:
        return
    raise SystemExit(
        f"{scene.selector or scene.scene_id}: execution_lane mismatch: "
        f"declared `{explicit_lane}` but this repo expects `{expected_lane}` "
        "from the current reference count"
    )


def _no_reference_image_lane_error(*, scene: SceneSpec, tool: str) -> str:
    selector = scene.selector or str(scene.scene_id)
    return (
        f"NO_REFERENCE_IMAGE_LANE_REQUIRED {selector}: `{tool}` cannot run in this repo "
        "without at least one resolved reference image. "
        "Route no-reference image work through Codex built-in image generation "
        f"(execution_lane=`{NO_REFERENCE_IMAGE_EXECUTION_LANE}`) instead. "
        "Use $toc-no-reference-image-runner for general no-reference image requests, "
        "or $toc-p500-bootstrap-image-runner for p500 asset seeds."
    )


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


def _video_target_log_slug(target: VideoRenderTargetSpec) -> str:
    return dotted_id_slug(target.selector or target.manifest_scene_id)


def _video_target_reference_strings(target: VideoRenderTargetSpec) -> list[str]:
    if target.video_references:
        return _dedupe_keep_order(list(target.video_references))
    refs: list[str] = []
    for scene in target.source_scenes:
        refs.extend(list(scene.video_references or []))
    # Image-prompt references are inputs for composing the approved first frame;
    # they are not implicit auxiliary inputs to the video provider. Video
    # references must be declared explicitly in video_generation.references.
    return _dedupe_keep_order(refs)


def _effective_video_target_reference_strings(
    target: VideoRenderTargetSpec,
    *,
    prefer_character_refstrips: bool,
    character_reference_strip_suffix: str,
) -> list[str]:
    refs = _video_target_reference_strings(target)
    if not prefer_character_refstrips:
        return refs
    non_character = [ref for ref in refs if not _is_character_ref_path(Path(ref))]
    character = [ref for ref in refs if _is_character_ref_path(Path(ref))]
    strips = [
        ref
        for ref in character
        if _is_character_refstrip_path(Path(ref), character_reference_strip_suffix)
    ]
    return _dedupe_keep_order([*non_character, *strips]) if strips else refs


def _video_target_first_frame_path(base_dir: Path, target: VideoRenderTargetSpec) -> Path | None:
    if (target.video_input_mode or "").strip() == "reference_images":
        return None
    first_frame = _resolve_run_confined_video_path(
        base_dir=base_dir,
        maybe_path=target.video_first_frame or target.video_input_image,
        selector=target.selector,
        role="first frame",
    )
    if first_frame is not None:
        return first_frame
    for scene in target.source_scenes:
        candidate = _resolve_run_confined_video_path(
            base_dir=base_dir,
            maybe_path=scene.video_first_frame or scene.video_input_image,
            selector=target.selector,
            role="first frame",
        )
        if candidate is not None:
            return candidate
        if scene.image_output:
            candidate = _resolve_run_confined_video_path(
                base_dir=base_dir,
                maybe_path=scene.image_output,
                selector=target.selector,
                role="first frame",
            )
            if candidate is not None:
                return candidate
    return None


def _video_target_last_frame_path(base_dir: Path, target: VideoRenderTargetSpec) -> Path | None:
    if (target.video_input_mode or "").strip() == "reference_images":
        return None
    last_frame = _resolve_run_confined_video_path(
        base_dir=base_dir,
        maybe_path=target.video_last_frame,
        selector=target.selector,
        role="last frame",
    )
    if last_frame is not None:
        return last_frame
    for scene in reversed(target.source_scenes):
        candidate = _resolve_run_confined_video_path(
            base_dir=base_dir,
            maybe_path=scene.video_last_frame,
            selector=target.selector,
            role="last frame",
        )
        if candidate is not None:
            return candidate
    return None


def _effective_video_target_frame_paths(
    base_dir: Path,
    ordered_targets: list[VideoRenderTargetSpec],
    index: int,
    *,
    chain_first_frame_from_prev_video: bool,
    enable_last_frame: bool,
) -> tuple[Path | None, Path | None]:
    target = ordered_targets[index]
    first_frame = _video_target_first_frame_path(base_dir, target)
    if (
        chain_first_frame_from_prev_video
        and index > 0
        and (target.video_input_mode or "").strip() != "reference_images"
    ):
        previous_output = _resolve_run_confined_video_path(
            base_dir=base_dir,
            maybe_path=ordered_targets[index - 1].video_output,
            selector=target.selector,
            role="previous video output",
        )
        if previous_output is None:
            raise SystemExit(
                f"{target.selector}: previous video output is required for chained first frame"
            )
        first_frame = previous_output.with_name(
            previous_output.stem + "_chain_first_frame.png"
        )
    last_frame = _video_target_last_frame_path(base_dir, target) if enable_last_frame else None
    return first_frame, last_frame


def _video_binding_path(base_dir: Path, value: Path | None) -> str:
    if value is None:
        return ""
    try:
        return value.resolve().relative_to(base_dir.resolve()).as_posix()
    except ValueError as exc:
        raise SystemExit(
            "video input must be a run-relative path confined to the manifest directory: "
            f"{value}"
        ) from exc


def _cut_contract_first_frame_observed_state_block(contract: dict[str, Any]) -> str:
    first_frame = contract.get("first_frame_contract") if isinstance(contract.get("first_frame_contract"), dict) else {}
    continuity = contract.get("continuity_contract") if isinstance(contract.get("continuity_contract"), dict) else {}
    if not first_frame and not continuity:
        return ""
    visible_start_state = first_frame.get("visible_start_state") if isinstance(first_frame.get("visible_start_state"), dict) else {}
    affordance = first_frame.get("motion_start_affordance") if isinstance(first_frame.get("motion_start_affordance"), dict) else {}
    start_state = continuity.get("start_state") if isinstance(continuity.get("start_state"), dict) else {}
    anchors = continuity.get("carry_forward_to_next_cut") if isinstance(continuity.get("carry_forward_to_next_cut"), list) else []
    lines = ["first_frame_observed_state:"]
    brief = _contract_text(contract, "first_frame_contract.first_frame_brief", "first_frame_brief")
    if brief:
        lines.append(f"  first_frame_brief: {brief}")
    for key in ("character_state", "prop_state", "spatial_state", "emotional_state", "gaze_or_attention"):
        value = str(visible_start_state.get(key) or start_state.get(key) or "").strip()
        if value:
            lines.append(f"  {key}: {value}")
    for key in ("movable_subject", "movement_vector", "camera_start_reason"):
        value = str(affordance.get(key) or "").strip()
        if value:
            lines.append(f"  {key}: {value}")
    anchor_terms = [str(item).strip() for item in anchors if str(item).strip()]
    if anchor_terms:
        lines.append("  continuity_anchors: " + " / ".join(anchor_terms))
    return "\n".join(lines) if len(lines) > 1 else ""


def _video_target_first_frame_context_blocks(target: VideoRenderTargetSpec) -> list[str]:
    blocks: list[str] = []
    for scene in target.source_scenes:
        block = _cut_contract_first_frame_observed_state_block(scene.cut_contract)
        if block:
            blocks.append(block)
    return _dedupe_keep_order(blocks)


def _video_target_has_prompt_source(target: VideoRenderTargetSpec) -> bool:
    motion_contract = target.video_generation_contract.get("motion_contract")
    return bool(
        (target.video_prompt_authoring_source or "").strip()
        or (target.video_motion_prompt or "").strip()
        or (isinstance(motion_contract, dict) and motion_contract)
        or _video_target_first_frame_context_blocks(target)
    )


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
            if key in {"topic", "time", "aspect_ratio", "resolution"}:
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
                image_api_prompt_payload={},
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
                manifest_cut_id=None,
            )
            continue

        if not current:
            continue

        # per-scene fields
        if key == "timestamp" and "scenes" in context_keys:
            current.timestamp = _parse_yaml_scalar(value)
            continue
        if (
            key == "time_of_day"
            and "scenes" in context_keys
            and len(context_keys) >= 2
            and context_keys[-2] == "scene_id"
        ):
            current.scene_time_of_day = _parse_yaml_scalar(value) or ""
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
            elif key == "prompt_authoring_source":
                current.video_prompt_authoring_source = (
                    value if "\n" in value else (_parse_yaml_scalar(value) or value)
                )
            elif key == "references":
                current.video_references = _parse_inline_yaml_list(value)
            elif key == "quality":
                current.video_quality = _parse_yaml_scalar(value)
            elif key == "aspect_ratio":
                current.video_aspect_ratio = _parse_yaml_scalar(value)
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
        for key in ("topic", "time", "experience", "aspect_ratio", "resolution"):
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
        scene_time_of_day = _as_opt_str(raw_scene.get("time_of_day")) or ""
        scene_time_of_day_visual_basis = deepcopy(
            raw_scene.get("time_of_day_visual_basis")
        )
        scene_location_mode = _as_opt_str(raw_scene.get("location_mode")) or ""
        scene_location_sequence = list(
            raw_scene.get("location_sequence")
            if isinstance(raw_scene.get("location_sequence"), list)
            else []
        )
        scene_location_segments = [
            dict(value)
            for value in (
                raw_scene.get("location_segments")
                if isinstance(raw_scene.get("location_segments"), list)
                else []
            )
            if isinstance(value, dict)
        ]
        scene_kind = _as_opt_str(raw_scene.get("kind"))
        reference_id = _as_opt_str(raw_scene.get("reference_id")) or _as_opt_str(raw_scene.get("character_reference_id"))
        scene_duration_seconds = _canonical_video_duration_seconds(raw_scene)

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
                cut_duration_seconds = _canonical_video_duration_seconds(raw_cut)
                image_tool = _as_opt_str(ig.get("tool")) if isinstance(ig, dict) else None
                image_prompt = _as_opt_str(ig.get("prompt")) if isinstance(ig, dict) else None
                image_api_prompt_payload = ig.get("api_prompt_payload") if isinstance(ig.get("api_prompt_payload"), dict) else {}
                image_first_frame_visual_plan = (
                    ig.get("first_frame_visual_plan")
                    if isinstance(ig.get("first_frame_visual_plan"), dict)
                    else {}
                )
                cut_contract = _node_cut_contract(raw_cut)
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
                image_stage_meta = _extract_asset_stage_image_metadata(
                    raw_node=raw_cut,
                    still_assets=cut_still_assets,
                    image_output=image_output,
                )

                video_tool = _as_opt_str(vg.get("tool")) if isinstance(vg, dict) else None
                video_input_image = _as_opt_str(vg.get("input_image")) if isinstance(vg, dict) else None
                video_first_frame = _as_opt_str(vg.get("first_frame")) if isinstance(vg, dict) else None
                video_last_frame = _as_opt_str(vg.get("last_frame")) if isinstance(vg, dict) else None
                video_motion_prompt = _as_opt_str(vg.get("motion_prompt")) if isinstance(vg, dict) else None
                video_prompt_authoring_source = (
                    _as_opt_str(vg.get("prompt_authoring_source"))
                    if isinstance(vg, dict)
                    else None
                )
                video_api_prompt_payload = (
                    dict(vg.get("api_prompt_payload"))
                    if isinstance(vg.get("api_prompt_payload"), dict)
                    else {}
                )
                video_references = _ensure_str_list(vg.get("references")) if isinstance(vg, dict) else []
                video_quality = _as_opt_str(vg.get("quality")) if isinstance(vg, dict) else None
                video_aspect_ratio = _as_opt_str(vg.get("aspect_ratio")) if isinstance(vg, dict) else None
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
                        image_api_prompt_payload=dict(image_api_prompt_payload),
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
                        video_prompt_authoring_source=video_prompt_authoring_source,
                        video_api_prompt_payload=video_api_prompt_payload,
                        video_references=video_references,
                        video_generation_contract=dict(vg),
                        video_quality=video_quality,
                        video_aspect_ratio=video_aspect_ratio,
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
                        image_asset_id=image_stage_meta["asset_id"],
                        image_asset_type=image_stage_meta["asset_type"],
                        image_execution_lane=image_stage_meta["execution_lane"],
                        image_bootstrap_allowed=image_stage_meta["bootstrap_allowed"],
                        image_bootstrap_reason=image_stage_meta["bootstrap_reason"],
                        image_review_status=image_stage_meta["review_status"],
                        still_image_generation_status=still_image_generation_status,
                        still_image_plan_source=still_image_plan_source,
                        cut_status=cut_status,
                        deletion_reason=deletion_reason,
                        manifest_cut_id=cut_id,
                        cut_contract=cut_contract,
                        image_first_frame_visual_plan=dict(image_first_frame_visual_plan),
                        scene_time_of_day=scene_time_of_day,
                        scene_time_of_day_visual_basis=scene_time_of_day_visual_basis,
                        scene_location_mode=scene_location_mode,
                        scene_location_sequence=list(scene_location_sequence),
                        scene_location_segments=deepcopy(scene_location_segments),
                        video_reference_roles=[
                            dict(value)
                            for value in _list_value(vg.get("reference_roles"))
                            if isinstance(value, dict)
                        ],
                    )
                )
            continue

        ig, image_output = _effective_image_generation(raw_scene, scene_still_assets)
        vg = raw_scene.get("video_generation") if isinstance(raw_scene.get("video_generation"), dict) else {}
        image_tool = _as_opt_str(ig.get("tool")) if isinstance(ig, dict) else None
        image_prompt = _as_opt_str(ig.get("prompt")) if isinstance(ig, dict) else None
        image_api_prompt_payload = ig.get("api_prompt_payload") if isinstance(ig.get("api_prompt_payload"), dict) else {}
        image_first_frame_visual_plan = (
            ig.get("first_frame_visual_plan")
            if isinstance(ig.get("first_frame_visual_plan"), dict)
            else {}
        )
        cut_contract = _node_cut_contract(raw_scene)
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
        image_stage_meta = _extract_asset_stage_image_metadata(
            raw_node=raw_scene,
            still_assets=scene_still_assets,
            image_output=image_output,
        )

        video_tool = _as_opt_str(vg.get("tool")) if isinstance(vg, dict) else None
        video_input_image = _as_opt_str(vg.get("input_image")) if isinstance(vg, dict) else None
        video_first_frame = _as_opt_str(vg.get("first_frame")) if isinstance(vg, dict) else None
        video_last_frame = _as_opt_str(vg.get("last_frame")) if isinstance(vg, dict) else None
        video_motion_prompt = _as_opt_str(vg.get("motion_prompt")) if isinstance(vg, dict) else None
        video_prompt_authoring_source = (
            _as_opt_str(vg.get("prompt_authoring_source"))
            if isinstance(vg, dict)
            else None
        )
        video_api_prompt_payload = (
            dict(vg.get("api_prompt_payload"))
            if isinstance(vg.get("api_prompt_payload"), dict)
            else {}
        )
        video_references = _ensure_str_list(vg.get("references")) if isinstance(vg, dict) else []
        video_quality = _as_opt_str(vg.get("quality")) if isinstance(vg, dict) else None
        video_aspect_ratio = _as_opt_str(vg.get("aspect_ratio")) if isinstance(vg, dict) else None
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
                image_api_prompt_payload=dict(image_api_prompt_payload),
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
                video_prompt_authoring_source=video_prompt_authoring_source,
                video_api_prompt_payload=video_api_prompt_payload,
                video_references=video_references,
                video_generation_contract=dict(vg),
                video_quality=video_quality,
                video_aspect_ratio=video_aspect_ratio,
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
                image_asset_id=image_stage_meta["asset_id"],
                image_asset_type=image_stage_meta["asset_type"],
                image_execution_lane=image_stage_meta["execution_lane"],
                image_bootstrap_allowed=image_stage_meta["bootstrap_allowed"],
                image_bootstrap_reason=image_stage_meta["bootstrap_reason"],
                image_review_status=image_stage_meta["review_status"],
                still_image_generation_status=still_image_generation_status,
                still_image_plan_source=still_image_plan_source,
                cut_status=cut_status,
                deletion_reason=deletion_reason,
                manifest_cut_id=None,
                cut_contract=cut_contract,
                image_first_frame_visual_plan=dict(image_first_frame_visual_plan),
                scene_time_of_day=scene_time_of_day,
                scene_time_of_day_visual_basis=scene_time_of_day_visual_basis,
                scene_location_mode=scene_location_mode,
                scene_location_sequence=list(scene_location_sequence),
                scene_location_segments=deepcopy(scene_location_segments),
                video_reference_roles=[
                    dict(value)
                    for value in _list_value(vg.get("reference_roles"))
                    if isinstance(value, dict)
                ],
            )
        )

    return metadata, assets, scenes


def parse_manifest_yaml_full(yaml_text: str) -> tuple[dict, AssetGuides, list[SceneSpec]]:
    try:
        metadata, assets, scenes = _parse_manifest_yaml_pyyaml(yaml_text)
    except Exception:
        metadata, scenes = _parse_manifest_yaml_minimal(yaml_text)
        assets = AssetGuides(character_bible=[], style_guide=None, object_bible=[], location_bible=[])
    story_time = str(metadata.get("time") or "").strip()
    for scene in scenes:
        scene.story_time = story_time
        _bind_scene_character_appearance_from_guides(scene=scene, guides=assets)
    return metadata, assets, scenes


def _bind_scene_character_appearance_from_guides(
    *, scene: SceneSpec, guides: AssetGuides
) -> None:
    """Project selected bible appearance state into a stored v2 visual plan."""

    plan = scene.image_first_frame_visual_plan
    if not isinstance(plan, dict) or not plan:
        return
    chosen_character_ids = set(scene.image_character_ids or [])
    selected_variant_ids = set(scene.image_character_variant_ids or [])
    resolved: list[dict[str, Any]] = []
    for entry in guides.character_bible or []:
        character_id = str(entry.character_id or "").strip()
        selected_variants = _selected_reference_variants(
            entry.reference_variants, selected_variant_ids
        )
        if selected_variants and (
            not character_id or character_id not in chosen_character_ids
        ):
            raise ValueError(
                "image_character_appearance_variant_character_unbound: "
                + (character_id or "<missing>")
            )
        if not selected_variants and character_id not in chosen_character_ids:
            continue
        appearance_sources = [
            dict(variant.appearance_continuity or {})
            for variant in selected_variants
            if variant.appearance_continuity
        ]
        if len(appearance_sources) > 1:
            raise ValueError(
                f"image_character_appearance_variant_conflict: {character_id}"
            )
        appearance = (
            appearance_sources[0]
            if appearance_sources
            else dict(entry.appearance_continuity or {})
        )
        if not appearance:
            continue
        character_name = next(
            (
                str(alias).strip()
                for alias in entry.review_aliases or []
                if str(alias).strip()
            ),
            character_id,
        )
        resolved.append(
            {
                "character_id": character_id,
                "character_name": character_name,
                "appearance_continuity": appearance,
            }
        )
    if not resolved:
        return

    gate = deepcopy(_dict_value(plan.get("character_state_gate")))
    raw_existing = gate.get("character_states", [])
    if not isinstance(raw_existing, list):
        raise ValueError("image_character_state_bindings_require_sequence")
    existing = [deepcopy(item) for item in raw_existing if isinstance(item, dict)]
    if len(existing) != len(raw_existing):
        raise ValueError("image_character_state_binding_invalid")
    existing_by_id = {
        str(item.get("character_id") or "").strip(): item for item in existing
    }
    for binding in resolved:
        character_id = binding["character_id"]
        previous = existing_by_id.get(character_id)
        if previous is not None and previous != binding:
            raise ValueError(
                f"image_character_appearance_binding_mismatch: {character_id}"
            )
        if previous is None:
            existing.append(binding)
    gate["character_states"] = existing
    plan["character_state_gate"] = gate

    reference_binding = deepcopy(_dict_value(plan.get("reference_binding")))
    references = reference_binding.get("character_references", [])
    if isinstance(references, list):
        identity_by_id = {
            binding["character_id"]: binding["character_name"]
            for binding in resolved
        }
        for reference in references:
            if not isinstance(reference, dict):
                continue
            character_id = str(
                reference.get("target_character_id") or ""
            ).strip()
            identity_name = identity_by_id.get(character_id)
            if identity_name:
                reference["target_identity_name"] = identity_name
        reference_binding["character_references"] = references
        plan["reference_binding"] = reference_binding
    scene.image_first_frame_visual_plan = plan


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


def _render_unit_selector(scene_id: str, unit_id: str) -> str:
    return f"scene{scene_id}_unit{unit_id}"


def _scene_has_explicit_render_units(raw_scene: Any) -> bool:
    return isinstance(raw_scene, dict) and isinstance(raw_scene.get("render_units"), list) and bool(raw_scene.get("render_units"))


def _scene_is_deleted(scene: SceneSpec) -> bool:
    return (scene.cut_status or "").strip().lower() == "deleted"


def _render_unit_video_input_contract(node: dict[str, Any]) -> dict[str, Any]:
    raw_contract = node.get("video_input_contract")
    if isinstance(raw_contract, dict) and raw_contract:
        return {
            "schema_version": str(raw_contract.get("schema_version") or "").strip(),
            "input_mode": str(raw_contract.get("input_mode") or "").strip(),
            "required_references": [
                str(value).strip()
                for value in _list_value(raw_contract.get("required_references"))
                if str(value).strip()
            ],
            "reference_roles": deepcopy(
                _list_value(raw_contract.get("reference_roles"))
            ),
            "explicit": True,
        }
    storyboard_image = str(node.get("storyboard_image") or "").strip()
    if not storyboard_image:
        return {}
    return {
        "schema_version": "legacy_storyboard_binding",
        "input_mode": "legacy_frame_plus_reference",
        "required_references": [],
        "reference_roles": [],
        "explicit": False,
    }


def _render_unit_video_input_issues(
    *, selector: str, node: dict[str, Any]
) -> list[str]:
    issues: list[str] = []
    raw_contract = node.get("video_input_contract")
    if raw_contract is not None and not isinstance(raw_contract, dict):
        return [f"{selector}: video_input_contract must be a mapping"]
    contract = _render_unit_video_input_contract(node)
    if not contract:
        return issues
    if (
        contract.get("explicit")
        and contract.get("schema_version")
        != RENDER_UNIT_VIDEO_INPUT_CONTRACT_VERSION
    ):
        issues.append(f"{selector}: unsupported video_input_contract schema_version")
    if not contract.get("explicit"):
        issues.append(
            f"{selector}: storyboard render unit requires an explicit "
            "reference-image video_input_contract"
        )
        return issues
    if contract.get("input_mode") != "reference_images":
        issues.append(
            f"{selector}: storyboard video_input_contract input_mode must be "
            "reference_images"
        )
    required_references = [
        str(value).strip()
        for value in _list_value(contract.get("required_references"))
        if str(value).strip()
    ]
    if len(required_references) != len(
        _list_value(contract.get("required_references"))
    ) or len(required_references) != len(set(required_references)):
        issues.append(
            f"{selector}: required render-unit references must be unique non-empty paths"
        )
    reference_roles = _list_value(contract.get("reference_roles"))
    if len(reference_roles) != len(required_references):
        issues.append(
            f"{selector}: video_input_contract.reference_roles count must equal "
            "ordered required_references count"
        )
    indexes: list[int] = []
    for role_index, raw_role in enumerate(reference_roles, start=1):
        if not isinstance(raw_role, dict):
            issues.append(
                f"{selector}: video_input_contract.reference_roles entries must be mappings"
            )
            continue
        image_index = raw_role.get("image_index")
        if not isinstance(image_index, int) or isinstance(image_index, bool):
            issues.append(
                f"{selector}: reference role image_index must be an integer"
            )
        else:
            indexes.append(image_index)
            if image_index != role_index:
                issues.append(
                    f"{selector}: reference role image_index must be 1-based, consecutive, unique, and ordered"
                )
        role = str(raw_role.get("role") or "").strip()
        if role not in VIDEO_REFERENCE_ROLE_INSTRUCTIONS:
            issues.append(
                f"{selector}: unsupported video reference role {role!r}"
            )
    if indexes and len(indexes) != len(set(indexes)):
        issues.append(
            f"{selector}: reference role image_index must be 1-based, consecutive, unique, and ordered"
        )
    storyboard_image = str(node.get("storyboard_image") or "").strip()
    if storyboard_image and storyboard_image not in required_references:
        issues.append(
            f"{selector}: storyboard_image must remain a required render-unit reference"
        )
    generation = _dict_value(node.get("video_generation"))
    generation_first = str(generation.get("first_frame") or "").strip()
    input_image = str(generation.get("input_image") or "").strip()
    last_frame = str(generation.get("last_frame") or "").strip()
    if generation_first or input_image or last_frame:
        issues.append(
            f"{selector}: reference-image mode must not combine "
            "first_frame/input_image/last_frame with multimodal references"
        )
    current_references = [
        str(value).strip()
        for value in _list_value(generation.get("references"))
        if str(value).strip()
    ]
    if current_references != required_references:
        issues.append(
            f"{selector}: video_generation references must exactly preserve the "
            "ordered required render-unit references"
        )
    return issues


def _render_unit_canonical_reference_issues(
    *,
    selector: str,
    node: dict[str, Any],
    source_scenes: list[SceneSpec],
) -> list[str]:
    contract = _render_unit_video_input_contract(node)
    storyboard_image = str(node.get("storyboard_image") or "").strip()
    if not contract and not storyboard_image:
        return []
    if contract.get("input_mode") != "reference_images" and not storyboard_image:
        return []

    issues: list[str] = []
    first_source_output = (
        str(source_scenes[0].image_output or "").strip()
        if source_scenes
        else ""
    )
    if not first_source_output:
        issues.append(
            f"{selector}: reference-image render unit requires the first source cut "
            "image_generation.output"
        )
    if not storyboard_image:
        issues.append(
            f"{selector}: reference-image render unit requires storyboard_image"
        )
    if not first_source_output or not storyboard_image:
        return issues

    expected_references = [first_source_output, storyboard_image]
    required_references = [
        str(value).strip()
        for value in _list_value(contract.get("required_references"))
        if str(value).strip()
    ]
    generation = _dict_value(node.get("video_generation"))
    generation_references = [
        str(value).strip()
        for value in _list_value(generation.get("references"))
        if str(value).strip()
    ]
    if required_references != expected_references:
        issues.append(
            f"{selector}: video_input_contract.required_references must exactly match "
            "the canonical ordered first-source/storyboard pair"
        )
    if generation_references != expected_references:
        issues.append(
            f"{selector}: video_generation.references must exactly match the canonical "
            "ordered first-source/storyboard pair"
        )
    expected_roles = [
        {"image_index": 1, "role": "start_state_visual_anchor"},
        {
            "image_index": 2,
            "role": "ordered_storyboard_sequence_guide",
        },
    ]
    if _list_value(contract.get("reference_roles")) != expected_roles:
        issues.append(
            f"{selector}: reference_roles must exactly bind image 1 as the "
            "start-state anchor and image 2 as the ordered storyboard guide"
        )
    return issues


def _materialized_video_model(video_generation: dict[str, Any]) -> str:
    payload = _dict_value(video_generation.get("api_prompt_payload"))
    binding = _dict_value(payload.get("provider_request_binding"))
    execution_options = _dict_value(binding.get("execution_options"))
    return str(execution_options.get("model") or "").strip()


def _video_generation_provider_context(
    video_generation: dict[str, Any],
    *,
    input_mode: str = "",
) -> tuple[str, str, str]:
    tool = str(video_generation.get("tool") or "kling_3_0").strip()
    payload = _dict_value(video_generation.get("api_prompt_payload"))
    model = _materialized_video_model(video_generation)
    mode = str(input_mode or payload.get("mode") or "").strip()
    if not mode:
        references = _list_value(video_generation.get("references"))
        first_frame = str(
            video_generation.get("first_frame")
            or video_generation.get("input_image")
            or ""
        ).strip()
        mode = "reference_images" if references and not first_frame else ""
    return tool, model, mode


def _video_provider_capability_issues(
    *,
    label: str,
    tool: str,
    model: str,
    input_mode: str,
    duration_seconds: int | None,
    reference_count: int,
) -> list[str]:
    capabilities = resolve_video_provider_capabilities(
        tool=normalize_tool_name(tool),
        model=model,
        input_mode=input_mode,
    )
    issues: list[str] = []
    if not capabilities.supported:
        issues.append(
            f"{label}: {capabilities.unsupported_reason or 'provider capability contract is unsupported'}"
        )
        return issues
    if duration_seconds is not None and not (
        capabilities.duration_min_seconds
        <= duration_seconds
        <= capabilities.duration_max_seconds
    ):
        issues.append(
            f"{label}: duration {duration_seconds}s is outside the {tool} "
            f"{input_mode or 'default'} limit "
            f"{capabilities.duration_min_seconds}-{capabilities.duration_max_seconds}s"
        )
    if not (
        capabilities.reference_images_min
        <= reference_count
        <= capabilities.reference_images_max
    ):
        issues.append(
            f"{label}: reference image count {reference_count} is outside the {tool} "
            f"{input_mode or 'default'} limit "
            f"{capabilities.reference_images_min}-{capabilities.reference_images_max}"
        )
    return issues


def _validate_effective_video_provider_capabilities(
    *,
    target: VideoRenderTargetSpec,
    duration_seconds: int,
    has_first_frame: bool,
    has_last_frame: bool,
    reference_count: int,
    execution_options: dict[str, Any],
) -> None:
    input_mode = str(target.video_input_mode or "").strip()
    if not input_mode:
        input_mode = (
            "reference_images"
            if reference_count and not has_first_frame
            else "first_last_frame"
            if has_first_frame and has_last_frame
            else "image_to_video"
            if has_first_frame
            else "text_to_video"
        )
    issues = _video_provider_capability_issues(
        label=target.selector,
        tool=normalize_tool_name(target.video_tool)
        or str(execution_options.get("backend") or ""),
        model=str(execution_options.get("model") or "").strip(),
        input_mode=input_mode,
        duration_seconds=int(duration_seconds),
        reference_count=int(reference_count),
    )
    if issues:
        raise SystemExit(
            "Video provider capability validation failed:\n- "
            + "\n- ".join(issues)
        )


def _build_video_render_targets(*, manifest: dict[str, Any], scenes: list[SceneSpec]) -> list[VideoRenderTargetSpec]:
    raw_scenes = manifest.get("scenes")
    if not isinstance(raw_scenes, list):
        return []

    scenes_by_manifest_scene_id: dict[str, list[SceneSpec]] = {}
    for scene in scenes:
        scenes_by_manifest_scene_id.setdefault(str(scene.manifest_scene_id), []).append(scene)

    issues: list[str] = []
    targets: list[VideoRenderTargetSpec] = []

    for raw_scene in raw_scenes:
        if not isinstance(raw_scene, dict):
            continue
        scene_id = normalize_dotted_id(raw_scene.get("scene_id"))
        if scene_id is None:
            continue

        scene_nodes = scenes_by_manifest_scene_id.get(scene_id, [])
        if _scene_has_explicit_render_units(raw_scene):
            cut_nodes = [node for node in scene_nodes if node.manifest_cut_id is not None]
            if not cut_nodes:
                issues.append(f"scene{scene_id}: render_units requires cuts[].")
                continue

            non_deleted_cut_nodes = [node for node in cut_nodes if not _scene_is_deleted(node)]
            non_deleted_by_cut_id = {
                str(node.manifest_cut_id): node
                for node in non_deleted_cut_nodes
                if node.manifest_cut_id is not None
            }
            ownership: dict[str, str] = {}
            ordered_source_cut_ids: list[str] = []
            raw_render_units = raw_scene.get("render_units") or []
            for raw_unit in raw_render_units:
                if not isinstance(raw_unit, dict):
                    issues.append(f"scene{scene_id}: render_units[] must be mappings.")
                    continue
                if is_non_renderable_manifest_node(raw_unit):
                    issues.append(f"scene{scene_id}: deleted/reference render_units are not supported.")
                    continue
                unit_id = normalize_dotted_id(raw_unit.get("unit_id"))
                if unit_id is None:
                    issues.append(f"scene{scene_id}: render_units[].unit_id is required.")
                    continue

                selector = _render_unit_selector(scene_id, unit_id)
                issues.extend(
                    _render_unit_video_input_issues(
                        selector=selector,
                        node=raw_unit,
                    )
                )
                source_cut_ids: list[str] = []
                raw_source_cut_ids = raw_unit.get("source_cut_ids")
                if not isinstance(raw_source_cut_ids, list) or not raw_source_cut_ids:
                    issues.append(f"{selector}: source_cut_ids must be a non-empty list.")
                    continue
                for raw_cut_id in raw_source_cut_ids:
                    normalized_cut_id = normalize_dotted_id(raw_cut_id)
                    if normalized_cut_id is None:
                        issues.append(f"{selector}: invalid source_cut_id: {raw_cut_id!r}")
                        continue
                    source_cut_ids.append(normalized_cut_id)
                ordered_source_cut_ids.extend(source_cut_ids)

                if not source_cut_ids:
                    continue

                source_scenes: list[SceneSpec] = []
                seen_within_unit: set[str] = set()
                for cut_id in source_cut_ids:
                    if cut_id in seen_within_unit:
                        issues.append(f"{selector}: duplicate source_cut_id within render unit: {cut_id}")
                        continue
                    seen_within_unit.add(cut_id)
                    source_scene = non_deleted_by_cut_id.get(cut_id)
                    if source_scene is None:
                        issues.append(f"{selector}: source_cut_id does not point to a non-deleted cut: {cut_id}")
                        continue
                    previous_owner = ownership.get(cut_id)
                    if previous_owner is not None:
                        issues.append(f"scene{scene_id}: cut {cut_id} is assigned to multiple render_units: {previous_owner}, {selector}")
                        continue
                    ownership[cut_id] = selector
                    source_scenes.append(source_scene)

                issues.extend(
                    _render_unit_canonical_reference_issues(
                        selector=selector,
                        node=raw_unit,
                        source_scenes=source_scenes,
                    )
                )

                video_generation = raw_unit.get("video_generation") if isinstance(raw_unit.get("video_generation"), dict) else {}
                video_input_contract = (
                    raw_unit.get("video_input_contract")
                    if isinstance(raw_unit.get("video_input_contract"), dict)
                    else {}
                )
                unit_video_tool = (
                    _as_opt_str(video_generation.get("tool"))
                    if isinstance(video_generation, dict)
                    else None
                )
                unit_video_input_mode = _as_opt_str(
                    video_input_contract.get("input_mode")
                )
                unit_video_reference_roles = [
                    dict(value)
                    for value in _list_value(
                        video_input_contract.get("reference_roles")
                    )
                    if isinstance(value, dict)
                ]
                unit_video_references = (
                    _ensure_str_list(video_generation.get("references"))
                    if isinstance(video_generation, dict)
                    else []
                )
                unit_duration_seconds: int | None = None
                if isinstance(video_generation, dict) and video_generation.get("duration_seconds") is not None:
                    try:
                        unit_duration_seconds = int(video_generation.get("duration_seconds"))
                    except Exception:
                        unit_duration_seconds = None
                if len(source_scenes) == len(source_cut_ids):
                    missing_source_durations = [
                        source.manifest_cut_id or "?"
                        for source in source_scenes
                        if source.duration_seconds is None
                        or int(source.duration_seconds) <= 0
                    ]
                    if missing_source_durations:
                        issues.append(
                            f"{selector}: approved source-cut duration is missing for "
                            f"{missing_source_durations}"
                        )
                    else:
                        source_duration_total = sum(
                            int(source.duration_seconds or 0)
                            for source in source_scenes
                        )
                        if (
                            source_duration_total
                            > VIDEO_GENERATION_DURATION_MAX_SECONDS
                        ):
                            issues.append(
                                f"{selector}: source-cut total {source_duration_total}s "
                                f"exceeds the {VIDEO_GENERATION_DURATION_MAX_SECONDS}s "
                                "provider limit; split the render unit"
                            )
                        if (
                            unit_duration_seconds is not None
                            and unit_duration_seconds != source_duration_total
                        ):
                            issues.append(
                                f"{selector}: duration {unit_duration_seconds}s must equal "
                                f"source-cut total {source_duration_total}s"
                        )
                        unit_duration_seconds = source_duration_total
                capability_tool, capability_model, capability_mode = (
                    _video_generation_provider_context(
                        video_generation,
                        input_mode=unit_video_input_mode or "",
                    )
                )
                issues.extend(
                    _video_provider_capability_issues(
                        label=selector,
                        tool=capability_tool,
                        model=capability_model,
                        input_mode=capability_mode,
                        duration_seconds=unit_duration_seconds,
                        reference_count=len(unit_video_references),
                    )
                )
                targets.append(
                    VideoRenderTargetSpec(
                        selector=selector,
                        manifest_scene_id=scene_id,
                        unit_id=unit_id,
                        source_cut_ids=list(source_cut_ids),
                        source_selectors=[scene.selector for scene in source_scenes if scene.selector],
                        source_scenes=source_scenes,
                        video_tool=unit_video_tool,
                        video_input_image=_as_opt_str(video_generation.get("input_image")) if isinstance(video_generation, dict) else None,
                        video_first_frame=_as_opt_str(video_generation.get("first_frame")) if isinstance(video_generation, dict) else None,
                        video_last_frame=_as_opt_str(video_generation.get("last_frame")) if isinstance(video_generation, dict) else None,
                        video_motion_prompt=_as_opt_str(video_generation.get("motion_prompt")) if isinstance(video_generation, dict) else None,
                        video_prompt_authoring_source=(
                            _as_opt_str(video_generation.get("prompt_authoring_source"))
                            if isinstance(video_generation, dict)
                            else None
                        ),
                        video_api_prompt_payload=(
                            dict(video_generation.get("api_prompt_payload"))
                            if isinstance(video_generation.get("api_prompt_payload"), dict)
                            else {}
                        ),
                        video_references=unit_video_references,
                        video_generation_contract=dict(video_generation),
                        video_quality=(
                            _as_opt_str(video_generation.get("quality"))
                            if isinstance(video_generation, dict)
                            else None
                        ),
                        video_aspect_ratio=(
                            _as_opt_str(video_generation.get("aspect_ratio"))
                            if isinstance(video_generation, dict)
                            else None
                        ),
                        video_input_mode=unit_video_input_mode,
                        video_reference_roles=unit_video_reference_roles,
                        video_output=_as_opt_str(video_generation.get("output")) if isinstance(video_generation, dict) else None,
                        video_applied_request_ids=_ensure_str_list(video_generation.get("applied_request_ids")) if isinstance(video_generation, dict) else [],
                        duration_seconds=unit_duration_seconds,
                        timestamp=source_scenes[0].timestamp if source_scenes else _as_opt_str(raw_scene.get("timestamp")),
                        reference_id=source_scenes[0].reference_id if source_scenes else None,
                        video_cut_contract=(
                            dict(raw_unit.get("cut_contract"))
                            if isinstance(raw_unit.get("cut_contract"), dict)
                            else {}
                        ),
                    )
                )

            missing_cut_ids = sorted(set(non_deleted_by_cut_id.keys()) - set(ownership.keys()))
            if missing_cut_ids:
                issues.append(f"scene{scene_id}: non-deleted cuts missing from render_units: {missing_cut_ids}")
            canonical_cut_ids = list(non_deleted_by_cut_id.keys())
            if not missing_cut_ids and ordered_source_cut_ids != canonical_cut_ids:
                issues.append(
                    f"scene{scene_id}: render_units source_cut_ids must follow canonical active cut order: "
                    f"expected {canonical_cut_ids}, got {ordered_source_cut_ids}"
                )
            continue

        for scene in scene_nodes:
            if _scene_is_deleted(scene):
                continue
            capability_tool, capability_model, capability_mode = (
                _video_generation_provider_context(
                    scene.video_generation_contract,
                )
            )
            issues.extend(
                _video_provider_capability_issues(
                    label=scene.selector
                    or make_scene_cut_selector(
                        scene.manifest_scene_id,
                        scene.manifest_cut_id,
                    ),
                    tool=capability_tool or scene.video_tool or "",
                    model=capability_model,
                    input_mode=capability_mode,
                    duration_seconds=scene.duration_seconds,
                    reference_count=len(scene.video_references or []),
                )
            )
            targets.append(
                VideoRenderTargetSpec(
                    selector=scene.selector or make_scene_cut_selector(scene.manifest_scene_id, scene.manifest_cut_id),
                    manifest_scene_id=scene.manifest_scene_id,
                    unit_id=None,
                    source_cut_ids=[scene.manifest_cut_id] if scene.manifest_cut_id is not None else [],
                    source_selectors=[scene.selector] if scene.selector else [],
                    source_scenes=[scene],
                    video_tool=scene.video_tool,
                    video_input_image=scene.video_input_image,
                    video_first_frame=scene.video_first_frame,
                    video_last_frame=scene.video_last_frame,
                    video_motion_prompt=scene.video_motion_prompt,
                    video_prompt_authoring_source=scene.video_prompt_authoring_source,
                    video_api_prompt_payload=dict(scene.video_api_prompt_payload or {}),
                    video_references=list(scene.video_references or []),
                    video_generation_contract=dict(scene.video_generation_contract or {}),
                    video_quality=scene.video_quality,
                    video_aspect_ratio=scene.video_aspect_ratio,
                    video_output=scene.video_output,
                    video_applied_request_ids=list(scene.video_applied_request_ids or []),
                    duration_seconds=scene.duration_seconds,
                    timestamp=scene.timestamp,
                    reference_id=scene.reference_id,
                    video_cut_contract=dict(scene.cut_contract or {}),
                    video_reference_roles=list(
                        scene.video_reference_roles or []
                    ),
                )
            )

    if issues:
        raise SystemExit("Render unit contract validation failed:\n- " + "\n- ".join(issues))
    return targets


def _video_target_matches_filter(target: VideoRenderTargetSpec, scene_filter: set[str] | None) -> bool:
    tokens = set(
        scene_selector_tokens(
            operational_scene_id=target.selector,
            manifest_scene_id=target.manifest_scene_id,
            reference_id=target.reference_id,
        )
    )
    tokens.add(target.selector)
    tokens.update(target.source_selectors)
    for cut_id in target.source_cut_ids:
        if str(cut_id).strip():
            tokens.add(make_scene_cut_selector(target.manifest_scene_id, cut_id))
    return selector_matches(tokens, scene_filter)


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


def _scene_has_compilable_image_prompt(scene: SceneSpec) -> bool:
    existing_payload = (
        scene.image_api_prompt_payload
        if isinstance(scene.image_api_prompt_payload, dict)
        else {}
    )
    existing_policy = str(existing_payload.get("policy_version") or "").strip()
    existing_prompt = str(existing_payload.get("prompt") or "").strip()
    return bool(
        scene.image_prompt
        or scene.cut_contract
        or (
            existing_policy in SUPPORTED_IMAGE_API_PROMPT_POLICY_VERSIONS
            and existing_prompt
        )
    )


def _should_generate_image_scene(scene: SceneSpec, *, allowed_story_modes: set[str], base_dir: Path) -> bool:
    if not scene.image_output:
        return False
    outp = resolve_path(base_dir, scene.image_output)
    if outp and (_is_character_ref_path(outp) or _is_object_ref_path(outp)):
        return bool(scene.image_prompt)
    if not _scene_has_compilable_image_prompt(scene):
        return False
    explicit_status = _normalize_generation_status(scene.still_image_generation_status)
    if explicit_status == "created":
        # `created` is an authoring hint, not reusable-output proof. Keep the
        # item in the execution plan so request-bound provenance can decide
        # whether to skip or regenerate it.
        return _should_generate_story_still_by_plan(scene, allowed_story_modes)
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
    _validate_image_execution_lane(scene)
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
    execution_lane = _effective_image_execution_lane(scene)

    if tool in DEPRECATED_EXTERNAL_IMAGE_TOOLS and execution_lane == NO_REFERENCE_IMAGE_EXECUTION_LANE:
        raise SystemExit(_no_reference_image_lane_error(scene=scene, tool=tool))

    is_char_ref = bool(out_path and _is_character_ref_path(out_path))
    is_reference_asset = _scene_is_reference_asset_image(out_path)

    if tool == CODEX_BUILTIN_IMAGE_TOOL:
        prefix = (args.image_prompt_prefix or "").strip()
        suffix = (args.image_prompt_suffix or "").strip()
        prompt_policy_version: str | None = None
        debug_prompt_source: dict[str, Any] = {}
        if is_reference_asset:
            api_prompt_payload = _asset_image_api_prompt_payload_for_scene(
                scene,
            )
            prompt = str(api_prompt_payload.get("prompt") or "").strip()
            prompt_policy_version = str(api_prompt_payload.get("policy_version") or "").strip() or None
            if prefix or suffix:
                raise SystemExit(
                    f"{_scene_selector(scene)}: compiled API prompt payload is immutable; "
                    "image prompt prefix/suffix overrides are not allowed"
                )
        else:
            api_prompt_payload = _image_api_prompt_payload_for_scene(scene)
            prompt = str(api_prompt_payload.get("prompt") or "").strip()
            prompt_policy_version = str(api_prompt_payload.get("policy_version") or "").strip() or None
            debug_prompt_source = {
                "first_frame_visual_plan": _build_first_frame_visual_plan(scene),
                "api_prompt_payload": {
                    "policy_version": prompt_policy_version or "",
                    "sha256": api_prompt_payload.get("sha256", ""),
                },
                "send_to_api": False,
            }

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
            generate_codex_builtin_image(
                prompt=front_prompt,
                reference_images=refs,
                out_path=view_paths["front"],
                force=args.force,
                log_path=log_dir / f"scene{scene.scene_id}_image.json",
                dry_run=args.dry_run,
                run_dir=base_dir,
                item_id=_scene_selector(scene),
                aspect_ratio=scene_aspect_ratio,
                image_size=scene_image_size,
                prompt_policy_version=prompt_policy_version,
                debug_prompt_source=debug_prompt_source,
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
                generate_codex_builtin_image(
                    prompt=vprompt,
                    reference_images=conditioned_refs,
                    out_path=view_paths[v],
                    force=args.force,
                    log_path=log_dir / f"scene{scene.scene_id}_image_{v}.json",
                    dry_run=args.dry_run,
                    run_dir=base_dir,
                    item_id=f"{_scene_selector(scene)}_{v}",
                    aspect_ratio=scene_aspect_ratio,
                    image_size=scene_image_size,
                    prompt_policy_version=prompt_policy_version,
                    debug_prompt_source=debug_prompt_source,
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
        generate_codex_builtin_image(
            prompt=prompt,
            reference_images=refs,
            out_path=out_path,
            force=args.force,
            log_path=log_dir / f"scene{scene.scene_id}_image.json",
            dry_run=args.dry_run,
            run_dir=base_dir,
            item_id=_scene_selector(scene),
            aspect_ratio=scene_aspect_ratio,
            image_size=scene_image_size,
            prompt_policy_version=prompt_policy_version,
            debug_prompt_source=debug_prompt_source,
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
                generate_codex_builtin_image(
                    prompt=prompt,
                    reference_images=refs,
                    out_path=variant_out,
                    force=args.force,
                    log_path=log_dir / f"scene{scene.scene_id}_image_test_v{variant_index:02d}.json",
                    dry_run=args.dry_run,
                    run_dir=base_dir,
                    item_id=f"{_scene_selector(scene)}_test_v{variant_index:02d}",
                    aspect_ratio=scene_aspect_ratio,
                    image_size=scene_image_size,
                    prompt_policy_version=prompt_policy_version,
                    debug_prompt_source=debug_prompt_source,
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


def _generate_single_audio_scene(
    *,
    scene: SceneSpec,
    base_dir: Path,
    args: Any,
    log_dir: Path,
    elevenlabs_client: ElevenLabsClient | None,
) -> None:
    if args.skip_audio or not scene.narration_output:
        return

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
        prepared = prepare_elevenlabs_tts_text(
            tts_text,
            pronunciation_aliases=getattr(args, "tts_pronunciation_aliases", ()),
        )
        normalize_dur = dur if scene.narration_normalize_to_scene_duration else None
        generate_elevenlabs_tts(
            client=elevenlabs_client,
            voice_id=str((args.elevenlabs_voice_id or DEFAULT_ELEVENLABS_VOICE_ID)),
            model_id=args.elevenlabs_model_id or "eleven_v3",
            output_format=args.elevenlabs_output_format or "mp3_44100_128",
            language_code=args.elevenlabs_language_code or DEFAULT_ELEVENLABS_LANGUAGE_CODE,
            pronunciation_dictionary_locators=getattr(args, "elevenlabs_pronunciation_dictionary_locators", ()),
            text=prepared.text,
            out_path=out_path,
            duration_seconds=normalize_dur,
            force=args.force,
            request_log_path=log_dir / f"scene{scene.scene_id}_tts_request.json",
            dry_run=args.dry_run,
        )
        return

    if tool in {"macos_say", "say"}:
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
        return

    if tool in {"silent", "tbd", ""}:
        if args.dry_run:
            print(f"[dry-run] AUDIO {out_path} <- placeholder (tool={scene.narration_tool})")
        else:
            _ffmpeg_write_silence_mp3(out_path, dur, args.force)
        return

    raise SystemExit(f"scene{scene.scene_id}: unsupported narration tool: {scene.narration_tool}")


def _generate_audio_scenes_in_parallel(
    *,
    audio_scenes: list[SceneSpec],
    audio_max_concurrency: int,
    base_dir: Path,
    args: Any,
    log_dir: Path,
    elevenlabs_client: ElevenLabsClient | None,
) -> None:
    if not audio_scenes:
        return
    with ThreadPoolExecutor(max_workers=audio_max_concurrency) as executor:
        futures = [
            executor.submit(
                _generate_single_audio_scene,
                scene=scene,
                base_dir=base_dir,
                args=args,
                log_dir=log_dir,
                elevenlabs_client=elevenlabs_client,
            )
            for scene in audio_scenes
        ]
        for future in futures:
            future.result()


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


def _format_character_appearance_continuity_line(
    character_name: str, appearance: dict[str, Any]
) -> str:
    costume_state = str(appearance.get("costume_state") or "").strip()
    if not costume_state:
        return ""
    forbidden_states = [
        str(value).strip()
        for value in appearance.get("forbidden_costume_states", [])
        if isinstance(value, str) and value.strip()
    ]
    line = f"{character_name}の衣装は{costume_state}で固定し"
    if forbidden_states:
        line += "、" + "、".join(
            f"{value}には変えない" for value in forbidden_states
        )
    else:
        line += "続ける"
    return line + "。"


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
                    appearance_continuity=dict(
                        variant.appearance_continuity or {}
                    ),
                    notes=variant.notes,
                )
            )

        expanded_cb.append(
            CharacterBibleEntry(
                character_id=entry.character_id,
                reference_images=_dedupe_keep_order(refs + extra),
                reference_variants=expanded_variants,
                fixed_prompts=list(entry.fixed_prompts or []),
                appearance_continuity=dict(entry.appearance_continuity or {}),
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
            appearance_sources = [
                variant.appearance_continuity
                for variant in active_variants
                if variant.appearance_continuity
            ] or ([entry.appearance_continuity] if entry.appearance_continuity else [])
            character_name = next(
                (
                    str(alias).strip()
                    for alias in entry.review_aliases or []
                    if str(alias).strip()
                ),
                str(entry.character_id or "人物").strip() or "人物",
            )
            for appearance in appearance_sources:
                appearance_line = _format_character_appearance_continuity_line(
                    character_name, appearance
                )
                if appearance_line:
                    char_lines.append(appearance_line)
            char_lines.extend(_format_physical_scale_lines(entry))

    if len(active_character_entries) >= 2:
        for entry in active_character_entries:
            char_lines.extend(entry.relative_scale_rules or [])

    # Inject object/setpiece prompts only when that object is active for the scene.
    prop_lines: list[str] = []
    chosen_object_ids = set(scene.image_object_ids or [])
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
    *,
    scenes: list[SceneSpec],
    require: bool,
    scene_filter: set[str] | None,
    video_participating_selectors: set[str] | None = None,
) -> None:
    if not require:
        return
    for scene in scenes:
        if not _scene_matches_filter(scene, scene_filter):
            continue
        if _scene_is_deleted(scene):
            continue
        if video_participating_selectors is not None:
            if scene.selector not in video_participating_selectors:
                continue
        elif not scene.video_tool and not scene.video_output:
            continue

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
        if not scene.narration_output:
            raise SystemExit(
                f"scene{scene.scene_id}: missing audio.narration.output (required). "
                "To intentionally generate assets without narration, pass --skip-audio."
            )
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


def _is_location_ref_path(path: Path) -> bool:
    try:
        return path.parent.name == "locations" and path.parent.parent.name == "assets"
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
    language_code: str,
    text: str,
    out_path: Path,
    duration_seconds: int | None,
    force: bool,
    request_log_path: Path | None,
    dry_run: bool,
    pronunciation_dictionary_locators: tuple[dict[str, str], ...] = (),
) -> None:
    if out_path.exists() and not force:
        return

    payload: dict = {
        "text": text,
        "model_id": model_id,
        "language_code": language_code,
        "voice_settings": {
            "stability": 0.35,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }

    if request_log_path:
        if pronunciation_dictionary_locators:
            payload["pronunciation_dictionary_locators"] = list(pronunciation_dictionary_locators)
        request_log_path.parent.mkdir(parents=True, exist_ok=True)
        request_log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if dry_run:
        print(f"[dry-run] AUDIO {out_path} <- elevenlabs voice={voice_id} model={model_id} fmt={output_format}")
        return

    if client is None:
        raise SystemExit("ElevenLabs client not configured (missing ELEVENLABS_API_KEY).")

    audio: bytes | None = None
    for attempt in range(5):
        try:
            audio = client.tts(
                text=text,
                voice_id=voice_id,
                model_id=model_id,
                output_format=output_format,
                language_code=language_code,
                pronunciation_dictionary_locators=pronunciation_dictionary_locators,
                voice_settings=payload["voice_settings"],
            )
            break
        except HttpError as e:
            body = (e.body or "").lower()
            if e.status == 429 and "concurrent_limit_exceeded" in body and attempt < 4:
                time.sleep(2 * (attempt + 1))
                continue
            raise SystemExit(str(e)) from e

    if audio is None:
        raise SystemExit("ElevenLabs TTS failed without returning audio.")

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
        print(f"[dry-run] IMAGE {out_path} skipped: external Gemini/Nano Banana image generation is disabled")
        return

    raise SystemExit(
        "Deprecated: external Gemini/Nano Banana image generation is disabled for this repo. "
        "Use codex_builtin_image / gpt-image-2 through the Codex app-server instead."
    )

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


_REQUEST_BOUND_PROVENANCE_POLICY = "request_bound_v2"


def _direct_image_global_lock_dir() -> Path:
    configured = os.environ.get("TOC_IMAGE_GEN_GLOBAL_LOCK_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    workspace_key = hashlib.sha256(str(REPO_ROOT.resolve()).encode("utf-8")).hexdigest()[:12]
    return Path("/tmp") / "toc-image-generation-locks" / workspace_key


def _direct_image_global_parallelism() -> int:
    raw = os.environ.get("TOC_IMAGE_GEN_GLOBAL_PARALLELISM", "6").strip()
    try:
        return max(1, int(raw))
    except ValueError as exc:
        raise SystemExit("TOC_IMAGE_GEN_GLOBAL_PARALLELISM must be an integer") from exc


def _direct_request_snapshot_binding(
    *,
    run_dir: Path,
    item_id: str,
    prompt: str,
    destination: Path,
    references: list[Path],
    prompt_policy_version: str | None,
) -> tuple[Any, Any, list[str]] | None:
    matches: list[tuple[Any, Any]] = []
    for filename in (
        "image_generation_request_snapshot.json",
        "asset_generation_request_snapshot.json",
    ):
        snapshot_path = run_dir / filename
        if not snapshot_path.is_file():
            continue
        try:
            snapshot = load_request_snapshot(
                snapshot_path,
                run_dir=run_dir,
                verify_references=False,
            )
            item = snapshot.item(item_id)
        except KeyError:
            continue
        except ImageRequestSnapshotError as exc:
            raise SystemExit(f"invalid image request snapshot: {exc}") from exc
        matches.append((snapshot, item))
    if len(matches) > 1:
        raise SystemExit(f"image request item appears in multiple snapshots: {item_id}")
    if not matches:
        if prompt_policy_version == IMAGE_API_PROMPT_POLICY_VERSION_V2:
            raise SystemExit(f"image_api_prompt_v2 requires an immutable request snapshot: {item_id}")
        return None

    snapshot, item = matches[0]
    try:
        destination_rel = destination.resolve().relative_to(run_dir.resolve()).as_posix()
        reference_rels = [
            reference.resolve().relative_to(run_dir.resolve()).as_posix()
            for reference in references
        ]
    except ValueError as exc:
        raise SystemExit(f"image request paths must stay inside the run directory: {item_id}") from exc
    if item.prompt != prompt or item.prompt_sha256 != sha256_text(prompt):
        raise SystemExit(f"image request snapshot prompt changed before send: {item_id}")
    if item.destination != destination_rel:
        raise SystemExit(f"image request snapshot destination changed before send: {item_id}")
    if snapshot.source_artifact:
        source_path = run_dir / snapshot.source_artifact
        if (
            not source_path.is_file()
            or not snapshot.source_artifact_sha256
            or sha256_file(source_path) != snapshot.source_artifact_sha256
        ):
            raise SystemExit("image request snapshot source artifact changed before send")
    if len(item.references) != len(references):
        raise SystemExit(f"image request snapshot reference order changed before send: {item_id}")
    reference_sha256s: list[str] = []
    for frozen_reference, actual_reference, actual_rel in zip(
        item.references,
        references,
        reference_rels,
        strict=True,
    ):
        is_archived_self_reference = (
            not frozen_reference.deferred
            and frozen_reference.path == item.destination
            and actual_rel != frozen_reference.path
        )
        if actual_rel != frozen_reference.path and not is_archived_self_reference:
            raise SystemExit(
                f"image request snapshot reference order changed before send: {item_id}"
            )
        if not actual_reference.is_file():
            raise SystemExit(
                f"image request snapshot reference changed before send: "
                f"reference does not exist for {item_id}: {actual_rel}"
            )
        actual_sha256 = sha256_file(actual_reference)
        if frozen_reference.sha256 and frozen_reference.sha256 != actual_sha256:
            raise SystemExit(
                f"image request snapshot reference changed before send: "
                f"reference sha256 mismatch for {item_id}: {frozen_reference.path}"
            )
        reference_sha256s.append(actual_sha256)
    return snapshot, item, reference_sha256s


def _direct_output_has_exact_provenance(
    *,
    run_dir: Path,
    snapshot_binding: tuple[Any, Any, list[str]] | None,
) -> bool:
    if snapshot_binding is None:
        return False
    snapshot, item, _reference_sha256s = snapshot_binding
    log_dir = run_dir / "logs" / "app_server" / "image_gen"
    if not log_dir.is_dir():
        return False
    for log_path in sorted(log_dir.glob("*.json"), reverse=True):
        try:
            payload = json.loads(log_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if match_output_provenance(run_dir, snapshot, item, payload):
            return True
    return False


def _validate_direct_request_bound_result(
    result: Any,
    *,
    generation_job_id: str,
    item_id: str,
    destination: Path,
    prompt_sha256: str,
    reference_sha256s: list[str],
) -> None:
    expected = {
        "provenance_policy": _REQUEST_BOUND_PROVENANCE_POLICY,
        "generation_job_id": generation_job_id,
        "item_id": item_id,
        "prompt_sha256": prompt_sha256,
        "destination": str(destination),
    }
    issues = [
        field
        for field, value in expected.items()
        if str(getattr(result, field, "") or "") != value
    ]
    if list(getattr(result, "reference_sha256s", None) or []) != reference_sha256s:
        issues.append("reference_sha256s")
    if not str(getattr(result, "turn_id", "") or "").strip():
        issues.append("turn_id")
    if not str(getattr(result, "image_generation_item_id", "") or "").strip():
        issues.append("image_generation_item_id")
    if int(getattr(result, "image_generation_item_count", 0) or 0) != 1:
        issues.append("image_generation_item_count")
    if str(getattr(result, "source", "") or "") != "app_server":
        issues.append("source")
    if not bool(getattr(result, "provenance_authoritative", False)):
        issues.append("provenance_authoritative")
    if issues:
        raise RuntimeError(
            f"Codex app-server request-bound provenance mismatch for {item_id}: "
            + ", ".join(dict.fromkeys(issues))
        )


def generate_codex_builtin_image(
    *,
    prompt: str,
    reference_images: list[Path] | None,
    out_path: Path,
    force: bool,
    log_path: Path | None,
    dry_run: bool,
    run_dir: Path,
    item_id: str,
    aspect_ratio: str,
    image_size: str,
    prompt_policy_version: str | None = None,
    debug_prompt_source: dict[str, Any] | None = None,
) -> None:
    if dry_run:
        ref_count = len(reference_images or [])
        print(f"[dry-run] IMAGE {out_path} <- {CODEX_BUILTIN_IMAGE_TOOL} (gpt-image-2, {aspect_ratio}, {image_size}, refs={ref_count})")
        return

    if app_server_disabled():
        raise SystemExit("Codex app-server is disabled; enable it to use codex_builtin_image / gpt-image-2 image generation.")

    async def _run_generation() -> None:
        references = list(reference_images or [])
        destination_key = hashlib.sha256(
            str(out_path.resolve()).encode("utf-8")
        ).hexdigest()[:24]
        item_lock = run_dir / ".locks" / "image_generation" / f"{destination_key}.lock"
        client = None
        result = None
        binding = None
        snapshot = None
        snapshot_item = None
        reference_sha256s: list[str] = []
        try:
            async with async_file_lock(item_lock, timeout_seconds=900):
                binding = _direct_request_snapshot_binding(
                    run_dir=run_dir,
                    item_id=item_id,
                    prompt=prompt,
                    destination=out_path,
                    references=references,
                    prompt_policy_version=prompt_policy_version,
                )
                if binding is not None:
                    snapshot, snapshot_item, reference_sha256s = binding
                else:
                    for reference in references:
                        if not reference.is_file():
                            raise RuntimeError(f"image reference not found for {item_id}: {reference}")
                    reference_sha256s = [sha256_file(reference) for reference in references]
                if (
                    out_path.is_file()
                    and not force
                    and _direct_output_has_exact_provenance(
                        run_dir=run_dir,
                        snapshot_binding=binding,
                    )
                ):
                    return

                generation_job_id = uuid.uuid4().hex
                prompt_sha256 = sha256_text(prompt)
                async with async_file_slot(
                    _direct_image_global_lock_dir(),
                    namespace="request-bound",
                    slots=_direct_image_global_parallelism(),
                    timeout_seconds=900,
                ):
                    client = create_codex_app_server_client(cwd=REPO_ROOT)
                    await client.start()
                    result = await client.generate_image(
                        prompt=prompt,
                        output_path=out_path,
                        reference_images=references,
                        item_id=item_id,
                        run_dir=run_dir,
                        fallback_cutoff_ns=None,
                        generation_job_id=generation_job_id,
                        allow_generated_images_fallback=False,
                        provenance_policy=_REQUEST_BOUND_PROVENANCE_POLICY,
                    )
                    if result.saved_path is None:
                        raise RuntimeError(f"Codex app-server did not return an image for {item_id}")
                    reject_local_raster_image_result(result, item_id=item_id)
                    _validate_direct_request_bound_result(
                        result,
                        generation_job_id=generation_job_id,
                        item_id=item_id,
                        destination=out_path,
                        prompt_sha256=prompt_sha256,
                        reference_sha256s=reference_sha256s,
                    )
                    copy_saved_image(result.saved_path, out_path)

                debug_path = write_app_server_image_debug_log(
                    run_dir=run_dir,
                    item_id=item_id,
                    index=1,
                    destination=out_path,
                    references=references,
                    prompt=prompt,
                    kind=getattr(snapshot_item, "kind", None) or "manifest",
                    prompt_policy_version=prompt_policy_version,
                    debug_prompt_source=debug_prompt_source,
                    request_revision=getattr(snapshot, "request_revision", None),
                    request_digest=getattr(snapshot_item, "request_digest", None),
                    compiler_version=getattr(snapshot_item, "compiler_version", None),
                    source_digest=getattr(snapshot_item, "source_digest", None),
                    result=result,
                )
                if log_path:
                    log_path.parent.mkdir(parents=True, exist_ok=True)
                    log_path.write_text(
                        json.dumps(
                            {
                                "tool": CODEX_BUILTIN_IMAGE_TOOL,
                                "model": "gpt-image-2",
                                "debug_log": str(debug_path.relative_to(run_dir)),
                                "status": result.status,
                                "source": result.source,
                                "saved_path": str(result.saved_path or ""),
                                "request_revision": getattr(snapshot, "request_revision", None),
                                "request_digest": getattr(snapshot_item, "request_digest", None),
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
        except Exception as exc:
            debug_path = write_app_server_image_debug_log(
                run_dir=run_dir,
                item_id=item_id,
                index=1,
                destination=out_path,
                references=references,
                prompt=prompt,
                kind=getattr(snapshot_item, "kind", None) or "manifest",
                prompt_policy_version=prompt_policy_version,
                debug_prompt_source=debug_prompt_source,
                request_revision=getattr(snapshot, "request_revision", None),
                request_digest=getattr(snapshot_item, "request_digest", None),
                compiler_version=getattr(snapshot_item, "compiler_version", None),
                source_digest=getattr(snapshot_item, "source_digest", None),
                result=result,
                error=str(exc),
            )
            if log_path:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(
                    json.dumps(
                        {
                            "tool": CODEX_BUILTIN_IMAGE_TOOL,
                            "model": "gpt-image-2",
                            "debug_log": str(debug_path.relative_to(run_dir)),
                            "status": "failed",
                            "source": getattr(result, "source", "") if result is not None else "",
                            "saved_path": str(getattr(result, "saved_path", "") or "") if result is not None else "",
                            "error": str(exc),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            raise
        finally:
            if client is not None:
                await client.stop()

    asyncio.run(_run_generation())


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
        print(f"[dry-run] IMAGE {out_path} skipped: external SeaDream image generation is disabled")
        return

    raise SystemExit(
        "Deprecated: external SeaDream image generation is disabled for this repo. "
        "Use codex_builtin_image / gpt-image-2 through the Codex app-server instead."
    )

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
        log_path.write_text(
            json.dumps(
                _redact_video_provider_log_payload(
                    {"submit": submit, "operation": op}
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        summary_path = log_path.with_name(log_path.stem + "_credit_summary.json")
        summary_path.write_text(
            json.dumps(
                _redact_video_provider_log_payload(
                    _extract_kling_credit_summary(
                        submit=submit,
                        operation=op,
                        model=model,
                        duration_seconds=duration_seconds,
                        aspect_ratio=aspect_ratio,
                        resolution=resolution,
                        output=str(out_path),
                    )
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    if client.is_failed_operation(op):
        raise SystemExit(f"Kling operation failed: {json.dumps(op, ensure_ascii=False)}")

    try:
        video_uri = client.extract_video_uri(op)
        client.download_to_file(uri=video_uri, out_path=out_path)
    except (HttpError, ValueError) as e:
        raise SystemExit(str(e)) from e


def _extract_kling_credit_summary(
    *,
    submit: dict[str, Any],
    operation: dict[str, Any],
    model: str,
    duration_seconds: int,
    aspect_ratio: str,
    resolution: str,
    output: str,
) -> dict[str, Any]:
    task_result = None
    for path in (
        "data.task_result",
        "task_result",
        "data.result",
        "result",
    ):
        value = _lookup_json_path(operation, path)
        if isinstance(value, dict):
            task_result = value
            break

    final_unit_deduction = None
    for path in (
        "data.task_result.final_unit_deduction",
        "task_result.final_unit_deduction",
        "data.final_unit_deduction",
        "final_unit_deduction",
    ):
        value = _lookup_json_path(operation, path)
        if value not in (None, ""):
            final_unit_deduction = value
            break

    task_id = None
    for path in ("data.task_id", "task_id", "data.id", "id"):
        value = _lookup_json_path(submit, path)
        if value not in (None, ""):
            task_id = value
            break
    if task_id in (None, ""):
        for path in ("data.task_id", "task_id", "data.id", "id"):
            value = _lookup_json_path(operation, path)
            if value not in (None, ""):
                task_id = value
                break

    status = None
    for path in ("data.task_status", "task_status", "data.status", "status"):
        value = _lookup_json_path(operation, path)
        if value not in (None, ""):
            status = value
            break

    return {
        "provider": "kling",
        "model": model,
        "duration_seconds": int(duration_seconds),
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "output": output,
        "task_id": task_id,
        "status": status,
        "final_unit_deduction": final_unit_deduction,
        "task_result": task_result,
    }


def _lookup_json_path(data: Any, path: str) -> Any:
    current: Any = data
    for raw_part in str(path or "").split("."):
        part = raw_part.strip()
        if not part:
            return None
        if isinstance(current, list):
            if not part.isdigit():
                return None
            idx = int(part)
            if idx < 0 or idx >= len(current):
                return None
            current = current[idx]
            continue
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current.get(part)
            continue
        return None
    return current


def _redact_video_provider_log_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _redact_video_provider_log_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_video_provider_log_payload(item) for item in value]
    if not isinstance(value, str):
        return value
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return value
    hostname = parsed.hostname
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    try:
        port = parsed.port
    except ValueError:
        port = None
    safe_netloc = f"{hostname}:{port}" if port is not None else hostname
    return urlunsplit((parsed.scheme.lower(), safe_netloc, parsed.path, "", ""))


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


_EVOLINK_PROTECTED_VIDEO_EXTRA_KEYS = {
    "model",
    "prompt",
    "negative_prompt",
    "duration",
    "aspect_ratio",
    "quality",
    "image_start",
    "image_end",
}


def _validate_evolink_video_extra_payload(extra_payload: dict[str, Any] | None) -> None:
    protected = sorted(
        _EVOLINK_PROTECTED_VIDEO_EXTRA_KEYS.intersection(extra_payload or {})
    )
    if protected:
        raise ValueError(
            "EvoLink extra_payload cannot override protected reviewed fields: "
            + ", ".join(protected)
        )


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
    _validate_evolink_video_extra_payload(extra_payload)
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
        # Safety default: no audio unless the reviewed extra payload enables it.
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
        log_path.write_text(
            json.dumps(
                _redact_video_provider_log_payload({"submit": submit, "task": task}),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

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
    watermark: bool,
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
        watermark=bool(watermark),
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
        log_path.write_text(
            json.dumps(
                _redact_video_provider_log_payload({"submit": submit, "task": task}),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    if client.is_failed_task(task):
        raise SystemExit(f"Seedance task failed: {json.dumps(task, ensure_ascii=False)}")

    try:
        video_url = client.extract_video_url(task)
        client.download_to_file(url=video_url, out_path=out_path)
    except (HttpError, ValueError) as e:
        raise SystemExit(str(e)) from e


def _reviewed_video_provider_request_values(
    *,
    selector: str,
    api_prompt_payload: dict[str, Any],
) -> dict[str, Any]:
    binding = api_prompt_payload.get("provider_request_binding")
    if not isinstance(binding, dict):
        raise SystemExit(
            f"{selector}: materialized provider_request_binding is missing"
        )
    execution_options = binding.get("execution_options")
    if not isinstance(execution_options, dict):
        raise SystemExit(
            f"{selector}: materialized provider execution_options are missing"
        )
    try:
        duration_seconds = int(binding.get("duration_seconds"))
    except (TypeError, ValueError) as exc:
        raise SystemExit(
            f"{selector}: materialized video duration_seconds is invalid"
        ) from exc
    if duration_seconds <= 0:
        raise SystemExit(
            f"{selector}: materialized video duration_seconds must be positive"
        )
    quality = str(binding.get("quality") or "").strip()
    aspect_ratio = str(binding.get("aspect_ratio") or "").strip()
    backend = str(execution_options.get("backend") or "").strip()
    model = str(execution_options.get("model") or "").strip()
    if not quality or not aspect_ratio or not backend or not model:
        raise SystemExit(
            f"{selector}: materialized provider settings are incomplete"
        )
    extra_payload = execution_options.get("extra_payload") or {}
    if not isinstance(extra_payload, dict):
        raise SystemExit(
            f"{selector}: materialized provider extra_payload must be an object"
        )
    return {
        "duration_seconds": duration_seconds,
        "quality": quality,
        "aspect_ratio": aspect_ratio,
        "backend": backend,
        "model": model,
        "extra_payload": dict(extra_payload),
        "generate_audio": bool(execution_options.get("generate_audio", False)),
        "watermark": bool(execution_options.get("watermark", False)),
    }


def _video_output_provenance_path(out_path: Path) -> Path:
    return out_path.with_name(out_path.name + ".provenance.json")


def _approved_video_provider_request_sha256(
    *,
    selector: str,
    tool: str,
    api_prompt_payload: dict[str, Any],
    prompt: str,
    negative_prompt: str,
    out_path: Path,
) -> str:
    binding = api_prompt_payload.get("provider_request_binding")
    if not isinstance(binding, dict):
        raise SystemExit(
            f"{selector}: materialized provider_request_binding is missing"
        )
    return sha256_canonical_json(
        {
            "selector": selector,
            "tool": tool,
            "output_path": str(out_path.absolute()),
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "provider_request_binding": binding,
        }
    )


def _video_provider_job_metadata(
    *,
    backend: str,
    log_path: Path,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {"backend": backend}
    if not log_path.is_file():
        return metadata
    metadata.update(
        {
            "log_path": str(log_path),
            "log_sha256": sha256_file(log_path),
        }
    )
    try:
        log_payload = json.loads(log_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return metadata
    if not isinstance(log_payload, dict):
        return metadata
    for path in (
        "submit.data.task_id",
        "submit.task_id",
        "submit.data.id",
        "submit.id",
        "operation.data.task_id",
        "operation.task_id",
        "operation.data.id",
        "operation.id",
        "task.data.task_id",
        "task.task_id",
        "task.data.id",
        "task.id",
    ):
        value = _lookup_json_path(log_payload, path)
        if value not in (None, ""):
            metadata["job_id"] = str(value)
            break
    for path in (
        "operation.data.task_status",
        "operation.task_status",
        "operation.data.status",
        "operation.status",
        "task.data.status",
        "task.status",
    ):
        value = _lookup_json_path(log_payload, path)
        if value not in (None, ""):
            metadata["status"] = str(value)
            break
    return metadata


def _write_video_output_provenance_atomic(
    *,
    selector: str,
    tool: str,
    backend: str,
    model: str,
    approved_provider_request_sha256: str,
    out_path: Path,
    log_path: Path,
) -> None:
    if not out_path.is_file() or out_path.stat().st_size <= 0:
        raise SystemExit(
            f"{selector}: video provider completed without a non-empty output: {out_path}"
        )
    sidecar_path = _video_output_provenance_path(out_path)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": VIDEO_OUTPUT_PROVENANCE_SCHEMA_VERSION,
        "selector": selector,
        "tool": tool,
        "backend": backend,
        "model": model,
        "approved_provider_request_sha256": approved_provider_request_sha256,
        "output_path": str(out_path.absolute()),
        "output_sha256": sha256_file(out_path),
        "output_size_bytes": out_path.stat().st_size,
        "provider_job": _video_provider_job_metadata(
            backend=backend,
            log_path=log_path,
        ),
    }
    temp_path = sidecar_path.with_name(
        f".{sidecar_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(sidecar_path)
    finally:
        temp_path.unlink(missing_ok=True)


def _require_exact_video_output_provenance(
    *,
    selector: str,
    approved_provider_request_sha256: str,
    out_path: Path,
) -> None:
    sidecar_path = _video_output_provenance_path(out_path)
    mismatches: list[str] = []
    try:
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sidecar = None
        mismatches.append("provenance_missing")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        sidecar = None
        mismatches.append("provenance_invalid")
    if not isinstance(sidecar, dict):
        if not mismatches:
            mismatches.append("provenance_invalid")
    else:
        if (
            str(sidecar.get("schema_version") or "")
            != VIDEO_OUTPUT_PROVENANCE_SCHEMA_VERSION
        ):
            mismatches.append("schema_version")
        if (
            str(sidecar.get("approved_provider_request_sha256") or "")
            != approved_provider_request_sha256
        ):
            mismatches.append("approved_provider_request_sha256")
        if str(sidecar.get("output_path") or "") != str(out_path.absolute()):
            mismatches.append("output_path")
        try:
            expected_size = int(sidecar.get("output_size_bytes"))
        except (TypeError, ValueError):
            expected_size = -1
        if out_path.stat().st_size != expected_size:
            mismatches.append("output_size_bytes")
        if str(sidecar.get("output_sha256") or "") != sha256_file(out_path):
            mismatches.append("output_sha256")
    if mismatches:
        raise SystemExit(
            f"{selector}: existing video output provenance does not match the approved request "
            f"({', '.join(dict.fromkeys(mismatches))}); use --force to regenerate"
        )


def _dispatch_reviewed_video_provider_call(
    *,
    selector: str,
    tool: str,
    api_prompt_payload: dict[str, Any],
    prompt: str,
    negative_prompt: str,
    input_image: Path | None,
    last_frame_image: Path | None,
    reference_images: list[Path],
    out_path: Path,
    log_dir: Path,
    poll_every: float,
    timeout_seconds: float,
    force: bool,
    dry_run: bool,
    gemini_client: GeminiClient | None,
    kling_client: KlingClient | None,
    evolink_client: EvoLinkClient | None,
    seedance_client: SeedanceClient | None,
) -> None:
    _assert_video_prompt_quality_allows_provider_execution(
        selector=selector,
        payload=api_prompt_payload,
    )
    reviewed = _reviewed_video_provider_request_values(
        selector=selector,
        api_prompt_payload=api_prompt_payload,
    )
    duration_seconds = int(reviewed["duration_seconds"])
    aspect_ratio = str(reviewed["aspect_ratio"])
    resolution = str(reviewed["quality"])
    backend = str(reviewed["backend"])
    model = str(reviewed["model"])
    extra_payload = dict(reviewed["extra_payload"])
    log_slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", selector).strip("._-") or "video"
    provider_log_path = log_dir / f"{log_slug}_video.json"
    approved_provider_request_sha256 = _approved_video_provider_request_sha256(
        selector=selector,
        tool=tool,
        api_prompt_payload=api_prompt_payload,
        prompt=prompt,
        negative_prompt=negative_prompt,
        out_path=out_path,
    )
    if not dry_run:
        if out_path.exists() and not force:
            _require_exact_video_output_provenance(
                selector=selector,
                approved_provider_request_sha256=approved_provider_request_sha256,
                out_path=out_path,
            )
            return
        _video_output_provenance_path(out_path).unlink(missing_ok=True)

    # The dispatch boundary already decided whether reuse is allowed. Bypass the
    # provider helpers' legacy existence-only short circuit so a concurrent stale
    # file cannot be silently adopted as the just-generated output.
    provider_force = bool(force or not dry_run)

    def finalize_output() -> None:
        if dry_run:
            return
        _write_video_output_provenance_atomic(
            selector=selector,
            tool=tool,
            backend=backend,
            model=model,
            approved_provider_request_sha256=approved_provider_request_sha256,
            out_path=out_path,
            log_path=provider_log_path,
        )

    if tool == "google_veo_3_1":
        if backend != "gemini":
            raise SystemExit(
                f"{selector}: reviewed backend {backend!r} does not match Veo"
            )
        segments, trim_to = _plan_veo_segments(duration_seconds)
        if len(segments) == 1:
            generate_veo_video(
                client=gemini_client,
                model=model,
                prompt=prompt,
                negative_prompt=negative_prompt,
                duration_seconds=segments[0],
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                input_image=input_image,
                last_frame_image=last_frame_image,
                reference_images=reference_images,
                out_path=out_path,
                poll_every=poll_every,
                timeout_seconds=timeout_seconds,
                force=provider_force,
                log_path=provider_log_path,
                dry_run=dry_run,
            )
            finalize_output()
            return
        if dry_run:
            print(
                f"[dry-run] VIDEO {selector}: segments={segments} then trim_to={trim_to}"
            )
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            segment_paths: list[Path] = []
            for index, segment_duration in enumerate(segments, start=1):
                segment_out = tmpdir_path / f"{log_slug}_seg{index}.mp4"
                generate_veo_video(
                    client=gemini_client,
                    model=model,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    duration_seconds=segment_duration,
                    aspect_ratio=aspect_ratio,
                    resolution=resolution,
                    input_image=input_image,
                    last_frame_image=last_frame_image,
                    reference_images=reference_images,
                    out_path=segment_out,
                    poll_every=poll_every,
                    timeout_seconds=timeout_seconds,
                    force=True,
                    log_path=log_dir / f"{log_slug}_video_seg{index}.json",
                    dry_run=False,
                )
                segment_paths.append(segment_out)
            concat_path = tmpdir_path / f"{log_slug}_concat.mp4"
            _ffmpeg_concat_videos(segment_paths, concat_path)
            if trim_to:
                _ffmpeg_trim_video(concat_path, out_path, int(trim_to))
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(concat_path.read_bytes())
        finalize_output()
        return

    if tool in {
        "kling_3_0",
        "kling",
        "kling_3_0_omni",
        "kling_omni",
        "kling-omni",
    }:
        if backend == "evolink":
            generate_evolink_video(
                client=evolink_client,
                model=model,
                prompt=prompt,
                negative_prompt=negative_prompt,
                duration_seconds=duration_seconds,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                input_image=input_image,
                last_frame_image=last_frame_image,
                extra_payload=extra_payload,
                out_path=out_path,
                poll_every=poll_every,
                timeout_seconds=timeout_seconds,
                force=provider_force,
                log_path=provider_log_path,
                dry_run=dry_run,
            )
            finalize_output()
            return
        if backend != "kling":
            raise SystemExit(
                f"{selector}: reviewed backend {backend!r} does not match Kling"
            )
        generate_kling_video(
            client=kling_client,
            model=model,
            prompt=prompt,
            negative_prompt=negative_prompt,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            input_image=input_image,
            last_frame_image=last_frame_image,
            extra_payload=extra_payload,
            out_path=out_path,
            poll_every=poll_every,
            timeout_seconds=timeout_seconds,
            force=provider_force,
            log_path=provider_log_path,
            dry_run=dry_run,
        )
        finalize_output()
        return

    if tool in {
        "seedance",
        "byteplus_seedance",
        "bytedance_seedance",
        "ark_seedance",
        "seadream_video",
        "seedream_video",
        "see_dream",
    }:
        if backend != "ark":
            raise SystemExit(
                f"{selector}: reviewed backend {backend!r} does not match Seedance"
            )
        generate_seedance_video(
            client=seedance_client,
            model=model,
            prompt=prompt,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            input_image=input_image,
            last_frame_image=last_frame_image,
            reference_images=reference_images,
            generate_audio=bool(reviewed["generate_audio"]),
            watermark=bool(reviewed["watermark"]),
            extra_payload=extra_payload,
            out_path=out_path,
            poll_every=poll_every,
            timeout_seconds=timeout_seconds,
            force=provider_force,
            log_path=provider_log_path,
            dry_run=dry_run,
        )
        finalize_output()
        return

    raise SystemExit(f"{selector}: unsupported video tool: {tool}")


def normalize_tool_name(tool: str | None) -> str:
    if not tool:
        return ""
    normalized = tool.strip().lower().replace(" ", "_")
    # Safety: treat Veo tool names as Kling to avoid accidental paid Google video calls.
    if normalized in {"google_veo_3_1", "veo", "veo_3_1", "veo3", "veo_3"}:
        return "kling_3_0_omni"
    if normalized in CODEX_BUILTIN_IMAGE_TOOL_ALIASES or normalized in DEPRECATED_EXTERNAL_IMAGE_TOOLS:
        return CODEX_BUILTIN_IMAGE_TOOL
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

        render_units = scene.get("render_units")
        if isinstance(render_units, list):
            for raw_unit in render_units:
                if not isinstance(raw_unit, dict):
                    continue
                unit_id = normalize_dotted_id(raw_unit.get("unit_id"))
                selector = _render_unit_selector(scene_id, unit_id) if unit_id is not None else f"scene{scene_id}_unit<missing>"
                source_cut_ids = [
                    cut_id
                    for cut_id in (normalize_dotted_id(value) for value in _ensure_str_list(raw_unit.get("source_cut_ids")))
                    if cut_id is not None
                ]
                if scene_filter:
                    filter_tokens = {selector, scene_id, _node_selector(scene_id)}
                    filter_tokens.update(_node_selector(scene_id, cut_id) for cut_id in source_cut_ids)
                    if not selector_matches(filter_tokens, scene_filter):
                        continue
                video_generation = raw_unit.get("video_generation") if isinstance(raw_unit.get("video_generation"), dict) else {}
                applied = _ensure_str_list(video_generation.get("applied_request_ids")) if isinstance(video_generation, dict) else []
                unknown_applied = [request_id for request_id in applied if request_id not in known_request_ids]
                if unknown_applied:
                    issues.append(
                        f"{selector}: unknown human_change_request id(s) in render_units.video_generation: "
                        + ", ".join(unknown_applied)
                    )

    if issues:
        raise SystemExit("Human review contract validation failed:\n- " + "\n- ".join(issues))


def resolve_path(base_dir: Path, maybe_path: str | None) -> Path | None:
    if not maybe_path:
        return None
    p = Path(maybe_path)
    return p if p.is_absolute() else (base_dir / p)


def _resolve_run_confined_video_path(
    *,
    base_dir: Path,
    maybe_path: str | None,
    selector: str,
    role: str,
) -> Path | None:
    raw_path = str(maybe_path or "").strip()
    if not raw_path:
        return None
    normalized = raw_path.replace("\\", "/")
    path = Path(raw_path)
    invalid_syntax = (
        path.is_absolute()
        or bool(re.match(r"^[A-Za-z]:/", normalized))
        or ".." in normalized.split("/")
    )
    candidate = base_dir / path
    try:
        candidate.resolve(strict=False).relative_to(base_dir.resolve(strict=False))
    except (OSError, RuntimeError, ValueError):
        invalid_syntax = True
    if invalid_syntax:
        raise SystemExit(
            f"{selector}: {role} must be a run-relative path confined to the manifest directory: "
            f"{raw_path}"
        )
    return candidate


def _require_run_confined_video_resolved_path(
    *,
    base_dir: Path,
    path: Path,
    selector: str,
    role: str,
) -> None:
    try:
        path.resolve(strict=False).relative_to(base_dir.resolve(strict=False))
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(
            f"{selector}: {role} must be a run-relative path confined to the manifest directory: "
            f"{path}"
        ) from exc


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


def _sanitize_contract_prompt_text(text: str) -> str:
    value = str(text or "").strip()
    replacements = (
        ("動画が動き出す直前に見えている初期状態。", ""),
        ("動画が動き出す直前に見えている初期状態", ""),
        ("動画が動き出す直前に見えている", ""),
        ("動画が動き出す直前", ""),
        ("最初の1フレーム", ""),
        ("1フレーム目", ""),
        ("first frame", ""),
        ("First frame", ""),
        ("prompt本文には制作メタを書かない", ""),
        ("prompt 本文には制作メタを書かない", ""),
        ("p600 image prompt authoring では参照しない", ""),
        ("p600では参照しない", ""),
        ("p800 motion prompt 専用。", ""),
        ("p800 motion prompt 専用", ""),
    )
    for old, new in replacements:
        value = value.replace(old, new)
    value = re.sub(r"\s+", " ", value).strip(" 。\n\t")
    return value.strip()


def _dedupe_nonempty(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _sanitize_contract_prompt_text(str(value or ""))
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _strip_legacy_prompt_blocks(prompt: str) -> str:
    lines: list[str] = []
    skip_old_heading = False
    for raw in (prompt or "").splitlines():
        stripped = raw.strip()
        if not stripped:
            skip_old_heading = False
            continue
        if re.fullmatch(r"\[(?:全体\s*/\s*不変条件|登場人物|小道具\s*/\s*舞台装置|シーン|連続性|禁止|cut契約からの可視要件)\]", stripped):
            skip_old_heading = True
            continue
        if skip_old_heading:
            skip_old_heading = False
        if re.search(r"場面の核:|画面上の問い:|観客理解の増分:|因果の証明:|映像で成立させる証拠:|必要な役割:|motion_brief:", stripped):
            continue
        cleaned = _sanitize_contract_prompt_text(stripped)
        if cleaned:
            lines.append(cleaned)
    return " ".join(_dedupe_nonempty(lines))


def _source_event_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return _dict_value(contract.get("source_event_contract"))


def _first_frame_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return _dict_value(contract.get("first_frame_contract"))


def _viewer_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return _dict_value(contract.get("viewer_contract"))


def _event_context_for_cut(contract: dict[str, Any]) -> dict[str, Any]:
    return _dict_value(contract.get("event_context_for_cut"))


def _image_prompt_section(title: str, lines: Iterable[Any]) -> str:
    cleaned = _dedupe_nonempty(lines)
    if not cleaned:
        cleaned = ["未指定の項目は、他のblockの具体描写と参照画像に矛盾しない範囲で自然に補完する。"]
    return f"[{title}]\n" + "\n".join(cleaned)


def _reference_usage_lines(scene: SceneSpec) -> list[str]:
    lines: list[str] = []
    if scene.image_character_ids:
        lines.append("人物参照: " + ", ".join(scene.image_character_ids) + " の顔、体格、衣装状態を維持する。")
    if scene.image_location_ids:
        lines.append("場所参照: " + ", ".join(scene.image_location_ids) + " の空間構造、床、壁、光源を背景基準にする。")
    if scene.image_object_ids:
        lines.append("小道具参照: " + ", ".join(scene.image_object_ids) + " の形状、素材、サイズ感を維持する。")
    if scene.image_references and not lines:
        lines.append("参照画像: " + " / ".join(scene.image_references) + " を、人物・場所・小道具の外観基準として使う。")
    if scene.image_references:
        lines.append("参照パス: " + " / ".join(scene.image_references))
    return lines


def _cut_start_state_lines(scene: SceneSpec) -> list[str]:
    contract = scene.cut_contract
    source = _source_event_contract(contract)
    first_frame = _first_frame_contract(contract)
    event_context = _event_context_for_cut(contract)
    primary_beat = _dict_value(event_context.get("primary_event_beat"))
    source_ids = _ensure_str_list(source.get("source_event_beat_ids"))
    primary_id = _contract_text(source, "primary_event_beat_id") or _contract_text(first_frame, "source_event_beat_id")
    lines = [
        f"source_event_beat_id: {primary_id or (source_ids[0] if source_ids else 'unknown')}",
        f"event_beat_function: {_contract_text(source, 'event_beat_function') or _contract_text(primary_beat, 'beat_function') or 'unknown'}",
        f"event_time_position: {_contract_text(source, 'event_time_position') or _contract_text(first_frame, 'event_time_position') or 'before_trigger'}",
    ]
    what_happens = (
        _contract_text(source, "source_event_summary")
        or _contract_text(primary_beat, "what_happens")
        or _contract_text(_viewer_contract(contract), "target_beat")
    )
    if what_happens:
        lines.append(f"what_happens: {what_happens}")
    visible_action = _contract_text(source, "source_visible_action") or _contract_text(primary_beat, "visible_action")
    if visible_action:
        lines.append(f"visible_action: {visible_action}")
    visible_reaction = _contract_text(source, "source_visible_reaction") or _contract_text(primary_beat, "visible_reaction")
    if visible_reaction:
        lines.append(f"visible_reaction: {visible_reaction}")
    visible_fact = _contract_text(first_frame, "event_fact_visible_in_still") or _contract_text(first_frame, "first_frame_brief")
    if visible_fact:
        lines.append(f"event_fact_visible_in_still: {visible_fact}")
    not_yet = _dedupe_nonempty(
        _contract_list(first_frame, "not_yet_happened_in_still")
        + _contract_list(source, "event_facts_not_to_invent")
        + _ensure_str_list(event_context.get("forbidden_event_changes"))
    )
    lines.append("not_yet_happened_in_still: " + (" / ".join(not_yet) if not_yet else "このcutの後続結果、次sceneの解決、未承認のrevealをまだ見せない。"))
    return lines


def _must_include_lines(scene: SceneSpec, base_prompt: str) -> list[str]:
    contract = scene.cut_contract
    viewer = _viewer_contract(contract)
    source = _source_event_contract(contract)
    first_frame = _first_frame_contract(contract)
    values = (
        _contract_list(viewer, "must_show")
        + _contract_list(first_frame, "must_include")
        + scene.image_character_ids
        + scene.image_object_ids
        + scene.image_location_ids
        + _contract_list(source, "event_facts_to_preserve")
    )
    cleaned = _dedupe_nonempty(values)
    if base_prompt:
        cleaned.append("追加の具体描写: " + base_prompt)
    return cleaned


def _must_not_include_lines(scene: SceneSpec) -> list[str]:
    contract = scene.cut_contract
    viewer = _viewer_contract(contract)
    source = _source_event_contract(contract)
    first_frame = _first_frame_contract(contract)
    event_context = _event_context_for_cut(contract)
    return _dedupe_nonempty(
        _contract_list(viewer, "must_avoid")
        + _contract_list(first_frame, "must_avoid")
        + _contract_list(first_frame, "not_yet_happened_in_still")
        + _contract_list(source, "event_facts_not_to_invent")
        + _contract_list(source, "forbidden_reveal_info_ids")
        + _ensure_str_list(event_context.get("forbidden_event_changes"))
    )


def _character_state_lines(scene: SceneSpec) -> list[str]:
    first_frame = _first_frame_contract(scene.cut_contract)
    visible = _dict_value(first_frame.get("visible_start_state"))
    continuity = _dict_value(scene.cut_contract.get("continuity_contract"))
    start_state = _dict_value(continuity.get("start_state"))
    lines = []
    costume = str(visible.get("costume_state") or start_state.get("character_state") or "").strip()
    if costume:
        lines.append(f"costume_state: {costume}")
    elif scene.image_character_ids:
        lines.append("costume_state: 参照画像とcutの時点に合う衣装状態を維持し、後続の衣装状態を先取りしない。")
    pose = str(visible.get("pose") or _contract_text(first_frame, "first_frame_brief") or "").strip()
    if pose:
        lines.append(f"pose: {pose}")
    gaze = str(visible.get("gaze_or_attention") or visible.get("gaze") or "").strip()
    if gaze:
        lines.append(f"gaze: {gaze}")
    emotional = str(visible.get("emotional_state") or first_frame.get("emotional_state") or "").strip()
    if emotional:
        lines.append(f"emotional_state: {emotional}")
    return lines


def _prop_setpiece_lines(scene: SceneSpec) -> list[str]:
    contract = scene.cut_contract
    source = _source_event_contract(contract)
    event_context = _event_context_for_cut(contract)
    allowed = _contract_list(source, "allowed_reveal_info_ids")
    forbidden = _contract_list(source, "forbidden_reveal_info_ids") + _ensure_str_list(event_context.get("forbidden_event_changes"))
    lines: list[str] = []
    if scene.image_object_ids:
        lines.append("object_state: " + ", ".join(scene.image_object_ids) + " を物語上の証拠として画面内の実物にする。")
        lines.append("visibility: " + ", ".join(f"{item}=clearly_visible" for item in scene.image_object_ids))
    elif allowed:
        lines.append("object_state: allowed reveal objects are visible only as required by this cut.")
        lines.append("visibility: " + ", ".join(f"{item}=clearly_visible" for item in allowed))
    else:
        lines.append("object_state: このcutで承認された小道具だけを画面に置く。")
        lines.append("visibility: 未承認または後続revealの小道具は hidden。")
    if forbidden:
        lines.append("must_not_show_yet: " + " / ".join(_dedupe_nonempty(forbidden)))
    meaning = _contract_text(_viewer_contract(contract), "visual_proof") or _contract_text(source, "source_event_summary")
    if meaning:
        lines.append(f"story_meaning_in_this_cut: {meaning}")
    return lines


def _composition_lines(scene: SceneSpec) -> list[str]:
    cinematic = _dict_value(scene.cut_contract.get("cinematic_contract"))
    geography = _dict_value(cinematic.get("screen_geography"))
    priority = _dict_value(cinematic.get("subject_priority"))
    lines = [
        f"aspect_ratio: {scene.image_aspect_ratio or '16:9'}",
        f"shot_size: {str(cinematic.get('shot_size') or 'medium wide').strip()}",
        f"camera_angle: {str(cinematic.get('camera_angle') or cinematic.get('camera_height') or '目線に近い映画的な高さ').strip()}",
        f"foreground: {str(geography.get('foreground') or '主要な小道具、足元、手元などの近景証拠').strip()}",
        f"midground: {str(geography.get('midground') or '主要人物の姿勢、表情、視線').strip()}",
        f"background: {str(geography.get('background') or '場所が読める建築、床、壁、空気感').strip()}",
    ]
    if priority:
        lines.append("subject_priority: " + " / ".join(f"{key}={value}" for key, value in priority.items() if str(value).strip()))
    return lines


def _light_material_lines(scene: SceneSpec, base_prompt: str) -> list[str]:
    first_frame = _first_frame_contract(scene.cut_contract)
    visible = _dict_value(first_frame.get("visible_start_state"))
    lines = [
        f"light_source: {str(visible.get('light_source') or 'scene固有の自然な光源').strip()}",
        f"light_direction: {str(visible.get('light_direction') or '人物と小道具の形が読める方向').strip()}",
    ]
    material = str(visible.get("dominant_materials") or "").strip()
    if not material:
        material_terms = [term for term in ("灰", "布", "木", "石", "金属", "ガラス", "水", "砂", "床", "階段") if term in base_prompt]
        material = "、".join(material_terms) if material_terms else "場所固有の床、壁、衣服、小道具の質感"
    lines.append(f"dominant_materials: {material}")
    air = str(visible.get("air_quality") or "").strip()
    if air:
        lines.append(f"air_quality: {air}")
    return lines


def _motion_start_affordance_lines(scene: SceneSpec) -> list[str]:
    first_frame = _first_frame_contract(scene.cut_contract)
    affordance = _dict_value(first_frame.get("motion_start_affordance"))
    lines = []
    for key in ("movable_subject", "movement_vector", "motion_should_start_from", "camera_start_reason", "must_not_resolve_in_image"):
        value = str(affordance.get(key) or "").strip()
        if value:
            lines.append(f"{key}: {value}")
    if not lines:
        visible_action = _contract_text(_source_event_contract(scene.cut_contract), "source_visible_action")
        if visible_action:
            lines.append(f"movable_subject: {visible_action}")
        lines.append("motion_should_start_from: この静止画に見える初期姿勢と視線から自然に動き出す。")
        lines.append("must_not_resolve_in_image: 行為完了後、次beat、次sceneの結果まで進めない。")
    return lines


def _infer_action_completion_state(event_time_position: str, first_frame: dict[str, Any]) -> str:
    explicit = str(first_frame.get("action_completion_state") or "").strip()
    if explicit:
        return explicit
    return {
        "before_trigger": "pre_action",
        "trigger_moment": "early_action",
        "early_action": "early_action",
        "mid_action": "mid_action",
        "consequence": "aftermath",
        "reaction_after": "aftermath",
        "handoff_after": "hold",
    }.get(event_time_position, "hold")


def _first_frame_visible_text(scene: SceneSpec) -> str:
    first_frame = _first_frame_contract(scene.cut_contract)
    cut_state = _dict_value(scene.cut_contract.get("cut_state_progression")) if isinstance(scene.cut_contract, dict) else {}
    state_visible = str(cut_state.get("state_visible_in_first_frame") or cut_state.get("state_visible_in_this_cut") or "").strip()
    if state_visible:
        return state_visible
    source = _source_event_contract(scene.cut_contract)
    event_context = _event_context_for_cut(scene.cut_contract)
    primary_beat = _dict_value(event_context.get("primary_event_beat"))
    return (
        _contract_text(first_frame, "event_fact_visible_in_still")
        or _contract_text(first_frame, "first_frame_brief")
        or _contract_text(source, "source_visible_action")
        or _contract_text(primary_beat, "visible_action")
        or _contract_text(_viewer_contract(scene.cut_contract), "visual_proof")
        or _strip_legacy_prompt_blocks(scene.image_prompt or "")
    )


def _build_first_frame_visual_plan(scene: SceneSpec, cut_contract: dict[str, Any] | None = None) -> dict[str, Any]:
    if (
        cut_contract is None
        and scene.image_first_frame_visual_plan
        and str(scene.image_api_prompt_payload.get("policy_version") or "").strip()
        == IMAGE_API_PROMPT_POLICY_VERSION_V2
    ):
        return json.loads(
            json.dumps(scene.image_first_frame_visual_plan, ensure_ascii=False)
        )
    contract = cut_contract if isinstance(cut_contract, dict) else scene.cut_contract
    source = _source_event_contract(contract)
    first_frame = _first_frame_contract(contract)
    cut_state = _dict_value(contract.get("cut_state_progression"))
    viewer = _viewer_contract(contract)
    event_context = _event_context_for_cut(contract)
    primary_beat = _dict_value(event_context.get("primary_event_beat"))
    cinematic = _dict_value(contract.get("cinematic_contract"))
    geography = _dict_value(cinematic.get("screen_geography"))
    priority = _dict_value(cinematic.get("subject_priority"))
    continuity = _dict_value(contract.get("continuity_contract"))
    visible_start = _dict_value(first_frame.get("visible_start_state"))
    motion_affordance = _dict_value(first_frame.get("motion_start_affordance"))
    motion_contract = _dict_value(contract.get("motion_contract"))

    source_ids = _ensure_str_list(source.get("source_event_beat_ids"))
    primary_id = (
        _contract_text(source, "primary_event_beat_id")
        or _contract_text(first_frame, "source_event_beat_id")
        or _contract_text(primary_beat, "beat_id")
        or (source_ids[0] if source_ids else "unknown")
    )
    event_time_position = (
        _contract_text(source, "event_time_position")
        or _contract_text(first_frame, "event_time_position")
        or "before_trigger"
    )
    progression_mode = str(cut_state.get("progression_mode") or "").strip()
    first_frame_temporal_role = str(cut_state.get("first_frame_temporal_role") or "").strip()
    action_completion_state = (
        str(cut_state.get("action_completion_state") or "").strip()
        or _infer_action_completion_state(event_time_position, first_frame)
    )
    if (
        progression_mode == "sequential_state_progression"
        and first_frame_temporal_role == "progressed_state_after_previous_cut"
        and action_completion_state in {"", "pre_action", "early_action"}
    ):
        action_completion_state = "progressed_state"
    not_yet = _dedupe_nonempty(
        _contract_list(first_frame, "not_yet_happened_in_still")
        + _contract_list(source, "event_facts_not_to_invent")
        + _ensure_str_list(event_context.get("forbidden_event_changes"))
        + _contract_list(motion_contract, "must_not_advance_to_event_beat_ids")
    )
    if progression_mode == "sequential_state_progression":
        not_yet = _dedupe_nonempty(
            _contract_list(motion_contract, "must_not_advance_to_event_beat_ids")
            + [cut_state.get("must_not_advance_beyond")]
            + _contract_list(source, "forbidden_reveal_info_ids")
            + _contract_list(first_frame, "must_avoid")
            + _contract_list(viewer, "must_avoid")
            + _ensure_str_list(event_context.get("forbidden_event_changes"))
        )
    if not not_yet:
        not_yet = (
            ["このcutの境界を越える後続結果、次sceneの解決、未承認のrevealを見せない。"]
            if progression_mode == "sequential_state_progression"
            else ["このcutの後続結果、次sceneの解決、未承認のrevealをまだ見せない。"]
        )

    event_fact_visible = _first_frame_visible_text(scene)
    must_show = _dedupe_nonempty(
        _contract_list(viewer, "must_show")
        + _contract_list(first_frame, "must_include")
        + scene.image_character_ids
        + scene.image_object_ids
        + scene.image_location_ids
        + _contract_list(source, "event_facts_to_preserve")
    )
    primary_anchor = (
        str(priority.get("primary") or "").strip()
        or (must_show[0] if must_show else "")
        or event_fact_visible
        or "このcutの主役になる人物・小道具・場所の証拠"
    )
    secondary_anchors = _dedupe_nonempty(
        [str(priority.get("secondary") or "").strip()]
        + must_show[1:4]
        + [str(priority.get("tertiary") or "").strip()]
    )
    forbidden_reveals = _dedupe_nonempty(
        _contract_list(source, "forbidden_reveal_info_ids")
        + _contract_list(first_frame, "must_avoid")
        + _contract_list(viewer, "must_avoid")
        + _ensure_str_list(event_context.get("forbidden_event_changes"))
    )
    object_entries = []
    for object_id in scene.image_object_ids:
        object_entries.append(
            {
                "object_id": object_id,
                "object_name": object_id,
                "visibility_in_this_cut": "clearly_visible",
                "object_state": f"{object_id} をこのcutの出来事に関係する実物として画面内に置く。",
                "relation_to_character": "主要人物の視線、手元、足元、または進路と関係づける。",
                "relation_to_event": event_fact_visible,
                "story_meaning_in_this_cut": _contract_text(viewer, "visual_proof") or _contract_text(source, "source_event_summary"),
                "required_screen_position": "foreground" if object_id == scene.image_object_ids[0] else "midground",
                "must_not_show_states": forbidden_reveals,
            }
        )
    if not object_entries:
        object_entries.append(
            {
                "object_id": "approved_story_evidence",
                "object_name": "このcutで承認された物語上の証拠",
                "visibility_in_this_cut": "hinted",
                "object_state": "未承認または後続revealの小道具は出さない。",
                "relation_to_character": "主要人物の行為や視線と矛盾しない位置。",
                "relation_to_event": event_fact_visible,
                "story_meaning_in_this_cut": _contract_text(viewer, "visual_proof") or _contract_text(source, "source_event_summary"),
                "required_screen_position": "midground",
                "must_not_show_states": forbidden_reveals,
            }
        )

    material = str(visible_start.get("dominant_materials") or "").strip()
    if not material:
        base_prompt = _strip_legacy_prompt_blocks(scene.image_prompt or "")
        material_terms = [term for term in ("灰", "布", "木", "石", "金属", "ガラス", "水", "砂", "床", "階段") if term in base_prompt]
        material = "、".join(material_terms) if material_terms else "場所固有の床、壁、衣服、小道具の質感"

    movement_vector = str(
        motion_affordance.get("movement_vector")
        or motion_contract.get("movement_vector")
        or motion_contract.get("subject_motion")
        or ""
    ).strip()
    if not movement_vector:
        movement_vector = "画面内の姿勢、視線、手足の位置から次の動きが自然に始まる方向。"
    movable_subject = str(
        motion_affordance.get("movable_subject")
        or motion_affordance.get("subject_id")
        or _contract_text(source, "source_visible_action")
        or primary_anchor
    ).strip()

    return {
        "schema_version": "first_frame_visual_plan_v1",
        "derived_from": [
            "scene_event.event_sequence[]",
            "cut_contract.source_event_contract",
            "cut_contract.first_frame_contract",
            "cut_contract.motion_contract",
            "cut_contract.event_context_for_cut",
        ],
        "editable": False,
        "source_grounding": {
            "scene_id": scene.scene_id,
            "cut_id": scene.manifest_cut_id or "",
            "source_event_beat_id": primary_id,
            "source_event_beat_ids": source_ids or [primary_id],
            "event_beat_function": _contract_text(source, "event_beat_function") or _contract_text(primary_beat, "beat_function") or "custom",
            "cut_function": _contract_text(contract, "cut_function") or "custom",
            "what_happens": _contract_text(source, "source_event_summary") or _contract_text(primary_beat, "what_happens") or _contract_text(viewer, "target_beat"),
            "visible_action": _contract_text(source, "source_visible_action") or _contract_text(primary_beat, "visible_action"),
            "visible_reaction": _contract_text(source, "source_visible_reaction") or _contract_text(primary_beat, "visible_reaction"),
            "event_facts_to_preserve": _contract_list(source, "event_facts_to_preserve"),
            "event_facts_not_to_invent": _contract_list(source, "event_facts_not_to_invent"),
            "allowed_reveal_info_ids": _contract_list(source, "allowed_reveal_info_ids"),
            "forbidden_reveal_info_ids": _contract_list(source, "forbidden_reveal_info_ids"),
        },
        "temporal_boundary": {
            "event_time_position": event_time_position,
            "first_visible_moment": event_fact_visible,
            "action_completion_state": action_completion_state,
            "event_fact_visible_in_still": event_fact_visible,
            "not_yet_happened_in_still": not_yet,
            "forbidden_future_event_beat_ids": _contract_list(motion_contract, "must_not_advance_to_event_beat_ids"),
            "forbidden_future_outcomes": not_yet,
            "still_must_not_show_completion": progression_mode != "sequential_state_progression",
            "one_visible_moment_rule": True,
        },
        "scene_state_progression": {
            "progression_mode": progression_mode or "suspended_moment",
            "cut_selector": str(cut_state.get("cut_selector") or scene.selector or scene.scene_id or "").strip(),
            "progression_position": str(cut_state.get("progression_position") or "").strip(),
            "first_frame_temporal_role": first_frame_temporal_role or "suspended_before_or_during_cut_event",
            "state_after_previous_cut": str(cut_state.get("state_after_previous_cut") or "").strip(),
            "state_visible_in_first_frame": str(cut_state.get("state_visible_in_first_frame") or cut_state.get("state_visible_in_this_cut") or event_fact_visible).strip(),
            "visible_state_delta_from_previous_cut": str(cut_state.get("visible_state_delta_from_previous_cut") or "").strip(),
            "must_not_revert_to": str(cut_state.get("must_not_revert_to") or "").strip(),
            "must_not_advance_beyond": str(cut_state.get("must_not_advance_beyond") or "").strip(),
            "done_when": _contract_list(cut_state, "done_when"),
        },
        "visual_translation": {
            "abstract_intent_terms": [],
            "concrete_visible_evidence": [
                {"abstract_term": "cutの出来事", "visible_substitute": event_fact_visible, "must_be_drawn_as": event_fact_visible}
            ],
            "nonvisual_terms_to_exclude_from_prompt": ["場面の核", "観客理解", "因果の証明", "価値変化", "場所の圧力"],
            "imageable_causal_proof": _contract_text(viewer, "visual_proof") or event_fact_visible,
            "imageable_pressure": _contract_text(viewer, "screen_question") or _contract_text(source, "source_visible_action"),
            "imageable_value_shift_evidence": _contract_text(viewer, "done_when") or event_fact_visible,
            "imageable_handoff_anchor": _contract_text(viewer, "handoff") or "",
        },
        "subject_binding": {
            "primary_subject": {
                "id": primary_anchor,
                "name": primary_anchor,
                "role": "protagonist" if scene.image_character_ids else "proof_object",
                "must_be_clearly_readable": True,
                "screen_priority": 1,
            },
            "secondary_subjects": [
                {"id": item, "name": item, "role": "supporting_visual_anchor", "relation_to_primary": "主役の行為や証拠を補強する。", "screen_priority": index + 2}
                for index, item in enumerate(secondary_anchors)
            ],
            "background_subjects": [
                {"id": item, "name": item, "role": "location_anchor", "visibility": "clearly_visible"}
                for item in scene.image_location_ids
            ],
        },
        "reference_binding": {
            "character_references": [
                {
                    "reference_label": ref,
                    "target_character_id": ref,
                    "preserve": ["face", "body_type", "hair", "costume_shape"],
                    "may_change": ["pose", "gaze", "lighting"],
                    "must_not_change": [],
                }
                for ref in scene.image_character_ids
            ],
            "object_references": [
                {
                    "reference_label": ref,
                    "target_object_id": ref,
                    "preserve": ["silhouette", "material", "scale"],
                    "required_visibility": "clearly_visible",
                }
                for ref in scene.image_object_ids
            ],
            "location_references": [
                {
                    "reference_label": ref,
                    "target_location_id": ref,
                    "preserve": ["layout", "material", "lighting_family"],
                    "may_change": ["camera_angle", "foreground_blocking"],
                }
                for ref in scene.image_location_ids
            ],
        },
        "character_state_gate": {
            "costume_state": str(visible_start.get("costume_state") or _dict_value(continuity.get("start_state")).get("character_state") or "参照画像とcutの時点に合う衣装状態を維持する。").strip(),
            "hair_state": str(visible_start.get("hair_state") or "参照画像とcut時点に合う髪型を維持する。").strip(),
            "physical_state": str(visible_start.get("physical_state") or event_fact_visible).strip(),
            "pose": str(visible_start.get("pose") or cut_state.get("state_visible_in_first_frame") or first_frame.get("first_frame_brief") or event_fact_visible).strip(),
            "gaze": str(visible_start.get("gaze_or_attention") or visible_start.get("gaze") or "主要な出来事の証拠へ向く。").strip(),
            "expression": str(visible_start.get("expression") or first_frame.get("expression") or "このcutの圧力や選択が読める表情。").strip(),
            "emotional_state": str(visible_start.get("emotional_state") or first_frame.get("emotional_state") or "scene内の現在の感情状態。").strip(),
            "hand_position": str(
                visible_start.get("hand_position")
                or ("前cutから進んだ状態に合う手元。" if progression_mode == "sequential_state_progression" else "行為が始まる直前または途中だと読める手の位置。")
            ).strip(),
            "foot_position": str(
                visible_start.get("foot_position")
                or ("前cutから進んだ位置関係が読める足元。" if progression_mode == "sequential_state_progression" else "次に動き出せる足元の重心。")
            ).strip(),
            "continuity_must_preserve": _contract_list(continuity, "must_preserve"),
            "must_not_show_character_states": _contract_list(first_frame, "must_not_show_character_states"),
        },
        "object_visibility_gate": {"objects": object_entries},
        "spatial_composition": {
            "aspect_ratio": scene.image_aspect_ratio or "16:9",
            "shot_size": str(cinematic.get("shot_size") or "medium_wide").strip(),
            "camera_height": str(cinematic.get("camera_height") or "目線に近い映画的な高さ").strip(),
            "camera_angle": str(cinematic.get("camera_angle") or cinematic.get("camera_height") or "目線に近い映画的な高さ").strip(),
            "lens_feel": str(cinematic.get("lens_feel") or "自然な遠近感").strip(),
            "depth_of_field": str(cinematic.get("depth_of_field") or "主役と物語上の証拠が読める被写界深度").strip(),
            "subject_priority_order": _dedupe_nonempty([primary_anchor] + secondary_anchors + scene.image_location_ids),
            "foreground": str(geography.get("foreground") or "主要な小道具、足元、手元などの近景証拠").strip(),
            "midground": str(geography.get("midground") or "主要人物の姿勢、表情、視線").strip(),
            "background": str(geography.get("background") or "場所が読める建築、床、壁、空気感").strip(),
            "negative_space": str(geography.get("negative_space") or "動き出す方向に余白を残す。").strip(),
            "gaze_path": str(geography.get("gaze_path") or "主要人物の視線が物語上の証拠へ流れる。").strip(),
            "screen_direction": str(geography.get("screen_direction") or "static").strip(),
            "frame_edge_handoff": str(geography.get("frame_edge_handoff") or "次の動きが始まる画面端に余白を残す。").strip(),
        },
        "scene_material_pack": {
            "location_id": scene.image_location_ids[0] if scene.image_location_ids else "",
            "dominant_materials": [material],
            "light_source": str(visible_start.get("light_source") or "scene固有の自然な光源").strip(),
            "light_direction": str(visible_start.get("light_direction") or "人物と小道具の形が読める方向").strip(),
            "light_quality": str(visible_start.get("light_quality") or "映画的だが場所に固有の光質").strip(),
            "air_quality": str(visible_start.get("air_quality") or "場所の空気感が読める。").strip(),
            "floor_or_ground_texture": str(visible_start.get("floor_or_ground_texture") or "足元の床または地面の質感。").strip(),
            "background_texture": str(visible_start.get("background_texture") or "背景の壁、床、空、建築の質感。").strip(),
            "story_specific_texture": str(visible_start.get("story_specific_texture") or material).strip(),
            "material_must_not_leak_from_other_scenes": _contract_list(first_frame, "material_must_not_include"),
        },
        "motion_affordance": {
            "movable_subjects": [
                {
                    "subject_id": movable_subject,
                    "visible_start_state": event_fact_visible,
                    "movement_vector": movement_vector,
                    "motion_can_begin_from_this_still": True,
                }
            ],
            "camera_start_reason": str(motion_affordance.get("camera_start_reason") or "主役と物語上の証拠を追える位置から動き出せる。").strip(),
            "image_supports_motion_start": True,
            "must_not_resolve_in_image": _ensure_str_list(motion_affordance.get("must_not_resolve_in_image")) or not_yet,
            "motion_ceiling": {
                "must_stop_before_event_beat_ids": _contract_list(motion_contract, "must_not_advance_to_event_beat_ids"),
                "must_not_complete_outcomes": _ensure_str_list(motion_affordance.get("must_not_resolve_in_image")) or not_yet,
            },
        },
        "prompt_rendering_policy": {
            "render_only_drawable_information": True,
            "do_not_render_internal_ids_except_source_event_beat_id": True,
            "do_not_render_design_meta": True,
            "do_not_render_future_motion_as_action": True,
            "convert_abstract_terms_to_visible_evidence": True,
            "final_prompt_language": "Japanese",
            "final_prompt_style": "concrete_visual_prompt",
        },
        "validation_gates": {
            "event_source_present": bool(primary_id),
            "temporal_boundary_present": bool(event_time_position),
            "not_yet_state_present": bool(not_yet),
            "single_moment_preserved": True,
            "visual_translation_complete": bool(event_fact_visible),
            "reference_binding_complete": bool(scene.image_references or scene.image_character_ids or scene.image_object_ids or scene.image_location_ids),
            "character_state_gate_complete": True,
            "object_visibility_gate_complete": bool(object_entries),
            "composition_specific": True,
            "scene_material_specific": True,
            "motion_affordance_complete": bool(movable_subject and movement_vector),
            "no_design_meta_leak": True,
            "no_future_event_leak": True,
        },
    }


def _render_first_frame_image_prompt(plan: dict[str, Any], *, base_prompt: str) -> str:
    source = _dict_value(plan.get("source_grounding"))
    temporal = _dict_value(plan.get("temporal_boundary"))
    visual = _dict_value(plan.get("visual_translation"))
    subjects = _dict_value(plan.get("subject_binding"))
    references = _dict_value(plan.get("reference_binding"))
    character = _dict_value(plan.get("character_state_gate"))
    objects = _dict_value(plan.get("object_visibility_gate"))
    composition = _dict_value(plan.get("spatial_composition"))
    material = _dict_value(plan.get("scene_material_pack"))
    motion = _dict_value(plan.get("motion_affordance"))

    character_refs = [
        f"人物参照: {item.get('target_character_id')} は face/body_type/hair/costume_shape を維持し、pose/gaze/lighting だけをcutに合わせる。"
        for item in _list_value(references.get("character_references"))
        if isinstance(item, dict) and str(item.get("target_character_id") or "").strip()
    ]
    object_refs = [
        f"小道具参照: {item.get('target_object_id')} は silhouette/material/scale を維持し、visibility={item.get('required_visibility') or 'clearly_visible'}。"
        for item in _list_value(references.get("object_references"))
        if isinstance(item, dict) and str(item.get("target_object_id") or "").strip()
    ]
    location_refs = [
        f"場所参照: {item.get('target_location_id')} は layout/material/lighting_family を維持し、camera_angle と foreground_blocking だけをcutに合わせる。"
        for item in _list_value(references.get("location_references"))
        if isinstance(item, dict) and str(item.get("target_location_id") or "").strip()
    ]
    primary = _dict_value(subjects.get("primary_subject"))
    secondary = [item for item in _list_value(subjects.get("secondary_subjects")) if isinstance(item, dict)]
    background = [item for item in _list_value(subjects.get("background_subjects")) if isinstance(item, dict)]
    evidence = [
        str(item.get("must_be_drawn_as") or item.get("visible_substitute") or "").strip()
        for item in _list_value(visual.get("concrete_visible_evidence"))
        if isinstance(item, dict)
    ]
    object_lines: list[str] = []
    for item in _list_value(objects.get("objects")):
        if not isinstance(item, dict):
            continue
        object_lines.extend(
            _dedupe_nonempty(
                [
                    f"object_id: {item.get('object_id')}",
                    f"object_state: {item.get('object_state')}",
                    f"visibility: {item.get('visibility_in_this_cut')}",
                    f"relation_to_character: {item.get('relation_to_character')}",
                    f"relation_to_event: {item.get('relation_to_event')}",
                    f"story_meaning_in_this_cut: {item.get('story_meaning_in_this_cut')}",
                    f"required_screen_position: {item.get('required_screen_position')}",
                    "must_not_show_states: " + " / ".join(_ensure_str_list(item.get("must_not_show_states"))),
                ]
            )
        )

    movable_lines: list[str] = []
    for item in _list_value(motion.get("movable_subjects")):
        if isinstance(item, dict):
            movable_lines.extend(
                _dedupe_nonempty(
                    [
                        f"movable_subject: {item.get('subject_id')}",
                        f"movement_vector: {item.get('movement_vector')}",
                        f"motion_should_start_from: {item.get('visible_start_state')}",
                    ]
                )
            )

    blocks = [
        _image_prompt_section("参照画像の使い方", character_refs + object_refs + location_refs),
        _image_prompt_section(
            "このcutの開始状態",
            [
                f"source_event_beat_id: {source.get('source_event_beat_id')}",
                f"event_beat_function: {source.get('event_beat_function')}",
                f"event_time_position: {temporal.get('event_time_position')}",
                f"what_happens: {source.get('what_happens')}",
                f"visible_action: {source.get('visible_action')}",
                f"visible_reaction: {source.get('visible_reaction')}",
                f"event_fact_visible_in_still: {temporal.get('event_fact_visible_in_still')}",
                "not_yet_happened_in_still: " + " / ".join(_ensure_str_list(temporal.get("not_yet_happened_in_still"))),
                f"action_completion_state: {temporal.get('action_completion_state')}",
                "forbidden_future_event_beat_ids: " + " / ".join(_ensure_str_list(temporal.get("forbidden_future_event_beat_ids"))),
            ],
        ),
        _image_prompt_section(
            "単一瞬間ルール",
            [
                f"visible_moment: {temporal.get('first_visible_moment')}",
                "must_not_mix: before_event / during_event / after_event / montage",
                "この画像は1つの瞬間だけを描く。同じ画像内に出来事の前・途中・後を同時に入れない。",
            ],
        ),
        _image_prompt_section(
            "画面に必ず見えるもの",
            [
                f"primary_visual_anchor: {primary.get('name') or primary.get('id')}",
                "secondary_visual_anchors: " + " / ".join(_dedupe_nonempty([str(item.get("name") or item.get("id") or "") for item in secondary])),
                "location_anchor: " + " / ".join(_dedupe_nonempty([str(item.get("name") or item.get("id") or "") for item in background])),
                f"light_anchor: {material.get('light_source')} / {material.get('light_direction')}",
                "required_story_evidence: " + " / ".join(_dedupe_nonempty(evidence + [str(visual.get("imageable_causal_proof") or "")])),
                f"追加の具体描写: {base_prompt}" if base_prompt else "",
            ],
        ),
        _image_prompt_section(
            "画面に入れてはいけないもの",
            [
                "forbidden_later_events: " + " / ".join(_ensure_str_list(temporal.get("forbidden_future_outcomes"))),
                "forbidden_reveals: " + " / ".join(_ensure_str_list(source.get("forbidden_reveal_info_ids"))),
                "forbidden_character_states: " + " / ".join(_ensure_str_list(character.get("must_not_show_character_states"))),
                "forbidden_object_states: " + " / ".join(_ensure_str_list(temporal.get("forbidden_future_outcomes"))),
                "unapproved_extra_subjects: 未承認の追加人物、後続sceneのreveal、字幕、ロゴ。",
            ],
        ),
        _image_prompt_section(
            "人物状態",
            [
                f"costume_state: {character.get('costume_state')}",
                f"hair_state: {character.get('hair_state')}",
                f"physical_state: {character.get('physical_state')}",
                f"pose: {character.get('pose')}",
                f"gaze: {character.get('gaze')}",
                f"expression: {character.get('expression')}",
                f"hand_position: {character.get('hand_position')}",
                f"foot_position: {character.get('foot_position')}",
                f"emotional_state: {character.get('emotional_state')}",
                "must_not_show: " + " / ".join(_ensure_str_list(character.get("must_not_show_character_states"))),
            ],
        ),
        _image_prompt_section("小道具 / 舞台装置", object_lines),
        _image_prompt_section(
            "構図",
            [
                f"aspect_ratio: {composition.get('aspect_ratio')}",
                f"shot_size: {composition.get('shot_size')}",
                f"camera_height: {composition.get('camera_height')}",
                f"camera_angle: {composition.get('camera_angle')}",
                f"lens_feel: {composition.get('lens_feel')}",
                f"depth_of_field: {composition.get('depth_of_field')}",
                f"foreground: {composition.get('foreground')}",
                f"midground: {composition.get('midground')}",
                f"background: {composition.get('background')}",
                "subject_priority: " + " / ".join(_ensure_str_list(composition.get("subject_priority_order"))),
                f"negative_space: {composition.get('negative_space')}",
                f"gaze_path: {composition.get('gaze_path')}",
                f"frame_edge_handoff: {composition.get('frame_edge_handoff')}",
            ],
        ),
        _image_prompt_section(
            "光 / 質感",
            [
                f"light_source: {material.get('light_source')}",
                f"light_direction: {material.get('light_direction')}",
                f"light_quality: {material.get('light_quality')}",
                "dominant_materials: " + " / ".join(_ensure_str_list(material.get("dominant_materials"))),
                f"air_quality: {material.get('air_quality')}",
                f"floor_or_ground_texture: {material.get('floor_or_ground_texture')}",
                f"scene_specific_texture: {material.get('story_specific_texture')}",
                "material_must_not_include: " + " / ".join(_ensure_str_list(material.get("material_must_not_leak_from_other_scenes"))),
            ],
        ),
        _image_prompt_section(
            "動画化のための開始余地",
            movable_lines
            + [
                f"camera_start_reason: {motion.get('camera_start_reason')}",
                f"image_supports_motion_start: {str(bool(motion.get('image_supports_motion_start'))).lower()}",
                "must_not_resolve_in_image: " + " / ".join(_ensure_str_list(motion.get("must_not_resolve_in_image"))),
                "motion_ceiling: " + " / ".join(_ensure_str_list(_dict_value(motion.get("motion_ceiling")).get("must_not_complete_outcomes"))),
            ],
        ),
        _image_prompt_section("禁止", ["text, subtitles, logos, watermark, anime, illustration, distorted anatomy, extra unapproved characters, wrong costume state, later event reveal."]),
    ]
    return "\n\n".join(blocks)


API_PROMPT_FORBIDDEN_GATES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "api_prompt_contains_no_scene_cut_ids",
        re.compile(
            r"\bscene\d+(?:\.\d+)?(?:[_-](?:cut|event)[A-Za-z0-9_.-]*)?\b|\b_event_[A-Za-z0-9_]+\b",
            re.I,
        ),
    ),
    (
        "api_prompt_contains_no_yaml_field_names",
        re.compile(
            r"first_frame_visual_plan|cut_contract|scene_event|source_event_contract|event_context_for_cut|validation_gates|"
            r"source_event_beat_id|event_time_position|what_happens|visible_action|motion_brief|debug_prompt_source|api_prompt_payload|"
            r"drawable_prompt_ir|dependencies|included_fragments|omitted_groups|required_groups|compiler_version|"
            r"scene_state_progression_plan|cut_state_progression|shot_design_contract|cut_location_frame_plan|"
            r"cut_visual_delta|blocking_and_interaction",
            re.I,
        ),
    ),
    ("api_prompt_contains_no_boolean_gate_values", re.compile(r"\b(?:true|false|null|none)\b", re.I)),
    ("api_prompt_contains_no_legacy_additional_description", re.compile(r"追加の具体描写|追加具体描写")),
    ("api_prompt_contains_no_abstract_story_terms", re.compile(r"場面の核|観客理解|因果の証明|価値変化|場所の圧力|場のルール|主人公の制限")),
    ("api_prompt_contains_no_unresolved_generic_placeholders", re.compile(r"\b(?:TODO|TBD|placeholder|approved_story_evidence|primary_visible_object|primary_visible_zone)\b", re.I)),
    ("api_prompt_contains_no_pipeline_stage_terms", re.compile(r"\bp[678]\d\d\b", re.I)),
)
API_PROMPT_FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = tuple(pattern for _, pattern in API_PROMPT_FORBIDDEN_GATES)
FINAL_IMAGE_PROMPT_LEAK_GATES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "final_prompt_contains_no_story_scene_management_text",
        re.compile(r"物語「[^」]+」の\s*scene\d+|この画像は物語「[^」]+」の一場面|(?:後続|次|前)\s*scene", re.I),
    ),
    ("final_prompt_contains_no_scene_cut_selector", re.compile(r"\bscene\d+[_-]cut\d+\b", re.I)),
    (
        "final_prompt_contains_no_internal_authoring_fields",
        re.compile(
            r"debug_prompt_source|first_frame_visual_plan|source_event_beat_id|event_time_position|what_happens|"
            r"visible_action|motion_brief|cut_contract|scene_event|validation_gates|api_prompt_payload",
            re.I,
        ),
    ),
)


def _scene_is_reference_asset_image(out_path: Path | None) -> bool:
    return bool(out_path and (_is_character_ref_path(out_path) or _is_object_ref_path(out_path) or _is_location_ref_path(out_path)))


def _api_prompt_text(value: Any, fallback: str = "") -> str:
    text = _sanitize_contract_prompt_text(str(value or "")).strip()
    for pattern in API_PROMPT_FORBIDDEN_PATTERNS:
        text = pattern.sub("", text)
    for term in (
        "source出来事",
        "scene開始",
        "scene_start_state",
        "same_camera_distance",
        "same_character_pose",
        "same_location_zone",
        "このcut",
        "前cut",
        "次cut",
        "変化cut",
        "sceneの",
        "scene固有",
    ):
        replacement = {
            "このcut": "この画像",
            "前cut": "前の画像",
            "次cut": "次の画像",
            "変化cut": "変化の画像",
            "sceneの": "場面の",
            "scene固有": "場面固有",
        }.get(term, "")
        text = text.replace(term, replacement)
    text = re.sub(r"\s+", " ", text).strip(" /。:：\n\t")
    return text or fallback


API_PROMPT_VALUE_LABELS = {
    "establishing": "場所と人物の関係を示す導入",
    "character_action": "人物の行為",
    "reaction": "人物の反応",
    "insert": "手元や小道具の寄り",
    "object_proof": "小道具が物語上の証拠になる画面",
    "b_roll": "補助的な証拠画面",
    "handoff": "次の動きへ渡す導線",
    "wide": "広い引き",
    "medium_wide": "やや引いた中広",
    "medium": "中景",
    "medium_closeup": "近めの中景",
    "closeup": "寄り",
    "extreme_closeup": "極端な寄り",
    "a_roll": "人物の本筋画面",
    "visible_not_touched": "見えているがまだ触れていない",
    "reaching_toward": "手を伸ばしかけている",
    "touching": "触れている",
    "holding": "持っている",
    "released": "手放した直後",
    "left_behind": "置き去りにされている",
    "not_visible": "画面に出さない",
    "scene_start_state": "場面の開始状態",
    "handoff_state": "次へ渡す直前",
    "deadline_pressure": "時間に急かされる方向",
    "reaction_hold": "反応を受け止める位置",
    "toward_next_scene": "次の場面へ向かう方向",
    "toward_primary_action": "主要な行為へ向かう位置",
    "proof_connected_to_scene": "証拠が場面の因果へつながる位置",
    "progressed_state": "前の状態から進んだ途中",
    "true": "ある",
    "false": "ない",
    "yes": "ある",
    "no": "ない",
}


def _api_prompt_display_value(value: Any) -> str:
    text = _api_prompt_text(value)
    if not text:
        return ""
    lowered = text.lower()
    if lowered in API_PROMPT_VALUE_LABELS:
        return API_PROMPT_VALUE_LABELS[lowered]
    for token, label in sorted(API_PROMPT_VALUE_LABELS.items(), key=lambda item: len(item[0]), reverse=True):
        text = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", label, text, flags=re.IGNORECASE)
    for token, label in {
        "same camera distance": "前と同じカメラ距離",
        "same character pose": "前と同じ人物姿勢",
        "same location zone": "前と同じ場所の切り取り",
        "full reveal": "最終的な明示",
        "next scene": "次の場面",
        "next cut": "次の画像",
        "previous cut": "前の画像",
    }.items():
        text = re.sub(re.escape(token), label, text, flags=re.IGNORECASE)
    return text


def _natural_api_prompt_line(line: Any) -> str:
    text = _api_prompt_text(line)
    if not text:
        return ""
    if text == "must_not_repeat":
        return "前の画像と同じ距離、同じ姿勢、同じ場所の切り取りを繰り返さない。"
    if ":" not in text:
        return text
    key, raw_value = text.split(":", 1)
    key = key.strip()
    value = _api_prompt_display_value(raw_value)
    if not value:
        return ""
    templates = {
        "shot_role": "この一枚は{value}として、画面上の意味が一目で伝わる構図にする。",
        "shot_scale": "画面サイズは{value}で、人物、場所、小道具の関係が読める距離にする。",
        "a_roll_or_b_roll": "{value}として、主役の行為または証拠物が自然に読める一枚にする。",
        "camera_position": "カメラ位置は{value}に置き、同じ場所でも前後の画像と違う見え方にする。",
        "camera_height": "カメラの高さは{value}。",
        "lens_feel": "レンズ感は{value}。",
        "should_show_face": "顔を見せる必要は{value}。",
        "should_show_hands": "手元を見せる必要は{value}。",
        "should_show_object_detail": "小道具の細部を見せる必要は{value}。",
        "cut_visible_moment": "この一枚では、{value}。",
        "visible_subjects": "画面には{value}が見える。",
        "action_completion_state": "行為は{value}の状態で、完了後の結果までは見せない。",
        "not_yet_happened": "まだ起きていない出来事は{value}。",
        "still_must_not_show": "この静止画では{value}を見せない。",
        "previous_cut_state": "前の画像では{value}。",
        "this_cut_delta": "この画像では{value}が新しく見える。",
        "must_not_revert": "前の状態へ戻らず、{value}を保つ。",
        "must_not_repeat": "前の画像と同じ距離、同じ姿勢、同じ場所の切り取りを繰り返さない。",
        "costume": "衣装は{value}。",
        "pose": "姿勢は{value}。",
        "gaze": "視線は{value}。",
        "expression": "表情は{value}。",
        "hand_position": "手元は{value}。",
        "foot_position": "足元は{value}。",
        "body_axis": "身体の向きは{value}。",
        "distance_to_other_subjects": "人物と周囲の距離は{value}。",
        "object_visibility": "小道具や物体は{value}。",
        "object_contact_state": "小道具への接触状態は{value}。",
        "object_position": "小道具は画面の{value}に置く。",
        "object_story_role": "小道具や場所の証拠は{value}として読ませる。",
        "object_must_not_show": "この画面では{value}を出さない。",
        "base_location_reference": "{value}",
        "location_zone": "場所は{value}を中心に切り取る。",
        "camera_station": "カメラは{value}から見る。",
        "foreground": "前景には{value}を置く。",
        "midground": "中景には{value}を置く。",
        "background": "背景には{value}を残す。",
        "set_dressing_delta": "{value}",
        "light_source": "光源は{value}。",
        "light_direction": "光の向きは{value}。",
        "material_focus": "質感は{value}を重点的に見せる。",
        "texture_specific_to_this_scene": "この場面固有の質感は{value}。",
        "material_must_not_leak": "{value}",
        "movable_subject": "動画開始時に動き出せる主体は{value}。",
        "movement_vector_visible_as_static_pose": "次の動きの方向は{value}として姿勢に残す。",
        "image_must_leave_room_for": "画面には{value}を残す。",
        "must_not_resolve": "この一枚で{value}まで解決しない。",
        "camera_start_reason": "カメラが動き出す理由は{value}。",
        "image_supports_motion_start": "動画開始に必要な余地を残す。",
        "motion_ceiling": "動画でも{value}までは進めない。",
    }
    template = templates.get(key)
    if template:
        return template.format(value=value)
    return value


def _api_prompt_section(title: str, lines: Iterable[Any]) -> str:
    cleaned = _dedupe_nonempty(_natural_api_prompt_line(line) for line in lines)
    if not cleaned:
        cleaned = ["この項目は、他の具体描写と参照画像に矛盾しない範囲で自然に補完する。"]
    return f"[{title}]\n" + "\n".join(cleaned)


def _api_prompt_pair_text(value: Any, fallback: str) -> str:
    if isinstance(value, dict):
        left = _api_prompt_text(value.get("left"))
        right = _api_prompt_text(value.get("right"))
        if left and right and left != right:
            return f"left: {left}; right: {right}"
        return left or right or fallback
    return _api_prompt_text(value, fallback)


def _previous_cut_selector(scene: SceneSpec) -> str:
    selector = scene.selector or ""
    cut_id = scene.manifest_cut_id or ""
    if cut_id.isdigit() and int(cut_id) > 1:
        previous = str(int(cut_id) - 1)
        if selector:
            return re.sub(r"cut0?\d+$", f"cut{previous}", selector)
        return f"scene{scene.manifest_scene_id}_cut{previous}"
    return ""


def _shot_design_contract_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    source = _dict_value(plan.get("source_grounding"))
    composition = _dict_value(plan.get("spatial_composition"))
    objects = _list_value(_dict_value(plan.get("object_visibility_gate")).get("objects"))
    cut_function = _api_prompt_text(source.get("cut_function"), "character_action")
    has_specific_object = any(
        isinstance(item, dict) and _api_prompt_text(item.get("object_id")) not in {"", "approved_story_evidence"}
        for item in objects
    )
    if has_specific_object:
        shot_role = "object_proof"
    elif cut_function in {"reaction", "payoff", "handoff"}:
        shot_role = cut_function
    elif cut_function in {"setup", "pressure"}:
        shot_role = "establishing"
    else:
        shot_role = "character_action"
    shot_scale = _api_prompt_text(composition.get("shot_size"), "medium")
    return {
        "shot_role": shot_role,
        "shot_scale": shot_scale,
        "a_roll_or_b_roll": "b_roll" if shot_role in {"insert", "object_proof", "b_roll"} else "a_roll",
        "camera_subject": {
            "primary": _api_prompt_text(_dict_value(_dict_value(plan.get("subject_binding")).get("primary_subject")).get("name"), "primary subject"),
            "secondary": " / ".join(
                _api_prompt_text(item.get("name") or item.get("id"))
                for item in _list_value(_dict_value(plan.get("subject_binding")).get("secondary_subjects"))
                if isinstance(item, dict)
            ),
        },
        "narrative_use": [shot_role, "motion_start"],
        "should_show_face": shot_role not in {"insert", "object_proof", "b_roll"},
        "should_show_hands": shot_role in {"insert", "object_proof", "character_action"},
        "should_show_object_detail": has_specific_object or shot_role in {"insert", "object_proof"},
    }


def _cut_location_frame_plan_from_plan(scene: SceneSpec, plan: dict[str, Any]) -> dict[str, Any]:
    composition = _dict_value(plan.get("spatial_composition"))
    material = _dict_value(plan.get("scene_material_pack"))
    location_id = _api_prompt_text(material.get("location_id") or (scene.image_location_ids[0] if scene.image_location_ids else ""), "location_reference")
    zone = _api_prompt_text(composition.get("foreground") or composition.get("background"), "この画面で行為が起きる場所の一部")
    return {
        "base_location_reference_id": location_id,
        "use_reference_as": "material_anchor",
        "location_zone_id": re.sub(r"\s+", "_", zone)[:80] or "primary_visible_zone",
        "location_zone_description": zone,
        "camera_station": _api_prompt_text(composition.get("camera_angle") or composition.get("camera_height"), "subject_side"),
        "framing_mode": _api_prompt_text(composition.get("shot_size"), "medium"),
        "foreground_zone": _api_prompt_text(composition.get("foreground"), "foreground action evidence"),
        "midground_zone": _api_prompt_text(composition.get("midground"), "main subject blocking"),
        "background_zone": _api_prompt_text(composition.get("background"), "location context"),
        "set_dressing_delta_from_base": {"add": [], "emphasize": [zone], "hide": []},
        "location_continuity_to_previous_cut": {
            "same_base_location": True,
            "changed_zone": zone,
            "changed_camera_station": _api_prompt_text(composition.get("camera_angle"), "camera station changes for this cut"),
            "changed_depth_layer": _api_prompt_text(composition.get("foreground"), "foreground layer changes"),
        },
    }


def _cut_visual_delta_from_plan(scene: SceneSpec, plan: dict[str, Any]) -> dict[str, Any]:
    character = _dict_value(plan.get("character_state_gate"))
    composition = _dict_value(plan.get("spatial_composition"))
    previous_selector = _previous_cut_selector(scene)
    current = _api_prompt_text(_dict_value(plan.get("temporal_boundary")).get("event_fact_visible_in_still"), "このcut固有の開始状態")
    return {
        "previous_cut_selector": previous_selector,
                    "previous_visible_state_summary": "前cutの構図をそのまま繰り返さない。" if previous_selector else "この場面の最初の画像なので場所と主体を明確に始める。",
        "this_cut_new_information": current,
        "changed_since_previous": {
            "character_pose": _api_prompt_text(character.get("pose"), "姿勢をこのcutの行為直前に変える"),
            "character_gaze": _api_prompt_text(character.get("gaze"), "視線の向きをこのcutの証拠へ変える"),
            "hand_position": _api_prompt_text(character.get("hand_position"), "手元をこのcutの行為直前に置く"),
            "foot_position": _api_prompt_text(character.get("foot_position"), "足先と重心を次の動きに向ける"),
            "camera_distance": _api_prompt_text(composition.get("shot_size"), "前cutと異なる距離"),
            "camera_angle": _api_prompt_text(composition.get("camera_angle"), "前cutと異なる角度"),
            "location_zone": _api_prompt_text(composition.get("foreground"), "前cutと異なる場所zone"),
            "emotional_state": _api_prompt_text(character.get("emotional_state"), "感情の変化が姿勢と表情で読める"),
        },
        "must_not_repeat_from_previous": ["same_camera_distance", "same_character_pose", "same_location_zone"],
        "cut_delta_visible_in_still": current,
    }


def _blocking_and_interaction_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    character = _dict_value(plan.get("character_state_gate"))
    objects = _list_value(_dict_value(plan.get("object_visibility_gate")).get("objects"))
    primary_object = next((item for item in objects if isinstance(item, dict)), {})
    object_id = _api_prompt_text(primary_object.get("object_id"), "この画面で確認できる主要な小道具")
    visible = _api_prompt_text(primary_object.get("visibility_in_this_cut"), "visible_not_touched")
    contact_state = "not_visible" if visible == "hidden" else "visible_not_touched"
    if "hand" in _api_prompt_text(character.get("hand_position")).lower() or "手" in _api_prompt_text(character.get("hand_position")):
        contact_state = "reaching_toward"
    return {
        "character_blocking": {
            "body_axis": _api_prompt_text(character.get("physical_state"), "身体軸は次の動きに向ける"),
            "head_direction": _api_prompt_text(character.get("gaze"), "視線方向へ頭を向ける"),
            "gaze_target": _api_prompt_text(character.get("gaze"), "主要な視覚証拠"),
            "hand_position": {
                "left": _api_prompt_text(character.get("hand_position"), "左手は身体近く"),
                "right": _api_prompt_text(character.get("hand_position"), "右手は行為の直前"),
            },
            "foot_position": {
                "left": _api_prompt_text(character.get("foot_position"), "左足に重心"),
                "right": _api_prompt_text(character.get("foot_position"), "右足は次に動ける向き"),
            },
            "weight_shift": _api_prompt_text(character.get("foot_position"), "次の動きに備えた重心"),
            "distance_to_primary_object": "手を伸ばせる距離だが、まだ完了していない。",
        },
        "object_interaction": {
            "object_id": object_id,
            "contact_state": contact_state,
            "object_screen_position": _api_prompt_text(primary_object.get("required_screen_position"), "foreground"),
            "object_distance_to_character": "人物の視線や手元と関係する距離。",
            "object_motion_potential": "動画開始後に接触または移動が始まる余地を残す。",
        },
    }


def _build_image_api_prompt_payload(scene: SceneSpec, *, request_visual_beat: str | None = None) -> dict[str, Any]:
    plan = _build_first_frame_visual_plan(scene)
    if request_visual_beat:
        plan = dict(plan)
        temporal_override = dict(_dict_value(plan.get("temporal_boundary")))
        temporal_override["event_fact_visible_in_still"] = request_visual_beat
        temporal_override["first_visible_moment"] = request_visual_beat
        plan["temporal_boundary"] = temporal_override
    shot = _shot_design_contract_from_plan(plan)
    location = _cut_location_frame_plan_from_plan(scene, plan)
    delta = _cut_visual_delta_from_plan(scene, plan)
    blocking = _blocking_and_interaction_from_plan(plan)
    return compile_image_api_prompt_v2(
        first_frame_visual_plan=plan,
        character_ids=scene.image_character_ids,
        object_ids=scene.image_object_ids,
        location_ids=scene.image_location_ids,
        reference_images=scene.image_references,
        story_time=scene.story_time,
        scene_time_of_day=scene.scene_time_of_day,
        review_metadata={
            "shot_design_contract": shot,
            "cut_location_frame_plan": location,
            "cut_visual_delta": delta,
            "blocking_and_interaction": blocking,
        },
    )


def _validate_frozen_v2_payload_matches_plan(
    scene: SceneSpec,
    payload: dict[str, Any],
) -> None:
    if not scene.image_first_frame_visual_plan:
        raise SystemExit(
            f"{scene.selector or scene.scene_id}: image_api_prompt_v2 requires stored first_frame_visual_plan"
        )
    expected = compile_image_api_prompt_v2(
        first_frame_visual_plan=scene.image_first_frame_visual_plan,
        character_ids=scene.image_character_ids,
        object_ids=scene.image_object_ids,
        location_ids=scene.image_location_ids,
        reference_images=scene.image_references,
        story_time=scene.story_time,
        scene_time_of_day=scene.scene_time_of_day,
    )
    canonical_keys = (
        "policy_version",
        "compiler_version",
        "source_digest",
        "prompt",
        "negative_prompt",
        "reference_instructions",
        "reference_images",
        "sha256",
        "drawable_prompt_ir",
    )
    mismatches = [key for key in canonical_keys if payload.get(key) != expected.get(key)]
    if mismatches:
        raise SystemExit(
            f"{scene.selector or scene.scene_id}: frozen v2 payload does not match "
            "first_frame_visual_plan/dependencies: "
            + ", ".join(mismatches)
        )


def _image_api_prompt_payload_for_scene(scene: SceneSpec, *, request_visual_beat: str | None = None) -> dict[str, Any]:
    existing = scene.image_api_prompt_payload if isinstance(scene.image_api_prompt_payload, dict) else {}
    if existing:
        policy_version = str(existing.get("policy_version") or "").strip()
        prompt = str(existing.get("prompt") or "").strip()
        if policy_version in SUPPORTED_IMAGE_API_PROMPT_POLICY_VERSIONS and not prompt:
            raise SystemExit(f"{scene.selector or scene.scene_id}: api_prompt_missing_for_new_prompt_policy")
        if policy_version in SUPPORTED_IMAGE_API_PROMPT_POLICY_VERSIONS and prompt:
            payload = dict(existing)
            payload.setdefault("negative_prompt", "")
            payload.setdefault("reference_instructions", "")
            payload.setdefault("reference_images", list(scene.image_references or []))
            actual_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            declared_sha256 = str(payload.get("sha256") or "").strip()
            if declared_sha256 and declared_sha256 != actual_sha256:
                raise SystemExit(
                    f"{scene.selector or scene.scene_id}: api_prompt_payload.sha256 does not match prompt"
                )
            payload["sha256"] = actual_sha256
            if policy_version == IMAGE_API_PROMPT_POLICY_VERSION_V2:
                _validate_frozen_v2_payload_matches_plan(scene, payload)
            if policy_version in SUPPORTED_IMAGE_API_PROMPT_POLICY_VERSIONS:
                _validate_image_api_prompt_payload(scene, payload)
            return payload

    payload = _build_image_api_prompt_payload(scene, request_visual_beat=request_visual_beat)
    _validate_image_api_prompt_payload(scene, payload)
    return payload


def _validate_image_api_prompt_payload(scene: SceneSpec, payload: dict[str, Any]) -> None:
    policy_version = str(payload.get("policy_version") or "").strip()
    prompt = str(payload.get("prompt") or "").strip()
    if policy_version in SUPPORTED_IMAGE_API_PROMPT_POLICY_VERSIONS and not prompt:
        raise SystemExit(f"{scene.selector or scene.scene_id}: api_prompt_missing_for_new_prompt_policy")
    if policy_version not in SUPPORTED_IMAGE_API_PROMPT_POLICY_VERSIONS:
        return

    issues: list[str] = []
    for gate_name, pattern in API_PROMPT_FORBIDDEN_GATES:
        if pattern.search(prompt):
            issues.append(gate_name)
    if policy_version == IMAGE_API_PROMPT_POLICY_VERSION_V2:
        if issues:
            raise SystemExit(
                f"{scene.selector or scene.scene_id}: Image API prompt v2 gate failed:\n- "
                + "\n- ".join(_dedupe_nonempty(issues))
            )
        return
    shot = payload.get("shot_design_contract") if isinstance(payload.get("shot_design_contract"), dict) else {}
    location = payload.get("cut_location_frame_plan") if isinstance(payload.get("cut_location_frame_plan"), dict) else {}
    delta = payload.get("cut_visual_delta") if isinstance(payload.get("cut_visual_delta"), dict) else {}
    blocking = payload.get("blocking_and_interaction") if isinstance(payload.get("blocking_and_interaction"), dict) else {}
    if not str(shot.get("shot_role") or "").strip():
        issues.append("api_prompt_has_shot_role")
    if not str(location.get("location_zone_id") or location.get("location_zone_description") or "").strip():
        issues.append("api_prompt_has_location_zone")
    if not str(delta.get("this_cut_new_information") or delta.get("cut_delta_visible_in_still") or "").strip():
        issues.append("api_prompt_has_previous_cut_delta")
    if not isinstance(blocking.get("character_blocking"), dict):
        issues.append("api_prompt_has_character_blocking")
    object_interaction = blocking.get("object_interaction") if isinstance(blocking.get("object_interaction"), dict) else {}
    if (scene.image_object_ids or scene.image_object_variant_ids) and not str(object_interaction.get("contact_state") or "").strip():
        issues.append("api_prompt_has_object_contact_state_if_object_present")
    if issues:
        raise SystemExit(
            f"{scene.selector or scene.scene_id}: Image API prompt v1 gate failed:\n- "
            + "\n- ".join(_dedupe_nonempty(issues))
        )


def _validate_final_image_prompt_no_leaks(*, prompt: str, selector: str) -> None:
    issues = [gate_name for gate_name, pattern in FINAL_IMAGE_PROMPT_LEAK_GATES if pattern.search(prompt or "")]
    if issues:
        raise SystemExit(
            f"{selector}: final image prompt leak gate failed:\n- "
            + "\n- ".join(_dedupe_nonempty(issues))
        )


def _final_image_prompt_editor(
    *,
    prompt: str,
    output: str,
    references: list[str],
    topic: str = "",
) -> str:
    text = _rewrite_request_prompt_for_review(
        prompt=prompt,
        output=output,
        references=references,
        topic=topic,
    )
    text = re.sub(r"\n?```[A-Za-z0-9_-]*\s*\n.*?\n```\n?", "\n", text, flags=re.DOTALL)
    text = re.sub(r"(?m)^\s*(debug_prompt_source|api_prompt_payload|first_frame_visual_plan)\s*:.*$", "", text)
    text = re.sub(r"(?m)^\s*(source_event_beat_id|event_time_position|what_happens|visible_action|motion_brief)\s*:.*$", "", text)
    text = re.sub(
        r"\s*(?:source_event_beat_id|event_time_position|what_happens|visible_action|motion_brief)\s*:[^。\n]*(?:。|$)",
        "。",
        text,
        flags=re.I,
    )
    text = text.replace("このcut", "この画像")
    text = text.replace("この cut", "この画像")
    text = re.sub(r"後続\s*scene", "後続画像", text, flags=re.I)
    text = re.sub(r"次\s*scene", "後続画像", text, flags=re.I)
    text = re.sub(r"前\s*scene", "前段画像", text, flags=re.I)
    text = re.sub(r"(後続画像|前段画像)\s+でも", r"\1でも", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    return text.strip()


def _asset_image_api_prompt_payload_for_scene(scene: SceneSpec, *, topic: str = "") -> dict[str, Any]:
    source_prompt = str(scene.image_prompt or "").strip()
    if not source_prompt:
        raise SystemExit(f"{scene.selector or scene.scene_id}: asset_api_prompt_missing_source_prompt")
    prompt = _final_image_prompt_editor(
        prompt=source_prompt,
        output=scene.image_output or "",
        references=list(scene.image_references or []),
        topic=topic,
    )
    if not prompt:
        raise SystemExit(f"{scene.selector or scene.scene_id}: asset_api_prompt_empty_after_editor")
    _validate_final_image_prompt_no_leaks(prompt=prompt, selector=scene.image_asset_id or scene.selector or scene.scene_id)
    return {
        "policy_version": IMAGE_API_PROMPT_POLICY_VERSION,
        "compiler_version": ASSET_PROMPT_COMPILER_VERSION,
        "source_digest": sha256_canonical_json(
            {
                "source_prompt": source_prompt,
                "output": scene.image_output or "",
                "references": list(scene.image_references or []),
            }
        ),
        "prompt": prompt,
        "negative_prompt": "text, subtitles, logos, watermark, anime, illustration, production metadata, scene ids, debug metadata",
        "reference_instructions": "",
        "reference_images": list(scene.image_references or []),
        "sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "compiler": ASSET_PROMPT_COMPILER_VERSION,
        "editor": "deterministic_drawable_prompt_editor_v1",
    }


def _structured_image_prompt_blocks(scene: SceneSpec) -> str:
    base_prompt = _strip_legacy_prompt_blocks(scene.image_prompt or "")
    plan = _build_first_frame_visual_plan(scene)
    return _render_first_frame_image_prompt(plan, base_prompt=base_prompt)


def _cut_contract_video_prompt_block(contract: dict[str, Any]) -> str:
    if not contract:
        return ""
    lines: list[str] = []
    cut_function = _contract_text(contract, "cut_function")
    target_beat = _contract_text(contract, "target_beat", "viewer_contract.target_beat")
    motion_brief = _contract_text(contract, "motion_brief", "motion_contract.motion_brief")
    camera_motion = _contract_text(contract, "motion_contract.camera_motion")
    subject_motion = _contract_text(contract, "motion_contract.subject_motion")
    environment_motion = _contract_text(contract, "motion_contract.environment_motion")
    emotional_change = _contract_text(contract, "motion_contract.emotional_change")
    start_from_visible_state = _contract_text(contract, "motion_contract.start_from_visible_state")
    end_state = _contract_text(contract, "motion_contract.end_state", "motion_end_state")
    end_frame_brief = _contract_text(contract, "motion_contract.end_frame_brief")
    must_not_add = _contract_list(contract, "motion_contract.must_not_add")
    if cut_function:
        lines.append(f"cut_function: {cut_function}")
    if target_beat:
        lines.append(f"target_beat: {target_beat}")
    if motion_brief:
        lines.append(f"motion_brief: {motion_brief}")
    if camera_motion:
        lines.append(f"camera_motion: {camera_motion}")
    if subject_motion:
        lines.append(f"subject_motion: {subject_motion}")
    if environment_motion:
        lines.append(f"environment_motion: {environment_motion}")
    if emotional_change:
        lines.append(f"emotional_change: {emotional_change}")
    if start_from_visible_state:
        lines.append(f"start_from_visible_state: {start_from_visible_state}")
    if end_state:
        lines.append(f"end_state: {end_state}")
    if end_frame_brief:
        lines.append(f"end_frame_brief: {end_frame_brief}")
    if must_not_add:
        lines.append("must_not_add: " + " / ".join(must_not_add))
    if not lines:
        return ""
    return "cut_contract:\n" + "\n".join(lines)


def _compose_final_image_prompt(
    scene: SceneSpec,
    *,
    prefix: str,
    suffix: str,
    request_visual_beat: str | None = None,
) -> str:
    prompt = _structured_image_prompt_blocks(scene)
    visual_beat = (request_visual_beat or "").strip()
    if visual_beat and visual_beat not in prompt:
        prompt = prompt.replace("[画面に必ず見えるもの]\n", f"[画面に必ず見えるもの]\n{_sanitize_contract_prompt_text(visual_beat)}\n", 1)
    if prefix:
        prompt = prefix + "\n\n" + prompt if prompt else prefix
    if suffix:
        prompt = prompt + "\n\n" + suffix if prompt else suffix
    return prompt.strip()


def _compose_final_video_prompt(scene: SceneSpec, *, prefix: str, suffix: str) -> str:
    return str(
        _video_api_prompt_payload_for_scene(scene, prefix=prefix, suffix=suffix).get("prompt")
        or ""
    ).strip()


def _video_api_prompt_payload_for_scene(
    scene: SceneSpec,
    *,
    prefix: str,
    suffix: str,
) -> dict[str, Any]:
    return compile_video_api_prompt_v1(
        cut_contract=scene.cut_contract,
        video_generation=scene.video_generation_contract,
        source_prompt=(
            scene.video_prompt_authoring_source
            or scene.video_motion_prompt
            or ""
        ),
        story_time=scene.story_time,
        time_of_day=scene.scene_time_of_day,
        tool=normalize_tool_name(scene.video_tool) or scene.video_tool or "kling_3_0",
        first_frame=scene.video_first_frame or scene.video_input_image or scene.image_output or "",
        last_frame=scene.video_last_frame or "",
        duration_seconds=scene.duration_seconds,
        references=scene.video_references,
        reference_roles=scene.video_reference_roles or None,
        quality=scene.video_quality,
        aspect_ratio=scene.video_aspect_ratio,
        first_frame_visual_plan=scene.image_first_frame_visual_plan,
        scene_time_of_day_visual_basis=scene.scene_time_of_day_visual_basis,
        scene_location_mode=scene.scene_location_mode,
        scene_location_sequence=scene.scene_location_sequence,
        scene_location_segments=scene.scene_location_segments,
        prefix=prefix,
        suffix=suffix,
    )


def _video_contract_for_target(target: VideoRenderTargetSpec) -> dict[str, Any]:
    composed = compose_video_render_unit_contract(
        [
            source.cut_contract
            for source in target.source_scenes
            if isinstance(source.cut_contract, dict)
        ]
    )
    return resolve_video_prompt_contract(
        {},
        cut_contract=target.video_cut_contract,
        scene_contract=composed,
    )


def _video_api_prompt_payload_for_target(
    target: VideoRenderTargetSpec,
    *,
    prefix: str,
    suffix: str,
    first_frame_override: Any = _UNSET,
    last_frame_override: Any = _UNSET,
    duration_seconds_override: Any = _UNSET,
    references_override: Any = _UNSET,
    quality: str | None = None,
    aspect_ratio: str | None = None,
    execution_options: dict[str, Any] | None = None,
    additional_negative_prompt: str = "",
) -> dict[str, Any]:
    first_source = target.source_scenes[0] if target.source_scenes else None
    reference_image_mode = (
        (target.video_input_mode or "").strip() == "reference_images"
    )
    default_first_frame = "" if reference_image_mode else (
        target.video_first_frame
        or target.video_input_image
        or (first_source.video_first_frame if first_source else "")
        or (first_source.video_input_image if first_source else "")
        or (first_source.image_output if first_source else "")
        or ""
    )
    first_frame = (
        default_first_frame
        if first_frame_override is _UNSET
        else str(first_frame_override or "")
    )
    last_frame = (
        ("" if reference_image_mode else target.video_last_frame)
        if last_frame_override is _UNSET
        else str(last_frame_override or "")
    )
    duration_seconds = (
        target.duration_seconds
        if duration_seconds_override is _UNSET
        else duration_seconds_override
    )
    references = (
        _video_target_reference_strings(target)
        if references_override is _UNSET
        else list(references_override or [])
    )
    normalized_tool = normalize_tool_name(target.video_tool) or target.video_tool or "kling_3_0"
    if normalized_tool in {
        "kling_3_0",
        "kling",
        "kling_3_0_omni",
        "kling_omni",
        "kling-omni",
    } and any(str(reference or "").strip() for reference in references):
        raise SystemExit(
            f"{target.selector}: Kling video requests do not support auxiliary references; "
            "use first_frame/last_frame only, or select a provider with typed reference support"
        )
    return compile_video_api_prompt_v1(
        cut_contract=_video_contract_for_target(target),
        video_generation=target.video_generation_contract,
        source_prompt=(
            target.video_prompt_authoring_source
            or target.video_motion_prompt
            or ""
        ),
        story_time=first_source.story_time if first_source else "",
        time_of_day=first_source.scene_time_of_day if first_source else "",
        tool=normalized_tool,
        first_frame=first_frame,
        last_frame=last_frame or "",
        duration_seconds=duration_seconds,
        references=references,
        reference_roles=target.video_reference_roles or None,
        quality=quality if quality is not None else target.video_quality,
        aspect_ratio=(
            aspect_ratio if aspect_ratio is not None else target.video_aspect_ratio
        ),
        execution_options=execution_options,
        additional_negative_prompt=additional_negative_prompt,
        first_frame_visual_plan=(
            first_source.image_first_frame_visual_plan if first_source else {}
        ),
        scene_time_of_day_visual_basis=(
            first_source.scene_time_of_day_visual_basis
            if first_source
            else None
        ),
        scene_location_mode=(
            first_source.scene_location_mode if first_source else ""
        ),
        scene_location_sequence=(
            first_source.scene_location_sequence if first_source else []
        ),
        scene_location_segments=(
            first_source.scene_location_segments if first_source else []
        ),
        review_only_dependencies=(
            {
                "render_unit_source_cut_ids": list(target.source_cut_ids),
                "render_unit_source_cut_contracts": [
                    source.cut_contract for source in target.source_scenes
                ],
            }
            if target.unit_id is not None
            else None
        ),
        prefix=prefix,
        suffix=suffix,
    )


def _video_execution_options(
    *,
    target: VideoRenderTargetSpec,
    args: argparse.Namespace,
    has_first_frame: bool,
    has_reference_images: bool,
    evolink_enabled: bool,
    kling_extra_payload: dict[str, Any] | None,
    kling_omni_extra_payload: dict[str, Any] | None,
    ark_extra_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    tool = normalize_tool_name(target.video_tool)
    options: dict[str, Any] = {}
    if tool in {"kling_3_0", "kling", "kling_3_0_omni", "kling_omni", "kling-omni"}:
        options["backend"] = "evolink" if evolink_enabled else "kling"
        if evolink_enabled:
            if tool in {"kling_3_0_omni", "kling_omni", "kling-omni"}:
                options["model"] = (
                    args.evolink_kling_o3_i2v_model
                    if has_first_frame
                    else args.evolink_kling_o3_t2v_model
                )
                options["extra_payload"] = (
                    kling_omni_extra_payload or kling_extra_payload or {}
                )
            else:
                options["model"] = (
                    args.evolink_kling_v3_i2v_model
                    if has_first_frame
                    else args.evolink_kling_v3_t2v_model
                )
                options["extra_payload"] = kling_extra_payload or {}
        elif tool in {"kling_3_0_omni", "kling_omni", "kling-omni"}:
            options["model"] = args.kling_omni_video_model
            options["extra_payload"] = (
                kling_omni_extra_payload or kling_extra_payload or {}
            )
        else:
            options["model"] = args.kling_video_model
            options["extra_payload"] = kling_extra_payload or {}
    elif tool in {
        "seedance",
        "byteplus_seedance",
        "bytedance_seedance",
        "ark_seedance",
        "seadream_video",
        "seedream_video",
        "see_dream",
    }:
        options.update(
            {
                "backend": "ark",
                "model": (
                    args.ark_seedance_i2v_model
                    if has_first_frame or has_reference_images
                    else args.ark_seedance_t2v_model
                ),
                "generate_audio": bool(args.ark_generate_audio),
                "watermark": False,
                "extra_payload": ark_extra_payload or {},
            }
        )
    elif tool == "google_veo_3_1":
        options.update({"backend": "gemini", "model": args.gemini_video_model})
    return options


def _video_reference_content_sha256s(
    *,
    base_dir: Path,
    bindings: Iterable[str],
    selector: str = "video_request",
) -> dict[str, str]:
    content_sha256s: dict[str, str] = {}
    for raw_binding in bindings:
        binding = str(raw_binding or "").strip()
        if not binding or binding in content_sha256s:
            continue
        path = _resolve_run_confined_video_path(
            base_dir=base_dir,
            maybe_path=binding,
            selector=selector,
            role="reference image",
        )
        if path is not None and path.is_file():
            content_sha256s[binding] = sha256_file(path)
    return content_sha256s


def _snapshot_reviewed_video_reference_inputs(
    *,
    base_dir: Path,
    selector: str,
    api_prompt_payload: dict[str, Any],
    input_image: Path | None,
    last_frame_image: Path | None,
    reference_images: list[Path],
) -> tuple[Path | None, Path | None, Path | None, list[Path]]:
    binding = _dict_value(api_prompt_payload.get("provider_request_binding"))
    execution_options = _dict_value(binding.get("execution_options"))
    expected_by_binding = _dict_value(
        execution_options.get("reference_content_sha256")
    )
    first_binding = str(binding.get("first_frame") or "").strip()
    last_binding = str(binding.get("last_frame") or "").strip()
    raw_reference_bindings = binding.get("references")
    if not isinstance(raw_reference_bindings, list):
        raw_reference_bindings = []
    reference_bindings = [
        str(reference or "").strip() for reference in raw_reference_bindings
    ]
    if len(reference_bindings) != len(reference_images):
        raise SystemExit(
            f"{selector}: reviewed video reference list does not match resolved inputs"
        )
    if bool(first_binding) != bool(input_image) or bool(last_binding) != bool(
        last_frame_image
    ):
        raise SystemExit(
            f"{selector}: reviewed video frame bindings do not match resolved inputs"
        )

    raw_inputs: list[tuple[str, Path | None]] = [
        (first_binding, input_image),
        (last_binding, last_frame_image),
        *list(zip(reference_bindings, reference_images, strict=True)),
    ]
    present_inputs = [
        (reference, source)
        for reference, source in raw_inputs
        if reference or source is not None
    ]
    if not present_inputs:
        return None, None, None, []

    snapshot_dir = (
        base_dir
        / "scratch"
        / "video_request_inputs"
        / f"{time.time_ns()}_{uuid.uuid4().hex}"
    )
    snapshot_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    copied_by_source: dict[Path, Path] = {}
    try:
        for index, (reference, source) in enumerate(present_inputs, start=1):
            if not reference or source is None:
                raise SystemExit(
                    f"{selector}: reviewed video reference binding is incomplete"
                )
            expected_source = _resolve_run_confined_video_path(
                base_dir=base_dir,
                maybe_path=reference,
                selector=selector,
                role="reference image",
            )
            _require_run_confined_video_resolved_path(
                base_dir=base_dir,
                path=source,
                selector=selector,
                role="reference image",
            )
            if expected_source is None or expected_source.absolute() != source.absolute():
                raise SystemExit(
                    f"{selector}: reviewed video reference path changed before provider submission"
                )
            expected_digest = str(expected_by_binding.get(reference) or "").strip()
            if not expected_digest:
                raise SystemExit(
                    f"{selector}: reviewed video reference content hash is missing"
                )
            copied = copied_by_source.get(source)
            if copied is None:
                suffix = source.suffix.lower() or ".bin"
                copied = snapshot_dir / f"reference_{index:02d}{suffix}"
                shutil.copyfile(source, copied)
                copied_by_source[source] = copied
            if sha256_file(copied) != expected_digest:
                raise SystemExit(
                    f"{selector}: reviewed video reference content changed before provider submission"
                )

        copied_input = copied_by_source.get(input_image) if input_image else None
        copied_last = (
            copied_by_source.get(last_frame_image) if last_frame_image else None
        )
        copied_references = [copied_by_source[path] for path in reference_images]
        return snapshot_dir, copied_input, copied_last, copied_references
    except BaseException:
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise


def _video_execution_options_with_reference_content(
    *,
    options: dict[str, Any],
    base_dir: Path,
    bindings: Iterable[str],
    stored_payload: dict[str, Any] | None,
    materializing: bool,
    selector: str = "video_request",
) -> dict[str, Any]:
    bound_options = dict(options)
    content_sha256s: dict[str, str] = {}
    if materializing:
        content_sha256s = _video_reference_content_sha256s(
            base_dir=base_dir,
            bindings=bindings,
            selector=selector,
        )
    else:
        provider_binding = (
            stored_payload.get("provider_request_binding")
            if isinstance(stored_payload, dict)
            and isinstance(stored_payload.get("provider_request_binding"), dict)
            else {}
        )
        stored_options = (
            provider_binding.get("execution_options")
            if isinstance(provider_binding.get("execution_options"), dict)
            else {}
        )
        stored_hashes = stored_options.get("reference_content_sha256")
        if isinstance(stored_hashes, dict):
            content_sha256s = {
                str(path).strip(): str(digest).strip()
                for path, digest in stored_hashes.items()
                if str(path).strip() and str(digest).strip()
            }
            current_hashes = _video_reference_content_sha256s(
                base_dir=base_dir,
                bindings=content_sha256s.keys(),
                selector=selector,
            )
            stale = [
                path
                for path, expected_digest in content_sha256s.items()
                if current_hashes.get(path) != expected_digest
            ]
            if stale:
                raise SystemExit(
                    "video reference content changed after prompt review: "
                    + ", ".join(stale)
                    + "; rematerialize and review"
                )
    if content_sha256s:
        bound_options["reference_content_sha256"] = content_sha256s
    else:
        bound_options.pop("reference_content_sha256", None)
    return bound_options


def _compose_final_video_prompt_for_target(
    target: VideoRenderTargetSpec,
    *,
    prefix: str,
    suffix: str,
) -> str:
    return str(
        _video_api_prompt_payload_for_target(target, prefix=prefix, suffix=suffix).get("prompt")
        or ""
    ).strip()


def _write_request_preview_md(
    *,
    out_path: Path,
    title: str,
    entries: list[dict[str, Any]],
    topic: str = "",
    merge_existing_sections: bool = False,
    drop_existing_sections: Iterable[str] = (),
) -> None:
    dropped_sections = {
        str(selector).strip()
        for selector in drop_existing_sections
        if str(selector).strip()
    }
    lines: list[str] = [f"# {title}", ""]
    if not entries:
        if merge_existing_sections and out_path.is_file():
            if dropped_sections:
                rendered = _merge_video_request_preview_sections(
                    out_path.read_text(encoding="utf-8"),
                    "\n".join(lines),
                    drop_existing_sections=dropped_sections,
                )
                out_path.write_text(rendered, encoding="utf-8")
            return
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
        if entry.get("asset_id"):
            lines.append(f"- asset_id: `{entry['asset_id']}`")
        if entry.get("asset_type"):
            lines.append(f"- asset_type: `{entry['asset_type']}`")
        if entry.get("execution_lane"):
            lines.append(f"- execution_lane: `{entry['execution_lane']}`")
        if entry.get("reference_count") is not None:
            lines.append(f"- reference_count: `{entry['reference_count']}`")
        if entry.get("review_status"):
            lines.append(f"- review_status: `{entry['review_status']}`")
        if entry.get("creation_status"):
            lines.append(f"- creation_status: `{entry['creation_status']}`")
        if "bootstrap_allowed" in entry:
            lines.append(f"- bootstrap_allowed: `{str(bool(entry['bootstrap_allowed'])).lower()}`")
        if entry.get("bootstrap_reason"):
            lines.append(f"- bootstrap_reason: `{entry['bootstrap_reason']}`")
        if entry.get("authoring_role"):
            lines.append(f"- authoring_role: `{entry['authoring_role']}`")
        if entry.get("authoring_note"):
            lines.append(f"- authoring_note: {entry['authoring_note']}")
        api_prompt_payload = entry.get("api_prompt_payload") if isinstance(entry.get("api_prompt_payload"), dict) else {}
        if api_prompt_payload.get("policy_version"):
            lines.append(f"- prompt_policy_version: `{api_prompt_payload['policy_version']}`")
        if api_prompt_payload.get("compiler_version"):
            lines.append(f"- compiler_version: `{api_prompt_payload['compiler_version']}`")
        if api_prompt_payload.get("source_digest"):
            lines.append(f"- source_digest: `{api_prompt_payload['source_digest']}`")
        if api_prompt_payload.get("sha256"):
            lines.append(f"- prompt_sha256: `{api_prompt_payload['sha256']}`")
        if api_prompt_payload.get("policy_version") == VIDEO_API_PROMPT_POLICY_VERSION:
            negative_prompt = str(api_prompt_payload.get("negative_prompt") or "")
            lines.append(
                f"- negative_prompt_sha256: `{hashlib.sha256(negative_prompt.encode('utf-8')).hexdigest()}`"
            )
            lines.append(
                f"- references_digest: `{sha256_canonical_json(list(entry.get('references') or []))}`"
            )
        lines.append(f"- output: `{entry['output']}`")
        if entry.get("duration_seconds") is not None:
            lines.append(f"- duration_seconds: `{entry['duration_seconds']}`")
        if entry.get("aspect_ratio"):
            lines.append(f"- aspect_ratio: `{entry['aspect_ratio']}`")
        quality = entry.get("quality") or (
            entry.get("resolution")
            if api_prompt_payload.get("policy_version")
            == VIDEO_API_PROMPT_POLICY_VERSION
            else ""
        )
        if quality:
            lines.append(f"- quality: `{quality}`")
        if entry.get("resolution"):
            lines.append(f"- resolution: `{entry['resolution']}`")
        if entry.get("first_frame"):
            lines.append(f"- first_frame: `{entry['first_frame']}`")
        if entry.get("last_frame"):
            lines.append(f"- last_frame: `{entry['last_frame']}`")
        source_cuts = entry.get("source_cuts") or []
        if source_cuts:
            lines.append("- source_cuts:")
            for source_cut in source_cuts:
                lines.append(f"  - `{source_cut}`")
        source_script_selectors = entry.get("source_script_selectors") or []
        if source_script_selectors:
            lines.append("- source_script_selectors:")
            for selector in source_script_selectors:
                lines.append(f"  - `{selector}`")
        required_views = entry.get("required_views") or []
        if required_views:
            lines.append("- required_views:")
            for view in required_views:
                lines.append(f"  - `{view}`")
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
        first_frame_visual_plan = entry.get("first_frame_visual_plan")
        debug_prompt_source = entry.get("debug_prompt_source") if isinstance(entry.get("debug_prompt_source"), dict) else {}
        if isinstance(first_frame_visual_plan, dict) and first_frame_visual_plan and not debug_prompt_source:
            debug_prompt_source = {"first_frame_visual_plan": first_frame_visual_plan, "send_to_api": False}
        if debug_prompt_source:
            lines.append("")
            lines.append("```debug_prompt_source")
            if yaml is not None:
                lines.append(
                    yaml.safe_dump(
                        debug_prompt_source,
                        allow_unicode=True,
                        sort_keys=False,
                    ).rstrip()
                )
            else:
                lines.append(json.dumps(debug_prompt_source, ensure_ascii=False, indent=2))
            lines.append("```")
        lines.append("")
        if api_prompt_payload.get("prompt"):
            prompt_fence = (
                "video_prompt"
                if api_prompt_payload.get("policy_version")
                == VIDEO_API_PROMPT_POLICY_VERSION
                else "api_prompt"
            )
            lines.append(f"```{prompt_fence}")
            lines.append(str(api_prompt_payload.get("prompt") or "").rstrip())
            lines.append("```")
            if api_prompt_payload.get("policy_version") == VIDEO_API_PROMPT_POLICY_VERSION:
                lines.extend(
                    [
                        "",
                        "```negative_prompt",
                        str(api_prompt_payload.get("negative_prompt") or "").rstrip(),
                        "```",
                    ]
                )
        else:
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
    rendered = "\n".join(lines)
    if merge_existing_sections and out_path.is_file():
        rendered = _merge_video_request_preview_sections(
            out_path.read_text(encoding="utf-8"),
            rendered,
            drop_existing_sections=dropped_sections,
        )
    out_path.write_text(rendered, encoding="utf-8")


def _split_video_request_sections(
    text: str,
) -> tuple[list[str], list[tuple[str, list[str]]]]:
    prefix: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_title is not None:
                sections.append((current_title, current_lines))
            current_title = line[3:].strip()
            current_lines = [line]
            continue
        if current_title is None:
            prefix.append(line)
        else:
            current_lines.append(line)
    if current_title is not None:
        sections.append((current_title, current_lines))
    return prefix, sections


def _merge_video_request_preview_sections(
    existing_text: str,
    new_text: str,
    *,
    drop_existing_sections: Iterable[str] = (),
) -> str:
    existing_prefix, existing_sections = _split_video_request_sections(existing_text)
    new_prefix, new_sections = _split_video_request_sections(new_text)
    dropped = {
        str(selector).strip()
        for selector in drop_existing_sections
        if str(selector).strip()
    }
    replacements = {title: "\n".join(lines).strip() for title, lines in new_sections}
    header = "\n".join(existing_prefix).strip() or "\n".join(new_prefix).strip()
    merged_sections: list[str] = []
    used: set[str] = set()
    for title, lines in existing_sections:
        if title in dropped:
            continue
        if title in replacements:
            merged_sections.append(replacements[title])
            used.add(title)
        else:
            merged_sections.append("\n".join(lines).strip())
    for title, _lines in new_sections:
        if title not in used:
            merged_sections.append(replacements[title])
            used.add(title)
    return "\n\n".join([header, *merged_sections]).rstrip() + "\n"


def _obsolete_video_request_selectors_for_selected_scenes(
    *,
    existing_text: str,
    targets: Iterable[VideoRenderTargetSpec],
    scene_filter: set[str] | None,
) -> set[str]:
    if scene_filter is None:
        return set()
    all_targets = list(targets)
    selected_scene_ids = {
        target.manifest_scene_id
        for target in all_targets
        if _video_target_matches_filter(target, scene_filter)
    }
    if not selected_scene_ids:
        return set()
    canonical_selectors = {
        target.selector
        for target in all_targets
        if target.manifest_scene_id in selected_scene_ids
    }
    _prefix, existing_sections = _split_video_request_sections(existing_text)
    obsolete: set[str] = set()
    for selector, _lines in existing_sections:
        belongs_to_selected_scene = any(
            selector == f"scene{scene_id}"
            or selector.startswith(f"scene{scene_id}_")
            for scene_id in selected_scene_ids
        )
        if belongs_to_selected_scene and selector not in canonical_selectors:
            obsolete.add(selector)
    return obsolete


def _validated_video_prompts_from_review_artifact(
    *,
    request_path: Path,
    entries: list[dict[str, Any]],
) -> dict[str, str]:
    """Return reviewed prompt bytes only when the current projection is identical."""

    if not entries:
        return {}
    if not request_path.is_file():
        raise SystemExit(
            "video generation request materialization is missing; rematerialize and review before generation"
        )
    text = request_path.read_text(encoding="utf-8")
    reviewed = _parse_video_request_artifact(text)
    state_path = request_path.parent / "state.txt"
    state = parse_state_file(state_path) if state_path.is_file() else {}
    prompts: dict[str, str] = {}
    for entry in entries:
        selector = str(entry.get("selector") or "").strip()
        materialized = reviewed.get(selector)
        if materialized is None:
            raise SystemExit(
                f"video generation request is stale or missing for {selector}; rematerialize and review"
            )
        payload = entry.get("api_prompt_payload") if isinstance(entry.get("api_prompt_payload"), dict) else {}
        current_prompt = str(payload.get("prompt") or "").strip()
        current_prompt_sha256 = hashlib.sha256(current_prompt.encode("utf-8")).hexdigest()
        expected = {
            "tool": str(entry.get("tool") or "").strip(),
            "output": str(entry.get("output") or "").strip(),
            "duration_seconds": str(entry.get("duration_seconds") or "").strip(),
            "aspect_ratio": str(entry.get("aspect_ratio") or "").strip(),
            "quality": str(
                entry.get("quality") or entry.get("resolution") or ""
            ).strip(),
            "resolution": str(entry.get("resolution") or "").strip(),
            "first_frame": str(entry.get("first_frame") or "").strip(),
            "last_frame": str(entry.get("last_frame") or "").strip(),
            "prompt_policy_version": str(payload.get("policy_version") or "").strip(),
            "compiler_version": str(payload.get("compiler_version") or "").strip(),
            "source_digest": str(payload.get("source_digest") or "").strip(),
            "prompt_sha256": current_prompt_sha256,
            "negative_prompt_sha256": hashlib.sha256(
                str(payload.get("negative_prompt") or "").encode("utf-8")
            ).hexdigest(),
            "references_digest": sha256_canonical_json(list(entry.get("references") or [])),
        }
        mismatches = [
            key
            for key, value in expected.items()
            if str(materialized.get(key) or "").strip() != value
        ]
        if str(payload.get("sha256") or "").strip() != current_prompt_sha256:
            mismatches.append("current_prompt_sha256")
        reviewed_prompt = str(materialized.get("prompt") or "").strip()
        reviewed_prompt_sha256 = hashlib.sha256(reviewed_prompt.encode("utf-8")).hexdigest()
        if reviewed_prompt_sha256 != str(materialized.get("prompt_sha256") or "").strip():
            mismatches.append("reviewed_prompt_sha256")
        if reviewed_prompt != current_prompt:
            mismatches.append("prompt")
        reviewed_negative_prompt = str(materialized.get("negative_prompt") or "").strip()
        current_negative_prompt = str(payload.get("negative_prompt") or "").strip()
        if reviewed_negative_prompt != current_negative_prompt:
            mismatches.append("negative_prompt")
        state_prefix = _video_prompt_approval_state_prefix(selector)
        approval_expected = {
            "status": "approved",
            "prompt_sha256": current_prompt_sha256,
            "source_digest": str(payload.get("source_digest") or "").strip(),
            "request_section_sha256": str(
                materialized.get("request_section_sha256") or ""
            ).strip(),
        }
        for field, expected_value in approval_expected.items():
            if state.get(f"{state_prefix}.{field}", "").strip() != expected_value:
                mismatches.append(f"approval_{field}")
        if mismatches:
            raise SystemExit(
                f"video generation request is stale for {selector} ({', '.join(dict.fromkeys(mismatches))}); "
                "rematerialize and review"
            )
        prompts[selector] = reviewed_prompt
    return prompts


def _parse_video_request_artifact(text: str) -> dict[str, dict[str, str]]:
    parsed: dict[str, dict[str, str]] = {}
    field_names = (
        "tool",
        "output",
        "duration_seconds",
        "aspect_ratio",
        "quality",
        "resolution",
        "first_frame",
        "last_frame",
        "prompt_policy_version",
        "compiler_version",
        "source_digest",
        "prompt_sha256",
        "negative_prompt_sha256",
        "references_digest",
    )
    _prefix, sections = _split_video_request_sections(text)
    for selector, section_lines in sections:
        if selector in parsed:
            raise SystemExit(f"video generation request has duplicate selector: {selector}")
        body = "\n".join(section_lines)
        values: dict[str, str] = {}
        for field in field_names:
            match = re.search(rf"(?m)^- {re.escape(field)}: `([^`]*)`\s*$", body)
            values[field] = match.group(1).strip() if match else ""
        prompt_match = re.search(
            r"(?ms)```(?:video_prompt|api_prompt)\s*\n(.*?)\n```",
            body,
        )
        values["prompt"] = prompt_match.group(1).strip() if prompt_match else ""
        negative_prompt_match = re.search(
            r"(?ms)```negative_prompt\s*\n(.*?)\n```",
            body,
        )
        values["negative_prompt"] = (
            negative_prompt_match.group(1).strip() if negative_prompt_match else ""
        )
        values["request_section_sha256"] = hashlib.sha256(
            body.encode("utf-8")
        ).hexdigest()
        parsed[selector] = values
    return parsed


def _video_prompt_approval_state_prefix(item_id: str) -> str:
    safe_item_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", item_id).strip("._-")
    return f"review.video_prompt.item.{safe_item_id or 'unknown'}"


def _video_prompt_pending_state_updates(
    *,
    request_path: Path,
    entries: list[dict[str, Any]],
) -> dict[str, str]:
    if not entries:
        return {}
    reviewed = _parse_video_request_artifact(request_path.read_text(encoding="utf-8"))
    updates: dict[str, str] = {}
    for entry in entries:
        selector = str(entry.get("selector") or "").strip()
        materialized = reviewed.get(selector)
        if materialized is None:
            raise SystemExit(
                f"video generation request is missing after materialization for {selector}"
            )
        payload = (
            entry.get("api_prompt_payload")
            if isinstance(entry.get("api_prompt_payload"), dict)
            else {}
        )
        prefix = _video_prompt_approval_state_prefix(selector)
        updates.update(
            {
                f"{prefix}.status": "pending",
                f"{prefix}.request_section_sha256": materialized[
                    "request_section_sha256"
                ],
                f"{prefix}.prompt_sha256": str(payload.get("sha256") or ""),
                f"{prefix}.source_digest": str(payload.get("source_digest") or ""),
                f"{prefix}.approved_by": "",
                f"{prefix}.approved_at": "",
            }
        )
    if entries:
        updates.update(
            {
                "review.video_prompt.status": "pending",
                "gate.video_prompt_review": "required",
            }
        )
    return updates


def _obsolete_video_prompt_state_updates(
    selectors: Iterable[str],
) -> dict[str, str]:
    obsolete_selectors = {
        str(selector).strip()
        for selector in selectors
        if str(selector).strip()
    }
    if not obsolete_selectors:
        return {}
    updates: dict[str, str] = {}
    for selector in sorted(obsolete_selectors):
        prefix = _video_prompt_approval_state_prefix(selector)
        updates.update(
            {
                f"{prefix}.status": "revoked",
                f"{prefix}.request_section_sha256": "",
                f"{prefix}.prompt_sha256": "",
                f"{prefix}.source_digest": "",
                f"{prefix}.approved_by": "",
                f"{prefix}.approved_at": "",
            }
        )
    updates.update(
        {
            "review.video_prompt.status": "pending",
            "gate.video_prompt_review": "required",
        }
    )
    return updates


def _manifest_video_generation_node(
    manifest: dict[str, Any],
    target: VideoRenderTargetSpec,
) -> dict[str, Any] | None:
    raw_scenes = manifest.get("scenes")
    if not isinstance(raw_scenes, list):
        return None
    for raw_scene in raw_scenes:
        if not isinstance(raw_scene, dict):
            continue
        if normalize_dotted_id(raw_scene.get("scene_id")) != target.manifest_scene_id:
            continue
        if target.unit_id is not None:
            for raw_unit in raw_scene.get("render_units") or []:
                if (
                    isinstance(raw_unit, dict)
                    and normalize_dotted_id(raw_unit.get("unit_id")) == target.unit_id
                ):
                    video_generation = raw_unit.get("video_generation")
                    if not isinstance(video_generation, dict):
                        video_generation = {}
                        raw_unit["video_generation"] = video_generation
                    return video_generation
            return None
        if target.source_cut_ids and isinstance(raw_scene.get("cuts"), list):
            cut_id = target.source_cut_ids[0]
            for raw_cut in raw_scene["cuts"]:
                if (
                    isinstance(raw_cut, dict)
                    and normalize_dotted_id(raw_cut.get("cut_id")) == cut_id
                ):
                    video_generation = raw_cut.get("video_generation")
                    if not isinstance(video_generation, dict):
                        video_generation = {}
                        raw_cut["video_generation"] = video_generation
                    return video_generation
            return None
        video_generation = raw_scene.get("video_generation")
        if not isinstance(video_generation, dict):
            video_generation = {}
            raw_scene["video_generation"] = video_generation
        return video_generation
    return None


def _write_manifest_yaml_atomic(
    *,
    manifest_path: Path,
    original_text: str,
    manifest: dict[str, Any],
) -> None:
    if yaml is None:  # pragma: no cover
        raise RuntimeError("PyYAML is required to persist video prompt payloads")
    rendered_yaml = yaml.safe_dump(
        manifest,
        allow_unicode=True,
        sort_keys=False,
    ).rstrip()
    fenced = re.search(r"(?ms)```yaml\s*\n(.*?)\n```", original_text)
    if fenced:
        updated_text = (
            original_text[: fenced.start(1)]
            + rendered_yaml
            + original_text[fenced.end(1) :]
        )
    else:
        updated_text = rendered_yaml + "\n"
    temp_path = manifest_path.with_name(
        f".{manifest_path.name}.tmp-{uuid.uuid4().hex}"
    )
    temp_path.write_text(updated_text, encoding="utf-8")
    temp_path.replace(manifest_path)


def _persist_video_materializations(
    *,
    manifest_path: Path,
    original_text: str,
    manifest: dict[str, Any],
    targets: Iterable[VideoRenderTargetSpec],
    entries: list[dict[str, Any]],
) -> None:
    targets_by_selector = {target.selector: target for target in targets}
    for entry in entries:
        selector = str(entry.get("selector") or "").strip()
        target = targets_by_selector.get(selector)
        if target is None:
            raise SystemExit(f"video render target missing while persisting {selector}")
        video_generation = _manifest_video_generation_node(manifest, target)
        if video_generation is None:
            raise SystemExit(f"manifest video_generation node missing for {selector}")
        video_generation.update(
            {
                "tool": str(entry.get("tool") or "").strip(),
                "output": str(entry.get("output") or "").strip(),
                "duration_seconds": int(entry.get("duration_seconds") or 0),
                "quality": str(
                    entry.get("quality") or entry.get("resolution") or ""
                ).strip(),
                "aspect_ratio": str(entry.get("aspect_ratio") or "").strip(),
                "first_frame": str(entry.get("first_frame") or "").strip(),
                "references": list(entry.get("references") or []),
                "api_prompt_payload": dict(entry.get("api_prompt_payload") or {}),
            }
        )
        last_frame = str(entry.get("last_frame") or "").strip()
        if last_frame:
            video_generation["last_frame"] = last_frame
        else:
            video_generation.pop("last_frame", None)
    if entries:
        _write_manifest_yaml_atomic(
            manifest_path=manifest_path,
            original_text=original_text,
            manifest=manifest,
        )


def _require_exact_persisted_video_payload(
    target: VideoRenderTargetSpec,
    current_payload: dict[str, Any],
) -> dict[str, Any]:
    stored_payload = dict(target.video_api_prompt_payload or {})
    if not stored_payload:
        raise SystemExit(
            f"video prompt payload is not persisted for {target.selector}; "
            "rematerialize and review"
        )
    if stored_payload != current_payload:
        changed = sorted(
            key
            for key in set(stored_payload) | set(current_payload)
            if stored_payload.get(key) != current_payload.get(key)
        )
        raise SystemExit(
            f"persisted video prompt payload is stale for {target.selector} "
            f"({', '.join(changed)}); rematerialize and review"
        )
    return stored_payload


def _blocking_video_prompt_quality_issue_codes(
    payload: dict[str, Any],
) -> list[str]:
    raw_ir = payload.get("video_prompt_ir")
    sources = [
        payload.get("quality_issues"),
        raw_ir.get("quality_issues") if isinstance(raw_ir, dict) else None,
    ]
    codes: list[str] = []
    for source in sources:
        for raw_issue in _list_value(source):
            if (
                not isinstance(raw_issue, dict)
                or raw_issue.get("blocking") is not True
            ):
                continue
            code = (
                str(raw_issue.get("code") or "").strip()
                or "video_motion_blocking_quality_issue"
            )
            if code and code not in codes:
                codes.append(code)
    return codes


def _assert_video_prompt_quality_allows_provider_execution(
    *,
    selector: str,
    payload: dict[str, Any],
) -> None:
    codes = _blocking_video_prompt_quality_issue_codes(payload)
    if codes:
        raise RuntimeError(
            f"video provider execution blocked for {selector}: "
            + ", ".join(codes)
        )


def _write_image_request_snapshot(
    *,
    run_dir: Path,
    request_path: Path,
    entries: list[dict[str, Any]],
    kind: str,
) -> Path | None:
    snapshot_filename = (
        "asset_generation_request_snapshot.json"
        if kind == "asset"
        else "image_generation_request_snapshot.json"
    )
    snapshot_path = run_dir / snapshot_filename
    if not entries:
        snapshot_path.unlink(missing_ok=True)
        return None
    snapshot_items: list[dict[str, Any]] = []
    for entry in entries:
        payload = entry.get("api_prompt_payload") if isinstance(entry.get("api_prompt_payload"), dict) else {}
        prompt = str(payload.get("prompt") or "").strip()
        if not prompt:
            prompt = _rewrite_request_prompt_for_review(
                prompt=str(entry.get("prompt") or ""),
                output=str(entry.get("output") or ""),
                references=list(entry.get("references") or []),
            ).strip()
        compiler_version = str(
            payload.get("compiler_version")
            or payload.get("compiler")
            or "request_projection_compat_v1"
        ).strip()
        source_digest = str(payload.get("source_digest") or "").strip()
        if not source_digest:
            source_digest = sha256_canonical_json(
                {
                    "selector": str(entry.get("selector") or ""),
                    "asset_id": str(entry.get("asset_id") or ""),
                    "asset_type": str(entry.get("asset_type") or ""),
                    "first_frame_visual_plan": entry.get("first_frame_visual_plan") or {},
                    "prompt_sha256": str(payload.get("sha256") or ""),
                }
            )
        snapshot_items.append(
            {
                "item_id": str(entry.get("selector") or ""),
                "kind": kind,
                "destination": str(entry.get("output") or ""),
                "prompt": prompt,
                "prompt_sha256": str(payload.get("sha256") or ""),
                "prompt_policy_version": str(
                    payload.get("policy_version") or "markdown_prompt_compat_v1"
                ),
                "compiler_version": compiler_version,
                "source_digest": source_digest,
                "references": list(entry.get("references") or []),
            }
        )
    snapshot = materialize_request_snapshot(
        run_dir,
        kind=kind,
        items=snapshot_items,
        source_artifact=request_path.relative_to(run_dir).as_posix(),
        defer_missing_references=True,
    )
    return write_request_snapshot_atomic(snapshot_path, snapshot, run_dir=run_dir)


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


def _strip_nonvisual_story_context(text: str) -> str:
    stripped = text
    stripped = re.sub(
        r"(?ms)\n?\[物語の文脈\]\n(?:この画像は物語「[^」]+」(?:の一場面(?:を視覚化する)?|に出てくる場所を表す)。\n*)+",
        "\n",
        stripped,
    )
    stripped = re.sub(
        r"この画像は物語「[^」]+」(?:の一場面(?:を視覚化する)?|に出てくる場所を表す)。\s*",
        "",
        stripped,
    )
    stripped = re.sub(
        r"物語「[^」]+」の\s*scene\d+(?:[_\s-]*cut\d+)?[。.\s]*",
        "",
        stripped,
        flags=re.I,
    )
    stripped = re.sub(
        r"(?<![A-Za-z0-9_/.-])scene\d+(?:[_-]cut\d+)?\s*の\s*",
        "",
        stripped,
        flags=re.I,
    )
    stripped = re.sub(
        r"(?<![A-Za-z0-9_/.-])scene\d+(?:[_-]cut\d+)?[、。.\s]*",
        "",
        stripped,
        flags=re.I,
    )
    stripped = re.sub(r"物語「[^」]+」に出てくる([^。\n]+)", r"\1", stripped)
    stripped = stripped.replace("[物語の文脈]\n", "")
    stripped = re.sub(r"(?:この画像は)?(?:動画(?:の)?(?:開始|冒頭)?)?最初の\s*1\s*フレーム(?:として|。|、)?\s*", "", stripped)
    stripped = re.sub(r"(?:この画像は)?(?:動画(?:の)?(?:開始|冒頭)?)?1\s*フレーム目(?:として|。|、)?\s*", "", stripped)
    stripped = re.sub(r"(?:この画像は)?(?:動画(?:の)?(?:開始|冒頭)?)?冒頭フレーム(?:として|。|、)?\s*", "", stripped)
    return stripped


def _rewrite_request_prompt_for_review(*, prompt: str, output: str, references: list[str], topic: str = "") -> str:
    text = (prompt or "").strip()
    if not text:
        return ""

    has_refs = bool(references)
    output_norm = (output or "").replace("\\", "/")
    is_character_asset = "/assets/characters/" in f"/{output_norm}"
    is_object_asset = "/assets/objects/" in f"/{output_norm}"
    labeled_refs = _label_reference_paths(list(references))
    path_to_label = {item["path"]: item["label"] for item in labeled_refs}

    text = _strip_nonvisual_story_context(text)
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
        "--ignore-duration-fit-gate",
        action="store_true",
        help="Allow video generation even if review.duration_fit.status=changes_requested.",
    )
    parser.add_argument(
        "--ignore-p400-readiness-gate",
        action="store_true",
        help="Allow read-only dry-run diagnostics even if eval.p400_readiness.status is not approved.",
    )
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
    parser.add_argument(
        "--audio-max-concurrency",
        type=int,
        default=3,
        help="Maximum number of audio generation tasks to run in parallel (capped at 12).",
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
        help=(
            "Deprecated and unsupported: dynamic chain frames cannot be added after "
            "video prompt approval. Materialize and approve the next target only after "
            "its boundary frame exists."
        ),
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
    parser.add_argument("--elevenlabs-model-id", default=_env("ELEVENLABS_MODEL_ID", "eleven_v3"))
    parser.add_argument("--elevenlabs-output-format", default=_env("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128"))
    parser.add_argument("--elevenlabs-language-code", default=_env("ELEVENLABS_LANGUAGE_CODE", DEFAULT_ELEVENLABS_LANGUAGE_CODE))
    parser.add_argument(
        "--elevenlabs-pronunciation-dictionary-locator",
        action="append",
        default=None,
        help="ElevenLabs pronunciation dictionary locator as id:version_id. Can be repeated.",
    )
    parser.add_argument(
        "--tts-pronunciation-alias-file",
        default=_env(
            "TOC_TTS_PRONUNCIATION_ALIAS_FILE",
            str(REPO_ROOT / "config" / "tts-pronunciation-aliases.tsv"),
        ),
        help="Optional local JSON/TSV alias file applied to ElevenLabs TTS text before API requests.",
    )
    parser.add_argument("--tts-prompt-prefix", default="", help="Optional text prepended to every TTS input.")
    parser.add_argument("--tts-prompt-suffix", default="", help="Optional text appended to every TTS input.")
    parser.add_argument("--macos-say-voice", default=_env("MACOS_SAY_VOICE", ""), help="Voice name for macos_say TTS (macOS only).")
    parser.add_argument(
        "--override-narration-tool",
        default="",
        help='Force narration tool for all scenes (e.g. "macos_say") for testing/ops. Empty = use manifest value.',
    )

    args = parser.parse_args()
    if args.chain_first_frame_from_prev_video:
        raise SystemExit(
            "--chain-first-frame-from-prev-video is deprecated and unsupported because "
            "a post-review dynamic frame cannot match the approved provider request. "
            "Generate the boundary frame first, then rematerialize and approve the next "
            "video target before execution."
        )
    if not args.elevenlabs_language_code:
        args.elevenlabs_language_code = DEFAULT_ELEVENLABS_LANGUAGE_CODE
    args.elevenlabs_pronunciation_dictionary_locators = parse_pronunciation_dictionary_locators(
        args.elevenlabs_pronunciation_dictionary_locator or _env("ELEVENLABS_PRONUNCIATION_DICTIONARY_LOCATORS")
    )
    args.tts_pronunciation_aliases = load_pronunciation_aliases(args.tts_pronunciation_alias_file)
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
    state_path = base_dir / "state.txt"
    md = manifest_path.read_text(encoding="utf-8")
    yaml_text = extract_yaml_block(md)
    manifest_data = yaml.safe_load(yaml_text) if yaml is not None else {}
    if not isinstance(manifest_data, dict):
        manifest_data = {}
    manifest_phase = str(manifest_data.get("manifest_phase") or "production").strip().lower() or "production"
    if manifest_phase not in {"skeleton", "production"}:
        raise SystemExit(f"Unsupported manifest_phase: {manifest_phase!r} (expected skeleton|production)")
    early_metadata = manifest_data.get("video_metadata") if isinstance(manifest_data.get("video_metadata"), dict) else {}
    early_experience = str(early_metadata.get("experience") or "").strip().lower()
    is_asset_stage_manifest = early_experience.startswith("asset_stage")
    canonical_manifest_path = (base_dir / "video_manifest.md").resolve()
    if manifest_path.resolve() != canonical_manifest_path and not is_asset_stage_manifest:
        raise SystemExit(
            "p400 readiness gate must evaluate the same manifest passed to generation.\n"
            f"  expected: {canonical_manifest_path}\n"
            f"  got: {manifest_path.resolve()}"
        )
    p400_override_is_read_only_diagnostic = bool(
        args.ignore_p400_readiness_gate
        and args.dry_run
        and args.skip_images
        and args.skip_videos
        and args.skip_audio
        and not args.materialize_request_files_only
    )
    if args.ignore_p400_readiness_gate and not p400_override_is_read_only_diagnostic:
        raise SystemExit(
            "--ignore-p400-readiness-gate is limited to read-only diagnostics: "
            "use it only with --dry-run --skip-images --skip-videos --skip-audio and without --materialize-request-files-only."
        )
    if not p400_override_is_read_only_diagnostic and not is_asset_stage_manifest:
        _stage_result, p400_updates = check_manifest_single(base_dir, "standard", "immersive")
        append_state_snapshot(state_path, p400_updates)
    if not p400_override_is_read_only_diagnostic and not is_asset_stage_manifest:
        state = parse_state_file(state_path) if state_path.exists() else {}
        if state.get("eval.p400_readiness.status", "").strip().lower() != "approved":
            raise SystemExit(
                "p400 readiness gate is not approved.\n"
                "  Run the p400 deterministic readiness review and resolve scene/cut/duration/review findings before p500+ generation,\n"
                "  or pass --ignore-p400-readiness-gate only with read-only dry-run diagnostic flags."
            )
    if args.skip_audio and not args.skip_videos and not args.ignore_duration_fit_gate and state_path.exists():
        state = parse_state_file(state_path)
        if state.get("review.duration_fit.status", "").strip().lower() == "changes_requested":
            raise SystemExit(
                "Audio duration gate is still requesting scene/narration expansion.\n"
                f"  Review prompts:\n"
                f"  - {base_dir / 'logs/review/duration_scene.subagent_prompt.md'}\n"
                f"  - {base_dir / 'logs/review/duration_narration.subagent_prompt.md'}\n"
                "  Resolve the duration-fit review before generating videos, or pass --ignore-duration-fit-gate."
            )
    allowed_image_plan_modes = _parse_csv_set(args.image_plan_modes)

    metadata, guides, scenes = parse_manifest_yaml_full(yaml_text)
    if not args.skip_audio and _manifest_has_revision_aware_narration(yaml_text):
        raise SystemExit(
            "Revision-aware narration audio cannot be generated directly from the manifest.\n"
            "  Use the frontend p730 candidate generation/playback/approval flow, then approve the full run at p750.\n"
            "  Re-run this command with --skip-audio to generate only the remaining assets."
        )
    aspect_ratio = (
        args.image_aspect_ratio
        or args.video_aspect_ratio
        or (metadata.get("aspect_ratio") if isinstance(metadata.get("aspect_ratio"), str) else None)
        or "9:16"
    )
    experience = str(metadata.get("experience") or "").strip().lower()
    image_request_filename = "asset_generation_requests.md" if experience.startswith("asset_stage") else "image_generation_requests.md"
    is_asset_stage_request = image_request_filename == "asset_generation_requests.md"
    production_stage_generation_requested = (
        (not args.skip_videos) or ((not args.skip_images) and not is_asset_stage_request)
    )
    if production_stage_generation_requested and manifest_phase != "production":
        raise SystemExit(
            "Manifest is still in skeleton phase.\n"
            "  Promote video_manifest.md to manifest_phase=production before generating scene images or videos."
        )
    if p400_override_is_read_only_diagnostic:
        print("[dry-run] p400 readiness override diagnostic only; no request files or assets were materialized.")
        return

    if not args.skip_images and not args.skip_image_prompt_review and manifest_phase == "production" and not is_asset_stage_request:
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
            str(REPO_ROOT / "scripts/run-p720-narration-l3.py"),
            "--run-dir",
            str(base_dir),
            "--manifest",
            str(manifest_path),
            "--script",
            str(base_dir / "script.md"),
            "--fail-on-findings",
        ]
        subprocess.run(review_cmd, check=True)
        semantic_review_cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts/run-p720-narration-semantic.py"),
            "--run-dir",
            str(base_dir),
            "--manifest",
            str(manifest_path),
            "--fail-on-findings",
        ]
        subprocess.run(semantic_review_cmd, check=True)
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
                        appearance_continuity=dict(
                            variant.appearance_continuity or {}
                        ),
                        notes=variant.notes,
                    )
                )
                expanded_cb.append(
                    CharacterBibleEntry(
                        character_id=entry.character_id,
                        reference_images=expanded,
                        reference_variants=expanded_variants,
                        fixed_prompts=list(entry.fixed_prompts or []),
                        appearance_continuity=dict(
                            entry.appearance_continuity or {}
                        ),
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
    video_render_targets = _build_video_render_targets(manifest=manifest_data, scenes=scenes)
    video_participating_selectors = {
        selector
        for target in video_render_targets
        for selector in target.source_selectors
        if selector
    }

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
        video_participating_selectors=video_participating_selectors,
    )

    log_dir = Path(args.log_dir) if args.log_dir else (base_dir / "logs/providers")

    def _scene_uses_tool(scene: Scene, tools: set[str]) -> bool:
        return normalize_tool_name(scene.image_tool) in tools

    needs_codex_image = (
        not args.skip_images
        and any(
            _scene_uses_tool(scene, {CODEX_BUILTIN_IMAGE_TOOL})
            and scene.image_output
            and scene.image_prompt
            and _scene_matches_filter(scene, scene_filter)
            for scene in scenes
        )
    )
    # External image providers are disabled; legacy tool aliases normalize to codex_builtin_image.
    needs_gemini_image = False
    needs_seadream_image = False
    needs_gemini_video = (
        not args.skip_videos
        and any(
            normalize_tool_name(target.video_tool) == "google_veo_3_1"
            and target.video_output
            and _video_target_matches_filter(target, scene_filter)
            for target in video_render_targets
        )
    )
    needs_kling_video = (
        not args.skip_videos
        and any(
            normalize_tool_name(target.video_tool) in {"kling_3_0", "kling", "kling_3_0_omni", "kling_omni", "kling-omni"}
            and target.video_output
            and _video_target_matches_filter(target, scene_filter)
            for target in video_render_targets
        )
    )
    needs_seedance_video = (
        not args.skip_videos
        and any(
            normalize_tool_name(target.video_tool)
            in {
                "seedance",
                "byteplus_seedance",
                "bytedance_seedance",
                "ark_seedance",
                "seadream_video",
                "seedream_video",
                "see_dream",
            }
            and target.video_output
            and _video_target_matches_filter(target, scene_filter)
            for target in video_render_targets
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
                    language_code=args.elevenlabs_language_code,
                    pronunciation_dictionary_locators=args.elevenlabs_pronunciation_dictionary_locators,
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
    written_request_paths: list[Path] = []
    if manifest_phase == "production" or is_asset_stage_request:
        include_image_source_requests = image_request_filename == "image_generation_requests.md"
        image_request_scenes: list[SceneSpec] = []
        for scene in scenes:
            if not _scene_matches_filter(scene, scene_filter):
                continue
            if _scene_is_deleted(scene):
                continue
            if not scene.image_output:
                continue
            if is_asset_stage_request and not scene.image_prompt:
                continue
            if not is_asset_stage_request and not _scene_has_compilable_image_prompt(scene):
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
            asset_stage_preview_metadata: dict[str, Any] = {}
            if is_asset_stage_request:
                primary_asset = _select_primary_still_asset(scene.still_assets)
                generation_plan = (
                    primary_asset.get("generation_plan")
                    if isinstance(primary_asset, dict) and isinstance(primary_asset.get("generation_plan"), dict)
                    else {}
                )
                if isinstance(primary_asset, dict):
                    asset_stage_preview_metadata = {
                        "creation_status": _as_opt_str(primary_asset.get("creation_status")) or "",
                        "bootstrap_allowed": bool(scene.image_bootstrap_allowed),
                        "bootstrap_reason": scene.image_bootstrap_reason or "",
                        "source_script_selectors": _ensure_str_list(primary_asset.get("source_script_selectors")),
                        "required_views": _ensure_str_list(generation_plan.get("required_views"))
                        or _ensure_str_list(primary_asset.get("required_views")),
                    }
            authoring_role = "reusable_asset_candidate" if is_asset_stage_request else "video_first_frame_candidate"
            authoring_note = (
                "このメタ情報はp550 reusable asset生成/レビュー用。prompt本文には物語タイトルやscene idを書かず、見える人物・場所・道具・行為だけを具体化する。"
                if is_asset_stage_request
                else "このメタ情報はプロンプト生成/レビュー用。prompt本文には「最初の1フレーム」等を書かず、見えている初期状態だけを具体化する。"
            )
            first_frame_visual_plan = {}
            api_prompt_payload = {}
            debug_prompt_source = {}
            if is_asset_stage_request:
                api_prompt_payload = _asset_image_api_prompt_payload_for_scene(
                    scene,
                    topic=str(metadata.get("topic") or ""),
                )
            else:
                first_frame_visual_plan = _build_first_frame_visual_plan(scene)
                api_prompt_payload = _image_api_prompt_payload_for_scene(
                    scene,
                    request_visual_beat=request_visual_beat,
                )
                debug_prompt_source = {
                    "first_frame_visual_plan": first_frame_visual_plan,
                    "api_prompt_payload": {
                        "policy_version": api_prompt_payload.get("policy_version", ""),
                        "sha256": api_prompt_payload.get("sha256", ""),
                    },
                    "send_to_api": False,
                }
            image_preview_entries.append(
                {
                    "selector": selector,
                    "tool": normalize_tool_name(scene.image_tool) or "",
                    "still_mode": scene.still_image_plan_mode or "",
                    "generation_status": _effective_still_generation_status(scene, base_dir=base_dir),
                    "plan_source": scene.still_image_plan_source or "",
                    "asset_id": scene.image_asset_id or "",
                    "asset_type": scene.image_asset_type or "",
                    "execution_lane": _effective_image_execution_lane(scene),
                    "reference_count": len(list(scene.image_references or [])),
                    "review_status": scene.image_review_status or "",
                    "authoring_role": authoring_role,
                    "authoring_note": authoring_note,
                    "output": str(out_path.relative_to(base_dir)) if out_path is not None else "",
                    "source_requests": source_requests,
                    "references": list(scene.image_references or []),
                    "first_frame_visual_plan": first_frame_visual_plan,
                    "debug_prompt_source": debug_prompt_source,
                    "api_prompt_payload": api_prompt_payload,
                    "prompt": scene.image_prompt
                    if is_asset_stage_request
                    else _compose_final_image_prompt(
                        scene,
                        prefix=image_prefix,
                        suffix=image_suffix,
                        request_visual_beat=request_visual_beat,
                    ),
                    **asset_stage_preview_metadata,
                }
            )
        image_request_path = base_dir / image_request_filename
        _write_request_preview_md(
            out_path=image_request_path,
            title="Asset Generation Requests" if image_request_filename == "asset_generation_requests.md" else "Image Generation Requests",
            entries=image_preview_entries,
            topic=str(metadata.get("topic") or ""),
        )
        snapshot_path = _write_image_request_snapshot(
            run_dir=base_dir,
            request_path=image_request_path,
            entries=image_preview_entries,
            kind="asset" if is_asset_stage_request else "scene",
        )
        written_request_paths.append(image_request_path)
        if snapshot_path is not None:
            written_request_paths.append(snapshot_path)

    reviewed_video_prompts: dict[str, str] = {}
    reviewed_video_negative_prompts: dict[str, str] = {}
    reviewed_video_payloads: dict[str, dict[str, Any]] = {}
    if manifest_phase == "production":
        video_targets_preview: list[VideoRenderTargetSpec] = []
        for target in video_render_targets:
            if not _video_target_matches_filter(target, scene_filter):
                continue
            if (
                args.skip_videos
                or not target.video_output
                or not _video_target_has_prompt_source(target)
            ):
                continue
            video_targets_preview.append(target)

        video_prefix = (args.video_prompt_prefix or "").strip()
        video_suffix = (args.video_prompt_suffix or "").strip()
        video_preview_entries: list[dict[str, Any]] = []
        for target_index, target in enumerate(video_targets_preview):
            out_path = _resolve_run_confined_video_path(
                base_dir=base_dir,
                maybe_path=target.video_output,
                selector=target.selector,
                role="video output",
            )
            first_frame, last_frame = _effective_video_target_frame_paths(
                base_dir,
                video_targets_preview,
                target_index,
                chain_first_frame_from_prev_video=bool(
                    args.chain_first_frame_from_prev_video
                ),
                enable_last_frame=bool(args.enable_last_frame),
            )
            duration_preview = (
                int(target.duration_seconds)
                if target.duration_seconds is not None
                else duration_from_timestamp_range(target.timestamp, args.default_scene_seconds)
            )
            effective_references = _effective_video_target_reference_strings(
                target,
                prefer_character_refstrips=bool(
                    args.video_reference_prefer_character_refstrips
                ),
                character_reference_strip_suffix=args.character_reference_strip_suffix,
            )
            source_requests: list[dict[str, str]] = []
            if target.video_applied_request_ids:
                source_requests = _resolve_source_requests(
                    request_ids=list(target.video_applied_request_ids),
                    request_lookup=human_change_request_lookup,
                    selector=target.selector,
                    section_name="video_generation.applied_request_ids",
                )
            first_frame_binding = _video_binding_path(base_dir, first_frame)
            last_frame_binding = _video_binding_path(base_dir, last_frame)
            effective_quality = target.video_quality or args.video_resolution
            effective_aspect_ratio = target.video_aspect_ratio or aspect_ratio
            execution_options = _video_execution_options(
                target=target,
                args=args,
                has_first_frame=first_frame is not None,
                has_reference_images=bool(effective_references),
                evolink_enabled=evolink_enabled,
                kling_extra_payload=kling_extra_payload,
                kling_omni_extra_payload=kling_omni_extra_payload,
                ark_extra_payload=ark_extra_payload,
            )
            _validate_effective_video_provider_capabilities(
                target=target,
                duration_seconds=duration_preview,
                has_first_frame=first_frame is not None,
                has_last_frame=last_frame is not None,
                reference_count=len(effective_references),
                execution_options=execution_options,
            )
            execution_options = _video_execution_options_with_reference_content(
                options=execution_options,
                base_dir=base_dir,
                bindings=[
                    first_frame_binding,
                    last_frame_binding,
                    *effective_references,
                ],
                stored_payload=target.video_api_prompt_payload,
                materializing=bool(args.materialize_request_files_only),
                selector=target.selector,
            )
            video_api_prompt_payload = _video_api_prompt_payload_for_target(
                target,
                prefix=video_prefix,
                suffix=video_suffix,
                first_frame_override=first_frame_binding,
                last_frame_override=last_frame_binding,
                duration_seconds_override=duration_preview,
                references_override=effective_references,
                quality=effective_quality,
                aspect_ratio=effective_aspect_ratio,
                execution_options=execution_options,
                additional_negative_prompt=args.video_negative_prompt or "",
            )
            if not args.materialize_request_files_only:
                _assert_video_prompt_quality_allows_provider_execution(
                    selector=str(target.selector),
                    payload=video_api_prompt_payload,
                )
                video_api_prompt_payload = _require_exact_persisted_video_payload(
                    target,
                    video_api_prompt_payload,
                )
                _assert_video_prompt_quality_allows_provider_execution(
                    selector=str(target.selector),
                    payload=video_api_prompt_payload,
                )
            video_preview_entries.append(
                {
                    "selector": target.selector,
                    "tool": normalize_tool_name(target.video_tool) or "",
                    "output": str(out_path.relative_to(base_dir)) if out_path is not None else "",
                    "duration_seconds": duration_preview,
                    "aspect_ratio": effective_aspect_ratio,
                    "quality": effective_quality,
                    "resolution": effective_quality,
                    "first_frame": first_frame_binding,
                    "last_frame": last_frame_binding,
                    "source_cuts": list(target.source_selectors),
                    "source_requests": source_requests,
                    "references": effective_references,
                    "prompt": str(video_api_prompt_payload.get("prompt") or ""),
                    "api_prompt_payload": video_api_prompt_payload,
                    "debug_prompt_source": {
                        "video_prompt_ir": video_api_prompt_payload.get("video_prompt_ir") or {},
                        "projection_review_contract": video_api_prompt_payload.get("projection_review_contract") or {},
                        "send_to_api": False,
                    },
                }
            )
        video_request_path = base_dir / "video_generation_requests.md"
        if args.materialize_request_files_only:
            obsolete_video_request_selectors: set[str] = set()
            if scene_filter is not None and video_request_path.is_file():
                obsolete_video_request_selectors = (
                    _obsolete_video_request_selectors_for_selected_scenes(
                        existing_text=video_request_path.read_text(encoding="utf-8"),
                        targets=video_render_targets,
                        scene_filter=scene_filter,
                    )
                )
            _persist_video_materializations(
                manifest_path=manifest_path,
                original_text=md,
                manifest=manifest_data,
                targets=video_render_targets,
                entries=video_preview_entries,
            )
            _write_request_preview_md(
                out_path=video_request_path,
                title="Video Generation Requests",
                entries=video_preview_entries,
                topic=str(metadata.get("topic") or ""),
                merge_existing_sections=bool(
                    args.skip_videos or scene_filter is not None
                ),
                drop_existing_sections=obsolete_video_request_selectors,
            )
            pending_updates = _obsolete_video_prompt_state_updates(
                obsolete_video_request_selectors
            )
            pending_updates.update(
                _video_prompt_pending_state_updates(
                    request_path=video_request_path,
                    entries=video_preview_entries,
                )
            )
            if pending_updates:
                append_state_snapshot(state_path, pending_updates)
        else:
            reviewed_video_prompts = _validated_video_prompts_from_review_artifact(
                request_path=video_request_path,
                entries=video_preview_entries,
            )
            reviewed_video_negative_prompts = {
                str(entry.get("selector") or ""): str(
                    (entry.get("api_prompt_payload") or {}).get("negative_prompt") or ""
                )
                for entry in video_preview_entries
            }
        _write_generation_exclusion_report_md(
            out_path=base_dir / "generation_exclusion_report.md",
            scenes=scenes,
        )
        written_request_paths.extend(
            [
                video_request_path,
                base_dir / "generation_exclusion_report.md",
            ]
        )

    if args.materialize_request_files_only:
        write_run_index(base_dir)
        for written_path in written_request_paths:
            print(f"[materialized] {written_path}")
        return

    image_max_concurrency = max(1, min(int(args.image_max_concurrency or 1), 10))
    if needs_codex_image:
        image_max_concurrency = min(
            image_max_concurrency,
            _direct_image_global_parallelism(),
        )
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

    # Pass 2: audio (TTS). The production order is images/assets -> narration -> videos.
    audio_scenes: list[SceneSpec] = []
    for scene in scenes:
        if not _scene_matches_filter(scene, scene_filter):
            continue
        if _scene_is_deleted(scene):
            continue
        if args.skip_audio or not scene.narration_output:
            continue
        audio_scenes.append(scene)

    audio_max_concurrency = max(1, min(int(args.audio_max_concurrency or 1), 12))
    _generate_audio_scenes_in_parallel(
        audio_scenes=audio_scenes,
        audio_max_concurrency=audio_max_concurrency,
        base_dir=base_dir,
        args=args,
        log_dir=log_dir,
        elevenlabs_client=elevenlabs_client,
    )

    # Pass 3: videos
    video_targets_in_order: list[VideoRenderTargetSpec] = []
    if manifest_phase == "production":
        for target in video_render_targets:
            if not _video_target_matches_filter(target, scene_filter):
                continue
            if (
                args.skip_videos
                or not target.video_output
                or not _video_target_has_prompt_source(target)
            ):
                continue
            video_targets_in_order.append(target)

        video_prefix = (args.video_prompt_prefix or "").strip()
        video_suffix = (args.video_prompt_suffix or "").strip()
        video_preview_entries: list[dict[str, Any]] = []
        for target_index, target in enumerate(video_targets_in_order):
            out_path = _resolve_run_confined_video_path(
                base_dir=base_dir,
                maybe_path=target.video_output,
                selector=target.selector,
                role="video output",
            )
            first_frame, last_frame = _effective_video_target_frame_paths(
                base_dir,
                video_targets_in_order,
                target_index,
                chain_first_frame_from_prev_video=bool(
                    args.chain_first_frame_from_prev_video
                ),
                enable_last_frame=bool(args.enable_last_frame),
            )
            duration_preview = (
                int(target.duration_seconds)
                if target.duration_seconds is not None
                else duration_from_timestamp_range(target.timestamp, args.default_scene_seconds)
            )
            effective_references = _effective_video_target_reference_strings(
                target,
                prefer_character_refstrips=bool(
                    args.video_reference_prefer_character_refstrips
                ),
                character_reference_strip_suffix=args.character_reference_strip_suffix,
            )
            source_requests: list[dict[str, str]] = []
            if target.video_applied_request_ids:
                source_requests = _resolve_source_requests(
                    request_ids=list(target.video_applied_request_ids),
                    request_lookup=human_change_request_lookup,
                    selector=target.selector,
                    section_name="video_generation.applied_request_ids",
                )
            first_frame_binding = _video_binding_path(base_dir, first_frame)
            last_frame_binding = _video_binding_path(base_dir, last_frame)
            effective_quality = target.video_quality or args.video_resolution
            effective_aspect_ratio = target.video_aspect_ratio or aspect_ratio
            execution_options = _video_execution_options(
                target=target,
                args=args,
                has_first_frame=first_frame is not None,
                has_reference_images=bool(effective_references),
                evolink_enabled=evolink_enabled,
                kling_extra_payload=kling_extra_payload,
                kling_omni_extra_payload=kling_omni_extra_payload,
                ark_extra_payload=ark_extra_payload,
            )
            _validate_effective_video_provider_capabilities(
                target=target,
                duration_seconds=duration_preview,
                has_first_frame=first_frame is not None,
                has_last_frame=last_frame is not None,
                reference_count=len(effective_references),
                execution_options=execution_options,
            )
            execution_options = _video_execution_options_with_reference_content(
                options=execution_options,
                base_dir=base_dir,
                bindings=[
                    first_frame_binding,
                    last_frame_binding,
                    *effective_references,
                ],
                stored_payload=target.video_api_prompt_payload,
                materializing=False,
                selector=target.selector,
            )
            video_api_prompt_payload = _video_api_prompt_payload_for_target(
                target,
                prefix=video_prefix,
                suffix=video_suffix,
                first_frame_override=first_frame_binding,
                last_frame_override=last_frame_binding,
                duration_seconds_override=duration_preview,
                references_override=effective_references,
                quality=effective_quality,
                aspect_ratio=effective_aspect_ratio,
                execution_options=execution_options,
                additional_negative_prompt=args.video_negative_prompt or "",
            )
            _assert_video_prompt_quality_allows_provider_execution(
                selector=str(target.selector),
                payload=video_api_prompt_payload,
            )
            video_api_prompt_payload = _require_exact_persisted_video_payload(
                target,
                video_api_prompt_payload,
            )
            _assert_video_prompt_quality_allows_provider_execution(
                selector=str(target.selector),
                payload=video_api_prompt_payload,
            )
            reviewed_video_payloads[str(target.selector)] = video_api_prompt_payload
            video_preview_entries.append(
                {
                    "selector": target.selector,
                    "tool": normalize_tool_name(target.video_tool) or "",
                    "output": str(out_path.relative_to(base_dir)) if out_path is not None else "",
                    "duration_seconds": duration_preview,
                    "aspect_ratio": effective_aspect_ratio,
                    "quality": effective_quality,
                    "resolution": effective_quality,
                    "first_frame": first_frame_binding,
                    "last_frame": last_frame_binding,
                    "source_cuts": list(target.source_selectors),
                    "source_requests": source_requests,
                    "references": effective_references,
                    "prompt": str(video_api_prompt_payload.get("prompt") or ""),
                    "api_prompt_payload": video_api_prompt_payload,
                    "debug_prompt_source": {
                        "video_prompt_ir": video_api_prompt_payload.get("video_prompt_ir") or {},
                        "projection_review_contract": video_api_prompt_payload.get("projection_review_contract") or {},
                        "send_to_api": False,
                    },
                }
            )
        reviewed_video_prompts = _validated_video_prompts_from_review_artifact(
            request_path=base_dir / "video_generation_requests.md",
            entries=video_preview_entries,
        )
        reviewed_video_negative_prompts = {
            str(entry.get("selector") or ""): str(
                (entry.get("api_prompt_payload") or {}).get("negative_prompt") or ""
            )
            for entry in video_preview_entries
        }

    for target_index, target in enumerate(video_targets_in_order):
        if (
            args.skip_videos
            or not target.video_output
            or not _video_target_has_prompt_source(target)
        ):
            continue

        tool = normalize_tool_name(target.video_tool)
        out_path = _resolve_run_confined_video_path(
            base_dir=base_dir,
            maybe_path=target.video_output,
            selector=target.selector,
            role="video output",
        )
        if not out_path:
            raise SystemExit(f"{target.selector}: missing video output path")

        dur = int(target.duration_seconds) if target.duration_seconds is not None else duration_from_timestamp_range(target.timestamp, args.default_scene_seconds)

        input_image, last_image = _effective_video_target_frame_paths(
            base_dir,
            video_targets_in_order,
            target_index,
            chain_first_frame_from_prev_video=bool(
                args.chain_first_frame_from_prev_video
            ),
            enable_last_frame=bool(args.enable_last_frame),
        )
        if input_image and not args.dry_run and not input_image.exists():
            raise SystemExit(f"{target.selector}: first frame image not found: {input_image}")
        if last_image and not args.dry_run and not last_image.exists():
            raise SystemExit(f"{target.selector}: last frame image not found: {last_image}")

        prompt = reviewed_video_prompts.get(str(target.selector), "")
        if not prompt:
            raise SystemExit(
                f"video generation request is missing for {target.selector}; rematerialize and review"
            )
        negative_prompt = reviewed_video_negative_prompts.get(str(target.selector), "")
        if args.log_prompts:
            log_dir.mkdir(parents=True, exist_ok=True)
            (log_dir / f"{_video_target_log_slug(target)}_video_prompt.txt").write_text(prompt + "\n", encoding="utf-8")

        video_ref_paths: list[Path] = []
        for ref_str in _effective_video_target_reference_strings(
            target,
            prefer_character_refstrips=bool(
                args.video_reference_prefer_character_refstrips
            ),
            character_reference_strip_suffix=args.character_reference_strip_suffix,
        ):
            ref_path = _resolve_run_confined_video_path(
                base_dir=base_dir,
                maybe_path=ref_str,
                selector=target.selector,
                role="reference image",
            )
            if not ref_path:
                continue
            if not args.dry_run and not ref_path.exists():
                raise SystemExit(f"{target.selector}: reference image not found: {ref_path}")
            video_ref_paths.append(ref_path)

        reviewed_payload = reviewed_video_payloads.get(str(target.selector))
        if reviewed_payload is None:
            raise SystemExit(
                f"video prompt payload is missing for {target.selector}; "
                "rematerialize and review"
            )
        _assert_video_prompt_quality_allows_provider_execution(
            selector=str(target.selector),
            payload=reviewed_payload,
        )
        snapshot_dir: Path | None = None
        provider_input_image = input_image
        provider_last_image = last_image
        provider_reference_images = video_ref_paths
        try:
            if not args.dry_run:
                (
                    snapshot_dir,
                    provider_input_image,
                    provider_last_image,
                    provider_reference_images,
                ) = _snapshot_reviewed_video_reference_inputs(
                    base_dir=base_dir,
                    selector=str(target.selector),
                    api_prompt_payload=reviewed_payload,
                    input_image=input_image,
                    last_frame_image=last_image,
                    reference_images=video_ref_paths,
                )
            _dispatch_reviewed_video_provider_call(
                selector=str(target.selector),
                tool=tool,
                api_prompt_payload=reviewed_payload,
                prompt=prompt,
                negative_prompt=negative_prompt,
                input_image=provider_input_image,
                last_frame_image=provider_last_image,
                reference_images=provider_reference_images,
                out_path=out_path,
                log_dir=log_dir,
                poll_every=float(args.poll_every),
                timeout_seconds=float(args.timeout_seconds),
                force=bool(args.force),
                dry_run=bool(args.dry_run),
                gemini_client=gemini_client,
                kling_client=kling_client,
                evolink_client=evolink_client,
                seedance_client=seedance_client,
            )
        finally:
            if snapshot_dir is not None:
                shutil.rmtree(snapshot_dir, ignore_errors=True)

        if (
            args.chain_first_frame_from_prev_video
            and target_index < len(video_targets_in_order) - 1
            and not args.dry_run
        ):
            chain_frame = out_path.with_name(out_path.stem + "_chain_first_frame.png")
            try:
                _ffmpeg_extract_frame_from_end_best_effort(
                    out_path,
                    chain_frame,
                    seconds_from_end=float(args.chain_first_frame_seconds_from_end),
                    force=True,
                )
            except FileNotFoundError as exc:
                raise SystemExit(
                    f"{target.selector}: could not extract the reviewed chained first frame"
                ) from exc

    write_run_index(base_dir)
    print("Done.")


if __name__ == "__main__":
    main()
