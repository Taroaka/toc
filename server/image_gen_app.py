from __future__ import annotations

import asyncio
from collections import Counter
from copy import deepcopy
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
import fcntl
import hashlib
import json
import math
import os
import re
import threading
import time
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit, urlunsplit

import yaml
try:
    from fastapi import APIRouter, HTTPException, Query
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
except ModuleNotFoundError:  # pragma: no cover - CLI-only environments may omit FastAPI.
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: Any = None) -> None:
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class _CliOnlyRouter:
        def get(self, *args: Any, **kwargs: Any) -> Any:
            def decorator(func: Any) -> Any:
                return func

            return decorator

        post = get

    def APIRouter(*args: Any, **kwargs: Any) -> _CliOnlyRouter:
        return _CliOnlyRouter()

    def Query(default: Any = None, **kwargs: Any) -> Any:
        return default

    class Response:  # noqa: D101
        pass

    class FileResponse(Response):  # noqa: D101
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class HTMLResponse(Response):  # noqa: D101
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class JSONResponse(Response):  # noqa: D101
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class StreamingResponse(Response):  # noqa: D101
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass
from pydantic import BaseModel, Field

from .codex_app_server import (
    CodexAppServerClient,
    CodexAppServerError,
    CodexAppServerTransportError,
    app_server_disabled,
    classify_codex_transport_error,
    create_codex_app_server_client,
    is_codex_transport_error,
    latest_generated_image_mtime_ns,
    reject_local_raster_image_result,
)
from toc.env import load_env_files
from toc.http import HttpError
from toc.asset_prompt_compiler import (
    ASSET_PROMPT_COMPILER_VERSION,
    ASSET_PROMPT_POLICY_VERSION,
    asset_prompt_source_digest,
    compile_asset_prompt,
)
from toc.image_prompt_compiler import compile_image_api_prompt_v2
from toc.video_prompt_compiler import (
    VIDEO_API_PROMPT_POLICY_VERSION,
    VIDEO_PROMPT_COMPILER_VERSION,
    VIDEO_PROMPT_IR_SCHEMA_VERSION,
    VIDEO_REFERENCE_ROLE_INSTRUCTIONS,
    compile_video_api_prompt_v1,
    compose_video_render_unit_contract,
)
from toc.video_prompt_projection_registry import (
    VIDEO_PROMPT_PROJECTION_REGISTRY_VERSION,
    resolve_video_prompt_contract,
)
from toc.video_provider_capabilities import resolve_video_provider_capabilities
from toc.image_request_snapshot import (
    ImageRequestSnapshotError,
    bind_request_snapshot_references,
    current_reference_sha256s,
    load_request_snapshot,
    materialize_request_snapshot,
    sha256_canonical_json,
    write_request_snapshot_atomic,
)
from toc.immersive_manifest import (
    is_non_renderable_manifest_node,
    make_scene_cut_selector,
    normalize_dotted_id,
    selector_aliases,
)
from toc.harness import append_state_snapshot, load_structured_document, now_iso, parse_state_file
from toc import process_store
from toc.providers.kling import KlingClient, KlingConfig
from toc.providers.seedance import SeedanceClient, SeedanceConfig
from toc.script_narration import materialize_elevenlabs_tts_text, resolve_script_cut_tts_text
from toc.narration_revision import (
    REVISION_SCHEMA_VERSION,
    NarrationRevisionConflict,
    apply_authoring_update,
    approve_audio_candidate,
    current_audio_is_human_approved,
    ensure_narration_revision,
    narration_text_hash,
    narration_tts_hash,
    prepare_audio_candidate,
    record_audio_candidate_result,
)
from toc.narration_arc import narration_text_set_hash
from toc.narration_review_gate import deterministic_narration_review_blockers
from toc.narration_semantic_review import (
    build_narration_semantic_review_pack,
    narration_semantic_review_is_current,
    run_narration_semantic_critics,
    validate_narration_semantic_aggregate,
)
from toc.narration_continuity import (
    invalidate_stale_tts_context_audio,
    narration_span_refs,
    reconcile_audio_story_text,
    tts_continuity_contexts,
)
from toc.story_duration import audit_duration, measure_manifest_runtime, normalize_target_duration
from toc.runtime_locks import (
    FileLockLease,
    FileLockUnavailable,
    acquire_file_lock,
    async_file_slot,
    release_file_lock,
)
from toc.semantic_review import (
    IMAGE_PROMPT_JUDGMENT_REPORT,
    SemanticReviewStatus,
    check_semantic_review,
    check_image_prompt_judgment,
    parse_judgment_report_status,
    review_status_to_state,
    semantic_state_updates,
    semantic_review_relpaths,
)
from toc.semantic_review_loop import (
    SEMANTIC_REVIEW_PRODUCER_TARGETS,
    semantic_loop_state_updates,
    scene_detail_review_concurrency,
    scene_detail_transport_retry_attempts,
    semantic_repair_state_updates,
    semantic_repair_relpaths,
    semantic_repair_timeout_seconds,
    semantic_review_max_attempts,
    semantic_review_timeout_seconds,
    write_semantic_repair_prompt,
)
from toc.tts_text import load_pronunciation_aliases, prepare_elevenlabs_tts_text
from .image_gen import (
    IMAGE_API_PROMPT_POLICY_VERSION,
    IMAGE_API_PROMPT_POLICY_PREFIX,
    IMAGE_SUFFIXES,
    build_zip,
    candidate_path,
    copy_saved_image,
    copy_saved_image_to_new_candidate,
    insert_candidate,
    item_to_api,
    list_reference_options,
    list_candidate_items,
    list_first_image_retentions,
    list_runs,
    load_request_items,
    output_root,
    prompt_setting_targets,
    reference_to_api,
    reserve_run_dir,
    require_image_file,
    require_candidate_path,
    read_prompt_setting,
    read_run_progress,
    rehydrate_retained_first_image,
    repo_root,
    restore_first_image_retention_run,
    retain_first_image,
    resolve_run_relative,
    safe_run_dir,
    is_first_image_retention_restored_run,
    target_matches_item,
    target_to_request_kind,
    update_request_prompts,
    validate_image_bytes,
    write_app_server_debug_log,
    write_app_server_image_debug_log,
    write_prompt_setting,
)


ROOT = repo_root()
APP_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "server" / "web"
DIST_DIR = WEB_DIR / "dist"

router = APIRouter()
PLACEHOLDER_MARKERS = (
    "placeholder",
    "scaffold placeholder",
    "replace_me",
    "todo",
    "TODO",
    "TBD",
)
P650_FIXED_SLOTS = (
    "p110",
    "p120",
    "p130",
    "p210",
    "p220",
    "p230",
    "p310",
    "p320",
    "p330",
    "p410",
    "p420",
    "p430",
    "p440",
    "p450",
    "p510",
    "p520",
    "p530",
    "p540",
    "p550",
    "p560",
    "p570",
    "p610",
    "p620",
    "p630",
    "p640",
    "p650",
)
P680_FIXED_SLOTS = (*P650_FIXED_SLOTS, "p660", "p670", "p680")
CREATE_MODE_NORMAL = "normal"
CREATE_MODE_SCENE_STORYBOARD = "scene_storyboard"
CREATE_MODE_SCENE_STORYBOARD_RUN_SUFFIX = "storyboard"
CREATE_STOP_TARGETS = {"p650", "p680"}
VIDEO_GENERATION_DURATION_MAX_SECONDS = 60
BOOTSTRAP_ASSET_MAX_ATTEMPTS = 10
# Request-bound provenance is the canonical production image-generation route.
# The generated_images time-order fallback remains only as an explicit legacy
# recovery mode because it cannot prove which request produced a file.
IMAGE_GENERATION_PARALLELISM = max(1, int(os.environ.get("TOC_IMAGE_GEN_PARALLELISM", "6") or "6"))
IMAGE_GENERATION_GLOBAL_PARALLELISM = max(
    1,
    int(os.environ.get("TOC_IMAGE_GEN_GLOBAL_PARALLELISM", str(IMAGE_GENERATION_PARALLELISM)) or IMAGE_GENERATION_PARALLELISM),
)
IMAGE_GENERATION_PROVENANCE_POLICY_SERIAL_FALLBACK = "serial_fallback"
IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2 = "request_bound_v2"
IMAGE_GENERATION_ITEM_MAX_ATTEMPTS = max(1, int(os.environ.get("TOC_IMAGE_GEN_ITEM_MAX_ATTEMPTS", "3") or "3"))
IMAGE_GENERATION_ITEM_TIMEOUT_SECONDS = max(
    1.0,
    float(os.environ.get("TOC_IMAGE_GEN_ITEM_TIMEOUT_SECONDS", "900") or "900"),
)
IMAGE_GENERATION_QUEUE_TIMEOUT_SECONDS = max(
    1.0,
    float(os.environ.get("TOC_IMAGE_GEN_QUEUE_TIMEOUT_SECONDS", "7200") or "7200"),
)
FRONTEND_CREATE_HELPER_TIMEOUT_SECONDS = max(
    1.0,
    float(os.environ.get("TOC_FRONTEND_CREATE_HELPER_TIMEOUT_SECONDS", "28800") or "28800"),
)
CODEX_APP_SERVER_START_TIMEOUT_SECONDS = max(
    1.0,
    float(os.environ.get("TOC_CODEX_APP_SERVER_START_TIMEOUT_SECONDS", "180") or "180"),
)
PROMPT_REPAIR_TIMEOUT_SECONDS = max(1.0, float(os.environ.get("TOC_PROMPT_REPAIR_TIMEOUT_SECONDS", "120") or "120"))
CREATE_SKILL_STOP_POLL_SECONDS = max(1.0, float(os.environ.get("TOC_CREATE_SKILL_STOP_POLL_SECONDS", "10") or "10"))
CREATE_SKILL_CANCEL_TIMEOUT_SECONDS = max(1.0, float(os.environ.get("TOC_CREATE_SKILL_CANCEL_TIMEOUT_SECONDS", "10") or "10"))
SLOT_TERMINAL_STATES = {"done", "skipped", "awaiting_approval"}
SLOT_AWAITING_APPROVAL_ALLOWED = {
    "p130",
    "p230",
    "p320",
    "p330",
    "p430",
    "p540",
    "p570",
    "p630",
    "p640",
    "p680",
}

TRANSIENT_CODEX_IMAGE_ERRORS = (
    "stream disconnected",
    "backend-api/codex/responses",
    "connection reset",
    "timed out during turn/start",
    "turn timed out",
)


def _codex_failure_context(exc: Exception, *, client: CodexAppServerClient | None = None) -> dict[str, Any]:
    context: dict[str, Any] = {
        "errorType": type(exc).__name__,
        "errorMessage": str(exc),
    }
    transcript = getattr(exc, "transcript", None)
    if isinstance(transcript, list):
        context["transcriptTail"] = transcript[-20:]
        context["transcriptCount"] = len(transcript)
    diagnostics = getattr(exc, "diagnostics", None)
    if isinstance(diagnostics, dict) and diagnostics:
        context["codexDiagnostics"] = diagnostics
    elif client is not None and hasattr(client, "diagnostics"):
        try:
            context["codexDiagnostics"] = client.diagnostics()
        except Exception as diagnostics_exc:
            context["codexDiagnosticsError"] = str(diagnostics_exc)
    transport_kind = classify_codex_transport_error(str(exc))
    if transport_kind:
        context["transportErrorKind"] = transport_kind
    if is_codex_transport_error(exc):
        context["probableCause"] = "Codex app-server turn failed while calling chatgpt.com backend-api/codex/responses; likely external app-server/network/backend stream interruption rather than ToC artifact validation."
    return context


def _continue_generation_after_item_error(kind: str) -> bool:
    configured = os.environ.get("TOC_IMAGE_GEN_CONTINUE_ON_ITEM_ERROR", "").strip().lower()
    if configured in {"1", "true", "yes", "on"}:
        return True
    if configured in {"0", "false", "no", "off"}:
        return False
    return kind == "scene"


class GenerateRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(asset|scene)$")
    item_id: str = Field(min_length=1, max_length=200)
    prompt: str = Field(max_length=20000)
    prompt_policy_version: str | None = Field(default=None, max_length=100)
    debug_prompt_source: dict[str, Any] = Field(default_factory=dict)
    references: list[str] = Field(default_factory=list, max_length=16)
    candidate_count: int = Field(default=1, ge=1, le=16)


class BulkGenerateRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(asset|scene)$")
    items: list[GenerateRequest] = Field(min_length=1, max_length=100)
    concurrency: int = Field(default=IMAGE_GENERATION_PARALLELISM, ge=1, le=100)
    background: bool = False


@dataclass(frozen=True)
class _BulkGenerationPlanItem:
    id: str
    output: str
    references: list[str]
    dependency_references: list[str]
    request: GenerateRequest


class InsertItem(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    candidate_path: str = Field(min_length=1, max_length=500)
    output: str = Field(min_length=1, max_length=500)


class BulkInsertRequest(BaseModel):
    items: list[InsertItem] = Field(min_length=1, max_length=64)


class ZipRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    paths: list[str] = Field(default_factory=list, max_length=128)


class ChatTurnRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    run_id: str | None = None
    session_id: str = Field(default="default", min_length=1, max_length=100)


class PromptSettingRequest(BaseModel):
    target: str = Field(pattern="^(character|item|location|scene)$")
    content: str = Field(min_length=1, max_length=40000)


class RegeneratePromptsRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    target: str = Field(pattern="^(character|item|location|scene)$")
    instruction: str = Field(min_length=1, max_length=40000)
    item_ids: list[str] = Field(default_factory=list, max_length=64)
    concurrency: int = Field(default=4, ge=1, le=8)


class CreateRunRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    source: str | None = Field(default=None, max_length=4000)
    generate_images: bool = True
    stop_target: str = Field(default="p680", pattern="^(p650|p680)$")
    target_duration_seconds: int = Field(default=300, ge=300, le=1200, strict=True)


class CreateStoryboardRunRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    source: str | None = Field(default=None, max_length=4000)
    stop_target: str = Field(default="p680", pattern="^(p650|p680)$")
    target_duration_seconds: int = Field(default=300, ge=300, le=1200, strict=True)


class ResumeRunRequest(BaseModel):
    stop_target: str = Field(default="p680", pattern="^(p680)$")


class FrontendReviewItem(BaseModel):
    item_id: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(asset|scene)$")
    output: str | None = Field(default=None, max_length=500)
    prompt: str = Field(default="", max_length=40000)
    references: list[str] = Field(default_factory=list, max_length=32)
    selected_candidate_path: str | None = Field(default=None, max_length=500)
    existing_image: str | None = Field(default=None, max_length=500)
    video_prompt: str | None = Field(default=None, max_length=40000)
    video_quality: str | None = Field(default=None, pattern="^(720p|1080p|4K)$")
    video_aspect_ratio: str | None = Field(default=None, pattern="^(16:9|9:16|1:1|4:3)$")
    video_duration_seconds: int | None = Field(default=None, ge=1, le=VIDEO_GENERATION_DURATION_MAX_SECONDS)
    video_first_reference: str | None = Field(default=None, max_length=500)
    video_last_reference: str | None = Field(default=None, max_length=500)
    video_references: list[str] = Field(default_factory=list, max_length=32)
    video_tool: str | None = Field(default=None, pattern="^(kling_3_0|kling_3_0_omni|seedance)$")
    narration_text: str | None = Field(default=None, max_length=40000)
    narration_tts_text: str | None = Field(default=None, max_length=40000)
    narration_output: str | None = Field(default=None, max_length=500)
    narration_tool: str | None = Field(default=None, pattern="^(elevenlabs|silent|macos_say|say)$")
    render_video_path: str | None = Field(default=None, max_length=500)
    render_narration_path: str | None = Field(default=None, max_length=500)
    render_video_duration_seconds: int | None = Field(default=None, ge=1, le=600)
    render_narration_offset_seconds: float | None = Field(default=None, ge=0, le=120)


class FrontendReviewDraftRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(asset|scene|video|narration|render)$")
    note: str | None = Field(default=None, max_length=2000)
    items: list[FrontendReviewItem] = Field(default_factory=list, max_length=256)


class InsertCutRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    anchor_item_id: str | None = Field(default=None, max_length=200)
    scene_id: str | None = Field(default=None, max_length=80)
    position: str = Field(default="after", pattern="^(before|after|end)$")
    cut_id: str | None = Field(default=None, max_length=80)
    cut_name: str = Field(min_length=1, max_length=120)
    prompt: str | None = Field(default=None, max_length=40000)


class AssetCreateRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    asset_type: str = Field(pattern="^(character|object|location)$")
    title: str = Field(min_length=1, max_length=120)


class VideoPromptCreateRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    items: list[FrontendReviewItem] = Field(min_length=1, max_length=256)
    note: str | None = Field(default=None, max_length=2000)
    replace_all: bool = True
    approve_for_generation: bool = False


class NarrationDraftCreateRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    replace: bool = False


class NarrationSilentOkRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    item_id: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=2000)
    expected_revision: int = Field(ge=0)


class VideoGenerateItem(BaseModel):
    item_id: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=40000)
    first_reference: str | None = Field(default=None, max_length=500)
    last_reference: str | None = Field(default=None, max_length=500)
    references: list[str] = Field(default_factory=list, max_length=32)
    negative_prompt: str | None = Field(default=None, max_length=40000)
    quality: str = Field(default="1080p", pattern="^(720p|1080p|4K)$")
    aspect_ratio: str = Field(default="16:9", pattern="^(16:9|9:16|1:1|4:3)$")
    duration_seconds: int = Field(default=8, ge=1, le=VIDEO_GENERATION_DURATION_MAX_SECONDS)
    tool: str = Field(default="kling_3_0", pattern="^(kling_3_0|kling_3_0_omni|seedance)$")
    candidate_count: int = Field(default=3, ge=1, le=8)
    prompt_policy_version: str | None = Field(default=None, max_length=100)
    prompt_compiler_version: str | None = Field(default=None, max_length=100)
    prompt_sha256: str | None = Field(default=None, max_length=80)
    prompt_source_digest: str | None = Field(default=None, max_length=80)
    provider_execution_options: dict[str, Any] = Field(default_factory=dict)


class VideoGenerateRequest(VideoGenerateItem):
    run_id: str = Field(min_length=1, max_length=200)


class BulkVideoGenerateRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    items: list[VideoGenerateItem] = Field(min_length=1, max_length=64)
    concurrency: int = Field(default=2, ge=1, le=8)


class NarrationGenerateItem(BaseModel):
    item_id: str = Field(min_length=1, max_length=200)
    text: str = Field(default="", max_length=40000)
    tts_text: str | None = Field(default=None, max_length=40000)
    output: str | None = Field(default=None, max_length=500)
    tool: str = Field(default="elevenlabs", pattern="^(elevenlabs|silent|macos_say|say)$")
    duration_seconds: float | None = Field(default=None, ge=0.1, le=600)
    expected_revision: int = Field(ge=0)
    expected_tts_hash: str = Field(min_length=1, max_length=80)
    voice_id: str | None = Field(default=None, max_length=200)
    model_id: str | None = Field(default=None, max_length=200)
    voice_settings: dict[str, Any] = Field(default_factory=dict)
    output_format: str | None = Field(default=None, max_length=100)
    language_code: str | None = Field(default=None, max_length=20)
    pronunciation_dictionary_locators: list[dict[str, str]] = Field(default_factory=list, max_length=3)
    pronunciation_alias_source: str | None = Field(default=None, max_length=200)
    pronunciation_alias_sha256: str | None = Field(default=None, max_length=80)
    pronunciation_alias_path: str | None = Field(default=None, max_length=500)
    effective_delivery_hash: str | None = Field(default=None, max_length=80)
    tts_generation_group_id: str | None = Field(default=None, max_length=200)
    tts_continuity_hash: str | None = Field(default=None, max_length=80)
    previous_text: str | None = Field(default=None, max_length=40000)
    next_text: str | None = Field(default=None, max_length=40000)


class NarrationGenerateRequest(NarrationGenerateItem):
    run_id: str = Field(min_length=1, max_length=200)


class BulkNarrationGenerateRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    items: list[NarrationGenerateItem] = Field(min_length=1, max_length=256)
    concurrency: int = Field(default=2, ge=1, le=8)


class NarrationTextSaveRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    item_id: str = Field(min_length=1, max_length=200)
    text: str = Field(default="", max_length=40000)
    tts_text: str = Field(default="", max_length=40000)
    tool: str = Field(default="elevenlabs", pattern="^(elevenlabs|silent|macos_say|say)$")
    authoring_status: str = Field(default="draft", pattern="^(draft|human_locked|silent)$")
    expected_revision: int = Field(ge=0)


class NarrationAudioApproveRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    item_id: str = Field(min_length=1, max_length=200)
    candidate_id: str = Field(min_length=1, max_length=200)
    expected_revision: int = Field(ge=0)
    expected_tts_hash: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=2000)


class NarrationTimelineItem(BaseModel):
    item_id: str = Field(min_length=1, max_length=200)
    video_duration_seconds: int = Field(
        ge=1,
        le=VIDEO_GENERATION_DURATION_MAX_SECONDS,
    )
    narration_offset_seconds: float = Field(default=0, ge=0, le=120)


class NarrationListenEvidence(BaseModel):
    mode: str = Field(pattern="^sequential_full_run$")
    audio_set_hash: str = Field(min_length=1, max_length=80)
    item_ids: list[str] = Field(min_length=1, max_length=512)
    timeline: list[NarrationTimelineItem] = Field(min_length=1, max_length=512)
    completed_at: str = Field(min_length=1, max_length=100)


class NarrationRunApproveRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=2000)
    expected_audio_set_hash: str = Field(min_length=1, max_length=80)
    timeline: list[NarrationTimelineItem] = Field(min_length=1, max_length=512)
    listen_evidence: NarrationListenEvidence


class NarrationReviewRunRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)


class RenderInputItem(BaseModel):
    item_id: str = Field(min_length=1, max_length=200)
    video_path: str | None = Field(default=None, max_length=500)
    narration_path: str | None = Field(default=None, max_length=500)
    video_duration_seconds: int = Field(default=8, ge=1, le=600)
    narration_offset_seconds: float = Field(default=0, ge=0, le=120)


class RenderFreezeRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    items: list[RenderInputItem] = Field(min_length=1, max_length=512)
    output: str = Field(default="video.mp4", min_length=1, max_length=500)


class FinalRenderRequest(RenderFreezeRequest):
    reencode: bool = False


_chat_threads: dict[str, str] = {}
_create_jobs: dict[str, dict[str, Any]] = {}
_bulk_generation_jobs: dict[str, dict[str, Any]] = {}
_bulk_generation_tasks: dict[str, asyncio.Task[None]] = {}
_codex_client: CodexAppServerClient | None = None
_client_lock = asyncio.Lock()
_create_jobs_lock = asyncio.Lock()
_bulk_generation_jobs_lock = asyncio.Lock()
_generation_semaphore = asyncio.Semaphore(100)
_video_generation_semaphore = asyncio.Semaphore(4)
_narration_generation_semaphore = asyncio.Semaphore(4)
_generated_images_cutoff_lock = asyncio.Lock()
_chat_turn_lock = asyncio.Lock()
_chat_semaphore = asyncio.Semaphore(2)
_scene_detail_canonical_progress_lock = threading.Lock()
_run_write_locks: dict[tuple[str, str], asyncio.Lock] = {}
_run_write_locks_guard = asyncio.Lock()
_run_execution_leases: dict[str, FileLockLease] = {}
_run_execution_leases_guard = asyncio.Lock()
MAX_ZIP_BYTES = 250 * 1024 * 1024
MAX_CREATE_JOBS = 64
MAX_RUNNING_CREATE_JOBS = 2
BULK_GENERATION_JOB_SCHEMA = "toc.bulk_image_generation_job.v1"
BULK_GENERATION_TERMINAL_STATUSES = {"completed", "failed", "interrupted"}
_BULK_GENERATION_SERVER_INSTANCE_ID = uuid.uuid4().hex


def _image_generation_provenance_policy() -> str:
    configured = os.environ.get("TOC_IMAGE_GEN_PROVENANCE_POLICY", "").strip().lower()
    if configured == IMAGE_GENERATION_PROVENANCE_POLICY_SERIAL_FALLBACK:
        return IMAGE_GENERATION_PROVENANCE_POLICY_SERIAL_FALLBACK
    return IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2


def _image_generation_request_bound_provenance_enabled() -> bool:
    return _image_generation_provenance_policy() == IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2


def _effective_image_generation_parallelism() -> int:
    if _image_generation_request_bound_provenance_enabled():
        return max(1, int(IMAGE_GENERATION_PARALLELISM))
    return 1


def _image_generation_outer_timeout_seconds() -> float:
    execution_timeout = max(0.01, float(IMAGE_GENERATION_ITEM_TIMEOUT_SECONDS))
    recovery_grace = max(0.1, min(60.0, execution_timeout * 0.1))
    return execution_timeout + recovery_grace


def _image_generation_global_lock_dir() -> Path:
    configured = os.environ.get("TOC_IMAGE_GEN_GLOBAL_LOCK_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    workspace_key = hashlib.sha256(str(ROOT.resolve()).encode("utf-8")).hexdigest()[:12]
    return Path("/tmp") / "toc-image-generation-locks" / workspace_key


@asynccontextmanager
async def _global_image_generation_slot(provenance_policy: str):
    is_serial_fallback = provenance_policy == IMAGE_GENERATION_PROVENANCE_POLICY_SERIAL_FALLBACK
    lock_dir = _image_generation_global_lock_dir()
    timeout_seconds = max(1.0, float(IMAGE_GENERATION_QUEUE_TIMEOUT_SECONDS))
    if is_serial_fallback:
        async with _global_image_generation_mode_lock(
            lock_dir,
            exclusive=True,
            timeout_seconds=timeout_seconds,
        ):
            yield "serial-exclusive"
        return

    # Claim a bounded request slot before the shared mode lock so queued
    # request-bound work does not prevent an exclusive serial fallback from
    # draining the currently active requests.
    async with async_file_slot(
        lock_dir,
        namespace="request-bound",
        slots=max(1, int(IMAGE_GENERATION_GLOBAL_PARALLELISM)),
        timeout_seconds=timeout_seconds,
    ) as slot:
        async with _global_image_generation_mode_lock(
            lock_dir,
            exclusive=False,
            timeout_seconds=timeout_seconds,
        ):
            yield slot


@asynccontextmanager
async def _global_image_generation_mode_lock(
    lock_dir: Path,
    *,
    exclusive: bool,
    timeout_seconds: float,
):
    """Cross-process shared/exclusive gate for both provenance lanes."""

    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_file = (lock_dir / "generation-mode.lock").open("a+b")
    operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    deadline = time.monotonic() + max(0.1, timeout_seconds)
    acquired = False
    try:
        while True:
            try:
                fcntl.flock(lock_file.fileno(), operation | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    mode = "exclusive" if exclusive else "shared"
                    raise TimeoutError(f"timed out acquiring global image generation {mode} mode lock")
                await asyncio.sleep(0.05)
        yield
    finally:
        if acquired:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


@asynccontextmanager
async def _generated_images_fallback_claim_scope(allow_generated_images_fallback: bool) -> Any:
    if allow_generated_images_fallback:
        async with _generated_images_cutoff_lock:
            yield
    else:
        yield


async def _run_write_lock(run_id: str, resource: str) -> asyncio.Lock:
    key = (run_id, re.sub(r"[^A-Za-z0-9_.-]+", "_", resource))
    async with _run_write_locks_guard:
        lock = _run_write_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _run_write_locks[key] = lock
        return lock


@asynccontextmanager
async def _serialized_run_write(run_dir: Path, resource: str):
    safe_resource = re.sub(r"[^A-Za-z0-9_.-]+", "_", resource).strip("._") or "artifact"
    process_lock = await _run_write_lock(run_dir.name, safe_resource)
    async with process_lock:
        lock_dir = run_dir / ".locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_file = (lock_dir / f"{safe_resource}.lock").open("a+", encoding="utf-8")
        try:
            await asyncio.to_thread(fcntl.flock, lock_file.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            await asyncio.to_thread(fcntl.flock, lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()


async def _acquire_run_execution_lease(job_id: str, run_dir: Path) -> None:
    lock_path = run_dir / ".locks" / "create_resume.lock"
    lease = await acquire_file_lock(lock_path, wait=False)
    async with _run_execution_leases_guard:
        previous = _run_execution_leases.pop(job_id, None)
        if previous is not None:
            await release_file_lock(previous)
        _run_execution_leases[job_id] = lease


async def _release_run_execution_lease(job_id: str) -> None:
    async with _run_execution_leases_guard:
        lease = _run_execution_leases.pop(job_id, None)
    if lease is not None:
        await release_file_lock(lease)


async def get_codex_client() -> CodexAppServerClient:
    global _codex_client
    if app_server_disabled():
        raise HTTPException(status_code=503, detail="Codex app-server is disabled")
    async with _client_lock:
        if _codex_client is None:
            _codex_client = create_codex_app_server_client(cwd=ROOT)
            await _codex_client.start()
        return _codex_client


async def shutdown_codex_client() -> None:
    global _codex_client
    tasks = list(_bulk_generation_tasks.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _bulk_generation_tasks.clear()
    if _codex_client:
        await _codex_client.stop()
        _codex_client = None


def _toc_run_command(*, topic: str, run_id: str) -> str:
    topic_arg = json.dumps(topic, ensure_ascii=False)
    run_dir_arg = json.dumps(f"output/{run_id}", ensure_ascii=False)
    return f"/toc-run {topic_arg} --dry-run --review-policy drafts --run-dir {run_dir_arg}"


def _toc_immersive_command(*, topic: str, source: str | None = None, run_id: str, stop_target: str = "p680") -> str:
    source_text = (source or "").strip() or topic
    if stop_target not in {"p650", "p680"}:
        raise ValueError("stop_target must be p650 or p680")
    payload = {
        "topic": topic,
        "source": source_text,
        "run_dir": f"output/{run_id}",
        "stop_target": stop_target,
        "experience": "cinematic_story",
        "review_policy": "frontend",
        "handoff": "frontend_image_review",
        "required_skill": "toc-immersive-runner",
        "expected_skill_path": str(_toc_immersive_skill_path().relative_to(ROOT)),
    }
    return "\n".join(
        [
            "Use $toc-immersive-runner.",
            "",
            "Create a ToC immersive cinematic story run from this request.",
            f"Run the canonical p100-{stop_target} frontend-review workflow in one skill invocation.",
            "Do not execute or depend on Claude slash commands.",
            "Do not create a second run directory.",
            "Do not return success for placeholder scaffold output.",
            "Do not replace the canonical stage route with a shortcut or postprocess patch.",
            "Human review must be handed off to the frontend, not skipped.",
            "",
            "Request JSON:",
            json.dumps(payload, ensure_ascii=False, indent=2),
        ]
    )


def _toc_immersive_skill_path() -> Path:
    return ROOT / ".codex" / "skills" / "toc-immersive-runner" / "SKILL.md"


def _skill_matches_path(skill: dict[str, Any], expected: Path) -> bool:
    raw_path = skill.get("path") or skill.get("sourcePath") or skill.get("skillPath")
    if not raw_path:
        return False
    try:
        return Path(str(raw_path)).expanduser().resolve() == expected.resolve()
    except OSError:
        return False


def _extract_manifest_yaml_text(manifest_text: str) -> str:
    marker = "```yaml"
    start = manifest_text.find(marker)
    if start == -1:
        return manifest_text
    start = manifest_text.find("\n", start)
    if start == -1:
        return manifest_text
    end = manifest_text.find("```", start + 1)
    return manifest_text[start + 1 : end if end != -1 else len(manifest_text)]


def _asset_prompt(
    *,
    topic: str,
    asset_kind: str,
    asset_id: str,
    output: str,
    fixed_prompts: list[str],
    story_time: str = "",
) -> str:
    asset_type = {
        "character": "character_reference",
        "object": "object_reference",
        "location": "location_reference",
        "style": "style_reference",
    }.get(asset_kind, f"{asset_kind}_reference")
    return compile_asset_prompt(
        {
            "asset_id": asset_id,
            "asset_type": asset_type,
            "fixed_prompts": fixed_prompts,
            "visual_spec": {"subject": (fixed_prompts or [asset_id])[0]},
            "generation_plan": {"output": output, "reference_inputs": []},
        },
        topic_label=topic,
        story_time=story_time,
    )


def _asset_usage_by_id(manifest: dict[str, Any], id_key: str) -> dict[str, list[str]]:
    usage: dict[str, list[str]] = {}
    scenes = manifest.get("scenes") if isinstance(manifest.get("scenes"), list) else []
    for scene in scenes:
        if not isinstance(scene, dict) or is_non_renderable_manifest_node(scene):
            continue
        scene_id = str(scene.get("scene_id") or "")
        cuts = scene.get("cuts") if isinstance(scene.get("cuts"), list) else [scene]
        for cut_index, cut in enumerate(cuts, start=1):
            if not isinstance(cut, dict) or is_non_renderable_manifest_node(cut):
                continue
            selector = str(cut.get("selector") or "").strip()
            if not selector:
                selector = make_scene_cut_selector(
                    scene_id,
                    str(cut.get("cut_id") or cut_index),
                )
            image_generation = cut.get("image_generation") if isinstance(cut.get("image_generation"), dict) else {}
            for asset_id in image_generation.get(id_key) or []:
                normalized_id = str(asset_id or "").strip()
                if normalized_id:
                    usage.setdefault(normalized_id, []).append(selector)
    return {key: list(dict.fromkeys(value)) for key, value in usage.items()}


def _project_asset_plan_from_manifest(
    run_dir: Path,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    """Project reviewed asset bibles into the canonical asset-plan source."""

    asset_plan_path = run_dir / "asset_plan.md"
    original_plan_text = asset_plan_path.read_text(encoding="utf-8") if asset_plan_path.exists() else "# Asset Plan\n\n```yaml\nassets: []\n```\n"
    try:
        plan_data = yaml.safe_load(_extract_manifest_yaml_text(original_plan_text)) or {}
    except yaml.YAMLError:
        plan_data = {}
    if not isinstance(plan_data, dict):
        plan_data = {}
    old_entries = plan_data.get("assets") if isinstance(plan_data.get("assets"), list) else []
    old_entries = [deepcopy(entry) for entry in old_entries if isinstance(entry, dict)]
    old_by_output: dict[str, dict[str, Any]] = {}
    old_by_id: dict[str, list[dict[str, Any]]] = {}
    for entry in old_entries:
        generation_plan = entry.get("generation_plan") if isinstance(entry.get("generation_plan"), dict) else {}
        output = str(generation_plan.get("output") or "").strip()
        asset_id = str(entry.get("asset_id") or "").strip()
        if output:
            old_by_output[output] = entry
        if asset_id:
            old_by_id.setdefault(asset_id, []).append(entry)

    usage_by_kind = {
        "character_reference": _asset_usage_by_id(manifest, "character_ids"),
        "object_reference": _asset_usage_by_id(manifest, "object_ids"),
        "location_reference": _asset_usage_by_id(manifest, "location_ids"),
    }
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), dict) else {}
    projected: list[dict[str, Any]] = []
    claimed_old_entries: set[int] = set()

    def append_nodes(
        *,
        nodes: Any,
        id_key: str,
        asset_type: str,
        default_style: str,
        default_forbidden: list[str],
        default_views: list[str],
    ) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            asset_id = str(node.get(id_key) or node.get("asset_id") or "").strip()
            if not asset_id:
                continue
            outputs = [str(value).strip() for value in node.get("reference_images") or [] if str(value).strip()]
            for output in outputs:
                existing = old_by_output.get(output)
                if existing is None:
                    existing = next(
                        (candidate for candidate in old_by_id.get(asset_id, []) if id(candidate) not in claimed_old_entries),
                        None,
                    )
                if existing is not None:
                    claimed_old_entries.add(id(existing))
                entry = deepcopy(existing) if existing is not None else {}
                cinematic = node.get("cinematic") if isinstance(node.get("cinematic"), dict) else {}
                fixed_prompts = [str(value).strip() for value in node.get("fixed_prompts") or [] if str(value).strip()]
                visual_spec = entry.get("visual_spec") if isinstance(entry.get("visual_spec"), dict) else {}
                visual_spec = deepcopy(visual_spec)
                subject = str(cinematic.get("visual_subject") or "").strip()
                if subject:
                    visual_spec["subject"] = subject
                elif not str(visual_spec.get("subject") or "").strip() and fixed_prompts:
                    visual_spec["subject"] = fixed_prompts[0]
                visual_spec.setdefault("style", default_style)
                visual_spec.setdefault("forbidden", default_forbidden)

                generation_plan = entry.get("generation_plan") if isinstance(entry.get("generation_plan"), dict) else {}
                generation_plan = deepcopy(generation_plan)
                explicit_reference_inputs: list[str] | None = None
                for key in ("generation_references", "reference_inputs"):
                    if key in node:
                        explicit_reference_inputs = [
                            str(value).strip() for value in node.get(key) or [] if str(value).strip()
                        ]
                        break
                reference_inputs = (
                    explicit_reference_inputs
                    if explicit_reference_inputs is not None
                    else [str(value).strip() for value in generation_plan.get("reference_inputs") or [] if str(value).strip()]
                )
                generation_plan.update(
                    {
                        "execution_lane": "standard" if reference_inputs else "bootstrap_builtin",
                        "bootstrap_allowed": not reference_inputs,
                        "required_views": generation_plan.get("required_views") or default_views,
                        "reference_inputs": reference_inputs,
                        "output": output,
                    }
                )
                role = str(cinematic.get("role") or "").strip()
                entry.update(
                    {
                        "asset_id": asset_id,
                        "asset_type": asset_type,
                        "source_script_selectors": usage_by_kind.get(asset_type, {}).get(asset_id, []),
                        "story_purpose": role or str(entry.get("story_purpose") or "").strip(),
                        "fixed_prompts": fixed_prompts,
                        "visual_spec": visual_spec,
                        "generation_plan": generation_plan,
                        "review": entry.get("review") or {"status": "approved", "reason": "reviewed asset bible projection"},
                    }
                )
                if "generation_prompt" in node:
                    entry["generation_prompt"] = str(node.get("generation_prompt") or "").strip()
                else:
                    # The reviewed manifest bible is canonical.  Never let an
                    # explicit prompt from an older asset-plan revision bypass
                    # newly reviewed fixed prompts or visual subjects.
                    entry.pop("generation_prompt", None)
                for contract_key in ("subject_contract", "appearance_contract", "reuse_contract"):
                    if isinstance(node.get(contract_key), dict):
                        entry[contract_key] = deepcopy(node[contract_key])
                projected.append(entry)

    append_nodes(
        nodes=assets.get("character_bible"),
        id_key="character_id",
        asset_type="character_reference",
        default_style="photorealistic live-action cinematic",
        default_forbidden=["文字", "ロゴ", "アニメ"],
        default_views=["front", "side", "back"],
    )
    append_nodes(
        nodes=assets.get("object_bible"),
        id_key="object_id",
        asset_type="object_reference",
        default_style="photorealistic live-action product still",
        default_forbidden=["文字", "ロゴ", "玩具風"],
        default_views=["front"],
    )
    append_nodes(
        nodes=assets.get("location_bible"),
        id_key="location_id",
        asset_type="location_reference",
        default_style="photorealistic live-action cinematic location still",
        default_forbidden=["文字", "ロゴ", "人物主役", "アニメ"],
        default_views=["wide"],
    )

    style_guide = assets.get("style_guide") if isinstance(assets.get("style_guide"), dict) else {}
    style_refs = [str(value).strip() for value in style_guide.get("reference_images") or [] if str(value).strip()]
    if style_refs:
        append_nodes(
            nodes=[
                {
                    "asset_id": "style_guide",
                    "reference_images": style_refs,
                    "fixed_prompts": [str(style_guide.get("visual_style") or "").strip()],
                    "cinematic": {"visual_subject": str(style_guide.get("visual_style") or "").strip()},
                    "generation_prompt": str(style_guide.get("generation_prompt") or "").strip(),
                }
            ],
            id_key="asset_id",
            asset_type="style_reference",
            default_style=str(style_guide.get("visual_style") or "photorealistic live-action cinematic"),
            default_forbidden=[str(value) for value in style_guide.get("forbidden") or [] if str(value).strip()],
            default_views=["wide"],
        )

    updated_plan = deepcopy(plan_data)
    updated_plan["assets"] = projected
    if updated_plan != plan_data or not asset_plan_path.exists():
        _write_manifest_data(asset_plan_path, original_plan_text, updated_plan)
    return projected


def _asset_entries_from_manifest(run_dir: Path) -> list[dict[str, Any]]:
    manifest_path = run_dir / "video_manifest.md"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    data = yaml.safe_load(_extract_manifest_yaml_text(manifest_text)) or {}
    if not isinstance(data, dict):
        return []
    video_metadata = data.get("video_metadata") if isinstance(data.get("video_metadata"), dict) else {}
    topic = str(video_metadata.get("topic") or data.get("topic") or run_dir.name)
    story_time = str(video_metadata.get("time") or "").strip()
    entries: list[dict[str, Any]] = []
    for plan_index, plan_entry in enumerate(_project_asset_plan_from_manifest(run_dir, data), start=1):
        generation_plan = plan_entry.get("generation_plan") if isinstance(plan_entry.get("generation_plan"), dict) else {}
        output = str(generation_plan.get("output") or "").strip()
        if not output:
            continue
        asset_id = str(plan_entry.get("asset_id") or f"asset_{plan_index}").strip()
        asset_type = str(plan_entry.get("asset_type") or "asset_reference").strip()
        references = [str(value).strip() for value in generation_plan.get("reference_inputs") or [] if str(value).strip()]
        entries.append(
            {
                "asset_id": asset_id,
                "selector": f"{asset_type}_{asset_id}",
                "tool": "codex_builtin_image",
                "asset_type": asset_type,
                "execution_lane": "standard" if references else "bootstrap_builtin",
                "references": references,
                "output": output,
                "prompt": compile_asset_prompt(
                    plan_entry,
                    topic_label=topic,
                    story_time=story_time,
                ),
            }
        )
    return entries


def _write_asset_request_files(run_dir: Path) -> list[dict[str, Any]]:
    entries = _asset_entries_from_manifest(run_dir)
    try:
        existing_by_output = {
            str(item.output or ""): item
            for item in load_request_items(run_dir, "asset")
            if str(item.output or "").strip()
        }
    except (ImageRequestSnapshotError, ValueError):
        existing_by_output = {}
    used_selectors: set[str] = set()
    for entry in entries:
        references = [str(value) for value in entry.get("references") or [] if str(value).strip()]
        existing = existing_by_output.get(str(entry["output"]))
        existing_selector = str(existing.id or "").strip() if existing is not None else ""
        if existing_selector and existing_selector not in used_selectors:
            selector = existing_selector
        else:
            selector = _safe_artifact_id(str(entry.get("selector") or entry.get("asset_id") or "asset"))
            if selector in used_selectors:
                selector = f"{selector}_{hashlib.sha256(str(entry['output']).encode('utf-8')).hexdigest()[:8]}"
        used_selectors.add(selector)
        entry["selector"] = selector
        entry["references"] = references
        entry["reference_count"] = len(references)
        entry["execution_lane"] = "standard" if references else "bootstrap_builtin"
        entry["prompt_policy_version"] = ASSET_PROMPT_POLICY_VERSION
        entry["compiler_version"] = ASSET_PROMPT_COMPILER_VERSION
        entry["source_digest"] = asset_prompt_source_digest(
            prompt=str(entry["prompt"]),
            output=str(entry["output"]),
            references=references,
        )
    lines = ["# Asset Generation Requests", ""]
    for entry in entries:
        lines.extend(
            [
                f"## {entry['selector']}",
                "",
                f"- tool: `{entry['tool']}`",
                f"- prompt_policy_version: `{entry['prompt_policy_version']}`",
                f"- asset_type: `{entry['asset_type']}`",
                f"- execution_lane: `{entry['execution_lane']}`",
                f"- reference_count: `{entry['reference_count']}`",
                f"- output: `{entry['output']}`",
                *(
                    ["- references:", *[f"  - `参照画像{index}`: `{reference}`" for index, reference in enumerate(entry["references"], start=1)]]
                    if entry["references"]
                    else ["- references: `[]`"]
                ),
                "",
                "```api_prompt",
                str(entry["prompt"]).strip(),
                "```",
                "",
            ]
        )
    if not entries:
        lines.extend(["該当エントリはありません。", ""])
    (run_dir / "asset_generation_requests.md").write_text("\n".join(lines), encoding="utf-8")
    manifest_lines = ["```yaml", "assets:"]
    for entry in entries:
        manifest_lines.extend(
            [
                f"  - selector: {json.dumps(entry['selector'], ensure_ascii=False)}",
                f"    output: {json.dumps(entry['output'], ensure_ascii=False)}",
                f"    asset_type: {json.dumps(entry['asset_type'], ensure_ascii=False)}",
                "    status: requested",
            ]
        )
    if not entries:
        manifest_lines.append("  []")
    manifest_lines.append("```")
    (run_dir / "asset_generation_manifest.md").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    if entries:
        snapshot = materialize_request_snapshot(
            run_dir,
            kind="asset",
            items=[
                {
                    "item_id": entry["selector"],
                    "destination": entry["output"],
                    "prompt": entry["prompt"],
                    "prompt_policy_version": entry["prompt_policy_version"],
                    "compiler_version": entry["compiler_version"],
                    "source_digest": entry["source_digest"],
                    "references": entry["references"],
                }
                for entry in entries
            ],
            source_artifact="asset_generation_requests.md",
        )
        write_request_snapshot_atomic(
            run_dir / "asset_generation_request_snapshot.json",
            snapshot,
            run_dir=run_dir,
        )
    else:
        (run_dir / "asset_generation_request_snapshot.json").unlink(missing_ok=True)
    return entries


async def _set_create_job(job_id: str, patch: dict[str, Any]) -> None:
    log_payload: dict[str, Any] | None = None
    async with _create_jobs_lock:
        job = _create_jobs.get(job_id)
        if job:
            job.update(patch)
            log_payload = dict(job)
    await asyncio.to_thread(_update_process_record_best_effort, job_id=job_id, patch=patch)
    if log_payload:
        try:
            run_dir = safe_run_dir(str(log_payload.get("runId") or ""), ROOT)
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="create_job_update",
                status=str(log_payload.get("status") or "unknown"),
                item_id=job_id,
                request={"patch": patch},
                response={
                    "jobId": job_id,
                    "runId": log_payload.get("runId"),
                    "message": log_payload.get("message"),
                    "error": log_payload.get("error"),
                    "errorCode": log_payload.get("errorCode"),
                },
            )
        except Exception:
            pass


def _process_label(process_number: int) -> str:
    return f"p{max(0, int(process_number)):03d}"


def _process_number(process: str | int | None) -> int:
    if isinstance(process, int):
        return process
    text = str(process or "").strip().lower()
    if text.startswith("p"):
        text = text[1:]
    try:
        return int(text)
    except ValueError:
        return 0


def _current_process_number_for_run(run_id: str) -> int:
    try:
        state = parse_state_file(safe_run_dir(run_id, ROOT) / "state.txt")
    except Exception:
        return 0
    current = 0
    for slot in P680_FIXED_SLOTS:
        status = (state.get(f"slot.{slot}.status") or "").strip().lower()
        if status in SLOT_TERMINAL_STATES:
            current = _process_number(slot)
    return current


def _current_process_for_run(run_id: str) -> str:
    return _process_label(_current_process_number_for_run(run_id))


def _create_process_record_best_effort(
    *,
    job: dict[str, Any],
    title: str,
    source: str,
    stop_target: str,
    generate_images: bool,
) -> dict[str, Any] | None:
    try:
        record = process_store.create_process_run(
            job_id=str(job["jobId"]),
            run_id=str(job["runId"]),
            title=title,
            source=source,
            run_path=str(job["path"]),
            create_mode=str(job.get("createMode") or CREATE_MODE_NORMAL),
            stop_target_number=_process_number(stop_target),
            current_process_number=_process_number(job.get("currentProcessNumber") or job.get("currentProcess")),
            status=str(job.get("status") or "running"),
            pid=os.getpid(),
            message=str(job.get("message") or ""),
            metadata={"generateImages": generate_images},
        )
    except Exception as exc:
        return {"enabled": process_store.enabled(), "error": str(exc)}
    return record.to_api() if record else {"enabled": False, "reason": process_store.unavailable_reason()}


def _update_process_record_best_effort(*, job_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    db_patch: dict[str, Any] = {}
    if "currentProcess" in patch and "currentProcessNumber" not in patch:
        db_patch["currentProcessNumber"] = _process_number(patch.get("currentProcess"))
    if "stopTarget" in patch and "stopTargetNumber" not in patch:
        db_patch["stopTargetNumber"] = _process_number(patch.get("stopTarget"))
    key_map = {
        "status": "status",
        "message": "message",
        "error": "error",
        "errorCode": "errorCode",
        "stopTargetNumber": "stopTargetNumber",
        "currentProcessNumber": "currentProcessNumber",
        "metadata": "metadata",
    }
    for source_key, target_key in key_map.items():
        if source_key in patch:
            db_patch[target_key] = patch[source_key]
    if not db_patch:
        return None
    try:
        record = process_store.update_process_run(job_id=job_id, patch=db_patch)
    except Exception as exc:
        return {"enabled": process_store.enabled(), "error": str(exc)}
    return record.to_api() if record else None


async def _sync_process_current_process(job_id: str, run_id: str) -> None:
    process_number = _current_process_number_for_run(run_id)
    await _set_create_job(job_id, {"currentProcess": _process_label(process_number), "currentProcessNumber": process_number})


def _delete_existing_images_for_image_resume(run_dir: Path) -> dict[str, Any]:
    assets_dir = run_dir / "assets"
    image_suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    preserved: list[str] = []
    if not assets_dir.exists():
        return {"deletedCount": 0, "deleted": [], "preservedCount": 0, "preserved": [], "errors": []}
    for path in sorted(assets_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in image_suffixes:
            continue
        preserved.append(path.relative_to(run_dir).as_posix())
    return {
        "deletedCount": 0,
        "deleted": [],
        "preservedCount": len(preserved),
        "preserved": preserved[:200],
        "errors": [],
        "reason": "hash-aware partial resume preserves existing outputs until each item is proven stale",
    }


def _validate_created_run(run_id: str) -> None:
    run_dir = safe_run_dir(run_id, ROOT)
    required = ["state.txt", "video_manifest.md"]
    missing = [name for name in required if not (run_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"ToC run was not scaffolded: missing {', '.join(missing)}")


def _manifest_cut_contract(data: dict[str, Any], *, min_cuts_per_scene: int = 1) -> tuple[list[str], set[str]]:
    issues: list[str] = []
    required_outputs: set[str] = set()
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        return ["video_manifest.md scenes must be a list"], required_outputs
    for index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            issues.append(f"scene[{index}]: invalid scene")
            continue
        if str(scene.get("kind") or "").strip().endswith("_reference"):
            continue
        scene_id = str(scene.get("scene_id") or index).strip()
        cuts = scene.get("cuts")
        if not isinstance(cuts, list) or len(cuts) < min_cuts_per_scene:
            issues.append(f"scene {scene_id}: requires at least {min_cuts_per_scene} cuts")
            continue
        coverage = scene.get("scene_cut_coverage_plan")
        if isinstance(coverage, dict):
            minimums = coverage.get("min_cut_count")
            if not isinstance(minimums, dict):
                issues.append(
                    f"scene {scene_id}: scene_cut_coverage_plan.min_cut_count must be a mapping"
                )
            else:
                distinct_minimum = minimums.get(
                    "by_distinct_semantic_obligations"
                )
                event_minimum = minimums.get("by_event_beats")
                selected_minimum = minimums.get("selected")
                semantic_values = (
                    distinct_minimum,
                    event_minimum,
                    selected_minimum,
                )
                if any(
                    isinstance(value, bool)
                    or not isinstance(value, int)
                    or value < 0
                    for value in semantic_values
                ):
                    issues.append(
                        f"scene {scene_id}: semantic cut minimums must be non-negative integers"
                    )
                else:
                    expected_minimum = max(distinct_minimum, event_minimum)
                    if selected_minimum != expected_minimum:
                        issues.append(
                            f"scene {scene_id}: semantic cut minimum selected "
                            f"{selected_minimum} != {expected_minimum}"
                        )
                    if len(cuts) < selected_minimum:
                        issues.append(
                            f"scene {scene_id}: {len(cuts)} cuts do not cover semantic "
                            f"minimum {selected_minimum}"
                        )
                for legacy_dimension in ("by_importance", "by_duration"):
                    legacy_value = minimums.get(legacy_dimension, 0)
                    if (
                        isinstance(legacy_value, bool)
                        or not isinstance(legacy_value, int)
                        or legacy_value != 0
                    ):
                        issues.append(
                            f"scene {scene_id}: {legacy_dimension} must be 0; "
                            "cut count is semantic-only"
                        )
            selected_cut_count = coverage.get("selected_cut_count")
            if selected_cut_count is not None and selected_cut_count != len(cuts):
                issues.append(
                    f"scene {scene_id}: selected_cut_count {selected_cut_count} "
                    f"!= actual cuts {len(cuts)}"
                )
        for cut_index, cut in enumerate(cuts, start=1):
            if not isinstance(cut, dict):
                issues.append(f"scene {scene_id} cut[{cut_index}]: invalid cut")
                continue
            image_generation = cut.get("image_generation")
            if not isinstance(image_generation, dict):
                issues.append(f"scene {scene_id} cut {cut.get('cut_id') or cut_index}: missing image_generation")
                continue
            output = str(image_generation.get("output") or "").strip()
            if not output:
                issues.append(f"scene {scene_id} cut {cut.get('cut_id') or cut_index}: missing image_generation.output")
                continue
            required_outputs.add(output)
    return issues, required_outputs


def _validate_image_prompt_request_revision(
    run_dir: Path,
    manifest_data: dict[str, Any],
    *,
    require_resolved_references: bool = False,
    require_compiled_v2: bool = False,
) -> str:
    """Verify the scene request snapshot against Markdown and manifest v2 payloads."""

    snapshot_path = run_dir / "image_generation_request_snapshot.json"
    if not snapshot_path.is_file():
        raise RuntimeError(
            "ToC run did not reach p650: missing image_generation_request_snapshot.json"
        )
    try:
        snapshot = load_request_snapshot(
            snapshot_path,
            run_dir=run_dir,
            verify_references=True,
        )
    except ImageRequestSnapshotError as exc:
        raise RuntimeError(
            f"ToC run did not reach p650: invalid image request snapshot: {exc}"
        ) from exc
    if snapshot.kind != "scene":
        raise RuntimeError(
            f"ToC run did not reach p650: image request snapshot kind must be scene, got {snapshot.kind}"
        )
    try:
        markdown_items = load_request_items(run_dir, "scene")
    except (ImageRequestSnapshotError, ValueError) as exc:
        raise RuntimeError(
            f"ToC run did not reach p650: request Markdown/snapshot mismatch: {exc}"
        ) from exc
    if {item.id for item in markdown_items} != {item.item_id for item in snapshot.items}:
        raise RuntimeError(
            "ToC run did not reach p650: request Markdown/snapshot item mismatch"
        )
    if require_resolved_references:
        try:
            for item in snapshot.items:
                deferred = [reference.path for reference in item.references if reference.deferred]
                if deferred:
                    raise ImageRequestSnapshotError(
                        f"snapshot still defers references for {item.item_id}: {', '.join(deferred)}"
                    )
                current_reference_sha256s(run_dir, item, allow_deferred=False)
        except ImageRequestSnapshotError as exc:
            raise RuntimeError(
                f"ToC run did not reach p650: unresolved image request reference: {exc}"
            ) from exc

    targets = _manifest_scene_targets(manifest_data)
    frontend_v2_contract = str(manifest_data.get("schema_version") or "") == "scene_event_v1"
    matched_selectors: set[str] = set()
    for item in snapshot.items:
        target = next(
            (candidate for candidate in targets if item.item_id in candidate["aliases"]),
            None,
        )
        if target is None:
            raise RuntimeError(
                f"ToC run did not reach p650: snapshot item is absent from manifest: {item.item_id}"
            )
        selector = str(target["selector"])
        matched_selectors.add(selector)
        node = target["cut"] if isinstance(target.get("cut"), dict) else {}
        image_generation = (
            node.get("image_generation")
            if isinstance(node.get("image_generation"), dict)
            else {}
        )
        output = str(image_generation.get("output") or "").strip()
        if item.destination != output:
            raise RuntimeError(
                f"ToC run did not reach p650: snapshot/manifest output mismatch for {selector}"
            )
        payload = image_generation.get("api_prompt_payload")
        payload = payload if isinstance(payload, dict) else {}
        policy_version = str(payload.get("policy_version") or "").strip()
        plan = image_generation.get("first_frame_visual_plan")
        has_v1_plan = isinstance(plan, dict) and str(plan.get("schema_version") or "") == "first_frame_visual_plan_v1"
        if (
            require_compiled_v2
            and (frontend_v2_contract or has_v1_plan)
            and policy_version != "image_api_prompt_v2"
        ):
            raise RuntimeError(
                f"ToC run did not reach p650: compiled v2 manifest payload required for {selector}"
            )
        if policy_version != "image_api_prompt_v2":
            if item.prompt_policy_version == "image_api_prompt_v2":
                raise RuntimeError(
                    f"ToC run did not reach p650: v2 snapshot item lacks v2 manifest payload for {selector}"
                )
            continue
        expected = {
            "prompt": str(payload.get("prompt") or ""),
            "prompt_policy_version": policy_version,
            "compiler_version": str(payload.get("compiler_version") or ""),
            "source_digest": str(payload.get("source_digest") or ""),
            "prompt_sha256": str(payload.get("sha256") or ""),
        }
        actual = {
            "prompt": item.prompt,
            "prompt_policy_version": item.prompt_policy_version,
            "compiler_version": item.compiler_version,
            "source_digest": item.source_digest,
            "prompt_sha256": item.prompt_sha256,
        }
        mismatched = [key for key, value in expected.items() if value != actual[key]]
        manifest_references = [
            str(value).strip()
            for value in payload.get("reference_images") or []
            if str(value).strip()
        ]
        snapshot_references = [reference.path for reference in item.references]
        if manifest_references != snapshot_references:
            mismatched.append("reference_images")
        if mismatched:
            raise RuntimeError(
                "ToC run did not reach p650: snapshot/manifest revision mismatch "
                f"for {selector}: {', '.join(mismatched)}"
            )

    missing_v2_targets = [
        str(target["selector"])
        for target in targets
        if str(
            (
                (
                    target["cut"].get("image_generation")
                    if isinstance(target.get("cut"), dict)
                    and isinstance(target["cut"].get("image_generation"), dict)
                    else {}
                ).get("api_prompt_payload")
                or {}
            ).get("policy_version")
            or ""
        )
        == "image_api_prompt_v2"
        and str(target["selector"]) not in matched_selectors
    ]
    if missing_v2_targets:
        raise RuntimeError(
            "ToC run did not reach p650: v2 manifest cuts missing from request snapshot "
            + ", ".join(missing_v2_targets)
        )
    return snapshot.request_revision


def _image_prompt_story_review_scalar(report_text: str, key: str) -> str:
    match = re.search(
        rf"(?mi)^\s*-?\s*{re.escape(key)}\s*:\s*`?([^`\n]+?)`?\s*$",
        report_text,
    )
    return match.group(1).strip() if match else ""


def _deterministic_image_prompt_review_sources_are_current(run_dir: Path) -> bool:
    report_path = run_dir / "image_prompt_story_review.md"
    source_paths = [run_dir / name for name in ("story.md", "script.md", "video_manifest.md")]
    if not report_path.is_file() or any(not path.is_file() for path in source_paths):
        return False
    report_mtime_ns = report_path.stat().st_mtime_ns
    return all(path.stat().st_mtime_ns <= report_mtime_ns for path in source_paths)


def _deterministic_image_prompt_review_sections(
    report_text: str,
) -> list[tuple[str, str]]:
    headings = list(re.finditer(r"(?m)^##\s+([^\r\n]+?)\s*$", report_text))
    sections: list[tuple[str, str]] = []
    for index, heading in enumerate(headings):
        selector = heading.group(1).strip().strip("`\"'")
        body_start = heading.end()
        body_end = headings[index + 1].start() if index + 1 < len(headings) else len(report_text)
        sections.append((selector, report_text[body_start:body_end]))
    return sections


def _canonical_deterministic_image_prompt_selector(value: Any) -> str:
    raw = str(value or "").strip().strip("`\"'")
    match = re.fullmatch(
        r"scene[_:]?([0-9]+(?:\.[0-9]+)*)[_-]?cut[_:]?([0-9]+(?:\.[0-9]+)*)",
        raw,
        flags=re.IGNORECASE,
    )
    if not match:
        return raw
    return make_scene_cut_selector(match.group(1), match.group(2))


def _deterministic_image_prompt_review_structure_errors(report_text: str) -> list[str]:
    errors: list[str] = []
    format_version = _image_prompt_story_review_scalar(report_text, "review_format_version")
    if format_version != "deterministic_image_prompt_review_v2":
        errors.append("deterministic image prompt story review format is missing or unsupported")

    scalar_values: dict[str, int] = {}
    for key in (
        "reviewed_entries",
        "entries_with_findings",
        "findings",
        "hard_findings",
        "blocking_hard_findings",
        "soft_findings",
        "unresolved_entries",
    ):
        raw = _image_prompt_story_review_scalar(report_text, key)
        try:
            parsed = int(raw)
        except ValueError:
            parsed = -1
        scalar_values[key] = parsed
        if parsed < 0:
            errors.append(
                f"deterministic image prompt story review {key} is missing or invalid"
            )

    reviewed_entries = scalar_values["reviewed_entries"]
    finding_count = scalar_values["findings"]
    blocking_hard_findings = scalar_values["blocking_hard_findings"]
    unresolved_entries = scalar_values["unresolved_entries"]
    if reviewed_entries == 0:
        errors.append("deterministic image prompt story review has no reviewed entries")
    empty_scope = _image_prompt_story_review_scalar(
        report_text,
        "empty_review_scope",
    ).lower()
    if empty_scope not in {"true", "false", "1", "0", "yes", "no"}:
        errors.append(
            "deterministic image prompt story review empty_review_scope is missing or invalid"
        )
    elif reviewed_entries > 0 and empty_scope in {"true", "1", "yes"}:
        errors.append(
            "deterministic image prompt story review marks a non-empty review as empty"
        )
    elif reviewed_entries == 0 and empty_scope in {"false", "0", "no"}:
        errors.append(
            "deterministic image prompt story review empty scope flag contradicts reviewed_entries"
        )

    status = _image_prompt_story_review_scalar(report_text, "status").upper()
    expected_status = (
        "FAIL"
        if reviewed_entries == 0 or unresolved_entries > 0
        else ("WARN" if finding_count > 0 else "PASS")
    )
    if status not in {"PASS", "WARN", "FAIL"}:
        errors.append("deterministic image prompt story review status is missing or invalid")
    elif finding_count >= 0 and unresolved_entries >= 0 and status != expected_status:
        errors.append(
            "deterministic image prompt story review status contradicts its finding summary: "
            f"status={status}, expected={expected_status}"
        )
    sections = _deterministic_image_prompt_review_sections(report_text)
    canonical_selectors = [
        _canonical_deterministic_image_prompt_selector(selector)
        for selector, _body in sections
    ]
    invalid_selectors = [
        selector
        for (selector, _body), canonical in zip(sections, canonical_selectors)
        if not re.fullmatch(
            r"scene[0-9]+(?:\.[0-9]+)*_cut[0-9]+(?:\.[0-9]+)*",
            canonical,
        )
    ]
    if invalid_selectors:
        errors.append(
            "deterministic image prompt story review has invalid selectors: "
            + ", ".join(invalid_selectors)
        )
    if reviewed_entries >= 0 and len(sections) != reviewed_entries:
        errors.append(
            "deterministic image prompt story review section coverage mismatch: "
            f"reviewed_entries={reviewed_entries}, sections={len(sections)}"
        )
    if len(set(canonical_selectors)) != len(canonical_selectors):
        errors.append("deterministic image prompt story review has duplicate selectors")
    derived_entries_with_findings = 0
    derived_finding_count = 0
    derived_hard_finding_count = 0
    derived_soft_finding_count = 0
    for selector, body in sections:
        for required_key in ("output", "narration", "rubric_scores"):
            if not _image_prompt_story_review_scalar(body, required_key):
                errors.append(
                    "deterministic image prompt story review section "
                    f"{required_key} is missing for {selector}"
                )
        overall_score_text = _image_prompt_story_review_scalar(body, "overall_score")
        try:
            overall_score = float(overall_score_text)
        except ValueError:
            overall_score = -1.0
        if not 0.0 <= overall_score <= 1.0:
            errors.append(
                "deterministic image prompt story review section overall_score is missing or invalid "
                f"for {selector}"
            )
        raw_hard_codes = {
            code.strip().strip("`\"'")
            for code in _image_prompt_story_review_scalar(
                body,
                "hard_finding_codes",
            ).split(",")
            if code.strip().strip("`\"'")
        }
        soft_codes = {
            code.strip().strip("`\"'")
            for code in _image_prompt_story_review_scalar(
                body,
                "soft_finding_codes",
            ).split(",")
            if code.strip().strip("`\"'")
        }
        blocking_hard_codes = {
            code.strip().strip("`\"'")
            for code in _image_prompt_story_review_scalar(
                body,
                "blocking_hard_finding_codes",
            ).split(",")
            if code.strip().strip("`\"'")
        }
        human_review_requested = _image_prompt_story_review_scalar(
            body,
            "human_review_ok",
        ).lower() in {"true", "1", "yes"}
        human_review_reason = _image_prompt_story_review_scalar(
            body,
            "human_review_reason",
        )
        human_review_ok = bool(human_review_requested and human_review_reason.strip())
        if human_review_requested and raw_hard_codes and not human_review_reason.strip():
            errors.append(
                "deterministic image prompt story review human override reason is missing for "
                f"{selector}"
            )
        expected_blocking_codes = set() if human_review_ok else raw_hard_codes
        if blocking_hard_codes != expected_blocking_codes:
            errors.append(
                "deterministic image prompt story review blocking code mismatch for "
                f"{selector}"
            )
        finding_codes = [
            finding_match.group(1).strip()
            for finding_match in re.finditer(
                r"(?m)^-\s+([a-z][a-z0-9_]*)\s*:\s*(.+?)\s*$",
                body,
            )
            if finding_match.group(1).strip()
            not in _DETERMINISTIC_REVIEW_METADATA_KEYS
        ]
        declared_codes = raw_hard_codes | soft_codes
        if set(finding_codes) != declared_codes:
            errors.append(
                "deterministic image prompt story review finding code/detail mismatch for "
                f"{selector}"
            )
        if finding_codes:
            derived_entries_with_findings += 1
        derived_finding_count += len(finding_codes)
        derived_hard_finding_count += sum(
            1 for code in finding_codes if code in raw_hard_codes
        )
        derived_soft_finding_count += sum(
            1 for code in finding_codes if code in soft_codes
        )
        section_review = _image_prompt_story_review_scalar(body, "review").upper()
        expected_section_review = (
            "FAIL"
            if raw_hard_codes and not human_review_ok
            else ("WARN" if finding_codes else "PASS")
        )
        if section_review not in {"PASS", "WARN", "FAIL"}:
            errors.append(
                "deterministic image prompt story review section review status is missing or invalid "
                f"for {selector}"
            )
        elif section_review != expected_section_review:
            errors.append(
                "deterministic image prompt story review section review status contradicts findings "
                f"for {selector}: review={section_review}, expected={expected_section_review}"
            )
    hard_findings = scalar_values["hard_findings"]
    entries_with_findings = scalar_values["entries_with_findings"]
    soft_findings = scalar_values["soft_findings"]
    if entries_with_findings >= 0 and entries_with_findings != derived_entries_with_findings:
        errors.append(
            "deterministic image prompt story review entries_with_findings detail mismatch: "
            f"summary={entries_with_findings}, sections={derived_entries_with_findings}"
        )
    if finding_count >= 0 and finding_count != derived_finding_count:
        errors.append(
            "deterministic image prompt story review finding detail count mismatch: "
            f"summary={finding_count}, details={derived_finding_count}"
        )
    if hard_findings >= 0 and hard_findings != derived_hard_finding_count:
        errors.append(
            "deterministic image prompt story review hard finding detail mismatch: "
            f"summary={hard_findings}, details={derived_hard_finding_count}"
        )
    if soft_findings >= 0 and soft_findings != derived_soft_finding_count:
        errors.append(
            "deterministic image prompt story review soft finding detail mismatch: "
            f"summary={soft_findings}, details={derived_soft_finding_count}"
        )
    if hard_findings >= 0 and blocking_hard_findings > hard_findings:
        errors.append(
            "deterministic image prompt story review has more blocking hard findings than hard findings"
        )
    derived_blocking_findings = _deterministic_image_prompt_hard_findings_from_report_text(
        report_text
    )
    derived_unresolved_selectors = {
        _canonical_deterministic_image_prompt_selector(detail["selector"])
        for detail in derived_blocking_findings
    }
    if (
        blocking_hard_findings >= 0
        and blocking_hard_findings != len(derived_blocking_findings)
    ):
        errors.append(
            "deterministic image prompt story review blocking finding detail mismatch: "
            f"summary={blocking_hard_findings}, details={len(derived_blocking_findings)}"
        )
    if unresolved_entries >= 0 and unresolved_entries != len(derived_unresolved_selectors):
        errors.append(
            "deterministic image prompt story review unresolved selector detail mismatch: "
            f"summary={unresolved_entries}, selectors={len(derived_unresolved_selectors)}"
        )
    return _dedupe_preserve_order(errors)


def _deterministic_image_prompt_review_binding_errors(
    run_dir: Path,
    report_text: str,
) -> list[str]:
    errors: list[str] = []
    canonical_manifest = (run_dir / "video_manifest.md").resolve()
    reported_manifest_text = _image_prompt_story_review_scalar(report_text, "manifest")
    if not reported_manifest_text:
        errors.append("deterministic image prompt story review manifest binding is missing")
    else:
        reported_manifest = Path(reported_manifest_text)
        if not reported_manifest.is_absolute():
            reported_manifest = (ROOT / reported_manifest).resolve()
        else:
            reported_manifest = reported_manifest.resolve()
        if reported_manifest != canonical_manifest:
            errors.append(
                "deterministic image prompt story review targets a different manifest"
            )

    for filename, key in (
        ("video_manifest.md", "manifest_sha256"),
        ("story.md", "story_sha256"),
        ("script.md", "script_sha256"),
    ):
        source_path = run_dir / filename
        reported_digest = _image_prompt_story_review_scalar(report_text, key).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", reported_digest):
            errors.append(
                f"deterministic image prompt story review {key} is missing or invalid"
            )
            continue
        if not source_path.is_file() or _file_sha256(source_path) != reported_digest:
            errors.append(
                f"deterministic image prompt story review {filename} digest is stale"
            )
    return _dedupe_preserve_order(errors)


def _deterministic_image_prompt_hard_gate_errors(
    run_dir: Path,
    *,
    require_current: bool = True,
) -> list[str]:
    report_path = run_dir / "image_prompt_story_review.md"
    if not report_path.is_file():
        return ["deterministic image prompt story review is missing"]
    errors: list[str] = []
    if require_current and not _deterministic_image_prompt_review_sources_are_current(run_dir):
        errors.append("deterministic image prompt story review is stale")
    report_text = report_path.read_text(encoding="utf-8", errors="replace")
    errors.extend(_deterministic_image_prompt_review_structure_errors(report_text))
    errors.extend(_deterministic_image_prompt_review_binding_errors(run_dir, report_text))
    status = _image_prompt_story_review_scalar(report_text, "status").upper()
    blocking_hard_text = _image_prompt_story_review_scalar(
        report_text,
        "blocking_hard_findings",
    )
    unresolved_text = _image_prompt_story_review_scalar(report_text, "unresolved_entries")
    empty_scope = _image_prompt_story_review_scalar(report_text, "empty_review_scope").lower()
    try:
        blocking_hard_findings = int(blocking_hard_text)
    except ValueError:
        blocking_hard_findings = -1
    try:
        unresolved_entries = int(unresolved_text)
    except ValueError:
        unresolved_entries = -1
    if status not in {"PASS", "WARN"}:
        errors.append(f"deterministic image prompt story review status is {status or '(missing)'}")
    if blocking_hard_findings != 0:
        errors.append(
            "deterministic image prompt story review has "
            f"{blocking_hard_text or '(missing)'} blocking hard finding(s)"
        )
    if unresolved_entries != 0:
        errors.append(
            "deterministic image prompt story review has "
            f"{unresolved_text or '(missing)'} unresolved entrie(s)"
        )
    if empty_scope not in {"false", "0", "no"}:
        errors.append("deterministic image prompt story review has an empty or invalid scope")
    return _dedupe_preserve_order(errors)


_DETERMINISTIC_REVIEW_METADATA_KEYS = {
    "output",
    "narration",
    "overall_score",
    "rubric_scores",
    "agent_review_ok",
    "human_review_ok",
    "human_review_reason",
    "review",
    "agent_review_reason_keys",
    "hard_finding_codes",
    "blocking_hard_finding_codes",
    "soft_finding_codes",
    "suggested_character_ids",
    "suggested_object_ids",
}


def _deterministic_image_prompt_hard_findings_from_report_text(
    report_text: str,
) -> list[dict[str, str]]:
    """Return unapproved selector/code/message detail from report text.

    Current reports name hard codes explicitly.  For an older report, an
    agent_review_ok=false section is still surfaced with all of its concrete
    finding lines so repair keeps the selector and evidence instead of falling
    back to an opaque run-wide error.
    """

    details: list[dict[str, str]] = []
    for selector, body in _deterministic_image_prompt_review_sections(report_text):
        human_review_requested = _image_prompt_story_review_scalar(
            body,
            "human_review_ok",
        ).lower() in {"true", "1", "yes"}
        human_review_reason = _image_prompt_story_review_scalar(
            body,
            "human_review_reason",
        )
        if human_review_requested and human_review_reason.strip():
            continue
        hard_code_text = _image_prompt_story_review_scalar(
            body,
            "hard_finding_codes",
        )
        hard_codes = {
            code.strip().strip("`\"'")
            for code in hard_code_text.split(",")
            if code.strip().strip("`\"'")
        }
        legacy_hard_section = (
            not hard_codes
            and _image_prompt_story_review_scalar(body, "agent_review_ok").lower()
            in {"false", "0", "no"}
        )
        if not hard_codes and not legacy_hard_section:
            continue
        for finding_match in re.finditer(
            r"(?m)^-\s+([a-z][a-z0-9_]*)\s*:\s*(.+?)\s*$",
            body,
        ):
            code = finding_match.group(1).strip()
            if code in _DETERMINISTIC_REVIEW_METADATA_KEYS:
                continue
            if hard_codes and code not in hard_codes:
                continue
            details.append(
                {
                    "selector": selector,
                    "code": code,
                    "message": finding_match.group(2).strip(),
                }
            )
    return details


def _deterministic_image_prompt_hard_findings(run_dir: Path) -> list[dict[str, str]]:
    report_path = run_dir / "image_prompt_story_review.md"
    if not report_path.is_file():
        return []
    return _deterministic_image_prompt_hard_findings_from_report_text(
        report_path.read_text(encoding="utf-8", errors="replace")
    )


def _deterministic_image_prompt_hard_finding_details_are_complete(
    run_dir: Path,
    details: list[dict[str, str]],
    entry_ids: list[str],
) -> bool:
    report_path = run_dir / "image_prompt_story_review.md"
    if not report_path.is_file() or not details:
        return False
    if not _deterministic_image_prompt_review_sources_are_current(run_dir):
        return False
    report_text = report_path.read_text(encoding="utf-8", errors="replace")
    if _deterministic_image_prompt_review_structure_errors(report_text):
        return False
    if _deterministic_image_prompt_review_binding_errors(run_dir, report_text):
        return False
    try:
        blocking_hard_findings = int(
            _image_prompt_story_review_scalar(report_text, "blocking_hard_findings")
        )
        unresolved_entries = int(
            _image_prompt_story_review_scalar(report_text, "unresolved_entries")
        )
    except ValueError:
        return False
    if blocking_hard_findings <= 0 or blocking_hard_findings != len(details):
        return False

    canonical_entry_tokens = [
        _canonical_deterministic_image_prompt_selector(entry_id)
        for entry_id in entry_ids
    ]
    if len(set(canonical_entry_tokens)) != len(canonical_entry_tokens):
        return False
    canonical_entry_token_set = set(canonical_entry_tokens)
    detail_tokens = {
        _canonical_deterministic_image_prompt_selector(detail.get("selector"))
        for detail in details
    }
    if not detail_tokens or not detail_tokens.issubset(canonical_entry_token_set):
        return False
    return unresolved_entries == len(detail_tokens)


def _refresh_deterministic_image_prompt_review_if_stale(run_dir: Path) -> None:
    report_path = run_dir / "image_prompt_story_review.md"
    if _deterministic_image_prompt_review_sources_are_current(run_dir):
        report_text = report_path.read_text(encoding="utf-8", errors="replace")
        if (
            _image_prompt_story_review_scalar(report_text, "review_format_version")
            == "deterministic_image_prompt_review_v2"
            and not _deterministic_image_prompt_review_binding_errors(
                run_dir,
                report_text,
            )
        ):
            return
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "review-image-prompt-story-consistency.py"),
            "--manifest",
            str(run_dir / "video_manifest.md"),
            "--story",
            str(run_dir / "story.md"),
            "--script",
            str(run_dir / "script.md"),
            "--out",
            str(run_dir / "image_prompt_story_review.md"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    refreshed_text = (
        report_path.read_text(encoding="utf-8", errors="replace")
        if report_path.is_file()
        else ""
    )
    if (
        result.returncode != 0
        or not _deterministic_image_prompt_review_sources_are_current(run_dir)
        or _image_prompt_story_review_scalar(refreshed_text, "review_format_version")
        != "deterministic_image_prompt_review_v2"
        or _deterministic_image_prompt_review_binding_errors(run_dir, refreshed_text)
    ):
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(detail or "deterministic image prompt review refresh failed")


def _prepare_image_prompt_request_revision_for_review(
    run_dir: Path,
    *,
    provider_ready: bool = True,
) -> str:
    """Prepare the exact draft or provider-ready revision for semantic review."""

    snapshot_path = run_dir / "image_generation_request_snapshot.json"
    try:
        draft_snapshot = load_request_snapshot(
            snapshot_path,
            run_dir=run_dir,
            verify_references=False,
        )
        if not provider_ready:
            _refresh_deterministic_image_prompt_review_if_stale(run_dir)
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    "review.image_prompt.request_freeze.status": "draft",
                    "review.image_prompt.request_freeze.semantic_input_mode": "deferred_references",
                    "review.image_prompt.request_freeze.review_candidate_revision": draft_snapshot.request_revision,
                },
            )
            return draft_snapshot.request_revision
        state = parse_state_file(run_dir / "state.txt")
        is_frozen = state.get("review.image_prompt.request_freeze.status") == "frozen"
        provider_snapshot = bind_request_snapshot_references(
            draft_snapshot,
            run_dir=run_dir,
            allow_existing_hash_changes=not is_frozen,
        )
        if provider_snapshot.request_revision != draft_snapshot.request_revision:
            if is_frozen:
                raise ImageRequestSnapshotError(
                    "frozen image request revision cannot rebind reference bytes"
                )
            write_request_snapshot_atomic(
                snapshot_path,
                provider_snapshot,
                run_dir=run_dir,
            )
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    "review.image_prompt.request_freeze.status": "draft",
                    "review.image_prompt.request_freeze.provider_ready_revision": (
                        provider_snapshot.request_revision
                    ),
                    "review.image_prompt.request_freeze.references_bound_at": now_iso(),
                },
            )
    except ImageRequestSnapshotError as exc:
        raise RuntimeError(
            f"ToC run did not reach p650: unresolved image request reference: {exc}"
        ) from exc
    _refresh_deterministic_image_prompt_review_if_stale(run_dir)
    return provider_snapshot.request_revision


def _validate_p650_run_core(
    run_id: str,
    *,
    require_downstream_semantic_reviews: bool,
    require_provider_ready_freeze: bool,
    require_generated_asset_outputs: bool,
) -> None:
    run_dir = safe_run_dir(run_id, ROOT)
    required = [
        "state.txt",
        "research.md",
        "story.md",
        "visual_value.md",
        "script.md",
        "video_manifest.md",
        "asset_generation_requests.md",
        "asset_generation_manifest.md",
        "image_generation_requests.md",
        "image_generation_request_snapshot.json",
        "p000_index.md",
    ]
    missing = [name for name in required if not (run_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"ToC run did not reach p650: missing {', '.join(missing)}")
    too_small = []
    placeholder_files = []
    for name in required:
        text = (run_dir / name).read_text(encoding="utf-8", errors="replace")
        if name != "state.txt" and len(text.strip()) < 80:
            too_small.append(name)
        if name != "state.txt":
            lowered = text.lower()
            if any(marker.lower() in lowered for marker in PLACEHOLDER_MARKERS):
                placeholder_files.append(name)
    if too_small:
        raise RuntimeError(f"ToC run did not reach p650: incomplete artifact content in {', '.join(too_small)}")
    if placeholder_files:
        raise RuntimeError(f"ToC run did not reach p650: placeholder scaffold content in {', '.join(placeholder_files)}")

    manifest_text = (run_dir / "video_manifest.md").read_text(encoding="utf-8", errors="replace")
    if "scenes:" not in manifest_text or "assets:" not in manifest_text:
        raise RuntimeError("ToC run did not reach p650: video_manifest.md is missing scenes/assets")
    manifest_data = yaml.safe_load(_extract_manifest_yaml_text(manifest_text)) or {}
    if not isinstance(manifest_data, dict):
        raise RuntimeError("ToC run did not reach p650: video_manifest.md YAML root must be a mapping")
    cut_issues, required_scene_outputs = _manifest_cut_contract(manifest_data)
    if cut_issues:
        raise RuntimeError(f"ToC run did not reach p650: invalid cut contract {', '.join(cut_issues)}")

    asset_items = load_request_items(run_dir, "asset")
    scene_items = load_request_items(run_dir, "scene")
    if not asset_items:
        raise RuntimeError("ToC run did not reach p650: asset_generation_requests.md has no concrete requests")
    if not scene_items:
        raise RuntimeError("ToC run did not reach p650: image_generation_requests.md has no concrete requests")
    request_outputs = {str(item.output).strip() for item in scene_items if item.output}
    missing_scene_requests = sorted(required_scene_outputs - request_outputs)
    if missing_scene_requests:
        raise RuntimeError(f"ToC run did not reach p650: missing scene cut requests {', '.join(missing_scene_requests)}")
    image_prompt_request_revision = _validate_image_prompt_request_revision(
        run_dir,
        manifest_data,
        require_resolved_references=require_provider_ready_freeze,
        require_compiled_v2=True,
    )
    _validate_semantic_reviews(run_dir, ("research", "story"))
    if require_downstream_semantic_reviews:
        _validate_semantic_reviews(
            run_dir,
            ("scene_set", "scene_detail", "cut_blueprint", "asset_plan", "image_prompt"),
        )
    if require_generated_asset_outputs:
        missing_asset_outputs = [
            str(item.output)
            for item in asset_items
            if item.output and not resolve_run_relative(run_dir, item.output).is_file()
        ]
        if missing_asset_outputs:
            raise RuntimeError(f"ToC run did not reach p650: missing generated asset outputs {', '.join(missing_asset_outputs)}")

    state = parse_state_file(run_dir / "state.txt")
    freeze_status = (state.get("review.image_prompt.request_freeze.status") or "").lower()
    if require_provider_ready_freeze and freeze_status != "frozen":
        raise RuntimeError(
            "ToC run did not reach p650: image prompt request freeze is not frozen"
        )
    if require_provider_ready_freeze and state.get(
        "review.image_prompt.request_freeze.request_revision"
    ) != image_prompt_request_revision:
        raise RuntimeError(
            "ToC run did not reach p650: frozen image prompt request revision is stale"
        )
    if not require_provider_ready_freeze and freeze_status not in {"reviewed_draft", "frozen"}:
        raise RuntimeError(
            "ToC run did not reach p650: image prompt request freeze state is missing"
        )
    if state.get("runtime.scaffold.content_status") == "placeholder":
        raise RuntimeError("ToC run did not reach p650: runtime scaffold content is still placeholder")
    scaffold_keys = [key for key, value in state.items() if key.startswith("artifact.") and value == "scaffold"]
    if scaffold_keys:
        raise RuntimeError(f"ToC run did not reach p650: scaffold artifact states remain {', '.join(scaffold_keys)}")
    missing_slots = [slot for slot in P650_FIXED_SLOTS if not state.get(f"slot.{slot}.status")]
    if missing_slots:
        raise RuntimeError(f"ToC run did not reach p650: missing fixed slot states {', '.join(missing_slots)}")
    incomplete_slots = [
        f"{slot}={state.get(f'slot.{slot}.status')}"
        for slot in P650_FIXED_SLOTS
        if (state.get(f"slot.{slot}.status") or "").lower() not in SLOT_TERMINAL_STATES
        and not (
            not require_provider_ready_freeze
            and slot == "p650"
            and (state.get("slot.p650.status") or "").lower() == "pending"
        )
    ]
    if incomplete_slots:
        raise RuntimeError(f"ToC run did not reach p650: incomplete fixed slot states {', '.join(incomplete_slots)}")
    invalid_approval_slots = [
        slot
        for slot in P650_FIXED_SLOTS
        if (state.get(f"slot.{slot}.status") or "").lower() == "awaiting_approval"
        and slot not in SLOT_AWAITING_APPROVAL_ALLOWED
    ]
    if invalid_approval_slots:
        raise RuntimeError(f"ToC run did not reach p650: invalid awaiting_approval fixed slots {', '.join(invalid_approval_slots)}")


def _validate_p650_run(run_id: str) -> None:
    _validate_p650_run_core(
        run_id,
        require_downstream_semantic_reviews=True,
        require_provider_ready_freeze=True,
        require_generated_asset_outputs=True,
    )


def _validate_materialized_p650_run(run_id: str) -> None:
    _validate_p650_run_core(
        run_id,
        require_downstream_semantic_reviews=True,
        require_provider_ready_freeze=False,
        require_generated_asset_outputs=False,
    )


def _validate_frontend_create_run(run_id: str, *, strict_visual_quality: bool = True) -> None:
    _validate_p650_run(run_id)
    run_dir = safe_run_dir(run_id, ROOT)
    _validate_semantic_reviews(
        run_dir,
        ("research", "story", "scene_set", "scene_detail", "cut_blueprint", "asset_plan", "image_prompt"),
    )
    _validate_generated_outputs(run_dir, "asset")
    _validate_generated_outputs(run_dir, "scene")
    if strict_visual_quality:
        _validate_p680_visual_quality(run_dir)
    state = parse_state_file(run_dir / "state.txt")
    missing_slots = [slot for slot in P680_FIXED_SLOTS if not state.get(f"slot.{slot}.status")]
    if missing_slots:
        raise RuntimeError(f"ToC run did not reach p680: missing fixed slot states {', '.join(missing_slots)}")
    incomplete_slots = [
        f"{slot}={state.get(f'slot.{slot}.status')}"
        for slot in P680_FIXED_SLOTS
        if (state.get(f"slot.{slot}.status") or "").lower() not in SLOT_TERMINAL_STATES
    ]
    if incomplete_slots:
        raise RuntimeError(f"ToC run did not reach p680: incomplete fixed slot states {', '.join(incomplete_slots)}")
    invalid_approval_slots = [
        slot
        for slot in P680_FIXED_SLOTS
        if (state.get(f"slot.{slot}.status") or "").lower() == "awaiting_approval"
        and slot not in SLOT_AWAITING_APPROVAL_ALLOWED
    ]
    if invalid_approval_slots:
        raise RuntimeError(f"ToC run did not reach p680: invalid awaiting_approval fixed slots {', '.join(invalid_approval_slots)}")
    expected = {
        "slot.p560.status": "done",
        "slot.p650.status": "done",
        "slot.p660.status": "done",
        "slot.p680.status": "awaiting_approval",
        "review.image.status": "pending",
        "gate.image_review": "required",
    }
    mismatches = [f"{key}={state.get(key)}" for key, value in expected.items() if state.get(key) != value]
    if mismatches:
        raise RuntimeError(f"frontend image review handoff incomplete: {', '.join(mismatches)}")


def _validate_image_prompt_semantic_review(run_dir: Path) -> None:
    result = check_semantic_review(run_dir, "image_prompt")
    if not result.passed:
        raise RuntimeError("image prompt semantic review incomplete: " + "; ".join(result.errors))


def _validate_semantic_reviews(run_dir: Path, stages: Iterable[str]) -> None:
    errors: list[str] = []
    for stage in stages:
        # The generic semantic report is the canonical review artifact.  The
        # legacy image-prompt judgment may coexist during migration, but it
        # must never mask a pending or failed canonical report.
        result = check_semantic_review(run_dir, stage)
        if not result.passed:
            errors.append(f"{stage}: {'; '.join(result.errors)}")
    if errors:
        raise RuntimeError("semantic review incomplete: " + " | ".join(errors))


def _cleanup_unscaffolded_run(run_id: str) -> None:
    try:
        run_dir = safe_run_dir(run_id, ROOT)
    except Exception:
        return
    if (run_dir / "state.txt").exists() or (run_dir / "video_manifest.md").exists():
        return
    shutil.rmtree(run_dir, ignore_errors=True)


def _write_cli_process_logs(run_dir: Path, log_name: str, stdout: bytes, stderr: bytes) -> None:
    log_dir = run_dir / "logs" / log_name
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "stdout.log").write_text(stdout.decode("utf-8", errors="replace"), encoding="utf-8")
    (log_dir / "stderr.log").write_text(stderr.decode("utf-8", errors="replace"), encoding="utf-8")


def _ensure_cli_run_dir(run_id: str) -> Path:
    if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
        raise ValueError("invalid run_id")
    base = output_root(ROOT).resolve()
    run_dir = (base / run_id).resolve()
    if base not in run_dir.parents and run_dir != base:
        raise ValueError("run_id escapes output root")
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


async def _run_toc_run_helper(*, topic: str, run_id: str) -> str:
    run_dir = _ensure_cli_run_dir(run_id)
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(ROOT / "scripts" / "toc-run.py"),
        topic,
        "--dry-run",
        "--review-policy",
        "drafts",
        "--run-dir",
        f"output/{run_id}",
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=1800)
    except asyncio.TimeoutError:
        proc.kill()
        stdout, stderr = await proc.communicate()
        _write_cli_process_logs(run_dir, "toc_run_cli", stdout, stderr)
        raise
    _write_cli_process_logs(run_dir, "toc_run_cli", stdout, stderr)
    if proc.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip() or stdout.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"toc-run exited with status {proc.returncode}")
    return stdout.decode("utf-8", errors="replace").strip()


async def _run_toc_immersive_frontend_cli_helper(
    *,
    topic: str,
    source: str | None = None,
    run_id: str,
    stop_target: str = "p680",
    target_duration_seconds: int = 300,
    materialize_only: bool = False,
) -> str:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "toc-immersive-frontend-run.py"),
        "--topic",
        topic,
        "--source",
        (source or "").strip() or topic,
        "--run-dir",
        f"output/{run_id}",
        "--target-duration-seconds",
        str(target_duration_seconds),
        "--stop-target",
        stop_target,
    ]
    if materialize_only:
        cmd.append("--materialize-only")
    env = dict(os.environ)
    env.setdefault("CODEX_HOME", str(Path.home() / ".codex"))
    run_dir = safe_run_dir(run_id, ROOT)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(ROOT),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=FRONTEND_CREATE_HELPER_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        stdout, stderr = await proc.communicate()
        _write_cli_process_logs(run_dir, "frontend_create_cli", stdout, stderr)
        raise
    _write_cli_process_logs(run_dir, "frontend_create_cli", stdout, stderr)
    if proc.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip() or stdout.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"toc-immersive-frontend-run exited with status {proc.returncode}")
    return stdout.decode("utf-8", errors="replace").strip()


def _is_unsupported_method_error(exc: CodexAppServerError) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "method not found",
            "unknown method",
            "unsupported method",
            "no such method",
        )
    )


def _is_skill_configuration_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "codex skill not found",
            "skill is not visible",
            "skill path mismatch",
            "skill is disabled",
        )
    )


async def _run_toc_skill_helper(*, topic: str, source: str | None = None, run_id: str, stop_target: str = "p680") -> None:
    if app_server_disabled():
        raise RuntimeError("Codex app-server is disabled")
    skill_path = _toc_immersive_skill_path()
    if not skill_path.is_file():
        raise RuntimeError(f"Codex skill not found: {skill_path}")
    run_dir = safe_run_dir(run_id, ROOT)
    client = create_codex_app_server_client(cwd=ROOT)
    skill_text = _toc_immersive_command(topic=topic, source=source, run_id=run_id, stop_target=stop_target)
    try:
        await client.start()
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="skill_start",
            status="started",
            item_id="toc-immersive-runner",
            request={"topic": topic, "stopTarget": stop_target, "skillPath": str(skill_path.relative_to(ROOT))},
        )
        try:
            skills = await client.list_skills(cwd=ROOT, force_reload=True)
        except CodexAppServerError as exc:
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="skill_list",
                status="failed" if not _is_unsupported_method_error(exc) else "unsupported",
                item_id="toc-immersive-runner",
                request={"forceReload": True},
                error=str(exc),
            )
            if not _is_unsupported_method_error(exc):
                raise
        else:
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="skill_list",
                status="completed",
                item_id="toc-immersive-runner",
                request={"forceReload": True},
                response={"skillCount": len(skills), "matched": any(skill.get("name") == "toc-immersive-runner" for skill in skills)},
            )
            matching = [skill for skill in skills if skill.get("name") == "toc-immersive-runner"]
            if not matching:
                raise RuntimeError("Codex skill is not visible to app-server: toc-immersive-runner")
            matching_path = [skill for skill in matching if _skill_matches_path(skill, skill_path)]
            if matching_path:
                matching = matching_path
            elif any(skill.get("path") or skill.get("sourcePath") or skill.get("skillPath") for skill in matching):
                raise RuntimeError(f"Codex skill path mismatch: expected {skill_path}")
            if not any(skill.get("enabled", True) for skill in matching):
                raise RuntimeError("Codex skill is disabled: toc-immersive-runner")
        transcript = await client.run_skill(
            text=skill_text,
            skill_path=skill_path,
            cwd=ROOT,
            timeout_seconds=int(FRONTEND_CREATE_HELPER_TIMEOUT_SECONDS),
        )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="skill_run",
            status="completed",
            item_id="toc-immersive-runner",
            request={"textLength": len(skill_text), "skillPath": str(skill_path.relative_to(ROOT)), "stopTarget": stop_target},
            transcript=transcript,
        )
        if not _stop_target_contract_reached(run_id, stop_target):
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="skill_contract_fallback",
                status="started",
                item_id="toc-immersive-runner",
                request={"stopTarget": stop_target, "reason": "skill_completed_without_stop_target_contract"},
            )
            stdout = await _run_toc_immersive_frontend_cli_helper(
                topic=topic,
                source=source,
                run_id=run_id,
                stop_target=stop_target,
            )
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="skill_contract_fallback",
                status="completed",
                item_id="toc-immersive-runner",
                request={"stopTarget": stop_target},
                response={"stdout": stdout[-2000:]},
            )
    except Exception as exc:
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="skill_run",
            status="failed",
            item_id="toc-immersive-runner",
            request={"textLength": len(skill_text), "skillPath": str(skill_path.relative_to(ROOT)), "stopTarget": stop_target},
            error=str(exc),
        )
        if _is_skill_configuration_error(exc):
            raise
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="skill_contract_fallback",
            status="started",
            item_id="toc-immersive-runner",
            request={"stopTarget": stop_target, "reason": f"skill_error:{type(exc).__name__}"},
        )
        stdout = await _run_toc_immersive_frontend_cli_helper(
            topic=topic,
            source=source,
            run_id=run_id,
            stop_target=stop_target,
        )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="skill_contract_fallback",
            status="completed",
            item_id="toc-immersive-runner",
            request={"stopTarget": stop_target},
            response={"stdout": stdout[-2000:]},
        )
    finally:
        await client.stop()


def _stop_target_contract_reached(run_id: str, stop_target: str) -> bool:
    try:
        if stop_target == "p650":
            _validate_p650_run(run_id)
        elif stop_target == "p680":
            _validate_frontend_create_run(run_id, strict_visual_quality=False)
        else:
            raise ValueError("stop_target must be p650 or p680")
    except Exception:
        return False
    return True


async def _run_toc_skill_helper_until_stop_target(
    *,
    topic: str,
    source: str | None = None,
    run_id: str,
    stop_target: str = "p680",
) -> None:
    task = asyncio.create_task(_run_toc_skill_helper(topic=topic, source=source, run_id=run_id, stop_target=stop_target))
    if stop_target == "p680":
        await task
        return
    try:
        while True:
            done, _pending = await asyncio.wait({task}, timeout=CREATE_SKILL_STOP_POLL_SECONDS)
            if task in done:
                await task
                return
            if _stop_target_contract_reached(run_id, stop_target):
                task.cancel()
                with suppress(asyncio.CancelledError, CodexAppServerError, asyncio.TimeoutError):
                    await asyncio.wait_for(task, timeout=CREATE_SKILL_CANCEL_TIMEOUT_SECONDS)
                run_dir = safe_run_dir(run_id, ROOT)
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        "runtime.app_server_skill.stop_target": stop_target,
                        "runtime.app_server_skill.stop_detected": "true",
                    },
                )
                return
    except Exception:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError, CodexAppServerError, asyncio.TimeoutError):
                await asyncio.wait_for(task, timeout=CREATE_SKILL_CANCEL_TIMEOUT_SECONDS)
        raise


async def _run_helper_command(*args: str, timeout: int = 1800) -> str:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        *args,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    if proc.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip() or stdout.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"{Path(args[0]).name} exited with status {proc.returncode}")
    return stdout.decode("utf-8", errors="replace").strip()


async def _set_slot(run_id: str, slot: str, status: str, note: str) -> None:
    await _run_helper_command(
        str(ROOT / "scripts" / "toc-state.py"),
        "set-slot",
        "--run-dir",
        f"output/{run_id}",
        "--slot",
        slot,
        "--status",
        status,
        "--note",
        note,
        timeout=60,
    )


async def _rebuild_run_index(run_id: str) -> None:
    await _run_helper_command(
        str(ROOT / "scripts" / "build-run-index.py"),
        "--run-dir",
        f"output/{run_id}",
        timeout=120,
    )


async def _materialize_scene_requests(run_id: str) -> None:
    await _run_helper_command(
        str(ROOT / "scripts" / "generate-assets-from-manifest.py"),
        "--manifest",
        f"output/{run_id}/video_manifest.md",
        "--base-dir",
        f"output/{run_id}",
        "--materialize-request-files-only",
        "--skip-videos",
        "--skip-audio",
        "--skip-image-prompt-review",
        timeout=300,
    )


def _now_stamp() -> str:
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns()}"


def _model_dump(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _validate_run_relative_image_path(run_dir: Path, value: str | None, *, must_exist: bool = False) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    if any(char in raw for char in "\r\n`"):
        raise ValueError("image paths must be markdown-safe")
    normalized = Path(raw)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("image paths must be run-relative and must not contain '..'")
    if not normalized.parts or normalized.parts[0] != "assets":
        raise ValueError("image paths must be under assets/")
    target = resolve_run_relative(run_dir, raw)
    assets_root = (run_dir / "assets").resolve()
    if assets_root not in target.resolve().parents and target.resolve() != assets_root:
        raise ValueError("image paths must stay under assets/")
    require_image_file(target)
    if must_exist and not target.is_file():
        raise ValueError(f"image path not found: {raw}")
    return raw


def _validate_run_relative_asset_video_path(run_dir: Path, value: str) -> str:
    if any(char in value for char in "\r\n`"):
        raise ValueError("video output must be markdown-safe")
    normalized = Path(value)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("video output must be run-relative and must not contain '..'")
    if not normalized.parts or normalized.parts[0] != "assets":
        raise ValueError("video output must be under assets/")
    if normalized.suffix.lower() != ".mp4":
        raise ValueError("video output must be an mp4 file")
    target = resolve_run_relative(run_dir, value)
    assets_root = (run_dir / "assets").resolve()
    if assets_root not in target.resolve().parents:
        raise ValueError("video output must stay under assets/")
    return value


def _validate_run_relative_video_path(run_dir: Path, value: str, *, must_exist: bool = False) -> str:
    if any(char in value for char in "\r\n`"):
        raise ValueError("video paths must be markdown-safe")
    normalized = Path(value)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("video paths must be run-relative and must not contain '..'")
    if not normalized.parts or normalized.parts[0] != "assets":
        raise ValueError("video paths must be under assets/")
    if normalized.suffix.lower() != ".mp4":
        raise ValueError("video paths must be mp4 files")
    target = resolve_run_relative(run_dir, value)
    assets_root = (run_dir / "assets").resolve()
    resolved = target.resolve()
    if assets_root not in resolved.parents and resolved != assets_root:
        raise ValueError("video paths must stay under assets/")
    if must_exist and not target.is_file():
        raise ValueError(f"video path not found: {value}")
    return value


def _validate_run_relative_audio_path(run_dir: Path, value: str | None, *, must_exist: bool = False) -> str | None:
    raw = (value or "").strip()
    if not raw:
        if must_exist:
            raise ValueError("audio path is required")
        return None
    if any(char in raw for char in "\r\n`"):
        raise ValueError("audio paths must be markdown-safe")
    normalized = Path(raw)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("audio paths must be run-relative and must not contain '..'")
    if not normalized.parts or normalized.parts[0] != "assets":
        raise ValueError("audio paths must be under assets/")
    if normalized.suffix.lower() not in {".mp3", ".wav", ".m4a", ".aac", ".ogg"}:
        raise ValueError("audio paths must be audio files")
    target = resolve_run_relative(run_dir, raw)
    assets_root = (run_dir / "assets").resolve()
    resolved = target.resolve()
    if assets_root not in resolved.parents and resolved != assets_root:
        raise ValueError("audio paths must stay under assets/")
    if must_exist and not target.is_file():
        raise ValueError(f"audio path not found: {raw}")
    return raw


def _validate_run_relative_render_output(run_dir: Path, value: str) -> str:
    raw = value.strip()
    if any(char in raw for char in "\r\n`"):
        raise ValueError("render output must be markdown-safe")
    normalized = Path(raw)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("render output must be run-relative and must not contain '..'")
    if normalized.suffix.lower() != ".mp4":
        raise ValueError("render output must be an mp4 file")
    target = resolve_run_relative(run_dir, raw)
    resolved = target.resolve()
    run_root = run_dir.resolve()
    if resolved != run_root and run_root not in resolved.parents:
        raise ValueError("render output must stay inside the run directory")
    return raw


def _safe_artifact_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_") or "item"


VIDEO_CANDIDATE_REVISION_SCHEMA = "video_candidate_revision_v1"
VIDEO_CANDIDATE_PROVENANCE_KEY = "_toc_candidate_revision"


def _video_candidate_revision_provenance(
    *,
    item_id: str,
    request_section_sha256: str,
    source_digest: str,
) -> dict[str, str]:
    request_digest = request_section_sha256.strip().lower()
    design_digest = source_digest.strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", request_digest) is None:
        raise ValueError("approved video request section hash is invalid")
    if re.fullmatch(r"[0-9a-f]{64}", design_digest) is None:
        raise ValueError("approved video prompt source digest is invalid")
    revision_id = sha256_canonical_json(
        {
            "schema_version": VIDEO_CANDIDATE_REVISION_SCHEMA,
            "item_id": item_id,
            "request_section_sha256": request_digest,
            "source_digest": design_digest,
        }
    )
    return {
        "schema_version": VIDEO_CANDIDATE_REVISION_SCHEMA,
        "item_id": item_id,
        "request_section_sha256": request_digest,
        "source_digest": design_digest,
        "revision_id": revision_id,
    }


def _video_candidate_provenance_from_request(
    request: VideoGenerateItem,
) -> dict[str, str]:
    raw = _dict_value(
        _dict_value(request.provider_execution_options).get(
            VIDEO_CANDIDATE_PROVENANCE_KEY
        )
    )
    expected = _video_candidate_revision_provenance(
        item_id=request.item_id,
        request_section_sha256=str(raw.get("request_section_sha256") or ""),
        source_digest=str(raw.get("source_digest") or ""),
    )
    if any(str(raw.get(field) or "") != value for field, value in expected.items()):
        raise ValueError(
            "materialized video candidate revision provenance is missing or invalid"
        )
    return expected


def _current_approved_video_candidate_provenance(
    run_dir: Path,
    item_id: str,
) -> dict[str, str] | None:
    """Resolve the one candidate namespace bound to the current item approval."""

    try:
        binding = _reviewed_video_request_binding(run_dir, item_id)
        _manifest_path, _original_text, data = _read_manifest_data(run_dir)
        target = _video_target_by_item_id(data, item_id)
        if target is None:
            return None
        generation = _dict_value(
            _dict_value(target.get("cut")).get("video_generation")
        )
        payload = _dict_value(generation.get("api_prompt_payload"))
        source_digest = str(payload.get("source_digest") or "")
        prompt_sha256 = str(payload.get("sha256") or "")
        if (
            binding.get("source_digest") != source_digest
            or binding.get("prompt_sha256") != prompt_sha256
        ):
            return None
        state_path = run_dir / "state.txt"
        state = parse_state_file(state_path) if state_path.is_file() else {}
        prefix = _video_prompt_approval_state_prefix(item_id)
        expected_state = {
            "status": "approved",
            "request_section_sha256": binding["request_section_sha256"],
            "prompt_sha256": prompt_sha256,
            "source_digest": source_digest,
        }
        if any(
            str(state.get(f"{prefix}.{field}") or "") != expected
            for field, expected in expected_state.items()
        ):
            return None
        return _video_candidate_revision_provenance(
            item_id=item_id,
            request_section_sha256=binding["request_section_sha256"],
            source_digest=source_digest,
        )
    except (FileNotFoundError, TypeError, ValueError):
        return None


def _video_candidate_dir(
    run_dir: Path,
    item_id: str,
    revision_id: str,
) -> Path:
    if re.fullmatch(r"[0-9a-f]{64}", revision_id) is None:
        raise ValueError("invalid video candidate revision id")
    return (
        run_dir
        / "assets"
        / "test"
        / "video_gen_candidates"
        / _safe_artifact_id(item_id)
        / revision_id
    )


def _video_candidate_path(
    run_dir: Path,
    item_id: str,
    revision_id: str,
    index: int,
) -> Path:
    return _video_candidate_dir(
        run_dir, item_id, revision_id
    ) / f"candidate_{index:02d}.mp4"


def _probe_media_duration_seconds(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not path.is_file():
        return None
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        return None
    try:
        duration = float(completed.stdout.strip())
    except ValueError:
        return None
    return duration if duration > 0 else None


def _write_silence_audio(path: Path, duration_seconds: float) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found. Please install ffmpeg to create silent narration.")
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            f"{duration_seconds:.3f}",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _effective_narration_delivery(narration: dict[str, Any]) -> dict[str, Any]:
    from toc.providers.elevenlabs import (
        DEFAULT_ELEVENLABS_LANGUAGE_CODE,
        DEFAULT_ELEVENLABS_VOICE_ID,
        parse_pronunciation_dictionary_locators,
    )

    load_env_files(repo_root=ROOT)
    alias_raw = str(
        narration.get("pronunciation_alias_file")
        or os.environ.get("TOC_TTS_PRONUNCIATION_ALIAS_FILE")
        or ROOT / "config" / "tts-pronunciation-aliases.tsv"
    ).strip()
    alias_path = Path(alias_raw).expanduser()
    if not alias_path.is_absolute():
        alias_path = ROOT / alias_path
    alias_sha256 = ""
    if alias_path.is_file():
        alias_sha256 = "sha256:" + hashlib.sha256(alias_path.read_bytes()).hexdigest()
    try:
        alias_source = alias_path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        alias_source = f"external:{alias_path.name}"
    raw_locators = narration.get("pronunciation_dictionary_locators")
    if raw_locators is None or raw_locators == "":
        raw_locators = os.environ.get("ELEVENLABS_PRONUNCIATION_DICTIONARY_LOCATORS")
    locators = [dict(value) for value in parse_pronunciation_dictionary_locators(raw_locators)]
    public = {
        "voice_id": str(narration.get("voice_id") or os.environ.get("ELEVENLABS_VOICE_ID") or DEFAULT_ELEVENLABS_VOICE_ID),
        "model_id": str(narration.get("model_id") or os.environ.get("ELEVENLABS_MODEL_ID") or "eleven_v3"),
        "voice_settings": _dict_value(narration.get("voice_settings")),
        "output_format": str(narration.get("output_format") or os.environ.get("ELEVENLABS_OUTPUT_FORMAT") or "mp3_44100_128"),
        "language_code": str(
            narration.get("language_code")
            or os.environ.get("ELEVENLABS_LANGUAGE_CODE")
            or DEFAULT_ELEVENLABS_LANGUAGE_CODE
        ),
        "pronunciation_dictionary_locators": locators,
        "pronunciation_alias_source": alias_source,
        "pronunciation_alias_sha256": alias_sha256,
    }
    return {
        **public,
        "pronunciation_alias_path": str(alias_path),
        "effective_delivery_hash": _full_json_hash(public),
    }


def _generate_elevenlabs_audio(path: Path, text: str, request: NarrationGenerateItem) -> None:
    if not text.strip():
        raise ValueError("narration text is required for elevenlabs")
    from toc.providers.elevenlabs import ElevenLabsClient, ElevenLabsConfig

    load_env_files(repo_root=ROOT)
    config = ElevenLabsConfig.from_env(
        voice_id=request.voice_id,
        model_id=request.model_id,
        output_format=request.output_format,
        language_code=request.language_code,
        pronunciation_dictionary_locators=request.pronunciation_dictionary_locators,
    )
    client = ElevenLabsClient(config)
    alias_file = request.pronunciation_alias_path or str(ROOT / "config" / "tts-pronunciation-aliases.tsv")
    aliases = load_pronunciation_aliases(alias_file)
    prepared = prepare_elevenlabs_tts_text(text, pronunciation_aliases=aliases)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        client.tts(
            text=prepared.text,
            voice_id=request.voice_id,
            model_id=request.model_id,
            output_format=request.output_format,
            language_code=request.language_code,
            pronunciation_dictionary_locators=request.pronunciation_dictionary_locators,
            voice_settings=request.voice_settings or None,
            previous_text=request.previous_text,
            next_text=request.next_text,
        )
    )


def _generate_macos_say_audio(path: Path, text: str) -> None:
    say = shutil.which("say")
    ffmpeg = shutil.which("ffmpeg")
    if not say or not ffmpeg:
        raise RuntimeError("macOS say and ffmpeg are required for macos_say narration")
    if not text.strip():
        raise ValueError("narration text is required for macos_say")
    path.parent.mkdir(parents=True, exist_ok=True)
    aiff_path = path.with_suffix(".aiff")
    try:
        subprocess.run([say, "-o", str(aiff_path), text], check=True, capture_output=True, text=True, timeout=180)
        subprocess.run(
            [ffmpeg, "-hide_banner", "-y", "-i", str(aiff_path), "-c:a", "libmp3lame", "-q:a", "2", str(path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )
    finally:
        aiff_path.unlink(missing_ok=True)


def _parse_optional_json_env(*names: str) -> dict[str, Any] | None:
    for name in names:
        raw = os.environ.get(name)
        if not raw or not raw.strip():
            continue
        loaded = json.loads(raw)
        if not isinstance(loaded, dict):
            raise ValueError(f"{name} must be a JSON object")
        return loaded
    return None


def _server_video_execution_options(
    *,
    tool: str,
    has_first_frame: bool,
    has_reference_images: bool = False,
) -> dict[str, Any]:
    load_env_files(repo_root=ROOT)
    if tool in {"kling_3_0", "kling_3_0_omni"}:
        is_omni = tool == "kling_3_0_omni"
        model = (
            os.environ.get("KLING_OMNI_VIDEO_MODEL", "kling-3.0-omni")
            if is_omni
            else os.environ.get("KLING_VIDEO_MODEL", "kling-3.0")
        )
        extra_payload = (
            _parse_optional_json_env("KLING_OMNI_EXTRA_JSON", "KLING_EXTRA_JSON")
            if is_omni
            else _parse_optional_json_env("KLING_EXTRA_JSON")
        )
        return {
            "backend": "kling",
            "model": str(model),
            "extra_payload": extra_payload or {},
        }
    if tool == "seedance":
        if has_first_frame or has_reference_images:
            model = (
                os.environ.get("ARK_SEEDANCE_I2V_MODEL")
                or os.environ.get("SEEDANCE_I2V_MODEL")
                or "seedance-1-0-lite-i2v-250428"
            )
        else:
            model = (
                os.environ.get("ARK_SEEDANCE_T2V_MODEL")
                or os.environ.get("SEEDANCE_T2V_MODEL")
                or "seedance-1-0-pro-250528"
            )
        return {
            "backend": "ark",
            "model": str(model),
            "generate_audio": False,
            "watermark": False,
            "extra_payload": _parse_optional_json_env("ARK_EXTRA_JSON") or {},
        }
    return {"backend": tool}


def _video_generation_provider_context(
    video_generation: dict[str, Any],
    *,
    input_mode: str = "",
) -> tuple[str, str, str]:
    tool = str(video_generation.get("tool") or "kling_3_0").strip()
    payload = _dict_value(video_generation.get("api_prompt_payload"))
    binding = _dict_value(payload.get("provider_request_binding"))
    execution_options = _dict_value(binding.get("execution_options"))
    model = str(execution_options.get("model") or "").strip()
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
    model: str = "",
    input_mode: str = "",
    duration_seconds: int,
    reference_count: int,
    validate_reference_count: bool = True,
) -> list[str]:
    capabilities = resolve_video_provider_capabilities(
        tool=tool,
        model=model,
        input_mode=input_mode,
    )
    issues: list[str] = []
    if not capabilities.supported:
        issues.append(
            f"{label}: {capabilities.unsupported_reason or 'provider capability contract is unsupported'}"
        )
        return issues
    if not (
        capabilities.duration_min_seconds
        <= int(duration_seconds)
        <= capabilities.duration_max_seconds
    ):
        issues.append(
            f"{label}: duration {int(duration_seconds)}s is outside the {tool} "
            f"{input_mode or 'default'} limit "
            f"{capabilities.duration_min_seconds}-{capabilities.duration_max_seconds}s"
        )
    if validate_reference_count and not (
        capabilities.reference_images_min
        <= int(reference_count)
        <= capabilities.reference_images_max
    ):
        issues.append(
            f"{label}: reference image count {int(reference_count)} is outside the {tool} "
            f"{input_mode or 'default'} limit "
            f"{capabilities.reference_images_min}-{capabilities.reference_images_max}"
        )
    return issues


def _video_request_input_mode(request: VideoGenerateItem) -> str:
    if request.first_reference and request.last_reference:
        return "first_last_frame"
    if request.first_reference:
        return "image_to_video"
    if request.references:
        return "reference_to_video"
    return "text_to_video"


def _assert_video_request_within_provider_capabilities(
    request: VideoGenerateItem,
    *,
    label: str | None = None,
) -> None:
    execution_options = _dict_value(request.provider_execution_options)
    issues = _video_provider_capability_issues(
        label=label or request.item_id,
        tool=request.tool,
        model=str(execution_options.get("model") or "").strip(),
        input_mode=_video_request_input_mode(request),
        duration_seconds=request.duration_seconds,
        reference_count=len(request.references),
    )
    if issues:
        raise ValueError("; ".join(issues))


def _assert_video_auxiliary_references_supported(
    *,
    tool: str,
    references: Iterable[str],
) -> None:
    normalized = [str(value).strip() for value in references if str(value).strip()]
    if normalized and tool in {"kling_3_0", "kling_3_0_omni"}:
        raise ValueError(
            f"{tool} adapter cannot encode auxiliary reference images; "
            "use first/last frame only or select seedance"
        )


def _video_poll_every_seconds() -> float:
    try:
        return float(os.environ.get("VIDEO_POLL_EVERY_SECONDS") or os.environ.get("POLL_EVERY_SECONDS") or "5")
    except ValueError:
        return 5.0


def _video_timeout_seconds() -> float:
    try:
        return float(os.environ.get("VIDEO_TIMEOUT_SECONDS") or "900")
    except ValueError:
        return 900.0


def _write_video_generation_debug_log(
    *,
    run_dir: Path,
    item_id: str,
    index: int,
    destination: Path,
    request: VideoGenerateItem,
    provider_result: dict[str, Any] | None = None,
    error: str | None = None,
) -> Path:
    log_dir = run_dir / "logs" / "providers" / "video_gen"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", item_id).strip("_") or "item"
    log_path = log_dir / f"{stamp}_{time.time_ns()}_{safe_id}_candidate_{index:02d}.json"
    payload = {
        "itemId": item_id,
        "candidateIndex": index,
        "destination": destination.relative_to(run_dir).as_posix(),
        "tool": request.tool,
        "quality": request.quality,
        "aspectRatio": request.aspect_ratio,
        "durationSeconds": request.duration_seconds,
        "firstReference": request.first_reference,
        "lastReference": request.last_reference,
        "references": request.references,
        "prompt": request.prompt,
        "negativePrompt": request.negative_prompt,
        "promptPolicyVersion": request.prompt_policy_version,
        "promptCompilerVersion": request.prompt_compiler_version,
        "promptSha256": request.prompt_sha256 or hashlib.sha256(request.prompt.encode("utf-8")).hexdigest(),
        "promptSourceDigest": request.prompt_source_digest,
        "providerExecutionOptions": request.provider_execution_options,
        "status": "failed" if error else "completed",
        "error": error,
        "provider": provider_result or {},
    }
    payload = _redact_video_provider_log_payload(payload)
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return log_path


_HTTP_URL_IN_LOG_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


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

    def redact_url(match: re.Match[str]) -> str:
        candidate = match.group(0)
        try:
            parsed = urlsplit(candidate)
            hostname = parsed.hostname
            port = parsed.port
        except ValueError:
            return "<redacted-media-url>"
        if parsed.scheme.lower() not in {"http", "https"} or not hostname:
            return candidate
        safe_host = f"[{hostname}]" if ":" in hostname else hostname
        safe_netloc = f"{safe_host}:{port}" if port is not None else safe_host
        return urlunsplit(
            (parsed.scheme.lower(), safe_netloc, parsed.path, "", "")
        )

    return _HTTP_URL_IN_LOG_RE.sub(redact_url, value)


def _generate_kling_video_file(
    *,
    request: VideoGenerateItem,
    input_image: Path | None,
    last_frame_image: Path | None,
    out_path: Path,
) -> dict[str, Any]:
    load_env_files(repo_root=ROOT)
    execution_options = dict(request.provider_execution_options or {})
    model = str(execution_options.get("model") or "").strip()
    if not model:
        raise ValueError("materialized Kling model is missing")
    extra_payload = execution_options.get("extra_payload") or None
    if extra_payload is not None and not isinstance(extra_payload, dict):
        raise ValueError("materialized Kling extra_payload must be an object")
    client = KlingClient(KlingConfig.from_env(video_model=model))
    submit = client.start_video_generation(
        prompt=request.prompt,
        duration_seconds=int(request.duration_seconds),
        aspect_ratio=request.aspect_ratio,
        resolution=request.quality,
        input_image=input_image,
        last_frame_image=last_frame_image,
        negative_prompt=(request.negative_prompt or "").strip() or None,
        model=model,
        extra_payload=extra_payload,
        timeout_seconds=180.0,
    )
    operation_id = client.extract_operation_id(submit)
    operation = client.poll_operation(
        operation_id_or_url=operation_id,
        poll_every_seconds=_video_poll_every_seconds(),
        timeout_seconds=_video_timeout_seconds(),
    )
    if client.is_failed_operation(operation):
        raise RuntimeError(f"Kling operation failed: {json.dumps(operation, ensure_ascii=False)}")
    video_uri = client.extract_video_uri(operation)
    client.download_to_file(uri=video_uri, out_path=out_path)
    return {"provider": "kling", "model": model, "submit": submit, "operation": operation}


def _generate_seedance_video_file(
    *,
    request: VideoGenerateItem,
    input_image: Path | None,
    last_frame_image: Path | None,
    reference_images: list[Path],
    out_path: Path,
) -> dict[str, Any]:
    load_env_files(repo_root=ROOT)
    execution_options = dict(request.provider_execution_options or {})
    model = str(execution_options.get("model") or "").strip()
    if not model:
        raise ValueError("materialized Seedance model is missing")
    extra_payload = execution_options.get("extra_payload") or None
    if extra_payload is not None and not isinstance(extra_payload, dict):
        raise ValueError("materialized Seedance extra_payload must be an object")
    client = SeedanceClient(SeedanceConfig.from_env())
    payload = client.build_video_payload(
        model=str(model),
        prompt=request.prompt,
        duration_seconds=int(request.duration_seconds),
        ratio=request.aspect_ratio,
        resolution=request.quality,
        input_image=input_image,
        last_frame_image=last_frame_image,
        reference_images=reference_images,
        generate_audio=bool(execution_options.get("generate_audio", False)),
        watermark=bool(execution_options.get("watermark", False)),
        extra_payload=extra_payload,
    )
    submit = client.create_task(payload=payload)
    task_id = client.extract_task_id(submit)
    task = client.poll_task(
        task_id=task_id,
        poll_every_seconds=_video_poll_every_seconds(),
        timeout_seconds=_video_timeout_seconds(),
    )
    if client.is_failed_task(task):
        raise RuntimeError(f"Seedance task failed: {json.dumps(task, ensure_ascii=False)}")
    video_url = client.extract_video_url(task)
    client.download_to_file(url=video_url, out_path=out_path)
    return {"provider": "seedance", "model": str(model), "submit": submit, "task": task}


def _generate_video_file_blocking(
    *,
    run_dir: Path,
    request: VideoGenerateItem,
    index: int,
    destination: Path,
    input_image: Path | None,
    last_frame_image: Path | None,
    reference_images: list[Path],
) -> dict[str, Any]:
    _assert_video_request_within_provider_capabilities(request)
    _assert_video_auxiliary_references_supported(
        tool=request.tool,
        references=request.references,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    snapshot_dir: Path | None = None
    try:
        (
            snapshot_dir,
            provider_input_image,
            provider_last_frame_image,
            provider_reference_images,
        ) = _snapshot_materialized_video_reference_inputs(
            run_dir=run_dir,
            request=request,
            input_image=input_image,
            last_frame_image=last_frame_image,
            reference_images=reference_images,
        )
        if request.tool in {"kling_3_0", "kling_3_0_omni"}:
            provider_result = _generate_kling_video_file(
                request=request,
                input_image=provider_input_image,
                last_frame_image=provider_last_frame_image,
                out_path=destination,
            )
        elif request.tool == "seedance":
            provider_result = _generate_seedance_video_file(
                request=request,
                input_image=provider_input_image,
                last_frame_image=provider_last_frame_image,
                reference_images=provider_reference_images,
                out_path=destination,
            )
        else:
            raise ValueError(f"unsupported video tool: {request.tool}")
    finally:
        if snapshot_dir is not None:
            shutil.rmtree(snapshot_dir, ignore_errors=True)
    if not destination.is_file():
        raise RuntimeError("provider completed without writing a video file")
    debug_log = _write_video_generation_debug_log(
        run_dir=run_dir,
        item_id=request.item_id,
        index=index,
        destination=destination,
        request=request,
        provider_result=provider_result,
    )
    return {
        "index": index,
        "status": "completed",
        "path": destination.relative_to(run_dir).as_posix(),
        "debugLog": debug_log.relative_to(run_dir).as_posix(),
        "source": request.tool,
    }


def _snapshot_materialized_video_reference_inputs(
    *,
    run_dir: Path,
    request: VideoGenerateItem,
    input_image: Path | None,
    last_frame_image: Path | None,
    reference_images: list[Path],
) -> tuple[Path | None, Path | None, Path | None, list[Path]]:
    """Copy approved reference bytes before the provider reads them.

    Validation and provider submission are separated by an async boundary.  A
    path-only binding would therefore permit the file at that path to change
    after approval.  The provider receives private copies whose bytes are
    checked against the materialized content hashes.
    """

    raw_inputs: list[tuple[str, Path | None]] = [
        (str(request.first_reference or "").strip(), input_image),
        (str(request.last_reference or "").strip(), last_frame_image),
        *[
            (str(reference or "").strip(), path)
            for reference, path in zip(
                request.references,
                reference_images,
                strict=False,
            )
        ],
    ]
    present_inputs = [(reference, path) for reference, path in raw_inputs if path]
    if not present_inputs:
        return None, None, None, []
    if len(reference_images) != len(request.references):
        raise ValueError("materialized video reference list does not match resolved inputs")

    expected_by_path = _dict_value(
        _dict_value(request.provider_execution_options).get(
            "reference_content_sha256"
        )
    )
    snapshot_dir = (
        run_dir
        / "scratch"
        / "video_request_inputs"
        / f"{time.time_ns()}_{uuid.uuid4().hex}"
    )
    snapshot_dir.mkdir(parents=True, exist_ok=False)
    copied_by_source: dict[Path, Path] = {}
    try:
        for index, (reference, source) in enumerate(present_inputs, start=1):
            assert source is not None
            expected = str(expected_by_path.get(reference) or "").strip()
            if not reference or not expected:
                raise ValueError(
                    "materialized video reference content hash is missing"
                )
            copied = copied_by_source.get(source)
            if copied is None:
                copied = snapshot_dir / f"reference_{index:02d}{source.suffix.lower()}"
                shutil.copyfile(source, copied)
                digest = hashlib.sha256()
                with copied.open("rb") as file:
                    for chunk in iter(lambda: file.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != expected:
                    raise ValueError(
                        "materialized video reference content changed before provider submission"
                    )
                copied_by_source[source] = copied

        copied_input = copied_by_source.get(input_image) if input_image else None
        copied_last = (
            copied_by_source.get(last_frame_image) if last_frame_image else None
        )
        copied_references = [copied_by_source[path] for path in reference_images]
        return snapshot_dir, copied_input, copied_last, copied_references
    except Exception:
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        raise


def _resolve_video_reference_image(run_dir: Path, value: str | None, *, field: str) -> Path | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        _validate_run_relative_image_path(run_dir, raw, must_exist=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field}: {exc}") from exc
    target = resolve_run_relative(run_dir, raw)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"{field} not found: {raw}")
    require_image_file(target)
    return target


async def _generate_video_one(run_dir: Path, req: VideoGenerateItem, index: int) -> dict[str, Any]:
    revision = _video_candidate_provenance_from_request(req)
    input_image = _resolve_video_reference_image(run_dir, req.first_reference, field="first_reference")
    last_frame_image = _resolve_video_reference_image(run_dir, req.last_reference, field="last_reference")
    reference_images = [
        image
        for image in (_resolve_video_reference_image(run_dir, ref, field="references") for ref in req.references)
        if image is not None
    ]
    destination = _video_candidate_path(
        run_dir,
        req.item_id,
        revision["revision_id"],
        index,
    )
    async with _video_generation_semaphore:
        try:
            result = await asyncio.to_thread(
                _generate_video_file_blocking,
                run_dir=run_dir,
                request=req,
                index=index,
                destination=destination,
                input_image=input_image,
                last_frame_image=last_frame_image,
                reference_images=reference_images,
            )
            current_revision = _current_approved_video_candidate_provenance(
                run_dir,
                req.item_id,
            )
            if (
                result.get("status") == "completed"
                and (
                    current_revision is None
                    or current_revision.get("revision_id")
                    != revision["revision_id"]
                )
            ):
                stale_path = result.get("path")
                return {
                    **result,
                    "status": "stale",
                    "path": None,
                    "stalePath": stale_path,
                    "error": (
                        "video candidate completed after its approved prompt "
                        "revision became stale"
                    ),
                }
            return result
        except (HttpError, TimeoutError, ValueError, RuntimeError, OSError) as exc:
            debug_log = _write_video_generation_debug_log(
                run_dir=run_dir,
                item_id=req.item_id,
                index=index,
                destination=destination,
                request=req,
                error=str(exc),
            )
            return {
                "index": index,
                "status": "failed",
                "path": None,
                "error": str(exc),
                "debugLog": debug_log.relative_to(run_dir).as_posix(),
                "source": req.tool,
            }


async def _generate_video_candidates(run_dir: Path, req: VideoGenerateItem) -> dict[str, Any]:
    _assert_video_request_within_provider_capabilities(req)
    min_duration = _narration_min_duration_seconds(run_dir, req.item_id)
    if min_duration is not None and req.duration_seconds < math.ceil(min_duration):
        raise ValueError(
            "materialized video duration is shorter than the approved narration; "
            "create video prompts again before generation"
        )
    candidates = await asyncio.gather(*(_generate_video_one(run_dir, req, index) for index in range(1, req.candidate_count + 1)))
    return {
        "itemId": req.item_id,
        "durationSeconds": req.duration_seconds,
        "minDurationSeconds": min_duration,
        "candidates": candidates,
    }


def _validate_video_request_reference_paths(run_dir: Path, req: VideoGenerateItem) -> None:
    for field, values in (
        ("first_reference", [req.first_reference]),
        ("last_reference", [req.last_reference]),
        ("references", req.references),
    ):
        for value in values:
            if not value:
                continue
            try:
                _validate_run_relative_image_path(run_dir, value, must_exist=True)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"{field}: {exc}") from exc


def _video_prompt_contract_version_mismatches(payload: dict[str, Any]) -> list[str]:
    video_prompt_ir = payload.get("video_prompt_ir")
    ir_schema_version = (
        str(video_prompt_ir.get("schema_version") or "")
        if isinstance(video_prompt_ir, dict)
        else ""
    )
    actual = {
        "policy_version": str(payload.get("policy_version") or ""),
        "compiler_version": str(payload.get("compiler_version") or ""),
        "projection_registry_version": str(
            payload.get("projection_registry_version") or ""
        ),
        "video_prompt_ir.schema_version": ir_schema_version,
    }
    expected = {
        "policy_version": VIDEO_API_PROMPT_POLICY_VERSION,
        "compiler_version": VIDEO_PROMPT_COMPILER_VERSION,
        "projection_registry_version": (
            VIDEO_PROMPT_PROJECTION_REGISTRY_VERSION
        ),
        "video_prompt_ir.schema_version": VIDEO_PROMPT_IR_SCHEMA_VERSION,
    }
    return [
        field
        for field, expected_value in expected.items()
        if actual[field] != expected_value
    ]


def _assert_current_video_prompt_contract_versions(
    *,
    selector: str,
    payload: dict[str, Any],
) -> None:
    mismatches = _video_prompt_contract_version_mismatches(payload)
    if mismatches:
        raise ValueError(
            "materialized video prompt is missing or uses obsolete contract versions: "
            + ", ".join(f"{selector}.{field}" for field in mismatches)
            + "; create video prompts before generation"
        )


def _materialized_video_generate_item(
    *,
    run_dir: Path,
    request: VideoGenerateItem,
) -> VideoGenerateItem:
    """Bind a generation request to the exact reviewed provider prompt.

    The browser submits the editable authoring source for drift detection.  The
    provider only receives the compiled prompt persisted by p800 materialization.
    """

    _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    target = _video_target_by_item_id(data, request.item_id)
    if target is None:
        raise ValueError(f"materialized video prompt target not found: {request.item_id}")
    node = target["cut"]
    video_generation = _dict_value(node.get("video_generation"))
    payload = _dict_value(video_generation.get("api_prompt_payload"))
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError(
            "materialized video prompt is missing or uses an obsolete policy; "
            "create video prompts before generation"
        )
    _assert_current_video_prompt_contract_versions(
        selector=request.item_id,
        payload=payload,
    )

    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if str(payload.get("sha256") or "") != prompt_sha256:
        raise ValueError("materialized video prompt hash does not match its provider prompt")

    authoring_source = str(
        video_generation.get("prompt_authoring_source")
        or video_generation.get("source_motion_prompt")
        or ""
    ).strip()
    submitted_prompt = request.prompt.strip()
    accepted_request_prompts = {prompt}
    if authoring_source:
        accepted_request_prompts.add(authoring_source)
    if submitted_prompt not in accepted_request_prompts:
        raise ValueError(
            "request prompt does not match the materialized video prompt source; "
            "materialize the current edit before generation"
        )

    first_reference = str(
        video_generation.get("first_frame") or video_generation.get("input_image") or ""
    ).strip()
    last_reference = str(video_generation.get("last_frame") or "").strip()
    references = [
        str(value).strip()
        for value in _list_value(video_generation.get("references"))
        if str(value).strip()
    ]
    quality = str(video_generation.get("quality") or "1080p").strip()
    aspect_ratio = str(video_generation.get("aspect_ratio") or "16:9").strip()
    duration_seconds = int(video_generation.get("duration_seconds") or 8)
    tool = str(video_generation.get("tool") or "kling_3_0").strip()
    _assert_video_auxiliary_references_supported(
        tool=tool,
        references=references,
    )

    mismatches: list[str] = []
    for field, submitted, materialized in (
        ("first_reference", (request.first_reference or "").strip(), first_reference),
        ("last_reference", (request.last_reference or "").strip(), last_reference),
        ("quality", request.quality, quality),
        ("aspect_ratio", request.aspect_ratio, aspect_ratio),
        ("duration_seconds", request.duration_seconds, duration_seconds),
        ("tool", request.tool, tool),
    ):
        if submitted != materialized:
            mismatches.append(field)
    if request.references != references:
        mismatches.append("references")
    if mismatches:
        raise ValueError(
            "request settings do not match the materialized video prompt: "
            + ", ".join(mismatches)
        )

    current_item = FrontendReviewItem(
        item_id=request.item_id,
        kind="scene",
        video_prompt=authoring_source,
        video_quality=quality,
        video_aspect_ratio=aspect_ratio,
        video_duration_seconds=duration_seconds,
        video_first_reference=first_reference or None,
        video_last_reference=last_reference or None,
        video_references=references,
        video_tool=tool,
    )
    try:
        _target, current_payload = _compile_frontend_video_prompt_payload(
            data=data,
            item=current_item,
            run_dir=run_dir,
        )
    except ValueError as exc:
        raise ValueError(
            "materialized video prompt is stale for the current design; "
            "create video prompts again before generation"
        ) from exc
    _assert_current_video_prompt_contract_versions(
        selector=request.item_id,
        payload=current_payload,
    )
    _assert_video_prompt_quality_allows_provider_execution(
        selector=request.item_id,
        payload=current_payload,
    )
    _assert_video_prompt_quality_allows_provider_execution(
        selector=request.item_id,
        payload=payload,
    )
    for field in ("prompt", "negative_prompt", "sha256", "source_digest"):
        if str(current_payload.get(field) or "") != str(payload.get(field) or ""):
            raise ValueError(
                "materialized video prompt is stale for the current design; "
                "create video prompts again before generation"
            )
    if current_payload.get("provider_request_binding") != payload.get(
        "provider_request_binding"
    ):
        raise ValueError(
            "materialized video provider request binding is stale or changed; "
            "create video prompts again before generation"
        )
    if current_payload != payload:
        raise ValueError(
            "materialized video prompt payload is stale or changed; "
            "create video prompts again before generation"
        )

    narration_duration = _narration_min_duration_seconds(run_dir, request.item_id)
    if narration_duration is not None and duration_seconds < math.ceil(narration_duration):
        raise ValueError(
            "materialized video duration is shorter than the approved narration; "
            "create video prompts again before generation"
        )

    reviewed = _reviewed_video_request_binding(run_dir, request.item_id)
    negative_prompt = str(payload.get("negative_prompt") or "")
    reviewed_expected = {
        "tool": tool,
        "output": str(video_generation.get("output") or "").strip(),
        "duration_seconds": str(duration_seconds),
        "quality": quality,
        "aspect_ratio": aspect_ratio,
        "first_frame": first_reference,
        "last_frame": last_reference,
        "prompt_policy_version": VIDEO_API_PROMPT_POLICY_VERSION,
        "compiler_version": VIDEO_PROMPT_COMPILER_VERSION,
        "source_digest": str(payload.get("source_digest") or ""),
        "prompt_sha256": prompt_sha256,
        "negative_prompt_sha256": hashlib.sha256(
            negative_prompt.encode("utf-8")
        ).hexdigest(),
        "references_digest": sha256_canonical_json(references),
        "prompt": prompt,
        "negative_prompt": negative_prompt,
    }
    reviewed_mismatches = [
        field
        for field, expected in reviewed_expected.items()
        if str(reviewed.get(field) or "") != str(expected)
    ]
    if reviewed_mismatches:
        raise ValueError(
            "reviewed video generation request is stale or changed: "
            + ", ".join(reviewed_mismatches)
        )

    state_path = run_dir / "state.txt"
    state = parse_state_file(state_path) if state_path.is_file() else {}
    approval_prefix = _video_prompt_approval_state_prefix(request.item_id)
    approval_expected = {
        "status": "approved",
        "request_section_sha256": reviewed["request_section_sha256"],
        "prompt_sha256": prompt_sha256,
        "source_digest": str(payload.get("source_digest") or ""),
    }
    approval_mismatches = [
        field
        for field, expected in approval_expected.items()
        if str(state.get(f"{approval_prefix}.{field}") or "") != expected
    ]
    if approval_mismatches:
        raise ValueError(
            "reviewed video generation request is not approved for generation: "
            + ", ".join(approval_mismatches)
        )

    provider_request_binding = _dict_value(
        payload.get("provider_request_binding")
    )
    provider_execution_options = _dict_value(
        provider_request_binding.get("execution_options")
    )
    if not provider_execution_options:
        raise ValueError(
            "materialized provider execution options are missing; create video prompts again"
        )
    provider_execution_options = {
        **provider_execution_options,
        VIDEO_CANDIDATE_PROVENANCE_KEY: _video_candidate_revision_provenance(
            item_id=request.item_id,
            request_section_sha256=reviewed["request_section_sha256"],
            source_digest=str(payload.get("source_digest") or ""),
        ),
    }

    materialized_request = request.model_copy(
        update={
            "prompt": prompt,
            "first_reference": first_reference or None,
            "last_reference": last_reference or None,
            "references": references,
            "negative_prompt": negative_prompt or None,
            "quality": quality,
            "aspect_ratio": aspect_ratio,
            "duration_seconds": duration_seconds,
            "tool": tool,
            "prompt_policy_version": VIDEO_API_PROMPT_POLICY_VERSION,
            "prompt_compiler_version": VIDEO_PROMPT_COMPILER_VERSION,
            "prompt_sha256": prompt_sha256,
            "prompt_source_digest": str(payload.get("source_digest") or ""),
            "provider_execution_options": provider_execution_options,
        }
    )
    _assert_video_request_within_provider_capabilities(
        materialized_request,
        label=f"{request.item_id} materialized provider request",
    )

    return materialized_request


def _require_markdown_scalar(value: str, *, field: str) -> str:
    text = value.strip()
    if not text or any(char in text for char in "\r\n`"):
        raise ValueError(f"{field} must be a single markdown-safe value")
    return text


def _require_no_code_fence(value: str | None, *, field: str) -> str:
    text = (value or "").strip()
    if "```" in text:
        raise ValueError(f"{field} must not contain markdown code fences")
    return text


def _validate_review_item_paths(run_dir: Path, item: FrontendReviewItem, *, strict_video_refs: bool = False) -> None:
    for value in [item.output, item.selected_candidate_path, item.existing_image]:
        _validate_run_relative_image_path(run_dir, value, must_exist=False)
    for ref in item.references:
        _validate_run_relative_image_path(run_dir, ref, must_exist=False)
    for ref in [item.video_first_reference, item.video_last_reference, *item.video_references]:
        _validate_run_relative_image_path(run_dir, ref, must_exist=strict_video_refs and bool(ref))
    _validate_run_relative_audio_path(run_dir, item.narration_output, must_exist=False)
    _validate_run_relative_audio_path(run_dir, item.render_narration_path, must_exist=False)
    if item.render_video_path:
        _validate_run_relative_video_path(run_dir, item.render_video_path, must_exist=False)


def _validate_candidate_matches_output(run_dir: Path, candidate: Path, output: str) -> None:
    expected_item_id: str | None = None
    for kind in ("asset", "scene"):
        try:
            items = load_request_items(run_dir, kind)
        except (FileNotFoundError, ValueError):
            continue
        for item in items:
            if item.output == output:
                expected_item_id = item.id
                break
        if expected_item_id:
            break
    if expected_item_id is None:
        return
    expected_dir = candidate_path(run_dir, expected_item_id, 1).parent.name
    actual_dir = candidate.parent.name
    if actual_dir != expected_dir:
        raise ValueError(
            f"candidate item mismatch: {candidate.relative_to(run_dir).as_posix()} cannot be inserted into {output}; "
            f"expected candidate directory {expected_dir}"
        )


def _frontend_review_dir(run_dir: Path) -> Path:
    return run_dir / "logs" / "review" / "frontend"


def _write_frontend_review_draft(
    *,
    run_id: str,
    run_dir: Path,
    kind: str,
    note: str | None,
    items: list[FrontendReviewItem],
    state_status: str = "draft",
    strict_video_refs: bool = False,
) -> Path:
    for item in items:
        _validate_review_item_paths(run_dir, item, strict_video_refs=strict_video_refs)
    review_dir = _frontend_review_dir(run_dir)
    review_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    payload = {
        "runId": run_id,
        "kind": kind,
        "savedAt": stamp,
        "note": note or "",
        "items": [_model_dump(item) for item in items],
    }
    path = review_dir / f"{stamp}_{kind}_draft.json"
    latest = review_dir / f"{kind}_draft_latest.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    latest.write_text(text, encoding="utf-8")
    rel_path = path.relative_to(run_dir).as_posix()
    latest_rel_path = latest.relative_to(run_dir).as_posix()
    append_state_snapshot(
        run_dir / "state.txt",
        {
            f"review.frontend.{kind}.status": state_status,
            f"review.frontend.{kind}.draft": rel_path,
            f"review.frontend.{kind}.latest": latest_rel_path,
            f"review.frontend.{kind}.saved_at": stamp,
        },
    )
    return path


def _backup_run_file(run_dir: Path, rel_path: str, *, label: str) -> Path | None:
    source = run_dir / rel_path
    if not source.exists():
        return None
    backup_dir = _frontend_review_dir(run_dir) / "backups" / _now_stamp()
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"{label}_{source.name}"
    shutil.copy2(source, backup)
    return backup


def _read_manifest_data(run_dir: Path) -> tuple[Path, str, dict[str, Any]]:
    manifest_path = run_dir / "video_manifest.md"
    if not manifest_path.exists():
        raise FileNotFoundError("video_manifest.md not found")
    original = manifest_path.read_text(encoding="utf-8")
    data = yaml.safe_load(_extract_manifest_yaml_text(original)) or {}
    if not isinstance(data, dict):
        raise ValueError("video_manifest.md YAML root must be a mapping")
    return manifest_path, original, data


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_text(path: Path, content: str) -> None:
    _atomic_write_bytes(path, content.encode("utf-8"))


def _capture_file_transaction(paths: Iterable[Path]) -> dict[Path, bytes | None]:
    return {
        path: path.read_bytes() if path.is_file() else None
        for path in dict.fromkeys(paths)
    }


def _restore_file_transaction(snapshot: dict[Path, bytes | None]) -> None:
    for path, previous_content in snapshot.items():
        if previous_content is None:
            path.unlink(missing_ok=True)
        else:
            _atomic_write_bytes(path, previous_content)


def _write_manifest_data(manifest_path: Path, original_text: str, data: dict[str, Any]) -> None:
    yaml_text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    if "```yaml" not in original_text:
        _atomic_write_text(manifest_path, f"```yaml\n{yaml_text}```\n")
        return
    start = original_text.find("```yaml")
    yaml_start = original_text.find("\n", start)
    if yaml_start == -1:
        _atomic_write_text(manifest_path, f"```yaml\n{yaml_text}```\n")
        return
    yaml_start += 1
    yaml_end = original_text.find("```", yaml_start)
    if yaml_end == -1:
        _atomic_write_text(manifest_path, original_text[:yaml_start] + yaml_text)
        return
    _atomic_write_text(manifest_path, original_text[:yaml_start] + yaml_text + original_text[yaml_end:])


def _full_json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_script_data(run_dir: Path) -> tuple[Path, str, dict[str, Any]]:
    script_path = run_dir / "script.md"
    if not script_path.exists():
        raise FileNotFoundError("script.md not found")
    original, data = load_structured_document(script_path)
    if not data:
        raise ValueError("script.md must contain structured YAML before frontend narration authoring")
    return script_path, original, data


def _script_cut_for_manifest_target(script_data: dict[str, Any], target: dict[str, Any]) -> dict[str, Any] | None:
    target_scene_id = normalize_dotted_id(target.get("scene_id"))
    target_cut = _dict_value(target.get("cut"))
    target_cut_id = normalize_dotted_id(target_cut.get("cut_id"))
    if not target_cut_id and target.get("cut_index") is not None:
        target_cut_id = str(int(target["cut_index"]) + 1)
    for scene in _list_value(script_data.get("scenes")):
        if not isinstance(scene, dict) or normalize_dotted_id(scene.get("scene_id")) != target_scene_id:
            continue
        cuts = scene.get("cuts")
        if not isinstance(cuts, list) or not cuts:
            return scene if target.get("cut_index") is None else None
        for index, cut in enumerate(cuts):
            if not isinstance(cut, dict):
                continue
            cut_id = normalize_dotted_id(cut.get("cut_id")) or str(index + 1)
            if cut_id == target_cut_id:
                return cut
    return None


def _invalidate_narration_run_approval(data: dict[str, Any], *, reason: str) -> None:
    workflow = _dict_value(data.get("narration_workflow"))
    final_review = _dict_value(workflow.get("final_audio_review"))
    if final_review.get("status") == "approved":
        final_review["status"] = "stale"
    else:
        final_review["status"] = "pending"
    final_review["approved_audio_set_hash"] = ""
    final_review["invalidated_at"] = now_iso()
    final_review["invalidation_reason"] = reason
    workflow["schema_version"] = "narration_run_workflow_v1"
    workflow["final_audio_review"] = final_review
    data["narration_workflow"] = workflow


def _narration_summary(target: dict[str, Any]) -> dict[str, Any]:
    node = _dict_value(target.get("cut"))
    narration = _dict_value(_dict_value(node.get("audio")).get("narration"))
    revision = _dict_value(narration.get("revision"))
    generation = _dict_value(narration.get("generation"))
    audio_review = _dict_value(narration.get("audio_review"))
    candidates = [candidate for candidate in _list_value(narration.get("candidates")) if isinstance(candidate, dict)]
    current_candidate = next(
        (
            candidate
            for candidate in reversed(candidates)
            if str(candidate.get("candidate_id") or "") == str(generation.get("candidate_id") or "")
        ),
        None,
    )
    approved_candidate_id = str(audio_review.get("approved_candidate_id") or "")
    approved_candidate = next(
        (
            candidate
            for candidate in candidates
            if str(candidate.get("candidate_id") or "") == approved_candidate_id
        ),
        None,
    )
    return {
        "itemId": str(target.get("selector") or ""),
        "authoringStatus": str(narration.get("authoring_status") or ""),
        "status": str(narration.get("status") or ""),
        "text": str(narration.get("text") or ""),
        "ttsText": str(narration.get("tts_text") or ""),
        "tool": str(narration.get("tool") or "elevenlabs"),
        "output": str(narration.get("output") or "") or None,
        "revision": revision,
        "generation": generation,
        "audioReview": audio_review,
        "candidate": current_candidate,
        "approvedCandidate": approved_candidate,
    }


def _narration_grounding_values(target: dict[str, Any]) -> dict[str, str]:
    node = _dict_value(target.get("cut"))
    return {
        "script_selector": str(target.get("selector") or ""),
        "contract_hash": _full_json_hash(_dict_value(node.get("cut_contract"))),
        "visual_grounding_hash": _full_json_hash(_dict_value(node.get("image_generation"))),
    }


def _narration_grounding_is_current(target: dict[str, Any], narration: dict[str, Any]) -> bool:
    binding = _dict_value(narration.get("source_binding"))
    expected = _narration_grounding_values(target)
    return all(str(binding.get(key) or "") == value for key, value in expected.items())


def _require_script_narration_source_current(
    script_cut: dict[str, Any], narration: dict[str, Any], request: NarrationTextSaveRequest
) -> None:
    script_text = str(script_cut.get("narration") or "").strip()
    script_tts_text = resolve_script_cut_tts_text(script_cut)
    binding = _dict_value(narration.get("source_binding"))
    revision = _dict_value(narration.get("revision"))
    tool = str(narration.get("tool") or request.tool or "elevenlabs").strip().lower()
    delivery = {
        "elevenlabs_prompt": _dict_value(narration.get("elevenlabs_prompt")),
        "model_id": str(narration.get("model_id") or "").strip(),
        "voice_id": str(narration.get("voice_id") or "").strip(),
        "voice_settings": _dict_value(narration.get("voice_settings")),
    }
    script_text_hash = narration_text_hash(script_text, tool=tool)
    script_tts_hash = narration_tts_hash(script_tts_text, tool=tool, delivery=delivery)
    bound_text_hash = str(binding.get("semantic_hash") or revision.get("text_hash") or "")
    bound_tts_hash = str(binding.get("tts_request_hash") or revision.get("tts_hash") or "")
    has_bound_source = bool(str(binding.get("script_selector") or "").strip())
    if has_bound_source and (script_text_hash != bound_text_hash or script_tts_hash != bound_tts_hash):
        raise NarrationRevisionConflict(
            "script.md narration changed outside the frontend revision; sync or reload it before saving"
        )
    if not has_bound_source and (script_text or script_tts_text):
        requested_text = request.text.strip()
        requested_tts = (request.tts_text or request.text).strip()
        if requested_text != script_text or requested_tts != script_tts_text:
            raise NarrationRevisionConflict(
                "script.md already contains a newer canonical narration; sync it before frontend editing"
            )
    authoring = _dict_value(script_cut.get("narration_authoring"))
    metadata_text_hash = str(authoring.get("semantic_hash") or "")
    metadata_tts_hash = str(authoring.get("tts_request_hash") or "")
    if metadata_text_hash and metadata_text_hash != script_text_hash:
        raise NarrationRevisionConflict("script.md narration_authoring semantic hash does not match its text")
    if metadata_tts_hash and metadata_tts_hash != script_tts_hash:
        raise NarrationRevisionConflict("script.md narration_authoring TTS hash does not match its text")


def _invalidate_narration_for_grounding_rebind(
    narration: dict[str, Any], *, at: str, bump_revision: bool
) -> None:
    had_candidate = False
    for candidate in _list_value(narration.get("candidates")):
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("status") or "") not in {"failed", "rejected"}:
            candidate["status"] = "stale"
            had_candidate = True
    had_audio = bool(str(narration.get("output") or "").strip()) or had_candidate
    narration["output"] = ""
    narration["status"] = "stale" if had_audio else "draft"
    narration["generation"] = {
        "status": "stale" if had_audio else "missing",
        "candidate_id": "",
        "generated_from_tts_hash": "",
    }
    narration["audio_review"] = {
        "status": "pending",
        "approved_candidate_id": "",
        "approved_revision": 0,
        "approved_text_hash": "",
        "approved_tts_hash": "",
        "approved_at": "",
    }
    review = _dict_value(narration.get("review"))
    review.update(
        {
            "status": "pending",
            "agent_review_ok": None,
            "agent_review_reason_keys": [],
            "agent_review_reason_messages": [],
            "human_review_ok": False,
            "semantic": {"status": "stale", "reviewed_text_hash": ""},
            "delivery": {"status": "stale", "reviewed_tts_hash": ""},
            "arc": {"status": "stale", "narration_set_hash": ""},
        }
    )
    narration["review"] = review
    revision = _dict_value(narration.get("revision"))
    if bump_revision:
        revision["number"] = int(revision.get("number") or 0) + 1
    revision["source"] = "frontend_grounding_rebind"
    revision["updated_at"] = at
    narration["revision"] = revision


def _append_narration_reopened_state(run_dir: Path, *, phase: str, note: str) -> None:
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "status": "P720",
            "runtime.stage": "narration_frontend_revision_workflow",
            "runtime.narration.phase": phase,
            "slot.p710.status": "done",
            "slot.p720.status": "in_progress",
            "slot.p720.note": note,
            "slot.p730.status": "in_progress" if phase == "tts_preview" else "pending",
            "slot.p740.status": "pending",
            "slot.p750.status": "pending",
            "stage.narration.status": "in_progress",
            "review.narration.status": "pending",
            "gate.narration_review": "required",
        },
    )


def _append_narration_preview_state(
    run_dir: Path,
    *,
    note: str,
    runtime_stage: str = "narration_audio_candidate_preview",
) -> None:
    """Record an alternate TTS preview without reopening current text/audio approvals."""

    current = parse_state_file(run_dir / "state.txt")
    if str(current.get("slot.p750.status") or "").strip().lower() == "done":
        updates = {
            "runtime.narration.preview_stage": runtime_stage,
            "runtime.narration.preview_note": note,
        }
    else:
        updates = {
            "runtime.stage": runtime_stage,
            "runtime.narration.phase": "tts_preview",
            "runtime.narration.preview_note": note,
            "slot.p730.status": "in_progress",
            "slot.p730.note": note,
        }
    append_state_snapshot(
        run_dir / "state.txt",
        updates,
    )


def _save_frontend_narration_text(run_dir: Path, request: NarrationTextSaveRequest) -> dict[str, Any]:
    manifest_path, manifest_original, manifest_data = _read_manifest_data(run_dir)
    target = _target_by_item_id(manifest_data, request.item_id)
    if target is None:
        raise ValueError(f"video manifest target not found: {request.item_id}")
    script_path, script_original, script_data = _read_script_data(run_dir)
    script_cut = _script_cut_for_manifest_target(script_data, target)
    if script_cut is None:
        raise ValueError(f"script.md narration target not found: {target['selector']}")

    node = _dict_value(target.get("cut"))
    audio = _dict_value(node.get("audio"))
    narration = _dict_value(audio.get("narration"))
    _require_script_narration_source_current(script_cut, narration, request)
    updated_at = now_iso()
    changed = apply_authoring_update(
        narration,
        text=request.text,
        tts_text=request.tts_text,
        tool=request.tool,
        authoring_status=request.authoring_status,
        source="frontend",
        expected_revision=request.expected_revision,
        now=updated_at,
    )
    grounding_current = _narration_grounding_is_current(target, narration)
    if not changed and grounding_current:
        return _narration_summary(target)
    if not grounding_current:
        _invalidate_narration_for_grounding_rebind(
            narration,
            at=updated_at,
            bump_revision=not changed,
        )
    revision = _dict_value(narration.get("revision"))
    selector = str(target.get("selector") or request.item_id)
    grounding = _narration_grounding_values(target)
    narration["source_binding"] = {
        **grounding,
        "semantic_revision": int(revision.get("text_revision") or 0),
        "semantic_hash": str(revision.get("text_hash") or ""),
        "tts_revision": int(revision.get("tts_revision") or 0),
        "tts_request_hash": str(revision.get("tts_hash") or ""),
        "synced_at": updated_at,
    }
    audio["narration"] = narration
    node["audio"] = audio

    script_cut["narration"] = request.text.strip()
    script_cut["tts_text"] = (request.tts_text or request.text).strip()
    script_cut["narration_authoring"] = {
        "schema_version": "narration_authoring_v1",
        "status": request.authoring_status,
        "semantic_revision": int(revision.get("text_revision") or 0),
        "semantic_hash": str(revision.get("text_hash") or ""),
        "tts_revision": int(revision.get("tts_revision") or 0),
        "tts_request_hash": str(revision.get("tts_hash") or ""),
        "source": "frontend",
        "updated_at": str(revision.get("updated_at") or updated_at),
        "updated_by": "frontend",
    }
    human_review = _dict_value(script_cut.get("human_review"))
    if request.authoring_status in {"human_locked", "silent"}:
        human_review.update(
            {
                "status": "approved",
                "approved_narration": request.text.strip(),
                "approved_tts_text": (request.tts_text or request.text).strip(),
                "approved_at": now_iso(),
            }
        )
    else:
        human_review.update(
            {
                "status": "pending",
                "approved_narration": "",
                "approved_tts_text": "",
                "approved_at": "",
            }
        )
    script_cut["human_review"] = human_review
    reconcile_audio_story_text(script_data)
    for projection_key in ("audio_story_plan", "narration_spans"):
        if projection_key in script_data:
            manifest_data[projection_key] = deepcopy(script_data[projection_key])
    refs_by_selector = narration_span_refs(script_data)
    for manifest_target in _manifest_scene_targets(manifest_data):
        manifest_node = _dict_value(manifest_target.get("cut"))
        manifest_audio = _dict_value(manifest_node.get("audio"))
        manifest_narration = _dict_value(manifest_audio.get("narration"))
        manifest_narration["span_refs"] = deepcopy(
            refs_by_selector.get(str(manifest_target.get("selector") or ""), [])
        )
        manifest_audio["narration"] = manifest_narration
        manifest_node["audio"] = manifest_audio
    reconcile_audio_story_text(manifest_data)
    invalidate_stale_tts_context_audio(manifest_data)
    _invalidate_narration_run_approval(manifest_data, reason=f"narration text saved: {selector}")

    transaction = _capture_file_transaction(
        [
            script_path,
            manifest_path,
            run_dir / "state.txt",
            run_dir / "run_status.json",
            run_dir / "p000_index.md",
        ]
    )
    _backup_run_file(run_dir, "script.md", label="before_frontend_narration_text_save")
    _backup_run_file(run_dir, "video_manifest.md", label="before_frontend_narration_text_save")
    try:
        _write_manifest_data(script_path, script_original, script_data)
        _write_manifest_data(manifest_path, manifest_original, manifest_data)
        if changed or not grounding_current:
            _append_narration_reopened_state(
                run_dir,
                phase="authoring" if request.authoring_status == "draft" else "review",
                note=(
                    "frontend narration text revision saved; downstream audio approval "
                    "invalidated when hashes changed"
                ),
            )
    except Exception:
        _restore_file_transaction(transaction)
        raise
    return _narration_summary(target)


def _is_non_renderable_manifest_node(node: dict[str, Any]) -> bool:
    return is_non_renderable_manifest_node(node)


def _manifest_scene_targets(
    data: dict[str, Any], *, include_non_renderable: bool = False
) -> list[dict[str, Any]]:
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        return []
    targets: list[dict[str, Any]] = []
    for scene_index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        if not include_non_renderable and _is_non_renderable_manifest_node(scene):
            continue
        scene_id = normalize_dotted_id(scene.get("scene_id"))
        if not scene_id:
            continue
        cuts = scene.get("cuts")
        if isinstance(cuts, list) and cuts:
            for cut_index, cut in enumerate(cuts):
                if not isinstance(cut, dict):
                    continue
                if not include_non_renderable and _is_non_renderable_manifest_node(cut):
                    continue
                cut_id = normalize_dotted_id(cut.get("cut_id")) or str(cut_index + 1)
                aliases = selector_aliases(scene_id, cut_id)
                aliases.add(make_scene_cut_selector(scene_id, cut_id))
                targets.append(
                    {
                        "selector": make_scene_cut_selector(scene_id, cut_id),
                        "aliases": aliases,
                        "scene": scene,
                        "scene_id": scene_id,
                        "cuts": cuts,
                        "cut": cut,
                        "cut_index": cut_index,
                        "scene_index": scene_index,
                    }
                )
            continue
        aliases = selector_aliases(scene_id)
        aliases.add(make_scene_cut_selector(scene_id))
        targets.append(
            {
                "selector": make_scene_cut_selector(scene_id),
                "aliases": aliases,
                "scene": scene,
                "scene_id": scene_id,
                "cuts": None,
                "cut": scene,
                "cut_index": None,
                "scene_index": scene_index,
            }
        )
    return targets


def _target_by_item_id(data: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    return next((target for target in _manifest_scene_targets(data) if item_id in target["aliases"]), None)


RENDER_UNIT_VIDEO_INPUT_CONTRACT_VERSION = "render_unit_video_input_v1"


def _render_unit_video_input_contract(node: dict[str, Any]) -> dict[str, Any]:
    """Return immutable provider inputs for a storyboard-backed render unit.

    New manifests persist the explicit contract. The storyboard fallback keeps
    already-created render units protected while they are migrated naturally.
    """

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
    if contract.get("explicit") and contract.get("schema_version") != RENDER_UNIT_VIDEO_INPUT_CONTRACT_VERSION:
        issues.append(
            f"{selector}: unsupported video_input_contract schema_version"
        )
    if not contract.get("explicit"):
        issues.append(
            f"{selector}: storyboard render unit requires an explicit reference-image video_input_contract"
        )
        return issues
    if contract.get("input_mode") != "reference_images":
        issues.append(
            f"{selector}: storyboard video_input_contract input_mode must be reference_images"
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
            f"{selector}: reference-image mode must not combine first_frame/input_image/last_frame "
            "with multimodal references"
        )
    current_references = [
        str(value).strip()
        for value in _list_value(generation.get("references"))
        if str(value).strip()
    ]
    if current_references != required_references:
        issues.append(
            f"{selector}: video_generation references must exactly preserve the ordered required render-unit references"
        )
    return issues


def _manifest_video_targets(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the canonical provider targets used by final rendering.

    A scene with render units is generated exclusively by those units. Exposing
    its source cuts as additional video targets would let the UI purchase clips
    that the final renderer intentionally ignores.
    """

    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        return []
    render_unit_issues = _render_unit_timeline_issues(data)
    if render_unit_issues:
        raise ValueError(
            "invalid render-unit timeline: " + "; ".join(render_unit_issues[:20])
        )
    cut_targets = _manifest_scene_targets(data)
    targets: list[dict[str, Any]] = []
    for scene_index, scene in enumerate(scenes):
        if not isinstance(scene, dict) or _is_non_renderable_manifest_node(scene):
            continue
        scene_id = normalize_dotted_id(scene.get("scene_id"))
        if not scene_id:
            continue
        render_units = [
            unit
            for unit in _list_value(scene.get("render_units"))
            if isinstance(unit, dict) and not _is_non_renderable_manifest_node(unit)
        ]
        if not render_units:
            targets.extend(
                target for target in cut_targets if target.get("scene") is scene
            )
            continue
        for unit_index, unit in enumerate(render_units):
            unit_id = normalize_dotted_id(unit.get("unit_id")) or str(
                unit_index + 1
            )
            selector = f"scene{scene_id}_unit{unit_id}"
            aliases = {
                selector,
                f"{make_scene_cut_selector(scene_id)}_unit{unit_id}",
            }
            targets.append({
                "selector": selector,
                "aliases": aliases,
                "scene": scene,
                "scene_id": scene_id,
                "cuts": render_units,
                "cut": unit,
                "cut_index": unit_index,
                "scene_index": scene_index,
                "is_render_unit": True,
            })
    return targets


def _video_target_by_item_id(
    data: dict[str, Any], item_id: str
) -> dict[str, Any] | None:
    return next(
        (
            target
            for target in _manifest_video_targets(data)
            if item_id in target["aliases"]
        ),
        None,
    )


def _video_contract_for_server_target(target: dict[str, Any]) -> dict[str, Any]:
    node = _dict_value(target.get("cut"))
    explicit = _dict_value(node.get("cut_contract"))
    if not target.get("is_render_unit"):
        return explicit

    scene = _dict_value(target.get("scene"))
    source_cut_ids = [
        normalize_dotted_id(value)
        for value in _list_value(node.get("source_cut_ids"))
    ]
    cuts_by_id: dict[str, dict[str, Any]] = {}
    for index, cut in enumerate(_list_value(scene.get("cuts")), start=1):
        if not isinstance(cut, dict) or _is_non_renderable_manifest_node(cut):
            continue
        cut_id = normalize_dotted_id(cut.get("cut_id")) or str(index)
        cuts_by_id[cut_id] = cut
    source_contracts = [
        _dict_value(cuts_by_id[cut_id].get("cut_contract"))
        for cut_id in source_cut_ids
        if cut_id and cut_id in cuts_by_id
    ]
    return compose_video_render_unit_contract(
        source_contracts,
        unit_contract=explicit or None,
    )


def _video_review_dependencies_for_server_target(
    target: dict[str, Any],
) -> dict[str, Any] | None:
    if not target.get("is_render_unit"):
        return None
    node = _dict_value(target.get("cut"))
    scene = _dict_value(target.get("scene"))
    source_cut_ids = [
        normalize_dotted_id(value)
        for value in _list_value(node.get("source_cut_ids"))
    ]
    cuts_by_id: dict[str, dict[str, Any]] = {}
    for index, cut in enumerate(_list_value(scene.get("cuts")), start=1):
        if not isinstance(cut, dict) or _is_non_renderable_manifest_node(cut):
            continue
        cut_id = normalize_dotted_id(cut.get("cut_id")) or str(index)
        cuts_by_id[cut_id] = cut
    return {
        "render_unit_source_cut_ids": [
            cut_id for cut_id in source_cut_ids if cut_id
        ],
        "render_unit_source_cut_contracts": [
            _dict_value(cuts_by_id[cut_id].get("cut_contract"))
            for cut_id in source_cut_ids
            if cut_id and cut_id in cuts_by_id
        ],
    }


def _first_frame_visual_plan_for_server_target(
    target: dict[str, Any],
) -> dict[str, Any]:
    """Resolve the visual plan for the image that anchors video motion."""

    node = _dict_value(target.get("cut"))
    own_plan = _dict_value(
        _dict_value(node.get("image_generation")).get("first_frame_visual_plan")
    )
    if own_plan:
        return own_plan
    if not target.get("is_render_unit"):
        return {}
    source_cut_ids = [
        normalize_dotted_id(value)
        for value in _list_value(node.get("source_cut_ids"))
    ]
    first_source_id = next((value for value in source_cut_ids if value), None)
    if not first_source_id:
        return {}
    scene = _dict_value(target.get("scene"))
    for index, cut in enumerate(_list_value(scene.get("cuts")), start=1):
        if not isinstance(cut, dict) or _is_non_renderable_manifest_node(cut):
            continue
        cut_id = normalize_dotted_id(cut.get("cut_id")) or str(index)
        if cut_id != first_source_id:
            continue
        source_plan = _dict_value(
            _dict_value(cut.get("image_generation")).get(
                "first_frame_visual_plan"
            )
        )
        return source_plan if source_plan else {}
    return {}


def _apply_v2_visual_plan_patch_and_compile(
    original_plan: dict[str, Any],
    patch: dict[str, Any],
    *,
    character_ids: Iterable[str],
    object_ids: Iterable[str],
    location_ids: Iterable[str],
    references: Iterable[str],
    story_time: str = "",
    scene_time_of_day: str = "",
    review_metadata: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan = deepcopy(original_plan)
    if str(plan.get("schema_version") or "") != "first_frame_visual_plan_v1":
        raise ValueError("compiled_v2_first_frame_visual_plan_v1_required")

    def assign_text(container: dict[str, Any], key: str, patch_key: str) -> None:
        value = str(patch.get(patch_key) or "").strip()
        if value:
            container[key] = value

    temporal = _dict_value(plan.get("temporal_boundary"))
    assign_text(temporal, "event_fact_visible_in_still", "event_fact_visible_in_still")
    plan["temporal_boundary"] = temporal

    subject_binding = _dict_value(plan.get("subject_binding"))
    primary_subject = _dict_value(subject_binding.get("primary_subject"))
    assign_text(primary_subject, "name", "primary_subject_name")
    subject_binding["primary_subject"] = primary_subject
    plan["subject_binding"] = subject_binding

    character_state = _dict_value(plan.get("character_state_gate"))
    for key in ("costume_state", "pose", "gaze"):
        assign_text(character_state, key, key)
    plan["character_state_gate"] = character_state

    composition = _dict_value(plan.get("spatial_composition"))
    for key in ("foreground", "midground", "background"):
        assign_text(composition, key, key)
    plan["spatial_composition"] = composition

    material = _dict_value(plan.get("scene_material_pack"))
    for key in ("light_source", "light_direction", "story_specific_texture"):
        assign_text(material, key, key)
    dominant_materials = patch.get("dominant_materials")
    if isinstance(dominant_materials, list):
        cleaned_materials = [str(value).strip() for value in dominant_materials if str(value).strip()]
        if cleaned_materials:
            material["dominant_materials"] = cleaned_materials
    plan["scene_material_pack"] = material

    payload = compile_image_api_prompt_v2(
        first_frame_visual_plan=plan,
        character_ids=character_ids,
        object_ids=object_ids,
        location_ids=location_ids,
        reference_images=references,
        story_time=story_time,
        scene_time_of_day=scene_time_of_day,
        review_metadata=review_metadata,
    )
    return plan, payload


def _default_narration_output_for_target(target: dict[str, Any]) -> str:
    selector = str(target["selector"])
    return f"assets/audio/{selector}/{selector}_narration.mp3"


def _json_hash(value: Any) -> str:
    text = json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int_value(value: Any, *, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _float_value(value: Any, *, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _list_value(value) if str(item).strip()]


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _cut_narration_contract(node: dict[str, Any]) -> dict[str, Any]:
    cut_contract = _dict_value(node.get("cut_contract"))
    narration = _dict_value(cut_contract.get("narration_contract"))
    if narration:
        return narration
    audio = _dict_value(node.get("audio"))
    narration = _dict_value(audio.get("narration_contract"))
    if narration:
        return narration
    return _dict_value(node.get("narration_contract"))


def _scene_logline(scene: dict[str, Any]) -> str:
    scene_event = _dict_value(scene.get("scene_event"))
    scene_contract = _dict_value(scene.get("scene_contract") or scene.get("contract"))
    return _first_non_empty(
        scene.get("logline"),
        scene.get("title"),
        scene.get("scene_title"),
        scene_event.get("logline"),
        scene_contract.get("screen_question"),
        scene_contract.get("dramatic_job"),
    )


def _cut_summary(node: dict[str, Any]) -> str:
    cut_contract = _dict_value(node.get("cut_contract"))
    scene_contract = _dict_value(node.get("scene_contract"))
    source_event = _dict_value(cut_contract.get("source_event_contract"))
    first_frame = _dict_value(cut_contract.get("first_frame_contract"))
    return _first_non_empty(
        scene_contract.get("visual_beat"),
        scene_contract.get("target_beat"),
        source_event.get("source_event_summary"),
        first_frame.get("event_fact_visible_in_still"),
        node.get("description"),
    )


def _is_silent_role(contract: dict[str, Any]) -> bool:
    role = str(contract.get("role") or "").strip().lower()
    speakable = contract.get("speakable_or_silent")
    return role == "silent" or speakable is False


def _narration_contract_payload(contract: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    cut_contract = _dict_value(node.get("cut_contract"))
    source_event = _dict_value(cut_contract.get("source_event_contract"))
    event_context = _dict_value(cut_contract.get("event_context_for_cut"))
    source_event_ids = _string_list(contract.get("source_event_beat_ids") or source_event.get("source_event_beat_ids"))
    must_cover = _string_list(contract.get("must_cover"))
    if not must_cover:
        must_cover = [item for item in [contract.get("target_function"), event_context.get("scene_event_logline"), _cut_summary(node)] if str(item or "").strip()]
    must_avoid = _string_list(contract.get("must_avoid"))
    forbidden = _string_list(contract.get("forbidden_info_ids") or event_context.get("forbidden_event_changes"))
    return {
        "role": _first_non_empty(contract.get("role"), "emotion"),
        "allowed_info_ids": _string_list(contract.get("allowed_info_ids")),
        "forbidden_info_ids": forbidden,
        "must_cover": must_cover,
        "must_avoid": must_avoid,
        "boundary": _first_non_empty(contract.get("narration_event_boundary"), "same_event_only"),
        "target_function": _first_non_empty(contract.get("target_function"), "映像を説明せず、物語上の意味だけを補う"),
        "source_event_beat_ids": source_event_ids,
        "must_not_advance_to_event_beat_ids": _string_list(contract.get("must_not_advance_to_event_beat_ids")),
        "must_not_explain_visible_action_as_caption": contract.get("must_not_explain_visible_action_as_caption") is not False,
        "done_when": _string_list(contract.get("done_when")) or ["映像の説明ではなく、このcutの感情・因果・余韻を補っている"],
    }


def _elevenlabs_prompt_payload(*, text: str, scene: dict[str, Any], node: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    spoken_context = _first_non_empty(
        _scene_logline(scene),
        _dict_value(_dict_value(node.get("cut_contract")).get("event_context_for_cut")).get("scene_event_logline"),
    )
    role = str(contract.get("role") or "").strip().lower()
    if role in {"emotion", "aftertaste"}:
        voice_tags = ["softly"]
    elif role in {"contrast", "fact"}:
        voice_tags = ["calm"]
    else:
        voice_tags = ["narration"]
    materialized = materialize_elevenlabs_tts_text(
        spoken_context=spoken_context,
        voice_tags=voice_tags,
        spoken_body=text,
    )
    return {
        "spoken_context": spoken_context,
        "voice_tags": voice_tags,
        "spoken_body": text,
        "stability": "creative",
        "materialized": materialized,
    }


def _pending_elevenlabs_prompt_payload(*, scene: dict[str, Any], node: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    payload = _elevenlabs_prompt_payload(text="", scene=scene, node=node, contract=contract)
    return {**payload, "materialized": ""}


def _silence_contract_payload(contract: dict[str, Any], *, confirmed_by_human: bool = False, reason: str | None = None) -> dict[str, Any]:
    silence_reason = _first_non_empty(reason, contract.get("silence_reason"), "このcutは映像だけで意味が成立するため")
    return {
        "intentional": True,
        "confirmed_by_human": bool(confirmed_by_human),
        "kind": "intentional_silence",
        "reason": silence_reason,
    }


def _build_scene_narration_plan(scene: dict[str, Any], targets: list[dict[str, Any]]) -> dict[str, Any]:
    roles: list[dict[str, str]] = []
    for target in targets:
        node = target["cut"]
        contract = _cut_narration_contract(node)
        role = _first_non_empty(contract.get("role"), "emotion")
        roles.append(
            {
                "cut_id": str(target["selector"]),
                "role": role,
                "reason": _first_non_empty(contract.get("target_function"), _cut_summary(node), "scene全体の語りの一部を担当する"),
            }
        )
    role_names = {item["role"] for item in roles}
    if role_names == {"silent"}:
        density = "silent_sparse"
    elif "silent" in role_names or len(roles) <= 2:
        density = "sparse"
    elif len(roles) >= 5:
        density = "dense"
    else:
        density = "balanced"
    first_role = roles[0]["role"] if roles else "setup"
    last_role = roles[-1]["role"] if roles else "aftertaste"
    forbidden: list[str] = []
    for target in targets:
        contract = _cut_narration_contract(target["cut"])
        forbidden.extend(_string_list(contract.get("forbidden_info_ids")))
        forbidden.extend(_string_list(contract.get("must_not_advance_to_event_beat_ids")))
    return {
        "scene_id": str(scene.get("scene_id") or ""),
        "narration_throughline": _first_non_empty(_scene_logline(scene), "scene全体の意味を、映像説明ではなく感情と因果でつなぐ"),
        "narration_density": density,
        "tone_arc": {
            "from": first_role,
            "to": last_role,
        },
        "silence_strategy": "画面で読める行為は説明せず、沈黙が余韻や緊張を作るcutでは無音を許可する",
        "reveal_boundary_summary": " / ".join(dict.fromkeys(forbidden)) if forbidden else "scene_eventとcut_contractのreveal boundaryを超えない",
        "cut_narration_roles": roles,
    }


def _has_existing_narration_review(narration: dict[str, Any]) -> bool:
    if not narration:
        return False
    status = str(narration.get("status") or "").strip().lower()
    review = _dict_value(narration.get("review"))
    review_status = str(review.get("status") or "").strip().lower()
    if status in {"review_pending", "pending", "approved", "audio_ready"}:
        return True
    if review_status in {"pending", "approved", "awaiting_approval"}:
        return True
    meaningful_keys = (
        "text",
        "tts_text",
        "text_draft",
        "output",
        "tool",
        "contract",
        "elevenlabs_prompt",
        "silence_contract",
        "review",
    )
    for key in meaningful_keys:
        value = narration.get(key)
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, list) and value:
            return True
    return False


def _validate_scene_image_outputs_ready(run_dir: Path, data: dict[str, Any]) -> None:
    missing: list[str] = []
    for target in _manifest_scene_targets(data):
        node = target["cut"]
        image_generation = _dict_value(node.get("image_generation"))
        output = str(image_generation.get("output") or "").strip()
        if not output:
            missing.append(f"{target['selector']}:image_generation.output")
            continue
        try:
            _validate_run_relative_image_path(run_dir, output, must_exist=True)
        except ValueError:
            missing.append(f"{target['selector']}:{output}")
            continue
        if not resolve_run_relative(run_dir, output).is_file():
            missing.append(f"{target['selector']}:{output}")
    if missing:
        raise ValueError("narration drafts require image outputs for all scene cuts: " + ", ".join(missing[:20]))


def _write_narration_authoring_report(run_dir: Path, *, updated: list[str], skipped: list[str], replace: bool) -> Path:
    path = run_dir / "narration_authoring_report.md"
    lines = [
        "# Narration Authoring Report",
        "",
        f"- created_at: `{_now_stamp()}`",
        f"- replace: `{str(replace).lower()}`",
        f"- updated_count: `{len(updated)}`",
        f"- skipped_count: `{len(skipped)}`",
        "",
        "## Updated Cuts",
        "",
    ]
    lines.extend(f"- `{item}`" for item in updated) if updated else lines.append("- none")
    lines.extend(["", "## Skipped Cuts", ""])
    lines.extend(f"- `{item}`" for item in skipped) if skipped else lines.append("- none")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def _create_narration_drafts_in_manifest(run_dir: Path, *, replace: bool) -> dict[str, Any]:
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    targets = _manifest_scene_targets(data)
    if not targets:
        raise ValueError("video_manifest.md has no scene cuts")
    if not replace:
        _validate_scene_image_outputs_ready(run_dir, data)
    _backup_run_file(run_dir, "video_manifest.md", label="before_narration_drafts_create")
    targets_by_scene: dict[int, list[dict[str, Any]]] = {}
    for target in targets:
        targets_by_scene.setdefault(int(target["scene_index"]), []).append(target)
    for scene_targets in targets_by_scene.values():
        scene = scene_targets[0]["scene"]
        if replace or not _dict_value(scene.get("scene_narration_plan")):
            scene["scene_narration_plan"] = _build_scene_narration_plan(scene, scene_targets)

    updated: list[str] = []
    skipped: list[str] = []
    for target in targets:
        node = target["cut"]
        scene = target["scene"]
        audio = _dict_value(node.get("audio"))
        previous = _dict_value(audio.get("narration"))
        previous_authoring_status = str(previous.get("authoring_status") or "").strip().lower()
        if previous_authoring_status in {"human_locked", "reviewed", "silent"}:
            skipped.append(str(target["selector"]))
            continue
        if not replace and _has_existing_narration_review(previous):
            skipped.append(str(target["selector"]))
            continue
        contract = _cut_narration_contract(node)
        cut_contract = _dict_value(node.get("cut_contract"))
        source_event_contract = _dict_value(cut_contract.get("source_event_contract"))
        event_context = _dict_value(cut_contract.get("event_context_for_cut"))
        is_silent = _is_silent_role(contract)
        text = ""
        elevenlabs_prompt = _pending_elevenlabs_prompt_payload(scene=scene, node=node, contract=contract) if not is_silent else {
            "spoken_context": _scene_logline(scene),
            "voice_tags": [],
            "spoken_body": "",
            "stability": "creative",
            "materialized": "",
        }
        tts_text = ""
        narration = {
            **previous,
            "status": "",
            "authoring_status": "silent" if is_silent else "missing",
            "missing_reason": "" if is_silent else "p700_narration_not_written_yet",
            "source": "p710_narration_contract_prepare",
            "source_cut_contract_version": str(cut_contract.get("schema_version") or ""),
            "source_event_contract_hash": _json_hash(source_event_contract),
            "event_context_hash": _json_hash(event_context),
            "cut_contract_hash": _json_hash(cut_contract),
            "contract": _narration_contract_payload(contract, node),
            "text": text,
            "tts_text": tts_text,
            "text_draft": text,
            "elevenlabs_prompt": elevenlabs_prompt,
            "silence_contract": _silence_contract_payload(contract, confirmed_by_human=False) if is_silent else {
                "intentional": False,
                "confirmed_by_human": False,
                "kind": "spoken",
                "reason": "",
            },
            "tool": "silent" if is_silent else str(previous.get("tool") or "elevenlabs"),
            # ``output`` is the selected, explicitly approved audio file.  A
            # planned destination must never look like an existing approval.
            "output": "",
            "review": {
                "status": "",
                "human_review_ok": False,
                "approved_at": "",
                "note": "p700 narration writer must author text before frontend TTS review",
            },
            "normalize_to_scene_duration": False,
        }
        ensure_narration_revision(narration)
        audio["narration"] = narration
        node["audio"] = audio
        updated.append(str(target["selector"]))

    _write_manifest_data(manifest_path, original_text, data)
    report_path = _write_narration_authoring_report(run_dir, updated=updated, skipped=skipped, replace=replace)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "status": "P720",
            "runtime.stage": "narration_contract_ready_p700_text_missing",
            "slot.p710.status": "done",
            "slot.p710.note": "narration grounding and scene_narration_plan created from video_manifest",
            "slot.p720.status": "pending",
            "slot.p720.note": "awaiting p700 narration writer before frontend TTS review",
            "slot.p730.status": "pending",
            "slot.p740.status": "pending",
            "slot.p750.status": "pending",
            "stage.narration.status": "in_progress",
            "review.narration.status": "not_started",
            "gate.narration_review": "required",
            "artifact.narration_authoring_report": report_path.relative_to(run_dir).as_posix(),
        },
    )
    return {"updated": updated, "skipped": skipped, "reportPath": report_path.relative_to(run_dir).as_posix()}


def _materialize_narration_authoring_workspace(run_dir: Path) -> dict[str, Any]:
    runner = ROOT / "scripts" / "ai" / "toc-immersive-narration-multiagent.py"
    if not runner.is_file():
        return {"status": "unavailable", "warning": f"authoring runner not found: {runner}"}
    result = subprocess.run(
        [sys.executable, str(runner), "--run-dir", str(run_dir)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        return {
            "status": "failed",
            "warning": result.stderr.strip() or result.stdout.strip() or "authoring workspace creation failed",
        }
    scratch_dir = run_dir / "scratch" / "narration"
    payload = {
        "status": "ready",
        "audioStoryPath": (scratch_dir / "audio_story.yaml").relative_to(run_dir).as_posix(),
        "authoringPromptPath": (scratch_dir / "authoring_prompt.md").relative_to(run_dir).as_posix(),
    }
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "artifact.narration_audio_story_scratch": payload["audioStoryPath"],
            "artifact.narration_authoring_prompt": payload["authoringPromptPath"],
        },
    )
    return payload


def _narration_silent_ok(run_dir: Path, *, item_id: str, reason: str | None = None) -> dict[str, Any]:
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    target = _target_by_item_id(data, item_id)
    if target is None:
        raise ValueError(f"video manifest target not found: {item_id}")
    _backup_run_file(run_dir, "video_manifest.md", label="before_narration_silent_ok")
    node = target["cut"]
    contract = _cut_narration_contract(node)
    audio = _dict_value(node.get("audio"))
    narration = _dict_value(audio.get("narration"))
    revision = ensure_narration_revision(narration)
    silence_contract = _silence_contract_payload(contract, confirmed_by_human=True, reason=reason)
    silence_contract["revision_hash"] = str(revision.get("source_hash") or "")
    narration.update(
        {
            "tool": "silent",
            "status": "audio_ready",
            "authoring_status": "silent",
            "text": "",
            "tts_text": "",
            "output": "",
            "silence_contract": silence_contract,
            "generation": {
                "status": "human_approved",
                "candidate_id": f"silent-revision-{int(revision.get('number') or 0)}",
                "generated_from_tts_hash": str(revision.get("tts_hash") or ""),
            },
            "audio_review": {
                "status": "approved",
                "approved_candidate_id": f"silent-revision-{int(revision.get('number') or 0)}",
                "approved_revision": int(revision.get("number") or 0),
                "approved_text_hash": str(revision.get("text_hash") or ""),
                "approved_tts_hash": str(revision.get("tts_hash") or ""),
                "approved_at": now_iso(),
                "note": "frontend explicitly approved intentional silence",
            },
            "review": {
                **_dict_value(narration.get("review")),
                "status": "pending",
                "human_review_ok": False,
            },
        }
    )
    audio["narration"] = narration
    node["audio"] = audio
    _invalidate_narration_run_approval(data, reason=f"intentional silence approved: {target['selector']}")
    _write_manifest_data(manifest_path, original_text, data)
    return {"itemId": str(target["selector"]), "status": "silent_ok"}


def _narration_audio_readiness(
    run_dir: Path, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    if data is None:
        _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    ready: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    for target in _manifest_scene_targets(data):
        selector = str(target["selector"])
        node = target["cut"]
        audio = _dict_value(node.get("audio"))
        narration = _dict_value(audio.get("narration"))
        revision_aware = _dict_value(narration.get("revision")).get("schema_version") == REVISION_SCHEMA_VERSION
        if revision_aware:
            if not _narration_grounding_is_current(target, narration):
                missing.append({"itemId": selector, "reason": "narration_grounding_revision_stale"})
                continue
            if not current_audio_is_human_approved(narration):
                missing.append({"itemId": selector, "reason": "current_revision_audio_not_human_approved"})
                continue
            if str(narration.get("tool") or "").strip().lower() == "silent":
                ready.append({"itemId": selector, "kind": "silent_ok"})
                continue
            output = str(narration.get("output") or "").strip()
            try:
                _validate_run_relative_audio_path(run_dir, output, must_exist=True)
                output_path = resolve_run_relative(run_dir, output)
                audio_review = _dict_value(narration.get("audio_review"))
                approved_candidate_id = str(audio_review.get("approved_candidate_id") or "")
                approved_candidate = next(
                    (
                        candidate
                        for candidate in _list_value(narration.get("candidates"))
                        if isinstance(candidate, dict)
                        and str(candidate.get("candidate_id") or "") == approved_candidate_id
                    ),
                    None,
                )
                if not _narration_candidate_context_is_current(
                    data,
                    selector=selector,
                    candidate=approved_candidate,
                ):
                    missing.append({"itemId": selector, "reason": "approved_audio_tts_context_stale"})
                    continue
                expected_sha256 = str((approved_candidate or {}).get("output_sha256") or "")
                if (
                    output_path.is_file()
                    and expected_sha256
                    and _audio_file_sha256(output_path) == expected_sha256
                ):
                    ready.append({"itemId": selector, "kind": "audio_file"})
                    continue
            except ValueError:
                pass
            missing.append({"itemId": selector, "reason": "approved_audio_file_missing_or_hash_mismatch"})
            continue
        if _narration_has_confirmed_silence(narration):
            ready.append({"itemId": selector, "kind": "silent_ok"})
            continue
        narration_status = str(narration.get("status") or "").strip().lower()
        review_status = str(_dict_value(narration.get("review")).get("status") or "").strip().lower()
        output = str(narration.get("output") or "").strip()
        if output and (narration_status in {"audio_ready", "approved"} or review_status == "approved"):
            try:
                _validate_run_relative_audio_path(run_dir, output, must_exist=True)
                if resolve_run_relative(run_dir, output).is_file():
                    ready.append({"itemId": selector, "kind": "audio_file"})
                    continue
            except ValueError:
                pass
        missing.append({"itemId": selector, "reason": "missing_audio_file_or_silent_ok"})
    return {"ready": not missing and bool(ready), "readyItems": ready, "missingItems": missing}


def _narration_has_confirmed_silence(narration: dict[str, Any]) -> bool:
    if _dict_value(narration.get("revision")).get("schema_version") == REVISION_SCHEMA_VERSION:
        return current_audio_is_human_approved(narration)
    tool = str(narration.get("tool") or "").strip().lower()
    silence_contract = _dict_value(narration.get("silence_contract"))
    return (
        tool == "silent"
        and silence_contract.get("intentional") is True
        and silence_contract.get("confirmed_by_human") is True
        and bool(str(silence_contract.get("kind") or "").strip())
        and bool(str(silence_contract.get("reason") or "").strip())
    )


def _duration_state_value(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.3f}".rstrip("0").rstrip(".")


def _narration_duration_readiness_for_data(
    run_dir: Path,
    data: dict[str, Any],
    *,
    manifest_path: Path,
) -> dict[str, Any]:
    audio_readiness = _narration_audio_readiness(run_dir, data)
    metadata = _dict_value(data.get("video_metadata"))
    try:
        target_seconds = normalize_target_duration(metadata.get("target_duration_seconds"))
    except ValueError as exc:
        return {
            **audio_readiness,
            "audioReady": bool(audio_readiness["ready"]),
            "ready": False,
            "durationPassed": False,
            "durationError": str(exc),
            "measurement": None,
            "audit": None,
            "manifestPath": manifest_path,
        }

    measurement = measure_manifest_runtime(
        data,
        base_dir=run_dir,
        probe=_probe_media_duration_seconds,
    )
    duration_audit = audit_duration(
        target_seconds=target_seconds,
        actual_seconds=measurement.effective_seconds,
        measurement_layer="frontend_audio_video_timeline",
    )
    audio_ready = bool(audio_readiness["ready"])
    duration_passed = bool(measurement.complete and duration_audit.passed)
    return {
        **audio_readiness,
        "audioReady": audio_ready,
        "ready": bool(audio_ready and duration_passed),
        "durationPassed": duration_passed,
        "durationError": "" if measurement.complete else "manifest runtime measurement is incomplete",
        "measurement": measurement,
        "audit": duration_audit,
        "manifestPath": manifest_path,
    }


def _narration_duration_readiness(run_dir: Path) -> dict[str, Any]:
    manifest_path, _original_text, data = _read_manifest_data(run_dir)
    return _narration_duration_readiness_for_data(
        run_dir,
        data,
        manifest_path=manifest_path,
    )


def _narration_duration_state_updates(readiness: dict[str, Any]) -> dict[str, str]:
    measurement = readiness.get("measurement")
    duration_audit = readiness.get("audit")
    if measurement is None or duration_audit is None:
        return {
            "review.duration_fit.status": "changes_requested",
            "review.duration_fit.note": str(readiness.get("durationError") or "duration contract is invalid"),
            "review.duration_fit.at": now_iso(),
        }

    def measurement_value(key: str, default: Any = 0) -> Any:
        return getattr(measurement, key, default)

    return {
        "review.duration_fit.status": "passed" if readiness.get("durationPassed") else "changes_requested",
        "review.duration_fit.target_seconds": str(duration_audit.target_seconds),
        "review.duration_fit.minimum_seconds": _duration_state_value(duration_audit.minimum_seconds),
        "review.duration_fit.actual_seconds": _duration_state_value(duration_audit.actual_seconds),
        "review.duration_fit.ratio": f"{duration_audit.ratio:.6f}",
        "review.duration_fit.measurement_layer": duration_audit.measurement_layer,
        "review.duration_fit.measurement_complete": str(bool(measurement_value("complete", True))).lower(),
        "review.duration_fit.spoken_audio_seconds": _duration_state_value(
            float(measurement_value("spoken_audio_seconds", 0))
        ),
        "review.duration_fit.intentional_silence_seconds": _duration_state_value(
            float(measurement_value("intentional_silence_seconds", 0))
        ),
        "review.duration_fit.audio_timeline_seconds": _duration_state_value(
            float(measurement_value("audio_timeline_seconds", 0))
        ),
        "review.duration_fit.video_timeline_seconds": _duration_state_value(
            float(measurement_value("video_timeline_seconds", 0))
        ),
        "review.duration_fit.video_timeline_source": str(measurement_value("video_timeline_source", "unknown")),
        "review.duration_fit.missing_items": json.dumps(
            list(measurement_value("missing_items", [])), ensure_ascii=False
        ),
        "review.duration_fit.invalid_items": json.dumps(
            list(measurement_value("invalid_items", [])), ensure_ascii=False
        ),
        "review.duration_fit.at": now_iso(),
    }


def _append_narration_review_approved_if_ready(run_dir: Path) -> dict[str, Any]:
    readiness = _narration_duration_readiness(run_dir)
    if not readiness["audioReady"]:
        return readiness
    measurement = readiness.get("measurement")
    duration_audit = readiness.get("audit")
    if measurement is None or duration_audit is None:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "review.duration_fit.status": "changes_requested",
                "review.duration_fit.note": str(readiness.get("durationError") or "duration contract is invalid"),
                "review.duration_fit.at": now_iso(),
                "slot.p740.status": "failed",
                "slot.p740.note": "duration contract could not be evaluated",
                "slot.p750.status": "blocked",
            },
        )
        return readiness

    duration_updates = _narration_duration_state_updates(readiness)
    if not readiness["durationPassed"]:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                **duration_updates,
                "review.duration_fit.note": "measured audio/video timeline is below 80% of target or incomplete",
                "slot.p740.status": "failed",
                "slot.p740.note": "measured narration timeline did not pass the 80% duration gate",
                "slot.p750.status": "blocked",
                "slot.p750.note": "audio QA is blocked by duration fit",
            },
        )
        return readiness
    _manifest_path, _manifest_original, data = _read_manifest_data(run_dir)
    review_blockers = _narration_review_blockers(data, run_dir=run_dir)
    if review_blockers:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                **duration_updates,
                "runtime.narration.phase": "review",
                "slot.p720.status": "in_progress",
                "slot.p720.note": "unresolved narration findings: " + ",".join(review_blockers[:20]),
                "slot.p740.status": "blocked",
                "slot.p750.status": "blocked",
                "stage.narration.status": "in_progress",
                "review.narration.status": "changes_requested",
                "gate.narration_review": "required",
            },
        )
        return readiness
    final_review_current = _narration_final_review_is_current(data, run_dir=run_dir)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            **duration_updates,
            "review.duration_fit.note": "measured audio/video timeline satisfies at least 80% of target",
            "slot.p720.status": "done",
            "slot.p720.note": "frontend narration text review completed through TTS/silent review",
            "slot.p730.status": "done",
            "slot.p730.note": "all cuts have audio files or intentional silence approvals",
            "slot.p740.status": "done",
            "slot.p740.note": "duration and current per-cut audio approvals passed",
            "slot.p750.status": "done" if final_review_current else "awaiting_approval",
            "slot.p750.note": (
                "full narration track explicitly approved"
                if final_review_current
                else "waiting for explicit frontend approval of the full narration track"
            ),
            "stage.narration.status": "done" if final_review_current else "awaiting_approval",
            "review.narration.status": "approved" if final_review_current else "pending",
            "gate.narration_review": "required",
        },
    )
    return readiness


def _require_narration_ready_for_video(run_dir: Path) -> dict[str, Any]:
    readiness = _append_narration_review_approved_if_ready(run_dir)
    if readiness["ready"]:
        _manifest_path, _original_text, data = _read_manifest_data(run_dir)
        if _narration_final_review_is_current(data, run_dir=run_dir):
            return readiness
        # Legacy manifests without the revision contract retain their previous
        # readiness behavior. Once a frontend revision exists, p750 is explicit.
        if not _revision_aware_narration_items(data):
            return readiness
        raise NarrationRevisionConflict(
            "video generation requires explicit p750 approval of the current full narration track"
        )
    if readiness.get("audioReady"):
        audit = readiness.get("audit")
        if audit is not None:
            raise NarrationRevisionConflict(
                "video generation requires measured duration of at least 80% of target: "
                f"actual={_duration_state_value(audit.actual_seconds)}s "
                f"minimum={_duration_state_value(audit.minimum_seconds)}s"
            )
        raise NarrationRevisionConflict("video generation requires a valid measured duration contract")
    missing = ", ".join(item["itemId"] for item in readiness["missingItems"][:20])
    raise NarrationRevisionConflict(
        "video generation requires audio files or silent approvals for all cuts: " + (missing or "none")
    )


def _default_video_output_for_target(target: dict[str, Any]) -> str:
    node = target["cut"]
    image_generation = node.get("image_generation") if isinstance(node.get("image_generation"), dict) else {}
    image_output = str(image_generation.get("output") or "").strip()
    if image_output:
        source = Path(image_output)
        return (source.parent / f"{source.stem}.mp4").as_posix()
    selector = str(target["selector"])
    return f"assets/scenes/{selector}/{selector}.mp4"


def _candidate_video_output_for_item(run_dir: Path, item_id: str) -> str | None:
    revision = _current_approved_video_candidate_provenance(run_dir, item_id)
    if revision is None:
        return None
    candidate = _video_candidate_path(
        run_dir,
        item_id,
        revision["revision_id"],
        1,
    )
    if candidate.is_file():
        return candidate.relative_to(run_dir).as_posix()
    return None


def _assert_current_video_candidate_path(
    run_dir: Path,
    item_id: str,
    video_path: str,
) -> None:
    """Reject a candidate generated for a superseded prompt revision."""

    parts = Path(video_path).parts
    prefix = (
        "assets",
        "test",
        "video_gen_candidates",
        _safe_artifact_id(item_id),
    )
    if tuple(parts[: len(prefix)]) != prefix:
        return
    if len(parts) != len(prefix) + 2:
        raise ValueError(f"invalid video candidate path: {item_id}")
    current = _current_approved_video_candidate_provenance(run_dir, item_id)
    if current is None or parts[len(prefix)] != current["revision_id"]:
        raise ValueError(f"stale video candidate revision: {item_id}")


def _manifest_narration_items(run_dir: Path, data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if data is None:
        _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    items: list[dict[str, Any]] = []
    for target in _manifest_scene_targets(data):
        selector = str(target["selector"])
        node = target["cut"]
        image_generation = node.get("image_generation") if isinstance(node.get("image_generation"), dict) else {}
        video_generation = node.get("video_generation") if isinstance(node.get("video_generation"), dict) else {}
        audio = node.get("audio") if isinstance(node.get("audio"), dict) else {}
        narration = audio.get("narration") if isinstance(audio.get("narration"), dict) else {}
        render = node.get("render") if isinstance(node.get("render"), dict) else {}
        narration_tool = str(narration.get("tool") or "elevenlabs").strip()
        silence_contract = narration.get("silence_contract") if isinstance(narration.get("silence_contract"), dict) else {}
        narration_silent_ok = (
            narration_tool == "silent"
            and silence_contract.get("intentional") is True
            and silence_contract.get("confirmed_by_human") is True
        )
        revision = _dict_value(narration.get("revision"))
        revision_aware = revision.get("schema_version") == REVISION_SCHEMA_VERSION
        generation = _dict_value(narration.get("generation"))
        audio_review = _dict_value(narration.get("audio_review"))
        narration_candidates = [value for value in _list_value(narration.get("candidates")) if isinstance(value, dict)]
        narration_candidate = next(
            (
                value
                for value in reversed(narration_candidates)
                if str(value.get("candidate_id") or "") == str(generation.get("candidate_id") or "")
            ),
            None,
        )
        approved_candidate_id = str(audio_review.get("approved_candidate_id") or "")
        approved_candidate = next(
            (
                value
                for value in narration_candidates
                if str(value.get("candidate_id") or "") == approved_candidate_id
            ),
            None,
        )
        narration_candidate_output = str((narration_candidate or {}).get("output") or "").strip()
        resolved_narration_candidate = (
            resolve_run_relative(run_dir, narration_candidate_output)
            if narration_candidate_output
            else run_dir / "__missing_narration_candidate__"
        )
        raw_narration_output = str(narration.get("output") or "").strip()
        narration_output = raw_narration_output or (
            "" if narration_silent_ok or revision_aware else _default_narration_output_for_target(target)
        )
        video_output = str(video_generation.get("output") or _default_video_output_for_target(target)).strip()
        candidate_output = _candidate_video_output_for_item(run_dir, selector)
        resolved_audio = resolve_run_relative(run_dir, narration_output) if narration_output else run_dir / "__missing_narration__"
        resolved_video = resolve_run_relative(run_dir, candidate_output or video_output)
        audio_duration = _probe_media_duration_seconds(resolved_audio)
        video_duration = _probe_media_duration_seconds(resolved_video)
        narration_audio_human_approved = bool(
            revision_aware
            and _narration_grounding_is_current(target, narration)
            and current_audio_is_human_approved(narration)
            and (
                narration_tool == "silent"
                or _narration_candidate_context_is_current(
                    data,
                    selector=selector,
                    candidate=approved_candidate,
                )
            )
        )
        if narration_audio_human_approved and narration_tool != "silent":
            expected_output_sha256 = str((approved_candidate or {}).get("output_sha256") or "")
            narration_audio_human_approved = bool(
                resolved_audio.is_file()
                and expected_output_sha256
                and _audio_file_sha256(resolved_audio) == expected_output_sha256
            )
        api_prompt_payload = image_generation.get("api_prompt_payload") if isinstance(image_generation.get("api_prompt_payload"), dict) else {}
        api_prompt_policy = str(api_prompt_payload.get("policy_version") or "").strip()
        api_prompt = str(api_prompt_payload.get("prompt") or "")
        legacy_prompt = str(image_generation.get("prompt") or "")
        prompt = api_prompt if api_prompt_policy.startswith(IMAGE_API_PROMPT_POLICY_PREFIX) else api_prompt or legacy_prompt
        configured_duration = int(
            render.get("video_duration_seconds")
            or video_generation.get("duration_seconds")
            or math.ceil(audio_duration or 8)
        )
        items.append(
            {
                "itemId": selector,
                "sceneId": target.get("scene_id"),
                "cutIndex": target.get("cut_index"),
                "imageOutput": image_generation.get("output"),
                "videoOutput": video_output,
                "selectedVideoPath": candidate_output or video_output,
                "videoExists": resolved_video.is_file(),
                "videoDurationSeconds": video_duration,
                "configuredVideoDurationSeconds": max(1, configured_duration),
                "videoPrompt": str(
                    video_generation.get("prompt_authoring_source")
                    or video_generation.get("source_motion_prompt")
                    or video_generation.get("motion_prompt")
                    or ""
                ),
                "videoTool": str(video_generation.get("tool") or "kling_3_0"),
                "videoQuality": str(video_generation.get("quality") or "1080p"),
                "videoAspectRatio": str(video_generation.get("aspect_ratio") or "16:9"),
                "videoFirstReference": str(video_generation.get("first_frame") or video_generation.get("input_image") or ""),
                "videoLastReference": str(video_generation.get("last_frame") or ""),
                "videoReferences": list(video_generation.get("references") or []) if isinstance(video_generation.get("references"), list) else [],
                "narrationText": str(narration.get("text") or ""),
                "narrationTtsText": str(narration.get("tts_text") or ""),
                "narrationOutput": narration_output or None,
                "narrationTool": narration_tool,
                "narrationStatus": str(narration.get("status") or ""),
                "narrationReviewStatus": str((narration.get("review") if isinstance(narration.get("review"), dict) else {}).get("status") or ""),
                "narrationAuthoringStatus": str(narration.get("authoring_status") or ""),
                "narrationRevision": int(revision.get("number") or 0),
                "narrationTextHash": str(revision.get("text_hash") or ""),
                "narrationTtsHash": str(revision.get("tts_hash") or ""),
                "narrationGenerationStatus": str(generation.get("status") or ""),
                "narrationCandidateId": str((narration_candidate or {}).get("candidate_id") or "") or None,
                "narrationCandidateOutput": narration_candidate_output or None,
                "narrationCandidateStatus": str((narration_candidate or {}).get("status") or ""),
                "narrationCandidateExists": resolved_narration_candidate.is_file(),
                "narrationCandidateDurationSeconds": (
                    float((narration_candidate or {}).get("duration_seconds"))
                    if (narration_candidate or {}).get("duration_seconds") is not None
                    else None
                ),
                "narrationGeneratedFromTtsHash": str(
                    (
                        approved_candidate
                        if narration_audio_human_approved
                        else narration_candidate
                    or {}
                    ).get("generated_from_tts_hash")
                    or ""
                ),
                "narrationAudioReviewStatus": str(audio_review.get("status") or ""),
                "narrationAudioHumanApproved": narration_audio_human_approved,
                "narrationSilentOk": narration_silent_ok,
                "narrationExists": resolved_audio.is_file(),
                "narrationDurationSeconds": audio_duration,
                "renderNarrationOffsetSeconds": float(
                    render.get("narration_offset_seconds")
                    or render.get("narration_start_seconds")
                    or 0
                ),
                "prompt": prompt,
                "legacyPrompt": legacy_prompt,
                "promptPolicyVersion": api_prompt_policy,
                "debugPromptSource": image_generation.get("debug_prompt_source") if isinstance(image_generation.get("debug_prompt_source"), dict) else {},
            }
        )
    return items


def _manifest_video_items(
    run_dir: Path,
    data: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Serialize exactly the cut or render-unit targets accepted by video APIs."""

    if data is None:
        _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    items: list[dict[str, Any]] = []
    for target in _manifest_video_targets(data):
        selector = str(target["selector"])
        node = _dict_value(target.get("cut"))
        image_generation = _dict_value(node.get("image_generation"))
        video_generation = _dict_value(node.get("video_generation"))
        input_contract = (
            _render_unit_video_input_contract(node)
            if target.get("is_render_unit")
            else {}
        )
        video_input_mode = str(input_contract.get("input_mode") or "").strip()
        if video_input_mode == "reference_images":
            first_frame = ""
        else:
            first_frame = str(
                video_generation.get("first_frame")
                or video_generation.get("input_image")
                or node.get("storyboard_image")
                or image_generation.get("output")
                or ""
            ).strip()
        last_frame = str(video_generation.get("last_frame") or "").strip()
        references = [
            str(value).strip()
            for value in _list_value(video_generation.get("references"))
            if str(value).strip()
        ]
        video_output = str(
            video_generation.get("output") or _default_video_output_for_target(target)
        ).strip()
        candidate_output = _candidate_video_output_for_item(run_dir, selector)
        selected_video = candidate_output or video_output
        resolved_video = resolve_run_relative(run_dir, selected_video)
        resolved_first_frame = (
            resolve_run_relative(run_dir, first_frame)
            if first_frame
            else run_dir / "__missing_video_first_frame__"
        )
        prompt_authoring_source = str(
            video_generation.get("prompt_authoring_source")
            or video_generation.get("source_motion_prompt")
            or ""
        ).strip()
        configured_duration = int(video_generation.get("duration_seconds") or 8)
        items.append(
            {
                "id": selector,
                "kind": "scene",
                "assetType": None,
                "tool": "video_manifest",
                "output": first_frame or None,
                "prompt": "",
                "promptPolicyVersion": None,
                "debugPromptSource": {
                    "videoTarget": "render_unit"
                    if target.get("is_render_unit")
                    else "cut",
                    "sourceCutIds": _list_value(node.get("source_cut_ids")),
                },
                "references": references,
                "referenceCount": len(references),
                "executionLane": "video_render_unit"
                if target.get("is_render_unit")
                else "video_cut",
                "generationStatus": "generated" if resolved_video.is_file() else None,
                "existingImage": first_frame if resolved_first_frame.is_file() else None,
                "candidates": [],
                "sceneId": target.get("scene_id"),
                "isRenderUnit": bool(target.get("is_render_unit")),
                "sourceCutIds": _list_value(node.get("source_cut_ids")),
                "videoPrompt": prompt_authoring_source,
                "videoOutput": video_output,
                "selectedVideoPath": selected_video,
                "videoExists": resolved_video.is_file(),
                "videoDurationSeconds": _probe_media_duration_seconds(resolved_video),
                "configuredVideoDurationSeconds": max(1, configured_duration),
                "videoTool": str(video_generation.get("tool") or "kling_3_0"),
                "videoQuality": str(video_generation.get("quality") or "1080p"),
                "videoAspectRatio": str(
                    video_generation.get("aspect_ratio") or "16:9"
                ),
                "videoFirstReference": first_frame,
                "videoLastReference": last_frame,
                "videoReferences": references,
                "videoInputMode": video_input_mode or None,
            }
        )
    return items


def _write_narration_debug_log(
    *,
    run_dir: Path,
    item_id: str,
    destination: Path,
    request: NarrationGenerateItem,
    duration_seconds: float | None = None,
    error: str | None = None,
) -> Path:
    log_dir = run_dir / "logs" / "providers" / "narration"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"{stamp}_{time.time_ns()}_{_safe_artifact_id(item_id)}.json"
    payload = {
        "itemId": item_id,
        "destination": destination.relative_to(run_dir).as_posix(),
        "tool": request.tool,
        "providerRequest": {
            "voice_id": request.voice_id,
            "model_id": request.model_id,
            "voice_settings": request.voice_settings,
            "output_format": request.output_format,
            "language_code": request.language_code,
            "pronunciation_dictionary_locators": request.pronunciation_dictionary_locators,
            "pronunciation_alias_source": request.pronunciation_alias_source,
            "pronunciation_alias_sha256": request.pronunciation_alias_sha256,
            "effective_delivery_hash": request.effective_delivery_hash,
            "tts_generation_group_id": request.tts_generation_group_id,
            "tts_continuity_hash": request.tts_continuity_hash,
            "previous_text": request.previous_text,
            "next_text": request.next_text,
        },
        "status": "failed" if error else "completed",
        "durationSeconds": duration_seconds,
        "error": error,
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return log_path


def _narration_candidate_output(target: dict[str, Any], requested_output: str | None, candidate_id: str) -> str:
    base = Path(requested_output or _default_narration_output_for_target(target))
    suffix = base.suffix or ".mp3"
    return (base.parent / "candidates" / f"{candidate_id}{suffix}").as_posix()


def _narration_tts_context_by_selector(data: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Build stable adjacent-text context for each full-run TTS continuity group."""

    refs_by_selector = narration_span_refs(data)
    for selector, refs in refs_by_selector.items():
        group_ids = {
            str(ref.get("tts_generation_group_id") or "").strip()
            for ref in refs
            if str(ref.get("audio_visual_relation") or "").strip() != "voice_silence"
            and str(ref.get("tts_generation_group_id") or "").strip()
        }
        if len(group_ids) > 1:
            raise ValueError(f"{selector}: narration spans assign more than one tts_generation_group_id")
    return tts_continuity_contexts(data)


def _narration_candidate_context_is_current(
    data: dict[str, Any], *, selector: str, candidate: dict[str, Any] | None
) -> bool:
    if candidate is None:
        return False
    current_hash = str(
        _dict_value(_narration_tts_context_by_selector(data).get(selector)).get("tts_continuity_hash") or ""
    )
    frozen_hash = str(_dict_value(candidate.get("provider_request")).get("tts_continuity_hash") or "")
    return frozen_hash == current_hash


def _prepare_narration_generation_request_snapshot(
    run_dir: Path,
    prepared: list[dict[str, Any]],
) -> tuple[str, dict[Path, str]]:
    snapshot_dir = run_dir / "logs" / "providers" / "narration" / "generation_requests"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    path = snapshot_dir / f"{stamp}.json"
    latest = snapshot_dir / "latest.json"
    payload = {
        "schemaVersion": "narration_generation_request_snapshot_v1",
        "createdAt": now_iso(),
        "items": [
            {
                "itemId": str(entry["request"].item_id),
                "tool": str(entry["request"].tool),
                **_dict_value(entry.get("snapshot")),
            }
            for entry in prepared
        ],
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return path.relative_to(run_dir).as_posix(), {path: serialized, latest: serialized}


def _prepare_manifest_narration_generation(
    run_dir: Path, items: list[NarrationGenerateItem]
) -> list[dict[str, Any]]:
    item_ids = [item.item_id for item in items]
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("bulk narration generation contains duplicate item_id values")
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    tts_contexts = _narration_tts_context_by_selector(data)
    prepared: list[dict[str, Any]] = []
    for item in items:
        target = _target_by_item_id(data, item.item_id)
        if target is None:
            raise ValueError(f"video manifest target not found: {item.item_id}")
        node = _dict_value(target.get("cut"))
        audio = _dict_value(node.get("audio"))
        narration = _dict_value(audio.get("narration"))
        revision = ensure_narration_revision(narration)
        current_text = str(narration.get("text") or "")
        current_tts = str(narration.get("tts_text") or current_text)
        requested_text = item.text.strip()
        requested_tts = (item.tts_text or "").strip()
        requested_payload_differs = bool(
            (requested_text and requested_text != current_text)
            or (requested_tts and requested_tts != current_tts)
            or (item.tool and item.tool != str(narration.get("tool") or "elevenlabs"))
        )
        if requested_payload_differs:
            raise NarrationRevisionConflict(
                "narration payload differs from the canonical saved revision; save text before generating"
            )
        source_binding = _dict_value(narration.get("source_binding"))
        if int(revision.get("number") or 0) <= 0 or not str(source_binding.get("script_selector") or "").strip():
            raise ValueError(f"narration text must be saved before generation: {item.item_id}")
        if not _narration_grounding_is_current(target, narration):
            raise NarrationRevisionConflict(
                f"narration grounding changed; save and review the current text before generation: {item.item_id}"
            )
        candidate_id = f"{_now_stamp()}_{uuid.uuid4().hex[:12]}"
        candidate_output = _narration_candidate_output(target, item.output, candidate_id)
        _validate_run_relative_audio_path(run_dir, candidate_output, must_exist=False)
        effective_delivery = _effective_narration_delivery(narration) if item.tool == "elevenlabs" else {}
        tts_context = tts_contexts.get(str(target["selector"]), {}) if item.tool == "elevenlabs" else {}
        provider_request = {
            key: value
            for key, value in {**effective_delivery, **tts_context}.items()
            if key != "pronunciation_alias_path"
        }
        snapshot = prepare_audio_candidate(
            narration,
            candidate_id=candidate_id,
            output=candidate_output,
            expected_revision=item.expected_revision,
            expected_tts_hash=item.expected_tts_hash,
            now=now_iso(),
            provider_request=provider_request,
        )
        audio["narration"] = narration
        node["audio"] = audio
        prepared_request = item.model_copy(
            update={
                "text": str(narration.get("text") or ""),
                "tts_text": str(narration.get("tts_text") or ""),
                "tool": str(narration.get("tool") or item.tool),
                "output": candidate_output,
                **effective_delivery,
                **tts_context,
            }
        )
        prepared.append({"request": prepared_request, "snapshot": snapshot, "selector": str(target["selector"])})
    snapshot_path, snapshot_writes = _prepare_narration_generation_request_snapshot(run_dir, prepared)
    transaction = _capture_file_transaction(
        [
            manifest_path,
            run_dir / "state.txt",
            run_dir / "run_status.json",
            run_dir / "p000_index.md",
            *snapshot_writes,
        ]
    )
    _backup_run_file(run_dir, "video_manifest.md", label="before_narration_candidate_prepare")
    try:
        _write_manifest_data(manifest_path, original_text, data)
        for path, content in snapshot_writes.items():
            _atomic_write_text(path, content)
        _append_narration_preview_state(
            run_dir,
            note="alternate narration TTS candidate generation started; current approval is unchanged",
        )
        append_state_snapshot(
            run_dir / "state.txt",
            {"artifact.narration_generation_request_snapshot": snapshot_path},
        )
    except Exception:
        _restore_file_transaction(transaction)
        raise
    return prepared


def _audio_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _record_manifest_narration_generation_results(
    run_dir: Path, prepared: list[dict[str, Any]], results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    prepared_by_id = {str(entry["request"].item_id): entry for entry in prepared}
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    invalidate_stale_tts_context_audio(data)
    recorded: list[dict[str, Any]] = []
    for result in results:
        item_id = str(result.get("itemId") or "")
        entry = prepared_by_id.get(item_id)
        if entry is None:
            continue
        target = _target_by_item_id(data, item_id)
        if target is None:
            continue
        narration = _dict_value(_dict_value(_dict_value(target["cut"]).get("audio")).get("narration"))
        snapshot = _dict_value(entry.get("snapshot"))
        path_text = str(result.get("path") or snapshot.get("output") or "")
        output_path = resolve_run_relative(run_dir, path_text) if path_text else run_dir / "__missing_narration_candidate__"
        succeeded = result.get("status") == "completed" and output_path.is_file()
        status = record_audio_candidate_result(
            narration,
            snapshot=snapshot,
            succeeded=succeeded,
            duration_seconds=float(result["durationSeconds"]) if result.get("durationSeconds") is not None else None,
            output_sha256=_audio_file_sha256(output_path) if succeeded else "",
            now=now_iso(),
        )
        recorded.append(
            {
                **result,
                "providerStatus": str(result.get("status") or ""),
                "status": status,
                "candidateId": str(snapshot.get("candidate_id") or ""),
                "generatedFromTtsHash": str(snapshot.get("generated_from_tts_hash") or ""),
                "requestRevision": int(snapshot.get("request_revision") or 0),
                "path": path_text or None,
            }
        )
    _write_manifest_data(manifest_path, original_text, data)
    return recorded


def _apply_audio_duration_to_manifest(run_dir: Path, durations_by_item: dict[str, float]) -> list[str]:
    if not durations_by_item:
        return []
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    updated: list[str] = []
    for item_id, duration in durations_by_item.items():
        target = _target_by_item_id(data, item_id)
        if target is None:
            continue
        node = target["cut"]
        min_duration = max(1, math.ceil(duration))
        video_generation = node.get("video_generation") if isinstance(node.get("video_generation"), dict) else {}
        current = int(video_generation.get("duration_seconds") or 0)
        if current < min_duration:
            video_generation["duration_seconds"] = min_duration
            node["video_generation"] = video_generation
            render = node.get("render") if isinstance(node.get("render"), dict) else {}
            if int(render.get("video_duration_seconds") or 0) < min_duration:
                render["video_duration_seconds"] = min_duration
                node["render"] = render
            updated.append(item_id)
    if updated:
        _backup_run_file(run_dir, "video_manifest.md", label="before_audio_duration_sync")
    _write_manifest_data(manifest_path, original_text, data)
    return updated


def _approve_manifest_narration_audio(
    run_dir: Path,
    *,
    item_id: str,
    candidate_id: str,
    expected_revision: int,
    expected_tts_hash: str,
    note: str | None,
) -> dict[str, Any]:
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    target = _target_by_item_id(data, item_id)
    if target is None:
        raise ValueError(f"video manifest target not found: {item_id}")
    node = _dict_value(target.get("cut"))
    narration = _dict_value(_dict_value(node.get("audio")).get("narration"))
    candidate = next(
        (
            value
            for value in _list_value(narration.get("candidates"))
            if isinstance(value, dict) and str(value.get("candidate_id") or "") == candidate_id
        ),
        None,
    )
    if candidate is None:
        raise NarrationRevisionConflict(f"narration candidate not found: {candidate_id}")
    candidate_output = str(candidate.get("output") or "").strip()
    _validate_run_relative_audio_path(run_dir, candidate_output, must_exist=True)
    candidate_path = resolve_run_relative(run_dir, candidate_output)
    if not candidate_path.is_file():
        raise ValueError(f"narration candidate audio file not found: {candidate_output}")
    expected_output_sha256 = str(candidate.get("output_sha256") or "").strip()
    actual_output_sha256 = _audio_file_sha256(candidate_path)
    if not expected_output_sha256 or actual_output_sha256 != expected_output_sha256:
        raise NarrationRevisionConflict("narration candidate audio bytes no longer match the generated snapshot")
    if not _narration_candidate_context_is_current(
        data,
        selector=str(target["selector"]),
        candidate=candidate,
    ):
        raise NarrationRevisionConflict("narration candidate was generated with stale full-run TTS context")
    if not _narration_grounding_is_current(target, narration):
        raise NarrationRevisionConflict("narration grounding changed after candidate generation")
    transaction = _capture_file_transaction(
        [
            manifest_path,
            run_dir / "state.txt",
            run_dir / "run_status.json",
            run_dir / "p000_index.md",
        ]
    )
    try:
        approved = approve_audio_candidate(
            narration,
            candidate_id=candidate_id,
            expected_revision=expected_revision,
            expected_tts_hash=expected_tts_hash,
            now=now_iso(),
        )
        audio_review = _dict_value(narration.get("audio_review"))
        audio_review["note"] = (
            note or "frontend explicitly approved this narration audio after playback"
        ).strip()
        narration["audio_review"] = audio_review
        _invalidate_narration_run_approval(
            data,
            reason=f"narration candidate approved: {target['selector']}",
        )
        _backup_run_file(run_dir, "video_manifest.md", label="before_narration_audio_approve")
        _write_manifest_data(manifest_path, original_text, data)
        duration = approved.get("duration_seconds")
        duration_updated = _apply_audio_duration_to_manifest(
            run_dir,
            {str(target["selector"]): float(duration)} if duration is not None else {},
        )
        _append_narration_review_approved_if_ready(run_dir)
        _manifest_path, _manifest_original, latest_data = _read_manifest_data(run_dir)
        latest_target = _target_by_item_id(latest_data, item_id)
        if latest_target is None:
            raise ValueError(f"video manifest target disappeared during approval: {item_id}")
    except Exception:
        _restore_file_transaction(transaction)
        raise
    return {
        "item": _narration_summary(latest_target),
        "durationUpdated": duration_updated,
        "audioSetHash": _manifest_narration_audio_set_hash(latest_data),
    }


def _revision_aware_narration_items(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    for target in _manifest_scene_targets(data):
        narration = _dict_value(_dict_value(_dict_value(target["cut"]).get("audio")).get("narration"))
        if _dict_value(narration.get("revision")).get("schema_version") == REVISION_SCHEMA_VERSION:
            items.append((str(target["selector"]), narration))
    return items


def _revision_aware_narration_contexts_are_current(data: dict[str, Any]) -> bool:
    for target in _manifest_scene_targets(data):
        narration = _dict_value(_dict_value(_dict_value(target["cut"]).get("audio")).get("narration"))
        if _dict_value(narration.get("revision")).get("schema_version") != REVISION_SCHEMA_VERSION:
            continue
        if str(narration.get("tool") or "").strip().lower() == "silent":
            continue
        review = _dict_value(narration.get("audio_review"))
        approved_id = str(review.get("approved_candidate_id") or "")
        candidate = next(
            (
                item
                for item in _list_value(narration.get("candidates"))
                if isinstance(item, dict) and str(item.get("candidate_id") or "") == approved_id
            ),
            None,
        )
        if not _narration_candidate_context_is_current(
            data,
            selector=str(target["selector"]),
            candidate=candidate,
        ):
            return False
    return True


async def _run_narration_semantic_review(
    run_dir: Path,
    data: dict[str, Any],
    *,
    expected_text_set_hash: str,
    expected_input_hash: str,
) -> dict[str, Any]:
    return await run_narration_semantic_critics(
        run_dir,
        data,
        expected_narration_text_set_hash=expected_text_set_hash,
        expected_semantic_review_input_hash=expected_input_hash,
        client_factory=create_codex_app_server_client,
        disabled=app_server_disabled(),
        timeout_seconds=600,
        max_concurrency=3,
    )


def _prepare_narration_semantic_review_artifacts(
    run_dir: Path, aggregate: dict[str, Any]
) -> tuple[str, str, dict[Path, str]]:
    review_dir = run_dir / "logs" / "eval" / "narration" / "semantic_critics"
    review_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_stamp()
    report_path = review_dir / f"{stamp}_review.md"
    json_path = review_dir / f"{stamp}_review.json"
    latest_report = review_dir / "latest.md"
    latest_json = review_dir / "latest.json"
    report_text = str(aggregate.get("report") or "").rstrip() + "\n"
    json_text = json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    writes = {
        report_path: report_text,
        json_path: json_text,
        latest_report: report_text,
        latest_json: json_text,
    }
    return (
        report_path.relative_to(run_dir).as_posix(),
        json_path.relative_to(run_dir).as_posix(),
        writes,
    )


def _semantic_review_manifest_record(
    aggregate: dict[str, Any], *, report_path: str, json_path: str
) -> dict[str, Any]:
    return {
        "schema_version": str(aggregate.get("schema_version") or ""),
        "status": str(aggregate.get("status") or "changes_requested"),
        "narration_text_set_hash": str(aggregate.get("narration_text_set_hash") or ""),
        "semantic_review_input_hash": str(
            aggregate.get("semantic_review_input_hash") or ""
        ),
        "reviewed_at": str(aggregate.get("reviewed_at") or now_iso()),
        "critics": deepcopy(_list_value(aggregate.get("critics"))),
        "findings": deepcopy(_list_value(aggregate.get("findings"))),
        "report": report_path,
        "json": json_path,
    }


def _narration_review_blockers(
    data: dict[str, Any],
    *,
    run_dir: Path | None = None,
    semantic_artifact: dict[str, Any] | None = None,
) -> list[str]:
    blockers = deterministic_narration_review_blockers(data)
    workflow = _dict_value(data.get("narration_workflow"))
    revision_aware_items = _revision_aware_narration_items(data)
    if revision_aware_items or "semantic_critic_review" in workflow:
        semantic_review = _dict_value(workflow.get("semantic_critic_review"))
        if not narration_semantic_review_is_current(
            data,
            semantic_review,
            run_dir=run_dir,
            artifact_aggregate=semantic_artifact,
        ):
            blockers.append("full_run_semantic_critics")
    return blockers


def _manifest_narration_audio_set_hash(data: dict[str, Any]) -> str:
    payload: list[dict[str, Any]] = []
    for target in _manifest_scene_targets(data):
        narration = _dict_value(_dict_value(_dict_value(target["cut"]).get("audio")).get("narration"))
        revision = _dict_value(narration.get("revision"))
        audio_review = _dict_value(narration.get("audio_review"))
        approved_candidate_id = str(audio_review.get("approved_candidate_id") or "")
        candidate = next(
            (
                value
                for value in _list_value(narration.get("candidates"))
                if isinstance(value, dict) and str(value.get("candidate_id") or "") == approved_candidate_id
            ),
            None,
        )
        payload.append(
            {
                "candidate_id": approved_candidate_id,
                "duration_seconds": candidate.get("duration_seconds") if candidate else None,
                "output": str(narration.get("output") or ""),
                "output_sha256": str((candidate or {}).get("output_sha256") or ""),
                "tts_continuity_hash": str(
                    _dict_value((candidate or {}).get("provider_request")).get("tts_continuity_hash") or ""
                ),
                "selector": str(target["selector"]),
                "source_hash": str(revision.get("source_hash") or ""),
                "status": str(narration.get("status") or ""),
                "tool": str(narration.get("tool") or ""),
            }
        )
    return _full_json_hash(payload)


def _manifest_narration_timeline_hash(data: dict[str, Any]) -> str:
    payload: list[dict[str, Any]] = []
    for target in _manifest_scene_targets(data):
        node = _dict_value(target["cut"])
        render = _dict_value(node.get("render"))
        video_generation = _dict_value(node.get("video_generation"))
        payload.append(
            {
                "selector": str(target["selector"]),
                "video_duration_seconds": _int_value(
                    render.get("video_duration_seconds")
                    or video_generation.get("duration_seconds")
                    or 0
                ),
                "narration_offset_seconds": round(
                    _float_value(render.get("narration_offset_seconds") or 0),
                    3,
                ),
            }
        )
    return _full_json_hash(payload)


def _render_unit_timeline_issues(
    data: dict[str, Any], *, synchronize: bool = False
) -> list[str]:
    """Validate/synchronize render-unit durations against the approved cut timeline."""

    issues: list[str] = []
    for target in _manifest_scene_targets(data):
        scene = _dict_value(target.get("scene"))
        if _list_value(scene.get("render_units")):
            continue
        node = _dict_value(target.get("cut"))
        render = _dict_value(node.get("render"))
        generation = _dict_value(node.get("video_generation"))
        duration = _int_value(
            render.get("video_duration_seconds")
            or generation.get("duration_seconds")
            or node.get("duration_seconds")
            or 0
        )
        if duration <= 0:
            continue
        tool, model, input_mode = _video_generation_provider_context(generation)
        issues.extend(
            _video_provider_capability_issues(
                label=str(target["selector"]),
                tool=tool,
                model=model,
                input_mode=input_mode,
                duration_seconds=duration,
                reference_count=len(_list_value(generation.get("references"))),
                # Reference edits are approval-payload drift, not timeline
                # drift. They are checked during materialization and dispatch.
                validate_reference_count=False,
            )
        )
    for scene_index, scene in enumerate(_list_value(data.get("scenes"))):
        if not isinstance(scene, dict) or _is_non_renderable_manifest_node(scene):
            continue
        raw_render_units = _list_value(scene.get("render_units"))
        if not raw_render_units:
            continue
        render_units = [unit for unit in raw_render_units if isinstance(unit, dict)]
        scene_id = normalize_dotted_id(scene.get("scene_id")) or str(scene_index + 1)
        if len(render_units) != len(raw_render_units):
            issues.append(f"scene{scene_id}: render_units must contain only mappings")
        active_cuts = [
            cut
            for cut in _list_value(scene.get("cuts"))
            if isinstance(cut, dict) and not _is_non_renderable_manifest_node(cut)
        ]
        cut_durations: dict[str, int] = {}
        active_cuts_by_id: dict[str, dict[str, Any]] = {}
        seen_cut_ids: set[str] = set()
        for cut_index, cut in enumerate(active_cuts):
            cut_id = normalize_dotted_id(cut.get("cut_id")) or str(cut_index + 1)
            if cut_id in seen_cut_ids:
                issues.append(f"scene{scene_id}_cut{cut_id}: duplicate active cut id")
                continue
            seen_cut_ids.add(cut_id)
            render = _dict_value(cut.get("render"))
            generation = _dict_value(cut.get("video_generation"))
            duration = _int_value(
                render.get("video_duration_seconds")
                or generation.get("duration_seconds")
                or cut.get("duration_seconds")
                or 0
            )
            if duration <= 0:
                issues.append(f"scene{scene_id}_cut{cut_id}: approved video duration is missing")
                continue
            cut_durations[cut_id] = duration
            active_cuts_by_id[cut_id] = cut

        ownership: dict[str, str] = {}
        canonical_source_ids = list(cut_durations)
        flattened_source_ids: list[str] = []
        seen_unit_ids: set[str] = set()
        for unit_index, unit in enumerate(render_units):
            unit_id = normalize_dotted_id(unit.get("unit_id")) or str(unit_index + 1)
            selector = f"scene{scene_id}_unit{unit_id}"
            if unit_id in seen_unit_ids:
                issues.append(f"{selector}: duplicate render unit id")
            seen_unit_ids.add(unit_id)
            if _is_non_renderable_manifest_node(unit):
                issues.append(f"{selector}: deleted/reference render units are not supported")
                continue
            issues.extend(
                _render_unit_video_input_issues(selector=selector, node=unit)
            )
            raw_source_ids = unit.get("source_cut_ids")
            if not isinstance(raw_source_ids, list) or not raw_source_ids:
                issues.append(f"{selector}: source_cut_ids must be a non-empty list")
                continue
            source_ids: list[str] = []
            for raw_source_id in raw_source_ids:
                source_id = normalize_dotted_id(raw_source_id)
                if source_id is None or source_id not in cut_durations:
                    issues.append(f"{selector}: unknown or deleted source cut {raw_source_id!r}")
                    continue
                if source_id in source_ids:
                    issues.append(f"{selector}: duplicate source cut {source_id}")
                    continue
                previous_owner = ownership.get(source_id)
                if previous_owner is not None:
                    issues.append(f"scene{scene_id}_cut{source_id}: owned by both {previous_owner} and {selector}")
                    continue
                ownership[source_id] = selector
                source_ids.append(source_id)
                flattened_source_ids.append(source_id)
            if not source_ids:
                continue
            expected_duration = sum(cut_durations[source_id] for source_id in source_ids)
            generation = _dict_value(unit.get("video_generation"))
            input_contract = _render_unit_video_input_contract(unit)
            if input_contract.get("input_mode") == "reference_images":
                first_source_cut = active_cuts_by_id[source_ids[0]]
                first_source_output = str(
                    _dict_value(first_source_cut.get("image_generation")).get(
                        "output"
                    )
                    or ""
                ).strip()
                storyboard_image = str(
                    unit.get("storyboard_image") or ""
                ).strip()
                if not first_source_output or not storyboard_image:
                    issues.append(
                        f"{selector}: reference-image render unit requires the first source-cut "
                        "image output and storyboard_image"
                    )
                else:
                    expected_references = [first_source_output, storyboard_image]
                    required_references = [
                        str(value).strip()
                        for value in _list_value(
                            input_contract.get("required_references")
                        )
                        if str(value).strip()
                    ]
                    current_references = [
                        str(value).strip()
                        for value in _list_value(generation.get("references"))
                        if str(value).strip()
                    ]
                    if required_references != expected_references:
                        issues.append(
                            f"{selector}: required render-unit references must exactly equal the "
                            "ordered first source-cut image and storyboard_image"
                        )
                    if current_references != expected_references:
                        issues.append(
                            f"{selector}: video generation references must exactly equal the "
                            "ordered first source-cut image and storyboard_image"
                        )
                    expected_roles = [
                        {
                            "image_index": 1,
                            "role": "start_state_visual_anchor",
                        },
                        {
                            "image_index": 2,
                            "role": "ordered_storyboard_sequence_guide",
                        },
                    ]
                    if _list_value(input_contract.get("reference_roles")) != expected_roles:
                        issues.append(
                            f"{selector}: reference_roles must exactly bind image 1 as the "
                            "start-state anchor and image 2 as the ordered storyboard guide"
                        )
            tool, model, input_mode = _video_generation_provider_context(
                generation,
                input_mode=str(input_contract.get("input_mode") or ""),
            )
            capability_issues = _video_provider_capability_issues(
                label=selector,
                tool=tool,
                model=model,
                input_mode=input_mode,
                duration_seconds=expected_duration,
                reference_count=len(_list_value(generation.get("references"))),
            )
            issues.extend(capability_issues)
            if any("duration" in issue for issue in capability_issues):
                issues.append(
                    f"{selector}: split the render unit to fit its provider capability"
                )
            actual_duration = _int_value(generation.get("duration_seconds") or 0)
            if synchronize:
                generation["duration_seconds"] = expected_duration
                unit["video_generation"] = generation
            elif actual_duration != expected_duration:
                issues.append(
                    f"{selector}: duration {actual_duration}s does not match approved source-cut total "
                    f"{expected_duration}s"
                )

        missing_cut_ids = [cut_id for cut_id in cut_durations if cut_id not in ownership]
        if missing_cut_ids:
            issues.append(
                f"scene{scene_id}: active cuts missing from render_units: {', '.join(missing_cut_ids)}"
            )
        if flattened_source_ids != canonical_source_ids:
            issues.append(
                f"scene{scene_id}: render_units source-cut order must match canonical cut order "
                f"({', '.join(canonical_source_ids)})"
            )
    return issues


def _apply_narration_approval_timeline(
    data: dict[str, Any], timeline: list[NarrationTimelineItem]
) -> str:
    targets = _manifest_scene_targets(data)
    expected_ids = [str(target["selector"]) for target in targets]
    requested_ids = [item.item_id for item in timeline]
    if requested_ids != expected_ids:
        raise NarrationRevisionConflict(
            "full narration timeline must include every manifest cut exactly once in canonical order"
        )
    for target, item in zip(targets, timeline, strict=True):
        node = _dict_value(target["cut"])
        narration = _dict_value(_dict_value(node.get("audio")).get("narration"))
        video_generation = _dict_value(node.get("video_generation"))
        render = _dict_value(node.get("render"))
        audio_review = _dict_value(narration.get("audio_review"))
        approved_candidate_id = str(audio_review.get("approved_candidate_id") or "")
        approved_candidate = next(
            (
                candidate
                for candidate in _list_value(narration.get("candidates"))
                if isinstance(candidate, dict)
                and str(candidate.get("candidate_id") or "") == approved_candidate_id
            ),
            None,
        )
        raw_audio_duration = (approved_candidate or {}).get("duration_seconds")
        revision_aware_spoken = bool(
            _dict_value(narration.get("revision")).get("schema_version") == REVISION_SCHEMA_VERSION
            and str(narration.get("tool") or "").strip().lower() != "silent"
        )
        audio_duration = _float_value(raw_audio_duration)
        if revision_aware_spoken and (not math.isfinite(audio_duration) or audio_duration <= 0):
            raise NarrationRevisionConflict(
                f"approved narration candidate has no positive measured duration: {item.item_id}"
            )
        required_duration = max(
            1,
            math.ceil(audio_duration + float(item.narration_offset_seconds)),
        )
        if item.video_duration_seconds < required_duration:
            raise NarrationRevisionConflict(
                f"approved narration timeline would truncate audio for {item.item_id}: "
                f"required={required_duration}s requested={item.video_duration_seconds}s"
            )
        video_generation["duration_seconds"] = item.video_duration_seconds
        node["video_generation"] = video_generation
        render["video_duration_seconds"] = item.video_duration_seconds
        render["narration_offset_seconds"] = float(item.narration_offset_seconds)
        node["render"] = render
    render_unit_issues = _render_unit_timeline_issues(data, synchronize=True)
    if render_unit_issues:
        raise NarrationRevisionConflict("invalid render-unit timeline: " + "; ".join(render_unit_issues[:20]))
    return _manifest_narration_timeline_hash(data)


def _narration_final_review_is_current(
    data: dict[str, Any],
    *,
    run_dir: Path | None = None,
) -> bool:
    items = _revision_aware_narration_items(data)
    if items and not all(current_audio_is_human_approved(narration) for _selector, narration in items):
        return False
    if items and not _revision_aware_narration_contexts_are_current(data):
        return False
    if items and _narration_review_blockers(data, run_dir=run_dir):
        return False
    if _render_unit_timeline_issues(data):
        return False
    final_review = _dict_value(_dict_value(data.get("narration_workflow")).get("final_audio_review"))
    current_set_hash = _manifest_narration_audio_set_hash(data)
    listen_evidence = _dict_value(final_review.get("listen_evidence"))
    expected_item_ids = [str(target["selector"]) for target in _manifest_scene_targets(data)]
    expected_timeline = [
        {
            "item_id": str(target["selector"]),
            "video_duration_seconds": _int_value(
                _dict_value(target["cut"].get("render")).get("video_duration_seconds")
                or _dict_value(target["cut"].get("video_generation")).get("duration_seconds")
                or 0
            ),
            "narration_offset_seconds": _float_value(
                _dict_value(target["cut"].get("render")).get("narration_offset_seconds") or 0
            ),
        }
        for target in _manifest_scene_targets(data)
    ]
    return bool(
        final_review.get("status") == "approved"
        and str(final_review.get("approved_audio_set_hash") or "") == current_set_hash
        and str(final_review.get("approved_timeline_hash") or "")
        == _manifest_narration_timeline_hash(data)
        and listen_evidence.get("mode") == "sequential_full_run"
        and str(listen_evidence.get("audio_set_hash") or "") == current_set_hash
        and _list_value(listen_evidence.get("item_ids")) == expected_item_ids
        and _list_value(listen_evidence.get("timeline")) == expected_timeline
        and bool(str(listen_evidence.get("completed_at") or "").strip())
    )


def _approve_narration_full_run(
    run_dir: Path,
    *,
    note: str,
    expected_audio_set_hash: str,
    timeline: list[NarrationTimelineItem],
    listen_evidence: NarrationListenEvidence,
) -> dict[str, Any]:
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    review_blockers = _narration_review_blockers(data, run_dir=run_dir)
    if review_blockers:
        raise ValueError("full narration approval has unresolved p720 findings: " + ", ".join(review_blockers[:20]))
    items = _revision_aware_narration_items(data)
    if items and not all(current_audio_is_human_approved(narration) for _selector, narration in items):
        raise ValueError("full narration approval contains stale or unapproved revision-aware audio")
    if items and not _revision_aware_narration_contexts_are_current(data):
        raise ValueError("full narration approval contains audio generated from stale full-run TTS context")
    approved_set_hash = _manifest_narration_audio_set_hash(data)
    if expected_audio_set_hash != approved_set_hash:
        raise NarrationRevisionConflict(
            "full narration audio set changed after it was loaded; reload and listen to the current set"
        )
    expected_item_ids = [str(target["selector"]) for target in _manifest_scene_targets(data)]
    if listen_evidence.audio_set_hash != approved_set_hash:
        raise NarrationRevisionConflict("full-run listen evidence belongs to a different narration audio set")
    if listen_evidence.item_ids != expected_item_ids:
        raise NarrationRevisionConflict("full-run listen evidence must cover every cut in canonical order")
    if [_model_dump(item) for item in listen_evidence.timeline] != [_model_dump(item) for item in timeline]:
        raise NarrationRevisionConflict("full-run listen evidence belongs to a different narration timeline")
    approved_timeline_hash = _apply_narration_approval_timeline(data, timeline)
    post_timeline_blockers = _narration_review_blockers(data, run_dir=run_dir)
    if post_timeline_blockers:
        raise NarrationRevisionConflict(
            "requested p740 timeline differs from the timing reviewed at p720; persist the timing first, "
            "rerun p720, and listen to the current full run: "
            + ", ".join(post_timeline_blockers[:20])
        )
    readiness = _narration_duration_readiness_for_data(
        run_dir,
        data,
        manifest_path=manifest_path,
    )
    if not readiness.get("audioReady"):
        missing = ", ".join(str(item.get("itemId") or "") for item in readiness.get("missingItems", [])[:20])
        raise ValueError("full narration approval requires current human-approved audio for every cut: " + (missing or "none"))
    if not readiness.get("durationPassed"):
        audit = readiness.get("audit")
        detail = (
            f" actual={getattr(audit, 'actual_seconds', 0)}s minimum={getattr(audit, 'minimum_seconds', 0)}s"
            if audit is not None
            else ""
        )
        raise ValueError("full narration approval requires the requested p740 timeline to pass" + detail)
    workflow = _dict_value(data.get("narration_workflow"))
    workflow["schema_version"] = "narration_run_workflow_v1"
    workflow["final_audio_review"] = {
        "status": "approved",
        "approved_audio_set_hash": approved_set_hash,
        "approved_timeline_hash": approved_timeline_hash,
        "approved_at": now_iso(),
        "approved_by": "frontend_human",
        "note": note.strip(),
        "listen_evidence": _model_dump(listen_evidence),
        "listen_evidence_hash": _full_json_hash(_model_dump(listen_evidence)),
    }
    data["narration_workflow"] = workflow
    _backup_run_file(run_dir, "video_manifest.md", label="before_narration_full_run_approve")
    transaction_paths = [
        manifest_path,
        run_dir / "state.txt",
        run_dir / "run_status.json",
        run_dir / "p000_index.md",
    ]
    before_transaction = {
        path: path.read_bytes() if path.is_file() else None
        for path in transaction_paths
    }
    try:
        _write_manifest_data(manifest_path, original_text, data)
        append_state_snapshot(
            run_dir / "state.txt",
            {
                **_narration_duration_state_updates(readiness),
                "review.duration_fit.note": "requested p740 timeline passed the measured duration gate",
                "status": "P750",
                "runtime.stage": "narration_audio_frontend_approved",
                "runtime.narration.phase": "done",
                "runtime.narration.approved_audio_set_hash": approved_set_hash,
                "runtime.narration.approved_timeline_hash": approved_timeline_hash,
                "slot.p720.status": "done",
                "slot.p730.status": "done",
                "slot.p740.status": "done",
                "slot.p750.status": "done",
                "slot.p750.note": "frontend explicitly approved the full narration track",
                "stage.narration.status": "done",
                "review.narration.status": "approved",
                "gate.narration_review": "required",
            },
        )
    except Exception:
        for path, previous_content in before_transaction.items():
            if previous_content is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_write_bytes(path, previous_content)
        raise
    audit = readiness.get("audit")
    return {
        "status": "approved",
        "approvedAudioSetHash": approved_set_hash,
        "approvedTimelineHash": approved_timeline_hash,
        "durationReady": True,
        "actualSeconds": float(getattr(audit, "actual_seconds", 0)) if audit is not None else None,
        "targetSeconds": float(getattr(audit, "target_seconds", 0)) if audit is not None else None,
    }


def _narration_min_duration_seconds(run_dir: Path, item_id: str) -> float | None:
    try:
        _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    except (FileNotFoundError, ValueError):
        return None
    target = _target_by_item_id(data, item_id)
    if target is None:
        return None
    node = target["cut"]
    audio = node.get("audio") if isinstance(node.get("audio"), dict) else {}
    narration = audio.get("narration") if isinstance(audio.get("narration"), dict) else {}
    output = str(narration.get("output") or "").strip()
    if not output:
        return None
    try:
        _validate_run_relative_audio_path(run_dir, output, must_exist=True)
    except ValueError:
        return None
    return _probe_media_duration_seconds(resolve_run_relative(run_dir, output))


def _generate_narration_file_blocking(run_dir: Path, request: NarrationGenerateItem) -> dict[str, Any]:
    _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    target = _target_by_item_id(data, request.item_id)
    if target is None:
        raise ValueError(f"video manifest target not found: {request.item_id}")
    output = request.output or _default_narration_output_for_target(target)
    _validate_run_relative_audio_path(run_dir, output, must_exist=False)
    destination = resolve_run_relative(run_dir, output)
    spoken_text = (request.tts_text or request.text or "").strip()
    if request.tool == "silent":
        _write_silence_audio(destination, float(request.duration_seconds or 1))
    elif request.tool == "elevenlabs":
        _generate_elevenlabs_audio(destination, spoken_text, request)
    elif request.tool in {"macos_say", "say"}:
        _generate_macos_say_audio(destination, spoken_text)
    else:
        raise ValueError(f"unsupported narration tool: {request.tool}")
    if not destination.is_file():
        raise RuntimeError("narration provider completed without writing an audio file")
    duration = _probe_media_duration_seconds(destination)
    debug_log = _write_narration_debug_log(
        run_dir=run_dir,
        item_id=request.item_id,
        destination=destination,
        request=request,
        duration_seconds=duration,
    )
    return {
        "itemId": request.item_id,
        "status": "completed",
        "path": destination.relative_to(run_dir).as_posix(),
        "durationSeconds": duration,
        "debugLog": debug_log.relative_to(run_dir).as_posix(),
        "source": request.tool,
    }


async def _generate_narration_one(run_dir: Path, req: NarrationGenerateItem) -> dict[str, Any]:
    async with _narration_generation_semaphore:
        try:
            return await asyncio.to_thread(_generate_narration_file_blocking, run_dir, req)
        except (HttpError, TimeoutError, ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
            _manifest_path, _original_text, data = _read_manifest_data(run_dir)
            target = _target_by_item_id(data, req.item_id)
            output = req.output or (_default_narration_output_for_target(target) if target else f"assets/audio/{_safe_artifact_id(req.item_id)}.mp3")
            destination = resolve_run_relative(run_dir, output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            debug_log = _write_narration_debug_log(
                run_dir=run_dir,
                item_id=req.item_id,
                destination=destination,
                request=req,
                error=str(exc),
            )
            return {
                "itemId": req.item_id,
                "status": "failed",
                "path": None,
                "durationSeconds": None,
                "error": str(exc),
                "debugLog": debug_log.relative_to(run_dir).as_posix(),
                "source": req.tool,
            }


def _concat_list_line(path: Path) -> str:
    return "file '" + str(path).replace("'", "'\\''") + "'"


def _render_asset_dir(run_dir: Path, kind: str) -> Path:
    path = run_dir / "assets" / "test" / f"render_{kind}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _require_prepared_media_duration(path: Path, *, expected_seconds: float, label: str) -> None:
    actual_seconds = _probe_media_duration_seconds(path)
    if actual_seconds is None:
        raise ValueError(f"{label} duration could not be measured after p750 render preparation: {path}")
    if abs(float(actual_seconds) - float(expected_seconds)) > 0.35:
        raise ValueError(
            f"{label} duration does not match the p750 timeline: "
            f"actual={actual_seconds:.3f}s expected={expected_seconds:.3f}s"
        )


def _prepare_render_video_clip(
    run_dir: Path,
    source: Path,
    item: RenderInputItem,
    *,
    strict: bool = False,
) -> Path:
    duration = max(1, int(item.video_duration_seconds))
    if not shutil.which("ffmpeg"):
        if strict:
            _require_prepared_media_duration(
                source,
                expected_seconds=float(duration),
                label=f"{item.item_id} video",
            )
        return source
    output = _render_asset_dir(run_dir, "video") / f"{_safe_artifact_id(item.item_id)}_{duration:03d}s.mp4"
    try:
        subprocess.run(
            [
                shutil.which("ffmpeg") or "ffmpeg",
                "-hide_banner",
                "-y",
                "-i",
                str(source),
                "-t",
                str(duration),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        if strict:
            raise ValueError(f"failed to prepare p750 video clip: {item.item_id}: {exc}") from exc
        return source
    prepared = output if output.is_file() else source
    if strict:
        if prepared == source:
            raise ValueError(f"p750 video preparation produced no output: {item.item_id}")
        _require_prepared_media_duration(
            prepared,
            expected_seconds=float(duration),
            label=f"{item.item_id} video",
        )
    return prepared


def _prepare_render_narration(
    run_dir: Path,
    source: Path,
    item: RenderInputItem,
    *,
    strict: bool = False,
) -> Path:
    offset = max(0.0, float(item.narration_offset_seconds))
    duration = max(1.0, float(item.video_duration_seconds))
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        if strict:
            if offset > 0:
                raise ValueError(f"ffmpeg is required to apply the approved narration offset: {item.item_id}")
            _require_prepared_media_duration(
                source,
                expected_seconds=duration,
                label=f"{item.item_id} narration",
            )
        return source
    safe_id = _safe_artifact_id(item.item_id)
    centiseconds = int(round(offset * 100))
    duration_cs = int(round(duration * 100))
    output = _render_asset_dir(run_dir, "audio") / f"{safe_id}_offset_{centiseconds:04d}_duration_{duration_cs:04d}.mp3"
    if offset <= 0:
        command = [
            ffmpeg,
            "-hide_banner",
            "-y",
            "-i",
            str(source),
            "-filter_complex",
            f"[0:a]apad,atrim=duration={duration:.3f}[a]",
            "-map",
            "[a]",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(output),
        ]
    else:
        command = [
            ffmpeg,
            "-hide_banner",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            f"{offset:.3f}",
            "-i",
            str(source),
            "-filter_complex",
            f"[0:a][1:a]concat=n=2:v=0:a=1[a0];[a0]apad,atrim=duration={duration:.3f}[a]",
            "-map",
            "[a]",
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(output),
        ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        if strict:
            raise ValueError(f"failed to prepare p750 narration: {item.item_id}: {exc}") from exc
        return source
    prepared = output if output.is_file() else source
    if strict:
        if prepared == source:
            raise ValueError(f"p750 narration preparation produced no output: {item.item_id}")
        _require_prepared_media_duration(
            prepared,
            expected_seconds=duration,
            label=f"{item.item_id} narration",
        )
    return prepared


def _silent_render_narration_path(run_dir: Path, item: RenderInputItem) -> str:
    safe_id = _safe_artifact_id(item.item_id)
    duration_cs = int(round(max(1.0, float(item.video_duration_seconds)) * 100))
    rel = f"assets/audio/{safe_id}/{safe_id}_intentional_silence_{duration_cs:04d}.mp3"
    _validate_run_relative_audio_path(run_dir, rel, must_exist=False)
    destination = resolve_run_relative(run_dir, rel)
    if not destination.is_file():
        try:
            _write_silence_audio(destination, max(1.0, float(item.video_duration_seconds)))
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc
    return rel


def _freeze_render_inputs(run_dir: Path, req: RenderFreezeRequest, *, snapshot_id: str | None = None) -> dict[str, Any]:
    _validate_run_relative_render_output(run_dir, req.output)
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    manifest_targets = _manifest_scene_targets(data)
    revision_aware = bool(_revision_aware_narration_items(data))
    approved_audio_set_hash = ""
    approved_timeline_hash = ""
    if revision_aware:
        _require_narration_ready_for_video(run_dir)
        final_review = _dict_value(_dict_value(data.get("narration_workflow")).get("final_audio_review"))
        approved_audio_set_hash = str(final_review.get("approved_audio_set_hash") or "")
        approved_timeline_hash = str(final_review.get("approved_timeline_hash") or "")
        if not approved_audio_set_hash or not approved_timeline_hash:
            raise NarrationRevisionConflict("revision-aware render requires immutable p750 approval hashes")
        expected_item_ids = [str(target["selector"]) for target in manifest_targets]
        requested_item_ids = [str(item.item_id) for item in req.items]
        if requested_item_ids != expected_item_ids:
            raise NarrationRevisionConflict(
                "revision-aware render inputs must include every manifest cut exactly once in canonical order"
            )
        for target, item in zip(manifest_targets, req.items, strict=True):
            node = _dict_value(target["cut"])
            render = _dict_value(node.get("render"))
            video_generation = _dict_value(node.get("video_generation"))
            approved_duration = _int_value(
                render.get("video_duration_seconds")
                or video_generation.get("duration_seconds")
                or 0
            )
            approved_offset = round(_float_value(render.get("narration_offset_seconds") or 0), 3)
            if (
                item.video_duration_seconds != approved_duration
                or round(float(item.narration_offset_seconds), 3) != approved_offset
            ):
                raise NarrationRevisionConflict(
                    f"render timeline differs from the p750-approved timeline: {item.item_id}"
                )
    _backup_run_file(run_dir, "video_manifest.md", label="before_render_freeze")
    clips: list[Path] = []
    narrations: list[Path] = []
    warnings: list[str] = []
    updated: list[str] = []
    request_by_id = {str(item.item_id): item for item in req.items}
    targets_by_scene_index: dict[int, list[dict[str, Any]]] = {}
    for target in manifest_targets:
        targets_by_scene_index.setdefault(int(target["scene_index"]), []).append(target)

    render_unit_issues = _render_unit_timeline_issues(data)
    if render_unit_issues:
        raise NarrationRevisionConflict("invalid render-unit timeline: " + "; ".join(render_unit_issues[:20]))

    for scene_index, scene in enumerate(_list_value(data.get("scenes"))):
        scene_targets = targets_by_scene_index.get(scene_index, [])
        if not scene_targets:
            continue
        render_units = [unit for unit in _list_value(scene.get("render_units")) if isinstance(unit, dict)]
        if render_units:
            scene_id = normalize_dotted_id(scene.get("scene_id")) or str(scene_index + 1)
            for unit_index, unit in enumerate(render_units):
                unit_id = normalize_dotted_id(unit.get("unit_id")) or str(unit_index + 1)
                unit_selector = f"scene{scene_id}_unit{unit_id}"
                generation = _dict_value(unit.get("video_generation"))
                video_path = (
                    _candidate_video_output_for_item(run_dir, unit_selector)
                    or str(generation.get("output") or "").strip()
                )
                _assert_current_video_candidate_path(
                    run_dir,
                    unit_selector,
                    video_path,
                )
                _validate_run_relative_video_path(run_dir, video_path, must_exist=True)
                duration = _int_value(generation.get("duration_seconds"))
                if duration <= 0:
                    raise NarrationRevisionConflict(f"render unit has no approved duration: {unit_selector}")
                unit_item = RenderInputItem(
                    item_id=unit_selector,
                    video_path=video_path,
                    narration_path=None,
                    video_duration_seconds=duration,
                    narration_offset_seconds=0,
                )
                unit_source = resolve_run_relative(run_dir, video_path)
                clips.append(
                    _prepare_render_video_clip(run_dir, unit_source, unit_item, strict=True)
                    if revision_aware
                    else _prepare_render_video_clip(run_dir, unit_source, unit_item)
                )
                generation["output"] = video_path
                unit["video_generation"] = generation
            warnings.append(
                f"scene{scene_id}: using {len(render_units)} render unit video clip(s) for the approved cut timeline"
            )
            continue
        for target in scene_targets:
            selector = str(target["selector"])
            item = request_by_id.get(selector)
            if item is None:
                raise NarrationRevisionConflict(f"render request is missing canonical item: {selector}")
            node = _dict_value(target["cut"])
            video_generation = _dict_value(node.get("video_generation"))
            video_path = (
                item.video_path
                or _candidate_video_output_for_item(run_dir, selector)
                or str(video_generation.get("output") or "")
            )
            _assert_current_video_candidate_path(run_dir, selector, video_path)
            _validate_run_relative_video_path(run_dir, video_path, must_exist=True)
            video_source = resolve_run_relative(run_dir, video_path)
            clips.append(
                _prepare_render_video_clip(run_dir, video_source, item, strict=True)
                if revision_aware
                else _prepare_render_video_clip(run_dir, video_source, item)
            )
            video_generation["duration_seconds"] = item.video_duration_seconds
            video_generation["output"] = video_path
            node["video_generation"] = video_generation
            render = _dict_value(node.get("render"))
            render["video_path"] = video_path
            node["render"] = render

    for item in req.items:
        target = _target_by_item_id(data, item.item_id)
        if target is None:
            raise ValueError(f"video manifest target not found: {item.item_id}")
        node = target["cut"]
        audio = node.get("audio") if isinstance(node.get("audio"), dict) else {}
        narration = audio.get("narration") if isinstance(audio.get("narration"), dict) else {}
        approved_narration_path = str(narration.get("output") or "")
        if revision_aware:
            is_silent = str(narration.get("tool") or "").strip().lower() == "silent"
            if is_silent and item.narration_path:
                raise NarrationRevisionConflict("revision-aware silent render audio is materialized by the server")
            if not is_silent and item.narration_path and item.narration_path != approved_narration_path:
                raise NarrationRevisionConflict(
                    f"render narration path differs from the p750-approved output: {item.item_id}"
                )
            narration_path = "" if is_silent else approved_narration_path
        else:
            narration_path = item.narration_path or approved_narration_path
        if _narration_has_confirmed_silence(narration) and not narration_path:
            narration_path = _silent_render_narration_path(run_dir, item)
            if not revision_aware:
                narration["output"] = narration_path
                audio["narration"] = narration
                node["audio"] = audio
        _validate_run_relative_audio_path(run_dir, narration_path, must_exist=True)
        narration_source = resolve_run_relative(run_dir, narration_path)
        audio_duration = _probe_media_duration_seconds(narration_source)
        if audio_duration is not None and item.video_duration_seconds < math.ceil(audio_duration + item.narration_offset_seconds):
            warnings.append(
                f"{item.item_id}: narration starts at {item.narration_offset_seconds:.1f}s and may exceed {item.video_duration_seconds}s clip"
            )
        render = node.get("render") if isinstance(node.get("render"), dict) else {}
        render.update(
            {
                "narration_path": narration_path,
                "video_duration_seconds": item.video_duration_seconds,
                "narration_offset_seconds": item.narration_offset_seconds,
            }
        )
        node["render"] = render
        narrations.append(
            _prepare_render_narration(run_dir, narration_source, item, strict=True)
            if revision_aware
            else _prepare_render_narration(run_dir, narration_source, item)
        )
        updated.append(item.item_id)
    if snapshot_id:
        list_dir = _frontend_review_dir(run_dir) / "render_inputs"
        list_dir.mkdir(parents=True, exist_ok=True)
        safe_snapshot = re.sub(r"[^A-Za-z0-9_.-]+", "_", snapshot_id).strip("._") or _now_stamp()
        clips_path = list_dir / f"{safe_snapshot}_video_clips.txt"
        narration_path = list_dir / f"{safe_snapshot}_video_narration_list.txt"
    else:
        clips_path = run_dir / "video_clips.txt"
        narration_path = run_dir / "video_narration_list.txt"
    review_dir = _frontend_review_dir(run_dir)
    review_dir.mkdir(parents=True, exist_ok=True)
    plan_path = review_dir / (f"render_plan_{safe_snapshot}.json" if snapshot_id else "render_plan_latest.json")
    clips_text = "\n".join(_concat_list_line(path) for path in clips) + ("\n" if clips else "")
    narration_text = "\n".join(_concat_list_line(path) for path in narrations) + ("\n" if narrations else "")
    plan_text = (
        json.dumps(
            {
                "output": req.output,
                "clips": [str(path) for path in clips],
                "narrations": [str(path) for path in narrations],
                "items": [_model_dump(item) for item in req.items],
                "approvedAudioSetHash": approved_audio_set_hash,
                "approvedTimelineHash": approved_timeline_hash,
                "warnings": warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    transaction_paths = [
        manifest_path,
        clips_path,
        narration_path,
        plan_path,
        run_dir / "state.txt",
        run_dir / "run_status.json",
        run_dir / "p000_index.md",
    ]
    before_transaction = {
        path: path.read_bytes() if path.is_file() else None
        for path in transaction_paths
    }
    try:
        _write_manifest_data(manifest_path, original_text, data)
        _atomic_write_text(clips_path, clips_text)
        _atomic_write_text(narration_path, narration_text)
        _atomic_write_text(plan_path, plan_text)
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "status": "P910",
                "runtime.stage": "render_inputs_frozen",
                "slot.p910.status": "done",
                "slot.p910.note": "frontend render inputs frozen",
                "artifact.video_clips": str(clips_path.resolve()),
                "artifact.video_narration_list": str(narration_path.resolve()),
                "review.frontend.render.plan": plan_path.relative_to(run_dir).as_posix(),
            },
        )
    except Exception:
        for path, previous_content in before_transaction.items():
            if previous_content is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_write_bytes(path, previous_content)
        raise
    return {
        "runId": run_dir.name,
        "status": "frozen",
        "updated": updated,
        "warnings": warnings,
        "clipList": clips_path.relative_to(run_dir).as_posix(),
        "narrationList": narration_path.relative_to(run_dir).as_posix(),
        "planPath": plan_path.relative_to(run_dir).as_posix(),
        "output": req.output,
        "approvedAudioSetHash": approved_audio_set_hash,
        "approvedTimelineHash": approved_timeline_hash,
    }


def _require_frozen_render_narration_current(run_dir: Path, freeze_result: dict[str, Any]) -> None:
    expected_audio_set_hash = str(freeze_result.get("approvedAudioSetHash") or "")
    expected_timeline_hash = str(freeze_result.get("approvedTimelineHash") or "")
    if not expected_audio_set_hash and not expected_timeline_hash:
        return
    _require_narration_ready_for_video(run_dir)
    _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    final_review = _dict_value(_dict_value(data.get("narration_workflow")).get("final_audio_review"))
    if (
        str(final_review.get("approved_audio_set_hash") or "") != expected_audio_set_hash
        or str(final_review.get("approved_timeline_hash") or "") != expected_timeline_hash
    ):
        raise NarrationRevisionConflict(
            "narration audio set or timeline changed while final render was running; rendered output is stale"
        )


def _apply_final_video_duration_gate(run_dir: Path, out_path: Path) -> dict[str, Any]:
    _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    metadata = _dict_value(data.get("video_metadata"))
    try:
        target_seconds = normalize_target_duration(metadata.get("target_duration_seconds"))
    except ValueError as exc:
        raise ValueError(f"final video duration target is invalid: {exc}") from exc
    actual_seconds = _probe_media_duration_seconds(out_path)
    if actual_seconds is None:
        raise ValueError("final video duration could not be measured with ffprobe")
    duration_audit = audit_duration(
        target_seconds=target_seconds,
        actual_seconds=actual_seconds,
        measurement_layer="frontend_final_video_ffprobe",
    )
    state_updates = {
        "review.final.duration_fit.status": duration_audit.status,
        "review.final.duration_fit.target_seconds": str(duration_audit.target_seconds),
        "review.final.duration_fit.minimum_seconds": _duration_state_value(duration_audit.minimum_seconds),
        "review.final.duration_fit.actual_seconds": _duration_state_value(duration_audit.actual_seconds),
        "review.final.duration_fit.ratio": f"{duration_audit.ratio:.6f}",
        "review.final.duration_fit.measurement_layer": duration_audit.measurement_layer,
        "review.final.duration_fit.at": now_iso(),
        "artifact.final_video": str(out_path.resolve()),
    }
    if not duration_audit.passed:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                **state_updates,
                "runtime.stage": "final_render_duration_failed",
                "slot.p920.status": "failed",
                "slot.p920.note": "final video is shorter than 80% of target",
                "slot.p930.status": "blocked",
                "slot.p930.note": "final QA blocked by duration fit",
                "review.final.status": "changes_requested",
            },
        )
        raise ValueError(
            "final video duration must be at least 80% of target: "
            f"actual={_duration_state_value(duration_audit.actual_seconds)}s "
            f"minimum={_duration_state_value(duration_audit.minimum_seconds)}s"
        )

    append_state_snapshot(
        run_dir / "state.txt",
        {
            **state_updates,
            "status": "P930",
            "runtime.stage": "final_render_ready_for_qa",
            "slot.p920.status": "done",
            "slot.p920.note": "final video rendered and duration gate passed",
            "slot.p930.status": "awaiting_approval",
            "slot.p930.note": "final QA ready in frontend",
            "review.final.status": "pending",
        },
    )
    return duration_audit.to_dict()


async def _run_final_render(run_dir: Path, req: FinalRenderRequest, freeze_result: dict[str, Any]) -> dict[str, Any]:
    out_path = resolve_run_relative(run_dir, req.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "bash",
        str(ROOT / "scripts" / "render-video.sh"),
        "--clip-list",
        str(run_dir / str(freeze_result["clipList"])),
        "--narration-list",
        str(run_dir / str(freeze_result["narrationList"])),
        "--out",
        str(out_path),
    ]
    if req.reencode:
        command.append("--reencode")
    proc = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=3600)
    if proc.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip() or stdout.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"render-video.sh exited with status {proc.returncode}")
    async with _serialized_run_write(run_dir, "run_artifacts"):
        try:
            _require_frozen_render_narration_current(run_dir, freeze_result)
        except NarrationRevisionConflict:
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    "runtime.stage": "final_render_narration_stale",
                    "slot.p920.status": "blocked",
                    "slot.p920.note": "rendered output used a stale narration approval snapshot",
                    "slot.p930.status": "blocked",
                    "slot.p930.note": "final QA requires rerendering the current p750 narration set",
                    "review.final.status": "changes_requested",
                    "artifact.stale_final_video": str(out_path.resolve()),
                },
            )
            raise
        final_duration_audit = _apply_final_video_duration_gate(run_dir, out_path)
    return {
        **freeze_result,
        "status": "rendered",
        "finalOutput": out_path.relative_to(run_dir).as_posix(),
        "durationAudit": final_duration_audit,
        "stdout": stdout.decode("utf-8", errors="replace").strip(),
    }


def _default_video_prompt(item: FrontendReviewItem) -> str:
    if item.video_prompt and item.video_prompt.strip():
        return item.video_prompt.strip()
    return ""


def _video_prompt_for_request(item: FrontendReviewItem) -> str:
    return _require_no_code_fence(_default_video_prompt(item), field="video_prompt")


def _video_reference_content_sha256(
    run_dir: Path | None,
    references: Iterable[str],
) -> dict[str, str]:
    if run_dir is None:
        return {}
    bindings: dict[str, str] = {}
    for raw in references:
        reference = str(raw or "").strip()
        if not reference or reference in bindings:
            continue
        try:
            path = resolve_run_relative(run_dir, reference)
        except ValueError:
            continue
        if not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        bindings[reference] = digest.hexdigest()
    return bindings


def _scene_visualizable_action_for_video_review(scene: dict[str, Any]) -> Any:
    """Return scene-wide action context for review, never provider prose."""

    top_level = scene.get("visualizable_action")
    if isinstance(top_level, str) and top_level.strip():
        return top_level
    if not isinstance(top_level, str) and top_level:
        return top_level
    return _dict_value(scene.get("scene_intent")).get(
        "review_only_visualizable_action"
    )


def _compile_frontend_video_prompt_payload(
    *,
    data: dict[str, Any],
    item: FrontendReviewItem,
    run_dir: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    target = _video_target_by_item_id(data, item.item_id)
    if target is None:
        raise ValueError(f"video manifest target not found: {item.item_id}")
    node = target["cut"]
    scene = target["scene"]
    video_generation = node.get("video_generation") if isinstance(node.get("video_generation"), dict) else {}
    metadata = data.get("video_metadata") if isinstance(data.get("video_metadata"), dict) else {}
    source_prompt = _video_prompt_for_request(item)
    if not source_prompt:
        source_prompt = str(
            video_generation.get("prompt_authoring_source")
            or video_generation.get("source_motion_prompt")
            or ""
        ).strip()
    tool = item.video_tool or str(video_generation.get("tool") or "kling_3_0")
    input_contract = (
        _render_unit_video_input_contract(_dict_value(node))
        if target.get("is_render_unit")
        else {}
    )
    if input_contract.get("input_mode") == "reference_images":
        first_frame = ""
    else:
        first_frame = _default_first_frame(item) or str(
            video_generation.get("first_frame")
            or video_generation.get("input_image")
            or ""
        )
    if item.video_last_reference is None:
        last_frame = str(video_generation.get("last_frame") or "").strip()
    else:
        # ``None`` means the field was not edited; an explicit empty string
        # means the caller intentionally cleared the end-frame constraint.
        last_frame = item.video_last_reference.strip()
    execution_options = _server_video_execution_options(
        tool=tool,
        has_first_frame=bool(first_frame),
        has_reference_images=bool(item.video_references),
    )
    reference_content_sha256 = _video_reference_content_sha256(
        run_dir,
        [first_frame, last_frame, *item.video_references],
    )
    if reference_content_sha256:
        execution_options["reference_content_sha256"] = reference_content_sha256
    payload = compile_video_api_prompt_v1(
        cut_contract=_video_contract_for_server_target(target),
        scene_contract=node.get("scene_contract") if isinstance(node.get("scene_contract"), dict) else {},
        video_generation=video_generation,
        source_prompt=source_prompt,
        story_time=str(metadata.get("time") or "").strip(),
        time_of_day=str(scene.get("time_of_day") or "").strip(),
        tool=tool,
        first_frame=first_frame,
        last_frame=last_frame,
        duration_seconds=item.video_duration_seconds or video_generation.get("duration_seconds") or 8,
        references=item.video_references,
        reference_roles=(
            _list_value(input_contract.get("reference_roles"))
            if input_contract
            else None
        ),
        quality=item.video_quality or str(video_generation.get("quality") or "1080p"),
        aspect_ratio=item.video_aspect_ratio
        or str(video_generation.get("aspect_ratio") or "16:9"),
        execution_options=execution_options,
        direction_notes=video_generation.get("direction_notes") or (),
        continuity_notes=video_generation.get("continuity_notes") or (),
        first_frame_visual_plan=_first_frame_visual_plan_for_server_target(
            target
        ),
        review_only_dependencies=_video_review_dependencies_for_server_target(
            target
        ),
        scene_time_of_day_visual_basis=scene.get(
            "time_of_day_visual_basis"
        ),
        scene_location_mode=str(scene.get("location_mode") or "").strip(),
        scene_location_sequence=_list_value(scene.get("location_sequence")),
        scene_location_segments=[
            dict(value)
            for value in _list_value(scene.get("location_segments"))
            if isinstance(value, dict)
        ],
        scene_visualizable_action=(
            _scene_visualizable_action_for_video_review(scene)
        ),
    )
    return target, payload


def _frontend_video_payloads(
    run_dir: Path,
    items: list[FrontendReviewItem],
) -> dict[str, dict[str, Any]]:
    _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    return {
        item.item_id: _compile_frontend_video_prompt_payload(
            data=data,
            item=item,
            run_dir=run_dir,
        )[1]
        for item in items
    }


def _effective_video_materialization_items(
    run_dir: Path,
    items: list[FrontendReviewItem],
) -> list[FrontendReviewItem]:
    _manifest_path, _original_text, manifest_data = _read_manifest_data(run_dir)
    targets_by_id = {
        str(target["selector"]): target
        for target in _manifest_video_targets(manifest_data)
    }
    final_review = _dict_value(
        _dict_value(manifest_data.get("narration_workflow")).get(
            "final_audio_review"
        )
    )
    approved_timeline_locked = bool(
        final_review.get("status") == "approved"
        and str(final_review.get("approved_timeline_hash") or "")
        == _manifest_narration_timeline_hash(manifest_data)
    )
    effective: list[FrontendReviewItem] = []
    for item in items:
        target = targets_by_id.get(item.item_id)
        node = _dict_value(target.get("cut")) if target else {}
        generation = _dict_value(node.get("video_generation"))
        render = _dict_value(node.get("render"))
        canonical_render_duration = _int_value(
            render.get("video_duration_seconds") or 0
        )
        current_timeline_duration = _int_value(
            canonical_render_duration
            or generation.get("duration_seconds")
            or 0
        )
        requested = int(
            item.video_duration_seconds
            or canonical_render_duration
            or generation.get("duration_seconds")
            or 8
        )
        if (
            target
            and not target.get("is_render_unit")
            and item.video_duration_seconds is not None
            and canonical_render_duration > 0
            and requested != canonical_render_duration
        ):
            raise ValueError(
                f"{item.item_id}: duration {requested}s differs from canonical render timeline duration "
                f"{canonical_render_duration}s"
            )
        if (
            target
            and not target.get("is_render_unit")
            and approved_timeline_locked
            and current_timeline_duration > 0
            and requested != current_timeline_duration
        ):
            raise ValueError(
                f"{item.item_id}: duration {requested}s differs from p750-approved canonical render "
                f"timeline duration {current_timeline_duration}s"
            )
        if target and target.get("is_render_unit"):
            scene = _dict_value(target.get("scene"))
            source_ids = [
                normalize_dotted_id(value)
                for value in _list_value(node.get("source_cut_ids"))
            ]
            if not source_ids or any(source_id is None for source_id in source_ids):
                raise ValueError(
                    f"{item.item_id}: render unit source_cut_ids must be a non-empty valid list"
                )
            cuts_by_id = {
                normalize_dotted_id(cut.get("cut_id")) or str(index): cut
                for index, cut in enumerate(_list_value(scene.get("cuts")), start=1)
                if isinstance(cut, dict) and not _is_non_renderable_manifest_node(cut)
            }
            source_durations: list[int] = []
            for source_id in source_ids:
                source_cut = cuts_by_id.get(source_id or "")
                if source_cut is None:
                    raise ValueError(
                        f"{item.item_id}: render unit has an unknown source cut {source_id!r}"
                    )
                source_render = _dict_value(source_cut.get("render"))
                source_generation = _dict_value(
                    source_cut.get("video_generation")
                )
                duration = _int_value(
                    source_render.get("video_duration_seconds")
                    or source_generation.get("duration_seconds")
                    or source_cut.get("duration_seconds")
                    or 0
                )
                if duration <= 0:
                    raise ValueError(
                        f"{item.item_id}: source cut {source_id} duration is missing"
                    )
                source_durations.append(duration)
            expected = sum(source_durations)
            if item.video_duration_seconds is not None and requested != expected:
                raise ValueError(
                    f"{item.item_id}: duration {requested}s must equal source-cut total {expected}s"
                )
            requested = expected
            input_contract = _render_unit_video_input_contract(node)
            if input_contract.get("input_mode") == "reference_images":
                if (
                    item.video_first_reference is not None
                    and item.video_first_reference.strip()
                ):
                    raise ValueError(
                        f"{item.item_id}: reference-image render unit must keep first frame empty"
                    )
                if (
                    item.video_last_reference is not None
                    and item.video_last_reference.strip()
                ):
                    raise ValueError(
                        f"{item.item_id}: reference-image render unit must keep last frame empty"
                    )
                required_references = [
                    str(value).strip()
                    for value in _list_value(
                        input_contract.get("required_references")
                    )
                    if str(value).strip()
                ]
                references_were_submitted = "video_references" in getattr(
                    item, "model_fields_set", set()
                )
                submitted_references = [
                    str(value).strip()
                    for value in item.video_references
                    if str(value).strip()
                ]
                if (
                    references_were_submitted
                    and submitted_references != required_references
                ):
                    raise ValueError(
                        f"{item.item_id}: video_references must exactly preserve the ordered "
                        "required render-unit references"
                    )
                item = item.model_copy(
                    update={
                        "video_first_reference": "",
                        "video_last_reference": "",
                        "video_references": required_references,
                    }
                )
        narration_duration = _narration_min_duration_seconds(run_dir, item.item_id)
        duration = max(requested, math.ceil(narration_duration or 0), 1)
        if (
            target
            and not target.get("is_render_unit")
            and canonical_render_duration > 0
            and duration != canonical_render_duration
        ):
            raise ValueError(
                f"{item.item_id}: effective duration {duration}s differs from canonical render timeline "
                f"duration {canonical_render_duration}s"
            )
        if target and target.get("is_render_unit") and duration != requested:
            raise ValueError(
                f"{item.item_id}: effective duration {duration}s must equal source-cut total "
                f"{requested}s; update the canonical cut timeline before materialization"
            )
        effective_item = item.model_copy(
            update={"video_duration_seconds": duration}
        )
        selected_tool = str(
            effective_item.video_tool
            or generation.get("tool")
            or "kling_3_0"
        ).strip()
        input_contract = (
            _render_unit_video_input_contract(node)
            if target and target.get("is_render_unit")
            else {}
        )
        reference_image_mode = (
            input_contract.get("input_mode") == "reference_images"
        )
        first_reference = (
            ""
            if reference_image_mode
            else (
                _default_first_frame(effective_item)
                or str(
                    generation.get("first_frame")
                    or generation.get("input_image")
                    or ""
                ).strip()
            )
        )
        last_reference = (
            ""
            if reference_image_mode
            else (
                str(generation.get("last_frame") or "").strip()
                if effective_item.video_last_reference is None
                else effective_item.video_last_reference.strip()
            )
        )
        references = [
            str(value).strip()
            for value in effective_item.video_references
            if str(value).strip()
        ]
        provider_options = _server_video_execution_options(
            tool=selected_tool,
            has_first_frame=bool(first_reference),
            has_reference_images=bool(references),
        )
        input_mode = (
            "first_last_frame"
            if first_reference and last_reference
            else "image_to_video"
            if first_reference
            else "reference_to_video"
            if references
            else "text_to_video"
        )
        capability_issues = _video_provider_capability_issues(
            label=item.item_id,
            tool=selected_tool,
            model=str(provider_options.get("model") or "").strip(),
            input_mode=input_mode,
            duration_seconds=duration,
            reference_count=len(references),
        )
        if capability_issues:
            raise ValueError("; ".join(capability_issues))
        effective.append(effective_item)
    return effective


def _default_video_output(item: FrontendReviewItem) -> str:
    if item.output:
        source = Path(item.output)
        return (source.parent / f"{source.stem}_video.mp4").as_posix()
    return f"assets/scenes/{item.item_id}/{item.item_id}.mp4"


def _default_first_frame(item: FrontendReviewItem) -> str:
    return (
        (item.video_first_reference or "").strip()
        or (item.selected_candidate_path or "").strip()
        or (item.existing_image or "").strip()
        or (item.output or "").strip()
    )


def _require_asset_video_output(run_dir: Path, output: str) -> Path:
    _validate_run_relative_asset_video_path(run_dir, output)
    target = resolve_run_relative(run_dir, output)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _write_video_prompt_design(
    *,
    run_dir: Path,
    review_path: Path,
    items: list[FrontendReviewItem],
) -> Path:
    existing_items = {item.id: item for item in load_request_items(run_dir, "scene")}
    payloads = _frontend_video_payloads(run_dir, items)
    lines = [
        "# Frontend Video Prompt Design",
        "",
        f"- review: `{review_path.relative_to(run_dir).as_posix()}`",
        f"- saved_at: `{_now_stamp()}`",
        "",
        "## Review Summary",
        "",
    ]
    for item in items:
        item_id = _require_markdown_scalar(item.item_id, field="item_id")
        source_prompt = _video_prompt_for_request(item)
        payload = payloads[item.item_id]
        prompt = str(payload.get("prompt") or "")
        original = existing_items.get(item.item_id)
        prompt_changed = bool(original and item.prompt.strip() and item.prompt.strip() != original.prompt.strip())
        references_changed = bool(original and sorted(item.references) != sorted(original.references))
        selected = (item.selected_candidate_path or "").strip()
        lines.extend(
            [
                f"### {item_id}",
                "",
                f"- output: `{item.output or ''}`",
                f"- selected_candidate: `{selected}`",
                f"- existing_image: `{item.existing_image or ''}`",
                f"- prompt_changed: `{str(prompt_changed).lower()}`",
                f"- references_changed: `{str(references_changed).lower()}`",
                f"- video_quality: `{item.video_quality or '1080p'}`",
                f"- video_aspect_ratio: `{item.video_aspect_ratio or '16:9'}`",
                f"- video_duration_seconds: `{item.video_duration_seconds or 8}`",
                f"- first_frame: `{_default_first_frame(item)}`",
                f"- last_frame: `{item.video_last_reference or ''}`",
                f"- prompt_policy_version: `{payload['policy_version']}`",
                f"- compiler_version: `{payload['compiler_version']}`",
                f"- prompt_sha256: `{payload['sha256']}`",
                "- selected_references:",
            ]
        )
        for ref in item.references:
            lines.append(f"  - `{ref}`")
        if not item.references:
            lines.append("  - `[]`")
        lines.extend(["- video_references:"])
        for ref in item.video_references:
            lines.append(f"  - `{ref}`")
        if not item.video_references:
            lines.append("  - `[]`")
        lines.extend(
            [
                "",
                "```prompt_authoring_source",
                source_prompt,
                "```",
                "",
                "```video_prompt",
                prompt,
                "```",
                "",
            ]
        )
    path = _frontend_review_dir(run_dir) / "video_prompt_design.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _video_generation_request_section(run_dir: Path, item: FrontendReviewItem) -> tuple[str, str]:
    item_id = _require_markdown_scalar(item.item_id, field="item_id")
    video_tool = _require_markdown_scalar(item.video_tool or "kling_3_0", field="video_tool")
    video_quality = _require_markdown_scalar(item.video_quality or "1080p", field="video_quality")
    video_aspect_ratio = _require_markdown_scalar(item.video_aspect_ratio or "16:9", field="video_aspect_ratio")
    payload = _frontend_video_payloads(run_dir, [item])[item.item_id]
    prompt = str(payload.get("prompt") or "")
    _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    target = _video_target_by_item_id(data, item.item_id)
    target_node = _dict_value(target.get("cut")) if target is not None else {}
    video_generation = _dict_value(target_node.get("video_generation"))
    output = str(video_generation.get("output") or "").strip() or _default_video_output(
        item
    )
    _require_asset_video_output(run_dir, output)
    input_contract = (
        _render_unit_video_input_contract(target_node)
        if target is not None and target.get("is_render_unit")
        else {}
    )
    reference_image_mode = input_contract.get("input_mode") == "reference_images"
    first_frame = "" if reference_image_mode else _default_first_frame(item)
    last_frame = (
        "" if reference_image_mode else (item.video_last_reference or "").strip()
    )
    for frame in [first_frame, last_frame, *item.video_references]:
        if frame:
            _validate_run_relative_image_path(run_dir, frame, must_exist=False)
    refs = list(dict.fromkeys([ref for ref in item.video_references if ref.strip()]))
    negative_prompt = str(payload.get("negative_prompt") or "")
    lines = [
        f"## {item_id}",
        "",
        f"- tool: `{video_tool}`",
        f"- output: `{output}`",
        f"- duration_seconds: `{item.video_duration_seconds or 8}`",
        f"- quality: `{video_quality}`",
        f"- resolution: `{video_quality}`",
        f"- aspect_ratio: `{video_aspect_ratio}`",
        f"- first_frame: `{first_frame}`",
        f"- prompt_policy_version: `{payload['policy_version']}`",
        f"- compiler_version: `{payload['compiler_version']}`",
        f"- source_digest: `{payload['source_digest']}`",
        f"- prompt_sha256: `{payload['sha256']}`",
        f"- negative_prompt_sha256: `{hashlib.sha256(negative_prompt.encode('utf-8')).hexdigest()}`",
        f"- references_digest: `{sha256_canonical_json(refs)}`",
    ]
    if last_frame:
        lines.append(f"- last_frame: `{last_frame}`")
    lines.append("- source_cuts:")
    lines.append(f"  - `{item.item_id}`")
    if refs:
        lines.append("- references:")
        for ref in refs:
            lines.append(f"  - `{ref}`")
    lines.extend(
        [
            "",
            "```video_prompt",
            prompt,
            "```",
            "",
            "```negative_prompt",
            negative_prompt,
            "```",
        ]
    )
    return item_id, "\n".join(lines)


def _split_video_request_sections(text: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
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


def _reviewed_video_request_binding(run_dir: Path, item_id: str) -> dict[str, str]:
    path = run_dir / "video_generation_requests.md"
    if not path.is_file():
        raise ValueError("reviewed video generation request is missing")
    _prefix, sections = _split_video_request_sections(path.read_text(encoding="utf-8"))
    matches = [lines for title, lines in sections if title == item_id]
    if len(matches) != 1:
        raise ValueError("reviewed video generation request is missing or duplicated")
    # Section separators add/remove trailing blank lines during partial merges.
    # Bind approval to the canonical section content, not file-layout whitespace.
    body = "\n".join(matches[0]).strip()

    def scalar(name: str) -> str:
        match = re.search(rf"(?m)^- {re.escape(name)}: `([^`]*)`\s*$", body)
        return match.group(1).strip() if match else ""

    def fenced(name: str) -> str:
        match = re.search(rf"(?ms)```{re.escape(name)}\s*\n(.*?)\n```", body)
        return match.group(1).strip() if match else ""

    fields = (
        "tool",
        "output",
        "duration_seconds",
        "quality",
        "aspect_ratio",
        "first_frame",
        "last_frame",
        "prompt_policy_version",
        "compiler_version",
        "source_digest",
        "prompt_sha256",
        "negative_prompt_sha256",
        "references_digest",
    )
    return {
        **{field: scalar(field) for field in fields},
        "prompt": fenced("video_prompt") or fenced("api_prompt"),
        "negative_prompt": fenced("negative_prompt"),
        "request_section_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


def _video_prompt_approval_state_prefix(item_id: str) -> str:
    safe_item_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", item_id).strip("._-")
    return f"review.video_prompt.item.{safe_item_id or 'unknown'}"


def _video_prompt_approval_updates(
    run_dir: Path,
    items: list[FrontendReviewItem],
    *,
    approved: bool,
) -> dict[str, str]:
    return _video_prompt_approval_updates_for_item_ids(
        run_dir,
        [item.item_id for item in items],
        approved=approved,
    )


def _video_prompt_approval_updates_for_item_ids(
    run_dir: Path,
    item_ids: Iterable[str],
    *,
    approved: bool,
) -> dict[str, str]:
    updates: dict[str, str] = {}
    for item_id in item_ids:
        binding = _reviewed_video_request_binding(run_dir, item_id)
        prefix = _video_prompt_approval_state_prefix(item_id)
        updates.update(
            {
                f"{prefix}.status": "approved" if approved else "pending",
                f"{prefix}.request_section_sha256": binding[
                    "request_section_sha256"
                ],
                f"{prefix}.prompt_sha256": binding["prompt_sha256"],
                f"{prefix}.source_digest": binding["source_digest"],
                f"{prefix}.approved_by": (
                    "frontend_generation_action" if approved else ""
                ),
                f"{prefix}.approved_at": _now_stamp() if approved else "",
                f"{prefix}.revoked_at": "",
                f"{prefix}.revocation_reason": "",
            }
        )
    return updates


def _video_prompt_stage_approval_complete(
    run_dir: Path,
    items: list[FrontendReviewItem],
    *,
    approval_updates: dict[str, str],
) -> bool:
    """Return true when every canonical target has a current item approval."""

    _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    canonical_ids = [
        str(target["selector"]) for target in _manifest_video_targets(data)
    ]
    requested_ids = [item.item_id for item in items]
    if (
        len(requested_ids) != len(set(requested_ids))
        or not set(requested_ids).issubset(set(canonical_ids))
    ):
        return False
    state_path = run_dir / "state.txt"
    state = parse_state_file(state_path) if state_path.is_file() else {}
    current_state = {**state, **approval_updates}
    for item_id in canonical_ids:
        try:
            binding = _reviewed_video_request_binding(run_dir, item_id)
        except ValueError:
            return False
        prefix = _video_prompt_approval_state_prefix(item_id)
        expected = {
            "status": "approved",
            "request_section_sha256": binding["request_section_sha256"],
            "prompt_sha256": binding["prompt_sha256"],
            "source_digest": binding["source_digest"],
        }
        if any(
            str(current_state.get(f"{prefix}.{field}") or "") != value
            for field, value in expected.items()
        ):
            return False
    return True


def _video_prompt_item_materialization_is_current(
    *,
    run_dir: Path,
    data: dict[str, Any],
    target: dict[str, Any],
) -> bool:
    selector = str(target.get("selector") or "").strip()
    if not selector:
        return False
    node = _dict_value(target.get("cut"))
    generation = _dict_value(node.get("video_generation"))
    payload = _dict_value(generation.get("api_prompt_payload"))
    if _video_prompt_contract_version_mismatches(payload):
        return False

    first_reference = str(
        generation.get("first_frame")
        or generation.get("input_image")
        or ""
    ).strip()
    last_reference = str(generation.get("last_frame") or "").strip()
    references = [
        str(value).strip()
        for value in _list_value(generation.get("references"))
        if str(value).strip()
    ]
    quality = str(generation.get("quality") or "1080p").strip()
    aspect_ratio = str(generation.get("aspect_ratio") or "16:9").strip()
    duration_seconds = int(generation.get("duration_seconds") or 8)
    tool = str(generation.get("tool") or "kling_3_0").strip()
    authoring_source = str(
        generation.get("prompt_authoring_source")
        or generation.get("source_motion_prompt")
        or ""
    ).strip()
    item = FrontendReviewItem(
        item_id=selector,
        kind="scene",
        video_prompt=authoring_source,
        video_quality=quality,
        video_aspect_ratio=aspect_ratio,
        video_duration_seconds=duration_seconds,
        video_first_reference=first_reference or None,
        video_last_reference=last_reference or None,
        video_references=references,
        video_tool=tool,
    )
    _current_target, current_payload = _compile_frontend_video_prompt_payload(
        data=data,
        item=item,
        run_dir=run_dir,
    )
    if _video_prompt_contract_version_mismatches(current_payload):
        return False
    for field in (
        "policy_version",
        "compiler_version",
        "projection_registry_version",
        "prompt",
        "negative_prompt",
        "sha256",
        "source_digest",
        "provider_request_binding",
    ):
        if payload.get(field) != current_payload.get(field):
            return False
    if payload != current_payload:
        return False

    binding = _reviewed_video_request_binding(run_dir, selector)
    negative_prompt = str(payload.get("negative_prompt") or "")
    expected_binding = {
        "tool": tool,
        "output": str(generation.get("output") or "").strip(),
        "duration_seconds": str(duration_seconds),
        "quality": quality,
        "aspect_ratio": aspect_ratio,
        "first_frame": first_reference,
        "last_frame": last_reference,
        "prompt_policy_version": str(payload.get("policy_version") or ""),
        "compiler_version": str(payload.get("compiler_version") or ""),
        "source_digest": str(payload.get("source_digest") or ""),
        "prompt_sha256": str(payload.get("sha256") or ""),
        "negative_prompt_sha256": hashlib.sha256(
            negative_prompt.encode("utf-8")
        ).hexdigest(),
        "references_digest": sha256_canonical_json(references),
        "prompt": str(payload.get("prompt") or "").strip(),
        "negative_prompt": negative_prompt.strip(),
    }
    return all(
        str(binding.get(field) or "") == expected_value
        for field, expected_value in expected_binding.items()
    )


def _video_prompt_stage_materialization_complete(run_dir: Path) -> bool:
    """Return true when every canonical target is recompiled and current."""

    try:
        _manifest_path, _original_text, data = _read_manifest_data(run_dir)
        targets = _manifest_video_targets(data)
        canonical_ids = [str(target["selector"]) for target in targets]
        request_path = run_dir / "video_generation_requests.md"
        if not canonical_ids or not request_path.is_file():
            return False
        _prefix, sections = _split_video_request_sections(
            request_path.read_text(encoding="utf-8")
        )
        section_ids = [title for title, _lines in sections]
        if (
            len(section_ids) != len(set(section_ids))
            or set(section_ids) != set(canonical_ids)
        ):
            return False
        return all(
            _video_prompt_item_materialization_is_current(
                run_dir=run_dir,
                data=data,
                target=target,
            )
            for target in targets
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return False


def _stale_video_prompt_approval_updates(
    run_dir: Path,
    *,
    pending_updates: dict[str, str],
) -> dict[str, str]:
    """Revoke approvals whose retained materialization is no longer current."""

    try:
        _manifest_path, _original_text, data = _read_manifest_data(run_dir)
        targets = _manifest_video_targets(data)
        state_path = run_dir / "state.txt"
        current_state = {
            **(parse_state_file(state_path) if state_path.is_file() else {}),
            **pending_updates,
        }
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        return {}

    updates: dict[str, str] = {}
    for target in targets:
        selector = str(target.get("selector") or "").strip()
        prefix = _video_prompt_approval_state_prefix(selector)
        if current_state.get(f"{prefix}.status") != "approved":
            continue
        try:
            is_current = _video_prompt_item_materialization_is_current(
                run_dir=run_dir,
                data=data,
                target=target,
            )
        except (FileNotFoundError, KeyError, TypeError, ValueError):
            is_current = False
        if is_current:
            continue
        updates.update(
            {
                f"{prefix}.status": "revoked",
                f"{prefix}.request_section_sha256": "",
                f"{prefix}.prompt_sha256": "",
                f"{prefix}.source_digest": "",
                f"{prefix}.approved_by": "",
                f"{prefix}.approved_at": "",
                f"{prefix}.revoked_at": _now_stamp(),
                f"{prefix}.revocation_reason": (
                    "materialized video prompt is stale for the current contract or design"
                ),
            }
        )
    return updates


def _assert_video_materialization_current_for_approval(
    run_dir: Path,
    items: list[FrontendReviewItem],
) -> None:
    _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    for item in items:
        target, current_payload = _compile_frontend_video_prompt_payload(
            data=data,
            item=item,
            run_dir=run_dir,
        )
        blocking_issue_codes = _blocking_video_prompt_quality_issue_codes(
            current_payload
        )
        if blocking_issue_codes:
            raise ValueError(
                f"video prompt approval blocked for {item.item_id}: "
                + ", ".join(blocking_issue_codes)
            )
        node = _dict_value(target.get("cut"))
        video_generation = _dict_value(node.get("video_generation"))
        stored_payload = _dict_value(video_generation.get("api_prompt_payload"))
        _assert_current_video_prompt_contract_versions(
            selector=item.item_id,
            payload=current_payload,
        )
        _assert_current_video_prompt_contract_versions(
            selector=item.item_id,
            payload=stored_payload,
        )
        _assert_video_prompt_quality_allows_provider_execution(
            selector=item.item_id,
            payload=stored_payload,
        )
        for field in (
            "policy_version",
            "compiler_version",
            "projection_registry_version",
            "prompt",
            "negative_prompt",
            "sha256",
            "source_digest",
            "provider_request_binding",
        ):
            if stored_payload.get(field) != current_payload.get(field):
                raise ValueError(
                    f"video prompt materialization changed during semantic review: "
                    f"{item.item_id}.{field}"
                )
        if stored_payload != current_payload:
            raise ValueError(
                "video prompt materialization changed during semantic review: "
                f"{item.item_id}.api_prompt_payload"
            )

        reviewed = _reviewed_video_request_binding(run_dir, item.item_id)
        expected = {
            "tool": str(video_generation.get("tool") or "").strip(),
            "output": str(video_generation.get("output") or "").strip(),
            "duration_seconds": str(
                int(video_generation.get("duration_seconds") or 8)
            ),
            "quality": str(video_generation.get("quality") or "1080p").strip(),
            "aspect_ratio": str(
                video_generation.get("aspect_ratio") or "16:9"
            ).strip(),
            "first_frame": str(
                video_generation.get("first_frame")
                or video_generation.get("input_image")
                or ""
            ).strip(),
            "last_frame": str(video_generation.get("last_frame") or "").strip(),
            "prompt_policy_version": str(
                stored_payload.get("policy_version") or ""
            ),
            "compiler_version": str(
                stored_payload.get("compiler_version") or ""
            ),
            "source_digest": str(stored_payload.get("source_digest") or ""),
            "prompt_sha256": str(stored_payload.get("sha256") or ""),
            "negative_prompt_sha256": hashlib.sha256(
                str(stored_payload.get("negative_prompt") or "").encode("utf-8")
            ).hexdigest(),
            "references_digest": sha256_canonical_json(
                [
                    str(value).strip()
                    for value in _list_value(video_generation.get("references"))
                    if str(value).strip()
                ]
            ),
            "prompt": str(stored_payload.get("prompt") or "").strip(),
            "negative_prompt": str(
                stored_payload.get("negative_prompt") or ""
            ).strip(),
        }
        mismatches = [
            field
            for field, expected_value in expected.items()
            if str(reviewed.get(field) or "") != expected_value
        ]
        if mismatches:
            raise ValueError(
                f"video generation request changed during semantic review: "
                f"{item.item_id} ({', '.join(mismatches)})"
            )


def _blocking_video_prompt_quality_issue_codes(
    payload: dict[str, Any],
) -> list[str]:
    sources = [
        payload.get("quality_issues"),
        _dict_value(payload.get("video_prompt_ir")).get("quality_issues"),
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
        raise ValueError(
            f"video provider execution blocked for {selector}: "
            + ", ".join(codes)
        )


def _assert_video_prompt_semantic_review_is_current(run_dir: Path) -> None:
    result = check_semantic_review(run_dir, "video_motion")
    if not result.passed:
        raise ValueError(
            "video motion semantic review did not pass: "
            + "; ".join(result.errors)
        )
    if not _semantic_review_report_sources_are_current(run_dir, "video_motion"):
        raise ValueError(
            "video motion semantic review became stale before approval"
        )


async def _run_video_prompt_semantic_review_before_approval(
    *,
    run_dir: Path,
) -> bool:
    review_job_id = f"video-prompt-approval-{uuid.uuid4().hex}"
    await _run_semantic_review(
        review_job_id,
        run_dir=run_dir,
        stage="video_motion",
    )
    _assert_video_prompt_semantic_review_is_current(run_dir)
    return True


def _merge_video_request_sections(
    existing_text: str,
    sections_by_id: dict[str, str],
    *,
    canonical_item_ids: set[str] | None = None,
) -> str:
    prefix, existing_sections = _split_video_request_sections(existing_text)
    header = "\n".join(prefix).strip() or "# Video Generation Requests"
    output_sections: list[str] = []
    used: set[str] = set()
    for title, lines in existing_sections:
        if title in sections_by_id:
            output_sections.append(sections_by_id[title])
            used.add(title)
        elif canonical_item_ids is None or title in canonical_item_ids:
            output_sections.append("\n".join(lines).strip())
    for title, section in sections_by_id.items():
        if title not in used:
            output_sections.append(section)
    return "\n\n".join([header, *output_sections]).rstrip() + "\n"


def _write_video_generation_requests(run_dir: Path, items: list[FrontendReviewItem], *, replace_all: bool = True) -> Path:
    _backup_run_file(run_dir, "video_generation_requests.md", label="before_video_prompt_create")
    path = run_dir / "video_generation_requests.md"
    sections_by_id = dict(_video_generation_request_section(run_dir, item) for item in items)
    _manifest_path, _original_text, manifest_data = _read_manifest_data(run_dir)
    canonical_item_ids = {
        str(target["selector"])
        for target in _manifest_video_targets(manifest_data)
    }
    unexpected = sorted(set(sections_by_id).difference(canonical_item_ids))
    if unexpected:
        raise ValueError(
            "video request sections are not canonical manifest targets: "
            + ", ".join(unexpected)
        )
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    _prefix, existing_sections = _split_video_request_sections(existing_text)
    existing_ids = {title for title, _lines in existing_sections}
    if replace_all or not path.exists():
        text = "\n\n".join(["# Video Generation Requests", *sections_by_id.values()]).rstrip() + "\n"
    else:
        text = _merge_video_request_sections(
            existing_text,
            sections_by_id,
            canonical_item_ids=canonical_item_ids,
        )
    path.write_text(text, encoding="utf-8")
    _new_prefix, new_sections = _split_video_request_sections(text)
    retained_ids = {title for title, _lines in new_sections}
    removed_ids = sorted(existing_ids.difference(retained_ids))
    if removed_ids:
        revocation_updates: dict[str, str] = {}
        for item_id in removed_ids:
            prefix = _video_prompt_approval_state_prefix(item_id)
            revocation_updates.update(
                {
                    f"{prefix}.status": "revoked",
                    f"{prefix}.request_section_sha256": "",
                    f"{prefix}.prompt_sha256": "",
                    f"{prefix}.source_digest": "",
                    f"{prefix}.approved_by": "",
                    f"{prefix}.approved_at": "",
                    f"{prefix}.revoked_at": _now_stamp(),
                    f"{prefix}.revocation_reason": (
                        "request section removed because it is no longer a canonical video target"
                    ),
                }
            )
        append_state_snapshot(run_dir / "state.txt", revocation_updates)
    return path


def _storyboard_scene_selector(scene: dict[str, Any], scene_index: int) -> str:
    raw = str(scene.get("scene_id") or scene_index).strip()
    if raw.lower().startswith("scene"):
        selector = raw
    else:
        selector = make_scene_cut_selector(raw)
    if not selector or selector == "sceneunknown":
        selector = f"scene{scene_index}"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", selector).strip("._-") or f"scene{scene_index}"


def _storyboard_cut_id(cut: dict[str, Any], cut_index: int, used_cut_ids: set[str]) -> str:
    raw = str(cut.get("cut_id") or "").strip()
    normalized = normalize_dotted_id(raw)
    if normalized and normalized not in used_cut_ids:
        cut["cut_id"] = normalized
        used_cut_ids.add(normalized)
        return _require_markdown_scalar(normalized, field="source_cut_id")
    if normalized and normalized in used_cut_ids:
        raise RuntimeError(f"storyboard create failed: duplicate cut_id {normalized}")
    candidate = cut_index
    while str(candidate) in used_cut_ids:
        candidate += 1
    fallback = str(candidate)
    cut["cut_id"] = fallback
    used_cut_ids.add(fallback)
    return _require_markdown_scalar(fallback, field="source_cut_id")


def _storyboard_cut_duration(cut: dict[str, Any]) -> int:
    candidates: list[Any] = [cut.get("duration_seconds")]
    video_generation = cut.get("video_generation") if isinstance(cut.get("video_generation"), dict) else {}
    candidates.append(video_generation.get("duration_seconds"))
    for value in candidates:
        try:
            duration = int(value)
        except (TypeError, ValueError):
            continue
        if duration > 0:
            return duration
    return 8


def _partition_storyboard_entries(
    entries: list[tuple[str, str, dict[str, Any], int]],
    *,
    minimum_duration_seconds: int,
    maximum_duration_seconds: int,
) -> list[list[tuple[str, str, dict[str, Any], int]]]:
    """Partition ordered cuts into the fewest provider-valid render units."""

    best: list[list[tuple[int, int]] | None] = [None] * (len(entries) + 1)
    best[0] = []
    for start in range(len(entries)):
        prior = best[start]
        if prior is None:
            continue
        duration = 0
        for end in range(start, len(entries)):
            duration += entries[end][3]
            if duration > maximum_duration_seconds:
                break
            if duration < minimum_duration_seconds:
                continue
            candidate = [*prior, (start, end + 1)]
            current = best[end + 1]
            candidate_boundaries = tuple(
                group_end for _group_start, group_end in candidate[:-1]
            )
            current_boundaries = tuple(
                group_end for _group_start, group_end in (current or [])[:-1]
            )
            if (
                current is None
                or len(candidate) < len(current)
                or (
                    len(candidate) == len(current)
                    and candidate_boundaries > current_boundaries
                )
            ):
                best[end + 1] = candidate
    partition = best[-1]
    if partition is None:
        durations = ", ".join(str(entry[3]) for entry in entries)
        raise ValueError(
            "ordered cut durations cannot be partitioned into provider-valid "
            f"{minimum_duration_seconds}-{maximum_duration_seconds}s render units "
            f"(cuts: {durations})"
        )
    return [entries[start:end] for start, end in partition]


def _storyboard_motion_prompt(
    _scene: dict[str, Any],
    _scene_selector: str,
    cuts: list[dict[str, Any]],
) -> str:
    """Return provider-neutral authoring source, not manifest/debug labels."""

    lines = [
        "motion_brief: 参照画像から動画を生成する。Image 1を開始状態の視覚アンカー、Image 2を出来事の順序と連続性の参考として読み、参照画像を厳密な先頭フレームまたは末尾フレームとは扱わない。入力されたストーリーボードのコマ順を時間順として読み、登場人物の行動と感情の推移を一つの連続した映画的な動きへつなぐ",
        "must_preserve: 各コマに写る人物、顔、衣装、場所、小道具、光、視線方向と出来事の順序",
        "must_not_add: パネル枠、分割画面、画面内テキスト、字幕、ロゴ、ストーリーボードにない人物や重要物",
    ]
    if cuts:
        start_state = _storyboard_cut_boundary(cuts[0], boundary="start")
        end_state = _storyboard_cut_boundary(cuts[-1], boundary="end")
        if start_state:
            lines.append(f"start_from_visible_state: {start_state}")
        if end_state:
            lines.append(f"end_state: {end_state}")
    return "\n".join(lines)


def _storyboard_cut_boundary(cut: dict[str, Any], *, boundary: str) -> str:
    cut_contract = _dict_value(cut.get("cut_contract"))
    motion = _dict_value(cut_contract.get("motion_contract"))
    if boundary == "end":
        continuity = _dict_value(cut_contract.get("continuity_contract"))
        candidates = [
            motion.get("end_state"),
            motion.get("end_frame_brief"),
            continuity.get("end_state"),
        ]
    else:
        first_frame = _dict_value(cut_contract.get("first_frame_contract"))
        visible = _dict_value(first_frame.get("visible_start_state"))
        candidates = [
            motion.get("start_from_visible_state"),
            first_frame.get("first_frame_brief"),
            *visible.values(),
        ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate = "、".join(
                str(value).strip() for value in candidate.values() if str(value).strip()
            )
        text = str(candidate or "").strip()
        if text:
            return text
    return ""


def _compose_storyboard_image(run_dir: Path, *, inputs: list[str], output: str) -> None:
    if not inputs:
        raise ValueError("storyboard requires at least one cut image")
    try:
        from PIL import Image, ImageOps  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover - environment dependency.
        raise RuntimeError("Pillow is required to compose storyboard images") from exc

    input_paths: list[Path] = []
    for rel in inputs:
        _validate_run_relative_image_path(run_dir, rel, must_exist=True)
        path = resolve_run_relative(run_dir, rel)
        validate_image_bytes(path)
        input_paths.append(path)
    _validate_run_relative_image_path(run_dir, output, must_exist=False)
    out_path = resolve_run_relative(run_dir, output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    width, height = 1920, 1080
    gutter = 16
    count = len(input_paths)
    columns = min(4, max(1, math.ceil(math.sqrt(count * 16 / 9))))
    rows = max(1, math.ceil(count / columns))
    cell_w = max(1, (width - gutter * (columns + 1)) // columns)
    cell_h = max(1, (height - gutter * (rows + 1)) // rows)
    canvas = Image.new("RGB", (width, height), (10, 12, 14))

    for index, path in enumerate(input_paths):
        row = index // columns
        col = index % columns
        x = gutter + col * (cell_w + gutter)
        y = gutter + row * (cell_h + gutter)
        with Image.open(path) as image:
            frame = ImageOps.contain(image.convert("RGB"), (cell_w, cell_h))
        cell = Image.new("RGB", (cell_w, cell_h), (18, 20, 23))
        paste_x = (cell_w - frame.width) // 2
        paste_y = (cell_h - frame.height) // 2
        cell.paste(frame, (paste_x, paste_y))
        canvas.paste(cell, (x, y))

    canvas.save(out_path, format="PNG")
    validate_image_bytes(out_path)


def _write_scene_storyboard_video_generation_requests(run_dir: Path, units: list[dict[str, Any]]) -> Path:
    _backup_run_file(run_dir, "video_generation_requests.md", label="before_scene_storyboard_create")
    path = run_dir / "video_generation_requests.md"
    lines = ["# Video Generation Requests", ""]
    for unit in units:
        item_id = _require_markdown_scalar(str(unit.get("request_id") or unit["unit_id"]), field="unit_id")
        first_frame = str(unit["first_frame"])
        storyboard_image = str(unit.get("storyboard_image") or first_frame)
        output = str(unit["output"])
        if first_frame:
            _validate_run_relative_image_path(run_dir, first_frame, must_exist=True)
        _validate_run_relative_image_path(run_dir, storyboard_image, must_exist=True)
        _require_asset_video_output(run_dir, output)
        references = [str(ref) for ref in unit.get("references", []) if str(ref).strip()]
        api_prompt_payload = _dict_value(unit.get("api_prompt_payload"))
        negative_prompt = str(api_prompt_payload.get("negative_prompt") or "")
        for ref in references:
            _validate_run_relative_image_path(run_dir, ref, must_exist=True)
        source_cuts = [_require_markdown_scalar(str(source), field="source_cut_id") for source in unit.get("source_cuts", [])]
        lines.extend(
            [
                f"## {item_id}",
                "",
                f"- tool: `{_require_markdown_scalar(str(unit.get('tool') or 'kling_3_0_omni'), field='video_tool')}`",
                f"- output: `{output}`",
                f"- duration_seconds: `{int(unit.get('duration_seconds') or 8)}`",
                "- quality: `1080p`",
                "- resolution: `1080p`",
                "- aspect_ratio: `16:9`",
                f"- first_frame: `{first_frame}`",
                f"- storyboard_image: `{storyboard_image}`",
                f"- prompt_policy_version: `{api_prompt_payload['policy_version']}`",
                f"- compiler_version: `{api_prompt_payload['compiler_version']}`",
                f"- source_digest: `{api_prompt_payload['source_digest']}`",
                f"- prompt_sha256: `{api_prompt_payload['sha256']}`",
                f"- negative_prompt_sha256: `{hashlib.sha256(negative_prompt.encode('utf-8')).hexdigest()}`",
                f"- references_digest: `{sha256_canonical_json(references)}`",
                "- source_cuts:",
            ]
        )
        lines.extend(f"  - `{source}`" for source in source_cuts)
        if references:
            lines.append("- references:")
            lines.extend(f"  - `{ref}`" for ref in references)
        lines.extend(
            [
                "",
                "```video_prompt",
                _require_no_code_fence(str(unit["motion_prompt"]), field="motion_prompt"),
                "```",
                "",
                "```negative_prompt",
                negative_prompt,
                "```",
                "",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def _explicit_storyboard_render_unit_contract(
    scene: dict[str, Any],
    source_cut_ids: list[str],
) -> dict[str, Any]:
    """Resolve only an explicitly authored contract for the exact source set."""

    for raw_unit in _list_value(scene.get("render_units")):
        if not isinstance(raw_unit, dict):
            continue
        existing_source_ids = [
            normalize_dotted_id(value)
            for value in _list_value(raw_unit.get("source_cut_ids"))
        ]
        if existing_source_ids != source_cut_ids:
            continue
        return _dict_value(raw_unit.get("cut_contract"))
    return {}


def _materialize_scene_storyboard_video_requests(run_id: str) -> dict[str, Any]:
    run_dir = safe_run_dir(run_id, ROOT)
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        raise RuntimeError("storyboard create failed: video_manifest.md scenes must be a list")

    storyboard_execution_options = _server_video_execution_options(
        tool="seedance",
        has_first_frame=False,
        has_reference_images=True,
    )
    storyboard_model = str(storyboard_execution_options.get("model") or "").strip()
    storyboard_capabilities = resolve_video_provider_capabilities(
        tool="seedance",
        model=storyboard_model,
        input_mode="reference_to_video",
    )
    if not storyboard_capabilities.supported:
        raise RuntimeError(
            "storyboard create failed: "
            + (
                storyboard_capabilities.unsupported_reason
                or "Seedance provider capability contract is unsupported"
            )
        )
    if not (
        storyboard_capabilities.reference_images_min
        <= 2
        <= storyboard_capabilities.reference_images_max
    ):
        raise RuntimeError(
            "storyboard create failed: the Seedance reference-image contract "
            "does not permit the required two ordered references"
        )

    units: list[dict[str, Any]] = []
    storyboard_paths: list[str] = []
    for scene_index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict) or str(scene.get("kind") or "").strip().endswith("_reference"):
            continue
        cuts = scene.get("cuts")
        if not isinstance(cuts, list) or not cuts:
            raise RuntimeError(f"storyboard create failed: scene {scene_index} has no cuts")
        scene_selector = _storyboard_scene_selector(scene, scene_index)
        cut_outputs: list[str] = []
        source_cut_ids: list[str] = []
        active_cuts: list[dict[str, Any]] = []
        cut_durations: list[int] = []
        used_cut_ids: set[str] = set()
        for cut_index, cut in enumerate(cuts, start=1):
            if not isinstance(cut, dict):
                raise RuntimeError(f"storyboard create failed: {scene_selector} cut {cut_index} is invalid")
            if str(cut.get("cut_status") or "active").strip().lower() == "deleted":
                continue
            image_generation = cut.get("image_generation") if isinstance(cut.get("image_generation"), dict) else {}
            output = str(image_generation.get("output") or "").strip()
            if not output:
                raise RuntimeError(f"storyboard create failed: {scene_selector} cut {cut_index} has no image output")
            _validate_run_relative_image_path(run_dir, output, must_exist=True)
            cut_outputs.append(output)
            source_cut_ids.append(_storyboard_cut_id(cut, cut_index, used_cut_ids))
            active_cuts.append(cut)
            cut_duration = _storyboard_cut_duration(cut)
            if cut_duration > storyboard_capabilities.duration_max_seconds:
                raise RuntimeError(
                    f"storyboard create failed: {scene_selector} cut {cut_index} "
                    f"duration {cut_duration}s exceeds the "
                    f"{storyboard_capabilities.duration_max_seconds}s Seedance "
                    "reference-image limit; split the cut"
                )
            if _int_value(cut.get("duration_seconds") or 0) <= 0:
                cut["duration_seconds"] = cut_duration
            cut_durations.append(cut_duration)
        if not cut_outputs:
            raise RuntimeError(f"storyboard create failed: {scene_selector} has no active cut images")
        entries = list(
            zip(
                cut_outputs,
                source_cut_ids,
                active_cuts,
                cut_durations,
                strict=True,
            )
        )
        try:
            grouped_entries = _partition_storyboard_entries(
                entries,
                minimum_duration_seconds=(
                    storyboard_capabilities.duration_min_seconds
                ),
                maximum_duration_seconds=(
                    storyboard_capabilities.duration_max_seconds
                ),
            )
        except ValueError as exc:
            raise RuntimeError(
                f"storyboard create failed: {scene_selector}: {exc}; split or retime the cuts"
            ) from exc

        scene_render_units: list[dict[str, Any]] = []
        multiple_units = len(grouped_entries) > 1
        video_metadata = _dict_value(data.get("video_metadata"))
        for unit_index, group in enumerate(grouped_entries, start=1):
            group_outputs = [entry[0] for entry in group]
            group_source_ids = [entry[1] for entry in group]
            group_cuts = [entry[2] for entry in group]
            video_duration_seconds = sum(entry[3] for entry in group)
            unit_id = str(unit_index)
            request_id = f"{scene_selector}_unit{unit_id}"
            storyboard_output = (
                f"assets/storyboards/{scene_selector}_unit{unit_id}_storyboard.png"
                if multiple_units
                else f"assets/storyboards/{scene_selector}_storyboard.png"
            )
            _compose_storyboard_image(
                run_dir,
                inputs=group_outputs,
                output=storyboard_output,
            )
            # BytePlus reference-image mode cannot be combined with first/last
            # frame boundary inputs. Image 1 anchors the start state and Image 2
            # communicates the ordered storyboard without claiming exact frame
            # boundary semantics.
            reference_images = [group_outputs[0], storyboard_output]
            first_frame = ""
            video_output = f"assets/scenes/{scene_selector}/{request_id}.mp4"
            motion_prompt = _storyboard_motion_prompt(
                scene,
                scene_selector,
                group_cuts,
            )
            explicit_render_unit_contract = (
                _explicit_storyboard_render_unit_contract(
                    scene,
                    group_source_ids,
                )
            )
            render_unit_contract = compose_video_render_unit_contract(
                [_dict_value(cut.get("cut_contract")) for cut in group_cuts],
                unit_contract=explicit_render_unit_contract or None,
            )
            execution_options = dict(storyboard_execution_options)
            reference_content_sha256 = _video_reference_content_sha256(
                run_dir,
                reference_images,
            )
            if reference_content_sha256:
                execution_options["reference_content_sha256"] = (
                    reference_content_sha256
                )
            review_dependencies = {
                "render_unit_source_cut_ids": list(group_source_ids),
                "render_unit_source_cut_contracts": [
                    _dict_value(cut.get("cut_contract")) for cut in group_cuts
                ],
            }
            reference_roles = [
                {
                    "image_index": 1,
                    "role": "start_state_visual_anchor",
                },
                {
                    "image_index": 2,
                    "role": "ordered_storyboard_sequence_guide",
                },
            ]
            api_prompt_payload = compile_video_api_prompt_v1(
                cut_contract=render_unit_contract,
                source_prompt=motion_prompt,
                story_time=str(video_metadata.get("time") or "").strip(),
                time_of_day=str(scene.get("time_of_day") or "").strip(),
                tool="seedance",
                duration_seconds=video_duration_seconds,
                references=reference_images,
                reference_roles=reference_roles,
                quality="1080p",
                aspect_ratio="16:9",
                execution_options=execution_options,
                review_only_dependencies=review_dependencies,
                scene_time_of_day_visual_basis=scene.get(
                    "time_of_day_visual_basis"
                ),
                scene_location_mode=str(
                    scene.get("location_mode") or ""
                ).strip(),
                scene_location_sequence=_list_value(
                    scene.get("location_sequence")
                ),
                scene_location_segments=[
                    dict(value)
                    for value in _list_value(scene.get("location_segments"))
                    if isinstance(value, dict)
                ],
                scene_visualizable_action=(
                    _scene_visualizable_action_for_video_review(scene)
                ),
            )
            video_generation = {
                "tool": "seedance",
                "duration_seconds": video_duration_seconds,
                "references": reference_images,
                "prompt_authoring_source": motion_prompt,
                "motion_prompt": api_prompt_payload["prompt"],
                "api_prompt_payload": api_prompt_payload,
                "output": video_output,
                "quality": "1080p",
                "aspect_ratio": "16:9",
            }
            scene_render_units.append(
                {
                    "unit_id": unit_id,
                    "source_cut_ids": group_source_ids,
                    "cut_contract": render_unit_contract,
                    "storyboard_image": storyboard_output,
                    "video_input_contract": {
                        "schema_version": RENDER_UNIT_VIDEO_INPUT_CONTRACT_VERSION,
                        "input_mode": "reference_images",
                        "required_references": reference_images,
                        "reference_roles": reference_roles,
                    },
                    "video_generation": video_generation,
                }
            )
            units.append(
                {
                    "unit_id": unit_id,
                    "request_id": request_id,
                    "source_cuts": group_source_ids,
                    "first_frame": first_frame,
                    "storyboard_image": storyboard_output,
                    "references": reference_images,
                    "motion_prompt": api_prompt_payload["prompt"],
                    "api_prompt_payload": api_prompt_payload,
                    "output": video_output,
                    "duration_seconds": video_duration_seconds,
                    "tool": video_generation["tool"],
                }
            )
            storyboard_paths.append(storyboard_output)
        scene["render_units"] = scene_render_units

    if not units:
        raise RuntimeError("storyboard create failed: no scene storyboard units were created")

    _backup_run_file(run_dir, "video_manifest.md", label="before_scene_storyboard_create")
    _write_manifest_data(manifest_path, original_text, data)
    request_path = _write_scene_storyboard_video_generation_requests(run_dir, units)
    approval_updates = _video_prompt_approval_updates_for_item_ids(
        run_dir,
        [str(unit["request_id"]) for unit in units],
        approved=False,
    )
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "runtime.create_mode": CREATE_MODE_SCENE_STORYBOARD,
            "runtime.stage": "scene_storyboard_video_requests_ready",
            "review.frontend.storyboard.status": "ready",
            "slot.p820.status": "pending",
            "slot.p820.note": "materialized storyboard video prompts await contextless semantic review",
            "slot.p830.status": "in_progress",
            "slot.p830.note": "storyboard video prompts are materialized; semantic review remains",
            "stage.video_generation.status": "in_progress",
            "review.video_prompt.status": "pending",
            "gate.video_prompt_review": "required",
            "artifact.scene_storyboards": ",".join(storyboard_paths),
            "artifact.video_generation_requests": str(request_path.resolve()),
            **approval_updates,
        },
    )
    return {"storyboards": storyboard_paths, "videoRequestPath": request_path.relative_to(run_dir).as_posix(), "unitCount": len(units)}


def _validate_scene_storyboard_create_run(run_id: str, *, strict_visual_quality: bool = True) -> None:
    _validate_frontend_create_run(run_id, strict_visual_quality=strict_visual_quality)
    run_dir = safe_run_dir(run_id, ROOT)
    _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        raise RuntimeError("storyboard create incomplete: video_manifest.md scenes must be a list")
    expected_units: list[str] = []
    expected_storyboards: list[str] = []
    for scene_index, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict) or str(scene.get("kind") or "").strip().endswith("_reference"):
            continue
        scene_selector = _storyboard_scene_selector(scene, scene_index)
        render_units = scene.get("render_units")
        if not isinstance(render_units, list) or not render_units:
            raise RuntimeError(
                f"storyboard create incomplete: {scene_selector} has no render_units"
            )
        for unit in render_units:
            if not isinstance(unit, dict):
                raise RuntimeError(
                    f"storyboard create incomplete: {scene_selector} render_unit is invalid"
                )
            unit_id = str(unit.get("unit_id") or "").strip()
            normalized_unit_id = normalize_dotted_id(unit_id)
            storyboard = str(unit.get("storyboard_image") or "").strip()
            video_generation = (
                unit.get("video_generation")
                if isinstance(unit.get("video_generation"), dict)
                else {}
            )
            first_frame = str(
                video_generation.get("first_frame")
                or video_generation.get("input_image")
                or ""
            ).strip()
            references = [
                str(value).strip()
                for value in _list_value(video_generation.get("references"))
                if str(value).strip()
            ]
            input_issues = _render_unit_video_input_issues(
                selector=f"{scene_selector}_unit{unit_id or '?'}",
                node=unit,
            )
            if not unit_id or not storyboard:
                raise RuntimeError(
                    f"storyboard create incomplete: {scene_selector} render_unit "
                    "is missing storyboard input"
                )
            if first_frame:
                raise RuntimeError(
                    f"storyboard create incomplete: {scene_selector} render_unit "
                    "must use reference-image mode without a first-frame boundary"
                )
            if input_issues:
                raise RuntimeError(
                    f"storyboard create incomplete: {scene_selector} render_unit input contract: "
                    + "; ".join(input_issues)
                )
            for reference in references:
                _validate_run_relative_image_path(
                    run_dir, reference, must_exist=True
                )
            if not isinstance(unit.get("source_cut_ids"), list) or not unit.get(
                "source_cut_ids"
            ):
                raise RuntimeError(
                    f"storyboard create incomplete: {scene_selector} render_unit has no source_cut_ids"
                )
            if normalized_unit_id is None:
                raise RuntimeError(
                    f"storyboard create incomplete: {scene_selector} render_unit has invalid unit_id"
                )
            expected_units.append(f"{scene_selector}_unit{normalized_unit_id}")
            expected_storyboards.append(storyboard)
    if not expected_units:
        raise RuntimeError("storyboard create incomplete: no storyboard render_units found")
    request_path = run_dir / "video_generation_requests.md"
    if not request_path.is_file():
        raise RuntimeError("storyboard create incomplete: missing video_generation_requests.md")
    request_text = request_path.read_text(encoding="utf-8", errors="replace")
    missing_units = [unit_id for unit_id in expected_units if f"## {unit_id}" not in request_text]
    missing_storyboards = [path for path in expected_storyboards if path not in request_text]
    if missing_units or missing_storyboards:
        raise RuntimeError(
            "storyboard create incomplete: video_generation_requests.md missing "
            + ", ".join([*missing_units, *missing_storyboards])
        )


def _asset_create_target(asset_type: str) -> str:
    if asset_type == "character":
        return "character"
    if asset_type == "location":
        return "location"
    return "item"


def _asset_create_output(asset_type: str, title: str) -> tuple[str, str, str]:
    slug = re.sub(r"[^0-9A-Za-z_一-龠ぁ-んァ-ンー]+", "_", title.strip().replace(" ", "_"))
    slug = re.sub(r"_+", "_", slug).strip("_") or f"{asset_type}_{_now_stamp()}"
    if asset_type == "character":
        return slug, "character_reference", f"assets/characters/{slug}.png"
    if asset_type == "location":
        return slug, "location_anchor", f"assets/locations/{slug}.png"
    return slug, "object_reference", f"assets/objects/{slug}.png"


def _asset_request_section(*, item_id: str, asset_type: str, output: str, prompt: str) -> str:
    return "\n".join(
        [
            f"## {item_id}",
            "",
            "- tool: `codex_builtin_image`",
            f"- asset_type: `{asset_type}`",
            "- execution_lane: `bootstrap_builtin`",
            "- reference_count: `0`",
            f"- output: `{output}`",
            "- references: `[]`",
            "",
            "```text",
            prompt.strip(),
            "```",
        ]
    )


def _append_asset_generation_request(run_dir: Path, *, item_id: str, asset_type: str, output: str, prompt: str) -> Path:
    _require_markdown_scalar(item_id, field="item_id")
    _require_markdown_scalar(asset_type, field="asset_type")
    _validate_run_relative_image_path(run_dir, output, must_exist=False)
    path = run_dir / "asset_generation_requests.md"
    _backup_run_file(run_dir, "asset_generation_requests.md", label="before_asset_create")
    section = _asset_request_section(item_id=item_id, asset_type=asset_type, output=output, prompt=prompt)
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        path.write_text("# Asset Generation Requests\n\n" + section + "\n", encoding="utf-8")
        return path
    existing = path.read_text(encoding="utf-8")
    if re.search(rf"(?m)^##\s+{re.escape(item_id)}\s*$", existing):
        raise ValueError(f"asset request already exists: {item_id}")
    path.write_text(existing.rstrip() + "\n\n" + section + "\n", encoding="utf-8")
    return path


def _update_manifest_video_generation(run_dir: Path, items: list[FrontendReviewItem]) -> dict[str, list[str]]:
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    targets_by_item: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for item in items:
        _require_markdown_scalar(item.item_id, field="item_id")
        _video_prompt_for_request(item)
        target = _video_target_by_item_id(data, item.item_id)
        if target is None:
            missing.append(item.item_id)
        else:
            targets_by_item[item.item_id] = target
    if missing:
        raise ValueError(f"video manifest targets not found: {', '.join(missing)}")
    _backup_run_file(run_dir, "video_manifest.md", label="before_video_prompt_create")
    updated: list[str] = []
    for item in items:
        target = targets_by_item[item.item_id]
        node = target["cut"]
        video_generation = node.get("video_generation") if isinstance(node.get("video_generation"), dict) else {}
        _target, api_prompt_payload = _compile_frontend_video_prompt_payload(
            data=data,
            item=item,
            run_dir=run_dir,
        )
        prompt_authoring_source = _video_prompt_for_request(item)
        if not prompt_authoring_source:
            prompt_authoring_source = str(
                video_generation.get("prompt_authoring_source")
                or video_generation.get("source_motion_prompt")
                or ""
            ).strip()
        output = str(video_generation.get("output") or "").strip() or _default_video_output(
            item
        )
        _require_asset_video_output(run_dir, output)
        input_contract = (
            _render_unit_video_input_contract(_dict_value(node))
            if target.get("is_render_unit")
            else {}
        )
        reference_image_mode = input_contract.get("input_mode") == "reference_images"
        video_generation.update(
            {
                "tool": item.video_tool or video_generation.get("tool") or "kling_3_0",
                "duration_seconds": item.video_duration_seconds or video_generation.get("duration_seconds") or 8,
                "prompt_authoring_source": prompt_authoring_source,
                "motion_prompt": api_prompt_payload["prompt"],
                "api_prompt_payload": api_prompt_payload,
                "output": output,
                "quality": item.video_quality or video_generation.get("quality") or "1080p",
                "aspect_ratio": item.video_aspect_ratio or video_generation.get("aspect_ratio") or "16:9",
            }
        )
        if reference_image_mode:
            video_generation.pop("first_frame", None)
            video_generation.pop("input_image", None)
            video_generation.pop("last_frame", None)
        else:
            video_generation["first_frame"] = _default_first_frame(item)
        if not reference_image_mode and item.video_last_reference is not None:
            if item.video_last_reference.strip():
                video_generation["last_frame"] = item.video_last_reference.strip()
            else:
                video_generation.pop("last_frame", None)
        video_generation["references"] = list(dict.fromkeys(item.video_references))
        provider_binding = _dict_value(
            api_prompt_payload.get("provider_request_binding")
        )
        provider_options = _dict_value(
            provider_binding.get("execution_options")
        )
        capability_issues = _video_provider_capability_issues(
            label=item.item_id,
            tool=str(video_generation.get("tool") or "kling_3_0"),
            model=str(provider_options.get("model") or "").strip(),
            input_mode=str(api_prompt_payload.get("mode") or "").strip(),
            duration_seconds=int(video_generation["duration_seconds"]),
            reference_count=len(video_generation["references"]),
        )
        if capability_issues:
            raise ValueError("; ".join(capability_issues))
        node["video_generation"] = video_generation
        if not target.get("is_render_unit"):
            render = _dict_value(node.get("render"))
            duration = int(video_generation["duration_seconds"])
            canonical_duration = _int_value(
                render.get("video_duration_seconds") or 0
            )
            if canonical_duration > 0 and canonical_duration != duration:
                raise ValueError(
                    f"{item.item_id}: duration {duration}s differs from canonical render timeline "
                    f"duration {canonical_duration}s"
                )
            render["video_duration_seconds"] = duration
            node["render"] = render
        updated.append(item.item_id)
    render_unit_issues = _render_unit_timeline_issues(data)
    if render_unit_issues:
        raise ValueError(
            "invalid render-unit timeline after video materialization: "
            + "; ".join(render_unit_issues[:20])
        )
    _write_manifest_data(manifest_path, original_text, data)
    return {"updated": updated, "missing": []}


def _next_cut_id(cuts: list[Any]) -> str:
    numbers: list[int] = []
    for index, cut in enumerate(cuts, start=1):
        if not isinstance(cut, dict):
            continue
        raw = normalize_dotted_id(cut.get("cut_id")) or str(index)
        try:
            numbers.append(int(raw.split(".", 1)[0]))
        except Exception:
            continue
    return str((max(numbers) if numbers else 0) + 1)


def _default_inserted_cut_prompt(cut_name: str) -> str:
    return "\n".join(
        [
            "[全体 / 不変条件]",
            "既存 scene の画調、人物、光、レンズ感を維持する。画面内テキストなし、字幕なし、ウォーターマークなし。",
            "",
            "[登場人物]",
            "必要な人物だけを既存参照と一致させる。",
            "",
            "[小道具 / 舞台装置]",
            "必要な小道具や舞台装置があれば形状と位置関係を固定する。",
            "",
            "[シーン]",
            cut_name,
            "",
            "[連続性]",
            "前後 cut と視線方向、照明方向、位置関係が自然につながる。",
            "",
            "[禁止]",
            "別人化、別場所化、アニメ調、読める文字、ロゴ、ウォーターマーク。",
        ]
    )


def _insert_cut_in_manifest(run_dir: Path, req: InsertCutRequest) -> dict[str, str]:
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    _backup_run_file(run_dir, "video_manifest.md", label="before_cut_insert")
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("video_manifest.md scenes must be a list")
    target = _target_by_item_id(data, req.anchor_item_id or "") if req.anchor_item_id else None
    scene = target["scene"] if target else None
    scene_id = target["scene_id"] if target else normalize_dotted_id(req.scene_id)
    if scene is None:
        scene = next(
            (
                raw_scene
                for raw_scene in scenes
                if isinstance(raw_scene, dict)
                and scene_id
                and normalize_dotted_id(raw_scene.get("scene_id")) == scene_id
            ),
            None,
        )
    if not isinstance(scene, dict) or not scene_id:
        raise ValueError("target scene not found")
    cuts = scene.get("cuts")
    if not isinstance(cuts, list):
        cuts = []
        scene["cuts"] = cuts
    requested_cut_id = normalize_dotted_id(req.cut_id) if req.cut_id else None
    cut_id = requested_cut_id or _next_cut_id(cuts)
    selector = make_scene_cut_selector(scene_id, cut_id)
    existing_aliases = {
        alias
        for target_info in _manifest_scene_targets(data, include_non_renderable=True)
        for alias in target_info["aliases"]
    }
    if selector in existing_aliases:
        raise ValueError(f"cut selector already exists: {selector}")
    scene_dir = f"assets/scenes/{selector}"
    audio_dir = f"assets/audio/{selector}"
    image_output = f"{scene_dir}/{selector}.png"
    video_output = f"{scene_dir}/{selector}.mp4"
    audio_output = f"{audio_dir}/{selector}_narration.mp3"
    for rel_path in (image_output, video_output, audio_output):
        resolve_run_relative(run_dir, rel_path).parent.mkdir(parents=True, exist_ok=True)
    new_cut = {
        "cut_id": cut_id,
        "cut_name": req.cut_name.strip(),
        "cut_role": "sub",
        "image_generation": {
            "tool": "codex_builtin_image",
            "character_ids": [],
            "character_variant_ids": [],
            "object_ids": [],
            "object_variant_ids": [],
            "references": [],
            "prompt": (req.prompt or "").strip() or _default_inserted_cut_prompt(req.cut_name.strip()),
            "output": image_output,
            "iterations": 4,
            "selected": None,
        },
        "video_generation": {
            "tool": "kling_3_0",
            "duration_seconds": 8,
            "first_frame": image_output,
            "motion_prompt": "静止画の構図を維持し、前後 cut と自然につながる小さなカメラ移動で見せる。",
            "output": video_output,
            "quality": "1080p",
            "aspect_ratio": "16:9",
        },
        "audio": {
            "narration": {
                "text": "",
                "tool": "elevenlabs",
                "output": audio_output,
                "normalize_to_scene_duration": False,
            }
        },
    }
    insert_index = len(cuts)
    if target and target.get("cuts") is cuts and target.get("cut_index") is not None and req.position != "end":
        anchor_index = int(target["cut_index"])
        insert_index = anchor_index if req.position == "before" else anchor_index + 1
    cuts.insert(insert_index, new_cut)
    _write_manifest_data(manifest_path, original_text, data)
    return {"selector": selector, "imageOutput": image_output, "videoOutput": video_output, "audioOutput": audio_output}


async def _generate_asset_outputs(run_dir: Path, run_id: str) -> None:
    await _generate_request_outputs(run_dir=run_dir, kind="asset")


def _prompt_needs_quality_upgrade(item: Any) -> bool:
    if str(getattr(item, "prompt_policy_version", "") or "") == "image_api_prompt_v2":
        return False
    prompt = str(getattr(item, "prompt", "") or "").strip()
    if len(prompt) < 360:
        return True
    required = ("[全体", "[禁止]")
    if not all(marker in prompt for marker in required):
        return True
    if getattr(item, "kind", "") == "asset":
        return not any(marker in prompt for marker in ("[作成するもの]", "[対象]", "[人物固定]", "[衣装]", "[生成方針]"))
    return not any(marker in prompt for marker in ("[登場人物]", "[シーン]", "[連続性]", "[構図]", "[カメラ]"))


def _prompt_target_for_item(item: Any) -> str:
    if getattr(item, "kind", "") == "scene":
        return "scene"
    asset_type = str(getattr(item, "asset_type", "") or "").lower()
    output = str(getattr(item, "output", "") or "").lower()
    if "character" in asset_type or output.startswith("assets/characters/"):
        return "character"
    if "location" in asset_type or output.startswith("assets/locations/") or output.startswith("assets/location/"):
        return "location"
    return "item"


async def _regenerate_prompt_with_log(
    client: CodexAppServerClient,
    *,
    run_dir: Path,
    item: dict[str, Any],
    target: str,
    instruction: str,
    setting_content: str,
    operation: str = "prompt_regeneration",
) -> str:
    item_id = str(item.get("id") or item.get("itemId") or "prompt")
    request = {
        "target": target,
        "itemId": item_id,
        "instructionLength": len(instruction),
        "settingLength": len(setting_content),
    }
    try:
        prompt = await client.regenerate_prompt(
            item=item,
            target=target,
            instruction=instruction,
            setting_content=setting_content,
            run_dir=run_dir,
        )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation=operation,
            status="completed",
            item_id=item_id,
            request=request,
            response={"promptLength": len(prompt), "promptPreview": prompt[:500]},
        )
        return prompt
    except Exception as exc:
        write_app_server_debug_log(
            run_dir=run_dir,
            operation=operation,
            status="failed",
            item_id=item_id,
            request=request,
            error=str(exc),
        )
        raise


async def _revise_v2_visual_plan_with_log(
    client: CodexAppServerClient,
    *,
    run_dir: Path,
    item: dict[str, Any],
    current_plan: dict[str, Any],
    instruction: str,
    setting_content: str,
) -> dict[str, Any]:
    item_id = str(item.get("id") or item.get("itemId") or "prompt")
    request = {
        "target": "scene",
        "itemId": item_id,
        "instructionLength": len(instruction),
        "settingLength": len(setting_content),
        "operation": "compiled_v2_recompile",
    }
    try:
        patch = await client.revise_first_frame_visual_plan(
            item=item,
            current_plan=current_plan,
            instruction=instruction,
            setting_content=setting_content,
            run_dir=run_dir,
        )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="prompt_recompile",
            status="visual_plan_patch_completed",
            item_id=item_id,
            request=request,
            response={"patchFields": sorted(patch)},
        )
        return patch
    except Exception as exc:
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="prompt_recompile",
            status="failed",
            item_id=item_id,
            request=request,
            error=str(exc),
        )
        raise


def _recompile_v2_scene_manifest(
    run_dir: Path,
    revisions: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    story_time = str(_dict_value(data.get("video_metadata")).get("time") or "").strip()
    compiled: dict[str, dict[str, Any]] = {}
    canonical_payload_keys = {
        "policy_version",
        "compiler_version",
        "source_digest",
        "prompt",
        "negative_prompt",
        "reference_instructions",
        "reference_images",
        "sha256",
        "drawable_prompt_ir",
    }
    for item_id, revision in revisions.items():
        target = _target_by_item_id(data, item_id)
        if target is None:
            raise ValueError(f"video manifest target not found: {item_id}")
        node = _dict_value(target.get("cut"))
        image_generation = _dict_value(node.get("image_generation"))
        current_plan = _dict_value(image_generation.get("first_frame_visual_plan"))
        if _json_hash(current_plan) != str(revision.get("expected_plan_hash") or ""):
            raise ValueError(f"compiled_v2_plan_revision_conflict: {item_id}")
        existing_payload = _dict_value(image_generation.get("api_prompt_payload"))
        if str(existing_payload.get("policy_version") or "") != "image_api_prompt_v2":
            raise ValueError(f"compiled_v2_policy_required: {item_id}")
        character_ids = _list_value(image_generation.get("character_ids"))
        object_ids = _list_value(image_generation.get("object_ids"))
        location_ids = _list_value(image_generation.get("location_ids"))
        references = _list_value(image_generation.get("references"))
        scene_time_of_day = str(
            _dict_value(target.get("scene")).get("time_of_day") or ""
        ).strip()
        plan, _discarded_payload = _apply_v2_visual_plan_patch_and_compile(
            current_plan,
            _dict_value(revision.get("patch")),
            character_ids=character_ids,
            object_ids=object_ids,
            location_ids=location_ids,
            references=references,
            story_time=story_time,
            scene_time_of_day=scene_time_of_day,
        )
        review_metadata = _review_metadata_for_recompiled_visual_plan(
            plan,
            selector=str(target["selector"]),
            character_ids=character_ids,
            object_ids=object_ids,
            location_ids=location_ids,
            existing_payload=existing_payload,
            canonical_payload_keys=canonical_payload_keys,
        )
        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            character_ids=character_ids,
            object_ids=object_ids,
            location_ids=location_ids,
            reference_images=references,
            story_time=story_time,
            scene_time_of_day=scene_time_of_day,
            review_metadata=review_metadata,
        )
        image_generation["first_frame_visual_plan"] = plan
        image_generation["api_prompt_payload"] = payload
        debug_prompt_source = deepcopy(_dict_value(image_generation.get("debug_prompt_source")))
        debug_prompt_source["first_frame_visual_plan"] = deepcopy(plan)
        debug_prompt_source["api_prompt_payload"] = {
            "policy_version": payload["policy_version"],
            "compiler_version": payload["compiler_version"],
            "source_digest": payload["source_digest"],
            "sha256": payload["sha256"],
        }
        image_generation["debug_prompt_source"] = debug_prompt_source
        node["image_generation"] = image_generation
        compiled[item_id] = payload
    _write_manifest_data(manifest_path, original_text, data)
    return compiled


def _review_metadata_for_recompiled_visual_plan(
    plan: dict[str, Any],
    *,
    selector: str,
    character_ids: list[str],
    object_ids: list[str],
    location_ids: list[str],
    existing_payload: dict[str, Any],
    canonical_payload_keys: set[str],
) -> dict[str, Any]:
    """Recompute every plan-derived review field from the repaired source."""

    derived_keys = {
        "shot_design_contract",
        "cut_location_frame_plan",
        "cut_visual_delta",
        "blocking_and_interaction",
    }
    metadata = {
        key: deepcopy(value)
        for key, value in existing_payload.items()
        if key not in canonical_payload_keys and key not in derived_keys
    }
    source_grounding = _dict_value(plan.get("source_grounding"))
    temporal = _dict_value(plan.get("temporal_boundary"))
    composition = _dict_value(plan.get("spatial_composition"))
    character_gate = _dict_value(plan.get("character_state_gate"))
    object_gate = _dict_value(plan.get("object_visibility_gate"))
    progression = _dict_value(plan.get("scene_state_progression"))
    object_entries = [
        value for value in object_gate.get("objects") or [] if isinstance(value, dict)
    ]
    cut_function = str(source_grounding.get("cut_function") or "").strip()
    if object_ids and cut_function in {"threshold", "handoff", "payoff", "proof"}:
        shot_role = "object_proof"
    elif cut_function == "setup" or not character_ids:
        shot_role = "establishing"
    elif cut_function in {"reaction", "payoff"}:
        shot_role = "reaction"
    elif cut_function == "handoff":
        shot_role = "handoff"
    else:
        shot_role = "character_action"
    shot_scale = str(composition.get("shot_size") or "").strip() or (
        "medium_wide" if shot_role in {"establishing", "handoff", "object_proof"} else "medium"
    )
    metadata["shot_design_contract"] = {
        "shot_role": shot_role,
        "shot_scale": shot_scale,
        "a_roll_or_b_roll": "b_roll" if shot_role == "object_proof" else "a_roll",
        "should_show_face": bool(character_ids) and bool(
            character_gate.get("face")
            or character_gate.get("gaze")
            or character_gate.get("pose")
        ),
        "should_show_hands": bool(character_ids) and bool(character_gate.get("hand_position")),
        "should_show_object_detail": bool(object_ids),
    }
    location_zone = str(
        composition.get("foreground") or composition.get("midground") or ""
    ).strip()
    metadata["cut_location_frame_plan"] = {
        "base_location_reference_id": location_ids[0] if location_ids else "",
        "use_reference_as": "material_anchor",
        "location_zone_id": re.sub(r"\s+", "_", location_zone)[:80],
        "location_zone_description": location_zone,
    }
    visible_delta = str(
        progression.get("visible_state_delta_from_previous_cut")
        or temporal.get("event_fact_visible_in_still")
        or temporal.get("first_visible_moment")
        or ""
    ).strip()
    cut_match = re.search(r"cut0*(\d+)$", selector)
    cut_number = int(cut_match.group(1)) if cut_match else 1
    previous_selector = (
        ""
        if cut_number <= 1
        else re.sub(r"cut0*\d+$", f"cut{cut_number - 1:02d}", selector)
    )
    metadata["cut_visual_delta"] = {
        "previous_cut_selector": previous_selector,
        "previous_visible_state_summary": str(
            progression.get("state_visible_in_first_frame") or ""
        ),
        "this_cut_new_information": visible_delta,
        "cut_delta_visible_in_still": visible_delta,
    }
    primary_object = object_entries[0] if object_entries else {}
    primary_object_id = str(primary_object.get("object_id") or "").strip()
    if not primary_object_id and object_ids:
        primary_object_id = object_ids[0]
    visibility = str(primary_object.get("visibility_in_this_cut") or "").strip()
    metadata["blocking_and_interaction"] = {
        "character_blocking": {
            "gaze_target": str(character_gate.get("gaze") or "").strip(),
            "hand_position": deepcopy(character_gate.get("hand_position") or ""),
            "foot_position": deepcopy(character_gate.get("foot_position") or ""),
        },
        "object_interaction": {
            "object_id": primary_object_id,
            "contact_state": "" if not primary_object_id else (
                "not_visible" if visibility == "hidden" else "visible"
            ),
            "object_screen_position": str(
                primary_object.get("required_screen_position") or ""
            ).strip(),
        },
    }
    return metadata


def _recompile_image_prompt_payloads_from_plans(run_dir: Path) -> list[str]:
    """Rebuild every compiled-v2 payload from the repaired visual-plan source."""

    manifest_path, original_text, data = _read_manifest_data(run_dir)
    story_time = str(_dict_value(data.get("video_metadata")).get("time") or "").strip()
    canonical_payload_keys = {
        "policy_version",
        "compiler_version",
        "source_digest",
        "prompt",
        "negative_prompt",
        "reference_instructions",
        "reference_images",
        "sha256",
        "drawable_prompt_ir",
    }
    changed_selectors: list[str] = []
    for target in _manifest_scene_targets(data):
        node = _dict_value(target.get("cut"))
        image_generation = _dict_value(node.get("image_generation"))
        existing_payload = _dict_value(image_generation.get("api_prompt_payload"))
        plan = _dict_value(image_generation.get("first_frame_visual_plan"))
        if str(plan.get("schema_version") or "") != "first_frame_visual_plan_v1":
            if str(existing_payload.get("policy_version") or "") != "image_api_prompt_v2":
                continue
            raise ValueError(
                f"compiled_v2_first_frame_visual_plan_v1_required: {target['selector']}"
            )
        character_ids = _list_value(image_generation.get("character_ids"))
        object_ids = _list_value(image_generation.get("object_ids"))
        location_ids = _list_value(image_generation.get("location_ids"))
        references = _list_value(image_generation.get("references"))
        scene_time_of_day = str(
            _dict_value(target.get("scene")).get("time_of_day") or ""
        ).strip()
        review_metadata = _review_metadata_for_recompiled_visual_plan(
            plan,
            selector=str(target["selector"]),
            character_ids=character_ids,
            object_ids=object_ids,
            location_ids=location_ids,
            existing_payload=existing_payload,
            canonical_payload_keys=canonical_payload_keys,
        )
        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            character_ids=character_ids,
            object_ids=object_ids,
            location_ids=location_ids,
            reference_images=references,
            story_time=story_time,
            scene_time_of_day=scene_time_of_day,
            review_metadata=review_metadata,
        )
        debug_prompt_source = deepcopy(_dict_value(image_generation.get("debug_prompt_source")))
        previous_debug_prompt_source = deepcopy(debug_prompt_source)
        debug_prompt_source["first_frame_visual_plan"] = deepcopy(plan)
        debug_prompt_source["api_prompt_payload"] = {
            "policy_version": payload["policy_version"],
            "compiler_version": payload["compiler_version"],
            "source_digest": payload["source_digest"],
            "sha256": payload["sha256"],
        }
        if payload == existing_payload and debug_prompt_source == previous_debug_prompt_source:
            continue
        image_generation["api_prompt_payload"] = payload
        image_generation["debug_prompt_source"] = debug_prompt_source
        node["image_generation"] = image_generation
        changed_selectors.append(str(target["selector"]))
    if changed_selectors:
        _write_manifest_data(manifest_path, original_text, data)
    return changed_selectors


def _synchronize_image_prompt_repair_outputs(run_dir: Path) -> None:
    """Compile repaired plans and atomically rematerialize request + snapshot files."""

    tracked_paths = (
        run_dir / "video_manifest.md",
        run_dir / "image_generation_requests.md",
        run_dir / "image_generation_request_snapshot.json",
        run_dir / "asset_generation_requests.md",
        run_dir / "asset_generation_request_snapshot.json",
        run_dir / "asset_generation_manifest.md",
        run_dir / "asset_plan.md",
        run_dir / "image_prompt_story_review.md",
    )
    before = _capture_file_transaction(tracked_paths)
    asset_snapshot_path = tracked_paths[4]

    def captured_request_item_digests(content: bytes | None) -> tuple[tuple[str, str], ...]:
        if content is None:
            return ()
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return ()
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            return ()
        return tuple(
            sorted(
                (
                    str(item.get("destination") or ""),
                    str(item.get("request_digest") or ""),
                )
                for item in payload["items"]
                if isinstance(item, dict)
            )
        )

    before_asset_request_digests = captured_request_item_digests(before[asset_snapshot_path])
    try:
        compiled_selectors = _recompile_image_prompt_payloads_from_plans(run_dir)
        _write_asset_request_files(run_dir)
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "generate-assets-from-manifest.py"),
                "--manifest",
                str(run_dir / "video_manifest.md"),
                "--base-dir",
                str(run_dir),
                "--materialize-request-files-only",
                "--skip-videos",
                "--skip-audio",
                "--skip-image-prompt-review",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(detail or "image prompt request rematerialization failed")
        deterministic_review = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "review-image-prompt-story-consistency.py"),
                "--manifest",
                str(run_dir / "video_manifest.md"),
                "--story",
                str(run_dir / "story.md"),
                "--script",
                str(run_dir / "script.md"),
                "--out",
                str(run_dir / "image_prompt_story_review.md"),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if deterministic_review.returncode != 0:
            detail = deterministic_review.stderr.strip() or deterministic_review.stdout.strip()
            raise RuntimeError(detail or "deterministic image prompt review refresh failed")
        for required_path in tracked_paths[1:3]:
            if not required_path.is_file() or required_path.stat().st_size == 0:
                raise RuntimeError(f"image prompt repair output missing: {required_path.name}")
    except Exception:
        _restore_file_transaction(before)
        raise
    try:
        after_asset_snapshot = load_request_snapshot(
            asset_snapshot_path,
            run_dir=run_dir,
            verify_references=False,
        )
        after_asset_request_digests = tuple(
            sorted((item.destination, item.request_digest) for item in after_asset_snapshot.items)
        )
    except ImageRequestSnapshotError:
        after_asset_request_digests = ()
    asset_request_changed = before_asset_request_digests != after_asset_request_digests
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "review.semantic.image_prompt.repair.request_sync.status": "done",
            "review.semantic.image_prompt.repair.request_sync.compiled_count": str(len(compiled_selectors)),
            "review.semantic.image_prompt.repair.request_sync.compiled_selectors": ", ".join(compiled_selectors),
            "review.semantic.image_prompt.repair.request_sync.synced_at": now_iso(),
            "review.semantic.image_prompt.repair.asset_refresh_required": str(asset_request_changed).lower(),
            "review.image_prompt.request_freeze.status": "draft",
            "artifact.image_generation_requests": str(tracked_paths[1].resolve()),
            "artifact.image_generation_request_snapshot": str(tracked_paths[2].resolve()),
        },
    )


def _project_image_prompt_reviews_to_p630_p640(
    run_dir: Path,
    *,
    request_revision: str,
    provider_ready: bool = True,
) -> None:
    """Make legacy p630/p640 audit artifacts reflect the real review gates."""

    deterministic_path = run_dir / "image_prompt_story_review.md"
    semantic_relpath = semantic_review_relpaths("image_prompt")["report"]
    semantic_path = run_dir / semantic_relpath
    deterministic_text = deterministic_path.read_text(encoding="utf-8", errors="replace")
    semantic_text = semantic_path.read_text(encoding="utf-8", errors="replace")
    deterministic_status = _image_prompt_story_review_scalar(
        deterministic_text, "status"
    ).upper()
    hard_findings = _image_prompt_story_review_scalar(
        deterministic_text, "hard_findings"
    )
    unresolved_entries = _image_prompt_story_review_scalar(
        deterministic_text, "unresolved_entries"
    )
    hard_aggregate_path = (
        run_dir
        / "logs/eval/scene_implementation_hard/round_01/aggregated_review.md"
    )
    judgment_aggregate_path = (
        run_dir
        / "logs/eval/scene_implementation_judgment/round_01/aggregated_review.md"
    )
    hard_aggregate = "\n".join(
        [
            "# Hard Scene Eval/Improve Loop / Aggregated Review",
            "",
            "status: passed",
            f"request_revision: {request_revision}",
            "source_review: image_prompt_story_review.md",
            f"deterministic_status: {deterministic_status}",
            f"hard_findings: {hard_findings}",
            f"unresolved_entries: {unresolved_entries}",
            "",
            "実際の deterministic story-consistency gate が同一 request revision を検査し、blocking finding がないことを確認した。",
            "",
        ]
    )
    judgment_aggregate = "\n".join(
        [
            "# Judgment Eval/Improve Loop / Aggregated Review",
            "",
            "status: passed",
            f"request_revision: {request_revision}",
            f"source_review: {semantic_relpath.as_posix()}",
            "",
            (
                "provider-ready prompt の semantic review / repair / recompile / rereview が合格した。"
                if provider_ready
                else "deferred reference を含む draft prompt の semantic review / repair / recompile / rereview が合格した。media生成前にreference bytesを束縛して再確認する。"
            ),
            "",
        ]
    )
    _atomic_write_text(hard_aggregate_path, hard_aggregate)
    _atomic_write_text(judgment_aggregate_path, judgment_aggregate)
    _atomic_write_text(
        run_dir / "manifest_review.md",
        "\n".join(
            [
                "# Hard Scene Eval/Improve Loop",
                "",
                "status: approved",
                f"request_revision: {request_revision}",
                "source_review: image_prompt_story_review.md",
                "",
                hard_aggregate,
            ]
        ),
    )
    _atomic_write_text(
        run_dir / "image_prompt_judgment_review.md",
        "\n".join(
            [
                "# Judgment Eval/Improve Loop",
                "",
                "status: approved",
                f"request_revision: {request_revision}",
                f"source_review: {semantic_relpath.as_posix()}",
                "",
                judgment_aggregate,
            ]
        ),
    )
    # The legacy judgment path is still part of the p640 audit surface.  Mirror
    # the real semantic report rather than leaving its materialization template
    # in a misleading pending state.
    _atomic_write_text(run_dir / "logs/review/image_prompt.judgment.md", semantic_text)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "eval.scene_implementation_hard.loop.status": "passed",
            "eval.scene_implementation_hard.loop.current_round": "1",
            "eval.scene_implementation_hard.loop.round_01.status": "passed",
            "eval.scene_implementation_hard.loop.round_01.aggregated_review": str(
                hard_aggregate_path.relative_to(run_dir)
            ),
            "eval.scene_implementation_judgment.loop.status": "passed",
            "eval.scene_implementation_judgment.loop.current_round": "1",
            "eval.scene_implementation_judgment.loop.round_01.status": "passed",
            "eval.scene_implementation_judgment.loop.round_01.aggregated_review": str(
                judgment_aggregate_path.relative_to(run_dir)
            ),
            "review.image_prompt.judgment.status": "passed",
            "review.image_prompt.judgment.error_count": "0",
            "slot.p630.status": "done",
            "slot.p630.note": (
                "deterministic image-prompt hard gate passed for provider-ready revision"
                if provider_ready
                else "deterministic image-prompt hard gate passed for reviewed draft revision"
            ),
            "slot.p640.status": "done",
            "slot.p640.note": (
                "semantic image-prompt review and repair loop passed for provider-ready revision"
                if provider_ready
                else "semantic image-prompt review and repair loop passed for reviewed draft revision"
            ),
            "artifact.manifest_review": str((run_dir / "manifest_review.md").resolve()),
            "artifact.image_prompt_judgment_review": str(
                (run_dir / "image_prompt_judgment_review.md").resolve()
            ),
        },
    )


def _mark_image_prompt_draft_reviewed(run_dir: Path, *, request_revision: str) -> None:
    """Record semantic approval without claiming provider-ready reference binding."""

    deterministic_errors = _deterministic_image_prompt_hard_gate_errors(run_dir)
    if deterministic_errors:
        raise RuntimeError(
            "draft image prompt deterministic review failed: "
            + "; ".join(deterministic_errors)
        )
    semantic_result = check_semantic_review(run_dir, "image_prompt")
    if not semantic_result.passed:
        raise RuntimeError(
            "draft image prompt semantic review is not passed: "
            + "; ".join(semantic_result.errors)
        )
    _project_image_prompt_reviews_to_p630_p640(
        run_dir,
        request_revision=request_revision,
        provider_ready=False,
    )
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "review.image_prompt.request_freeze.status": "reviewed_draft",
            "review.image_prompt.request_freeze.reviewed_request_revision": request_revision,
            "review.image_prompt.request_freeze.semantic_input_mode": "deferred_references",
            "review.image_prompt.request_freeze.semantic_report": str(
                semantic_review_relpaths("image_prompt")["report"]
            ),
            "review.image_prompt.request_freeze.reviewed_at": now_iso(),
            "slot.p650.status": "pending",
            "slot.p650.note": "semantic prompt review passed; media generation and provider-ready reference freeze not requested",
        },
    )


def _mark_image_prompt_request_freeze_done(run_dir: Path) -> None:
    _manifest_path, _original_text, manifest_data = _read_manifest_data(run_dir)
    request_revision = _validate_image_prompt_request_revision(
        run_dir,
        manifest_data,
        require_resolved_references=True,
        require_compiled_v2=True,
    )
    deterministic_errors = _deterministic_image_prompt_hard_gate_errors(run_dir)
    if deterministic_errors:
        raise RuntimeError(
            "ToC run did not reach p650: deterministic image prompt review failed: "
            + "; ".join(deterministic_errors)
        )
    semantic_result = check_semantic_review(run_dir, "image_prompt")
    if not semantic_result.passed:
        raise RuntimeError(
            "ToC run did not reach p650: semantic image prompt review is not passed: "
            + "; ".join(semantic_result.errors)
        )
    if not _semantic_review_report_sources_are_current(run_dir, "image_prompt"):
        raise RuntimeError(
            "ToC run did not reach p650: semantic image prompt review is stale for the request revision"
        )
    _project_image_prompt_reviews_to_p630_p640(
        run_dir,
        request_revision=request_revision,
        provider_ready=True,
    )
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "review.image_prompt.request_freeze.status": "frozen",
            "review.image_prompt.request_freeze.request_revision": request_revision,
            "review.image_prompt.request_freeze.reviewed_request_revision": request_revision,
            "review.image_prompt.request_freeze.semantic_report": str(
                semantic_review_relpaths("image_prompt")["report"]
            ),
            "review.image_prompt.request_freeze.frozen_at": now_iso(),
            "slot.p650.status": "done",
            "slot.p650.note": "semantic image-prompt review passed; compiled requests frozen",
        },
    )
    _finalize_p600_supervisor_result(
        run_dir,
        completed_slots=("p610", "p620", "p630", "p640", "p650"),
        terminal_slot="p650",
        terminal_status="done",
        review_outputs=(
            "image_prompt_story_review.md",
            semantic_review_relpaths("image_prompt")["report"].as_posix(),
        ),
    )


def _finalize_p600_supervisor_result(
    run_dir: Path,
    *,
    completed_slots: Iterable[str],
    terminal_slot: str,
    terminal_status: str,
    review_outputs: Iterable[str] = (),
) -> None:
    """Advance the p600 supervisor artifact to the latest truthful handoff."""

    result_path = run_dir / "logs/orchestration/p600.supervisor_result.json"
    if not result_path.is_file():
        return
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict):
        return
    completed = _dedupe_preserve_order(
        [
            *[str(value).strip() for value in payload.get("completed_slots") or [] if str(value).strip()],
            *[str(value).strip() for value in completed_slots if str(value).strip()],
        ]
    )
    outputs = _dedupe_preserve_order(
        [
            *[str(value).strip() for value in payload.get("review_outputs") or [] if str(value).strip()],
            *[str(value).strip() for value in review_outputs if str(value).strip()],
        ]
    )
    finished_at = now_iso()
    state_updates = {
        "orchestration.p600.supervisor.call_status": "returned",
        "orchestration.p600.supervisor.status": "done",
        "orchestration.p600.supervisor.finished_at": finished_at,
        "orchestration.p600.supervisor.result": "logs/orchestration/p600.supervisor_result.json",
    }
    append_state_snapshot(run_dir / "state.txt", state_updates)
    payload.update(
        {
            "bucket": "p600",
            "status": "done",
            "completed_slots": completed,
            "state_keys": {
                "orchestration.p600.supervisor.call_status": "returned",
                "orchestration.p600.supervisor.status": "done",
                "orchestration.p600.supervisor.result": "logs/orchestration/p600.supervisor_result.json",
                f"slot.{terminal_slot}.status": terminal_status,
            },
            "review_outputs": outputs,
            "next_bucket": None,
            "finished_at": finished_at,
        }
    )
    _atomic_write_text(result_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


async def _start_app_server_with_log(client: CodexAppServerClient, *, run_dir: Path, operation: str, item_id: str) -> None:
    try:
        await client.start()
        write_app_server_debug_log(
            run_dir=run_dir,
            operation=f"{operation}_start",
            status="completed",
            item_id=item_id,
            request={"cwd": str(ROOT)},
        )
    except Exception as exc:
        write_app_server_debug_log(
            run_dir=run_dir,
            operation=f"{operation}_start",
            status="failed",
            item_id=item_id,
            request={"cwd": str(ROOT)},
            error=str(exc),
        )
        raise


async def _upgrade_initial_request_prompts(job_id: str, *, run_id: str) -> None:
    run_dir = safe_run_dir(run_id, ROOT)
    if app_server_disabled():
        return
    await _set_create_job(job_id, {"message": "画像生成プロンプトを高密度化中"})
    client = create_codex_app_server_client(cwd=ROOT)
    try:
        await _start_app_server_with_log(client, run_dir=run_dir, operation="prompt_upgrade", item_id="create_flow")
        for kind in ("asset", "scene"):
            items = [item for item in load_request_items(run_dir, kind) if _prompt_needs_quality_upgrade(item)]
            if not items:
                continue
            prompts: dict[str, str] = {}
            for item in items:
                target = _prompt_target_for_item(item)
                setting = read_prompt_setting(target, root=ROOT)
                prompt = await _regenerate_prompt_with_log(
                    client,
                    run_dir=run_dir,
                    item=item_to_api(item),
                    target=target,
                    instruction=(
                        "Upgrade this initial create-flow image prompt to the same quality as the manual asset creation flow. "
                        "Read and preserve the current run context from story.md, script.md, asset_plan.md, video_manifest.md, and existing request files. "
                        "Return a self-contained Japanese prompt with stable bracketed sections. "
                        "For character assets, include [全体 / 不変条件], [作成するもの], [人物固定], [衣装] when relevant, and [禁止]. "
                        "For scene images, include [全体 / 不変条件], [登場人物], [小道具 / 舞台装置] when relevant, [シーン], [連続性], and [禁止]. "
                        "For scene images, design the still as the visible initial state of the later video clip, but do not write authoring metadata such as `最初の1フレーム`, `1フレーム目`, or `first frame` in the prompt body. "
                        "Do not shorten or summarize. Make the prompt production-ready for cinematic live-action image generation."
                    ),
                    setting_content=str(setting["content"]),
                    operation="prompt_upgrade",
                )
                prompts[item.id] = prompt
            async with _serialized_run_write(run_dir, "run_artifacts"):
                async with _serialized_run_write(run_dir, f"{kind}_request_revision"):
                    update_result = update_request_prompts(run_dir, kind, prompts, allow_inline_prompt=True)
                    if update_result["missing"]:
                        raise RuntimeError(f"{kind} prompt upgrade failed for {', '.join(update_result['missing'])}")
                    append_state_snapshot(
                        run_dir / "state.txt",
                        {
                            f"review.frontend.{kind}_prompt_upgrade.status": "done",
                            f"review.frontend.{kind}_prompt_upgrade.count": str(len(update_result["updated"])),
                        },
                    )
    finally:
        await client.stop()


def _run_relative_key(run_dir: Path, value: str) -> str:
    return resolve_run_relative(run_dir, value).resolve().relative_to(run_dir.resolve()).as_posix()


def _generation_order_references(item: Any) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *(getattr(item, "references", []) or []),
                *(getattr(item, "dependency_references", []) or []),
            ]
        )
    )


def _build_generation_groups(items: list[Any], *, run_dir: Path, kind: str) -> list[list[Any]]:
    output_items = [item for item in items if getattr(item, "output", None)]
    if not output_items:
        return []
    output_to_item: dict[str, Any] = {}
    for item in output_items:
        output = _run_relative_key(run_dir, str(item.output))
        if output in output_to_item:
            raise RuntimeError(f"{kind} generation plan has duplicate output: {output}")
        output_to_item[output] = item

    dependencies: dict[str, set[str]] = {item.id: set() for item in output_items}
    item_by_id = {item.id: item for item in output_items}
    for item in output_items:
        for ref in _generation_order_references(item):
            ref_key = _run_relative_key(run_dir, str(ref))
            producer = output_to_item.get(ref_key)
            if producer is not None:
                if producer.id == item.id:
                    raise RuntimeError(f"{kind} generation plan has cyclic reference dependencies: {item.id}")
                dependencies[item.id].add(producer.id)
                continue
            reference = resolve_run_relative(run_dir, str(ref))
            if not reference.exists() or not reference.is_file():
                raise RuntimeError(f"{kind} reference not found before generation plan: {item.id}: {ref}")
            require_image_file(reference)

    groups: list[list[Any]] = []
    resolved: set[str] = set()
    pending = set(item_by_id)
    while pending:
        ready_ids = [item.id for item in output_items if item.id in pending and dependencies[item.id] <= resolved]
        if not ready_ids:
            cycle_ids = ", ".join(sorted(pending))
            raise RuntimeError(f"{kind} generation plan has cyclic reference dependencies: {cycle_ids}")
        groups.append([item_by_id[item_id] for item_id in ready_ids])
        resolved.update(ready_ids)
        pending.difference_update(ready_ids)
    return groups


def _validate_generation_groups(groups: list[list[Any]], *, run_dir: Path, kind: str) -> None:
    available = {path.relative_to(run_dir).as_posix() for path in run_dir.glob("assets/**/*") if path.is_file()}
    for index, group in enumerate(groups, start=1):
        group_outputs = {str(item.output) for item in group if getattr(item, "output", None)}
        for item in group:
            for ref in _generation_order_references(item):
                ref_key = _run_relative_key(run_dir, str(ref))
                if ref_key in group_outputs:
                    raise RuntimeError(f"{kind} generation group {index} has same-phase reference dependency: {item.id}: {ref}")
                if ref_key not in available:
                    producer_in_later_group = any(
                        ref_key == _run_relative_key(run_dir, str(other.output))
                        for later in groups[index:]
                        for other in later
                        if getattr(other, "output", None)
                    )
                    if producer_in_later_group:
                        raise RuntimeError(f"{kind} generation group {index} depends on a later group: {item.id}: {ref}")
        available.update(_run_relative_key(run_dir, str(item.output)) for item in group if getattr(item, "output", None))


def _validate_generated_group_outputs(group: list[Any], *, run_dir: Path, kind: str, group_index: int) -> None:
    issues: list[str] = []
    for item in group:
        if not getattr(item, "output", None):
            continue
        try:
            output = resolve_run_relative(run_dir, str(item.output))
            require_image_file(output)
            if not output.is_file():
                issues.append(str(item.output))
                continue
            validate_image_bytes(output)
        except (OSError, ValueError) as exc:
            issues.append(f"{item.output}: {exc}")
    if issues:
        raise RuntimeError(f"{kind} generation group {group_index} incomplete: {', '.join(issues)}")


def _is_transient_codex_image_error(exc: Exception) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return True
    message = str(exc).lower()
    return any(marker in message for marker in TRANSIENT_CODEX_IMAGE_ERRORS)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_completed_app_server_image_provenance(
    run_dir: Path,
    *,
    item_id: str,
    destination: Path,
    prompt_sha256: str,
    reference_sha256s: list[str],
    request_revision: str | None = None,
    request_digest: str | None = None,
    compiler_version: str | None = None,
    source_digest: str | None = None,
) -> bool:
    log_dir = run_dir / "logs" / "app_server" / "image_gen"
    if not log_dir.exists() or not destination.is_file():
        return False
    destination_key = _run_relative_key(run_dir, str(destination))
    output_sha256 = _file_sha256(destination)
    for log_path in sorted(log_dir.glob("*.json"), reverse=True):
        try:
            payload = json.loads(log_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("itemId") or "") != str(item_id):
            continue
        try:
            logged_destination = _run_relative_key(run_dir, str(payload.get("destination") or ""))
        except ValueError:
            continue
        if logged_destination != destination_key:
            continue
        if str(payload.get("status") or "").lower() not in {"completed", "succeeded"}:
            continue
        provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
        source = str(provenance.get("source") or payload.get("source") or "").lower()
        if source != "app_server":
            continue
        policy = str(provenance.get("policy") or "")
        if policy != IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2:
            continue
        if provenance.get("authoritative") is not True:
            continue
        if not str(provenance.get("generationJobId") or "").strip():
            continue
        provenance_item_id = str(provenance.get("itemId") or "")
        if provenance_item_id != str(item_id):
            continue
        if not str(provenance.get("turnId") or "").strip():
            continue
        if not str(provenance.get("imageGenerationItemId") or "").strip():
            continue
        try:
            image_item_count = int(provenance.get("imageGenerationItemCount") or 0)
        except (TypeError, ValueError):
            continue
        if image_item_count != 1:
            continue
        if not str(provenance.get("savedPath") or "").strip():
            continue
        if str(provenance.get("promptSha256") or "") != prompt_sha256:
            continue
        logged_reference_sha256s = provenance.get("referenceSha256s")
        if not isinstance(logged_reference_sha256s, list) or logged_reference_sha256s != reference_sha256s:
            continue
        if str(provenance.get("outputSha256") or "") != output_sha256:
            continue
        try:
            provenance_destination = _run_relative_key(run_dir, str(provenance.get("destination") or ""))
        except ValueError:
            continue
        if provenance_destination != destination_key:
            continue
        expected_snapshot_fields = {
            "requestDigest": request_digest,
            "compilerVersion": compiler_version,
            "sourceDigest": source_digest,
        }
        if any(
            expected is not None and str(provenance.get(field) or "") != str(expected)
            for field, expected in expected_snapshot_fields.items()
        ):
            continue
        return True
    return False


def _validate_request_bound_image_result(
    result: Any,
    *,
    generation_job_id: str,
    item_id: str,
    destination: Path,
    prompt_sha256: str,
    reference_sha256s: list[str],
) -> None:
    issues: list[str] = []
    if str(getattr(result, "provenance_policy", "") or "") != IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2:
        issues.append("provenance_policy")
    if str(getattr(result, "source", "") or "") != "app_server":
        issues.append("source")
    if str(getattr(result, "generation_job_id", "") or "") != generation_job_id:
        issues.append("generation_job_id")
    if str(getattr(result, "item_id", "") or "") != item_id:
        issues.append("item_id")
    if str(getattr(result, "prompt_sha256", "") or "") != prompt_sha256:
        issues.append("prompt_sha256")
    actual_reference_sha256s = getattr(result, "reference_sha256s", None)
    if not isinstance(actual_reference_sha256s, list) or actual_reference_sha256s != reference_sha256s:
        issues.append("reference_sha256s")
    try:
        actual_destination = Path(str(getattr(result, "destination", "") or "")).resolve()
    except (OSError, ValueError):
        actual_destination = Path(".")
    if actual_destination != destination.resolve():
        issues.append("destination")
    if not str(getattr(result, "turn_id", "") or "").strip():
        issues.append("turn_id")
    if not str(getattr(result, "image_generation_item_id", "") or "").strip():
        issues.append("image_generation_item_id")
    if int(getattr(result, "image_generation_item_count", 0) or 0) != 1:
        issues.append("image_generation_item_count")
    if not bool(getattr(result, "provenance_authoritative", False)):
        issues.append("provenance_authoritative")
    if issues:
        raise RuntimeError(
            f"Codex app-server request-bound provenance mismatch for {item_id}: {', '.join(issues)}"
        )


async def _generate_request_item_output(*, run_dir: Path, kind: str, item: Any) -> None:
    provenance_policy = _image_generation_provenance_policy()
    async with _global_image_generation_slot(provenance_policy) as global_slot:
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="image_generation_global_slot",
            status="acquired",
            item_id=str(getattr(item, "id", "")),
            request={
                "kind": kind,
                "slot": global_slot,
                "provenancePolicy": provenance_policy,
                "globalParallelism": 1
                if provenance_policy == IMAGE_GENERATION_PROVENANCE_POLICY_SERIAL_FALLBACK
                else max(1, int(IMAGE_GENERATION_GLOBAL_PARALLELISM)),
            },
        )
        await _generate_request_item_output_with_slot(run_dir=run_dir, kind=kind, item=item)


async def _generate_request_item_output_with_slot(*, run_dir: Path, kind: str, item: Any) -> None:
    if not getattr(item, "output", None):
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="request_item_generation",
            status="skipped",
            item_id=str(getattr(item, "id", "")),
            request={"kind": kind, "reason": "missing output"},
        )
        return
    if not str(getattr(item, "prompt", "") or "").strip():
        raise RuntimeError(f"{kind} request has no prompt: {item.id}")
    destination = resolve_run_relative(run_dir, str(item.output))
    references: list[Path] = []
    for ref in getattr(item, "references", []) or []:
        reference = resolve_run_relative(run_dir, str(ref))
        if not reference.exists() or not reference.is_file():
            raise RuntimeError(f"{kind} reference not found for {item.id}: {ref}")
        require_image_file(reference)
        references.append(reference)
    prompt_sha256 = hashlib.sha256(str(item.prompt).encode("utf-8")).hexdigest()
    reference_sha256s = [_file_sha256(reference) for reference in references]
    snapshot_prompt_sha256 = str(getattr(item, "prompt_sha256", "") or "")
    if snapshot_prompt_sha256 and snapshot_prompt_sha256 != prompt_sha256:
        raise RuntimeError(f"{kind} request snapshot prompt hash changed before send: {item.id}")
    snapshot_reference_sha256s = getattr(item, "reference_sha256s", None)
    if isinstance(snapshot_reference_sha256s, list) and snapshot_reference_sha256s:
        if len(snapshot_reference_sha256s) != len(reference_sha256s):
            raise RuntimeError(f"{kind} request snapshot reference count changed before send: {item.id}")
        for index, (expected, actual) in enumerate(
            zip(snapshot_reference_sha256s, reference_sha256s, strict=False)
        ):
            if expected is not None and str(expected) != actual:
                raise RuntimeError(
                    f"{kind} request snapshot reference hash changed before send: {item.id} reference {index}"
                )
    if (
        str(getattr(item, "prompt_policy_version", "") or "") == "image_api_prompt_v2"
        and not str(getattr(item, "request_revision", "") or "").strip()
    ):
        raise RuntimeError(f"{kind} request v2 requires an immutable request snapshot: {item.id}")
    if destination.exists():
        if _has_completed_app_server_image_provenance(
            run_dir,
            item_id=str(item.id),
            destination=destination,
            prompt_sha256=prompt_sha256,
            reference_sha256s=reference_sha256s,
            request_revision=getattr(item, "request_revision", None),
            request_digest=getattr(item, "request_digest", None),
            compiler_version=getattr(item, "compiler_version", None),
            source_digest=getattr(item, "source_digest", None),
        ):
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="request_item_generation",
                status="skipped",
                item_id=str(item.id),
                request={
                    "kind": kind,
                    "reason": "destination already exists",
                    "output": str(item.output),
                    "destination": str(destination),
                },
            )
            return
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="request_item_generation",
            status="retrying",
            item_id=str(item.id),
            request={
                "kind": kind,
                "reason": "existing destination is stale and will be replaced only after successful generation",
                "output": str(item.output),
                "destination": str(destination),
                "promptSha256": prompt_sha256,
                "referenceSha256s": reference_sha256s,
            },
        )
    started = time.monotonic()
    generation_job_id = uuid.uuid4().hex
    provenance_policy = _image_generation_provenance_policy()
    allow_generated_images_fallback = provenance_policy != IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2
    write_app_server_debug_log(
        run_dir=run_dir,
        operation="request_item_generation",
        status="started",
        item_id=str(item.id),
        request={
            "kind": kind,
            "output": str(item.output),
            "destination": str(destination),
            "referenceCount": len(references),
            "references": [str(ref) for ref in references],
            "promptLength": len(str(item.prompt or "")),
            "promptSha256": prompt_sha256,
            "referenceSha256s": reference_sha256s,
            "executionLane": str(getattr(item, "execution_lane", "") or ""),
            "assetType": str(getattr(item, "asset_type", "") or ""),
            "timeoutSeconds": IMAGE_GENERATION_ITEM_TIMEOUT_SECONDS,
            "maxAttempts": IMAGE_GENERATION_ITEM_MAX_ATTEMPTS,
            "generationJobId": generation_job_id,
            "provenancePolicy": provenance_policy,
            "allowGeneratedImagesFallback": allow_generated_images_fallback,
        },
    )
    client = create_codex_app_server_client(
        cwd=ROOT,
        scrub_sensitive_env=True,
        require_chatgpt_account=True,
        require_chatgpt_pro=True,
    )
    result = None
    debug_log = None
    retention_record: dict[str, Any] | None = None
    try:
        await asyncio.wait_for(client.start(), timeout=CODEX_APP_SERVER_START_TIMEOUT_SECONDS)
        async with _generated_images_fallback_claim_scope(allow_generated_images_fallback):
            generated_root = client.generated_images_root() if hasattr(client, "generated_images_root") else None
            fallback_cutoff_ns = latest_generated_image_mtime_ns(generated_root) if allow_generated_images_fallback else None
            for attempt in range(1, IMAGE_GENERATION_ITEM_MAX_ATTEMPTS + 1):
                try:
                    result = await asyncio.wait_for(
                        client.generate_image(
                            prompt=item.prompt,
                            output_path=destination,
                            reference_images=references,
                            item_id=item.id,
                            run_dir=run_dir,
                            fallback_cutoff_ns=fallback_cutoff_ns,
                            generation_job_id=generation_job_id,
                            allow_generated_images_fallback=allow_generated_images_fallback,
                            provenance_policy=provenance_policy,
                            timeout_seconds=max(1, int(IMAGE_GENERATION_ITEM_TIMEOUT_SECONDS)),
                        ),
                        timeout=_image_generation_outer_timeout_seconds(),
                    )
                    if result.saved_path is None:
                        raise RuntimeError(f"Codex app-server did not return an image for {item.id}")
                    reject_local_raster_image_result(result, item_id=item.id)
                    if provenance_policy == IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2 and not bool(getattr(result, "provenance_authoritative", False)):
                        raise RuntimeError(f"Codex app-server did not return authoritative request-bound provenance for {item.id}")
                    if provenance_policy == IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2:
                        _validate_request_bound_image_result(
                            result,
                            generation_job_id=generation_job_id,
                            item_id=str(item.id),
                            destination=destination,
                            prompt_sha256=prompt_sha256,
                            reference_sha256s=reference_sha256s,
                        )
                    retention_record = retain_first_image(
                        result.saved_path,
                        root=ROOT,
                        run_id=run_dir.name,
                        kind=kind,
                        item_id=str(item.id),
                        candidate_index=1,
                        destination=str(item.output),
                        storage_role="canonical",
                        provenance={
                            "generationJobId": generation_job_id,
                            "turnId": getattr(result, "turn_id", None),
                            "imageGenerationItemId": getattr(result, "image_generation_item_id", None),
                            "promptSha256": prompt_sha256,
                            "referenceSha256s": reference_sha256s,
                            "provenancePolicy": provenance_policy,
                            "provenanceAuthoritative": bool(getattr(result, "provenance_authoritative", False)),
                        },
                    )
                    break
                except Exception as exc:
                    if attempt >= IMAGE_GENERATION_ITEM_MAX_ATTEMPTS or not _is_transient_codex_image_error(exc):
                        raise
                    write_app_server_debug_log(
                        run_dir=run_dir,
                        operation="request_item_generation_retry",
                        status="retrying",
                        item_id=str(item.id),
                        request={
                            "kind": kind,
                            "output": str(item.output),
                            "attempt": attempt,
                            "generationJobId": generation_job_id,
                            "provenancePolicy": provenance_policy,
                        },
                        response=_codex_failure_context(exc, client=client),
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    await client.stop()
                    client = create_codex_app_server_client(cwd=ROOT)
                    await asyncio.wait_for(client.start(), timeout=CODEX_APP_SERVER_START_TIMEOUT_SECONDS)
        if result.saved_path is None:
            raise RuntimeError(f"Codex app-server did not return an image for {item.id}")
        copy_saved_image(result.saved_path, destination)
        debug_log = write_app_server_image_debug_log(
            run_dir=run_dir,
            item_id=item.id,
            index=1,
            destination=destination,
            references=references,
            prompt=item.prompt,
            kind=kind,
            prompt_policy_version=getattr(item, "prompt_policy_version", None),
            debug_prompt_source=getattr(item, "debug_prompt_source", None),
            request_revision=getattr(item, "request_revision", None),
            request_digest=getattr(item, "request_digest", None),
            compiler_version=getattr(item, "compiler_version", None),
            source_digest=getattr(item, "source_digest", None),
            result=result,
        )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="request_item_generation",
            status="completed",
            item_id=str(item.id),
            request={"kind": kind, "output": str(item.output)},
            response={
                "elapsedMs": int((time.monotonic() - started) * 1000),
                "debugLog": debug_log.relative_to(run_dir).as_posix() if debug_log else "",
                "savedPath": str(result.saved_path),
                "source": getattr(result, "source", "app_server"),
                "destinationExists": destination.exists(),
                "outputSha256": _file_sha256(destination),
                "generationJobId": generation_job_id,
                "turnId": getattr(result, "turn_id", None),
                "imageGenerationItemId": getattr(result, "image_generation_item_id", None),
                "provenancePolicy": provenance_policy,
                "provenanceAuthoritative": bool(getattr(result, "provenance_authoritative", False)),
                "retainedFirstImage": bool(retention_record),
                "retainedFirstImageCreated": bool(retention_record and retention_record.get("created")),
            },
        )
    except Exception as exc:
        write_app_server_image_debug_log(
            run_dir=run_dir,
            item_id=item.id,
            index=1,
            destination=destination,
            references=references,
            prompt=item.prompt,
            kind=kind,
            prompt_policy_version=getattr(item, "prompt_policy_version", None),
            debug_prompt_source=getattr(item, "debug_prompt_source", None),
            request_revision=getattr(item, "request_revision", None),
            request_digest=getattr(item, "request_digest", None),
            compiler_version=getattr(item, "compiler_version", None),
            source_digest=getattr(item, "source_digest", None),
            result=result,
            error=str(exc),
        )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="request_item_generation",
            status="failed",
            item_id=str(item.id),
            request={"kind": kind, "output": str(item.output), "referenceCount": len(references)},
            response={
                "elapsedMs": int((time.monotonic() - started) * 1000),
                "failureContext": _codex_failure_context(exc, client=client),
                "generationJobId": generation_job_id,
                "provenancePolicy": provenance_policy,
            },
            error=f"{type(exc).__name__}: {exc}",
        )
        raise
    finally:
        await client.stop()


async def _generate_request_outputs(*, run_dir: Path, kind: str) -> None:
    # Keep the immutable request snapshot stable from load through provider
    # submission. Prompt edits/materialization use this same revision lock.
    async with _serialized_run_write(run_dir, f"{kind}_request_revision"):
        await _generate_request_outputs_unlocked(run_dir=run_dir, kind=kind)


async def _generate_request_outputs_unlocked(*, run_dir: Path, kind: str) -> None:
    items = load_request_items(run_dir, kind)
    if not items:
        raise RuntimeError(f"{kind} request file has no {kind} items")
    if app_server_disabled():
        raise RuntimeError("Codex app-server is disabled")
    blocked_item_ids = _semantic_blocked_image_item_ids(run_dir, items) if kind == "scene" else set()
    skipped_items = [item for item in items if str(getattr(item, "id", "") or "") in blocked_item_ids]
    if skipped_items:
        items = [item for item in items if str(getattr(item, "id", "") or "") not in blocked_item_ids]
        blocked_ids = [str(getattr(item, "id", "") or "") for item in skipped_items]
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "review.semantic.scene_detail.partial_media_generated": "true",
                "review.semantic.partial_media.blocked_image_items": ", ".join(blocked_ids),
                "review.semantic.partial_media.blocked_image_item_count": str(len(blocked_ids)),
            },
        )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="request_generation_skip",
            status="skipped",
            item_id=kind,
            request={
                "kind": kind,
                "reason": "localized semantic QA blocked selected scene image items",
                "skippedItemIds": blocked_ids,
            },
        )
    if not items:
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="request_generation_batch",
            status="skipped",
            item_id=kind,
            request={
                "kind": kind,
                "reason": "all request items are blocked by localized semantic QA",
                "skippedItemCount": len(skipped_items),
            },
        )
        return
    groups = _build_generation_groups(items, run_dir=run_dir, kind=kind)
    if not groups:
        raise RuntimeError(f"{kind} request file has no output items")
    _validate_generation_groups(groups, run_dir=run_dir, kind=kind)
    provenance_policy = _image_generation_provenance_policy()
    parallelism_requested = max(1, int(IMAGE_GENERATION_PARALLELISM))
    parallelism_effective = _effective_image_generation_parallelism()
    write_app_server_debug_log(
        run_dir=run_dir,
        operation="request_generation_batch",
        status="started",
        item_id=kind,
        request={
            "kind": kind,
            "itemCount": len(items),
            "groupCount": len(groups),
            "parallelism": parallelism_effective,
            "parallelismRequested": parallelism_requested,
            "parallelismEffective": parallelism_effective,
            "provenancePolicy": provenance_policy,
            "groups": [
                {
                    "index": group_index,
                    "itemIds": [str(getattr(item, "id", "")) for item in group],
                    "outputs": [str(getattr(item, "output", "") or "") for item in group],
                }
                for group_index, group in enumerate(groups, start=1)
            ],
        },
    )
    semaphore = asyncio.Semaphore(parallelism_effective)
    for index, group in enumerate(groups, start=1):
        group_started = time.monotonic()
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="request_generation_group",
            status="started",
            item_id=f"{kind}_group_{index}",
            request={
                "kind": kind,
                "groupIndex": index,
                "groupCount": len(groups),
                "itemIds": [str(getattr(item, "id", "")) for item in group],
                "parallelismRequested": parallelism_requested,
                "parallelismEffective": parallelism_effective,
                "provenancePolicy": provenance_policy,
            },
        )

        continue_after_item_error = _continue_generation_after_item_error(kind)
        failure_event = asyncio.Event()

        async def generate_item(item: Any) -> None:
            async with semaphore:
                if failure_event.is_set() and not continue_after_item_error:
                    return
                try:
                    await _generate_request_item_output(run_dir=run_dir, kind=kind, item=item)
                except Exception:
                    if not continue_after_item_error:
                        failure_event.set()
                    raise

        try:
            tasks = [asyncio.create_task(generate_item(item)) for item in group]
            if continue_after_item_error:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                first_exception = next((result for result in results if isinstance(result, Exception)), None)
                if first_exception is not None:
                    try:
                        _validate_generated_group_outputs(group, run_dir=run_dir, kind=kind, group_index=index)
                    except RuntimeError as validation_exc:
                        raise validation_exc from first_exception
                    raise first_exception
            else:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                first_exception = next((task.exception() for task in done if task.exception() is not None), None)
                if first_exception is not None:
                    for task in pending:
                        task.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)
                    raise first_exception
                await asyncio.gather(*pending)
            _validate_generated_group_outputs(group, run_dir=run_dir, kind=kind, group_index=index)
        except Exception as exc:
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="request_generation_group",
                status="failed",
                item_id=f"{kind}_group_{index}",
                request={"kind": kind, "groupIndex": index, "itemCount": len(group)},
                response={"elapsedMs": int((time.monotonic() - group_started) * 1000)},
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="request_generation_group",
            status="completed",
            item_id=f"{kind}_group_{index}",
            request={"kind": kind, "groupIndex": index, "itemCount": len(group)},
            response={"elapsedMs": int((time.monotonic() - group_started) * 1000)},
        )
    write_app_server_debug_log(
        run_dir=run_dir,
        operation="request_generation_batch",
        status="completed",
        item_id=kind,
        request={
            "kind": kind,
            "itemCount": len(items),
            "groupCount": len(groups),
            "parallelism": parallelism_effective,
            "parallelismRequested": parallelism_requested,
            "parallelismEffective": parallelism_effective,
            "provenancePolicy": provenance_policy,
        },
    )


def _validate_generated_outputs(run_dir: Path, kind: str) -> None:
    issues: list[str] = []
    blocked_item_ids = _semantic_blocked_image_item_ids(run_dir) if kind == "scene" else set()
    for item in load_request_items(run_dir, kind):
        if str(getattr(item, "id", "") or "") in blocked_item_ids:
            continue
        if not item.output:
            issues.append(f"{item.id}: missing output")
            continue
        try:
            output = resolve_run_relative(run_dir, item.output)
            require_image_file(output)
            if not output.is_file():
                issues.append(item.output)
                continue
            validate_image_bytes(output)
            if str(getattr(item, "prompt_policy_version", "") or "") == "image_api_prompt_v2":
                references = [resolve_run_relative(run_dir, str(ref)) for ref in item.references]
                reference_sha256s = [_file_sha256(reference) for reference in references]
                if not _has_completed_app_server_image_provenance(
                    run_dir,
                    item_id=str(item.id),
                    destination=output,
                    prompt_sha256=hashlib.sha256(str(item.prompt).encode("utf-8")).hexdigest(),
                    reference_sha256s=reference_sha256s,
                    request_revision=getattr(item, "request_revision", None),
                    request_digest=getattr(item, "request_digest", None),
                    compiler_version=getattr(item, "compiler_version", None),
                    source_digest=getattr(item, "source_digest", None),
                ):
                    issues.append(f"{item.output}: missing strict request-bound provenance for current snapshot")
        except (OSError, ValueError) as exc:
            issues.append(f"{item.output}: {exc}")
    if issues:
        raise RuntimeError(f"{kind} image generation incomplete: {', '.join(issues)}")


def _validate_p680_visual_quality(run_dir: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(APP_ROOT / "scripts" / "verify-pipeline.py"),
            "--run-dir",
            str(run_dir),
            "--flow",
            "immersive",
            "--profile",
            "standard",
            "--stage-target",
            "p680",
        ],
        cwd=APP_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"p680 visual quality gate failed: {detail}")


def _validate_p560_asset_quality(run_dir: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(APP_ROOT / "scripts" / "verify-pipeline.py"),
            "--run-dir",
            str(run_dir),
            "--flow",
            "immersive",
            "--profile",
            "standard",
            "--stage-target",
            "p570",
        ],
        cwd=APP_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"p560 bootstrap asset visual gate failed: {detail}")


def _bootstrap_asset_items(run_dir: Path) -> list[Any]:
    return [
        item
        for item in load_request_items(run_dir, "asset")
        if item.output
        and (
            item.reference_count == 0
            or not item.references
            or str(item.execution_lane or "").strip() == "bootstrap_builtin"
        )
    ]


def _remove_bootstrap_asset_outputs(run_dir: Path) -> None:
    for item in _bootstrap_asset_items(run_dir):
        if not item.output:
            continue
        output = resolve_run_relative(run_dir, item.output)
        with suppress(FileNotFoundError):
            if output.is_file():
                output.unlink()


async def _repair_bootstrap_asset_prompts(job_id: str, *, run_dir: Path, failure_detail: str, attempt: int) -> None:
    items = _bootstrap_asset_items(run_dir)
    if not items or app_server_disabled():
        return
    await _set_create_job(job_id, {"message": "素材画像を生成中"})
    client = create_codex_app_server_client(cwd=ROOT)
    try:
        await _start_app_server_with_log(client, run_dir=run_dir, operation="prompt_repair", item_id="asset_visual_gate")
        prompts: dict[str, str] = {}
        for item in items:
            target = _prompt_target_for_item(item)
            setting = read_prompt_setting(target, root=ROOT)
            prompt = await _regenerate_prompt_with_log(
                client,
                run_dir=run_dir,
                item=item_to_api(item),
                target=target,
                instruction=(
                    "Revise this no-reference bootstrap asset prompt because the generated raster failed the visual quality gate. "
                    "Make the next output unmistakably photorealistic live-action, high-detail, textured, naturally lit, and usable as a downstream reference image. "
                    "Explicitly avoid flat illustration, vector art, SVG-like shapes, cel shading, anime, cartoon, low-detail poster styling, and simple graphic design. "
                    "Keep the prompt self-contained Japanese with stable bracketed sections. "
                    f"Gate failure detail from attempt {attempt}: {failure_detail[:1200]}"
                ),
                setting_content=str(setting["content"]),
                operation="prompt_repair",
            )
            prompts[item.id] = prompt
        async with _serialized_run_write(run_dir, "run_artifacts"):
            async with _serialized_run_write(run_dir, "asset_request_revision"):
                update_result = update_request_prompts(run_dir, "asset", prompts, allow_inline_prompt=True)
                if update_result["missing"]:
                    raise RuntimeError(f"asset prompt repair failed for {', '.join(update_result['missing'])}")
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        "review.asset_visual_gate.repair.status": "done",
                        "review.asset_visual_gate.repair.attempt": str(attempt),
                        "review.asset_visual_gate.repair.count": str(len(update_result["updated"])),
                    },
                )
    finally:
        await client.stop()


def _mark_image_generation_review_ready(run_id: str) -> None:
    run_dir = safe_run_dir(run_id, ROOT)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "status": "P680",
            "runtime.stage": "scene_images_ready_for_review",
            "slot.p660.status": "done",
            "slot.p660.note": "scene images generated",
            "slot.p670.status": "skipped",
            "slot.p670.note": "scene image semantic QA removed; frontend human review is next",
            "slot.p680.status": "awaiting_approval",
            "slot.p680.note": "scene image human review ready in frontend",
            "stage.scene_implementation.status": "awaiting_approval",
            "review.image.status": "pending",
            "gate.image_review": "required",
        },
    )
    _finalize_p600_supervisor_result(
        run_dir,
        completed_slots=("p610", "p620", "p630", "p640", "p650", "p660", "p670", "p680"),
        terminal_slot="p680",
        terminal_status="awaiting_approval",
    )


def _validate_image_review_ready(run_id: str) -> None:
    run_dir = safe_run_dir(run_id, ROOT)
    _validate_generated_outputs(run_dir, "asset")
    _validate_generated_outputs(run_dir, "scene")
    _validate_p680_visual_quality(run_dir)
    state = parse_state_file(run_dir / "state.txt")
    expected = {
        "slot.p660.status": "done",
        "slot.p670.status": "skipped",
        "slot.p680.status": "awaiting_approval",
        "review.image.status": "pending",
    }
    mismatches = [f"{key}={state.get(key)}" for key, value in expected.items() if state.get(key) != value]
    if mismatches:
        raise RuntimeError(f"image review handoff incomplete: {', '.join(mismatches)}")


def _scene_numbers_from_scene_selectors(selectors: Iterable[Any]) -> set[str]:
    scene_numbers: set[str] = set()
    pattern = re.compile(r"\bscene[_:]?(\d+)\b|\bscene(\d+)_cut\b|\bscene(\d+)cut\b")
    for selector in selectors:
        value = str(selector or "")
        for match in pattern.finditer(value):
            for group in match.groups():
                if group:
                    scene_numbers.add(str(int(group)))
                    break
    return scene_numbers


def _state_list_value(state: dict[str, str], key: str) -> list[str]:
    raw = str(state.get(key, "") or "").strip()
    if not raw:
        return []
    return [item.strip().strip("`\"'") for item in raw.split(",") if item.strip()]


def _normalized_scene_cut_token(value: Any) -> str:
    raw = str(value or "").strip().strip("`\"'")
    match = re.search(r"\bscene[_:]?(\d+)[_\-]?cut[_:]?0*(\d+)\b", raw)
    if not match:
        return raw
    return f"scene{int(match.group(1))}_cut{int(match.group(2))}"


def _image_item_selector_aliases(item: Any) -> set[str]:
    aliases: set[str] = set()
    item_id = str(getattr(item, "id", "") or "")
    output = str(getattr(item, "output", "") or "")
    for value in (item_id, Path(output).stem if output else ""):
        if value:
            aliases.add(value)
            aliases.add(_normalized_scene_cut_token(value))
    return {alias for alias in aliases if alias}


def _semantic_failure_selectors(
    run_dir: Path,
    stage: str,
    failure_context: dict[str, Any] | None = None,
) -> list[Any]:
    state = parse_state_file(run_dir / "state.txt")
    selectors: list[Any] = []
    if failure_context:
        for key in ("failedSelectors", "blockedEntries"):
            values = failure_context.get(key)
            if isinstance(values, list):
                selectors.extend(values)
    selectors.extend(_state_list_value(state, f"review.semantic.{stage}.failure.failed_selectors"))
    selectors.extend(_state_list_value(state, f"review.semantic.{stage}.failure.blocked_entries"))
    selectors.extend(_state_list_value(state, f"review.semantic.{stage}.blocked_image_items"))
    if stage == "asset_plan":
        selectors.extend(_asset_plan_source_selectors_for_failed_entries(run_dir, selectors))
    return selectors


def _asset_plan_source_selectors_for_failed_entries(run_dir: Path, selectors: Iterable[Any]) -> list[str]:
    selector_keys = {str(selector or "").strip().strip("`\"'") for selector in selectors if str(selector or "").strip()}
    if not selector_keys:
        return []
    normalized_keys = {_normalized_scene_cut_token(key) for key in selector_keys}
    asset_plan_path = run_dir / "asset_plan.md"
    if not asset_plan_path.exists():
        return []
    try:
        data = yaml.safe_load(_extract_manifest_yaml_text(asset_plan_path.read_text(encoding="utf-8"))) or {}
    except Exception:
        return []
    assets = data.get("assets") if isinstance(data, dict) else None
    if not isinstance(assets, list):
        return []
    source_selectors: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("asset_id") or "").strip()
        output_stem = Path(str(asset.get("generation_plan", {}).get("output") or asset.get("output") or "")).stem
        aliases = {asset_id, output_stem}
        aliases = {alias for alias in aliases if alias}
        if not (aliases & selector_keys or {_normalized_scene_cut_token(alias) for alias in aliases} & normalized_keys):
            continue
        for source_selector in asset.get("source_script_selectors") or []:
            text = str(source_selector or "").strip()
            if text:
                source_selectors.append(text)
    return source_selectors


def _scene_detail_transport_blocked_scene_numbers(run_dir: Path) -> set[str]:
    state = parse_state_file(run_dir / "state.txt")
    blocked: set[str] = set()
    pattern = re.compile(r"^review\.semantic\.scene_detail\.shards\.scene_(\d+)\.transport\.status$")
    for key, value in state.items():
        match = pattern.match(key)
        if match and str(value).strip().lower() == "failed":
            blocked.add(match.group(1))
    return blocked


def _scene_detail_semantic_blocked_scene_numbers(
    run_dir: Path,
    failure_context: dict[str, Any] | None = None,
) -> set[str]:
    return _scene_numbers_from_scene_selectors(
        _semantic_failure_selectors(run_dir, "scene_detail", failure_context=failure_context)
    )


def _scene_detail_blocked_scene_numbers(
    run_dir: Path,
    failure_context: dict[str, Any] | None = None,
) -> set[str]:
    return _scene_detail_transport_blocked_scene_numbers(run_dir) | _scene_detail_semantic_blocked_scene_numbers(
        run_dir,
        failure_context=failure_context,
    )


def _item_matches_scene_number(item: Any, scene_number: str) -> bool:
    item_id = str(getattr(item, "id", "") or "")
    output = str(getattr(item, "output", "") or "")
    scene_token = f"scene{scene_number}"
    return (
        item_id == scene_token
        or item_id.startswith(f"{scene_token}_")
        or item_id.startswith(f"{scene_token}cut")
        or f"/{scene_token}_" in output
        or f"/{scene_token}cut" in output
    )


def _scene_detail_transport_blocked_image_item_ids(run_dir: Path, items: list[Any] | None = None) -> set[str]:
    blocked_scene_numbers = _scene_detail_blocked_scene_numbers(run_dir)
    if not blocked_scene_numbers:
        return set()
    scene_items = items if items is not None else load_request_items(run_dir, "scene")
    return {
        str(getattr(item, "id", "") or "")
        for item in scene_items
        if any(_item_matches_scene_number(item, scene_number) for scene_number in blocked_scene_numbers)
    }


def _localized_semantic_blocked_image_item_ids(
    run_dir: Path,
    *,
    stage: str,
    items: list[Any] | None = None,
    failure_context: dict[str, Any] | None = None,
) -> set[str]:
    scene_items = items if items is not None else load_request_items(run_dir, "scene")
    if stage == "scene_detail":
        blocked_scene_numbers = _scene_detail_blocked_scene_numbers(run_dir, failure_context=failure_context)
        return {
            str(getattr(item, "id", "") or "")
            for item in scene_items
            if any(_item_matches_scene_number(item, scene_number) for scene_number in blocked_scene_numbers)
        }
    selectors = _semantic_failure_selectors(run_dir, stage, failure_context=failure_context)
    normalized_selectors = {_normalized_scene_cut_token(selector) for selector in selectors if str(selector or "").strip()}
    blocked_scene_numbers = _scene_numbers_from_scene_selectors(selectors)
    blocked_item_ids: set[str] = set()
    for item in scene_items:
        item_id = str(getattr(item, "id", "") or "")
        if not item_id:
            continue
        if _image_item_selector_aliases(item) & normalized_selectors:
            blocked_item_ids.add(item_id)
            continue
        if any(_item_matches_scene_number(item, scene_number) for scene_number in blocked_scene_numbers):
            blocked_item_ids.add(item_id)
    return blocked_item_ids


def _semantic_blocked_image_item_ids(run_dir: Path, items: list[Any] | None = None) -> set[str]:
    blocked: set[str] = set()
    for stage in ("scene_detail", "cut_blueprint", "asset_plan", "image_prompt"):
        blocked.update(_localized_semantic_blocked_image_item_ids(run_dir, stage=stage, items=items))
    return blocked


def _semantic_blocked_candidate(run_dir: Path, item: Any) -> dict[str, Any]:
    state = parse_state_file(run_dir / "state.txt")
    item_id = str(getattr(item, "id", "") or "")
    for stage in ("scene_detail", "cut_blueprint", "asset_plan", "image_prompt"):
        if item_id in _localized_semantic_blocked_image_item_ids(run_dir, stage=stage, items=[item]):
            if stage == "scene_detail":
                return _scene_detail_blocked_candidate(run_dir, item)
            reason_keys = state.get(f"review.semantic.{stage}.failure.reason_keys", "semantic_review_failed")
            return {
                "index": 1,
                "status": "failed",
                "path": None,
                "error": f"semantic {stage} failed; image generation skipped for this item ({reason_keys})",
            }
    return {
        "index": 1,
        "status": "failed",
        "path": None,
        "error": "semantic QA failed; image generation skipped for this item",
    }


def _scene_detail_blocked_candidate(run_dir: Path, item: Any) -> dict[str, Any]:
    state = parse_state_file(run_dir / "state.txt")
    transport_scene_numbers = _scene_detail_transport_blocked_scene_numbers(run_dir)
    blocked_scene_numbers = sorted(scene_number for scene_number in _scene_detail_blocked_scene_numbers(run_dir) if _item_matches_scene_number(item, scene_number))
    scene_number = blocked_scene_numbers[0] if blocked_scene_numbers else ""
    if scene_number in transport_scene_numbers:
        error_kind = state.get(f"review.semantic.scene_detail.shards.scene_{scene_number}.transport.error_kind", "timeout")
        error = f"semantic scene_detail transport {error_kind}; image generation skipped for this scene"
    else:
        reason_keys = state.get("review.semantic.scene_detail.failure.reason_keys", "semantic_review_failed")
        error = f"semantic scene_detail failed; image generation skipped for this scene ({reason_keys})"
    return {
        "index": 1,
        "status": "failed",
        "path": None,
        "error": error,
    }


async def _refresh_image_prompt_repair_assets_if_required(run_dir: Path) -> None:
    state = parse_state_file(run_dir / "state.txt")
    if state.get("review.semantic.image_prompt.repair.asset_refresh_required") != "true":
        return
    append_state_snapshot(
        run_dir / "state.txt",
        {"review.semantic.image_prompt.repair.asset_refresh.status": "generating"},
    )
    await _generate_request_outputs(run_dir=run_dir, kind="asset")
    _validate_p560_asset_quality(run_dir)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "review.semantic.image_prompt.repair.asset_refresh.status": "done",
            "review.semantic.image_prompt.repair.asset_refresh_required": "false",
            "review.semantic.image_prompt.repair.asset_refresh.finished_at": now_iso(),
        },
    )


async def _prepare_image_prompt_repair_revision_for_rereview(
    run_dir: Path,
    *,
    provider_ready: bool = True,
) -> None:
    """Synchronize a repair, refresh changed assets, then bind scene refs again."""

    _synchronize_image_prompt_repair_outputs(run_dir)
    state = parse_state_file(run_dir / "state.txt")
    if provider_ready and state.get("review.semantic.image_prompt.repair.asset_refresh_required") == "true":
        await _refresh_image_prompt_repair_assets_if_required(run_dir)
        # Asset bytes are part of the immutable scene request revision. Rebuild
        # the scene snapshot after refresh and before the fresh semantic review.
        _synchronize_image_prompt_repair_outputs(run_dir)
    elif state.get("review.semantic.image_prompt.repair.asset_refresh_required") == "true":
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "review.semantic.image_prompt.repair.asset_refresh.status": "deferred",
                "review.semantic.image_prompt.repair.asset_refresh.note": "media generation disabled; refreshed asset bytes will be required before provider-ready freeze",
            },
        )
    _prepare_image_prompt_request_revision_for_review(
        run_dir,
        provider_ready=provider_ready,
    )


async def _generate_scene_outputs_after_p650_preflight(
    job_id: str,
    *,
    run_id: str,
    run_dir: Path,
) -> None:
    """Validate, submit, and hand off one immutable scene request revision."""

    # Prompt edits and request rematerialization use this same lock.  Keeping
    # the final p650 validation, provider submission, and p680 handoff in one
    # critical section closes the validate-then-edit race.
    async with _serialized_run_write(run_dir, "scene_request_revision"):
        try:
            # This is the final p660 preflight: the reviewed provider prompt
            # bytes, reference hashes, semantic reports, and frozen revision
            # must still be the same revision that p650 approved.
            _validate_p650_run(run_id)
        except RuntimeError as exc:
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    "runtime.stage": "p650_gate_failed_before_scene_generation",
                    "slot.p660.status": "pending",
                    "slot.p660.note": "blocked before scene image generation by p650 revision validation",
                    "slot.p680.status": "pending",
                    "review.image.status": "pending",
                    "review.semantic.create_scene_media_generated": "false",
                    "image_generation.status": "not_started",
                    "image_generation.started": "false",
                    "image_generation.generated_count": "0",
                    "image_generation.blocked_by": "p650_revision_gate",
                },
            )
            raise RuntimeError(f"scene image generation blocked by p650 gate: {exc}") from exc
        await _set_create_job(job_id, {"message": "シーン画像を生成中"})
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "runtime.stage": "scene_images_generating",
                "slot.p660.status": "in_progress",
                "slot.p660.note": "scene image generation started after image-prompt semantic gate",
            },
        )
        # The outer revision lock is already held.  Calling the locked wrapper
        # here would deadlock because asyncio locks are not re-entrant.
        await _generate_request_outputs_unlocked(run_dir=run_dir, kind="scene")
        _mark_image_generation_review_ready(run_id)


async def _generate_create_images(job_id: str, *, run_id: str) -> bool:
    run_dir = safe_run_dir(run_id, ROOT)
    semantic_failures: list[str] = []
    failed_semantic_stages: set[str] = set()
    await _set_create_job(job_id, {"message": "上流設計をsemantic QA中"})
    for stage in ("scene_set", "scene_detail", "cut_blueprint", "asset_plan"):
        failure = await _run_semantic_review_for_media_generation(job_id, run_dir=run_dir, stage=stage)
        if failure:
            semantic_failures.append(failure)
            failed_semantic_stages.add(stage)
    asset_quality_passed = False
    last_asset_gate_error = ""
    for attempt in range(1, BOOTSTRAP_ASSET_MAX_ATTEMPTS + 1):
        await _set_create_job(job_id, {"message": "素材画像を生成中"})
        await _generate_request_outputs(run_dir=run_dir, kind="asset")
        try:
            _validate_p560_asset_quality(run_dir)
        except RuntimeError as exc:
            last_asset_gate_error = str(exc)
            if attempt >= BOOTSTRAP_ASSET_MAX_ATTEMPTS:
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        "review.asset_visual_gate.status": "needs_frontend_review",
                        "review.asset_visual_gate.attempts": str(attempt),
                        "review.asset_visual_gate.last_error": last_asset_gate_error[:2000],
                    },
                )
                break
            try:
                await asyncio.wait_for(
                    _repair_bootstrap_asset_prompts(
                        job_id,
                        run_dir=run_dir,
                        failure_detail=last_asset_gate_error,
                        attempt=attempt,
                    ),
                    timeout=PROMPT_REPAIR_TIMEOUT_SECONDS,
                )
                _remove_bootstrap_asset_outputs(run_dir)
            except Exception as repair_exc:
                write_app_server_debug_log(
                    run_dir=run_dir,
                    operation="prompt_repair",
                    status="failed",
                    item_id="asset_visual_gate",
                    request={"attempt": attempt, "timeoutSeconds": PROMPT_REPAIR_TIMEOUT_SECONDS},
                    error=f"{type(repair_exc).__name__}: {repair_exc}",
                )
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        "review.asset_visual_gate.status": "needs_frontend_review",
                        "review.asset_visual_gate.attempts": str(attempt),
                        "review.asset_visual_gate.last_error": last_asset_gate_error[:2000],
                        "review.asset_visual_gate.repair.status": "failed",
                        "review.asset_visual_gate.repair.error": str(repair_exc)[:2000],
                    },
                )
                break
        else:
            asset_quality_passed = True
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    "review.asset_visual_gate.status": "passed",
                    "review.asset_visual_gate.attempts": str(attempt),
                },
            )
            break
    await _set_create_job(job_id, {"message": "画像プロンプトをsemantic QA中"})
    failure = await _run_semantic_review_for_media_generation(job_id, run_dir=run_dir, stage="image_prompt")
    if failure:
        semantic_failures.append(failure)
        failed_semantic_stages.add("image_prompt")
    if semantic_failures:
        failed_stage_label = "+".join(sorted(failed_semantic_stages)) or "unknown"
        invalidated_by = f"semantic.{failed_stage_label}.failed"
        _invalidate_p600_supervisor_result(run_dir, invalidated_by=invalidated_by)
        failure_updates = {
            "runtime.stage": "semantic_review_failed_before_scene_generation",
            "review.image_prompt.request_freeze.status": "draft",
            "review.image_prompt.request_freeze.invalidated_by": invalidated_by,
            "review.image_prompt.request_freeze.invalidated_at": now_iso(),
            "orchestration.p600.supervisor.status": "invalidated",
            "orchestration.p600.supervisor.invalidated_by": invalidated_by,
            "slot.p650.status": "pending",
            "slot.p650.note": "semantic review must pass before the scene request revision can be handed to p660",
            "slot.p660.status": "pending",
            "slot.p660.note": "blocked before scene image generation by semantic review failure",
            "slot.p670.status": "pending",
            "slot.p670.note": "waiting for semantic QA before scene image generation",
            "slot.p680.status": "pending",
            "slot.p680.note": "frontend image review is not ready because semantic QA blocked scene generation",
            "review.image.status": "pending",
            "review.semantic.create_media_generated": "false",
            "review.semantic.create_scene_media_generated": "false",
            "review.semantic.create_failure_count": str(len(semantic_failures)),
            "review.semantic.create_failures": " | ".join(semantic_failures)[:2000],
            "image_generation.status": "not_started",
            "image_generation.started": "false",
            "image_generation.generated_count": "0",
            "image_generation.blocked_by": "semantic_review",
        }
        for stage in sorted(failed_semantic_stages):
            slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
            if slot:
                failure_updates[f"slot.{slot}.status"] = "failed"
                failure_updates[f"slot.{slot}.note"] = (
                    f"contextless semantic {stage} review failed; p660 is blocked"
                )
        append_state_snapshot(run_dir / "state.txt", failure_updates)
        raise RuntimeError(
            "semantic review failed before scene image generation: "
            + " | ".join(semantic_failures)
        )
    await _generate_scene_outputs_after_p650_preflight(
        job_id,
        run_id=run_id,
        run_dir=run_dir,
    )
    return asset_quality_passed


async def _run_image_prompt_semantic_review(job_id: str, *, run_dir: Path) -> None:
    await _run_semantic_review(job_id, run_dir=run_dir, stage="image_prompt")


def _invalidate_p600_supervisor_result(run_dir: Path, *, invalidated_by: str) -> None:
    result_path = run_dir / "logs/orchestration/p600.supervisor_result.json"
    if not result_path.exists():
        return
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(payload, dict) or payload.get("status") == "invalidated":
        return
    payload["previous_status"] = str(payload.get("status") or "unknown")
    payload["status"] = "invalidated"
    payload["invalidated_at"] = now_iso()
    payload["invalidated_by"] = invalidated_by
    _atomic_write_text(result_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


async def _run_semantic_review_for_media_generation(job_id: str, *, run_dir: Path, stage: str) -> str | None:
    try:
        await _run_semantic_review(job_id, run_dir=run_dir, stage=stage)
        return None
    except Exception as exc:
        if is_codex_transport_error(exc):
            transport_kind = classify_codex_transport_error(str(exc)) or "unknown"
            current_state = parse_state_file(run_dir / "state.txt")
            repair_status = str(current_state.get(f"review.semantic.{stage}.repair.status") or "")
            failure_phase = "semantic_producer_repair" if repair_status else "semantic_review"
            blocked_by = f"semantic.{stage}.{failure_phase}"
            invalidated_by = f"semantic.{stage}.transport.{transport_kind}"
            last_progress_at = str(
                current_state.get(f"review.semantic.{stage}.repair.pending.updated_at")
                or current_state.get(f"review.semantic.{stage}.watchdog.last_progress_at")
                or "unknown"
            )
            blocked_item_ids = (
                _localized_semantic_blocked_image_item_ids(run_dir, stage=stage)
                if stage in {"scene_detail", "cut_blueprint", "asset_plan", "image_prompt"}
                else set()
            )
            _invalidate_p600_supervisor_result(run_dir, invalidated_by=invalidated_by)
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    f"review.semantic.{stage}.transport.status": "failed",
                    f"review.semantic.{stage}.transport.error_kind": transport_kind,
                    f"review.semantic.{stage}.transport.error": str(exc)[:2000],
                    f"review.semantic.{stage}.loop.status": "blocked_transport",
                    "runtime.stage": "semantic_review_blocked_transport",
                    "runtime.app_server.transport.status": "failed",
                    "runtime.app_server.transport.error_kind": transport_kind,
                    "runtime.failure.stage": stage,
                    "runtime.failure.phase": failure_phase,
                    "runtime.failure.error_kind": transport_kind,
                    "runtime.failure.last_progress_at": last_progress_at,
                    "image_generation.status": "not_started",
                    "image_generation.started": "false",
                    "image_generation.generated_count": "0",
                    "image_generation.blocked_by": blocked_by,
                    "image_generation.block_reason": f"app_server_transport_{transport_kind}",
                    "orchestration.p600.supervisor.status": "invalidated",
                    "orchestration.p600.supervisor.invalidated_by": invalidated_by,
                    "slot.p660.status": "pending",
                    "slot.p660.note": f"blocked before image generation by {stage} transport failure",
                    "slot.p670.status": "pending",
                    "slot.p670.note": "waiting for semantic QA transport recovery before image generation",
                    "slot.p680.status": "pending",
                    "slot.p680.note": "frontend image review is not ready because semantic QA transport failed before image generation",
                    "review.image.status": "pending",
                },
            )
            if blocked_item_ids:
                blocked_ids = sorted(blocked_item_ids)
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        f"review.semantic.{stage}.partial_media_allowed": "false",
                        f"review.semantic.{stage}.blocked_image_items": ", ".join(blocked_ids),
                        f"review.semantic.{stage}.blocked_image_item_count": str(len(blocked_ids)),
                        f"review.semantic.{stage}.localization.status": "localized_to_image_items",
                        f"review.semantic.{stage}.localization.blocked_image_items": ", ".join(blocked_ids),
                        "runtime.stage": "semantic_review_transport_failed_before_scene_generation",
                    },
                )
                write_app_server_debug_log(
                    run_dir=run_dir,
                    operation="semantic_review",
                    status="transport_localized_but_scene_generation_blocked",
                    item_id=job_id,
                    request={"stage": stage},
                    response={
                        "transportErrorKind": transport_kind,
                        "blockedImageItems": blocked_ids,
                        "note": "semantic transport failure is localized, but p660 remains blocked until every semantic gate passes",
                    },
                    error=f"{type(exc).__name__}: {exc}",
                )
                return f"{stage}: transport {transport_kind}; skipped image generation for {', '.join(blocked_ids)}"
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    f"review.semantic.{stage}.localization.status": "not_localized",
                    f"review.semantic.{stage}.localization.reason": "transport failure did not map to scene image request items",
                },
            )
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="semantic_review",
                status="transport_blocked_before_image_generation",
                item_id=job_id,
                request={"stage": stage, "phase": failure_phase},
                response={
                    "errorKind": transport_kind,
                    "imageGenerationStatus": "not_started",
                    "imageGenerationStarted": False,
                    "generatedCount": 0,
                    "blockedBy": blocked_by,
                    "lastProgressAt": last_progress_at,
                    "p600SupervisorStatus": "invalidated",
                    "p600SupervisorInvalidatedBy": invalidated_by,
                },
                error=f"{type(exc).__name__}: {exc}",
            )
            slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
            if slot:
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        f"slot.{slot}.status": "failed",
                        f"slot.{slot}.note": f"contextless semantic {stage} review blocked by app-server transport",
                    },
                )
            raise RuntimeError(f"{stage} semantic review blocked by Codex app-server transport failure: {exc}") from exc
        message = f"{stage}: {type(exc).__name__}: {exc}"
        state_updates = semantic_state_updates(
            stage,
            status="failed",
            entry_count=None,
            error_count=1,
        )
        state_updates.update(
            {
                "runtime.stage": "semantic_review_failed_before_media_generation",
                "review.semantic.create_media_generated": "false",
                "review.semantic.create_blocking_stage": stage,
                "slot.p660.status": "pending",
                "slot.p660.note": f"blocked before image generation by {stage} semantic review failure",
                "slot.p670.status": "pending",
                "slot.p670.note": "waiting for semantic QA before image generation",
                "slot.p680.status": "pending",
                "slot.p680.note": "frontend image review is not ready because semantic QA failed before image generation",
                "review.image.status": "pending",
            }
        )
        semantic_failure_context = _semantic_review_failure_context(run_dir, stage)
        state_updates.update(_semantic_review_failure_state(run_dir, stage))
        blocked_item_ids = (
            _localized_semantic_blocked_image_item_ids(
                run_dir,
                stage=stage,
                items=load_request_items(run_dir, "scene"),
                failure_context=semantic_failure_context,
            )
            if stage in {"scene_detail", "cut_blueprint", "asset_plan", "image_prompt"}
            else set()
        )
        if blocked_item_ids:
            blocked_ids = sorted(blocked_item_ids)
            state_updates.update(
                {
                    f"review.semantic.{stage}.partial_media_allowed": "false",
                    f"review.semantic.{stage}.blocked_image_items": ", ".join(blocked_ids),
                    f"review.semantic.{stage}.blocked_image_item_count": str(len(blocked_ids)),
                    f"review.semantic.{stage}.localization.status": "localized_to_image_items",
                    f"review.semantic.{stage}.localization.blocked_image_items": ", ".join(blocked_ids),
                    "runtime.stage": "semantic_review_failed_before_scene_generation",
                    "slot.p660.status": "pending",
                    "slot.p660.note": f"all scene images are blocked until {stage} semantic review passes",
                    "slot.p670.status": "pending",
                    "slot.p670.note": "waiting for semantic QA before scene image generation",
                    "slot.p680.status": "pending",
                    "slot.p680.note": "frontend image review is not ready because semantic QA blocked scene generation",
                    "review.image.status": "pending",
                }
            )
            append_state_snapshot(run_dir / "state.txt", state_updates)
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="semantic_review",
                status="semantic_localized_but_scene_generation_blocked",
                item_id=job_id,
                request={"stage": stage},
                response={
                    "blockedImageItems": blocked_ids,
                    "semanticFailureContext": semantic_failure_context,
                    "note": "semantic failure is localized, but p660 remains blocked until every semantic gate passes",
                },
                error=message,
            )
            return f"{stage}: semantic QA failed; skipped image generation for {', '.join(blocked_ids)}"
        state_updates[f"review.semantic.{stage}.localization.status"] = "not_localized"
        state_updates[f"review.semantic.{stage}.localization.reason"] = "semantic failure did not map to scene image request items"
        slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
        if slot:
            state_updates[f"slot.{slot}.status"] = "failed"
            state_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} review failed; media generation blocked"
        state_updates[f"review.semantic.{stage}.last_error"] = str(exc)[:2000]
        append_state_snapshot(run_dir / "state.txt", state_updates)
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="semantic_review",
            status="failed_nonblocking_for_media_generation",
            item_id=job_id,
            request={"stage": stage},
            response={
                "failureContext": _codex_failure_context(exc),
                "semanticFailureContext": _semantic_review_failure_context(run_dir, stage),
            },
            error=message,
        )
        raise RuntimeError(f"{stage} semantic review failed before media generation: {exc}") from exc


SEMANTIC_REVIEW_SLOT_BY_STAGE = {
    "research": "p130",
    "story": "p230",
    "scene_set": "p410",
    "scene_detail": "p410",
    "cut_blueprint": "p420",
    "asset_plan": "p540",
    "image_prompt": "p640",
    "narration": "p720",
    "video_motion": "p820",
}


async def _run_semantic_review(
    job_id: str,
    *,
    run_dir: Path,
    stage: str,
    max_attempts: int | None = None,
    image_prompt_provider_ready: bool = True,
) -> None:
    attempts = max(1, max_attempts or semantic_review_max_attempts())
    if stage == "image_prompt":
        # The semantic pack must review the exact provider-ready snapshot.
        # Freeze is validation/state only; it must not mutate a reviewed source.
        image_prompt_request_revision = _prepare_image_prompt_request_revision_for_review(
            run_dir,
            provider_ready=image_prompt_provider_ready,
        )
    else:
        image_prompt_request_revision = ""
    reusable_result = _reusable_passed_semantic_review(run_dir, stage)
    if reusable_result is not None:
        _record_reused_semantic_review(run_dir, stage, reusable_result, max_attempts=attempts)
        if stage == "image_prompt" and image_prompt_provider_ready:
            _mark_image_prompt_request_freeze_done(run_dir)
        elif stage == "image_prompt":
            _mark_image_prompt_draft_reviewed(
                run_dir,
                request_revision=image_prompt_request_revision,
            )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="semantic_review",
            status="reused_passed_report",
            item_id=job_id,
            request={"stage": stage, "maxAttempts": attempts},
            response={"status": reusable_result.status, "entryCount": reusable_result.entry_count},
        )
        return
    last_result: SemanticReviewStatus | None = None
    for attempt in range(1, attempts + 1):
        append_state_snapshot(
            run_dir / "state.txt",
            semantic_loop_state_updates(stage, status="reviewing", attempt=attempt, max_attempts=attempts),
        )
        try:
            result = await _await_semantic_operation_with_progress_watchdog(
                _run_semantic_review_once(
                    job_id,
                    run_dir=run_dir,
                    stage=stage,
                    attempt=attempt,
                    max_attempts=attempts,
                    final_attempt=attempt >= attempts,
                ),
                run_dir=run_dir,
                stage=stage,
                operation="review",
                timeout_seconds=_semantic_review_no_progress_timeout_seconds(),
                fingerprint=lambda: _semantic_review_progress_fingerprint(run_dir, stage),
            )
        except asyncio.TimeoutError as exc:
            _record_semantic_review_hard_timeout(
                run_dir,
                stage,
                attempt=attempt,
                max_attempts=attempts,
                timeout_seconds=_semantic_review_no_progress_timeout_seconds(),
            )
            raise CodexAppServerTransportError(
                f"{stage} semantic review timed out after no observable progress"
            ) from exc
        last_result = result
        if result.passed:
            append_state_snapshot(
                run_dir / "state.txt",
                semantic_loop_state_updates(stage, status="passed", attempt=attempt, max_attempts=attempts, error_count=0),
            )
            if stage == "image_prompt" and image_prompt_provider_ready:
                _mark_image_prompt_request_freeze_done(run_dir)
            elif stage == "image_prompt":
                _mark_image_prompt_draft_reviewed(
                    run_dir,
                    request_revision=image_prompt_request_revision,
                )
            return
        if attempt >= attempts:
            failure_updates = semantic_loop_state_updates(
                stage,
                status="failed",
                attempt=attempt,
                max_attempts=attempts,
                error_count=len(result.errors),
            )
            failure_updates.update(_semantic_review_failure_state(run_dir, stage))
            if attempts <= 1:
                failure_updates.update(
                    {
                        f"review.semantic.{stage}.repair.active": "false",
                        f"review.semantic.{stage}.repair.skipped": "true",
                        f"review.semantic.{stage}.repair.skipped_reason": "max_attempts_1",
                    }
                )
                slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
                if slot:
                    failure_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} review failed without repair"
            append_state_snapshot(run_dir / "state.txt", failure_updates)
            error_text = f"{stage} semantic review failed after {attempts} attempt(s): " + "; ".join(result.errors)
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="semantic_review",
                status="failed_after_max_attempts",
                item_id=job_id,
                request={
                    "stage": stage,
                    "attempt": attempt,
                    "maxAttempts": attempts,
                },
                response=_semantic_review_failure_context(run_dir, stage),
                error=error_text,
            )
            raise RuntimeError(error_text)
        repair_source_fingerprint_before = _semantic_repair_source_artifact_fingerprint(run_dir, stage)
        repair_paths = semantic_repair_relpaths(stage, attempt)
        repair_report_path = run_dir / repair_paths["report"]
        repair_activity_relpath = _semantic_turn_activity_relpath(repair_paths["report"])
        try:
            await _await_semantic_operation_with_progress_watchdog(
                _run_semantic_review_producer_repair(
                    job_id,
                    run_dir=run_dir,
                    stage=stage,
                    round_number=attempt,
                    max_attempts=attempts,
                    errors=result.errors,
                ),
                run_dir=run_dir,
                stage=stage,
                operation="producer_repair",
                timeout_seconds=_semantic_repair_no_progress_timeout_seconds(),
                fingerprint=lambda: _semantic_repair_progress_fingerprint(run_dir, stage, attempt),
                pending_state=lambda pending_seconds: _semantic_repair_pending_state(
                    run_dir,
                    stage,
                    round_number=attempt,
                    timeout_seconds=_semantic_repair_no_progress_timeout_seconds(),
                    pending_duration_seconds=pending_seconds,
                ),
            )
        except asyncio.TimeoutError as exc:
            repair_source_fingerprint_after = _semantic_repair_source_artifact_fingerprint(run_dir, stage)
            changed_artifacts = _changed_semantic_repair_artifacts(repair_source_fingerprint_before, repair_source_fingerprint_after)
            if changed_artifacts:
                _record_semantic_repair_salvaged_after_source_change(
                    run_dir,
                    stage,
                    round_number=attempt,
                    max_attempts=attempts,
                    error_count=len(result.errors),
                    timeout_seconds=_semantic_repair_no_progress_timeout_seconds(),
                    changed_artifacts=changed_artifacts,
                    source_fingerprint_before=repair_source_fingerprint_before,
                    source_fingerprint_after=repair_source_fingerprint_after,
                )
                write_app_server_debug_log(
                    run_dir=run_dir,
                    operation="semantic_review_producer_repair",
                    status="completed_after_source_artifact_change_before_hard_timeout",
                    item_id=job_id,
                    request={
                        "stage": stage,
                        "round": attempt,
                        "maxAttempts": attempts,
                        "report": repair_paths["report"].as_posix(),
                        "activityMarker": repair_activity_relpath.as_posix(),
                        "sourceFingerprintBefore": _semantic_repair_fingerprint_summary(repair_source_fingerprint_before),
                    },
                    response={
                        "errorCount": len(result.errors),
                        "transportErrorKind": "timeout",
                        "changedArtifacts": changed_artifacts,
                        "sourceFingerprintAfter": _semantic_repair_fingerprint_summary(repair_source_fingerprint_after),
                        "reportStatus": _semantic_repair_report_status(repair_report_path),
                        "note": "producer repair changed source artifacts before the outer hard timeout; rerunning semantic review instead of failing transport",
                    },
                    error=f"TimeoutError: semantic producer repair no-progress timeout after {_semantic_repair_no_progress_timeout_seconds():.0f}s",
                )
                if stage == "image_prompt":
                    await _prepare_image_prompt_repair_revision_for_rereview(
                        run_dir,
                        provider_ready=image_prompt_provider_ready,
                    )
                    image_prompt_request_revision = _prepare_image_prompt_request_revision_for_review(
                        run_dir,
                        provider_ready=image_prompt_provider_ready,
                    )
                continue
            _record_semantic_repair_hard_timeout(
                run_dir,
                stage,
                round_number=attempt,
                max_attempts=attempts,
                error_count=len(result.errors),
                timeout_seconds=_semantic_repair_no_progress_timeout_seconds(),
                changed_artifacts=changed_artifacts,
                source_fingerprint_before=repair_source_fingerprint_before,
                source_fingerprint_after=repair_source_fingerprint_after,
            )
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="semantic_review_producer_repair",
                status="no_progress_timeout",
                item_id=job_id,
                request={
                    "stage": stage,
                    "round": attempt,
                    "maxAttempts": attempts,
                    "report": repair_paths["report"].as_posix(),
                    "activityMarker": repair_activity_relpath.as_posix(),
                    "sourceFingerprintBefore": _semantic_repair_fingerprint_summary(repair_source_fingerprint_before),
                },
                response={
                    "errorCount": len(result.errors),
                    "changedArtifacts": changed_artifacts,
                    "sourceFingerprintAfter": _semantic_repair_fingerprint_summary(repair_source_fingerprint_after),
                    "reportStatus": _semantic_repair_report_status(repair_report_path),
                    "noProgressTimeoutSeconds": _semantic_repair_no_progress_timeout_seconds(),
                },
                error=f"TimeoutError: semantic producer repair no-progress timeout after {_semantic_repair_no_progress_timeout_seconds():.0f}s",
            )
            raise CodexAppServerTransportError(
                f"{stage} semantic producer repair timed out after no observable progress"
            ) from exc
        if stage == "image_prompt":
            await _prepare_image_prompt_repair_revision_for_rereview(
                run_dir,
                provider_ready=image_prompt_provider_ready,
            )
            image_prompt_request_revision = _prepare_image_prompt_request_revision_for_review(
                run_dir,
                provider_ready=image_prompt_provider_ready,
            )
    if last_result is not None and not last_result.passed:
        raise RuntimeError(f"{stage} semantic review failed: " + "; ".join(last_result.errors))


def _reusable_passed_semantic_review(run_dir: Path, stage: str) -> SemanticReviewStatus | None:
    if os.environ.get("TOC_SEMANTIC_REVIEW_REUSE_PASSED", "1").strip().lower() in {"0", "false", "no"}:
        return None
    result = check_semantic_review(run_dir, stage)
    if not result.passed:
        return None
    if not _semantic_review_report_sources_are_current(run_dir, stage):
        return None
    return result


def _semantic_review_report_sources_are_current(run_dir: Path, stage: str) -> bool:
    relpaths = semantic_review_relpaths(stage)
    scope_path = run_dir / relpaths["scope"]
    report_path = run_dir / relpaths["report"]
    if not scope_path.exists() or not report_path.exists():
        return False
    try:
        scope = json.loads(scope_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    source_artifacts = scope.get("source_artifacts")
    if not isinstance(source_artifacts, list) or not source_artifacts:
        return False
    report_mtime_ns = report_path.stat().st_mtime_ns
    for raw_rel in source_artifacts:
        if not isinstance(raw_rel, str) or not raw_rel.strip():
            return False
        source_path = run_dir / raw_rel
        if not source_path.exists():
            return False
        if source_path.stat().st_mtime_ns > report_mtime_ns:
            return False
    return True


_SEMANTIC_REPAIR_HASH_LIMIT_BYTES = 2_000_000


def _semantic_repair_source_artifact_relpaths(run_dir: Path, stage: str) -> list[str]:
    relpaths = semantic_review_relpaths(stage)
    scope_path = run_dir / relpaths["scope"]
    source_artifacts: list[str] = []
    if scope_path.exists():
        try:
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            scope = {}
        raw_artifacts = scope.get("source_artifacts") if isinstance(scope, dict) else None
        if isinstance(raw_artifacts, list):
            source_artifacts = [item for item in raw_artifacts if isinstance(item, str) and item.strip()]
    if not source_artifacts:
        target = SEMANTIC_REVIEW_PRODUCER_TARGETS.get(stage, {})
        raw_artifacts = target.get("artifacts") if isinstance(target, dict) else None
        if isinstance(raw_artifacts, list):
            source_artifacts = [item for item in raw_artifacts if isinstance(item, str) and item.strip()]

    run_root = run_dir.resolve()
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in source_artifacts:
        value = raw.strip().replace("\\", "/")
        if not value:
            continue
        if any(char in value for char in "*?["):
            value_path = Path(value)
            if value_path.is_absolute() or ".." in value_path.parts:
                continue
            for candidate in sorted(run_dir.glob(value)):
                if not candidate.is_file():
                    continue
                try:
                    rel = candidate.resolve().relative_to(run_root).as_posix()
                except ValueError:
                    continue
                if rel not in seen:
                    seen.add(rel)
                    normalized.append(rel)
            continue
        try:
            target_path = resolve_run_relative(run_dir, value)
            rel = target_path.resolve().relative_to(run_root).as_posix()
        except (ValueError, RuntimeError):
            continue
        if rel not in seen:
            seen.add(rel)
            normalized.append(rel)
    return normalized


def _semantic_repair_artifact_signature(path: Path) -> str:
    if not path.exists():
        return "missing"
    try:
        stat = path.stat()
    except OSError as exc:
        return f"stat_error:{type(exc).__name__}"
    if not path.is_file():
        return f"not_file:{stat.st_size}:{stat.st_mtime_ns}"
    digest = ""
    if stat.st_size <= _SEMANTIC_REPAIR_HASH_LIMIT_BYTES:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            digest = f"read_error:{type(exc).__name__}"
    return f"file:{stat.st_size}:{stat.st_mtime_ns}:{digest}"


def _semantic_repair_source_artifact_fingerprint(run_dir: Path, stage: str) -> dict[str, str]:
    return {
        rel: _semantic_repair_artifact_signature(resolve_run_relative(run_dir, rel))
        for rel in _semantic_repair_source_artifact_relpaths(run_dir, stage)
    }


def _changed_semantic_repair_artifacts(before: dict[str, str], after: dict[str, str]) -> list[str]:
    return sorted(rel for rel in set(before) | set(after) if before.get(rel) != after.get(rel))


def _semantic_repair_fingerprint_summary(fingerprint: dict[str, str]) -> dict[str, Any]:
    return {
        "artifactCount": len(fingerprint),
        "artifacts": sorted(fingerprint),
        "hash": _json_hash(fingerprint),
    }


def _semantic_repair_report_status(report_path: Path) -> str:
    if not report_path.exists():
        return "missing"
    report_text = report_path.read_text(encoding="utf-8", errors="replace")
    return parse_judgment_report_status(report_text) or "pending"


def _semantic_repair_target_selectors(run_dir: Path, stage: str) -> list[str]:
    report_path = run_dir / semantic_review_relpaths(stage)["report"]
    if not report_path.exists():
        return []
    selectors: list[str] = []
    seen: set[str] = set()
    in_selector_list = False
    for raw in report_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if stripped.startswith("failed_selectors:") or stripped.startswith("blocked_entries:"):
            inline = stripped.split(":", 1)[1].strip()
            values = _semantic_report_inline_values(inline)
            in_selector_list = inline in {"", "[]", "[ ]"}
        elif in_selector_list and stripped.startswith("-"):
            values = _semantic_report_inline_values(stripped[1:].strip())
        else:
            if in_selector_list and stripped and not stripped.startswith("-"):
                in_selector_list = False
            values = []
        for value in values:
            if value not in seen:
                seen.add(value)
                selectors.append(value)
    return selectors[:50]


def _semantic_repair_pending_state(
    run_dir: Path,
    stage: str,
    *,
    round_number: int,
    timeout_seconds: float,
    pending_duration_seconds: float,
) -> dict[str, str]:
    relpaths = semantic_repair_relpaths(stage, round_number)
    report_path = run_dir / relpaths["report"]
    activity_relpath = _semantic_turn_activity_relpath(relpaths["report"])
    return {
        f"review.semantic.{stage}.repair.pending.status": "producer_report_pending",
        f"review.semantic.{stage}.repair.pending.duration_seconds": f"{pending_duration_seconds:.0f}",
        f"review.semantic.{stage}.repair.pending.no_progress_timeout_seconds": f"{timeout_seconds:.0f}",
        f"review.semantic.{stage}.repair.pending.report_status": _semantic_repair_report_status(report_path),
        f"review.semantic.{stage}.repair.pending.report": relpaths["report"].as_posix(),
        f"review.semantic.{stage}.repair.pending.activity_marker": activity_relpath.as_posix(),
        f"review.semantic.{stage}.repair.pending.updated_at": now_iso(),
    }


def _semantic_report_inline_values(raw: str) -> list[str]:
    value = raw.strip()
    if not value or value in {"[]", "[ ]"}:
        return []
    if value.startswith("[") and value.endswith("]"):
        candidates = value[1:-1].split(",")
    else:
        candidates = [value]
    return [cleaned for item in candidates if (cleaned := item.strip().strip(",").strip("`\"'")) and cleaned != "..."]


def _semantic_review_failure_context(run_dir: Path, stage: str) -> dict[str, Any]:
    relpaths = semantic_review_relpaths(stage)
    report_path = run_dir / relpaths["report"]
    scope_path = run_dir / relpaths["scope"]
    report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else ""
    entry_count: int | None = None
    source_artifacts: list[str] = []
    if scope_path.exists():
        try:
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            scope = {}
        if isinstance(scope, dict):
            raw_entry_count = scope.get("entry_count")
            if isinstance(raw_entry_count, int):
                entry_count = raw_entry_count
            raw_sources = scope.get("source_artifacts")
            if isinstance(raw_sources, list):
                source_artifacts = [str(item) for item in raw_sources if isinstance(item, str) and item.strip()]
    return {
        "stage": stage,
        "report": relpaths["report"].as_posix(),
        "scope": relpaths["scope"].as_posix(),
        "prompt": relpaths["prompt"].as_posix(),
        "collection": relpaths["collection"].as_posix(),
        "reportExists": report_path.exists(),
        "scopeExists": scope_path.exists(),
        "reportStatus": parse_judgment_report_status(report_text) or ("missing" if not report_text else "unknown"),
        "entryCount": entry_count,
        "failedSelectors": _semantic_report_list_values(report_text, "failed_selectors"),
        "blockedEntries": _semantic_report_list_values(report_text, "blocked_entries"),
        "reasonKeys": _semantic_report_list_values(report_text, "reason_keys"),
        "sourceArtifacts": source_artifacts,
    }


def _semantic_review_failure_state(run_dir: Path, stage: str) -> dict[str, str]:
    context = _semantic_review_failure_context(run_dir, stage)
    updates = {
        f"review.semantic.{stage}.failure.report": str(context["report"]),
        f"review.semantic.{stage}.failure.report_status": str(context["reportStatus"]),
        f"review.semantic.{stage}.failure.updated_at": now_iso(),
    }
    if context["entryCount"] is not None:
        updates[f"review.semantic.{stage}.failure.entry_count"] = str(context["entryCount"])
    for key, state_key in (
        ("failedSelectors", "failed_selectors"),
        ("blockedEntries", "blocked_entries"),
        ("reasonKeys", "reason_keys"),
    ):
        values = context.get(key)
        if isinstance(values, list):
            updates[f"review.semantic.{stage}.failure.{state_key}"] = ", ".join(str(item) for item in values)[:2000]
    return updates


def _record_reused_semantic_review(
    run_dir: Path,
    stage: str,
    result: SemanticReviewStatus,
    *,
    max_attempts: int,
) -> None:
    state_updates = review_status_to_state(stage, result)
    state_updates.update(
        semantic_loop_state_updates(stage, status="passed", attempt=0, max_attempts=max_attempts, error_count=0)
    )
    state_updates.update(
        {
            f"review.semantic.{stage}.reuse.status": "reused_passed_report",
            f"review.semantic.{stage}.transport.status": "passed",
            f"review.semantic.{stage}.repair.active": "false",
        }
    )
    slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
    if slot:
        state_updates[f"slot.{slot}.status"] = "done"
        state_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} review reused non-stale passed report"
    if stage == "image_prompt":
        state_updates.update(
            {
                "review.image_prompt.judgment.status": result.status or "failed",
                "review.image_prompt.judgment.error_count": str(len(result.errors)),
            }
        )
    append_state_snapshot(run_dir / "state.txt", state_updates)


def _semantic_review_no_progress_timeout_seconds() -> float:
    return float(semantic_review_timeout_seconds())


def _semantic_repair_no_progress_timeout_seconds() -> float:
    return float(semantic_repair_timeout_seconds())


def _semantic_review_once_hard_timeout_seconds() -> float:
    return _semantic_review_no_progress_timeout_seconds()


def _semantic_repair_once_hard_timeout_seconds() -> float:
    return _semantic_repair_no_progress_timeout_seconds()


def _semantic_review_progress_fingerprint(run_dir: Path, stage: str) -> dict[str, str]:
    relpaths = semantic_review_relpaths(stage)
    activity_relpath = _semantic_turn_activity_relpath(relpaths["report"])
    return {
        relpaths["report"].as_posix(): _semantic_repair_artifact_signature(run_dir / relpaths["report"]),
        activity_relpath.as_posix(): _semantic_repair_artifact_signature(run_dir / activity_relpath),
    }


def _semantic_repair_progress_fingerprint(run_dir: Path, stage: str, round_number: int) -> dict[str, str]:
    fingerprint = _semantic_repair_source_artifact_fingerprint(run_dir, stage)
    repair_paths = semantic_repair_relpaths(stage, round_number)
    activity_relpath = _semantic_turn_activity_relpath(repair_paths["report"])
    fingerprint[repair_paths["report"].as_posix()] = _semantic_repair_artifact_signature(run_dir / repair_paths["report"])
    fingerprint[activity_relpath.as_posix()] = _semantic_repair_artifact_signature(run_dir / activity_relpath)
    return fingerprint


def _semantic_turn_activity_relpath(report_relpath: Path) -> Path:
    return report_relpath.with_name(f"{report_relpath.name}.app_server_activity.json")


def _write_semantic_turn_activity_marker(report_path: Path, notification: dict[str, Any]) -> None:
    path = report_path.with_name(f"{report_path.name}.app_server_activity.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": now_iso(),
        "method": str(notification.get("method") or ""),
    }
    params = notification.get("params")
    if isinstance(params, dict):
        turn_id = params.get("turnId")
        if turn_id:
            payload["turn_id"] = str(turn_id)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def _await_semantic_operation_with_progress_watchdog(
    awaitable,
    *,
    run_dir: Path,
    stage: str,
    operation: str,
    timeout_seconds: float,
    fingerprint: Callable[[], dict[str, str]],
    pending_state: Callable[[float], dict[str, str]] | None = None,
):
    task = asyncio.create_task(awaitable)
    last_fingerprint = fingerprint()
    started_at = time.monotonic()
    append_state_snapshot(
        run_dir / "state.txt",
        {
            f"review.semantic.{stage}.watchdog.status": "monitoring",
            f"review.semantic.{stage}.watchdog.operation": operation,
            f"review.semantic.{stage}.watchdog.no_progress_timeout_seconds": f"{timeout_seconds:.0f}",
            f"review.semantic.{stage}.watchdog.started_at": now_iso(),
        },
    )
    # Synchronous audit writes can be slow on a nearly full filesystem.  The
    # watchdog starts after its own bookkeeping so that observer overhead is
    # never mistaken for producer inactivity.
    last_progress_at = time.monotonic()
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=SEMANTIC_TURN_ARTIFACT_POLL_SECONDS)
            if task in done:
                result = await task
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        f"review.semantic.{stage}.watchdog.status": "completed",
                        f"review.semantic.{stage}.watchdog.operation": operation,
                        f"review.semantic.{stage}.watchdog.completed_at": now_iso(),
                    },
                )
                return result
            current_fingerprint = fingerprint()
            if current_fingerprint != last_fingerprint:
                last_fingerprint = current_fingerprint
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        f"review.semantic.{stage}.watchdog.status": "progress_observed",
                        f"review.semantic.{stage}.watchdog.operation": operation,
                        f"review.semantic.{stage}.watchdog.last_progress_at": now_iso(),
                        f"review.semantic.{stage}.watchdog.fingerprint": _json_hash(current_fingerprint),
                    },
                )
                last_progress_at = time.monotonic()
            if time.monotonic() - last_progress_at >= timeout_seconds:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        f"review.semantic.{stage}.watchdog.status": "no_progress_timeout",
                        f"review.semantic.{stage}.watchdog.operation": operation,
                        f"review.semantic.{stage}.watchdog.last_progress_at": now_iso(),
                        f"review.semantic.{stage}.watchdog.no_progress_timeout_seconds": f"{timeout_seconds:.0f}",
                    },
                )
                raise asyncio.TimeoutError
            if pending_state is not None:
                bookkeeping_started_at = time.monotonic()
                append_state_snapshot(
                    run_dir / "state.txt",
                    pending_state(time.monotonic() - started_at),
                )
                last_progress_at += time.monotonic() - bookkeeping_started_at
    except Exception:
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        raise


def _record_semantic_review_hard_timeout(
    run_dir: Path,
    stage: str,
    *,
    attempt: int,
    max_attempts: int,
    timeout_seconds: float,
) -> None:
    updates = semantic_loop_state_updates(
        stage,
        status="blocked_transport",
        attempt=attempt,
        max_attempts=max_attempts,
        error_count=1,
    )
    updates.update(
        {
            f"review.semantic.{stage}.transport.status": "failed",
            f"review.semantic.{stage}.transport.error_kind": "timeout",
            f"review.semantic.{stage}.transport.error": f"semantic review no-progress timeout after {timeout_seconds:.0f}s",
            "runtime.stage": "app_server_transport_failed",
            "runtime.app_server.transport.status": "failed",
            "runtime.app_server.transport.error_kind": "timeout",
        }
    )
    slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
    if slot:
        updates[f"slot.{slot}.status"] = "failed"
        updates[f"slot.{slot}.note"] = f"contextless semantic {stage} review blocked by no-progress timeout"
    append_state_snapshot(run_dir / "state.txt", updates)


def _record_semantic_repair_hard_timeout(
    run_dir: Path,
    stage: str,
    *,
    round_number: int,
    max_attempts: int,
    error_count: int,
    timeout_seconds: float,
    changed_artifacts: list[str],
    source_fingerprint_before: dict[str, str],
    source_fingerprint_after: dict[str, str],
) -> None:
    relpaths = semantic_repair_relpaths(stage, round_number)
    report_path = run_dir / relpaths["report"]
    activity_relpath = _semantic_turn_activity_relpath(relpaths["report"])
    updates = semantic_loop_state_updates(
        stage,
        status="blocked_transport",
        attempt=round_number,
        max_attempts=max_attempts,
        error_count=error_count,
    )
    updates.update(
        semantic_repair_state_updates(
            stage,
            status="blocked_transport",
            round_number=round_number,
            max_attempts=max_attempts,
            error_count=error_count,
        )
    )
    updates.update(
        {
            f"review.semantic.{stage}.transport.status": "failed",
            f"review.semantic.{stage}.transport.error_kind": "timeout",
            f"review.semantic.{stage}.transport.error": f"semantic producer repair no-progress timeout after {timeout_seconds:.0f}s",
            f"review.semantic.{stage}.repair.transport.status": "failed",
            f"review.semantic.{stage}.repair.transport.error_kind": "timeout",
            f"review.semantic.{stage}.repair.changed_artifacts_detected": ", ".join(changed_artifacts)[:2000],
            f"review.semantic.{stage}.repair.source_fingerprint.before": _json_hash(source_fingerprint_before),
            f"review.semantic.{stage}.repair.source_fingerprint.after": _json_hash(source_fingerprint_after),
            f"review.semantic.{stage}.repair.source_fingerprint.before_count": str(len(source_fingerprint_before)),
            f"review.semantic.{stage}.repair.source_fingerprint.after_count": str(len(source_fingerprint_after)),
            f"review.semantic.{stage}.repair.report_status": _semantic_repair_report_status(report_path),
            f"review.semantic.{stage}.repair.report": relpaths["report"].as_posix(),
            f"review.semantic.{stage}.repair.activity_marker": activity_relpath.as_posix(),
            f"review.semantic.{stage}.repair.pending.status": "no_progress_timeout",
            f"review.semantic.{stage}.repair.pending.report_status": _semantic_repair_report_status(
                report_path
            ),
            f"review.semantic.{stage}.repair.pending.report": relpaths["report"].as_posix(),
            f"review.semantic.{stage}.repair.pending.activity_marker": activity_relpath.as_posix(),
            f"review.semantic.{stage}.repair.pending.no_progress_timeout_seconds": f"{timeout_seconds:.0f}",
            f"review.semantic.{stage}.repair.pending.updated_at": now_iso(),
            "runtime.stage": "app_server_transport_failed",
            "runtime.app_server.transport.status": "failed",
            "runtime.app_server.transport.error_kind": "timeout",
        }
    )
    slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
    if slot:
        updates[f"slot.{slot}.status"] = "failed"
        updates[f"slot.{slot}.note"] = f"contextless semantic {stage} producer repair blocked by no-progress timeout"
    append_state_snapshot(run_dir / "state.txt", updates)


def _record_semantic_repair_salvaged_after_source_change(
    run_dir: Path,
    stage: str,
    *,
    round_number: int,
    max_attempts: int,
    error_count: int,
    timeout_seconds: float,
    changed_artifacts: list[str],
    source_fingerprint_before: dict[str, str] | None = None,
    source_fingerprint_after: dict[str, str] | None = None,
) -> None:
    relpaths = semantic_repair_relpaths(stage, round_number)
    report_path = run_dir / relpaths["report"]
    activity_relpath = _semantic_turn_activity_relpath(relpaths["report"])
    updates = semantic_repair_state_updates(
        stage,
        status="done",
        round_number=round_number,
        max_attempts=max_attempts,
        error_count=error_count,
    )
    updates.update(
        {
            f"review.semantic.{stage}.repair.transport.status": "salvaged_after_source_artifact_change",
            f"review.semantic.{stage}.repair.transport.error_kind": "timeout",
            f"review.semantic.{stage}.repair.transport.error": f"semantic producer repair no-progress timeout after {timeout_seconds:.0f}s",
            f"review.semantic.{stage}.repair.changed_artifacts_detected": ", ".join(changed_artifacts)[:2000],
            f"review.semantic.{stage}.repair.report_status": _semantic_repair_report_status(report_path),
            f"review.semantic.{stage}.repair.report": relpaths["report"].as_posix(),
            f"review.semantic.{stage}.repair.activity_marker": activity_relpath.as_posix(),
            f"review.semantic.{stage}.repair.pending.status": "salvaged_after_source_artifact_change",
        }
    )
    if source_fingerprint_before is not None:
        updates[f"review.semantic.{stage}.repair.source_fingerprint.before"] = _json_hash(source_fingerprint_before)
        updates[f"review.semantic.{stage}.repair.source_fingerprint.before_count"] = str(len(source_fingerprint_before))
    if source_fingerprint_after is not None:
        updates[f"review.semantic.{stage}.repair.source_fingerprint.after"] = _json_hash(source_fingerprint_after)
        updates[f"review.semantic.{stage}.repair.source_fingerprint.after_count"] = str(len(source_fingerprint_after))
    slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
    if slot:
        updates[f"slot.{slot}.status"] = "in_progress"
        updates[f"slot.{slot}.note"] = f"contextless semantic {stage} repair changed artifacts before timeout; rereview pending"
    append_state_snapshot(run_dir / "state.txt", updates)


async def _run_semantic_review_once(
    job_id: str,
    *,
    run_dir: Path,
    stage: str,
    attempt: int,
    max_attempts: int,
    final_attempt: bool,
) -> SemanticReviewStatus:
    if stage == "scene_detail":
        return await _run_scene_detail_sharded_semantic_review_once(
            job_id,
            run_dir=run_dir,
            attempt=attempt,
            max_attempts=max_attempts,
            final_attempt=final_attempt,
        )
    if stage == "image_prompt":
        return await _run_image_prompt_sharded_semantic_review_once(
            job_id,
            run_dir=run_dir,
            attempt=attempt,
            max_attempts=max_attempts,
            final_attempt=final_attempt,
        )

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build-semantic-review-pack.py"),
            "--run-dir",
            str(run_dir),
            "--stage",
            stage,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    relpaths = semantic_review_relpaths(stage)
    prompt_path = run_dir / relpaths["prompt"]
    report_path = run_dir / relpaths["report"]
    prompt = _semantic_review_prompt_for_attempt(
        prompt_path.read_text(encoding="utf-8"),
        stage=stage,
        final_attempt=final_attempt,
    )
    prompt_path.write_text(prompt.rstrip() + "\n", encoding="utf-8")
    client = create_codex_app_server_client(cwd=ROOT)
    transcript: list[dict[str, Any]] = []
    try:
        thread_id = await asyncio.wait_for(
            client.start_thread(cwd=ROOT, approval_policy="never"),
            timeout=CODEX_APP_SERVER_START_TIMEOUT_SECONDS,
        )
        transcript, completed_from_report = await _run_turn_until_semantic_artifact_completed(
            client,
            thread_id=thread_id,
            text=prompt,
            cwd=ROOT,
            timeout_seconds=semantic_review_timeout_seconds(),
            report_path=report_path,
            is_completed=_semantic_review_report_completed,
        )
        if not _semantic_review_report_completed(report_path):
            report_from_agent = _semantic_report_text_from_transcript(transcript, stage)
            if report_from_agent is not None:
                report_path.write_text(report_from_agent, encoding="utf-8")
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        f"review.semantic.{stage}.report.source": "agent_message_transport_fallback",
                        f"review.semantic.{stage}.report.materialized_at": now_iso(),
                    },
                )
        if completed_from_report:
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="semantic_review",
                status="completed_after_report_before_turn_completed",
                item_id=job_id,
                request={
                    "stage": stage,
                    "attempt": attempt,
                    "maxAttempts": max_attempts,
                    "prompt": str(prompt_path.relative_to(run_dir)),
                    "report": str(report_path.relative_to(run_dir)),
                },
                response={
                    "note": "semantic report reached a terminal status before app-server turn/completed notification arrived",
                },
                transcript=transcript,
            )
    except Exception as exc:
        transport_kind = classify_codex_transport_error(str(exc))
        if is_codex_transport_error(exc) and _semantic_review_report_completed(report_path):
            transcript = getattr(exc, "transcript", transcript)
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="semantic_review",
                status="completed_after_transport_timeout",
                item_id=job_id,
                request={
                    "stage": stage,
                    "attempt": attempt,
                    "maxAttempts": max_attempts,
                    "prompt": str(prompt_path.relative_to(run_dir)),
                    "report": str(report_path.relative_to(run_dir)),
                },
                response={
                    "transportErrorKind": transport_kind or "unknown",
                    "note": "semantic report was completed before app-server turn completion notification timed out",
                },
                transcript=transcript if isinstance(transcript, list) else [],
            )
        else:
            if is_codex_transport_error(exc):
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        f"review.semantic.{stage}.transport.status": "failed",
                        f"review.semantic.{stage}.transport.error_kind": transport_kind or "unknown",
                        f"review.semantic.{stage}.transport.error": str(exc)[:2000],
                        f"review.semantic.{stage}.loop.status": "blocked_transport",
                    },
                )
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="semantic_review",
                status="app_server_failed",
                item_id=job_id,
                request={
                    "stage": stage,
                    "attempt": attempt,
                    "maxAttempts": max_attempts,
                    "prompt": str(prompt_path.relative_to(run_dir)),
                    "report": str(report_path.relative_to(run_dir)),
                },
                response={"failureContext": _codex_failure_context(exc, client=client)},
                transcript=getattr(exc, "transcript", []) if isinstance(getattr(exc, "transcript", None), list) else [],
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
    finally:
        await client.stop()
    if stage == "image_prompt" and report_path.exists():
        (run_dir / IMAGE_PROMPT_JUDGMENT_REPORT).write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
    result = check_semantic_review(run_dir, stage)
    state_updates = review_status_to_state(stage, result)
    slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
    if slot:
        if result.passed:
            state_updates[f"slot.{slot}.status"] = "done"
            state_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} review passed"
            state_updates[f"review.semantic.{stage}.transport.status"] = "passed"
            state_updates[f"review.semantic.{stage}.repair.active"] = "false"
        elif final_attempt:
            state_updates[f"slot.{slot}.status"] = "failed"
            state_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} review failed after repair loop"
        else:
            state_updates[f"slot.{slot}.status"] = "in_progress"
            state_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} review requested producer repair"
    if stage == "image_prompt":
        state_updates.update(
            {
                "review.image_prompt.judgment.status": result.status or "failed",
                "review.image_prompt.judgment.error_count": str(len(result.errors)),
            }
        )
    append_state_snapshot(run_dir / "state.txt", state_updates)
    if not result.passed:
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="semantic_review",
            status="failed" if final_attempt else "changes_requested",
            item_id=job_id,
            request={
                "stage": stage,
                "attempt": attempt,
                "maxAttempts": max_attempts,
                "prompt": str(prompt_path.relative_to(run_dir)),
                "report": str(report_path.relative_to(run_dir)),
            },
            transcript=transcript,
            error="; ".join(result.errors),
        )
        return result
    write_app_server_debug_log(
        run_dir=run_dir,
        operation="semantic_review",
        status="completed",
        item_id=job_id,
        request={
            "stage": stage,
            "attempt": attempt,
            "maxAttempts": max_attempts,
            "prompt": str(prompt_path.relative_to(run_dir)),
            "report": str(report_path.relative_to(run_dir)),
        },
        response={"status": result.status, "entryCount": result.entry_count},
        transcript=transcript,
    )
    return result


def _semantic_review_prompt_for_attempt(prompt: str, *, stage: str, final_attempt: bool) -> str:
    if not final_attempt:
        return prompt
    marker = "## Final Attempt Review Policy"
    if marker in prompt:
        return prompt
    if stage in {"research", "story"}:
        final_policy = (
            "A missing or contradictory internal baseline, timeline, character/conflict chain, unresolved internal reference, "
            "or unallocated required event is fatal because cut generation must not invent the foundation.\n"
            "Do not browse or judge external URLs, editions, translations, rights, or factual fidelity; those are outside this gate.\n"
            "Use `status: passed` only when the complete scope is internally sufficient for the next stage.\n"
        )
    else:
        final_policy = (
            "Use `status: passed` unless you find a fatal defect that would break the story meaning, source identity, reveal order, safety, or the next downstream stage.\n"
            "Treat non-fatal polish issues, minor wording weakness, and repairable prompt-strengthening suggestions as notes rather than blockers.\n"
        )
    return (
        prompt.rstrip()
        + "\n\n"
        + f"{marker}\n\n"
        + f"This is the final semantic review attempt for `{stage}`. If this report is `failed`, the project run will stop before downstream generation.\n"
        + final_policy
        + "If you pass with reservations, include the reservations in `notes` and keep `blocked_entries` and `failed_selectors` empty.\n"
    )


def _image_prompt_review_concurrency() -> int:
    raw = os.environ.get("TOC_IMAGE_PROMPT_REVIEW_CONCURRENCY", "").strip()
    if not raw:
        return scene_detail_review_concurrency()
    try:
        return max(1, int(raw))
    except ValueError:
        return scene_detail_review_concurrency()


def _image_prompt_transport_retry_attempts() -> int:
    raw = os.environ.get("TOC_IMAGE_PROMPT_TRANSPORT_RETRY_ATTEMPTS", "").strip()
    if not raw:
        return scene_detail_transport_retry_attempts()
    try:
        return max(1, int(raw))
    except ValueError:
        return scene_detail_transport_retry_attempts()


def _load_semantic_scope(scope_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(scope_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _scope_string_list(scope: dict[str, Any], key: str) -> list[str]:
    raw = scope.get(key)
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _validate_image_prompt_shard_scope(
    scope: dict[str, Any],
    collection_sections: dict[str, str],
) -> list[str]:
    """Validate exact canonical-selector to scene-shard coverage."""

    errors: list[str] = []
    entry_count = scope.get("entry_count")
    entry_ids = _scope_string_list(scope, "entry_ids")
    if not isinstance(entry_count, int):
        errors.append("image_prompt scope is missing integer entry_count")
    elif entry_count <= 0:
        errors.append("image_prompt scope has zero entries")
    if isinstance(entry_count, int) and entry_count != len(entry_ids):
        errors.append(
            f"image_prompt scope entry_count mismatch: declared {entry_count}, entry_ids has {len(entry_ids)}"
        )
    duplicate_entry_ids = sorted(entry_id for entry_id, count in Counter(entry_ids).items() if count > 1)
    if duplicate_entry_ids:
        errors.append(f"image_prompt scope has duplicate entry ids: {', '.join(duplicate_entry_ids)}")

    raw_shards = scope.get("shards")
    shards = raw_shards if isinstance(raw_shards, list) else []
    if not shards:
        errors.append("image_prompt scope has no scene shards")
    shard_ids: list[str] = []
    assigned: list[str] = []
    for index, raw_shard in enumerate(shards, start=1):
        if not isinstance(raw_shard, dict):
            errors.append(f"image_prompt shard {index} must be an object")
            continue
        shard_id = str(raw_shard.get("shard_id") or "").strip()
        if not shard_id:
            errors.append(f"image_prompt shard {index} is missing shard_id")
        else:
            shard_ids.append(shard_id)
        shard_entry_ids = _scope_string_list(raw_shard, "entry_ids")
        shard_entry_count = raw_shard.get("entry_count")
        if not shard_entry_ids:
            errors.append(f"image_prompt shard {shard_id or index} has zero entries")
        if not isinstance(shard_entry_count, int) or shard_entry_count != len(shard_entry_ids):
            errors.append(
                f"image_prompt shard {shard_id or index} entry_count mismatch: "
                f"declared {shard_entry_count!r}, entry_ids has {len(shard_entry_ids)}"
            )
        shard_duplicates = sorted(
            entry_id for entry_id, count in Counter(shard_entry_ids).items() if count > 1
        )
        if shard_duplicates:
            errors.append(
                f"image_prompt shard {shard_id or index} has duplicate entry ids: {', '.join(shard_duplicates)}"
            )
        assigned.extend(shard_entry_ids)
    duplicate_shard_ids = sorted(shard_id for shard_id, count in Counter(shard_ids).items() if count > 1)
    if duplicate_shard_ids:
        errors.append(f"image_prompt scope has duplicate shard ids: {', '.join(duplicate_shard_ids)}")

    expected_counter = Counter(entry_ids)
    assigned_counter = Counter(assigned)
    missing = sorted((expected_counter - assigned_counter).elements())
    unexpected = sorted((assigned_counter - expected_counter).elements())
    multiply_assigned = sorted(entry_id for entry_id, count in assigned_counter.items() if count > 1)
    if missing:
        errors.append(f"image_prompt shard coverage is missing entry ids: {', '.join(missing)}")
    if unexpected:
        errors.append(f"image_prompt shard coverage has unexpected entry ids: {', '.join(unexpected)}")
    if multiply_assigned:
        errors.append(f"image_prompt shard coverage assigns entry ids multiple times: {', '.join(multiply_assigned)}")

    missing_sections = [entry_id for entry_id in entry_ids if not collection_sections.get(entry_id, "").strip()]
    if missing_sections:
        errors.append(
            f"image_prompt collection section missing for entry ids: {', '.join(missing_sections)}"
        )
    unexpected_sections = sorted(set(collection_sections) - set(entry_ids))
    if unexpected_sections:
        errors.append(
            f"image_prompt collection has unexpected sections outside scope: {', '.join(unexpected_sections)}"
        )
    coverage = scope.get("coverage")
    if isinstance(coverage, dict) and str(coverage.get("status") or "").strip() == "invalid":
        raw_coverage_errors = coverage.get("errors")
        if isinstance(raw_coverage_errors, list):
            errors.extend(
                f"image_prompt pack coverage invalid: {str(error).strip()}"
                for error in raw_coverage_errors
                if str(error).strip()
            )
        else:
            errors.append("image_prompt pack coverage status is invalid")
    return _dedupe_preserve_order(errors)


def _image_prompt_scope_shards(scope: dict[str, Any]) -> list[dict[str, Any]]:
    raw_shards = scope.get("shards")
    if not isinstance(raw_shards, list):
        return []
    shards: list[dict[str, Any]] = []
    for raw_shard in raw_shards:
        if not isinstance(raw_shard, dict):
            continue
        shards.append(
            {
                "shard_id": str(raw_shard.get("shard_id") or "").strip(),
                "scene_id": str(raw_shard.get("scene_id") or "").strip(),
                "entry_ids": _scope_string_list(raw_shard, "entry_ids"),
            }
        )
    return shards


def _write_image_prompt_shard_aggregate_report(
    report_path: Path,
    *,
    status: str,
    reviewed_entries: list[str],
    blocked_entries: list[str],
    findings: list[str],
    reason_keys: list[str],
    notes: list[str],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_text = "\n".join(
        [
            "# Semantic Review Report: image_prompt",
            "",
            f"status: {status}",
            "reviewed_entries:",
            *[f"  - {entry}" for entry in reviewed_entries],
            "blocked_entries:",
            *[f"  - {entry}" for entry in blocked_entries],
            "findings:",
            *[f"  - {finding}" for finding in findings],
            "failed_selectors:",
            *[f"  - {entry}" for entry in blocked_entries],
            "reason_keys:",
            *[f"  - {key}" for key in reason_keys],
            "notes:",
            *[f"  - {note}" for note in notes],
            "",
        ]
    )
    report_path.write_text(report_text, encoding="utf-8")
    legacy_report_path = report_path.parents[3] / IMAGE_PROMPT_JUDGMENT_REPORT
    legacy_report_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_report_path.write_text(report_text, encoding="utf-8")


def _image_prompt_shard_failure_result(
    *,
    shard: dict[str, Any],
    status: str,
    errors: list[str],
    findings: list[str] | None = None,
    reason_keys: list[str] | None = None,
    transport_error_kind: str = "",
    transport_error: str = "",
) -> dict[str, Any]:
    result = {
        "shard_id": str(shard.get("shard_id") or ""),
        "scene_id": str(shard.get("scene_id") or ""),
        "entry_ids": list(shard.get("entry_ids") or []),
        "status": status,
        "errors": errors,
        "blocked_entries": list(shard.get("entry_ids") or []),
        "findings": list(findings or []),
        "reason_keys": list(reason_keys or ["image_prompt_shard_failed"]),
    }
    if transport_error_kind:
        result["transport_error_kind"] = transport_error_kind
    if transport_error:
        result["transport_error"] = transport_error
    return result


def _image_prompt_transport_failure_result(
    *,
    shard: dict[str, Any],
    exc: BaseException,
) -> dict[str, Any]:
    transport_kind = classify_codex_transport_error(str(exc)) or "unknown"
    reason_keys = ["image_prompt_shard_transport_failed"]
    if transport_kind == "timeout":
        reason_keys.append("image_prompt_shard_transport_timeout")
    message = f"{type(exc).__name__}: {exc}"
    return _image_prompt_shard_failure_result(
        shard=shard,
        status="transport_failed",
        errors=[f"app-server transport {transport_kind}: {message}"],
        findings=[f"image_prompt scene shard transport failed before a terminal report: {message}"],
        reason_keys=reason_keys,
        transport_error_kind=transport_kind,
        transport_error=message,
    )


def _semantic_report_list_values_with_duplicates(report_text: str, field: str) -> list[str]:
    values: list[str] = []
    lines = report_text.splitlines()
    in_field = False
    field_prefix = f"{field}:"
    label_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_ -]*:\s*")
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            if in_field:
                break
            continue
        if stripped.startswith(field_prefix):
            in_field = True
            inline = stripped.split(":", 1)[1].strip()
            values.extend(_semantic_report_inline_values(inline))
            if inline and inline not in {"[]", "[ ]"}:
                in_field = False
            continue
        if not in_field:
            continue
        if label_re.match(stripped):
            break
        value = _semantic_report_scalar(stripped[1:].strip() if stripped.startswith("-") else stripped)
        if value:
            values.append(value)
    return values


def _image_prompt_reviewed_entry_coverage_errors(
    expected_entry_ids: list[str],
    reviewed_entry_ids: list[str],
) -> list[str]:
    expected = Counter(expected_entry_ids)
    reviewed = Counter(reviewed_entry_ids)
    errors: list[str] = []
    missing = sorted((expected - reviewed).elements())
    unexpected = sorted((reviewed - expected).elements())
    duplicates = sorted(entry_id for entry_id, count in reviewed.items() if count > 1)
    if missing:
        errors.append(f"reviewed_entries missing selectors: {', '.join(missing)}")
    if unexpected:
        errors.append(f"reviewed_entries has unexpected selectors: {', '.join(unexpected)}")
    if duplicates:
        errors.append(f"reviewed_entries has duplicate selectors: {', '.join(duplicates)}")
    return errors


async def _run_image_prompt_sharded_semantic_review_once(
    job_id: str,
    *,
    run_dir: Path,
    attempt: int,
    max_attempts: int,
    final_attempt: bool,
) -> SemanticReviewStatus:
    stage = "image_prompt"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build-semantic-review-pack.py"),
            "--run-dir",
            str(run_dir),
            "--stage",
            stage,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    relpaths = semantic_review_relpaths(stage)
    collection_path = run_dir / relpaths["collection"]
    scope_path = run_dir / relpaths["scope"]
    report_path = run_dir / relpaths["report"]
    shard_dir = run_dir / "logs" / "review" / "semantic" / "image_prompt_shards" / f"attempt_{attempt:02d}"
    concurrency = _image_prompt_review_concurrency()
    transport_retry_attempts = _image_prompt_transport_retry_attempts()
    scope = _load_semantic_scope(scope_path)
    collection_text = collection_path.read_text(encoding="utf-8", errors="replace") if collection_path.exists() else ""
    sections = _semantic_collection_sections_by_entry(collection_text)
    validation_errors = _validate_image_prompt_shard_scope(scope, sections)
    entry_ids = _scope_string_list(scope, "entry_ids")
    shards = _image_prompt_scope_shards(scope)
    if validation_errors:
        blocked_entries = entry_ids or ["image_prompt"]
        _write_image_prompt_shard_aggregate_report(
            report_path,
            status="failed",
            reviewed_entries=[],
            blocked_entries=blocked_entries,
            findings=validation_errors,
            reason_keys=["semantic_review_selector_coverage_invalid"],
            notes=["image_prompt per-scene shard review did not start"],
        )
        result = check_image_prompt_judgment(run_dir)
        state_updates = review_status_to_state(stage, result)
        state_updates.update(
            {
                "review.semantic.image_prompt.shards.status": "failed",
                "review.semantic.image_prompt.shards.count": str(len(shards)),
                "review.semantic.image_prompt.shards.concurrency": str(concurrency),
                "review.semantic.image_prompt.shards.failed_count": str(max(1, len(shards))),
                "review.semantic.image_prompt.shards.attempt": str(attempt),
                "review.semantic.image_prompt.shards.dir": shard_dir.relative_to(run_dir).as_posix(),
                "review.semantic.image_prompt.shards.coverage.status": "invalid",
                "review.semantic.image_prompt.shards.coverage.errors": " | ".join(validation_errors)[:2000],
                "review.semantic.image_prompt.shards.updated_at": now_iso(),
            }
        )
        slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
        if slot:
            state_updates[f"slot.{slot}.status"] = "failed" if final_attempt else "in_progress"
            state_updates[f"slot.{slot}.note"] = "contextless image_prompt shard selector coverage is invalid"
        append_state_snapshot(run_dir / "state.txt", state_updates)
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="semantic_review",
            status="failed" if final_attempt else "changes_requested",
            item_id=job_id,
            request={
                "stage": stage,
                "mode": "per_scene_shards",
                "attempt": attempt,
                "maxAttempts": max_attempts,
                "shardCount": len(shards),
            },
            response={
                "status": result.status,
                "entryCount": result.entry_count,
                "coverageErrors": validation_errors,
            },
            error="; ".join(result.errors) if result.errors else None,
        )
        return result

    append_state_snapshot(
        run_dir / "state.txt",
        {
            "review.semantic.image_prompt.shards.status": "reviewing",
            "review.semantic.image_prompt.shards.count": str(len(shards)),
            "review.semantic.image_prompt.shards.concurrency": str(concurrency),
            "review.semantic.image_prompt.shards.attempt": str(attempt),
            "review.semantic.image_prompt.shards.dir": shard_dir.relative_to(run_dir).as_posix(),
            "review.semantic.image_prompt.shards.coverage.status": "valid",
            "review.semantic.image_prompt.shards.updated_at": now_iso(),
        },
    )
    semaphore = asyncio.Semaphore(concurrency)

    async def run_shards(selected: list[dict[str, Any]], transport_attempt: int) -> list[dict[str, Any]]:
        tasks = [
            asyncio.create_task(
                _run_image_prompt_scene_shard_review(
                    job_id,
                    run_dir=run_dir,
                    shard_dir=shard_dir,
                    shard=shard,
                    shard_index=shards.index(shard) + 1,
                    total_shards=len(shards),
                    collection_sections=sections,
                    canonical_scope_path=scope_path,
                    canonical_report_path=report_path,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    final_attempt=final_attempt,
                    semaphore=semaphore,
                    transport_attempt=transport_attempt,
                    transport_max_attempts=transport_retry_attempts,
                )
            )
            for shard in selected
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        results: list[dict[str, Any]] = []
        for shard, raw_result in zip(selected, raw_results):
            if isinstance(raw_result, BaseException):
                if is_codex_transport_error(raw_result):
                    results.append(_image_prompt_transport_failure_result(shard=shard, exc=raw_result))
                    continue
                raise raw_result
            results.append(raw_result)
        return results

    shard_results = await run_shards(shards, 1)
    for transport_attempt in range(2, transport_retry_attempts + 1):
        failed_ids = {
            str(result_item.get("shard_id") or "")
            for result_item in shard_results
            if str(result_item.get("status") or "") == "transport_failed"
        }
        if not failed_ids:
            break
        retry_shards = [shard for shard in shards if str(shard.get("shard_id") or "") in failed_ids]
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "review.semantic.image_prompt.shards.transport.status": "retrying",
                "review.semantic.image_prompt.shards.transport.attempt": str(transport_attempt),
                "review.semantic.image_prompt.shards.transport.max_attempts": str(transport_retry_attempts),
                "review.semantic.image_prompt.shards.transport.retry_entries": ", ".join(sorted(failed_ids)),
                "review.semantic.image_prompt.shards.updated_at": now_iso(),
            },
        )
        retry_results = await run_shards(retry_shards, transport_attempt)
        replacement_by_id = {str(item.get("shard_id") or ""): item for item in retry_results}
        shard_results = [replacement_by_id.get(str(item.get("shard_id") or ""), item) for item in shard_results]
        for shard_id, replacement in replacement_by_id.items():
            label = _safe_scene_detail_shard_label(shard_id)
            status = "failed" if str(replacement.get("status") or "") == "transport_failed" else "recovered"
            updates = {
                f"review.semantic.image_prompt.shards.{label}.transport.status": status,
                f"review.semantic.image_prompt.shards.{label}.transport.retry_count": str(transport_attempt - 1),
            }
            if status == "failed":
                updates[f"review.semantic.image_prompt.shards.{label}.transport.error_kind"] = str(
                    replacement.get("transport_error_kind") or "unknown"
                )
                updates[f"review.semantic.image_prompt.shards.{label}.transport.error"] = str(
                    replacement.get("transport_error") or ""
                )[:2000]
            append_state_snapshot(run_dir / "state.txt", updates)

    blocked_entries = _dedupe_preserve_order(
        entry
        for result_item in shard_results
        if str(result_item.get("status") or "") != "passed"
        for entry in (result_item.get("blocked_entries") or result_item.get("entry_ids") or [])
    )
    findings: list[str] = []
    reason_keys: list[str] = []
    for result_item in shard_results:
        shard_label = _safe_scene_detail_shard_label(str(result_item.get("shard_id") or "unknown"))
        shard_status = str(result_item.get("status") or "missing")
        append_state_snapshot(
            run_dir / "state.txt",
            {
                f"review.semantic.image_prompt.shards.{shard_label}.status": shard_status,
                f"review.semantic.image_prompt.shards.{shard_label}.entry_ids": ", ".join(
                    str(item) for item in result_item.get("entry_ids") or []
                )[:2000],
                f"review.semantic.image_prompt.shards.{shard_label}.blocked_entries": ", ".join(
                    str(item) for item in result_item.get("blocked_entries") or []
                )[:2000],
                f"review.semantic.image_prompt.shards.{shard_label}.reason_keys": ", ".join(
                    str(item) for item in result_item.get("reason_keys") or []
                )[:2000],
                f"review.semantic.image_prompt.shards.{shard_label}.updated_at": now_iso(),
            },
        )
        if str(result_item.get("status") or "") == "passed":
            continue
        shard_id = str(result_item.get("shard_id") or "unknown")
        findings.extend(f"{shard_id}: {error}" for error in result_item.get("errors") or [])
        findings.extend(f"{shard_id}: {finding}" for finding in result_item.get("findings") or [])
        reason_keys.extend(str(key) for key in result_item.get("reason_keys") or [])
    deterministic_errors = _deterministic_image_prompt_hard_gate_errors(run_dir)
    if deterministic_errors:
        deterministic_details = _deterministic_image_prompt_hard_findings(run_dir)
        canonical_entry_tokens = [
            _canonical_deterministic_image_prompt_selector(entry_id)
            for entry_id in entry_ids
        ]
        canonical_entry_tokens_are_unique = (
            len(set(canonical_entry_tokens)) == len(canonical_entry_tokens)
        )
        canonical_entry_by_token = {
            token: entry_id
            for token, entry_id in zip(canonical_entry_tokens, entry_ids)
        }
        detailed_blocked_entries = _dedupe_preserve_order(
            canonical_entry_by_token[
                _canonical_deterministic_image_prompt_selector(detail["selector"])
            ]
            for detail in deterministic_details
            if _canonical_deterministic_image_prompt_selector(detail["selector"])
            in canonical_entry_by_token
        )
        # Stale/malformed/empty-scope reports do not provide trustworthy
        # selector detail, so retain the safe run-wide fallback for those
        # failures.  A current report with concrete findings blocks only the
        # exact canonical entries named by the deterministic reviewer.
        deterministic_details_are_complete = (
            canonical_entry_tokens_are_unique
            and _deterministic_image_prompt_hard_finding_details_are_complete(
                run_dir,
                deterministic_details,
                entry_ids,
            )
        )
        blocked_entries = _dedupe_preserve_order(
            [
                *blocked_entries,
                *(
                    detailed_blocked_entries
                    if deterministic_details_are_complete
                    else entry_ids
                ),
            ]
        )
        if deterministic_details:
            for detail in deterministic_details:
                canonical_selector = canonical_entry_by_token.get(
                    _canonical_deterministic_image_prompt_selector(detail["selector"]),
                    detail["selector"],
                ) if canonical_entry_tokens_are_unique else detail["selector"]
                findings.append(
                    "deterministic_story_review: "
                    f"{canonical_selector} [{detail['code']}]: {detail['message']}"
                )
                reason_keys.append(detail["code"])
        findings.extend(
            f"deterministic_story_review: {error}" for error in deterministic_errors
        )
        reason_keys.append("deterministic_image_prompt_story_review_failed")
    if blocked_entries and not reason_keys:
        reason_keys.append("image_prompt_shard_failed")
    transport_failures = [
        result_item
        for result_item in shard_results
        if str(result_item.get("status") or "") == "transport_failed"
    ]
    for result_item in transport_failures:
        label = _safe_scene_detail_shard_label(str(result_item.get("shard_id") or "unknown"))
        append_state_snapshot(
            run_dir / "state.txt",
            {
                f"review.semantic.image_prompt.shards.{label}.transport.status": "failed",
                f"review.semantic.image_prompt.shards.{label}.transport.error_kind": str(
                    result_item.get("transport_error_kind") or "unknown"
                ),
                f"review.semantic.image_prompt.shards.{label}.transport.error": str(
                    result_item.get("transport_error") or ""
                )[:2000],
            },
        )

    notes = [
        f"image_prompt reviewed as {len(shard_results)} per-scene shard(s)",
        f"exact selector coverage: {len(entry_ids)} of {len(entry_ids)} canonical entries scheduled",
        f"bounded concurrency: {concurrency}",
        f"transport retry attempts: {transport_retry_attempts}",
    ]
    _write_image_prompt_shard_aggregate_report(
        report_path,
        status="failed" if blocked_entries else "passed",
        reviewed_entries=entry_ids,
        blocked_entries=blocked_entries,
        findings=findings,
        reason_keys=sorted(set(reason_keys)),
        notes=notes,
    )
    result = check_image_prompt_judgment(run_dir)
    state_updates = review_status_to_state(stage, result)
    state_updates.update(
        {
            "review.semantic.image_prompt.shards.status": "passed" if result.passed else "failed",
            "review.semantic.image_prompt.shards.failed_count": str(
                sum(1 for item in shard_results if str(item.get("status") or "") != "passed")
            ),
            "review.semantic.image_prompt.shards.coverage.status": "valid" if not blocked_entries else "failed",
            "review.semantic.image_prompt.shards.updated_at": now_iso(),
        }
    )
    slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
    if slot:
        if result.passed:
            state_updates[f"slot.{slot}.status"] = "done"
            state_updates[f"slot.{slot}.note"] = "contextless semantic image_prompt per-scene shard review passed"
            state_updates["review.semantic.image_prompt.transport.status"] = "passed"
            state_updates["review.semantic.image_prompt.repair.active"] = "false"
        elif final_attempt:
            state_updates[f"slot.{slot}.status"] = "failed"
            state_updates[f"slot.{slot}.note"] = "contextless semantic image_prompt per-scene shard review failed"
        else:
            state_updates[f"slot.{slot}.status"] = "in_progress"
            state_updates[f"slot.{slot}.note"] = "contextless semantic image_prompt shard review requested producer repair"
    append_state_snapshot(run_dir / "state.txt", state_updates)
    write_app_server_debug_log(
        run_dir=run_dir,
        operation="semantic_review",
        status="completed" if result.passed else ("failed" if final_attempt else "changes_requested"),
        item_id=job_id,
        request={
            "stage": stage,
            "attempt": attempt,
            "maxAttempts": max_attempts,
            "mode": "per_scene_shards",
            "concurrency": concurrency,
            "transportRetryAttempts": transport_retry_attempts,
            "shardCount": len(shards),
            "entryCount": len(entry_ids),
            "report": str(report_path.relative_to(run_dir)),
        },
        response={
            "status": result.status,
            "entryCount": result.entry_count,
            "failedShardCount": sum(
                1 for item in shard_results if str(item.get("status") or "") != "passed"
            ),
            "blockedEntries": blocked_entries,
            "transportFailedShardCount": len(transport_failures),
        },
        error="; ".join(result.errors) if result.errors else None,
    )
    if transport_failures:
        failed_shards = ", ".join(str(item.get("shard_id") or "unknown") for item in transport_failures)
        raise CodexAppServerTransportError(
            f"image_prompt scene shard transport failed after {transport_retry_attempts} attempt(s): {failed_shards}"
        )
    return result


def _write_image_prompt_scene_shard_artifacts(
    *,
    run_dir: Path,
    shard: dict[str, Any],
    shard_index: int,
    total_shards: int,
    collection_sections: dict[str, str],
    collection_path: Path,
    scope_path: Path,
    prompt_path: Path,
    report_path: Path,
    canonical_scope_path: Path,
    canonical_report_path: Path,
) -> None:
    shard_id = str(shard.get("shard_id") or "")
    scene_id = str(shard.get("scene_id") or "")
    entry_ids = [str(item) for item in shard.get("entry_ids") or []]
    collection_path.parent.mkdir(parents=True, exist_ok=True)
    sections = [collection_sections[entry_id].strip() for entry_id in entry_ids]
    collection_path.write_text(
        "\n".join(
            [
                "# Semantic Review Collection: image_prompt scene shard",
                "",
                f"Shard: `{shard_id}`",
                f"Scene: `{scene_id}`",
                f"Shard index: `{shard_index}` of `{total_shards}`",
                f"Entry count: `{len(entry_ids)}`",
                "",
                *sections,
                "",
            ]
        ),
        encoding="utf-8",
    )
    source_artifacts = _semantic_scope_source_artifacts(canonical_scope_path)
    scope_payload = {
        "stage": "image_prompt",
        "run_dir": str(run_dir.resolve()),
        "entry_count": len(entry_ids),
        "entry_ids": entry_ids,
        "review_scope": "single_scene_image_prompt_shard",
        "shard_id": shard_id,
        "scene_id": scene_id,
        "canonical_scope": str(canonical_scope_path.relative_to(run_dir)),
        "canonical_report": str(canonical_report_path.relative_to(run_dir)),
        "source_artifacts": source_artifacts,
        "artifacts": {
            "collection": str(collection_path.relative_to(run_dir)),
            "scope": str(scope_path.relative_to(run_dir)),
            "prompt": str(prompt_path.relative_to(run_dir)),
            "report": str(report_path.relative_to(run_dir)),
        },
        "generated_at": now_iso(),
    }
    scope_path.write_text(json.dumps(scope_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source_lines = [f"- `{(run_dir / rel).resolve()}`" for rel in source_artifacts]
    prompt_path.write_text(
        "\n".join(
            [
                "You are a contextless semantic review agent for one ToC `image_prompt` scene shard.",
                "",
                "Do semantic judgment only. Do not edit source artifacts and do not repair outputs.",
                f"Review only image_prompt scene shard `{shard_id}`.",
                "Expected reviewed_entries exactly once: " + json.dumps(entry_ids, ensure_ascii=False),
                "Do not report selectors from any other scene.",
                "",
                "Read these artifacts in order:",
                f"1. `{scope_path}`",
                f"2. `{collection_path}`",
                f"3. `{report_path}`",
                "",
                "Use these source artifacts as cross-check context when present:",
                *(source_lines or ["- `(none discovered)`"]),
                "",
                f"Write the final report to `{report_path}` and replace the pending template.",
                "",
                "Review every cut entry and the scene_composite entry together as one scene-local gate.",
                "Judge api_prompt_payload.prompt only as the provider prompt; design/debug fields are review evidence and must not be required verbatim in the provider prompt.",
                "Do not map upstream keys one-to-one into the provider prompt. For each cut explicitly judge include / omit / add / replace: keep only cut-local drawable facts, omit future motion/internal metadata/unneeded references, add visible behavior or period detail needed for imageability, and replace abstract or contradictory wording without changing the story event.",
                "Require only drawable information needed by each cut, correct subject/reference/location dependencies, one first-frame moment, reveal and temporal boundaries, and meaningful visual differences across cuts.",
                "Fail if a positive must-show/current-state fact is also forbidden by not_yet/constraints, if internal field names or scaffold prose leak into the provider prompt, required drawable evidence is absent, references are semantically wrong, or the cuts fail to visualize the scene obligations.",
                "When story_time is non-empty, require period-consistent clothing, hair, architecture, everyday objects, materials, and technology; reject missing grounding or mixed-era details.",
                "Require dependencies/references for visibly important characters, objects, and locations, but do not pull offscreen, merely mentioned, future, or scene-wide subjects into every cut.",
                "Reject production residue such as 画面上の状態差として確定する, 次区間へ渡す, 後続場面へ観客を運ぶ, 視覚証拠:, malformed/truncated prose, and unjustified exact or near-duplicate prompts across distinct cuts.",
                "Do not require every optional prompt fragment in every cut. Omitted conditional fragments are correct when their drawable dependency is absent.",
                "Do not fail solely because generated image/video/audio files do not exist yet.",
                "",
                "Report format:",
                "status: passed|failed",
                "reviewed_entries: [...]",
                "blocked_entries: [...]",
                "findings: [...]",
                "failed_selectors: [...]",
                "reason_keys: [semantic_subject_mismatch|semantic_location_mismatch|semantic_object_mismatch|semantic_reference_mismatch|semantic_timeline_mismatch|semantic_reveal_order_mismatch|semantic_output_mismatch|image_prompt_temporal_polarity_conflict|image_prompt_period_mismatch|api_prompt_design_meta_leak|scene_cut_coverage_insufficient|scene_cut_prompt_too_similar|scene_meaning_not_visualized_across_cuts|cut_prompt_requires_reinforcement|api_prompt_internal_field_leak|api_prompt_drawable_dependency_missing|...]",
                "notes: [...]",
                "",
                f"Run dir: `{run_dir.resolve()}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    report_path.write_text(
        "\n".join(
            [
                "# Semantic Review Report: image_prompt scene shard",
                "",
                "status: pending",
                "reviewed_entries: []",
                "blocked_entries: []",
                "findings: []",
                "failed_selectors: []",
                "reason_keys: []",
                "notes: []",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _touch_image_prompt_canonical_progress(
    canonical_report_path: Path,
    *,
    message: str,
) -> None:
    canonical_report_path.parent.mkdir(parents=True, exist_ok=True)
    with _scene_detail_canonical_progress_lock:
        canonical_report_path.write_text(
            "\n".join(
                [
                    "# Semantic Review Report: image_prompt",
                    "",
                    "status: pending",
                    "reviewed_entries: []",
                    "blocked_entries: []",
                    "findings: []",
                    "failed_selectors: []",
                    "reason_keys: []",
                    f"notes: [{json.dumps(message, ensure_ascii=False)}]",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def _write_image_prompt_shard_activity(
    *,
    report_path: Path,
    canonical_report_path: Path,
    notification: dict[str, Any],
) -> None:
    _write_semantic_turn_activity_marker(report_path, notification)
    with _scene_detail_canonical_progress_lock:
        _write_semantic_turn_activity_marker(canonical_report_path, notification)


async def _run_image_prompt_scene_shard_review(
    job_id: str,
    *,
    run_dir: Path,
    shard_dir: Path,
    shard: dict[str, Any],
    shard_index: int,
    total_shards: int,
    collection_sections: dict[str, str],
    canonical_scope_path: Path,
    canonical_report_path: Path,
    attempt: int,
    max_attempts: int,
    final_attempt: bool,
    semaphore: asyncio.Semaphore,
    transport_attempt: int,
    transport_max_attempts: int,
) -> dict[str, Any]:
    async with semaphore:
        shard_id = str(shard.get("shard_id") or "")
        entry_ids = [str(item) for item in shard.get("entry_ids") or []]
        shard_label = _safe_scene_detail_shard_label(shard_id)
        base = shard_dir / f"{shard_index:03d}_{shard_label}"
        collection_path = base.with_suffix(".collection.md")
        scope_path = base.with_suffix(".scope.json")
        prompt_path = base.with_suffix(".prompt.md")
        report_path = base.with_suffix(".report.md")
        _write_image_prompt_scene_shard_artifacts(
            run_dir=run_dir,
            shard=shard,
            shard_index=shard_index,
            total_shards=total_shards,
            collection_sections=collection_sections,
            collection_path=collection_path,
            scope_path=scope_path,
            prompt_path=prompt_path,
            report_path=report_path,
            canonical_scope_path=canonical_scope_path,
            canonical_report_path=canonical_report_path,
        )
        _touch_image_prompt_canonical_progress(
            canonical_report_path,
            message=f"image_prompt shard {shard_index}/{total_shards} started: {shard_id}",
        )
        client = create_codex_app_server_client(cwd=ROOT)
        transcript: list[dict[str, Any]] = []
        try:
            thread_id = await asyncio.wait_for(
                client.start_thread(cwd=ROOT, approval_policy="never"),
                timeout=CODEX_APP_SERVER_START_TIMEOUT_SECONDS,
            )
            prompt = _semantic_review_prompt_for_attempt(
                prompt_path.read_text(encoding="utf-8"),
                stage="image_prompt",
                final_attempt=final_attempt,
            )
            prompt_path.write_text(prompt.rstrip() + "\n", encoding="utf-8")
            transcript, completed_from_report = await _run_turn_until_semantic_artifact_completed(
                client,
                thread_id=thread_id,
                text=prompt,
                cwd=ROOT,
                timeout_seconds=semantic_review_timeout_seconds(),
                report_path=report_path,
                is_completed=_semantic_review_report_completed,
                progress_callback=lambda notification: _write_image_prompt_shard_activity(
                    report_path=report_path,
                    canonical_report_path=canonical_report_path,
                    notification=notification,
                ),
            )
            if completed_from_report:
                write_app_server_debug_log(
                    run_dir=run_dir,
                    operation="semantic_review",
                    status="completed_after_report_before_turn_completed",
                    item_id=job_id,
                    request={
                        "stage": "image_prompt",
                        "mode": "per_scene_shard",
                        "shardId": shard_id,
                        "entryIds": entry_ids,
                        "attempt": attempt,
                        "maxAttempts": max_attempts,
                        "transportAttempt": transport_attempt,
                        "transportMaxAttempts": transport_max_attempts,
                    },
                    response={"note": "scene shard report reached terminal status before turn/completed"},
                    transcript=transcript,
                )
        except Exception as exc:
            if is_codex_transport_error(exc) and _semantic_review_report_completed(report_path):
                transcript = getattr(exc, "transcript", transcript)
            elif is_codex_transport_error(exc):
                failure = _image_prompt_transport_failure_result(shard=shard, exc=exc)
                write_app_server_debug_log(
                    run_dir=run_dir,
                    operation="semantic_review",
                    status="app_server_failed",
                    item_id=job_id,
                    request={
                        "stage": "image_prompt",
                        "mode": "per_scene_shard",
                        "shardId": shard_id,
                        "entryIds": entry_ids,
                        "attempt": attempt,
                        "maxAttempts": max_attempts,
                        "transportAttempt": transport_attempt,
                        "transportMaxAttempts": transport_max_attempts,
                    },
                    response={
                        "transportErrorKind": failure.get("transport_error_kind"),
                        "failureContext": _codex_failure_context(exc, client=client),
                    },
                    transcript=getattr(exc, "transcript", [])
                    if isinstance(getattr(exc, "transcript", None), list)
                    else [],
                    error=f"{type(exc).__name__}: {exc}",
                )
                return failure
            else:
                raise
        finally:
            await client.stop()

        report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else ""
        reported_status = parse_judgment_report_status(report_text) if report_text else ""
        reviewed_entries = _semantic_report_list_values_with_duplicates(report_text, "reviewed_entries")
        coverage_errors = _image_prompt_reviewed_entry_coverage_errors(entry_ids, reviewed_entries)
        reported_blocked_entries = _semantic_report_list_values(report_text, "blocked_entries")
        reported_failed_selectors = _semantic_report_list_values(report_text, "failed_selectors")
        findings = _semantic_report_list_values(report_text, "findings")
        reason_keys = _semantic_report_list_values(report_text, "reason_keys")
        errors: list[str] = []
        if reported_status != "passed":
            errors.append(f"shard report status must be passed, got {reported_status or '(missing)'}")
        if reported_blocked_entries:
            errors.append(
                "passed shard report must have empty blocked_entries: "
                + ", ".join(reported_blocked_entries)
            )
        if reported_failed_selectors:
            errors.append(
                "passed shard report must have empty failed_selectors: "
                + ", ".join(reported_failed_selectors)
            )
        errors.extend(coverage_errors)
        if coverage_errors:
            reason_keys.append("semantic_review_selector_coverage_invalid")
            findings.extend(coverage_errors)
        if reported_blocked_entries or reported_failed_selectors:
            reason_keys.append("image_prompt_shard_report_inconsistent")
        if errors and not reason_keys:
            reason_keys.append("image_prompt_shard_failed")
        status = "passed" if not errors else "failed"
        if status == "passed":
            result: dict[str, Any] = {
                "shard_id": shard_id,
                "scene_id": str(shard.get("scene_id") or ""),
                "entry_ids": entry_ids,
                "status": "passed",
                "errors": [],
                "blocked_entries": [],
                "findings": [],
                "reason_keys": [],
            }
        else:
            result = _image_prompt_shard_failure_result(
                shard=shard,
                status="failed",
                errors=errors,
                findings=findings,
                reason_keys=_dedupe_preserve_order(reason_keys),
            )
        _touch_image_prompt_canonical_progress(
            canonical_report_path,
            message=f"image_prompt shard {shard_index}/{total_shards} completed: {shard_id} -> {status}",
        )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="semantic_review",
            status="completed" if status == "passed" else "changes_requested",
            item_id=job_id,
            request={
                "stage": "image_prompt",
                "mode": "per_scene_shard",
                "shardId": shard_id,
                "entryIds": entry_ids,
                "attempt": attempt,
                "maxAttempts": max_attempts,
                "transportAttempt": transport_attempt,
                "transportMaxAttempts": transport_max_attempts,
                "prompt": str(prompt_path.relative_to(run_dir)),
                "report": str(report_path.relative_to(run_dir)),
            },
            response={
                "status": status,
                "reportedStatus": reported_status,
                "expectedEntryCount": len(entry_ids),
                "reviewedEntryCount": len(reviewed_entries),
                "coverageErrors": coverage_errors,
                "reportedBlockedEntries": reported_blocked_entries,
                "reportedFailedSelectors": reported_failed_selectors,
                "blockedEntries": result["blocked_entries"],
                "reasonKeys": result["reason_keys"],
            },
            transcript=transcript if isinstance(transcript, list) else [],
            error="; ".join(errors) if errors else None,
        )
        return result


async def _run_scene_detail_sharded_semantic_review_once(
    job_id: str,
    *,
    run_dir: Path,
    attempt: int,
    max_attempts: int,
    final_attempt: bool,
) -> SemanticReviewStatus:
    stage = "scene_detail"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "build-semantic-review-pack.py"),
            "--run-dir",
            str(run_dir),
            "--stage",
            stage,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    relpaths = semantic_review_relpaths(stage)
    collection_path = run_dir / relpaths["collection"]
    scope_path = run_dir / relpaths["scope"]
    report_path = run_dir / relpaths["report"]
    shard_dir = run_dir / "logs" / "review" / "semantic" / "scene_detail_shards" / f"attempt_{attempt:02d}"
    concurrency = scene_detail_review_concurrency()
    transport_retry_attempts = scene_detail_transport_retry_attempts()
    entry_ids = _semantic_review_scope_entry_ids(scope_path)
    if not entry_ids:
        _write_scene_detail_shard_aggregate_report(
            report_path,
            status="failed",
            reviewed_entries=[],
            blocked_entries=["scene_detail"],
            findings=["scene_detail scope has no entry_ids; cannot shard review"],
            reason_keys=["semantic_review_scope_missing_entry_ids"],
            notes=[],
        )
        result = check_semantic_review(run_dir, stage)
        state_updates = review_status_to_state(stage, result)
        state_updates.update(
            {
                "review.semantic.scene_detail.shards.status": "failed",
                "review.semantic.scene_detail.shards.count": "0",
                "review.semantic.scene_detail.shards.concurrency": str(concurrency),
                "review.semantic.scene_detail.shards.failed_count": "1",
                "review.semantic.scene_detail.shards.attempt": str(attempt),
                "review.semantic.scene_detail.shards.dir": shard_dir.relative_to(run_dir).as_posix(),
                "review.semantic.scene_detail.shards.updated_at": now_iso(),
            }
        )
        slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
        if slot:
            state_updates[f"slot.{slot}.status"] = "failed" if final_attempt else "in_progress"
            state_updates[f"slot.{slot}.note"] = "contextless semantic scene_detail shard review could not start because scope entry_ids were missing"
        append_state_snapshot(run_dir / "state.txt", state_updates)
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="semantic_review",
            status="failed" if final_attempt else "changes_requested",
            item_id=job_id,
            request={
                "stage": stage,
                "attempt": attempt,
                "maxAttempts": max_attempts,
                "mode": "per_scene_shards",
                "concurrency": concurrency,
                "transportRetryAttempts": transport_retry_attempts,
                "shardCount": 0,
                "report": str(report_path.relative_to(run_dir)),
            },
            response={
                "status": result.status,
                "entryCount": result.entry_count,
                "failedShardCount": 1,
                "reasonKeys": ["semantic_review_scope_missing_entry_ids"],
            },
            error="; ".join(result.errors) if result.errors else None,
        )
        return result

    collection_text = collection_path.read_text(encoding="utf-8", errors="replace")
    sections = _semantic_collection_sections_by_entry(collection_text)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "review.semantic.scene_detail.shards.status": "reviewing",
            "review.semantic.scene_detail.shards.count": str(len(entry_ids)),
            "review.semantic.scene_detail.shards.concurrency": str(concurrency),
            "review.semantic.scene_detail.shards.attempt": str(attempt),
            "review.semantic.scene_detail.shards.dir": shard_dir.relative_to(run_dir).as_posix(),
            "review.semantic.scene_detail.shards.updated_at": now_iso(),
        },
    )

    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        asyncio.create_task(
            _run_scene_detail_shard_review(
                job_id,
                run_dir=run_dir,
                shard_dir=shard_dir,
                entry_id=entry_id,
                entry_index=index,
                total_entries=len(entry_ids),
                collection_section=sections.get(entry_id, ""),
                canonical_scope_path=scope_path,
                canonical_report_path=report_path,
                attempt=attempt,
                max_attempts=max_attempts,
                final_attempt=final_attempt,
                transport_attempt=1,
                transport_max_attempts=transport_retry_attempts,
                semaphore=semaphore,
            )
        )
        for index, entry_id in enumerate(entry_ids, start=1)
    ]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    shard_results: list[dict[str, Any]] = []
    unexpected_exceptions: list[BaseException] = []
    for entry_id, raw_result in zip(entry_ids, raw_results):
        if isinstance(raw_result, BaseException):
            if is_codex_transport_error(raw_result):
                shard_results.append(
                    _scene_detail_transport_failure_result(entry_id=entry_id, exc=raw_result)
                )
                continue
            unexpected_exceptions.append(raw_result)
            continue
        shard_results.append(raw_result)
    if unexpected_exceptions:
        raise unexpected_exceptions[0]

    for transport_attempt in range(2, transport_retry_attempts + 1):
        transport_failures_for_retry = [
            result_item
            for result_item in shard_results
            if str(result_item.get("status") or "") == "transport_failed"
        ]
        if not transport_failures_for_retry:
            break
        retry_entry_ids = [str(result_item["entry_id"]) for result_item in transport_failures_for_retry]
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "review.semantic.scene_detail.shards.transport.status": "retrying",
                "review.semantic.scene_detail.shards.transport.attempt": str(transport_attempt),
                "review.semantic.scene_detail.shards.transport.max_attempts": str(transport_retry_attempts),
                "review.semantic.scene_detail.shards.transport.retry_entries": ", ".join(retry_entry_ids),
                "review.semantic.scene_detail.shards.updated_at": now_iso(),
            },
        )
        for entry_id in retry_entry_ids:
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    f"review.semantic.scene_detail.shards.{_safe_scene_detail_shard_label(entry_id)}.transport.status": "retrying",
                    f"review.semantic.scene_detail.shards.{_safe_scene_detail_shard_label(entry_id)}.transport.retry_count": str(transport_attempt - 1),
                    f"review.semantic.scene_detail.shards.{_safe_scene_detail_shard_label(entry_id)}.transport.max_attempts": str(transport_retry_attempts),
                },
            )
        retry_tasks = [
            asyncio.create_task(
                _run_scene_detail_shard_review(
                    job_id,
                    run_dir=run_dir,
                    shard_dir=shard_dir,
                    entry_id=entry_id,
                    entry_index=entry_ids.index(entry_id) + 1,
                    total_entries=len(entry_ids),
                    collection_section=sections.get(entry_id, ""),
                    canonical_scope_path=scope_path,
                    canonical_report_path=report_path,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    final_attempt=final_attempt,
                    transport_attempt=transport_attempt,
                    transport_max_attempts=transport_retry_attempts,
                    semaphore=semaphore,
                )
            )
            for entry_id in retry_entry_ids
        ]
        raw_retry_results = await asyncio.gather(*retry_tasks, return_exceptions=True)
        retry_results_by_entry: dict[str, dict[str, Any]] = {}
        retry_unexpected_exceptions: list[BaseException] = []
        for entry_id, raw_result in zip(retry_entry_ids, raw_retry_results):
            if isinstance(raw_result, BaseException):
                if is_codex_transport_error(raw_result):
                    retry_results_by_entry[entry_id] = _scene_detail_transport_failure_result(entry_id=entry_id, exc=raw_result)
                    continue
                retry_unexpected_exceptions.append(raw_result)
                continue
            retry_results_by_entry[entry_id] = raw_result
        if retry_unexpected_exceptions:
            raise retry_unexpected_exceptions[0]
        next_shard_results: list[dict[str, Any]] = []
        for result_item in shard_results:
            entry_id = str(result_item["entry_id"])
            replacement = retry_results_by_entry.get(entry_id)
            if replacement is None:
                next_shard_results.append(result_item)
                continue
            next_shard_results.append(replacement)
            label = _safe_scene_detail_shard_label(entry_id)
            if str(replacement.get("status") or "") == "transport_failed":
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        f"review.semantic.scene_detail.shards.{label}.transport.status": "failed",
                        f"review.semantic.scene_detail.shards.{label}.transport.retry_count": str(transport_attempt - 1),
                        f"review.semantic.scene_detail.shards.{label}.transport.error_kind": str(replacement.get("transport_error_kind") or "unknown"),
                        f"review.semantic.scene_detail.shards.{label}.transport.error": str(replacement.get("transport_error") or "")[:2000],
                    },
                )
            else:
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        f"review.semantic.scene_detail.shards.{label}.transport.status": "recovered",
                        f"review.semantic.scene_detail.shards.{label}.transport.retry_count": str(transport_attempt - 1),
                    },
                )
        shard_results = next_shard_results

    reviewed_entries = [result["entry_id"] for result in shard_results]
    blocked_entries = _dedupe_preserve_order(
        blocked_entry
        for result in shard_results
        if result["status"] != "passed"
        for blocked_entry in (result["blocked_entries"] or [result["entry_id"]])
    )
    findings: list[str] = []
    reason_keys: list[str] = []
    notes = [
        f"scene_detail reviewed as {len(shard_results)} per-scene shard(s)",
        f"bounded concurrency: {concurrency}",
        f"transport retry attempts: {transport_retry_attempts}",
    ]
    for result_item in shard_results:
        if result_item["status"] == "passed":
            continue
        entry_id = str(result_item["entry_id"])
        findings.append(f"{entry_id}: semantic shard status was {result_item['status'] or 'missing'}")
        for error in result_item["errors"]:
            findings.append(f"{entry_id}: {error}")
        for finding in result_item["findings"]:
            findings.append(f"{entry_id}: {finding}")
        reason_keys.extend(result_item["reason_keys"])
    transport_failures = [
        result_item
        for result_item in shard_results
        if str(result_item.get("status") or "") == "transport_failed"
    ]
    for result_item in transport_failures:
        entry_id = str(result_item["entry_id"])
        append_state_snapshot(
            run_dir / "state.txt",
            {
                f"review.semantic.scene_detail.shards.{_safe_scene_detail_shard_label(entry_id)}.transport.status": "failed",
                f"review.semantic.scene_detail.shards.{_safe_scene_detail_shard_label(entry_id)}.transport.error_kind": str(result_item.get("transport_error_kind") or "unknown"),
                f"review.semantic.scene_detail.shards.{_safe_scene_detail_shard_label(entry_id)}.transport.error": str(result_item.get("transport_error") or "")[:2000],
            },
        )
    if not reason_keys and blocked_entries:
        reason_keys.append("scene_detail_shard_failed")

    _write_scene_detail_shard_aggregate_report(
        report_path,
        status="failed" if blocked_entries else "passed",
        reviewed_entries=reviewed_entries,
        blocked_entries=blocked_entries,
        findings=findings,
        reason_keys=sorted(set(reason_keys)),
        notes=notes,
    )
    result = check_semantic_review(run_dir, stage)
    state_updates = review_status_to_state(stage, result)
    state_updates.update(
        {
            "review.semantic.scene_detail.shards.status": "passed" if result.passed else "failed",
            "review.semantic.scene_detail.shards.failed_count": str(len(blocked_entries)),
            "review.semantic.scene_detail.shards.updated_at": now_iso(),
        }
    )
    slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
    if slot:
        if result.passed:
            state_updates[f"slot.{slot}.status"] = "done"
            state_updates[f"slot.{slot}.note"] = "contextless semantic scene_detail shard review passed"
            state_updates["review.semantic.scene_detail.transport.status"] = "passed"
            state_updates["review.semantic.scene_detail.repair.active"] = "false"
        elif final_attempt:
            state_updates[f"slot.{slot}.status"] = "failed"
            if max_attempts <= 1:
                state_updates[f"slot.{slot}.note"] = "contextless semantic scene_detail shard review failed without repair"
                state_updates["review.semantic.scene_detail.repair.active"] = "false"
                state_updates["review.semantic.scene_detail.repair.skipped"] = "true"
                state_updates["review.semantic.scene_detail.repair.skipped_reason"] = "max_attempts_1"
            else:
                state_updates[f"slot.{slot}.note"] = "contextless semantic scene_detail shard review failed after repair loop"
        else:
            state_updates[f"slot.{slot}.status"] = "in_progress"
            state_updates[f"slot.{slot}.note"] = "contextless semantic scene_detail shard review requested producer repair"
    append_state_snapshot(run_dir / "state.txt", state_updates)
    write_app_server_debug_log(
        run_dir=run_dir,
        operation="semantic_review",
        status="completed" if result.passed else ("failed" if final_attempt else "changes_requested"),
        item_id=job_id,
        request={
            "stage": stage,
            "attempt": attempt,
            "maxAttempts": max_attempts,
            "mode": "per_scene_shards",
            "concurrency": concurrency,
            "transportRetryAttempts": transport_retry_attempts,
            "shardCount": len(shard_results),
            "report": str(report_path.relative_to(run_dir)),
        },
        response={
            "status": result.status,
            "entryCount": result.entry_count,
            "failedShardCount": len(blocked_entries),
            "transportFailedShardCount": len(transport_failures),
            "transportFailedEntries": [str(result_item["entry_id"]) for result_item in transport_failures],
        },
        error="; ".join(result.errors) if result.errors else None,
    )
    if transport_failures:
        failed_entries = ", ".join(str(result_item["entry_id"]) for result_item in transport_failures)
        raise CodexAppServerTransportError(
            f"scene_detail shard transport failed after {transport_retry_attempts} attempt(s): {failed_entries}"
        )
    return result


def _semantic_review_scope_entry_ids(scope_path: Path) -> list[str]:
    try:
        scope = json.loads(scope_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_ids = scope.get("entry_ids") if isinstance(scope, dict) else None
    return [str(item).strip() for item in raw_ids if str(item).strip()] if isinstance(raw_ids, list) else []


def _semantic_collection_sections_by_entry(collection_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for chunk in collection_text.split("\n## ")[1:]:
        if not chunk.strip():
            continue
        heading, _, body = chunk.partition("\n")
        entry_id = heading.strip().strip("`")
        if entry_id:
            sections[entry_id] = f"## {heading}\n{body}".strip() + "\n"
    return sections


async def _run_scene_detail_shard_review(
    job_id: str,
    *,
    run_dir: Path,
    shard_dir: Path,
    entry_id: str,
    entry_index: int,
    total_entries: int,
    collection_section: str,
    canonical_scope_path: Path,
    canonical_report_path: Path,
    attempt: int,
    max_attempts: int,
    final_attempt: bool,
    semaphore: asyncio.Semaphore,
    transport_attempt: int = 1,
    transport_max_attempts: int = 1,
) -> dict[str, Any]:
    async with semaphore:
        shard_label = _safe_scene_detail_shard_label(entry_id)
        collection_path = shard_dir / f"{entry_index:03d}_{shard_label}.collection.md"
        scope_path = shard_dir / f"{entry_index:03d}_{shard_label}.scope.json"
        prompt_path = shard_dir / f"{entry_index:03d}_{shard_label}.prompt.md"
        report_path = shard_dir / f"{entry_index:03d}_{shard_label}.report.md"
        _write_scene_detail_shard_artifacts(
            run_dir=run_dir,
            entry_id=entry_id,
            entry_index=entry_index,
            total_entries=total_entries,
            collection_section=collection_section,
            collection_path=collection_path,
            scope_path=scope_path,
            prompt_path=prompt_path,
            report_path=report_path,
            canonical_scope_path=canonical_scope_path,
            canonical_report_path=canonical_report_path,
        )
        _touch_scene_detail_canonical_progress(
            canonical_report_path,
            status="pending",
            message=f"scene_detail shard {entry_index}/{total_entries} started: {entry_id}",
        )
        client = create_codex_app_server_client(cwd=ROOT)
        transcript: list[dict[str, Any]] = []
        try:
            thread_id = await asyncio.wait_for(
                client.start_thread(cwd=ROOT, approval_policy="never"),
                timeout=CODEX_APP_SERVER_START_TIMEOUT_SECONDS,
            )
            prompt = prompt_path.read_text(encoding="utf-8")
            prompt = _semantic_review_prompt_for_attempt(
                prompt,
                stage="scene_detail",
                final_attempt=final_attempt,
            )
            prompt_path.write_text(prompt.rstrip() + "\n", encoding="utf-8")
            transcript, completed_from_report = await _run_turn_until_semantic_artifact_completed(
                client,
                thread_id=thread_id,
                text=prompt,
                cwd=ROOT,
                timeout_seconds=semantic_review_timeout_seconds(),
                report_path=report_path,
                is_completed=_semantic_review_report_completed,
                progress_callback=lambda notification: _write_scene_detail_shard_activity(
                    report_path=report_path,
                    canonical_report_path=canonical_report_path,
                    notification=notification,
                ),
            )
            if completed_from_report:
                write_app_server_debug_log(
                    run_dir=run_dir,
                    operation="semantic_review",
                    status="completed_after_report_before_turn_completed",
                    item_id=job_id,
                    request={
                        "stage": "scene_detail",
                        "mode": "per_scene_shard",
                        "entryId": entry_id,
                        "attempt": attempt,
                        "maxAttempts": max_attempts,
                        "transportAttempt": transport_attempt,
                        "transportMaxAttempts": transport_max_attempts,
                        "prompt": str(prompt_path.relative_to(run_dir)),
                        "report": str(report_path.relative_to(run_dir)),
                    },
                    response={
                        "note": "scene_detail shard report reached a terminal status before app-server turn/completed notification arrived",
                    },
                    transcript=transcript,
                )
        except Exception as exc:
            transport_kind = classify_codex_transport_error(str(exc))
            if is_codex_transport_error(exc) and _semantic_review_report_completed(report_path):
                transcript = getattr(exc, "transcript", transcript)
                write_app_server_debug_log(
                    run_dir=run_dir,
                    operation="semantic_review",
                    status="completed_after_transport_timeout",
                    item_id=job_id,
                    request={
                        "stage": "scene_detail",
                        "mode": "per_scene_shard",
                        "entryId": entry_id,
                        "attempt": attempt,
                        "maxAttempts": max_attempts,
                        "transportAttempt": transport_attempt,
                        "transportMaxAttempts": transport_max_attempts,
                        "prompt": str(prompt_path.relative_to(run_dir)),
                        "report": str(report_path.relative_to(run_dir)),
                    },
                    response={
                        "transportErrorKind": transport_kind or "unknown",
                        "note": "scene_detail shard report was completed before app-server turn completion notification timed out",
                    },
                    transcript=transcript if isinstance(transcript, list) else [],
                )
            else:
                if is_codex_transport_error(exc):
                    transport_kind = classify_codex_transport_error(str(exc)) or "unknown"
                    write_app_server_debug_log(
                        run_dir=run_dir,
                        operation="semantic_review",
                        status="app_server_failed",
                        item_id=job_id,
                        request={
                            "stage": "scene_detail",
                            "mode": "per_scene_shard",
                            "entryId": entry_id,
                            "attempt": attempt,
                            "maxAttempts": max_attempts,
                            "transportAttempt": transport_attempt,
                            "transportMaxAttempts": transport_max_attempts,
                            "prompt": str(prompt_path.relative_to(run_dir)),
                            "report": str(report_path.relative_to(run_dir)),
                        },
                        response={
                            "transportErrorKind": transport_kind,
                            "failureContext": _codex_failure_context(exc, client=client),
                        },
                        transcript=getattr(exc, "transcript", []) if isinstance(getattr(exc, "transcript", None), list) else [],
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    return _scene_detail_transport_failure_result(entry_id=entry_id, exc=exc)
                write_app_server_debug_log(
                    run_dir=run_dir,
                    operation="semantic_review",
                    status="app_server_failed",
                    item_id=job_id,
                    request={
                        "stage": "scene_detail",
                        "mode": "per_scene_shard",
                        "entryId": entry_id,
                        "attempt": attempt,
                        "maxAttempts": max_attempts,
                        "transportAttempt": transport_attempt,
                        "transportMaxAttempts": transport_max_attempts,
                        "prompt": str(prompt_path.relative_to(run_dir)),
                        "report": str(report_path.relative_to(run_dir)),
                    },
                    response={"failureContext": _codex_failure_context(exc, client=client)},
                    transcript=getattr(exc, "transcript", []) if isinstance(getattr(exc, "transcript", None), list) else [],
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise
        finally:
            await client.stop()
        report_text = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else ""
        status = parse_judgment_report_status(report_text) if report_text else ""
        failed_selectors = _semantic_report_list_values(report_text, "failed_selectors")
        blocked_entries = _semantic_report_list_values(report_text, "blocked_entries")
        findings = _semantic_report_list_values(report_text, "findings")
        reason_keys = _semantic_report_list_values(report_text, "reason_keys")
        if status != "passed":
            if not blocked_entries and not failed_selectors:
                blocked_entries = [entry_id]
            if not reason_keys:
                reason_keys = ["scene_detail_shard_failed"]
        result = {
            "entry_id": entry_id,
            "status": status,
            "errors": [] if status == "passed" else [f"shard report status must be passed, got {status or '(missing)'}"],
            "blocked_entries": _dedupe_preserve_order([*failed_selectors, *blocked_entries]) if status != "passed" else [],
            "findings": findings if status != "passed" else [],
            "reason_keys": _dedupe_preserve_order(reason_keys) if status != "passed" else [],
        }
        _touch_scene_detail_canonical_progress(
            canonical_report_path,
            status="pending",
            message=f"scene_detail shard {entry_index}/{total_entries} completed: {entry_id} -> {status or 'missing'}",
        )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="semantic_review",
            status="completed" if status == "passed" else "changes_requested",
            item_id=job_id,
            request={
                "stage": "scene_detail",
                "mode": "per_scene_shard",
                "entryId": entry_id,
                "attempt": attempt,
                "maxAttempts": max_attempts,
                "transportAttempt": transport_attempt,
                "transportMaxAttempts": transport_max_attempts,
                "prompt": str(prompt_path.relative_to(run_dir)),
                "report": str(report_path.relative_to(run_dir)),
            },
            response={
                "status": status,
                "entryCount": 1,
                "blockedEntries": result["blocked_entries"],
                "reasonKeys": result["reason_keys"],
            },
            transcript=transcript,
            error="; ".join(result["errors"]) if result["errors"] else None,
        )
        return result


def _write_scene_detail_shard_artifacts(
    *,
    run_dir: Path,
    entry_id: str,
    entry_index: int,
    total_entries: int,
    collection_section: str,
    collection_path: Path,
    scope_path: Path,
    prompt_path: Path,
    report_path: Path,
    canonical_scope_path: Path,
    canonical_report_path: Path,
) -> None:
    collection_path.parent.mkdir(parents=True, exist_ok=True)
    if not collection_section:
        collection_section = f"## {entry_id}\n\n```json\n{{\"id\": {json.dumps(entry_id, ensure_ascii=False)}}}\n```\n"
    collection_path.write_text(
        "\n".join(
            [
                "# Semantic Review Collection: scene_detail shard",
                "",
                f"Shard entry: `{entry_id}`",
                f"Shard index: `{entry_index}` of `{total_entries}`",
                "",
                collection_section.strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )
    source_artifacts = _semantic_scope_source_artifacts(canonical_scope_path)
    scope_payload = {
        "stage": "scene_detail",
        "run_dir": str(run_dir.resolve()),
        "entry_count": 1,
        "entry_ids": [entry_id],
        "review_scope": "single_scene_entry",
        "canonical_stage": "scene_detail",
        "canonical_scope": str(canonical_scope_path.relative_to(run_dir)),
        "canonical_report": str(canonical_report_path.relative_to(run_dir)),
        "source_artifacts": source_artifacts,
        "artifacts": {
            "collection": str(collection_path.relative_to(run_dir)),
            "scope": str(scope_path.relative_to(run_dir)),
            "prompt": str(prompt_path.relative_to(run_dir)),
            "report": str(report_path.relative_to(run_dir)),
        },
        "generated_at": now_iso(),
    }
    scope_path.write_text(json.dumps(scope_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source_lines = [f"- `{(run_dir / rel).resolve()}`" for rel in source_artifacts]
    prompt_path.write_text(
        "\n".join(
            [
                "You are a contextless semantic review agent for a single ToC `scene_detail` entry.",
                "",
                "Do semantic judgment only. Do not edit source artifacts and do not repair outputs.",
                f"Review only shard entry `{entry_id}`. Ignore other scene ids except as source context for neighbor handoff.",
                "",
                "Read these artifacts in order:",
                f"1. `{scope_path}`",
                f"2. `{collection_path}`",
                f"3. `{report_path}`",
                "",
                "Use these source artifacts as cross-check context when present:",
                *(source_lines or ["- `(none discovered)`"]),
                "",
                f"Write the final report to `{report_path}` and replace the pending template.",
                "",
                "Gate this scene_detail entry on scene necessity, internal pressure, value_shift visibility, causal_turn visibility, scene_event sequence, scene_generation prompt separation, story-specific concrete grounding, non_replaceable_elements, concrete detail story_function, source grounding confidence, canonical event coverage, turning_event/end_situation alignment, cut summary support, reveal order, and neighbor handoff.",
                "Treat `scene_generation.scene_prompt_payload.prompt` as the canonical scene authoring prompt. This review prompt is only a display/review artifact, not the scene generation canon.",
                "Fail if scene_prompt_payload mixes downstream image/video/audio execution details, fixed cut count, or image directing terms instead of describing what the scene must establish in the story.",
                "Do not reject useful abstract dramatic language by itself. Reject only when abstraction is not paired with concrete_event / story_grounding that comes from source story, user input, canonical reference, or asset bible.",
                "Treat decorative concrete detail without story_function, asset names mentioned without story function, invented_candidate details without approval, and missing required canonical events as gate failures.",
                "Do not require a fixed cut count. Judge whether this scene's actual visual obligations are sufficiently represented by its cut summaries and contracts.",
                "Do not fail solely because generated image/video/audio files do not exist yet.",
                "",
                "Report format:",
                "status: passed|failed",
                "reviewed_entries: [...]",
                "blocked_entries: [...]",
                "findings: [...]",
                "failed_selectors: [...]",
                "reason_keys: [semantic_subject_mismatch|semantic_location_mismatch|semantic_timeline_mismatch|semantic_reveal_order_mismatch|scene_detail_obligation_missing|scene_detail_cut_support_weak|scene_detail_handoff_weak|scene_generation_payload_missing|scene_generation_payload_downstream_leak|scene_generation_payload_fixed_cut_count|scene_generation_debug_source_missing|scene_generation_contract_mismatch|scene_event_abstract_only|scene_event_concrete_but_not_story_specific|scene_event_concrete_but_decorative|scene_event_missing_non_replaceable_elements|scene_event_missing_source_grounding|scene_event_source_grounding_low_confidence|scene_event_missing_character_relationship_specificity|scene_event_missing_story_rule_specificity|scene_event_missing_object_story_function|scene_event_asset_mentioned_without_story_function|scene_event_canonical_event_missing|scene_event_canonical_order_broken|scene_event_invented_detail_without_approval|scene_event_specificity_overloaded|...]",
                "notes: [...]",
                "",
                f"Run dir: `{run_dir.resolve()}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        "\n".join(
            [
                "# Semantic Review Report: scene_detail shard",
                "",
                f"- run_dir: `{run_dir.resolve()}`",
                "- stage: `scene_detail`",
                f"- entry_id: `{entry_id}`",
                f"- scope: `{scope_path}`",
                f"- collection: `{collection_path}`",
                "- status: `pending`",
                "",
                "## Reviewed Entries",
                "",
                "- `...`",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _semantic_scope_source_artifacts(scope_path: Path) -> list[str]:
    try:
        scope = json.loads(scope_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw = scope.get("source_artifacts") if isinstance(scope, dict) else None
    return [str(item) for item in raw if isinstance(item, str) and item.strip()] if isinstance(raw, list) else []


def _scene_detail_transport_failure_result(*, entry_id: str, exc: BaseException) -> dict[str, Any]:
    transport_kind = classify_codex_transport_error(str(exc)) or "unknown"
    reason_keys = ["scene_detail_shard_transport_failed"]
    if transport_kind == "timeout":
        reason_keys.append("scene_detail_shard_transport_timeout")
    return {
        "entry_id": entry_id,
        "status": "transport_failed",
        "errors": [f"app-server transport {transport_kind}: {type(exc).__name__}: {exc}"],
        "blocked_entries": [entry_id],
        "findings": [f"scene_detail shard transport failed before a terminal report: {type(exc).__name__}: {exc}"],
        "reason_keys": reason_keys,
        "transport_error_kind": transport_kind,
        "transport_error": f"{type(exc).__name__}: {exc}",
    }


def _semantic_report_list_values(report_text: str, field: str) -> list[str]:
    values: list[str] = []
    lines = report_text.splitlines()
    in_field = False
    field_prefix = f"{field}:"
    label_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_ -]*:\s*")
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            if in_field:
                break
            continue
        if stripped.startswith(field_prefix):
            in_field = True
            inline = stripped.split(":", 1)[1].strip()
            values.extend(_semantic_report_inline_values(inline))
            if inline and inline not in {"[]", "[ ]"}:
                in_field = False
            continue
        if not in_field:
            continue
        if label_re.match(stripped):
            break
        if stripped.startswith("-"):
            value = _semantic_report_scalar(stripped[1:].strip())
            if value:
                values.append(value)
        else:
            value = _semantic_report_scalar(stripped)
            if value:
                values.append(value)
    return _dedupe_preserve_order(values)


def _semantic_report_inline_values(value: str) -> list[str]:
    cleaned = value.strip()
    if not cleaned or cleaned in {"[]", "[ ]"}:
        return []
    if cleaned.startswith("[") and cleaned.endswith("]"):
        body = cleaned[1:-1].strip()
        if not body:
            return []
        return [_semantic_report_scalar(item) for item in body.split(",") if _semantic_report_scalar(item)]
    scalar = _semantic_report_scalar(cleaned)
    return [scalar] if scalar else []


def _semantic_report_scalar(value: str) -> str:
    cleaned = value.strip().strip(",").strip()
    cleaned = cleaned.strip("`\"'")
    return "" if cleaned in {"...", "[]"} else cleaned


def _dedupe_preserve_order(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _safe_scene_detail_shard_label(entry_id: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", entry_id).strip("._-")
    return label or "entry"


def _touch_scene_detail_canonical_progress(canonical_report_path: Path, *, status: str, message: str) -> None:
    canonical_report_path.parent.mkdir(parents=True, exist_ok=True)
    with _scene_detail_canonical_progress_lock:
        canonical_report_path.write_text(
            "\n".join(
                [
                    "# Semantic Review Report: scene_detail",
                    "",
                    f"status: {status}",
                    "reviewed_entries: []",
                    "blocked_entries: []",
                    "findings: []",
                    f"notes: [{json.dumps(message, ensure_ascii=False)}]",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def _write_scene_detail_shard_activity(
    *,
    report_path: Path,
    canonical_report_path: Path,
    notification: dict[str, Any],
) -> None:
    _write_semantic_turn_activity_marker(report_path, notification)
    with _scene_detail_canonical_progress_lock:
        _write_semantic_turn_activity_marker(canonical_report_path, notification)


def _write_scene_detail_shard_aggregate_report(
    report_path: Path,
    *,
    status: str,
    reviewed_entries: list[str],
    blocked_entries: list[str],
    findings: list[str],
    reason_keys: list[str],
    notes: list[str],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        "\n".join(
            [
                "# Semantic Review Report: scene_detail",
                "",
                f"status: {status}",
                "reviewed_entries:",
                *[f"  - {entry}" for entry in reviewed_entries],
                "blocked_entries:",
                *[f"  - {entry}" for entry in blocked_entries],
                "findings:",
                *[f"  - {finding}" for finding in findings],
                "failed_selectors:",
                *[f"  - {entry}" for entry in blocked_entries],
                "reason_keys:",
                *[f"  - {key}" for key in reason_keys],
                "notes:",
                *[f"  - {note}" for note in notes],
                "",
            ]
        ),
        encoding="utf-8",
    )


def _semantic_repair_report_completed(report_path: Path) -> bool:
    if not report_path.exists():
        return False
    for raw in report_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip().lower()
        if line.startswith("status:"):
            return line.split(":", 1)[1].strip(" `\"'") == "done"
    return False


def _semantic_review_report_completed(report_path: Path) -> bool:
    if not report_path.exists():
        return False
    report_text = report_path.read_text(encoding="utf-8", errors="replace")
    if "`...`" in report_text or "- `...`" in report_text:
        return False
    status = parse_judgment_report_status(report_text)
    return bool(status and status != "pending")


SEMANTIC_TURN_ARTIFACT_POLL_SECONDS = 2.0
SEMANTIC_TURN_COMPLETION_GRACE_SECONDS = 15.0


def _semantic_report_text_from_transcript(
    transcript: list[dict[str, Any]],
    stage: str,
) -> str | None:
    """Recover a complete AI verdict when it was returned in chat instead of the report file."""

    for notification in reversed(transcript):
        if notification.get("method") != "item/completed":
            continue
        params = notification.get("params")
        item = params.get("item") if isinstance(params, dict) else None
        if not isinstance(item, dict) or item.get("type") != "agentMessage":
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        status = parse_judgment_report_status(text)
        if status not in {"passed", "failed"}:
            match = re.search(
                r"(?im)^\s*(?:recommended\s+overall\s+)?status\s*:\s*`?(passed|failed)`?\s*$",
                text,
            )
            status = match.group(1).lower() if match else ""
        required_fields = ("reviewed_entries:", "blocked_entries:", "failed_selectors:")
        if status not in {"passed", "failed"} or any(field not in text for field in required_fields):
            continue
        if stage in {"research", "story"} and "criteria_results_json:" not in text:
            continue
        return (
            f"status: {status}\n"
            "report_transport: agent_message_fallback\n"
            + text
            + "\n"
        )
    return None


async def _run_turn_until_semantic_artifact_completed(
    client: CodexAppServerClient,
    *,
    thread_id: str,
    text: str,
    cwd: Path,
    timeout_seconds: int,
    report_path: Path,
    is_completed,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    progress_writer = progress_callback or (lambda notification: _write_semantic_turn_activity_marker(report_path, notification))
    turn_task = asyncio.create_task(
        client.run_turn(
            thread_id=thread_id,
            text=text,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            reset_timeout_on_notification=True,
            progress_callback=progress_writer,
        )
    )
    try:
        while True:
            done, _ = await asyncio.wait({turn_task}, timeout=SEMANTIC_TURN_ARTIFACT_POLL_SECONDS)
            if turn_task in done:
                return await turn_task, False
            if is_completed(report_path):
                try:
                    transcript = await asyncio.wait_for(turn_task, timeout=SEMANTIC_TURN_COMPLETION_GRACE_SECONDS)
                    return transcript, False
                except asyncio.TimeoutError:
                    turn_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await turn_task
                    return [], True
                except Exception as exc:
                    if is_codex_transport_error(exc):
                        transcript = getattr(exc, "transcript", [])
                        return transcript if isinstance(transcript, list) else [], True
                    raise
    except Exception:
        if not turn_task.done():
            turn_task.cancel()
            with suppress(asyncio.CancelledError):
                await turn_task
        raise


async def _run_semantic_review_producer_repair(
    job_id: str,
    *,
    run_dir: Path,
    stage: str,
    round_number: int,
    max_attempts: int,
    errors: tuple[str, ...],
) -> None:
    paths = write_semantic_repair_prompt(
        run_dir,
        stage,
        round_number=round_number,
        max_attempts=max_attempts,
        errors=errors,
    )
    source_fingerprint_before = _semantic_repair_source_artifact_fingerprint(run_dir, stage)
    target_selectors = _semantic_repair_target_selectors(run_dir, stage)
    report_relpath = paths["report"].relative_to(run_dir).as_posix()
    prompt_relpath = paths["prompt"].relative_to(run_dir).as_posix()
    activity_relpath = _semantic_turn_activity_relpath(paths["report"].relative_to(run_dir)).as_posix()
    state_updates = {}
    state_updates.update(
        semantic_loop_state_updates(
            stage,
            status="repairing",
            attempt=round_number,
            max_attempts=max_attempts,
            error_count=len(errors),
        )
    )
    state_updates.update(
        semantic_repair_state_updates(
            stage,
            status="in_progress",
            round_number=round_number,
            max_attempts=max_attempts,
            error_count=len(errors),
        )
    )
    state_updates.update(
        {
            f"review.semantic.{stage}.repair.report_status": _semantic_repair_report_status(paths["report"]),
            f"review.semantic.{stage}.repair.activity_marker": activity_relpath,
            f"review.semantic.{stage}.repair.source_fingerprint.before": _json_hash(source_fingerprint_before),
            f"review.semantic.{stage}.repair.source_fingerprint.before_count": str(len(source_fingerprint_before)),
            f"review.semantic.{stage}.repair.no_progress_timeout_seconds": f"{_semantic_repair_no_progress_timeout_seconds():.0f}",
        }
    )
    if target_selectors:
        state_updates[f"review.semantic.{stage}.repair.target_selectors"] = ", ".join(target_selectors)[:2000]
    slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
    if slot:
        state_updates[f"slot.{slot}.status"] = "in_progress"
        state_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} repair round {round_number} in progress"
    append_state_snapshot(run_dir / "state.txt", state_updates)
    write_app_server_debug_log(
        run_dir=run_dir,
        operation="semantic_review_producer_repair",
        status="started",
        item_id=job_id,
        request={
            "stage": stage,
            "round": round_number,
            "maxAttempts": max_attempts,
            "prompt": prompt_relpath,
            "report": report_relpath,
            "targetSelectors": target_selectors,
            "sourceFingerprintBefore": _semantic_repair_fingerprint_summary(source_fingerprint_before),
        },
        response={
            "errorCount": len(errors),
            "reportStatus": _semantic_repair_report_status(paths["report"]),
            "activityMarker": activity_relpath,
            "noProgressTimeoutSeconds": _semantic_repair_no_progress_timeout_seconds(),
        },
    )

    completion_log_status = "completed"
    completion_log_response: dict[str, Any] = {"errorCount": len(errors)}
    prompt = paths["prompt"].read_text(encoding="utf-8")
    client = create_codex_app_server_client(cwd=ROOT)
    transcript: list[dict[str, Any]] = []
    try:
        thread_id = await asyncio.wait_for(
            client.start_thread(cwd=ROOT, approval_policy="never"),
            timeout=CODEX_APP_SERVER_START_TIMEOUT_SECONDS,
        )
        transcript, completed_from_report = await _run_turn_until_semantic_artifact_completed(
            client,
            thread_id=thread_id,
            text=prompt,
            cwd=ROOT,
            timeout_seconds=semantic_repair_timeout_seconds(),
            report_path=paths["report"],
            is_completed=_semantic_repair_report_completed,
        )
        if completed_from_report:
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="semantic_review_producer_repair",
                status="completed_after_report_before_turn_completed",
                item_id=job_id,
                request={
                    "stage": stage,
                    "round": round_number,
                    "maxAttempts": max_attempts,
                    "prompt": str(paths["prompt"].relative_to(run_dir)),
                    "report": str(paths["report"].relative_to(run_dir)),
                },
                response={"errorCount": len(errors)},
                transcript=transcript,
            )
    except Exception as exc:
        if is_codex_transport_error(exc) and _semantic_repair_report_completed(paths["report"]):
            transcript = getattr(exc, "transcript", transcript)
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="semantic_review_producer_repair",
                status="completed_after_transport_timeout",
                item_id=job_id,
                request={
                    "stage": stage,
                    "round": round_number,
                    "maxAttempts": max_attempts,
                    "prompt": str(paths["prompt"].relative_to(run_dir)),
                    "report": str(paths["report"].relative_to(run_dir)),
                },
                response={
                    "errorCount": len(errors),
                    "transportErrorKind": classify_codex_transport_error(str(exc)) or "unknown",
                    "note": "producer report was completed before app-server turn completion notification timed out",
                },
                transcript=transcript if isinstance(transcript, list) else [],
            )
        else:
            failed_updates = {}
            transport_kind = classify_codex_transport_error(str(exc))
            salvaged_transport = False
            changed_artifacts: list[str] = []
            if is_codex_transport_error(exc):
                source_fingerprint_after = _semantic_repair_source_artifact_fingerprint(run_dir, stage)
                changed_artifacts = _changed_semantic_repair_artifacts(source_fingerprint_before, source_fingerprint_after)
                if changed_artifacts:
                    salvaged_transport = True
                    transcript = getattr(exc, "transcript", transcript)
                    completion_log_status = "completed_after_source_artifact_change_before_report"
                    completion_log_response = {
                        "errorCount": len(errors),
                        "transportErrorKind": transport_kind or "unknown",
                        "changedArtifacts": changed_artifacts,
                        "sourceFingerprintAfter": _semantic_repair_fingerprint_summary(source_fingerprint_after),
                        "reportStatus": _semantic_repair_report_status(paths["report"]),
                        "note": "producer repair changed source artifacts before its report reached status: done; rerunning semantic review instead of failing transport",
                    }
                    append_state_snapshot(
                        run_dir / "state.txt",
                        {
                            f"review.semantic.{stage}.repair.transport.status": "salvaged_after_source_artifact_change",
                            f"review.semantic.{stage}.repair.transport.error_kind": transport_kind or "unknown",
                            f"review.semantic.{stage}.repair.transport.error": str(exc)[:2000],
                            f"review.semantic.{stage}.repair.changed_artifacts_detected": ", ".join(changed_artifacts)[:2000],
                            f"review.semantic.{stage}.repair.source_fingerprint.after": _json_hash(source_fingerprint_after),
                            f"review.semantic.{stage}.repair.source_fingerprint.after_count": str(len(source_fingerprint_after)),
                            f"review.semantic.{stage}.repair.report_status": _semantic_repair_report_status(paths["report"]),
                            f"review.semantic.{stage}.repair.report": report_relpath,
                            f"review.semantic.{stage}.repair.activity_marker": activity_relpath,
                            f"review.semantic.{stage}.repair.pending.status": "salvaged_after_source_artifact_change",
                        },
                    )
                else:
                    failed_updates.update(
                        semantic_loop_state_updates(
                            stage,
                            status="blocked_transport",
                            attempt=round_number,
                            max_attempts=max_attempts,
                            error_count=len(errors),
                        )
                    )
                    failed_updates.update(
                        semantic_repair_state_updates(
                            stage,
                            status="blocked_transport",
                            round_number=round_number,
                            max_attempts=max_attempts,
                            error_count=len(errors),
                        )
                    )
                    failed_updates.update(
                        {
                            f"review.semantic.{stage}.transport.status": "failed",
                            f"review.semantic.{stage}.transport.error_kind": transport_kind or "unknown",
                            f"review.semantic.{stage}.transport.error": str(exc)[:2000],
                            f"review.semantic.{stage}.repair.transport.status": "failed",
                            f"review.semantic.{stage}.repair.transport.error_kind": transport_kind or "unknown",
                            "runtime.stage": "app_server_transport_failed",
                            "runtime.app_server.transport.status": "failed",
                            "runtime.app_server.transport.error_kind": transport_kind or "unknown",
                        }
                    )
            else:
                failed_updates.update(
                    semantic_loop_state_updates(
                        stage,
                        status="failed",
                        attempt=round_number,
                        max_attempts=max_attempts,
                        error_count=len(errors),
                    )
                )
                failed_updates.update(
                    semantic_repair_state_updates(
                        stage,
                        status="failed",
                        round_number=round_number,
                        max_attempts=max_attempts,
                        error_count=len(errors),
                    )
                )
            if not salvaged_transport and slot:
                failed_updates[f"slot.{slot}.status"] = "failed"
                if is_codex_transport_error(exc):
                    failed_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} producer repair blocked by app-server transport"
                else:
                    failed_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} producer repair failed"
            if not salvaged_transport:
                failed_updates[f"review.semantic.{stage}.repair.last_error"] = str(exc)[:2000]
                append_state_snapshot(run_dir / "state.txt", failed_updates)
                write_app_server_debug_log(
                    run_dir=run_dir,
                    operation="semantic_review_producer_repair",
                    status="app_server_transport_failed" if is_codex_transport_error(exc) else "app_server_failed",
                    item_id=job_id,
                    request={
                        "stage": stage,
                        "round": round_number,
                        "maxAttempts": max_attempts,
                        "prompt": str(paths["prompt"].relative_to(run_dir)),
                        "report": str(paths["report"].relative_to(run_dir)),
                    },
                    response={"failureContext": _codex_failure_context(exc, client=client)},
                    transcript=getattr(exc, "transcript", []) if isinstance(getattr(exc, "transcript", None), list) else [],
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise
    finally:
        await client.stop()

    source_fingerprint_after = _semantic_repair_source_artifact_fingerprint(run_dir, stage)
    changed_artifacts = _changed_semantic_repair_artifacts(source_fingerprint_before, source_fingerprint_after)
    report_status = _semantic_repair_report_status(paths["report"])
    done_updates = semantic_repair_state_updates(
        stage,
        status="done",
        round_number=round_number,
        max_attempts=max_attempts,
        error_count=len(errors),
    )
    done_updates.update(
        {
            f"review.semantic.{stage}.repair.changed_artifacts_detected": ", ".join(changed_artifacts)[:2000],
            f"review.semantic.{stage}.repair.report_status": report_status,
            f"review.semantic.{stage}.repair.source_fingerprint.after": _json_hash(source_fingerprint_after),
            f"review.semantic.{stage}.repair.source_fingerprint.after_count": str(len(source_fingerprint_after)),
            f"review.semantic.{stage}.repair.activity_marker": activity_relpath,
            f"review.semantic.{stage}.repair.pending.status": "completed",
        }
    )
    if slot:
        done_updates[f"slot.{slot}.status"] = "in_progress"
        done_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} repair round {round_number} completed; rereview pending"
    append_state_snapshot(run_dir / "state.txt", done_updates)
    completion_log_response.update(
        {
            "changedArtifacts": changed_artifacts,
            "reportStatus": report_status,
            "sourceFingerprintAfter": _semantic_repair_fingerprint_summary(source_fingerprint_after),
        }
    )
    write_app_server_debug_log(
        run_dir=run_dir,
        operation="semantic_review_producer_repair",
        status=completion_log_status,
        item_id=job_id,
        request={
            "stage": stage,
            "round": round_number,
            "maxAttempts": max_attempts,
            "prompt": str(paths["prompt"].relative_to(run_dir)),
            "report": str(paths["report"].relative_to(run_dir)),
        },
        response=completion_log_response,
        transcript=transcript,
    )


def _create_run_error_message(exc: Exception, *, max_length: int = 1800) -> str:
    raw = str(exc).strip()
    if not raw:
        raw = type(exc).__name__
    normalized = " ".join(raw.split())
    normalized_lower = normalized.lower()
    if "401 unauthorized" in normalized_lower or "missing bearer or basic authentication" in normalized_lower:
        prefix = "Codex app-server の画像生成認証が不足しています"
    elif isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or "timeouterror" in normalized_lower:
        prefix = "Codex app-server の画像生成がタイムアウトしました"
    elif "transport failure" in normalized_lower or "blocked by codex app-server transport" in normalized_lower or "transport failed" in normalized_lower:
        prefix = "Codex app-server の通信確認に失敗したため semantic QA を完了できませんでした"
    elif "semantic review failed after media generation" in normalized_lower:
        prefix = "semantic QA に失敗しました。asset/scene 画像生成は実行済みですが p680 承認には進めません"
    elif "semantic review failed" in normalized_lower:
        prefix = "semantic QA に失敗しました"
    elif "readonly database" in normalized or "failed to initialize sqlite state runtime" in normalized:
        prefix = "Codex app-server の状態DBを初期化できませんでした"
    elif "stream disconnected" in normalized or "backend-api/codex/responses" in normalized:
        prefix = "Codex app-server の画像生成通信が途中で切断されました"
    elif "did not return an image" in normalized or "savedPath" in normalized:
        prefix = "Codex app-server が画像ファイルを返しませんでした"
    elif "p680 visual quality gate failed" in normalized:
        prefix = "p680 の画像品質検証に失敗しました"
    elif "storyboard create" in normalized_lower:
        prefix = "ストーリーボード式ToC作成に失敗しました"
    else:
        return "ToC作成に失敗しました"
    message = f"{prefix}: {normalized}"
    if len(message) > max_length:
        return message[: max_length - 1] + "…"
    return message


def _create_job_failure_diagnostics(run_dir: Path) -> dict[str, Any]:
    state = parse_state_file(run_dir / "state.txt")
    generated_count = str(state.get("image_generation.generated_count") or "0")
    return {
        "runtimeStage": str(state.get("runtime.stage") or "unknown"),
        "failureStage": str(state.get("runtime.failure.stage") or "unknown"),
        "failurePhase": str(state.get("runtime.failure.phase") or "unknown"),
        "errorKind": str(state.get("runtime.failure.error_kind") or "unknown"),
        "lastProgressAt": str(state.get("runtime.failure.last_progress_at") or "unknown"),
        "imageGenerationStatus": str(state.get("image_generation.status") or "unknown"),
        "imageGenerationStarted": str(state.get("image_generation.started") or "unknown") == "true",
        "generatedCount": int(generated_count) if generated_count.isdigit() else 0,
        "blockedBy": str(state.get("image_generation.blocked_by") or "unknown"),
        "blockReason": str(state.get("image_generation.block_reason") or "unknown"),
        "p600SupervisorStatus": str(state.get("orchestration.p600.supervisor.status") or "unknown"),
        "p600SupervisorInvalidatedBy": str(state.get("orchestration.p600.supervisor.invalidated_by") or ""),
    }


async def _run_create_job(
    job_id: str,
    *,
    title: str,
    source: str,
    run_id: str,
    generate_images: bool = True,
    create_mode: str = CREATE_MODE_NORMAL,
    stop_target: str = "p680",
    target_duration_seconds: int = 300,
) -> None:
    if stop_target not in CREATE_STOP_TARGETS:
        raise ValueError("stop_target must be p650 or p680")
    if not 300 <= target_duration_seconds <= 1200:
        raise ValueError("target_duration_seconds must be between 300 and 1200")
    run_dir_for_log = safe_run_dir(run_id, ROOT)
    job_started = time.monotonic()
    try:
        async with _run_execution_leases_guard:
            lease_already_reserved = job_id in _run_execution_leases
        if not lease_already_reserved:
            await _acquire_run_execution_lease(job_id, run_dir_for_log)
        write_app_server_debug_log(
            run_dir=run_dir_for_log,
            operation="create_job_step",
            status="started",
            item_id=job_id,
            request={
                "step": "frontend_create_cli",
                "title": title,
                "sourceLength": len(source),
                "runId": run_id,
                "createMode": create_mode,
                "stopTarget": stop_target,
                "targetDurationSeconds": target_duration_seconds,
            },
        )
        if generate_images:
            await _set_create_job(job_id, {"message": f"本家ToC工程を{stop_target}まで実行中", "stopTarget": stop_target, "currentProcess": "p000"})
            await _run_toc_immersive_frontend_cli_helper(
                topic=title,
                source=source,
                run_id=run_id,
                stop_target=stop_target,
                target_duration_seconds=target_duration_seconds,
            )
        else:
            await _set_create_job(job_id, {"message": f"本家ToC工程を画像生成なしで{stop_target}まで実行中", "stopTarget": stop_target, "currentProcess": "p000"})
            await _run_toc_immersive_frontend_cli_helper(
                topic=title,
                source=source,
                run_id=run_id,
                stop_target=stop_target,
                target_duration_seconds=target_duration_seconds,
                materialize_only=True,
            )
        await _sync_process_current_process(job_id, run_id)
        if generate_images and create_mode == CREATE_MODE_SCENE_STORYBOARD:
            storyboard_started = time.monotonic()
            await _set_create_job(job_id, {"message": "cutストーリーボードを作成中"})
            storyboard_result = _materialize_scene_storyboard_video_requests(run_id)
            write_app_server_debug_log(
                run_dir=run_dir_for_log,
                operation="create_job_step",
                status="completed",
                item_id=job_id,
                request={"step": "scene_storyboard_materialization", "runId": run_id, "createMode": create_mode},
                response={**storyboard_result, "elapsedMs": int((time.monotonic() - storyboard_started) * 1000)},
            )
        write_app_server_debug_log(
            run_dir=run_dir_for_log,
            operation="create_job_step",
            status="completed",
            item_id=job_id,
            request={"step": "frontend_create_cli", "runId": run_id, "createMode": create_mode, "stopTarget": stop_target, "targetDurationSeconds": target_duration_seconds},
            response={"elapsedMs": int((time.monotonic() - job_started) * 1000)},
        )
        validation_started = time.monotonic()
        write_app_server_debug_log(
            run_dir=run_dir_for_log,
            operation="create_job_step",
            status="started",
            item_id=job_id,
            request={"step": "stop_target_validation", "runId": run_id, "createMode": create_mode, "stopTarget": stop_target},
        )
        await _set_create_job(job_id, {"message": f"{stop_target}成果物を検証中" if generate_images else "画像生成なし成果物を検証中"})
        _validate_created_run(run_id)
        if stop_target == "p650" and generate_images:
            _validate_p650_run(run_id)
        elif stop_target == "p650":
            _validate_materialized_p650_run(run_id)
        elif generate_images and create_mode == CREATE_MODE_SCENE_STORYBOARD:
            _validate_scene_storyboard_create_run(run_id, strict_visual_quality=True)
        elif generate_images:
            _validate_frontend_create_run(run_id, strict_visual_quality=True)
        else:
            _validate_materialized_p650_run(run_id)
        write_app_server_debug_log(
            run_dir=run_dir_for_log,
            operation="create_job_step",
            status="completed",
            item_id=job_id,
            request={"step": "stop_target_validation", "runId": run_id, "createMode": create_mode, "stopTarget": stop_target},
            response={"elapsedMs": int((time.monotonic() - validation_started) * 1000)},
        )
        if stop_target == "p650":
            await _set_create_job(job_id, {"status": "paused", "message": "p650で中断しました", "currentProcess": "p650"})
        else:
            await _set_create_job(job_id, {"status": "completed", "message": "作成完了", "currentProcess": "p680"})
    except Exception as exc:
        with suppress(Exception):
            await _sync_process_current_process(job_id, run_id)
        _cleanup_unscaffolded_run(run_id)
        detail = _create_run_error_message(exc)
        try:
            run_dir = safe_run_dir(run_id, ROOT)
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="create_job_step",
                status="failed",
                item_id=job_id,
                request={"runId": run_id, "title": title, "sourceLength": len(source), "createMode": create_mode, "stopTarget": stop_target, "targetDurationSeconds": target_duration_seconds},
                response={
                    "elapsedMs": int((time.monotonic() - job_started) * 1000),
                    **_create_job_failure_diagnostics(run_dir),
                },
                error=f"{type(exc).__name__}: {exc}",
            )
            if (run_dir / "state.txt").exists():
                current_state = parse_state_file(run_dir / "state.txt")
                existing_runtime_stage = str(current_state.get("runtime.stage") or "")
                preserve_runtime_stage = existing_runtime_stage in {
                    "semantic_review_blocked_transport",
                    "semantic_review_failed_before_media_generation",
                    "semantic_review_failed_after_media_generation",
                    "app_server_transport_failed",
                }
                failure_updates = {
                    "status": "FAILED",
                    "runtime.create_job.status": "failed",
                    "runtime.create_job.error_code": type(exc).__name__,
                    "runtime.create_job.stop_target": stop_target,
                    "last_error": detail,
                }
                if not preserve_runtime_stage:
                    failure_updates["runtime.stage"] = "create_run_failed"
                append_state_snapshot(
                    run_dir / "state.txt",
                    failure_updates,
                )
        except Exception:
            pass
        await _set_create_job(
            job_id,
            {
                "status": "failed",
                "error": detail,
                "errorCode": type(exc).__name__,
                "message": "作成失敗",
            },
        )
    finally:
        await _release_run_execution_lease(job_id)


@router.get("/image_gen", response_class=HTMLResponse)
async def image_gen_page() -> Response:
    index = DIST_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse(
        "<!doctype html><title>ToC Image Gen</title><body><h1>ToC Image Gen</h1>"
        "<p>Run <code>npm install && npm run build</code> in <code>server/web</code>.</p></body>"
    )


@router.get("/api/image-gen/runs")
async def api_runs() -> dict[str, Any]:
    return {"runs": list_runs(ROOT)}


@router.post("/api/image-gen/runs/create")
async def api_create_run(req: CreateRunRequest) -> dict[str, Any]:
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must not be blank")
    source = (req.source or "").strip() or title
    stop_target = req.stop_target
    target_duration_seconds = req.target_duration_seconds
    job_id = uuid.uuid4().hex
    async with _create_jobs_lock:
        running_count = sum(1 for existing in _create_jobs.values() if existing.get("status") == "running")
        if running_count >= MAX_RUNNING_CREATE_JOBS:
            raise HTTPException(status_code=429, detail="too many create jobs are running")
        if len(_create_jobs) >= MAX_CREATE_JOBS:
            terminal_job_id = next(
                (existing_id for existing_id, existing in _create_jobs.items() if existing.get("status") in {"completed", "failed"}),
                None,
            )
            if terminal_job_id:
                _create_jobs.pop(terminal_job_id)
            else:
                raise HTTPException(status_code=503, detail="too many create jobs are running")
        run_id, _run_dir = reserve_run_dir(title, root=ROOT)
        job = {
            "jobId": job_id,
            "runId": run_id,
            "path": f"output/{run_id}",
            "status": "running",
            "title": title,
            "createMode": CREATE_MODE_NORMAL,
            "targetDurationSeconds": target_duration_seconds,
            "stopTarget": stop_target,
            "stopTargetNumber": _process_number(stop_target),
            "currentProcess": "p000",
            "currentProcessNumber": 0,
            "pid": os.getpid(),
            "error": None,
            "errorCode": None,
            "message": "フォルダを作成中",
        }
        _create_jobs[job_id] = job
    try:
        await _acquire_run_execution_lease(job_id, _run_dir)
    except FileLockUnavailable as exc:
        async with _create_jobs_lock:
            _create_jobs.pop(job_id, None)
        raise HTTPException(status_code=409, detail="run create/resume is already active") from exc
    process_store_result = await asyncio.to_thread(
        _create_process_record_best_effort,
        job=job,
        title=title,
        source=source,
        stop_target=stop_target,
        generate_images=bool(req.generate_images),
    )
    if process_store_result:
        job["processStore"] = process_store_result
    write_app_server_debug_log(
        run_dir=_run_dir,
        operation="create_job_start",
        status="running",
        item_id=job_id,
        request={
            "title": title,
            "sourceLength": len(source),
            "runId": run_id,
            "maxRunningCreateJobs": MAX_RUNNING_CREATE_JOBS,
            "generateImages": bool(req.generate_images),
            "createMode": CREATE_MODE_NORMAL,
            "stopTarget": stop_target,
            "targetDurationSeconds": target_duration_seconds,
            "processStore": process_store_result,
        },
        response={"path": f"output/{run_id}"},
    )
    asyncio.create_task(
        _run_create_job(
            job_id,
            title=title,
            source=source,
            run_id=run_id,
            generate_images=bool(req.generate_images),
            create_mode=CREATE_MODE_NORMAL,
            stop_target=stop_target,
            target_duration_seconds=target_duration_seconds,
        )
    )
    return job


@router.post("/api/image-gen/runs/create/storyboard")
async def api_create_storyboard_run(req: CreateStoryboardRunRequest) -> dict[str, Any]:
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must not be blank")
    source = (req.source or "").strip() or title
    stop_target = req.stop_target
    target_duration_seconds = req.target_duration_seconds
    job_id = uuid.uuid4().hex
    async with _create_jobs_lock:
        running_count = sum(1 for existing in _create_jobs.values() if existing.get("status") == "running")
        if running_count >= MAX_RUNNING_CREATE_JOBS:
            raise HTTPException(status_code=429, detail="too many create jobs are running")
        if len(_create_jobs) >= MAX_CREATE_JOBS:
            terminal_job_id = next(
                (existing_id for existing_id, existing in _create_jobs.items() if existing.get("status") in {"completed", "failed"}),
                None,
            )
            if terminal_job_id:
                _create_jobs.pop(terminal_job_id)
            else:
                raise HTTPException(status_code=503, detail="too many create jobs are running")
        run_id, _run_dir = reserve_run_dir(f"{title}_{CREATE_MODE_SCENE_STORYBOARD_RUN_SUFFIX}", root=ROOT)
        job = {
            "jobId": job_id,
            "runId": run_id,
            "path": f"output/{run_id}",
            "status": "running",
            "title": title,
            "createMode": CREATE_MODE_SCENE_STORYBOARD,
            "targetDurationSeconds": target_duration_seconds,
            "stopTarget": stop_target,
            "stopTargetNumber": _process_number(stop_target),
            "currentProcess": "p000",
            "currentProcessNumber": 0,
            "pid": os.getpid(),
            "error": None,
            "errorCode": None,
            "message": "フォルダを作成中",
        }
        _create_jobs[job_id] = job
    try:
        await _acquire_run_execution_lease(job_id, _run_dir)
    except FileLockUnavailable as exc:
        async with _create_jobs_lock:
            _create_jobs.pop(job_id, None)
        raise HTTPException(status_code=409, detail="run create/resume is already active") from exc
    process_store_result = await asyncio.to_thread(
        _create_process_record_best_effort,
        job=job,
        title=title,
        source=source,
        stop_target=stop_target,
        generate_images=True,
    )
    if process_store_result:
        job["processStore"] = process_store_result
    write_app_server_debug_log(
        run_dir=_run_dir,
        operation="create_job_start",
        status="running",
        item_id=job_id,
        request={
            "title": title,
            "sourceLength": len(source),
            "runId": run_id,
            "maxRunningCreateJobs": MAX_RUNNING_CREATE_JOBS,
            "generateImages": True,
            "createMode": CREATE_MODE_SCENE_STORYBOARD,
            "stopTarget": stop_target,
            "targetDurationSeconds": target_duration_seconds,
            "processStore": process_store_result,
        },
        response={"path": f"output/{run_id}"},
    )
    asyncio.create_task(
        _run_create_job(
            job_id,
            title=title,
            source=source,
            run_id=run_id,
            generate_images=True,
            create_mode=CREATE_MODE_SCENE_STORYBOARD,
            stop_target=stop_target,
            target_duration_seconds=target_duration_seconds,
        )
    )
    return job


@router.get("/api/image-gen/runs/create/{job_id}")
async def api_create_run_status(job_id: str) -> dict[str, Any]:
    async with _create_jobs_lock:
        job = _create_jobs.get(job_id)
        if job:
            return dict(job)
    try:
        record = await asyncio.to_thread(process_store.get_process_run, job_id=job_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"create job not found; process DB unavailable: {exc}") from exc
    if not record:
        raise HTTPException(status_code=404, detail="create job not found")
    return record.to_api()


@router.get("/api/image-gen/runs/{run_id}/process")
async def api_run_process(run_id: str) -> dict[str, Any]:
    safe_run_dir(run_id, ROOT)
    current_process_number = _current_process_number_for_run(run_id)
    current_process = _process_label(current_process_number)
    try:
        record = await asyncio.to_thread(process_store.get_process_run, run_id=run_id)
    except Exception as exc:
        return {
            "runId": run_id,
            "currentProcess": current_process,
            "currentProcessNumber": current_process_number,
            "processStore": {"enabled": process_store.enabled(), "error": str(exc)},
        }
    if record:
        payload = record.to_api()
        payload["currentProcessFromState"] = current_process
        payload["currentProcessNumberFromState"] = current_process_number
        return payload
    return {
        "runId": run_id,
        "currentProcess": current_process,
        "currentProcessNumber": current_process_number,
        "processStore": {"enabled": False, "reason": process_store.unavailable_reason() or "record not found"},
    }


def _target_duration_seconds_for_run(run_dir: Path) -> int:
    manifest_path = run_dir / "video_manifest.md"
    if manifest_path.is_file():
        _path, _original_text, data = _read_manifest_data(run_dir)
        metadata = _dict_value(data.get("video_metadata"))
        if "target_duration_seconds" in metadata:
            return normalize_target_duration(metadata.get("target_duration_seconds"))
    state = parse_state_file(run_dir / "state.txt")
    if str(state.get("runtime.target_video_seconds") or "").strip():
        return normalize_target_duration(state["runtime.target_video_seconds"])
    return normalize_target_duration(None)


@router.post("/api/image-gen/runs/{run_id}/resume")
async def api_resume_run(run_id: str, req: ResumeRunRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(run_id, ROOT)
    current_process_number = _current_process_number_for_run(run_id)
    async with _create_jobs_lock:
        running_count = sum(1 for existing in _create_jobs.values() if existing.get("status") == "running")
        if running_count >= MAX_RUNNING_CREATE_JOBS:
            raise HTTPException(status_code=429, detail="too many create jobs are running")
    try:
        record = await asyncio.to_thread(process_store.get_process_run, run_id=run_id)
    except Exception:
        record = None
    if current_process_number == 0 and record is not None:
        current_process_number = int(record.current_process_number)
    current_process = _process_label(current_process_number)
    if current_process_number >= 680:
        raise HTTPException(status_code=409, detail="run already reached p680")
    title = record.title if record else run_id
    source = record.source if record and record.source else title
    create_mode = record.create_mode if record else CREATE_MODE_NORMAL
    try:
        target_duration_seconds = _target_duration_seconds_for_run(run_dir)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=f"run target duration is invalid: {exc}") from exc
    job_id = uuid.uuid4().hex
    try:
        await _acquire_run_execution_lease(job_id, run_dir)
    except FileLockUnavailable as exc:
        raise HTTPException(status_code=409, detail="run create/resume is already active") from exc
    job = {
        "jobId": job_id,
        "runId": run_id,
        "path": f"output/{run_id}",
        "status": "running",
        "title": title,
        "createMode": create_mode,
        "targetDurationSeconds": target_duration_seconds,
        "stopTarget": req.stop_target,
        "stopTargetNumber": _process_number(req.stop_target),
        "currentProcess": current_process,
        "currentProcessNumber": current_process_number,
        "pid": os.getpid(),
        "error": None,
        "errorCode": None,
        "message": f"{current_process}から{req.stop_target}へ再開中",
    }
    async with _create_jobs_lock:
        _create_jobs[job_id] = job
    process_store_result = await asyncio.to_thread(
        _create_process_record_best_effort,
        job=job,
        title=title,
        source=source,
        stop_target=req.stop_target,
        generate_images=True,
    )
    if process_store_result:
        job["processStore"] = process_store_result
    resume_images: dict[str, Any] | None = None
    if req.stop_target == "p680" and current_process_number >= 650:
        resume_images = await asyncio.to_thread(_delete_existing_images_for_image_resume, run_dir)
        await _set_create_job(
            job_id,
            {
                "message": f"{current_process}から{req.stop_target}へ再開中: 既存画像を照合して差分だけ再生成します",
                "metadata": {
                    "resumeFromProcessNumber": current_process_number,
                    "preservedImagesCount": resume_images.get("preservedCount", 0),
                    "resumePolicy": "hash_aware_partial",
                },
            },
        )
    write_app_server_debug_log(
        run_dir=run_dir,
        operation="create_job_resume",
        status="running",
        item_id=job_id,
        request={
            "runId": run_id,
            "fromProcess": current_process,
            "fromProcessNumber": current_process_number,
            "stopTarget": req.stop_target,
            "targetDurationSeconds": target_duration_seconds,
            "resumeImages": resume_images,
            "resumePolicy": "hash_aware_partial",
            "processStore": process_store_result,
        },
        response={"path": f"output/{run_id}"},
    )
    asyncio.create_task(
        _run_create_job(
            job_id,
            title=title,
            source=source,
            run_id=run_id,
            generate_images=True,
            create_mode=create_mode,
            stop_target=req.stop_target,
            target_duration_seconds=target_duration_seconds,
        )
    )
    return job


@router.get("/api/image-gen/requests")
async def api_requests(run_id: str, kind: str = Query(pattern="^(asset|scene)$")) -> dict[str, Any]:
    try:
        run_dir = safe_run_dir(run_id, ROOT)
    except FileNotFoundError:
        restored = restore_first_image_retention_run(run_id, root=ROOT)
        if restored is None:
            raise
        run_dir = restored
    if is_first_image_retention_restored_run(run_dir):
        restore_first_image_retention_run(run_id, root=ROOT)
    items = []
    request_items = load_request_items(run_dir, kind)
    blocked_scene_item_ids = _semantic_blocked_image_item_ids(run_dir, request_items) if kind == "scene" else set()
    for item in request_items:
        payload = item_to_api(item)
        rehydrate_retained_first_image(
            run_dir,
            root=ROOT,
            kind=kind,
            item_id=str(item.id),
        )
        persisted_candidates = list_candidate_items(run_dir, item.id)
        if str(item.id) in blocked_scene_item_ids:
            payload["generationStatus"] = "blocked"
            payload["candidates"] = persisted_candidates or [_semantic_blocked_candidate(run_dir, item)]
        else:
            payload["candidates"] = persisted_candidates
        items.append(payload)
    if not request_items and is_first_image_retention_restored_run(run_dir):
        for retention in list_first_image_retentions(root=ROOT, run_id=run_id, kind=kind):
            item_id = str(retention["itemId"])
            output = str(retention.get("destination") or "") if retention.get("storageRole") == "canonical" else None
            items.append(
                {
                    "id": item_id,
                    "kind": kind,
                    "assetType": None,
                    "tool": "codex_builtin_image",
                    "output": output,
                    "prompt": "",
                    "promptPolicyVersion": None,
                    "debugPromptSource": {
                        "retentionArchive": True,
                        "retainedAt": retention.get("retainedAt"),
                    },
                    "references": [],
                    "referenceCount": 0,
                    "executionLane": "retention_archive",
                    "generationStatus": "retained",
                    "existingImage": None,
                    "candidates": list_candidate_items(run_dir, item_id),
                }
            )
    references = [reference_to_api(option) for option in list_reference_options(run_dir)]
    return {
        "run": {"id": run_id, "path": f"output/{run_id}"},
        "kind": kind,
        "items": items,
        "references": references,
        "progress": read_run_progress(run_dir),
    }


@router.get("/api/image-gen/narration-items")
async def api_narration_items(run_id: str) -> dict[str, Any]:
    run_dir = safe_run_dir(run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            _manifest_path, _manifest_original, manifest_data = _read_manifest_data(run_dir)
            items = _manifest_narration_items(run_dir, manifest_data)
            audio_set_hash = _manifest_narration_audio_set_hash(manifest_data)
            progress = read_run_progress(run_dir)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "run": {"id": run_id, "path": f"output/{run_id}"},
        "items": items,
        "audioSetHash": audio_set_hash,
        "progress": progress,
    }


@router.get("/api/image-gen/video-items")
async def api_video_items(run_id: str) -> dict[str, Any]:
    run_dir = safe_run_dir(run_id, ROOT)
    try:
        _manifest_path, _manifest_original, manifest_data = _read_manifest_data(
            run_dir
        )
        items = _manifest_video_items(run_dir, manifest_data)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "run": {"id": run_id, "path": f"output/{run_id}"},
        "items": items,
        "references": [
            reference_to_api(option) for option in list_reference_options(run_dir)
        ],
        "progress": read_run_progress(run_dir),
    }


@router.get("/api/image-gen/progress")
async def api_progress(run_id: str) -> dict[str, Any]:
    run_dir = safe_run_dir(run_id, ROOT)
    return {
        "run": {"id": run_id, "path": f"output/{run_id}"},
        "progress": read_run_progress(run_dir),
    }


@router.post("/api/image-gen/assets/create")
async def api_create_asset(req: AssetCreateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    if app_server_disabled():
        raise HTTPException(status_code=503, detail="Codex app-server is disabled")
    item_id, request_asset_type, output = _asset_create_output(req.asset_type, req.title)
    target = _asset_create_target(req.asset_type)
    try:
        setting = read_prompt_setting(target, root=ROOT)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    item = {
        "id": item_id,
        "kind": "asset",
        "assetType": request_asset_type,
        "output": output,
        "references": [],
        "referenceCount": 0,
        "executionLane": "bootstrap_builtin",
        "title": req.title.strip(),
    }
    client = create_codex_app_server_client(cwd=ROOT)
    try:
        await _start_app_server_with_log(client, run_dir=run_dir, operation="asset_create_prompt", item_id=item_id)
        prompt = await _regenerate_prompt_with_log(
            client,
            run_dir=run_dir,
            item=item,
            target=target,
            instruction=(
                "Create a new ToC reusable asset image-generation prompt from the title and permanent instruction. "
                "The prompt must describe exactly what to create, preserve continuity with the whole run, and be ready for image generation. "
                f"Asset title: {req.title.strip()}"
            ),
            setting_content=str(setting["content"]),
            operation="asset_create_prompt",
        )
    except CodexAppServerError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        await client.stop()
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            request_path = _append_asset_generation_request(
                run_dir,
                item_id=item_id,
                asset_type=request_asset_type,
                output=output,
                prompt=prompt,
            )
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    "review.frontend.asset_create.status": "done",
                    "review.frontend.asset_create.item": item_id,
                    "artifact.asset_generation_requests": str(request_path.resolve()),
                },
            )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    created = next((item for item in load_request_items(run_dir, "asset") if item.id == item_id), None)
    return {
        "runId": req.run_id,
        "status": "completed",
        "item": item_to_api(created) if created else {**item, "prompt": prompt, "existingImage": None, "generationStatus": None, "tool": "codex_builtin_image"},
        "references": [reference_to_api(option) for option in list_reference_options(run_dir)],
        "progress": read_run_progress(run_dir),
    }


@router.post("/api/image-gen/reviews/draft")
async def api_save_frontend_review(req: FrontendReviewDraftRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            path = _write_frontend_review_draft(
                run_id=req.run_id,
                run_dir=run_dir,
                kind=req.kind,
                note=req.note,
                items=req.items,
            )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "runId": req.run_id,
        "kind": req.kind,
        "status": "saved",
        "path": path.relative_to(run_dir).as_posix(),
        "progress": read_run_progress(run_dir),
    }


@router.post("/api/image-gen/cuts/insert")
async def api_insert_cut(req: InsertCutRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            async with _serialized_run_write(run_dir, "scene_request_revision"):
                rollback_paths = (
                    run_dir / "video_manifest.md",
                    run_dir / "image_generation_requests.md",
                    run_dir / "image_generation_request_snapshot.json",
                )
                before = {
                    path: path.read_bytes() if path.is_file() else None
                    for path in rollback_paths
                }
                try:
                    result = _insert_cut_in_manifest(run_dir, req)
                    await _materialize_scene_requests(req.run_id)
                    append_state_snapshot(
                        run_dir / "state.txt",
                        {
                            "review.frontend.cut_insert.status": "done",
                            "review.frontend.cut_insert.selector": result["selector"],
                            "review.frontend.cut_insert.name": req.cut_name.strip(),
                            "artifact.video_manifest": str((run_dir / "video_manifest.md").resolve()),
                            "artifact.image_generation_requests": str((run_dir / "image_generation_requests.md").resolve()),
                            "artifact.image_generation_request_snapshot": str(
                                (run_dir / "image_generation_request_snapshot.json").resolve()
                            ),
                        },
                    )
                except (FileNotFoundError, RuntimeError, ValueError):
                    for path, original_bytes in before.items():
                        if original_bytes is None:
                            path.unlink(missing_ok=True)
                        else:
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_bytes(original_bytes)
                    raise
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    item = next((item for item in load_request_items(run_dir, "scene") if item.id == result["selector"]), None)
    return {
        "runId": req.run_id,
        "status": "completed",
        **result,
        "item": item_to_api(item) if item else None,
        "references": [reference_to_api(option) for option in list_reference_options(run_dir)],
        "progress": read_run_progress(run_dir),
    }


async def _create_video_prompts_locked(
    req: VideoPromptCreateRequest,
    *,
    run_dir: Path,
) -> dict[str, Any]:
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            _manifest_path, _original_text, manifest_data = _read_manifest_data(run_dir)
            effective_items = _effective_video_materialization_items(run_dir, req.items)
            missing_targets = [
                item.item_id
                for item in effective_items
                if _video_target_by_item_id(manifest_data, item.item_id) is None
            ]
            if missing_targets:
                raise ValueError(
                    "video manifest targets not found: " + ", ".join(missing_targets)
                )
            if req.approve_for_generation:
                for item in effective_items:
                    target = _video_target_by_item_id(manifest_data, item.item_id)
                    if target is None:
                        continue
                    target_generation = _dict_value(
                        _dict_value(target.get("cut")).get("video_generation")
                    )
                    _assert_video_auxiliary_references_supported(
                        tool=item.video_tool
                        or str(target_generation.get("tool") or "kling_3_0"),
                        references=item.video_references,
                    )
            review_path = _write_frontend_review_draft(
                run_id=req.run_id,
                run_dir=run_dir,
                kind="video",
                note=req.note,
                items=effective_items,
                state_status="saved_for_video_prompt",
                strict_video_refs=req.approve_for_generation,
            )
            design_path = _write_video_prompt_design(
                run_dir=run_dir,
                review_path=review_path,
                items=effective_items,
            )
            manifest_update = _update_manifest_video_generation(run_dir, effective_items)
            request_path = _write_video_generation_requests(
                run_dir,
                effective_items,
                replace_all=req.replace_all,
            )
            approval_updates = _video_prompt_approval_updates(
                run_dir,
                effective_items,
                approved=False,
            )
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    "status": "P830",
                    "runtime.stage": (
                        "video_prompts_ready_for_semantic_review"
                        if req.approve_for_generation
                        else "video_prompts_ready_for_review"
                    ),
                    "slot.p810.status": "done",
                    "slot.p810.note": "frontend image review saved before video prompt creation",
                    "slot.p820.status": "pending",
                    "slot.p820.note": (
                        "materialized video prompts await contextless semantic review"
                        if req.approve_for_generation
                        else "video prompts created; semantic review has not run"
                    ),
                    "slot.p830.status": "in_progress",
                    "slot.p830.note": "video generation requests are materialized; semantic review remains",
                    "stage.video_generation.status": "in_progress",
                    "review.video_prompt.status": "pending",
                    "gate.video_prompt_review": "required",
                    "artifact.video_generation_requests": str(request_path.resolve()),
                    "review.frontend.video_prompt.design": design_path.relative_to(run_dir).as_posix(),
                    **approval_updates,
                },
            )
        if req.approve_for_generation:
            await _run_video_prompt_semantic_review_before_approval(
                run_dir=run_dir,
            )
            async with _serialized_run_write(run_dir, "run_artifacts"):
                _assert_video_prompt_semantic_review_is_current(run_dir)
                _assert_video_materialization_current_for_approval(
                    run_dir,
                    effective_items,
                )
                approval_updates = _video_prompt_approval_updates(
                    run_dir,
                    effective_items,
                    approved=True,
                )
                materialization_complete = (
                    _video_prompt_stage_materialization_complete(run_dir)
                )
                approval_updates.update(
                    _stale_video_prompt_approval_updates(
                        run_dir,
                        pending_updates=approval_updates,
                    )
                )
                stage_approval_complete = (
                    materialization_complete
                    and _video_prompt_stage_approval_complete(
                        run_dir,
                        effective_items,
                        approval_updates=approval_updates,
                    )
                )
                review_status = (
                    "approved_for_generation"
                    if stage_approval_complete
                    else "partially_approved_for_generation"
                )
                human_approval_is_only_remaining_gate = (
                    materialization_complete and not stage_approval_complete
                )
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        "runtime.stage": "video_prompt_items_approved_for_generation",
                        "slot.p820.status": "done",
                        "slot.p820.note": "contextless video-motion semantic review passed for the exact materialized payload",
                        "slot.p830.status": (
                            "done"
                            if stage_approval_complete
                            else (
                                "awaiting_approval"
                                if human_approval_is_only_remaining_gate
                                else "in_progress"
                            )
                        ),
                        "slot.p830.note": (
                            "all materialized provider requests approved"
                            if stage_approval_complete
                            else (
                                "all provider requests are current; remaining items require only human approval"
                                if human_approval_is_only_remaining_gate
                                else "selected provider requests approved; remaining items require materialization or semantic review"
                            )
                        ),
                        "stage.video_generation.status": (
                            "awaiting_approval"
                            if human_approval_is_only_remaining_gate
                            else "in_progress"
                        ),
                        "review.video_prompt.status": review_status,
                        "gate.video_prompt_review": "required",
                        **approval_updates,
                    },
                )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "runId": req.run_id,
        "status": "completed",
        "reviewPath": review_path.relative_to(run_dir).as_posix(),
        "designPath": design_path.relative_to(run_dir).as_posix(),
        "videoRequestsPath": request_path.relative_to(run_dir).as_posix(),
        "updated": manifest_update["updated"],
        "missing": manifest_update["missing"],
        "durationSecondsByItem": {
            item.item_id: item.video_duration_seconds for item in effective_items
        },
        "approvedForGeneration": req.approve_for_generation,
        "progress": read_run_progress(run_dir),
    }


@router.post("/api/image-gen/video-prompts/create")
async def api_create_video_prompts(req: VideoPromptCreateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    # The semantic report is written to one canonical run-level artifact.  Keep
    # materialization, review, and approval in the same revision transaction so
    # another request cannot replace the manifest while the report is running.
    async with _serialized_run_write(run_dir, "video_prompt_review_revision"):
        return await _create_video_prompts_locked(req, run_dir=run_dir)


@router.get("/api/image-gen/prompt-settings")
async def api_prompt_settings(target: str = Query(pattern="^(character|item|location|scene)$")) -> dict[str, Any]:
    try:
        setting = read_prompt_setting(target, root=ROOT)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"targets": prompt_setting_targets(), **setting}


@router.post("/api/image-gen/prompt-settings")
async def api_write_prompt_settings(req: PromptSettingRequest) -> dict[str, Any]:
    if "<!-- image-gen-setting:" in req.content:
        raise HTTPException(status_code=400, detail="prompt setting content must not include image-gen setting markers")
    try:
        setting = write_prompt_setting(req.target, req.content, root=ROOT)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"targets": prompt_setting_targets(), **setting}


@router.get("/api/image-gen/file")
async def api_file(run_id: str, path: str) -> FileResponse:
    run_dir = safe_run_dir(run_id, ROOT)
    target = resolve_run_relative(run_dir, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    if target.suffix.lower() not in IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="only image files can be served")
    return FileResponse(target)


@router.get("/api/image-gen/video-file")
async def api_video_file(run_id: str, path: str) -> FileResponse:
    run_dir = safe_run_dir(run_id, ROOT)
    try:
        _validate_run_relative_video_path(run_dir, path, must_exist=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    target = resolve_run_relative(run_dir, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(target, media_type="video/mp4")


@router.get("/api/image-gen/audio-file")
async def api_audio_file(run_id: str, path: str) -> FileResponse:
    run_dir = safe_run_dir(run_id, ROOT)
    try:
        _validate_run_relative_audio_path(run_dir, path, must_exist=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    target = resolve_run_relative(run_dir, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    media_type = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
    }.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(target, media_type=media_type)


@router.get("/api/image-gen/candidates")
async def api_candidates(
    run_id: str,
    item_id: str = Query(min_length=1, max_length=200),
    kind: str | None = None,
) -> dict[str, Any]:
    try:
        run_dir = safe_run_dir(run_id, ROOT)
    except FileNotFoundError:
        restored = restore_first_image_retention_run(run_id, root=ROOT)
        if restored is None:
            raise
        run_dir = restored
    if is_first_image_retention_restored_run(run_dir):
        restore_first_image_retention_run(run_id, root=ROOT)
        archived = list_first_image_retentions(root=ROOT, run_id=run_id, kind=kind, item_id=item_id) if kind in {"asset", "scene"} else list_first_image_retentions(root=ROOT, run_id=run_id, item_id=item_id)
        if not archived:
            return {"itemId": item_id, "candidates": []}
        return {"itemId": item_id, "candidates": list_candidate_items(run_dir, item_id)}
    kinds = [kind] if kind in {"asset", "scene"} else ["scene", "asset"]
    for request_kind in kinds:
        if not any(item.id == item_id for item in load_request_items(run_dir, request_kind)):
            continue
        restored = rehydrate_retained_first_image(
            run_dir,
            root=ROOT,
            kind=request_kind,
            item_id=item_id,
        )
        if restored is not None:
            break
    return {"itemId": item_id, "candidates": list_candidate_items(run_dir, item_id)}


@router.post("/api/image-gen/narration-drafts/create")
async def api_create_narration_drafts(req: NarrationDraftCreateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            result = _create_narration_drafts_in_manifest(run_dir, replace=req.replace)
            authoring_workspace = await asyncio.to_thread(_materialize_narration_authoring_workspace, run_dir)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "runId": req.run_id,
        "status": "completed",
        **result,
        "authoringWorkspace": authoring_workspace,
        "progress": read_run_progress(run_dir),
    }


@router.post("/api/image-gen/narration-silent-ok")
async def api_narration_silent_ok(req: NarrationSilentOkRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            transaction = _capture_file_transaction(
                [
                    run_dir / "script.md",
                    run_dir / "video_manifest.md",
                    run_dir / "state.txt",
                    run_dir / "run_status.json",
                    run_dir / "p000_index.md",
                ]
            )
            try:
                _save_frontend_narration_text(
                    run_dir,
                    NarrationTextSaveRequest(
                        run_id=req.run_id,
                        item_id=req.item_id,
                        text="",
                        tts_text="",
                        tool="silent",
                        authoring_status="silent",
                        expected_revision=req.expected_revision,
                    ),
                )
                result = _narration_silent_ok(
                    run_dir,
                    item_id=req.item_id,
                    reason=req.reason,
                )
                _append_narration_review_approved_if_ready(run_dir)
                _manifest_path, _manifest_original, latest_data = _read_manifest_data(run_dir)
                result["audioSetHash"] = _manifest_narration_audio_set_hash(latest_data)
                progress = read_run_progress(run_dir)
            except Exception:
                _restore_file_transaction(transaction)
                raise
    except NarrationRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "runId": req.run_id,
        **result,
        "progress": progress,
    }


@router.post("/api/image-gen/narration-text/save")
async def api_narration_text_save(req: NarrationTextSaveRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            item = _save_frontend_narration_text(run_dir, req)
            _manifest_path, _manifest_original, latest_data = _read_manifest_data(run_dir)
            audio_set_hash = _manifest_narration_audio_set_hash(latest_data)
            progress = read_run_progress(run_dir)
    except NarrationRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "runId": req.run_id,
        "status": "saved",
        "item": item,
        "audioSetHash": audio_set_hash,
        "progress": progress,
    }


@router.post("/api/image-gen/narration-generate")
async def api_narration_generate(req: NarrationGenerateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    item = NarrationGenerateItem.model_validate(req.model_dump(exclude={"run_id"}))
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            prepared = _prepare_manifest_narration_generation(run_dir, [item])
    except NarrationRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    provider_result = await _generate_narration_one(run_dir, prepared[0]["request"])
    async with _serialized_run_write(run_dir, "run_artifacts"):
        transaction = _capture_file_transaction(
            [
                run_dir / "video_manifest.md",
                run_dir / "state.txt",
                run_dir / "run_status.json",
                run_dir / "p000_index.md",
            ]
        )
        try:
            result = _record_manifest_narration_generation_results(
                run_dir,
                prepared,
                [provider_result],
            )[0]
            _append_narration_preview_state(
                run_dir,
                runtime_stage=(
                    "narration_audio_candidate_ready"
                    if result.get("status") == "candidate"
                    else "narration_generation_stale_or_failed"
                ),
                note=(
                    "generated alternate audio candidate; current approval remains unchanged"
                    if result.get("status") == "candidate"
                    else "alternate audio candidate failed or became stale; current approval remains unchanged"
                ),
            )
        except Exception:
            _restore_file_transaction(transaction)
            raise
        progress = read_run_progress(run_dir)
    return {
        "runId": req.run_id,
        "status": result.get("status"),
        "updated": [str(prepared[0]["selector"])],
        "audioReadyUpdated": [],
        "durationUpdated": [],
        "durationReady": False,
        "item": result,
        "progress": progress,
    }


@router.post("/api/image-gen/narration-generate-bulk")
async def api_narration_generate_bulk(req: BulkNarrationGenerateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            prepared = _prepare_manifest_narration_generation(run_dir, req.items)
    except NarrationRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    semaphore = asyncio.Semaphore(req.concurrency)

    async def guarded(entry: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await _generate_narration_one(run_dir, entry["request"])

    provider_results = await asyncio.gather(*(guarded(entry) for entry in prepared))
    async with _serialized_run_write(run_dir, "run_artifacts"):
        transaction = _capture_file_transaction(
            [
                run_dir / "video_manifest.md",
                run_dir / "state.txt",
                run_dir / "run_status.json",
                run_dir / "p000_index.md",
            ]
        )
        try:
            results = _record_manifest_narration_generation_results(
                run_dir,
                prepared,
                provider_results,
            )
            failed = [result for result in results if result.get("status") == "failed"]
            _append_narration_preview_state(
                run_dir,
                runtime_stage=(
                    "narration_audio_candidates_ready"
                    if not failed
                    else "narration_generation_partial_failure"
                ),
                note=(
                    f"generated {len(results) - len(failed)}/{len(results)} alternate narration candidates; "
                    "current approvals remain unchanged"
                ),
            )
        except Exception:
            _restore_file_transaction(transaction)
            raise
        progress = read_run_progress(run_dir)
    return {
        "runId": req.run_id,
        "status": "completed" if not failed else "partial_failure",
        "updated": [str(entry["selector"]) for entry in prepared],
        "audioReadyUpdated": [],
        "durationUpdated": [],
        "durationReady": False,
        "results": results,
        "progress": progress,
    }


@router.post("/api/image-gen/narration-audio/approve")
async def api_narration_audio_approve(req: NarrationAudioApproveRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            result = _approve_manifest_narration_audio(
                run_dir,
                item_id=req.item_id,
                candidate_id=req.candidate_id,
                expected_revision=req.expected_revision,
                expected_tts_hash=req.expected_tts_hash,
                note=req.note,
            )
            progress = read_run_progress(run_dir)
    except NarrationRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"runId": req.run_id, "status": "approved", **result, "progress": progress}


@router.post("/api/image-gen/narration-review/run")
async def api_narration_review_run(req: NarrationReviewRunRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    review_run_id = uuid.uuid4().hex
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run-p720-narration-l3.py"),
        "--run-dir",
        str(run_dir),
    ]
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            command,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=500, detail=f"p720 narration review failed: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "p720 narration review failed"
        raise HTTPException(status_code=409, detail=detail)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            _manifest_path, _original_text, review_snapshot = _read_manifest_data(run_dir)
            expected_text_set_hash = narration_text_set_hash(review_snapshot)
            expected_input_hash = str(
                build_narration_semantic_review_pack(
                    review_snapshot,
                    text_set_hash=expected_text_set_hash,
                )["semantic_review_input_hash"]
            )
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    "runtime.stage": "narration_semantic_critics_running",
                    "runtime.narration.phase": "review",
                    "slot.p720.status": "in_progress",
                    "slot.p720.note": "five independent full-run semantic critics are reviewing one frozen text set",
                    "review.narration.semantic_critics.status": "in_progress",
                    "review.narration.semantic_critics.text_set_hash": expected_text_set_hash,
                    "review.narration.semantic_critics.input_hash": expected_input_hash,
                    "review.narration.semantic_critics.review_run_id": review_run_id,
                    "gate.narration_review": "required",
                },
            )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    semantic_review = await _run_narration_semantic_review(
        run_dir,
        review_snapshot,
        expected_text_set_hash=expected_text_set_hash,
        expected_input_hash=expected_input_hash,
    )
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            manifest_path, original_text, data = _read_manifest_data(run_dir)
            active_review_run_id = str(
                parse_state_file(run_dir / "state.txt").get(
                    "review.narration.semantic_critics.review_run_id"
                )
                or ""
            )
            if active_review_run_id != review_run_id:
                raise NarrationRevisionConflict(
                    "a newer p720 semantic review superseded this result"
                )
            current_text_set_hash = narration_text_set_hash(data)
            current_input_hash = str(
                build_narration_semantic_review_pack(
                    data,
                    text_set_hash=current_text_set_hash,
                )["semantic_review_input_hash"]
            )
            if (
                current_text_set_hash != expected_text_set_hash
                or current_input_hash != expected_input_hash
            ):
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        "runtime.stage": "narration_semantic_critics_stale",
                        "slot.p720.status": "in_progress",
                        "slot.p720.note": "narration or critic-visible context changed during semantic review; rerun p720",
                        "review.narration.semantic_critics.status": "stale",
                        "review.narration.semantic_critics.text_set_hash": expected_text_set_hash,
                        "review.narration.semantic_critics.input_hash": expected_input_hash,
                    },
                )
                raise NarrationRevisionConflict(
                    "narration or critic-visible context changed while semantic critics were running; rerun p720"
                )
            if str(semantic_review.get("narration_text_set_hash") or "") != current_text_set_hash:
                raise NarrationRevisionConflict(
                    "semantic critic result is not bound to the current narration text set"
                )
            if str(semantic_review.get("semantic_review_input_hash") or "") != current_input_hash:
                raise NarrationRevisionConflict(
                    "semantic critic result is not bound to the current exact review pack"
                )
            validate_narration_semantic_aggregate(
                semantic_review,
                expected_text_set_hash=current_text_set_hash,
                expected_semantic_review_input_hash=current_input_hash,
            )
            semantic_report_path, semantic_json_path, semantic_artifact_writes = (
                _prepare_narration_semantic_review_artifacts(run_dir, semantic_review)
            )
            workflow = _dict_value(data.get("narration_workflow"))
            workflow["schema_version"] = "narration_run_workflow_v1"
            workflow["semantic_critic_review"] = _semantic_review_manifest_record(
                semantic_review,
                report_path=semantic_report_path,
                json_path=semantic_json_path,
            )
            data["narration_workflow"] = workflow
            review_blockers = _narration_review_blockers(
                data,
                semantic_artifact=semantic_review,
            )
            review_status = "passed" if not review_blockers else "changes_requested"
            if review_status != "passed":
                _invalidate_narration_run_approval(
                    data,
                    reason="p720 deterministic or semantic narration review requested changes",
                )

            transaction_paths = [
                manifest_path,
                run_dir / "state.txt",
                run_dir / "run_status.json",
                run_dir / "p000_index.md",
                *semantic_artifact_writes,
            ]
            before_transaction = {
                path: path.read_bytes() if path.is_file() else None
                for path in transaction_paths
            }
            state_updates = {
                "runtime.stage": (
                    "narration_text_semantic_review_passed"
                    if review_status == "passed"
                    else "narration_text_semantic_review_changes_requested"
                ),
                "runtime.narration.phase": "review",
                "slot.p720.status": "done" if review_status == "passed" else "blocked",
                "slot.p720.note": (
                    "deterministic checks and five independent full-run semantic critics passed"
                    if review_status == "passed"
                    else "p720 full-run narration review has unresolved findings"
                ),
                "review.narration.status": "approved" if review_status == "passed" else "changes_requested",
                "review.narration.semantic_critics.status": str(semantic_review.get("status") or "changes_requested"),
                "review.narration.semantic_critics.text_set_hash": current_text_set_hash,
                "review.narration.semantic_critics.input_hash": current_input_hash,
                "review.narration.semantic_critics.review_run_id": review_run_id,
                "artifact.narration_semantic_review": semantic_report_path,
                "artifact.narration_semantic_review_json": semantic_json_path,
                "gate.narration_review": "required",
            }
            if review_status != "passed":
                state_updates.update(
                    {
                        "status": "P720",
                        "slot.p730.status": "blocked",
                        "slot.p740.status": "blocked",
                        "slot.p750.status": "blocked",
                        "stage.narration.status": "in_progress",
                    }
                )
            _backup_run_file(run_dir, "video_manifest.md", label="before_narration_semantic_review")
            try:
                for path, content in semantic_artifact_writes.items():
                    _atomic_write_text(path, content)
                _write_manifest_data(manifest_path, original_text, data)
                append_state_snapshot(run_dir / "state.txt", state_updates)
            except Exception:
                for path, previous_content in before_transaction.items():
                    if previous_content is None:
                        path.unlink(missing_ok=True)
                    else:
                        _atomic_write_bytes(path, previous_content)
                raise
    except NarrationRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    arc_review = _dict_value(_dict_value(data.get("narration_workflow")).get("arc_review"))
    arc_findings = [str(value) for value in _list_value(arc_review.get("findings"))]
    cut_findings: list[dict[str, Any]] = []
    for target in _manifest_scene_targets(data):
        narration = _dict_value(_dict_value(_dict_value(target["cut"]).get("audio")).get("narration"))
        review = _dict_value(narration.get("review"))
        keys = [str(value) for value in _list_value(review.get("agent_review_reason_keys")) if str(value)]
        messages = [
            str(value)
            for value in _list_value(review.get("agent_review_reason_messages"))
            if str(value)
        ]
        if review.get("agent_review_ok") is not True and (keys or messages):
            cut_findings.append(
                {
                    "itemId": str(target["selector"]),
                    "reasonKeys": keys,
                    "messages": messages,
                }
            )
    combined_findings = list(arc_findings)
    for finding in cut_findings:
        messages = finding["messages"] or finding["reasonKeys"]
        combined_findings.extend(f"{finding['itemId']}: {message}" for message in messages)
    semantic_findings = deepcopy(_list_value(semantic_review.get("findings")))
    combined_findings.extend(
        f"{str(finding.get('critic_label') or finding.get('critic_id') or 'semantic critic')}: "
        f"{str(finding.get('message') or '')}"
        for finding in semantic_findings
        if isinstance(finding, dict)
    )
    return {
        "runId": req.run_id,
        "status": review_status,
        "findings": combined_findings,
        "arcFindings": arc_findings,
        "cutFindings": cut_findings,
        "semanticFindings": semantic_findings,
        "semanticCritics": deepcopy(_list_value(semantic_review.get("critics"))),
        "narrationTextSetHash": current_text_set_hash,
        "semanticReviewInputHash": current_input_hash,
        "report": semantic_report_path,
        "arcReport": str(arc_review.get("report") or "narration_text_review.md"),
        "semanticReport": semantic_report_path,
        "stdout": result.stdout.strip(),
        "progress": read_run_progress(run_dir),
    }


@router.post("/api/image-gen/narration-review/approve")
async def api_narration_review_approve(req: NarrationRunApproveRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            result = _approve_narration_full_run(
                run_dir,
                note=req.note,
                expected_audio_set_hash=req.expected_audio_set_hash,
                timeline=req.timeline,
                listen_evidence=req.listen_evidence,
            )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"runId": req.run_id, **result, "progress": read_run_progress(run_dir)}


@router.post("/api/image-gen/video-generate")
async def api_video_generate(req: VideoGenerateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    item = VideoGenerateItem.model_validate(req.model_dump(exclude={"run_id"}))
    _validate_video_request_reference_paths(run_dir, item)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            _require_narration_ready_for_video(run_dir)
            item = _materialized_video_generate_item(run_dir=run_dir, request=item)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _validate_video_request_reference_paths(run_dir, item)
    return await _generate_video_candidates(run_dir, item)


@router.post("/api/image-gen/video-generate-bulk")
async def api_video_generate_bulk(req: BulkVideoGenerateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    for item in req.items:
        _validate_video_request_reference_paths(run_dir, item)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            _require_narration_ready_for_video(run_dir)
            items = [
                _materialized_video_generate_item(run_dir=run_dir, request=item)
                for item in req.items
            ]
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    for item in items:
        _validate_video_request_reference_paths(run_dir, item)
    total_candidates = sum(item.candidate_count for item in items)
    if total_candidates > 96:
        raise HTTPException(status_code=400, detail="bulk video generation is limited to 96 total candidates")
    semaphore = asyncio.Semaphore(req.concurrency)

    async def guarded(item: VideoGenerateItem) -> dict[str, Any]:
        async with semaphore:
            return await _generate_video_candidates(run_dir, item)

    results = await asyncio.gather(*(guarded(item) for item in items), return_exceptions=True)
    payload = []
    for item, result in zip(items, results, strict=False):
        if isinstance(result, Exception):
            payload.append({"itemId": item.item_id, "error": str(result), "candidates": []})
        else:
            payload.append(result)
    return {"runId": req.run_id, "results": payload}


@router.post("/api/image-gen/render-inputs/freeze")
async def api_render_inputs_freeze(req: RenderFreezeRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            result = _freeze_render_inputs(run_dir, req)
    except NarrationRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {**result, "runId": req.run_id, "progress": read_run_progress(run_dir)}


@router.post("/api/image-gen/final-render")
async def api_final_render(req: FinalRenderRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            freeze_result = _freeze_render_inputs(run_dir, req, snapshot_id=_now_stamp())
        result = await _run_final_render(run_dir, req, freeze_result)
    except NarrationRevisionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {**result, "runId": req.run_id, "progress": read_run_progress(run_dir)}


def _bulk_generation_job_dir(run_dir: Path) -> Path:
    return run_dir / "logs" / "image_generation_jobs"


def _bulk_generation_job_path(run_dir: Path, job_id: str) -> Path:
    if re.fullmatch(r"[0-9a-f]{32}", job_id) is None:
        raise ValueError("invalid bulk generation job id")
    return _bulk_generation_job_dir(run_dir) / f"{job_id}.json"


def _persist_bulk_generation_job(job: dict[str, Any]) -> None:
    run_dir = safe_run_dir(str(job.get("runId") or ""), ROOT)
    path = _bulk_generation_job_path(run_dir, str(job.get("jobId") or ""))
    _atomic_write_text(path, json.dumps(job, ensure_ascii=False, indent=2) + "\n")


def _load_bulk_generation_job_path(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schemaVersion") != BULK_GENERATION_JOB_SCHEMA:
        return None
    return payload


def _bulk_generation_job_files(run_dir: Path) -> list[Path]:
    directory = _bulk_generation_job_dir(run_dir)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime_ns, reverse=True)


def _refresh_bulk_generation_job_counts(job: dict[str, Any]) -> None:
    results = job.get("results") or []
    for result in results:
        candidates = result.get("candidates") or []
        statuses = [str(candidate.get("status") or "queued") for candidate in candidates]
        if any(status == "running" for status in statuses):
            result["status"] = "running"
        elif any(status == "queued" for status in statuses):
            result["status"] = "queued"
        elif statuses and all(status == "blocked" for status in statuses):
            result["status"] = "blocked"
        elif any(status in {"failed", "blocked"} for status in statuses):
            result["status"] = "failed"
        elif any(candidate.get("path") for candidate in candidates):
            result["status"] = "completed"
            result.pop("error", None)
        else:
            result["status"] = "failed"
        if result.get("status") in {"failed", "blocked"}:
            errors = [str(candidate.get("error") or "").strip() for candidate in candidates]
            result["error"] = next((error for error in errors if error), "generation failed")

    item_statuses = [str(result.get("status") or "queued") for result in results]
    job["totalCount"] = len(results)
    job["completedCount"] = sum(status == "completed" for status in item_statuses)
    job["failedCount"] = sum(status in {"failed", "blocked"} for status in item_statuses)
    job["runningCount"] = sum(status == "running" for status in item_statuses)
    job["queuedCount"] = sum(status == "queued" for status in item_statuses)


def _reconcile_bulk_generation_job_candidates(job: dict[str, Any], run_dir: Path) -> None:
    """Merge validated run-local files without replacing transient job status."""
    for result in job.get("results") or []:
        item_id = str(result.get("itemId") or "").strip()
        if not item_id:
            continue
        disk_candidates = list_candidate_items(run_dir, item_id)
        candidates = result.setdefault("candidates", [])
        by_index = {
            int(candidate.get("index") or 0): candidate
            for candidate in candidates
            if isinstance(candidate, dict)
        }
        for disk_candidate in disk_candidates:
            index = int(disk_candidate.get("index") or 0)
            current = by_index.get(index)
            if current is None:
                current = dict(disk_candidate)
                candidates.append(current)
                by_index[index] = current
                continue
            if not current.get("path"):
                current["path"] = disk_candidate.get("path")
            if disk_candidate.get("mtimeMs") is not None:
                current["mtimeMs"] = disk_candidate["mtimeMs"]
        candidates.sort(key=lambda candidate: int(candidate.get("index") or 0))


def _patch_bulk_generation_candidate(
    job: dict[str, Any],
    *,
    item_id: str,
    candidate_index: int,
    patch: dict[str, Any],
) -> None:
    for result in job.get("results") or []:
        if result.get("itemId") != item_id:
            continue
        for candidate in result.get("candidates") or []:
            request_index = candidate.get("requestIndex", candidate.get("index"))
            if int(request_index or 0) == candidate_index:
                candidate.update(patch)
                return
    raise KeyError(f"bulk generation candidate not found: {item_id}:{candidate_index}")


def _patch_bulk_generation_group(job: dict[str, Any], *, group_index: int, status: str) -> None:
    for group in job.get("groups") or []:
        if int(group.get("index") or 0) == group_index:
            group["status"] = status
            return


def _interrupt_bulk_generation_job(job: dict[str, Any], message: str) -> None:
    for result in job.get("results") or []:
        for candidate in result.get("candidates") or []:
            if candidate.get("status") in {"queued", "running"}:
                candidate.update({"status": "failed", "error": message})
    job.update(
        {
            "status": "interrupted",
            "completedAt": now_iso(),
            "error": message,
        }
    )


def _fail_bulk_generation_job(job: dict[str, Any], message: str) -> None:
    for result in job.get("results") or []:
        for candidate in result.get("candidates") or []:
            if candidate.get("status") in {"queued", "running"}:
                candidate.update({"status": "failed", "error": message})
    job.update(
        {
            "status": "failed",
            "completedAt": now_iso(),
            "error": message,
        }
    )


async def _mutate_bulk_generation_job(
    job_id: str,
    mutation: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    async with _bulk_generation_jobs_lock:
        job = _bulk_generation_jobs.get(job_id)
        if job is None:
            raise KeyError(f"bulk generation job not found: {job_id}")
        mutation(job)
        run_dir = safe_run_dir(str(job.get("runId") or ""), ROOT)
        _reconcile_bulk_generation_job_candidates(job, run_dir)
        _refresh_bulk_generation_job_counts(job)
        job["updatedAt"] = now_iso()
        _persist_bulk_generation_job(job)
        return deepcopy(job)


def _prepare_bulk_generation_plan(
    *,
    run_dir: Path,
    req: BulkGenerateRequest,
) -> list[list[_BulkGenerationPlanItem]]:
    canonical_item_list = load_request_items(run_dir, req.kind)
    canonical_items = {item.id: item for item in canonical_item_list}
    if not canonical_items:
        raise ValueError(f"{req.kind} request file has no items")
    canonical_output_paths = {
        _run_relative_key(run_dir, str(item.output))
        for item in canonical_item_list
        if item.output
    }
    seen: set[str] = set()
    plan_items: list[_BulkGenerationPlanItem] = []
    for submitted in req.items:
        if submitted.item_id in seen:
            raise ValueError(f"duplicate bulk generation item: {submitted.item_id}")
        seen.add(submitted.item_id)
        canonical = canonical_items.get(submitted.item_id)
        if canonical is None:
            raise ValueError(f"bulk generation item is not in canonical request: {submitted.item_id}")
        if not canonical.output:
            raise ValueError(f"bulk generation item has no output: {submitted.item_id}")
        # Older frontend builds omitted every reference when a deferred producer
        # did not exist yet. Preserve the canonical inputs for that payload, but
        # keep explicit reference edits independent from immutable canonical DAG
        # edges so adding one unrelated reference cannot collapse generation
        # groups or bypass a failed producer.
        references = list(submitted.references) or list(canonical.references)
        dependency_references = list(
            dict.fromkeys(
                ref
                for ref in canonical.references
                if _run_relative_key(run_dir, str(ref)) in canonical_output_paths
            )
        )
        normalized = submitted.model_copy(
            update={
                "run_id": req.run_id,
                "kind": req.kind,
                "references": references,
            }
        )
        plan_items.append(
            _BulkGenerationPlanItem(
                id=submitted.item_id,
                output=str(canonical.output),
                references=references,
                dependency_references=dependency_references,
                request=normalized,
            )
        )
    groups = _build_generation_groups(plan_items, run_dir=run_dir, kind=req.kind)
    _validate_generation_groups(groups, run_dir=run_dir, kind=req.kind)
    return groups


def _bulk_generation_fingerprint(
    *,
    run_id: str,
    kind: str,
    groups: list[list[_BulkGenerationPlanItem]],
) -> str:
    payload = {
        "runId": run_id,
        "kind": kind,
        "groups": [
            [
                {
                    "itemId": item.id,
                    "output": item.output,
                    "references": item.references,
                    "dependencyReferences": item.dependency_references,
                    "prompt": item.request.prompt,
                    "promptPolicyVersion": item.request.prompt_policy_version,
                    "debugPromptSource": item.request.debug_prompt_source,
                    "candidateCount": item.request.candidate_count,
                }
                for item in group
            ]
            for group in groups
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _initial_bulk_generation_job(
    *,
    req: BulkGenerateRequest,
    groups: list[list[_BulkGenerationPlanItem]],
    fingerprint: str,
) -> dict[str, Any]:
    job_id = uuid.uuid4().hex
    created_at = now_iso()
    group_index_by_item = {
        item.id: group_index
        for group_index, group in enumerate(groups, start=1)
        for item in group
    }
    plan_by_id = {item.id: item for group in groups for item in group}
    results = []
    for submitted in req.items:
        plan = plan_by_id[submitted.item_id]
        results.append(
            {
                "itemId": submitted.item_id,
                "status": "queued",
                "groupIndex": group_index_by_item[submitted.item_id],
                "output": plan.output,
                "references": list(plan.references),
                "dependencyReferences": list(plan.dependency_references),
                "candidates": [
                    {"index": index, "requestIndex": index, "status": "queued", "path": None}
                    for index in range(1, submitted.candidate_count + 1)
                ],
            }
        )
    job: dict[str, Any] = {
        "schemaVersion": BULK_GENERATION_JOB_SCHEMA,
        "jobId": job_id,
        "runId": req.run_id,
        "kind": req.kind,
        "status": "queued",
        "fingerprint": fingerprint,
        "serverInstanceId": _BULK_GENERATION_SERVER_INSTANCE_ID,
        "pid": os.getpid(),
        "groupCount": len(groups),
        "currentGroup": None,
        "groups": [
            {
                "index": index,
                "status": "queued",
                "itemIds": [item.id for item in group],
            }
            for index, group in enumerate(groups, start=1)
        ],
        "results": results,
        "createdAt": created_at,
        "startedAt": None,
        "updatedAt": created_at,
        "completedAt": None,
        "error": None,
    }
    _refresh_bulk_generation_job_counts(job)
    return job


def _loaded_bulk_generation_job(job: dict[str, Any]) -> dict[str, Any]:
    try:
        run_dir = safe_run_dir(str(job.get("runId") or ""), ROOT)
    except (FileNotFoundError, ValueError):
        run_dir = None
    if run_dir is not None:
        _reconcile_bulk_generation_job_candidates(job, run_dir)
    if (
        job.get("status") in {"queued", "running"}
        and job.get("serverInstanceId") != _BULK_GENERATION_SERVER_INSTANCE_ID
    ):
        _interrupt_bulk_generation_job(
            job,
            "server restarted while image generation was running; start a new job to resume safely",
        )
        _refresh_bulk_generation_job_counts(job)
        job["updatedAt"] = job["completedAt"]
        _persist_bulk_generation_job(job)
    return job


def _bulk_generation_job_from_disk(job_id: str) -> dict[str, Any] | None:
    if re.fullmatch(r"[0-9a-f]{32}", job_id) is None:
        raise ValueError("invalid bulk generation job id")
    for path in output_root(ROOT).glob(f"*/logs/image_generation_jobs/{job_id}.json"):
        job = _load_bulk_generation_job_path(path)
        if job is not None:
            return _loaded_bulk_generation_job(job)
    return None


async def _run_bulk_generation_job(
    *,
    job_id: str,
    run_dir: Path,
    groups: list[list[_BulkGenerationPlanItem]],
    requested_concurrency: int,
) -> None:
    plan_by_id = {item.id: item for group in groups for item in group}
    output_to_item_id = {
        _run_relative_key(run_dir, item.output): item.id
        for group in groups
        for item in group
    }
    successful_candidates: dict[str, dict[int, str]] = {
        item_id: {} for item_id in plan_by_id
    }
    effective_parallelism = max(
        1,
        min(
            int(requested_concurrency),
            int(_effective_image_generation_parallelism()),
        ),
    )
    semaphore = asyncio.Semaphore(effective_parallelism)

    try:
        await _mutate_bulk_generation_job(
            job_id,
            lambda job: job.update(
                {
                    "status": "running",
                    "startedAt": now_iso(),
                    "effectiveConcurrency": effective_parallelism,
                }
            ),
        )
        for group_index, group in enumerate(groups, start=1):
            def start_group(job: dict[str, Any], index: int = group_index) -> None:
                job["currentGroup"] = index
                _patch_bulk_generation_group(job, group_index=index, status="running")

            await _mutate_bulk_generation_job(job_id, start_group)

            async def generate_candidate(plan: _BulkGenerationPlanItem, candidate_index: int) -> None:
                async with semaphore:
                    await _mutate_bulk_generation_job(
                        job_id,
                        lambda job: _patch_bulk_generation_candidate(
                            job,
                            item_id=plan.id,
                            candidate_index=candidate_index,
                            patch={"status": "running", "error": None},
                        ),
                    )
                    resolved_references: list[str] = []
                    blocked_reason: str | None = None

                    def producer_candidate(reference: str) -> tuple[str | None, str | None]:
                        producer_id = output_to_item_id.get(
                            _run_relative_key(run_dir, reference)
                        )
                        if producer_id is None:
                            return None, None
                        producer_successes = successful_candidates.get(producer_id, {})
                        producer_plan = plan_by_id[producer_id]
                        replacement = producer_successes.get(candidate_index)
                        if replacement is None and producer_plan.request.candidate_count == 1:
                            replacement = producer_successes.get(1)
                        return producer_id, replacement

                    def add_resolved_reference(reference: str) -> None:
                        if reference not in resolved_references:
                            resolved_references.append(reference)

                    for dependency_reference in plan.dependency_references:
                        producer_id, replacement = producer_candidate(dependency_reference)
                        if producer_id is None:
                            add_resolved_reference(dependency_reference)
                        elif replacement is None:
                            blocked_reason = (
                                f"dependency candidate unavailable: {producer_id} "
                                f"candidate {candidate_index}"
                            )
                            break
                        else:
                            add_resolved_reference(replacement)

                    for reference in plan.references:
                        if blocked_reason is not None:
                            break
                        producer_id, replacement = producer_candidate(reference)
                        if producer_id is None:
                            add_resolved_reference(reference)
                            continue
                        if replacement is None:
                            blocked_reason = (
                                f"dependency candidate unavailable: {producer_id} "
                                f"candidate {candidate_index}"
                            )
                            break
                        add_resolved_reference(replacement)
                    if blocked_reason is not None:
                        await _mutate_bulk_generation_job(
                            job_id,
                            lambda job: _patch_bulk_generation_candidate(
                                job,
                                item_id=plan.id,
                                candidate_index=candidate_index,
                                patch={
                                    "status": "blocked",
                                    "path": None,
                                    "error": blocked_reason,
                                },
                            ),
                        )
                        return

                    request = plan.request.model_copy(
                        update={"references": resolved_references}
                    )
                    try:
                        candidate = await _generate_one(run_dir, request, candidate_index)
                        candidate = dict(candidate)
                        path = str(candidate.get("path") or "").strip()
                        if path:
                            _validate_run_relative_image_path(run_dir, path, must_exist=True)
                            validate_image_bytes(resolve_run_relative(run_dir, path))
                            successful_candidates[plan.id][candidate_index] = path
                            candidate["status"] = "completed"
                        else:
                            candidate["status"] = "failed"
                            candidate.setdefault("error", "generation did not import an image")
                    except Exception as exc:
                        candidate = {
                            "index": candidate_index,
                            "status": "failed",
                            "path": None,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    await _mutate_bulk_generation_job(
                        job_id,
                        lambda job: _patch_bulk_generation_candidate(
                            job,
                            item_id=plan.id,
                            candidate_index=candidate_index,
                            patch=candidate,
                        ),
                    )

            tasks = [
                asyncio.create_task(generate_candidate(plan, candidate_index))
                for plan in group
                for candidate_index in range(1, plan.request.candidate_count + 1)
            ]
            await asyncio.gather(*tasks)
            snapshot = await _mutate_bulk_generation_job(
                job_id,
                lambda job: _patch_bulk_generation_group(
                    job,
                    group_index=group_index,
                    status="completed",
                ),
            )
            if any(
                result.get("groupIndex") == group_index
                and result.get("status") in {"failed", "blocked"}
                for result in snapshot.get("results") or []
            ):
                await _mutate_bulk_generation_job(
                    job_id,
                    lambda job: _patch_bulk_generation_group(
                        job,
                        group_index=group_index,
                        status="completed_with_errors",
                    ),
                )

        async with _bulk_generation_jobs_lock:
            current = _bulk_generation_jobs[job_id]
            has_failures = any(
                result.get("status") in {"failed", "blocked"}
                for result in current.get("results") or []
            )
        await _mutate_bulk_generation_job(
            job_id,
            lambda job: job.update(
                {
                    "status": "failed" if has_failures else "completed",
                    "completedAt": now_iso(),
                    "error": "one or more image items failed" if has_failures else None,
                }
            ),
        )
    except asyncio.CancelledError:
        with suppress(Exception):
            await _mutate_bulk_generation_job(
                job_id,
                lambda job: _interrupt_bulk_generation_job(
                    job,
                    "image generation job was cancelled",
                ),
            )
        raise
    except Exception as exc:
        with suppress(Exception):
            await _mutate_bulk_generation_job(
                job_id,
                lambda job: _fail_bulk_generation_job(
                    job,
                    f"{type(exc).__name__}: {exc}",
                ),
            )
    finally:
        _bulk_generation_tasks.pop(job_id, None)


async def _create_bulk_generation_job(
    *,
    run_dir: Path,
    req: BulkGenerateRequest,
) -> dict[str, Any]:
    groups = _prepare_bulk_generation_plan(run_dir=run_dir, req=req)
    fingerprint = _bulk_generation_fingerprint(
        run_id=req.run_id,
        kind=req.kind,
        groups=groups,
    )
    async with _bulk_generation_jobs_lock:
        known_jobs = [
            job
            for job in _bulk_generation_jobs.values()
            if job.get("runId") == req.run_id and job.get("kind") == req.kind
        ]
        known_ids = {str(job.get("jobId") or "") for job in known_jobs}
        for path in _bulk_generation_job_files(run_dir):
            disk_job = _load_bulk_generation_job_path(path)
            if disk_job is None or str(disk_job.get("jobId") or "") in known_ids:
                continue
            known_jobs.append(_loaded_bulk_generation_job(disk_job))
        existing = next(
            (
                job
                for job in known_jobs
                if job.get("fingerprint") == fingerprint
                and job.get("status") in {"queued", "running"}
            ),
            None,
        )
        if existing is not None:
            _bulk_generation_jobs[str(existing["jobId"])] = existing
            return deepcopy(existing)
        active = next(
            (
                job
                for job in known_jobs
                if job.get("status") in {"queued", "running"}
            ),
            None,
        )
        if active is not None:
            raise HTTPException(
                status_code=409,
                detail=f"bulk image generation is already running: {active.get('jobId')}",
            )
        job = _initial_bulk_generation_job(
            req=req,
            groups=groups,
            fingerprint=fingerprint,
        )
        _bulk_generation_jobs[str(job["jobId"])] = job
        _persist_bulk_generation_job(job)

    task = asyncio.create_task(
        _run_bulk_generation_job(
            job_id=str(job["jobId"]),
            run_dir=run_dir,
            groups=groups,
            requested_concurrency=int(req.concurrency),
        )
    )
    _bulk_generation_tasks[str(job["jobId"])] = task
    return deepcopy(job)


async def _generate_one(run_dir: Path, req: GenerateRequest, index: int) -> dict[str, Any]:
    if not req.prompt.strip():
        detail = (
            "api_prompt_missing_for_new_prompt_policy"
            if str(req.prompt_policy_version or "").startswith(IMAGE_API_PROMPT_POLICY_PREFIX)
            else "prompt is required"
        )
        raise HTTPException(status_code=400, detail=detail)
    destination = candidate_path(run_dir, req.item_id, index)
    started = time.monotonic()
    generation_job_id = uuid.uuid4().hex
    provenance_policy = _image_generation_provenance_policy()
    allow_generated_images_fallback = provenance_policy != IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2
    references = []
    for ref in req.references:
        try:
            _validate_run_relative_image_path(run_dir, ref, must_exist=True)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        reference = resolve_run_relative(run_dir, ref)
        if not reference.exists() or not reference.is_file():
            raise HTTPException(status_code=404, detail=f"reference not found: {ref}")
        require_image_file(reference)
        references.append(reference)
    prompt_sha256 = hashlib.sha256(req.prompt.encode("utf-8")).hexdigest()
    reference_sha256s = [_file_sha256(reference) for reference in references]
    if app_server_disabled():
        raise HTTPException(status_code=503, detail="Codex app-server is disabled")
    write_app_server_debug_log(
        run_dir=run_dir,
        operation="candidate_generation",
        status="started",
        item_id=req.item_id,
        request={
            "kind": req.kind,
            "candidateIndex": index,
            "destination": destination.relative_to(run_dir).as_posix(),
            "referenceCount": len(references),
            "references": [ref.relative_to(run_dir).as_posix() if ref.is_relative_to(run_dir) else str(ref) for ref in references],
            "promptLength": len(req.prompt),
            "promptPolicyVersion": req.prompt_policy_version,
            "debugPromptSource": req.debug_prompt_source,
            "generationJobId": generation_job_id,
            "provenancePolicy": provenance_policy,
            "allowGeneratedImagesFallback": allow_generated_images_fallback,
        },
    )
    async with _generation_semaphore, _global_image_generation_slot(provenance_policy):
        client = create_codex_app_server_client(
            cwd=ROOT,
            scrub_sensitive_env=True,
            require_chatgpt_account=True,
            require_chatgpt_pro=True,
        )
        result = None
        debug_log = None
        retention_record: dict[str, Any] | None = None
        try:
            await client.start()
            async with _generated_images_fallback_claim_scope(allow_generated_images_fallback):
                fallback_cutoff_ns = latest_generated_image_mtime_ns() if allow_generated_images_fallback else None
                result = await client.generate_image(
                    prompt=req.prompt,
                    output_path=destination,
                    reference_images=references,
                    item_id=req.item_id,
                    run_dir=run_dir,
                    fallback_cutoff_ns=fallback_cutoff_ns,
                    generation_job_id=generation_job_id,
                    allow_generated_images_fallback=allow_generated_images_fallback,
                    provenance_policy=provenance_policy,
                    timeout_seconds=max(1, int(IMAGE_GENERATION_ITEM_TIMEOUT_SECONDS)),
            )
            reject_local_raster_image_result(result, item_id=req.item_id)
            if (
                result.saved_path is not None
                and provenance_policy == IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2
                and not bool(getattr(result, "provenance_authoritative", False))
            ):
                raise RuntimeError(f"Codex app-server did not return authoritative request-bound provenance for {req.item_id}")
            if (
                result.saved_path is not None
                and provenance_policy == IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2
            ):
                _validate_request_bound_image_result(
                    result,
                    generation_job_id=generation_job_id,
                    item_id=req.item_id,
                    destination=destination,
                    prompt_sha256=prompt_sha256,
                    reference_sha256s=reference_sha256s,
                )
            if result.saved_path is not None:
                retention_record = retain_first_image(
                    result.saved_path,
                    root=ROOT,
                    run_id=run_dir.name,
                    kind=req.kind,
                    item_id=req.item_id,
                    candidate_index=index,
                    destination=destination.relative_to(run_dir).as_posix(),
                    storage_role="candidate",
                    provenance={
                        "generationJobId": generation_job_id,
                        "turnId": getattr(result, "turn_id", None),
                        "imageGenerationItemId": getattr(result, "image_generation_item_id", None),
                        "promptSha256": prompt_sha256,
                        "referenceSha256s": reference_sha256s,
                        "provenancePolicy": provenance_policy,
                        "provenanceAuthoritative": bool(getattr(result, "provenance_authoritative", False)),
                    },
                )
        except Exception as exc:
            debug_log = write_app_server_image_debug_log(
                run_dir=run_dir,
                item_id=req.item_id,
                index=index,
                destination=destination,
                references=references,
                prompt=req.prompt,
                kind=req.kind,
                prompt_policy_version=req.prompt_policy_version,
                debug_prompt_source=req.debug_prompt_source,
                result=result,
                error=str(exc),
            )
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="candidate_generation",
                status="failed",
                item_id=req.item_id,
                request={"kind": req.kind, "candidateIndex": index, "destination": destination.relative_to(run_dir).as_posix()},
                response={
                    "elapsedMs": int((time.monotonic() - started) * 1000),
                    "debugLog": debug_log.relative_to(run_dir).as_posix() if debug_log else None,
                    "generationJobId": generation_job_id,
                    "provenancePolicy": provenance_policy,
                },
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        finally:
            await client.stop()
    debug_log_path = debug_log.relative_to(run_dir).as_posix() if debug_log else None
    result_source = getattr(result, "source", "app_server")
    if result.saved_path is None:
        debug_log = write_app_server_image_debug_log(
            run_dir=run_dir,
            item_id=req.item_id,
            index=index,
            destination=destination,
            references=references,
            prompt=req.prompt,
            kind=req.kind,
            prompt_policy_version=req.prompt_policy_version,
            debug_prompt_source=req.debug_prompt_source,
            result=result,
            error="Codex app-server did not return imageGeneration.savedPath",
        )
        debug_log_path = debug_log.relative_to(run_dir).as_posix()
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="candidate_generation",
            status="failed",
            item_id=req.item_id,
            request={"kind": req.kind, "candidateIndex": index, "destination": destination.relative_to(run_dir).as_posix()},
            response={
                "elapsedMs": int((time.monotonic() - started) * 1000),
                "debugLog": debug_log_path,
                "source": result_source,
                "generationJobId": generation_job_id,
                "provenancePolicy": provenance_policy,
            },
            error="Codex app-server did not return imageGeneration.savedPath",
        )
        return {
            "index": index,
            "status": "failed",
            "error": "Codex app-server did not return imageGeneration.savedPath",
            "path": None,
            "revisedPrompt": result.revised_prompt,
            "debugLog": debug_log_path,
            "source": result_source,
            "generationJobId": generation_job_id,
            "provenancePolicy": provenance_policy,
        }
    try:
        destination, index = copy_saved_image_to_new_candidate(
            result.saved_path,
            run_dir=run_dir,
            item_id=req.item_id,
            requested_index=index,
        )
        debug_log = write_app_server_image_debug_log(
            run_dir=run_dir,
            item_id=req.item_id,
            index=index,
            destination=destination,
            references=references,
            prompt=req.prompt,
            kind=req.kind,
            prompt_policy_version=req.prompt_policy_version,
            debug_prompt_source=req.debug_prompt_source,
            result=result,
        )
        debug_log_path = debug_log.relative_to(run_dir).as_posix()
    except Exception as exc:
        debug_log = write_app_server_image_debug_log(
            run_dir=run_dir,
            item_id=req.item_id,
            index=index,
            destination=destination,
            references=references,
            prompt=req.prompt,
            kind=req.kind,
            prompt_policy_version=req.prompt_policy_version,
            debug_prompt_source=req.debug_prompt_source,
            result=result,
            error=str(exc),
        )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="candidate_generation",
            status="failed",
            item_id=req.item_id,
            request={
                "kind": req.kind,
                "candidateIndex": index,
                "destination": destination.relative_to(run_dir).as_posix(),
            },
            response={
                "elapsedMs": int((time.monotonic() - started) * 1000),
                "debugLog": debug_log.relative_to(run_dir).as_posix(),
                "generationJobId": generation_job_id,
                "provenancePolicy": provenance_policy,
            },
            error=f"{type(exc).__name__}: {exc}",
        )
        raise
    write_app_server_debug_log(
        run_dir=run_dir,
        operation="candidate_generation",
        status="completed",
        item_id=req.item_id,
        request={"kind": req.kind, "candidateIndex": index, "destination": destination.relative_to(run_dir).as_posix()},
        response={
            "elapsedMs": int((time.monotonic() - started) * 1000),
            "debugLog": debug_log_path,
            "source": result_source,
            "savedPath": str(result.saved_path),
            "generationJobId": generation_job_id,
            "turnId": getattr(result, "turn_id", None),
            "provenancePolicy": provenance_policy,
            "provenanceAuthoritative": bool(getattr(result, "provenance_authoritative", False)),
            "retainedFirstImage": bool(retention_record),
            "retainedFirstImageCreated": bool(retention_record and retention_record.get("created")),
        },
    )
    return {
        "index": index,
        "status": "completed",
        "path": destination.relative_to(run_dir).as_posix(),
        "revisedPrompt": result.revised_prompt,
        "debugLog": debug_log_path,
        "source": result_source,
        "generationJobId": generation_job_id,
        "provenancePolicy": provenance_policy,
        "provenanceAuthoritative": bool(getattr(result, "provenance_authoritative", False)),
        "retainedFirstImage": bool(retention_record),
        "retainedFirstImageCreated": bool(retention_record and retention_record.get("created")),
    }


@router.post("/api/image-gen/generate")
async def api_generate(req: GenerateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    candidates = await asyncio.gather(*(_generate_one(run_dir, req, index) for index in range(1, req.candidate_count + 1)))
    return {"itemId": req.item_id, "candidates": candidates}


@router.post("/api/image-gen/generate-bulk")
async def api_generate_bulk(req: BulkGenerateRequest) -> Any:
    run_dir = safe_run_dir(req.run_id, ROOT)
    total_candidates = sum(item.candidate_count for item in req.items)
    if total_candidates > 100:
        raise HTTPException(status_code=400, detail="bulk generation is limited to 100 total candidates")
    if req.background:
        try:
            job = await _create_bulk_generation_job(run_dir=run_dir, req=req)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(status_code=202, content=job)
    normalized_items = [item.model_copy(update={"run_id": req.run_id, "kind": req.kind}) for item in req.items]
    candidates_by_item: list[list[dict[str, Any]]] = [[] for _ in normalized_items]
    semaphore = asyncio.Semaphore(min(req.concurrency, max(total_candidates, 1)))
    jobs = [
        (item_position, item, candidate_index)
        for item_position, item in enumerate(normalized_items)
        for candidate_index in range(1, item.candidate_count + 1)
    ]

    async def guarded(item_position: int, item: GenerateRequest, candidate_index: int) -> tuple[int, dict[str, Any]]:
        async with semaphore:
            try:
                return item_position, await _generate_one(run_dir, item, candidate_index)
            except Exception as exc:
                return item_position, {
                    "index": candidate_index,
                    "status": "failed",
                    "path": None,
                    "error": str(exc),
                }

    for item_position, candidate in await asyncio.gather(*(guarded(*job) for job in jobs)):
        candidates_by_item[item_position].append(candidate)

    payload = []
    for item, candidates in zip(normalized_items, candidates_by_item, strict=False):
        candidates.sort(key=lambda candidate: int(candidate.get("index") or 0))
        has_error = candidates and not any(candidate.get("path") for candidate in candidates)
        result: dict[str, Any] = {"itemId": item.item_id, "candidates": candidates}
        if has_error:
            result["error"] = "generation failed"
        payload.append(result)
    return {"runId": req.run_id, "kind": req.kind, "results": payload}


@router.get("/api/image-gen/generate-bulk/{job_id}")
async def api_generate_bulk_status(job_id: str) -> dict[str, Any]:
    async with _bulk_generation_jobs_lock:
        job = _bulk_generation_jobs.get(job_id)
        if job is not None:
            try:
                run_dir = safe_run_dir(str(job.get("runId") or ""), ROOT)
            except (FileNotFoundError, ValueError):
                run_dir = None
            if run_dir is not None:
                _reconcile_bulk_generation_job_candidates(job, run_dir)
                _refresh_bulk_generation_job_counts(job)
            return deepcopy(job)
    try:
        job = _bulk_generation_job_from_disk(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if job is None:
        raise HTTPException(status_code=404, detail="bulk generation job not found")
    async with _bulk_generation_jobs_lock:
        _bulk_generation_jobs[job_id] = job
    return deepcopy(job)


@router.get("/api/image-gen/runs/{run_id}/generate-bulk/active")
async def api_active_generate_bulk_job(
    run_id: str,
    kind: str = Query(pattern="^(asset|scene)$"),
) -> dict[str, Any]:
    run_dir = safe_run_dir(run_id, ROOT)
    async with _bulk_generation_jobs_lock:
        jobs = [
            deepcopy(job)
            for job in _bulk_generation_jobs.values()
            if job.get("runId") == run_id and job.get("kind") == kind
        ]
    for job in jobs:
        _reconcile_bulk_generation_job_candidates(job, run_dir)
        _refresh_bulk_generation_job_counts(job)
    known_ids = {str(job.get("jobId") or "") for job in jobs}
    for path in _bulk_generation_job_files(run_dir):
        disk_job = _load_bulk_generation_job_path(path)
        if (
            disk_job is None
            or disk_job.get("kind") != kind
            or str(disk_job.get("jobId") or "") in known_ids
        ):
            continue
        jobs.append(_loaded_bulk_generation_job(disk_job))
    if not jobs:
        raise HTTPException(status_code=404, detail="bulk generation job not found")
    active_jobs = [job for job in jobs if job.get("status") in {"queued", "running"}]
    candidates = active_jobs or jobs
    latest = max(
        candidates,
        key=lambda job: str(job.get("updatedAt") or job.get("createdAt") or ""),
    )
    async with _bulk_generation_jobs_lock:
        _bulk_generation_jobs[str(latest["jobId"])] = latest
    return deepcopy(latest)


@router.post("/api/image-gen/regenerate-prompts")
async def api_regenerate_prompts(req: RegeneratePromptsRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    if app_server_disabled():
        raise HTTPException(status_code=503, detail="Codex app-server is disabled")
    try:
        kind = target_to_request_kind(req.target)
        setting = read_prompt_setting(req.target, root=ROOT)
        items = [item for item in load_request_items(run_dir, kind) if target_matches_item(req.target, item)]
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if req.item_ids:
        requested_ids = set(req.item_ids)
        eligible_ids = {item.id for item in items}
        missing_ids = sorted(requested_ids - eligible_ids)
        if missing_ids:
            raise HTTPException(status_code=400, detail={"unknownItemIds": missing_ids})
        items = [item for item in items if item.id in requested_ids]
    if not items:
        raise HTTPException(status_code=400, detail="no matching prompt items")
    v2_items = [item for item in items if str(getattr(item, "prompt_policy_version", "") or "") == "image_api_prompt_v2"]
    if v2_items and kind != "scene":
        raise HTTPException(status_code=409, detail="compiled_v2_recompile_is_supported_for_scene_items_only")
    manifest_plans: dict[str, dict[str, Any]] = {}
    if v2_items:
        try:
            _manifest_path, _manifest_original, manifest_data = _read_manifest_data(run_dir)
            for item in v2_items:
                target = _target_by_item_id(manifest_data, item.id)
                if target is None:
                    raise ValueError(f"video manifest target not found: {item.id}")
                image_generation = _dict_value(_dict_value(target.get("cut")).get("image_generation"))
                plan = _dict_value(image_generation.get("first_frame_visual_plan"))
                if not plan:
                    raise ValueError(f"compiled_v2_first_frame_visual_plan_missing: {item.id}")
                manifest_plans[item.id] = deepcopy(plan)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    semaphore = asyncio.Semaphore(req.concurrency)

    async def regenerate_one(item: Any) -> dict[str, Any]:
        async with semaphore:
            client = create_codex_app_server_client(cwd=ROOT)
            try:
                await _start_app_server_with_log(client, run_dir=run_dir, operation="prompt_regeneration", item_id=item.id)
                if item.id in manifest_plans:
                    patch = await _revise_v2_visual_plan_with_log(
                        client,
                        run_dir=run_dir,
                        item=item_to_api(item),
                        current_plan=manifest_plans[item.id],
                        instruction=req.instruction,
                        setting_content=setting["content"],
                    )
                    return {
                        "itemId": item.id,
                        "operation": "recompiled",
                        "patch": patch,
                        "expectedPlanHash": _json_hash(manifest_plans[item.id]),
                    }
                prompt = await _regenerate_prompt_with_log(
                    client,
                    run_dir=run_dir,
                    item=item_to_api(item),
                    target=req.target,
                    instruction=req.instruction,
                    setting_content=setting["content"],
                    operation="prompt_regeneration",
                )
                return {"itemId": item.id, "prompt": prompt, "operation": "direct_update"}
            finally:
                await client.stop()

    results = await asyncio.gather(*(regenerate_one(item) for item in items), return_exceptions=True)
    failures: list[dict[str, str]] = []
    prompts: dict[str, str] = {}
    v2_revisions: dict[str, dict[str, Any]] = {}
    for item, result in zip(items, results, strict=False):
        if isinstance(result, Exception):
            failures.append({"itemId": item.id, "error": str(result)})
        else:
            item_id = str(result["itemId"])
            if result.get("operation") == "recompiled":
                v2_revisions[item_id] = {
                    "patch": _dict_value(result.get("patch")),
                    "expected_plan_hash": str(result.get("expectedPlanHash") or ""),
                }
            else:
                prompts[item_id] = str(result["prompt"])
    if failures:
        raise HTTPException(status_code=500, detail={"status": "failed", "failures": failures})
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            async with _serialized_run_write(run_dir, f"{kind}_request_revision"):
                rollback_paths = (
                    run_dir / "video_manifest.md",
                    run_dir / "image_generation_requests.md",
                    run_dir / "image_generation_request_snapshot.json",
                    run_dir / "asset_generation_requests.md",
                    run_dir / "asset_generation_request_snapshot.json",
                )
                before = _capture_file_transaction(rollback_paths)
                try:
                    compiled = _recompile_v2_scene_manifest(run_dir, v2_revisions) if v2_revisions else {}
                    if v2_revisions:
                        await _materialize_scene_requests(req.run_id)
                    update_result = update_request_prompts(run_dir, kind, prompts) if prompts else {"updated": [], "missing": []}
                    reloaded = {item.id: item for item in load_request_items(run_dir, kind)}
                    missing_recompiled = sorted(set(v2_revisions) - set(reloaded))
                    if missing_recompiled:
                        raise ValueError(f"recompiled request items missing: {', '.join(missing_recompiled)}")
                    if v2_revisions:
                        append_state_snapshot(
                            run_dir / "state.txt",
                            {
                                "runtime.stage": "prompt_recompiled_awaiting_semantic_review",
                                "review.frontend.prompt_recompile.status": "done",
                                "review.frontend.prompt_recompile.items": ", ".join(v2_revisions),
                                "review.semantic.image_prompt.status": "pending",
                                "review.image.status": "pending",
                                "review.image_prompt.request_freeze.status": "draft",
                                "slot.p650.status": "pending",
                                "slot.p650.note": "compiled-v2 draft rematerialized; semantic image-prompt review must pass before freeze",
                                "slot.p660.status": "pending",
                                "slot.p670.status": "pending",
                                "slot.p680.status": "pending",
                                "artifact.video_manifest": str((run_dir / "video_manifest.md").resolve()),
                                "artifact.image_generation_requests": str((run_dir / "image_generation_requests.md").resolve()),
                                "artifact.image_generation_request_snapshot": str(
                                    (run_dir / "image_generation_request_snapshot.json").resolve()
                                ),
                            },
                        )
                except Exception:
                    _restore_file_transaction(before)
                    raise
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        status_code = 409 if "conflict" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if update_result["missing"]:
        raise HTTPException(status_code=400, detail={"missingPromptSections": update_result["missing"]})
    response_prompts = [
        {
            "itemId": item_id,
            "prompt": str(reloaded[item_id].prompt),
            "promptPolicyVersion": str(reloaded[item_id].prompt_policy_version or ""),
            "operation": "recompiled",
            "requestRevision": str(reloaded[item_id].request_revision or ""),
            "sourceDigest": str(compiled[item_id].get("source_digest") or ""),
            "compilerVersion": str(compiled[item_id].get("compiler_version") or ""),
        }
        for item_id in v2_revisions
    ] + [
        {"itemId": item_id, "prompt": prompt, "operation": "direct_update"}
        for item_id, prompt in prompts.items()
    ]
    return {
        "runId": req.run_id,
        "target": req.target,
        "kind": kind,
        "status": "completed",
        "operation": "recompiled" if v2_revisions else "direct_update",
        "prompts": response_prompts,
        "updated": [*v2_revisions.keys(), *update_result["updated"]],
        "missing": update_result["missing"],
    }


@router.post("/api/image-gen/download-zip")
async def api_download_zip(req: ZipRequest) -> StreamingResponse:
    run_dir = safe_run_dir(req.run_id, ROOT)
    paths = []
    total_bytes = 0
    for raw_path in req.paths:
        path = resolve_run_relative(run_dir, raw_path)
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail=f"file not found: {raw_path}")
        try:
            require_candidate_path(run_dir, path)
            validate_image_bytes(path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        total_bytes += path.stat().st_size
        if total_bytes > MAX_ZIP_BYTES:
            raise HTTPException(status_code=400, detail="zip payload is too large")
        paths.append(path)
    data = build_zip(paths, base_dir=run_dir)
    return StreamingResponse(
        iter([data]),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="image-gen-candidates.zip"'},
    )


@router.post("/api/image-gen/insert-bulk")
async def api_insert_bulk(req: BulkInsertRequest) -> dict[str, Any]:
    inserted = []
    for item in req.items:
        run_dir = safe_run_dir(item.run_id, ROOT)
        candidate = resolve_run_relative(run_dir, item.candidate_path)
        if not candidate.exists():
            raise HTTPException(status_code=404, detail=f"candidate not found: {item.candidate_path}")
        try:
            _validate_candidate_matches_output(run_dir, candidate, item.output)
            inserted.append(insert_candidate(run_dir, candidate, item.output))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"inserted": inserted}


@router.post("/api/chat/turn")
async def api_chat_turn(req: ChatTurnRequest) -> dict[str, Any]:
    async with _chat_semaphore:
        async with _chat_turn_lock:
            client = await get_codex_client()
            cwd = safe_run_dir(req.run_id, ROOT) if req.run_id else ROOT
            log_dir = cwd if req.run_id else ROOT
            thread_id = _chat_threads.get(req.session_id)
            try:
                if not thread_id:
                    thread_id = await client.start_thread(cwd=cwd)
                    write_app_server_debug_log(
                        run_dir=log_dir,
                        operation="chat_thread_start",
                        status="completed",
                        item_id=req.session_id,
                        request={"cwd": str(cwd), "sessionId": req.session_id},
                        response={"threadId": thread_id},
                    )
                    if len(_chat_threads) >= 32:
                        _chat_threads.pop(next(iter(_chat_threads)))
                    _chat_threads[req.session_id] = thread_id
                transcript = await client.run_turn(thread_id=thread_id, text=req.message, cwd=cwd, timeout_seconds=300)
                write_app_server_debug_log(
                    run_dir=log_dir,
                    operation="chat_turn",
                    status="completed",
                    item_id=req.session_id,
                    request={"threadId": thread_id, "messageLength": len(req.message), "runId": req.run_id},
                    transcript=transcript,
                )
            except Exception as exc:
                write_app_server_debug_log(
                    run_dir=log_dir,
                    operation="chat_turn",
                    status="failed",
                    item_id=req.session_id,
                    request={"threadId": thread_id, "messageLength": len(req.message), "runId": req.run_id},
                    error=str(exc),
                )
                raise
    messages: list[str] = []
    approvals: list[dict[str, Any]] = []
    for event in transcript:
        method = event.get("method")
        params = event.get("params") or {}
        item = params.get("item") or {}
        if item.get("type") == "agentMessage" and item.get("text"):
            messages.append(str(item["text"]))
        if method and str(method).endswith("/requestApproval"):
            approvals.append({"method": method, "params": params})
    return {"sessionId": req.session_id, "threadId": thread_id, "message": "\n".join(messages).strip(), "approvals": approvals}
