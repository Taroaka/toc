from __future__ import annotations

import asyncio
from collections import Counter
from copy import deepcopy
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager, suppress
import ctypes
from dataclasses import dataclass
import errno
import fcntl
import hashlib
import importlib.util
import json
import math
import os
import re
import signal
import stat
import threading
import time
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import uuid
import warnings
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping
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
    create_codex_app_server_client as _create_codex_app_server_client_unbound,
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
from toc.production_repair import RepairSession
from toc.production_diagnostics import MediaOutputError
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
    current_reference_sha256s as _current_reference_sha256s_unbound,
    load_request_snapshot as _load_request_snapshot_unbound,
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
from toc.state_store import append_state_delta
from toc.run_root_binding import (
    RunRootBinding,
    RunRootBindingError,
    bind_run_root,
    current_run_root_binding,
    read_run_file_bytes,
    require_bound_run_root,
    require_live_run_root_binding,
    run_file_entry_exists,
    unlink_run_file,
    verify_run_root,
    write_run_file_text,
)
from toc import process_store
from toc.providers.kling import KlingClient, KlingConfig
from toc.providers.seedance import SeedanceClient, SeedanceConfig
from toc.script_narration import materialize_elevenlabs_tts_text, resolve_script_cut_tts_text
from toc.narration_revision import (
    REVISION_SCHEMA_VERSION,
    NarrationRevisionConflict,
    apply_authoring_update,
    approve_audio_candidate,
    current_audio_candidate,
    current_audio_is_ready,
    ensure_narration_revision,
    narration_text_hash,
    narration_tts_hash,
    prepare_audio_candidate,
    record_audio_candidate_result,
)
from toc.narration_continuity import (
    invalidate_stale_tts_context_audio,
    narration_span_refs,
    reconcile_audio_story_text,
    tts_continuity_contexts,
)
from toc.story_duration import audit_duration, measure_manifest_runtime, normalize_target_duration
from scripts.world_walk_source import (
    read_regular_file_nofollow,
    validate_world_walk_source_path,
    write_regular_file_nofollow,
)
from toc.runtime_locks import (
    FileLockLease,
    FileLockUnavailable,
    acquire_file_lock,
    async_file_lock,
    async_file_slot,
    release_file_lock,
)
from toc.manifest_source import manifest_source_sha256
from toc.scene_acceptance_contract import criterion_registry_payload, resolve_criterion
from toc.tts_text import load_pronunciation_aliases, prepare_elevenlabs_tts_text
from .image_gen import (
    IMAGE_API_PROMPT_POLICY_VERSION,
    IMAGE_API_PROMPT_POLICY_PREFIX,
    IMAGE_SUFFIXES,
    MAX_IMAGE_BYTES,
    build_zip,
    candidate_path,
    copy_saved_image_to_new_candidate,
    insert_candidate,
    item_to_api,
    list_reference_options,
    list_candidate_items,
    list_first_image_retentions,
    list_restored_first_image_items,
    list_runs,
    load_request_items_for_display,
    load_request_items as _load_request_items_unbound,
    output_root,
    prompt_setting_targets,
    reference_to_api,
    require_image_file,
    require_candidate_path,
    read_prompt_setting,
    read_run_progress,
    rehydrate_retained_first_image,
    repo_root,
    restore_first_image_retention_run,
    retain_first_image,
    sanitize_run_title,
    resolve_run_relative as _resolve_run_relative_unbound,
    safe_run_dir as _safe_run_dir_unbound,
    is_first_image_retention_restored_run,
    target_matches_item,
    target_to_request_kind,
    update_request_prompts,
    validate_candidate_insertion,
    validate_image_bytes,
    write_app_server_debug_log as _write_app_server_debug_log_unbound,
    write_app_server_image_debug_log as _write_app_server_image_debug_log_unbound,
    write_app_server_image_provenance_invalidation_log as _write_app_server_image_provenance_invalidation_log_unbound,
    write_prompt_setting,
)


ROOT = repo_root()
APP_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "server" / "web"
DIST_DIR = WEB_DIR / "dist"

router = APIRouter()


def _assert_bound_run_root(run_dir: Path) -> RunRootBinding | None:
    """Fail closed when a frontend/resume owner pinned a different inode."""

    return require_bound_run_root(Path(run_dir))


def create_codex_app_server_client(
    *,
    cwd: Path,
    **kwargs: Any,
) -> CodexAppServerClient:
    binding = current_run_root_binding()
    if binding is not None and "submission_guard" not in kwargs:
        bound_root = Path(binding.lexical_root)

        def guard_submission() -> None:
            require_live_run_root_binding(binding)
            verify_run_root(
                bound_root,
                expected_identity=binding.identity,
            )
            require_live_run_root_binding(binding)
            active = current_run_root_binding()
            if active is not None and (
                active.lexical_root != binding.lexical_root
                or active.identity != binding.identity
            ):
                raise RunRootBindingError(
                    "app-server submission escaped its captured run binding"
                )
            require_live_run_root_binding(binding)

        kwargs["submission_guard"] = guard_submission
    return _create_codex_app_server_client_unbound(
        cwd=cwd,
        **kwargs,
    )


def safe_run_dir(run_id: str, root: Path | None = None) -> Path:
    """Resolve an API run while preserving an active frontend inode binding."""

    binding = current_run_root_binding()
    if binding is None:
        return _safe_run_dir_unbound(run_id, root)
    if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
        raise ValueError("invalid run_id")
    resolved = _safe_run_dir_unbound(run_id, root)
    opened = os.stat(resolved, follow_symlinks=False)
    if (opened.st_dev, opened.st_ino) != binding.identity:
        raise RunRootBindingError(
            "requested run does not match the active bound run root"
        )
    lexical = Path(binding.lexical_root)
    _assert_bound_run_root(lexical)
    _assert_bound_run_root(lexical)
    return lexical


def resolve_run_relative(run_dir: Path, value: str) -> Path:
    _assert_bound_run_root(run_dir)
    result = _resolve_run_relative_unbound(run_dir, value)
    _assert_bound_run_root(run_dir)
    return result


def load_request_items(run_dir: Path, kind: str) -> list[Any]:
    binding = _assert_bound_run_root(run_dir)
    result = _load_request_items_unbound(
        run_dir,
        kind,
        expected_root_identity=(binding.identity if binding else None),
    )
    _assert_bound_run_root(run_dir)
    return result


def load_request_snapshot(
    path: Path,
    *,
    run_dir: Path | None = None,
    verify_references: bool = True,
):
    base = run_dir or path.parent
    binding = _assert_bound_run_root(base)
    result = _load_request_snapshot_unbound(
        path,
        run_dir=run_dir,
        verify_references=verify_references,
        expected_root_identity=(binding.identity if binding else None),
    )
    _assert_bound_run_root(base)
    return result


def current_reference_sha256s(
    run_dir: Path,
    item: Any,
    *,
    allow_deferred: bool = False,
):
    binding = _assert_bound_run_root(run_dir)
    result = _current_reference_sha256s_unbound(
        run_dir,
        item,
        allow_deferred=allow_deferred,
        expected_root_identity=(binding.identity if binding else None),
    )
    _assert_bound_run_root(run_dir)
    return result


def write_app_server_debug_log(*, run_dir: Path, **kwargs: Any) -> Path:
    _assert_bound_run_root(run_dir)
    result = _write_app_server_debug_log_unbound(
        run_dir=run_dir,
        **kwargs,
    )
    _assert_bound_run_root(run_dir)
    return result


def write_app_server_image_debug_log(
    *,
    run_dir: Path,
    **kwargs: Any,
) -> Path | None:
    _assert_bound_run_root(run_dir)
    result = _write_app_server_image_debug_log_unbound(
        run_dir=run_dir,
        **kwargs,
    )
    _assert_bound_run_root(run_dir)
    return result


def write_app_server_image_provenance_invalidation_log(
    *,
    run_dir: Path,
    **kwargs: Any,
) -> Path:
    _assert_bound_run_root(run_dir)
    result = _write_app_server_image_provenance_invalidation_log_unbound(
        run_dir=run_dir,
        **kwargs,
    )
    _assert_bound_run_root(run_dir)
    return result


def _rewrite_bound_subprocess_paths(
    command: Iterable[str | os.PathLike[str]],
    *,
    binding: RunRootBinding,
) -> list[str]:
    rewritten: list[str] = []
    for raw_argument in command:
        argument = os.fspath(raw_argument)
        absolute_argument = os.path.abspath(argument)
        try:
            contained = os.path.commonpath(
                (binding.lexical_root, absolute_argument)
            ) == binding.lexical_root
        except ValueError:
            contained = False
        if contained:
            relative = os.path.relpath(
                absolute_argument,
                binding.lexical_root,
            )
            rewritten.append("." if relative == "." else relative)
        else:
            rewritten.append(argument)
    return rewritten


def _run_bound_subprocess(
    run_dir: Path,
    command: Iterable[str | os.PathLike[str]],
    **kwargs: Any,
) -> subprocess.CompletedProcess[Any]:
    """Run verifiers from the pinned run descriptor when a binding is active."""

    binding = _assert_bound_run_root(run_dir)
    subprocess_command = [os.fspath(argument) for argument in command]
    if binding is None:
        return subprocess.run(subprocess_command, **kwargs)
    if "preexec_fn" in kwargs:
        raise ValueError("bound run subprocess cannot override preexec_fn")
    subprocess_command = _rewrite_bound_subprocess_paths(
        subprocess_command,
        binding=binding,
    )
    inherited = set(kwargs.pop("pass_fds", ()))
    inherited.add(binding.descriptor)
    kwargs["pass_fds"] = tuple(sorted(inherited))

    subprocess_command = [
        sys.executable,
        str(APP_ROOT / "scripts" / "run-from-directory-fd.py"),
        "--fd",
        str(binding.descriptor),
        "--",
        *subprocess_command,
    ]
    try:
        return subprocess.run(subprocess_command, **kwargs)
    finally:
        _assert_bound_run_root(run_dir)
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
    "p210",
    "p220",
    "p310",
    "p330",
    "p410",
    "p420",
    "p440",
    "p450",
    "p510",
    "p520",
    "p530",
    "p550",
    "p560",
    "p570",
    "p610",
    "p620",
    "p650",
)
P680_FIXED_SLOTS = (*P650_FIXED_SLOTS, "p660", "p670", "p680")
CREATE_MODE_NORMAL = "normal"
CREATE_MODE_SCENE_STORYBOARD = "scene_storyboard"
CREATE_MODE_WORLD_WALK = "world_walk"
CREATE_MODE_SCENE_STORYBOARD_RUN_SUFFIX = "storyboard"
CREATE_STOP_TARGETS = {"p650", "p680"}
VIDEO_GENERATION_DURATION_MAX_SECONDS = 60
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
RESUME_SUBPROCESS_TERMINATION_GRACE_SECONDS = max(
    0.1,
    float(
        os.environ.get(
            "TOC_RESUME_SUBPROCESS_TERMINATION_GRACE_SECONDS",
            "5",
        )
        or "5"
    ),
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


class CanonicalP500ResumeRequiredError(RuntimeError):
    """Image-only resume cannot safely repair current p500 references."""


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
    cinematic_preferences: str | None = Field(default=None, max_length=12000)
    generate_images: bool = True
    stop_target: str = Field(default="p680", pattern="^(p650|p680)$")
    target_duration_seconds: int = Field(default=300, ge=300, le=1200, strict=True)
    review_mode: Literal["standard", "preapproved"] = "standard"


class CreateStoryboardRunRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    source: str | None = Field(default=None, max_length=4000)
    cinematic_preferences: str | None = Field(default=None, max_length=12000)
    stop_target: Literal["p680"] = "p680"
    target_duration_seconds: int = Field(default=300, ge=300, le=1200, strict=True)
    review_mode: Literal["standard", "preapproved"] = "standard"


class CreateWorldWalkRunRequest(BaseModel):
    source_run_id: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=120)
    target_duration_seconds: int = Field(default=300, ge=300, le=1200, strict=True)
    review_mode: Literal["standard", "preapproved"] = "standard"


class ResumeRunRequest(BaseModel):
    continue_waiting: bool = False
    stop_target: str = Field(default="p680", pattern="^(p680)$")
    operation_id: str | None = Field(default=None, pattern="^[0-9a-f]{32}$")


class FrontendReviewItem(BaseModel):
    item_id: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(asset|scene)$")
    output: str | None = Field(default=None, max_length=500)
    prompt: str = Field(default="", max_length=40000)
    references: list[str] = Field(default_factory=list, max_length=32)
    selected_candidate_path: str | None = Field(default=None, max_length=500)
    existing_image: str | None = Field(default=None, max_length=500)
    video_prompt: str | None = Field(default=None, max_length=40000)
    video_quality: str | None = Field(default=None, pattern="^(480p|720p|1080p|4K)$")
    video_aspect_ratio: str | None = Field(default=None, pattern="^(16:9|9:16|1:1|4:3|3:4|21:9)$")
    video_duration_seconds: int | None = Field(default=None, ge=1, le=VIDEO_GENERATION_DURATION_MAX_SECONDS)
    video_first_reference: str | None = Field(default=None, max_length=500)
    video_last_reference: str | None = Field(default=None, max_length=500)
    video_references: list[str] = Field(default_factory=list, max_length=32)
    video_tool: str | None = Field(default=None, pattern="^(kling_3_0|kling_3_0_omni|seedance|higgsfield)$")
    video_input_mode: str | None = Field(default=None, pattern='^(image_to_video|reference_images)$')
    video_native_audio_mode: str | None = Field(default=None, pattern='^(off|natural_sound|dialogue_and_sound)$')
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
    quality: str = Field(default="1080p", pattern="^(480p|720p|1080p|4K)$")
    aspect_ratio: str = Field(default="16:9", pattern="^(16:9|9:16|1:1|4:3|3:4|21:9)$")
    duration_seconds: int = Field(default=8, ge=1, le=VIDEO_GENERATION_DURATION_MAX_SECONDS)
    tool: str = Field(default="kling_3_0", pattern="^(kling_3_0|kling_3_0_omni|seedance|higgsfield)$")
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
_create_job_failure_baselines: dict[str, tuple[str, str, str]] = {}
_bulk_generation_jobs: dict[str, dict[str, Any]] = {}
_bulk_generation_tasks: dict[str, asyncio.Task[None]] = {}
_create_tasks: dict[str, asyncio.Task[None]] = {}
_resume_tasks: dict[str, asyncio.Task[None]] = {}
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

@dataclass
class _RunExecutionLease:
    runtime_lease: FileLockLease
    run_descriptor: int
    identity: tuple[int, int]


_run_execution_leases: dict[str, _RunExecutionLease] = {}
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
        binding = _assert_bound_run_root(run_dir)
        async with async_file_lock(
            run_dir / ".locks" / f"{safe_resource}.lock",
            wait=True,
            **(
                {
                    "run_root_descriptor": binding.descriptor,
                    "expected_run_root_identity": binding.identity,
                }
                if binding is not None
                else {}
            ),
        ):
            yield


async def _acquire_run_execution_lease(
    job_id: str,
    run_dir: Path,
    *,
    run_descriptor: int | None = None,
    expected_run_identity: tuple[int, int] | None = None,
) -> _RunExecutionLease:
    retained_descriptor = -1
    runtime_lease: FileLockLease | None = None
    if run_descriptor is None:
        try:
            with _frontend_create_directory_lock(
                run_dir,
                expected_identity=expected_run_identity,
            ) as directory_lease:
                retained_descriptor = os.dup(directory_lease.descriptor)
                expected_run_identity = directory_lease.identity
        except FrontendCreateLockOwnedError as exc:
            raise FileLockUnavailable(
                f"run execution directory is already locked: {run_dir}"
            ) from exc
    else:
        try:
            opened = os.fstat(run_descriptor)
        except OSError as exc:
            raise FileLockUnavailable(
                f"run execution descriptor is unavailable: {run_dir}"
            ) from exc
        actual_identity = opened.st_dev, opened.st_ino
        if (
            not stat.S_ISDIR(opened.st_mode)
            or expected_run_identity is None
            or actual_identity != expected_run_identity
        ):
            raise FileLockUnavailable(
                f"run execution descriptor identity changed: {run_dir}"
            )
        retained_descriptor = os.dup(run_descriptor)

    assert expected_run_identity is not None
    lock_path = run_dir / ".locks" / "create_resume.lock"
    try:
        runtime_lease = await acquire_file_lock(
            lock_path,
            wait=False,
            run_root_descriptor=retained_descriptor,
            expected_run_root_identity=expected_run_identity,
        )
        try:
            fcntl.flock(
                retained_descriptor,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as exc:
            raise FileLockUnavailable(
                f"frontend create is active for this run: {run_dir}"
            ) from exc
        lease = _RunExecutionLease(
            runtime_lease=runtime_lease,
            run_descriptor=retained_descriptor,
            identity=expected_run_identity,
        )
        runtime_lease = None
        retained_descriptor = -1
        async with _run_execution_leases_guard:
            previous = _run_execution_leases.pop(job_id, None)
            _run_execution_leases[job_id] = lease
        if previous is not None:
            await _release_run_execution_lease_value(previous)
        return lease
    finally:
        if runtime_lease is not None:
            await release_file_lock(runtime_lease)
        if retained_descriptor >= 0:
            os.close(retained_descriptor)


async def _release_run_execution_lease_value(
    lease: _RunExecutionLease | FileLockLease,
) -> None:
    if isinstance(lease, FileLockLease):
        await release_file_lock(lease)
        return
    try:
        fcntl.flock(lease.run_descriptor, fcntl.LOCK_UN)
    finally:
        try:
            os.close(lease.run_descriptor)
        finally:
            await release_file_lock(lease.runtime_lease)


async def _release_run_execution_lease(job_id: str) -> None:
    async with _run_execution_leases_guard:
        lease = _run_execution_leases.pop(job_id, None)
    if lease is not None:
        await _release_run_execution_lease_value(lease)


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
    tracked_job_ids = {
        *_bulk_generation_tasks.keys(),
        *_create_tasks.keys(),
        *_resume_tasks.keys(),
    }
    tasks = [
        *list(_bulk_generation_tasks.values()),
        *list(_create_tasks.values()),
        *list(_resume_tasks.values()),
    ]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    # A task cancelled before its coroutine takes its first step never reaches
    # the worker's finally block.  Release the pre-acquired lease explicitly;
    # this is idempotent for workers that already released their own lease.
    for job_id in tracked_job_ids:
        await _release_run_execution_lease(job_id)
    _bulk_generation_tasks.clear()
    _create_tasks.clear()
    _resume_tasks.clear()
    if _codex_client:
        await _codex_client.stop()
        _codex_client = None


def _toc_run_command(*, topic: str, run_id: str) -> str:
    topic_arg = json.dumps(topic, ensure_ascii=False)
    run_dir_arg = json.dumps(f"output/{run_id}", ensure_ascii=False)
    return f"/toc-run {topic_arg} --dry-run --run-dir {run_dir_arg}"


def _toc_immersive_command(
    *,
    topic: str,
    source: str | None = None,
    run_id: str,
    stop_target: str = "p680",
    experience: str = "cinematic_story",
    source_run_id: str | None = None,
    target_duration_seconds: int = 300,
    review_mode: Literal["standard", "preapproved"] = "standard",
) -> str:
    source_text = (source or "").strip() or topic
    if stop_target not in {"p650", "p680"}:
        raise ValueError("stop_target must be p650 or p680")
    if not 300 <= target_duration_seconds <= 1200:
        raise ValueError("target_duration_seconds must be between 300 and 1200")
    if review_mode not in {"standard", "preapproved"}:
        raise ValueError("review_mode must be standard or preapproved")
    if experience == CREATE_MODE_WORLD_WALK and not source_run_id:
        raise ValueError("source_run_id is required for world_walk")
    payload = {
        "topic": topic,
        "source": source_text,
        "run_dir": f"output/{run_id}",
        "stop_target": stop_target,
        "experience": experience,
        "target_duration_seconds": target_duration_seconds,
        "handoff": "generated_outputs",
        "required_skill": "toc-immersive-runner",
        "expected_skill_path": str(_toc_immersive_skill_path().relative_to(ROOT)),
    }
    if source_run_id:
        payload["source_run"] = f"output/{source_run_id}"
    return "\n".join(
        [
            "Use $toc-immersive-runner.",
            "",
            f"Create a ToC immersive {experience} run from this request.",
            f"Run the canonical p100-{stop_target} production workflow in one skill invocation.",
            "Do not execute or depend on Claude slash commands.",
            "Do not create a second run directory.",
            "Do not return success for placeholder scaffold output.",
            "Do not replace the canonical stage route with a shortcut or postprocess patch.",
            "Generate directly without reviewer agents, scores or review certificates.",
            "",
            "Request JSON:",
            json.dumps(payload, ensure_ascii=False, indent=2),
        ]
    )


def _toc_world_walk_command(
    *,
    topic: str,
    run_id: str,
    source_run_id: str,
    target_duration_seconds: int = 300,
    review_mode: Literal["standard", "preapproved"] = "standard",
) -> str:
    return _toc_immersive_command(
        topic=topic,
        run_id=run_id,
        experience=CREATE_MODE_WORLD_WALK,
        source_run_id=source_run_id,
        target_duration_seconds=target_duration_seconds,
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


async def _set_create_job(
    job_id: str,
    patch: dict[str, Any],
    *,
    write_run_log: bool = True,
) -> None:
    log_payload: dict[str, Any] | None = None
    async with _create_jobs_lock:
        job = _create_jobs.get(job_id)
        if job:
            job.update(patch)
            log_payload = dict(job)
    await asyncio.to_thread(_update_process_record_best_effort, job_id=job_id, patch=patch)
    if log_payload and write_run_log:
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


def _reconcile_create_job_with_run_state(job: dict[str, Any]) -> dict[str, Any]:
    """Project a canonical run failure over stale in-memory/DB job state.

    The process store is optional and can outlive the worker that owns the
    append-only state.  A successful status lookup must therefore never return
    ``running`` after the run itself has published a terminal failure.
    """

    run_id = str(job.get("runId") or "").strip()
    if not run_id:
        return job
    job_status = str(job.get("status") or "").strip().lower()
    if job_status not in {"queued", "running", "inspecting"}:
        _create_job_failure_baselines.pop(str(job.get("jobId") or ""), None)
        return job
    try:
        progress = read_run_progress(safe_run_dir(run_id, ROOT), validate_request_outputs=False)
    except (FileNotFoundError, OSError, ValueError):
        return job
    failure = progress.get("failure")
    if not isinstance(failure, dict) or not bool(failure.get("terminal")):
        _create_job_failure_baselines.pop(str(job.get("jobId") or ""), None)
        return job
    failure_signature = (
        str(failure.get("stage") or ""),
        str(failure.get("runtimeStage") or ""),
        str(failure.get("message") or ""),
    )
    baseline = _create_job_failure_baselines.get(str(job.get("jobId") or ""))
    if baseline is not None and baseline == failure_signature:
        # A resume starts from a stopped run.  Keep the new job running until
        # its worker publishes a fresh active state or a new terminal error.
        resume_task = _resume_tasks.get(str(job.get("jobId") or ""))
        if resume_task is not None and not resume_task.done():
            return job
    if baseline is not None:
        _create_job_failure_baselines.pop(str(job.get("jobId") or ""), None)
    stage = str(failure.get("stage") or "").strip()
    message = str(failure.get("message") or "").strip()
    error_code = str(failure.get("errorKind") or "").strip() or None
    return {
        **job,
        "status": "failed",
        "message": "作成失敗",
        "error": str(job.get("error") or "").strip() or message or "ToC作成に失敗しました",
        "errorCode": str(job.get("errorCode") or "").strip() or error_code,
        **(
            {"currentProcess": stage, "currentProcessNumber": _process_number(stage)}
            if stage
            else {}
        ),
    }


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


def _slot_reaches_process(slot: str, status: str) -> bool:
    if slot == "p680":
        # p680 is a handoff boundary.  Only a real review handoff/completion
        # reaches it; a failed or skipped placeholder must remain resumable.
        return status in {"awaiting_approval", "approved", "done"}
    if status in {"done", "skipped"}:
        return True
    if status in {"awaiting_approval", "approved"}:
        return slot in SLOT_AWAITING_APPROVAL_ALLOWED
    return False


def _runtime_failure_process_number(state: dict[str, str]) -> int:
    failure_stage = str(state.get("runtime.failure.stage") or "").strip().lower()
    if not failure_stage:
        return 0
    mapped_slot = CREATION_SLOT_BY_STAGE.get(failure_stage, failure_stage)
    process_number = _process_number(mapped_slot)
    if _process_label(process_number) not in P680_FIXED_SLOTS:
        return 0
    # A failure while publishing p680 has not reached the handoff boundary.
    return 0 if process_number >= 680 else process_number


def _current_process_number_for_run(run_id: str) -> int:
    try:
        state = parse_state_file(safe_run_dir(run_id, ROOT) / "state.txt")
    except Exception:
        return 0
    current = 0
    first_unreached = 0
    for slot in P680_FIXED_SLOTS:
        status = (state.get(f"slot.{slot}.status") or "").strip().lower()
        if _slot_reaches_process(slot, status):
            current = _process_number(slot)
            continue
        first_unreached = _process_number(slot)
        if status == "failed" and slot != "p680":
            current = first_unreached
        break
    if current == 680:
        return current
    failure_process = _runtime_failure_process_number(state)
    if failure_process and failure_process == first_unreached:
        return failure_process
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


_REGENERATABLE_ASSET_OUTPUT_DIRS = {
    "characters",
    "location",
    "locations",
    "objects",
    "scenes",
    "style",
    "styles",
}


def _canonical_regeneration_output(
    run_dir: Path,
    value: str,
    *,
    kind: str,
) -> tuple[str, Path]:
    raw = str(value or "").strip()
    if not raw or "\\" in raw:
        raise ValueError("output is not a canonical POSIX path")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("output contains a non-canonical path segment")
    if len(parts) < 3 or parts[0] != "assets":
        raise ValueError("output must be a canonical assets path")
    if kind == "scene":
        if parts[1] != "scenes":
            raise ValueError("scene output must be under assets/scenes")
    elif kind == "asset":
        if parts[1] not in _REGENERATABLE_ASSET_OUTPUT_DIRS:
            raise ValueError("asset output is not in a generated asset directory")
    else:
        raise ValueError("request kind must be asset or scene")
    if Path(parts[-1]).suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError("output must use a supported image suffix")
    relative = "/".join(parts)
    return relative, run_dir.resolve().joinpath(*parts)


def _validate_generation_destination_nofollow(
    run_dir: Path,
    value: str,
    *,
    kind: str,
) -> tuple[str, Path]:
    relative, destination = _canonical_regeneration_output(
        run_dir,
        value,
        kind=kind,
    )
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if not nofollow or not directory:
        raise ValueError("platform lacks no-follow directory operations")

    parts = relative.split("/")
    current_fd = -1
    try:
        current_fd = os.open(
            run_dir.resolve(),
            os.O_RDONLY | directory | cloexec | nofollow,
        )
        for index, part in enumerate(parts):
            is_destination = index == len(parts) - 1
            try:
                current_stat = os.stat(
                    part,
                    dir_fd=current_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                return relative, destination
            if stat.S_ISLNK(current_stat.st_mode):
                raise ValueError(f"generation destination is a symlink at {part}")
            if is_destination:
                if not stat.S_ISREG(current_stat.st_mode):
                    raise ValueError("generation destination is not a regular file")
                if current_stat.st_nlink != 1:
                    raise ValueError("generation destination has multiple hard links")
                return relative, destination
            if not stat.S_ISDIR(current_stat.st_mode):
                raise ValueError(f"generation destination parent is not a directory at {part}")
            next_fd = os.open(
                part,
                os.O_RDONLY | directory | cloexec | nofollow,
                dir_fd=current_fd,
            )
            os.close(current_fd)
            current_fd = next_fd
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError(f"unsafe generation destination: {exc}") from exc
    finally:
        if current_fd >= 0:
            os.close(current_fd)
    return relative, destination


class _UnsafeGenerationDestinationError(ValueError):
    pass


@dataclass(frozen=True)
class _GenerationDestinationCopyReceipt:
    destination: Path
    output_sha256: str
    size_bytes: int


def _validate_image_descriptor(
    descriptor: int,
    *,
    suffix: str,
    label: str,
) -> os.stat_result:
    file_stat = os.fstat(descriptor)
    if not stat.S_ISREG(file_stat.st_mode):
        raise ValueError(f"{label} is not a regular file")
    if file_stat.st_size <= 0:
        raise ValueError(f"{label} is empty")
    if file_stat.st_size > MAX_IMAGE_BYTES:
        raise ValueError(f"{label} is too large")
    header = os.pread(descriptor, 16, 0)
    normalized_suffix = suffix.lower()
    if (
        normalized_suffix == ".png"
        and not header.startswith(b"\x89PNG\r\n\x1a\n")
    ):
        raise ValueError(f"{label} has invalid png magic bytes")
    if (
        normalized_suffix in {".jpg", ".jpeg"}
        and not header.startswith(b"\xff\xd8\xff")
    ):
        raise ValueError(f"{label} has invalid jpeg magic bytes")
    if normalized_suffix == ".webp" and not (
        header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    ):
        raise ValueError(f"{label} has invalid webp magic bytes")
    return file_stat


def _sha256_stable_image_descriptor(
    descriptor: int,
    *,
    label: str,
) -> tuple[str, int]:
    before = os.fstat(descriptor)
    digest = hashlib.sha256()
    offset = 0
    while offset < before.st_size:
        chunk = os.pread(
            descriptor,
            min(1024 * 1024, before.st_size - offset),
            offset,
        )
        if not chunk:
            raise _UnsafeGenerationDestinationError(
                f"{label} changed while hashing"
            )
        digest.update(chunk)
        offset += len(chunk)
    after = os.fstat(descriptor)
    if (
        (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or after.st_ctime_ns != before.st_ctime_ns
        or os.pread(descriptor, 1, offset)
    ):
        raise _UnsafeGenerationDestinationError(
            f"{label} changed while hashing"
        )
    return digest.hexdigest(), offset


def _open_generation_directory_nofollow(
    parent_descriptor: int,
    parts: list[str],
    *,
    create: bool,
) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    current_descriptor = os.dup(parent_descriptor)
    try:
        for part in parts:
            try:
                next_descriptor = os.open(
                    part,
                    os.O_RDONLY | directory | cloexec | nofollow,
                    dir_fd=current_descriptor,
                )
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(part, mode=0o755, dir_fd=current_descriptor)
                except FileExistsError:
                    pass
                next_descriptor = os.open(
                    part,
                    os.O_RDONLY | directory | cloexec | nofollow,
                    dir_fd=current_descriptor,
                )
            os.close(current_descriptor)
            current_descriptor = next_descriptor
        return current_descriptor
    except BaseException:
        os.close(current_descriptor)
        raise


def _assert_generation_parent_is_current(
    run_dir: Path,
    *,
    root_identity: tuple[int, int],
    parent_parts: list[str],
    parent_identity: tuple[int, int],
) -> None:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    fresh_root_descriptor = -1
    fresh_parent_descriptor = -1
    try:
        fresh_root_descriptor = os.open(
            run_dir,
            os.O_RDONLY | directory | cloexec | nofollow,
        )
        fresh_root_stat = os.fstat(fresh_root_descriptor)
        if (fresh_root_stat.st_dev, fresh_root_stat.st_ino) != root_identity:
            raise _UnsafeGenerationDestinationError(
                "generation run directory changed during copy"
            )
        fresh_parent_descriptor = _open_generation_directory_nofollow(
            fresh_root_descriptor,
            parent_parts,
            create=False,
        )
        fresh_parent_stat = os.fstat(fresh_parent_descriptor)
        if (
            fresh_parent_stat.st_dev,
            fresh_parent_stat.st_ino,
        ) != parent_identity:
            raise _UnsafeGenerationDestinationError(
                "generation destination parent changed during copy"
            )
    except _UnsafeGenerationDestinationError:
        raise
    except OSError as exc:
        raise _UnsafeGenerationDestinationError(
            f"generation destination parent became unsafe during copy: {exc}"
        ) from exc
    finally:
        if fresh_parent_descriptor >= 0:
            os.close(fresh_parent_descriptor)
        if fresh_root_descriptor >= 0:
            os.close(fresh_root_descriptor)


def _ensure_generation_destination_entry_is_safe(
    parent_descriptor: int,
    name: str,
) -> os.stat_result | None:
    try:
        destination_stat = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(destination_stat.st_mode):
        raise _UnsafeGenerationDestinationError(
            "generation destination is a symlink"
        )
    if not stat.S_ISREG(destination_stat.st_mode):
        raise _UnsafeGenerationDestinationError(
            "generation destination is not a regular file"
        )
    if destination_stat.st_nlink != 1:
        raise _UnsafeGenerationDestinationError(
            "generation destination has multiple hard links"
        )
    return destination_stat


def _copy_saved_image_to_generation_destination_nofollow(
    *,
    run_dir: Path,
    saved_path: Path,
    output: str,
    kind: str,
) -> _GenerationDestinationCopyReceipt:
    binding = _assert_bound_run_root(run_dir)
    relative, destination = _canonical_regeneration_output(
        run_dir,
        output,
        kind=kind,
    )
    require_image_file(saved_path)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if not nofollow or not directory:
        raise _UnsafeGenerationDestinationError(
            "platform lacks no-follow directory operations"
        )

    source_descriptor = -1
    root_descriptor = -1
    parent_descriptor = -1
    temporary_descriptor = -1
    temporary_name = ""
    backup_name = ""
    preserve_backup = False
    parts = relative.split("/")
    parent_parts = parts[:-1]
    destination_name = parts[-1]
    try:
        try:
            source_descriptor = os.open(
                saved_path,
                os.O_RDONLY | cloexec | nofollow,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"saved image not found: {saved_path}"
            ) from exc
        except OSError as exc:
            raise ValueError(f"saved image is unsafe: {exc}") from exc
        source_stat = _validate_image_descriptor(
            source_descriptor,
            suffix=saved_path.suffix,
            label="saved image",
        )

        try:
            root_descriptor = os.open(
                run_dir,
                os.O_RDONLY | directory | cloexec | nofollow,
            )
            root_stat = os.fstat(root_descriptor)
            root_identity = (root_stat.st_dev, root_stat.st_ino)
            if binding is not None and root_identity != binding.identity:
                raise _UnsafeGenerationDestinationError(
                    "generation run directory no longer matches its "
                    "frontend/resume binding"
                )
            parent_descriptor = _open_generation_directory_nofollow(
                root_descriptor,
                parent_parts,
                create=True,
            )
            parent_stat = os.fstat(parent_descriptor)
            parent_identity = (parent_stat.st_dev, parent_stat.st_ino)
            _ensure_generation_destination_entry_is_safe(
                parent_descriptor,
                destination_name,
            )
        except _UnsafeGenerationDestinationError:
            raise
        except OSError as exc:
            raise _UnsafeGenerationDestinationError(
                f"unsafe generation destination: {exc}"
            ) from exc

        temporary_name = (
            f".toc-image-{uuid.uuid4().hex}.tmp{destination.suffix.lower()}"
        )
        try:
            temporary_descriptor = os.open(
                temporary_name,
                os.O_RDWR
                | os.O_CREAT
                | os.O_EXCL
                | cloexec
                | nofollow,
                0o600,
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise _UnsafeGenerationDestinationError(
                f"could not create a safe destination temporary file: {exc}"
            ) from exc

        bytes_written = 0
        copied_digest = hashlib.sha256()
        while True:
            chunk = os.read(source_descriptor, 1024 * 1024)
            if not chunk:
                break
            bytes_written += len(chunk)
            if bytes_written > MAX_IMAGE_BYTES:
                raise ValueError("saved image is too large")
            copied_digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(temporary_descriptor, view)
                if written <= 0:
                    raise OSError(
                        "could not make progress writing destination image"
                    )
                view = view[written:]
        os.fchmod(temporary_descriptor, stat.S_IMODE(source_stat.st_mode))
        os.fsync(temporary_descriptor)
        temporary_stat = _validate_image_descriptor(
            temporary_descriptor,
            suffix=destination.suffix,
            label="copied image",
        )

        _assert_generation_parent_is_current(
            run_dir,
            root_identity=root_identity,
            parent_parts=parent_parts,
            parent_identity=parent_identity,
        )
        _assert_bound_run_root(run_dir)
        previous_destination_stat = (
            _ensure_generation_destination_entry_is_safe(
                parent_descriptor,
                destination_name,
            )
        )
        previous_destination_identity = (
            (
                previous_destination_stat.st_dev,
                previous_destination_stat.st_ino,
            )
            if previous_destination_stat is not None
            else None
        )
        # A held directory descriptor prevents symlink traversal, but the
        # directory can still be renamed after the ancestry check. Preserve
        # the old entry so a failed post-commit check can restore it through
        # that same descriptor. For a previously absent entry, link-based
        # publication lets rollback remove only the inode created here.
        if previous_destination_stat is not None:
            backup_name = (
                f".toc-image-backup-{uuid.uuid4().hex}.tmp"
                f"{destination.suffix.lower()}"
            )
            try:
                os.link(
                    destination_name,
                    backup_name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                backup_stat = os.stat(
                    backup_name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                current_destination_stat = os.stat(
                    destination_name,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise _UnsafeGenerationDestinationError(
                    f"could not preserve destination rollback state: {exc}"
                ) from exc
            backup_identity = (backup_stat.st_dev, backup_stat.st_ino)
            current_destination_identity = (
                current_destination_stat.st_dev,
                current_destination_stat.st_ino,
            )
            if (
                not stat.S_ISREG(backup_stat.st_mode)
                or backup_identity != previous_destination_identity
                or current_destination_identity
                != previous_destination_identity
            ):
                raise _UnsafeGenerationDestinationError(
                    "generation destination changed while preserving "
                    "rollback state"
                )
        else:
            current_destination_stat = (
                _ensure_generation_destination_entry_is_safe(
                    parent_descriptor,
                    destination_name,
                )
            )
            if current_destination_stat is not None:
                raise _UnsafeGenerationDestinationError(
                    "generation destination appeared during copy"
                )

        committed = False
        committed_identity = (
            temporary_stat.st_dev,
            temporary_stat.st_ino,
        )
        try:
            if previous_destination_stat is not None:
                os.replace(
                    temporary_name,
                    destination_name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                )
                temporary_name = ""
                committed = True
            else:
                os.link(
                    temporary_name,
                    destination_name,
                    src_dir_fd=parent_descriptor,
                    dst_dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                committed = True
                os.unlink(temporary_name, dir_fd=parent_descriptor)
                temporary_name = ""

            _assert_generation_parent_is_current(
                run_dir,
                root_identity=root_identity,
                parent_parts=parent_parts,
                parent_identity=parent_identity,
            )
            committed_stat = (
                _ensure_generation_destination_entry_is_safe(
                    parent_descriptor,
                    destination_name,
                )
            )
            if committed_stat is None or (
                committed_stat.st_dev,
                committed_stat.st_ino,
            ) != committed_identity:
                raise _UnsafeGenerationDestinationError(
                    "generation destination changed after atomic copy"
                )
            _validate_image_descriptor(
                temporary_descriptor,
                suffix=destination.suffix,
                label="committed image",
            )
            committed_output_sha256, committed_size_bytes = (
                _sha256_stable_image_descriptor(
                    temporary_descriptor,
                    label="committed image",
                )
            )
            if (
                committed_output_sha256 != copied_digest.hexdigest()
                or committed_size_bytes != bytes_written
            ):
                raise _UnsafeGenerationDestinationError(
                    "committed image differs from copied image bytes"
                )
            if backup_name:
                os.unlink(backup_name, dir_fd=parent_descriptor)
                backup_name = ""
        except BaseException as exc:
            rollback_error: BaseException | None = None
            if committed:
                try:
                    if backup_name:
                        try:
                            current_stat = os.stat(
                                destination_name,
                                dir_fd=parent_descriptor,
                                follow_symlinks=False,
                            )
                        except FileNotFoundError as missing_destination:
                            raise _UnsafeGenerationDestinationError(
                                "destination disappeared before rollback"
                            ) from missing_destination
                        if (
                            current_stat.st_dev,
                            current_stat.st_ino,
                        ) != committed_identity:
                            raise _UnsafeGenerationDestinationError(
                                "destination changed before rollback"
                            )
                        rollback_stat = os.stat(
                            backup_name,
                            dir_fd=parent_descriptor,
                            follow_symlinks=False,
                        )
                        if (
                            not stat.S_ISREG(rollback_stat.st_mode)
                            or (
                                rollback_stat.st_dev,
                                rollback_stat.st_ino,
                            )
                            != previous_destination_identity
                        ):
                            raise _UnsafeGenerationDestinationError(
                                "destination rollback state changed"
                            )
                        os.replace(
                            backup_name,
                            destination_name,
                            src_dir_fd=parent_descriptor,
                            dst_dir_fd=parent_descriptor,
                        )
                        backup_name = ""
                    else:
                        try:
                            current_stat = os.stat(
                                destination_name,
                                dir_fd=parent_descriptor,
                                follow_symlinks=False,
                            )
                        except FileNotFoundError:
                            current_stat = None
                        if current_stat is not None and (
                            current_stat.st_dev,
                            current_stat.st_ino,
                        ) == committed_identity:
                            os.unlink(
                                destination_name,
                                dir_fd=parent_descriptor,
                            )
                except BaseException as rollback_exc:
                    rollback_error = rollback_exc
            if rollback_error is not None:
                preserve_backup = True
                raise _UnsafeGenerationDestinationError(
                    "atomic destination rollback failed: "
                    f"{rollback_error}"
                ) from exc
            raise
        with suppress(OSError):
            os.fsync(parent_descriptor)
        return _GenerationDestinationCopyReceipt(
            destination=destination,
            output_sha256=committed_output_sha256,
            size_bytes=committed_size_bytes,
        )
    finally:
        if temporary_descriptor >= 0:
            os.close(temporary_descriptor)
        if temporary_name and parent_descriptor >= 0:
            with suppress(OSError):
                os.unlink(temporary_name, dir_fd=parent_descriptor)
        if (
            backup_name
            and not preserve_backup
            and parent_descriptor >= 0
        ):
            with suppress(OSError):
                os.unlink(backup_name, dir_fd=parent_descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
        if root_descriptor >= 0:
            os.close(root_descriptor)
        if source_descriptor >= 0:
            os.close(source_descriptor)


def _current_image_request_paths(
    run_dir: Path,
) -> tuple[dict[str, dict[str, Path]], list[str]]:
    paths: dict[str, dict[str, Path]] = {"asset": {}, "scene": {}}
    errors: list[str] = []
    for kind in ("asset", "scene"):
        try:
            items = load_request_items(run_dir, kind)
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as exc:
            errors.append(
                f"current {kind} request snapshot is unreadable or malformed ({exc})"
            )
            continue
        for item in items:
            value = str(item.output or "").strip()
            if not value:
                continue
            try:
                relative, path = _validate_generation_destination_nofollow(
                    run_dir,
                    value,
                    kind=kind,
                )
            except ValueError as exc:
                errors.append(
                    f"unsafe current {kind} request output ignored: {value} ({exc})"
                )
                continue
            paths[kind][relative] = path
    return paths, errors


@dataclass(frozen=True)
class _P680RegenerationPlanClassification:
    targets: dict[str, Path]
    asset_targets: frozenset[str]
    actions: frozenset[str]
    errors: tuple[str, ...]

    @property
    def requires_canonical_p500(self) -> bool:
        return "regenerate_p500_reference_first" in self.actions


def _p680_plan_classification_error(
    message: str,
) -> _P680RegenerationPlanClassification:
    return _P680RegenerationPlanClassification(
        targets={},
        asset_targets=frozenset(),
        actions=frozenset(),
        errors=(message,),
    )


def _inspect_p680_regeneration_plan(
    run_dir: Path, *, current_request_paths: dict[str, dict[str, Path]],
) -> _P680RegenerationPlanClassification:
    """Classify missing/stale outputs from current requests, never review reports."""
    _assert_bound_run_root(run_dir)
    targets: dict[str, Path] = {}
    asset_targets: set[str] = set()
    actions: set[str] = set()
    errors: list[str] = []
    for kind in ("asset", "scene"):
        try:
            items = load_request_items(run_dir, kind)
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as exc:
            errors.append(f"invalid current {kind} requests: {exc}")
            continue
        for item in items:
            relative = str(item.output or "").strip()
            path = current_request_paths.get(kind, {}).get(relative)
            if path is None:
                errors.append(f"output is not bound to a safe current request: {relative}")
                continue
            valid = False
            if path.is_file():
                try:
                    validate_image_bytes(path)
                    refs = [resolve_run_relative(run_dir, ref) for ref in item.references]
                    valid = _has_completed_app_server_image_provenance(
                        run_dir, item_id=str(item.id), destination=path,
                        prompt_sha256=hashlib.sha256(str(item.prompt).encode("utf-8")).hexdigest(),
                        reference_sha256s=[_file_sha256(ref) for ref in refs],
                        request_revision=getattr(item, "request_revision", None),
                        request_digest=getattr(item, "request_digest", None),
                        compiler_version=getattr(item, "compiler_version", None),
                        source_digest=getattr(item, "source_digest", None),
                    )
                except (OSError, ValueError):
                    valid = False
            if not valid:
                targets[relative] = path
                actions.add("regenerate_p500_reference_first" if kind == "asset" else "regenerate_p600_scene")
                if kind == "asset":
                    asset_targets.add(relative)
    return _P680RegenerationPlanClassification(
        targets=targets, asset_targets=frozenset(asset_targets),
        actions=frozenset(actions), errors=tuple(errors),
    )


def _p680_regeneration_targets(
    run_dir: Path,
    *,
    current_request_paths: dict[str, dict[str, Path]],
) -> tuple[dict[str, Path], list[str]]:
    classification = _inspect_p680_regeneration_plan(
        run_dir,
        current_request_paths=current_request_paths,
    )
    return classification.targets, list(classification.errors)


def _classify_p680_regeneration_plan(
    run_dir: Path,
) -> _P680RegenerationPlanClassification:
    current_request_paths, request_errors = _current_image_request_paths(run_dir)
    classification = _inspect_p680_regeneration_plan(
        run_dir,
        current_request_paths=current_request_paths,
    )
    if not request_errors:
        return classification
    return _P680RegenerationPlanClassification(
        targets=classification.targets,
        asset_targets=classification.asset_targets,
        actions=classification.actions,
        errors=tuple([*request_errors, *classification.errors]),
    )


def _unlink_regeneration_output_nofollow(
    run_dir: Path,
    relative: str,
    *,
    expected_identity: tuple[int, int, int] | None,
) -> tuple[bool, str | None]:
    if expected_identity is None:
        return False, None
    try:
        was_deleted = unlink_run_file(
            run_dir,
            relative,
            missing_ok=True,
            expected_identity=expected_identity,
        )
        return was_deleted, None
    except FileNotFoundError:
        return False, None
    except (OSError, RunRootBindingError, ValueError) as exc:
        return False, f"unsafe regeneration path: {exc}"


def _inspect_regeneration_output_nofollow(
    run_dir: Path,
    relative: str,
) -> tuple[tuple[int, int, int] | None, str | None]:
    """Capture the exact bound leaf identity that a later delete may remove."""

    binding = _assert_bound_run_root(run_dir)
    if binding is None:
        return None, "regeneration deletion requires a retained run binding"
    parts = relative.split("/")
    parent_descriptor = -1
    try:
        parent_descriptor = _open_generation_directory_nofollow(
            binding.descriptor,
            parts[:-1],
            create=False,
        )
        try:
            target_stat = os.stat(
                parts[-1],
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return None, None
        if stat.S_ISLNK(target_stat.st_mode):
            return None, "regeneration target is a symlink"
        if not stat.S_ISREG(target_stat.st_mode):
            return None, "regeneration target is not a regular file"
        if target_stat.st_nlink != 1:
            return None, "regeneration target has multiple hard links"
        return (
            target_stat.st_dev,
            target_stat.st_ino,
            stat.S_IFMT(target_stat.st_mode),
        ), None
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        return None, f"unsafe regeneration path: {exc}"
    finally:
        if parent_descriptor >= 0:
            os.close(parent_descriptor)


def _preserved_image_outputs_nofollow(
    run_dir: Path,
    *,
    image_suffixes: set[str],
) -> tuple[list[str], str | None]:
    binding = _assert_bound_run_root(run_dir)
    if binding is None:
        return [], "could not enumerate preserved images without a retained run binding"
    preserved: list[str] = []

    def walk(directory_descriptor: int, prefix: Path) -> None:
        for name in sorted(os.listdir(directory_descriptor)):
            entry_stat = os.stat(
                name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            relative = prefix / name
            if stat.S_ISDIR(entry_stat.st_mode):
                child_descriptor = os.open(
                    name,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_descriptor,
                )
                try:
                    opened = os.fstat(child_descriptor)
                    if (
                        not stat.S_ISDIR(opened.st_mode)
                        or (opened.st_dev, opened.st_ino)
                        != (entry_stat.st_dev, entry_stat.st_ino)
                    ):
                        raise RunRootBindingError(
                            f"preserved image directory changed while opening: {relative}"
                        )
                    walk(child_descriptor, relative)
                finally:
                    os.close(child_descriptor)
                continue
            if relative.suffix.lower() not in image_suffixes:
                continue
            if not (
                stat.S_ISREG(entry_stat.st_mode)
                or stat.S_ISLNK(entry_stat.st_mode)
            ):
                continue
            preserved.append(relative.as_posix())

    assets_descriptor = -1
    try:
        assets_descriptor = _open_generation_directory_nofollow(
            binding.descriptor,
            ["assets"],
            create=False,
        )
        walk(assets_descriptor, Path("assets"))
    except FileNotFoundError:
        return [], None
    except (OSError, ValueError) as exc:
        return sorted(preserved), f"could not enumerate preserved images safely: {exc}"
    finally:
        if assets_descriptor >= 0:
            os.close(assets_descriptor)
    return sorted(preserved), None


def _delete_existing_images_for_image_resume(run_dir: Path) -> dict[str, Any]:
    binding = _assert_bound_run_root(run_dir)
    if binding is None:
        try:
            named = os.stat(run_dir, follow_symlinks=False)
        except OSError as exc:
            raise RunRootBindingError(
                f"image resume run root is unavailable: {run_dir}"
            ) from exc
        if not stat.S_ISDIR(named.st_mode):
            raise RunRootBindingError(
                f"image resume run root is not a real directory: {run_dir}"
            )
        with bind_run_root(
            run_dir,
            expected_identity=(named.st_dev, named.st_ino),
        ):
            return _delete_existing_images_for_image_resume(run_dir)

    try:
        assets_stat = os.stat(
            "assets",
            dir_fd=binding.descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        assets_stat = None
        assets_error = None
    except OSError as exc:
        assets_stat = None
        assets_error = f"unsafe assets directory: {exc}"
    else:
        assets_error = None

    image_suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    deleted: list[str] = []
    preserved: list[str] = []
    classification = _classify_p680_regeneration_plan(run_dir)
    errors = list(classification.errors)
    if classification.requires_canonical_p500:
        errors.append(
            "canonical p500 resume is required for the current p680 "
            "asset/reference regeneration plan"
        )
    if assets_stat is None:
        if assets_error:
            errors.append(assets_error)
        return {
            "deletedCount": 0,
            "deleted": [],
            "preservedCount": 0,
            "preserved": [],
            "errors": errors[:200],
            "requiresCanonicalP500": classification.requires_canonical_p500,
            "assetTargets": sorted(classification.asset_targets)[:200],
            "regenerationActions": sorted(classification.actions),
        }
    if stat.S_ISLNK(assets_stat.st_mode):
        return {
            "deletedCount": 0,
            "deleted": [],
            "preservedCount": 0,
            "preserved": [],
            "errors": [*errors, "unsafe assets directory symlink"][:200],
            "requiresCanonicalP500": classification.requires_canonical_p500,
            "assetTargets": sorted(classification.asset_targets)[:200],
            "regenerationActions": sorted(classification.actions),
        }
    if not stat.S_ISDIR(assets_stat.st_mode):
        return {
            "deletedCount": 0,
            "deleted": [],
            "preservedCount": 0,
            "preserved": [],
            "errors": [*errors, "unsafe assets entry is not a directory"][:200],
            "requiresCanonicalP500": classification.requires_canonical_p500,
            "assetTargets": sorted(classification.asset_targets)[:200],
            "regenerationActions": sorted(classification.actions),
        }
    regeneration_targets = (
        {}
        if classification.requires_canonical_p500
        else classification.targets
    )
    deletion_targets: list[tuple[str, tuple[int, int, int] | None]] = []
    for relative, _path in sorted(regeneration_targets.items()):
        if Path(relative).suffix.lower() not in image_suffixes:
            errors.append(f"regeneration target is not a supported image: {relative}")
            continue
        try:
            _canonical_regeneration_output(
                run_dir,
                relative,
                kind="scene" if relative.startswith("assets/scenes/") else "asset",
            )
        except ValueError as exc:
            errors.append(f"unsafe regeneration target ignored: {relative} ({exc})")
            continue
        expected_identity, inspection_error = (
            _inspect_regeneration_output_nofollow(run_dir, relative)
        )
        if inspection_error:
            errors.append(f"{inspection_error}: {relative}")
            continue
        deletion_targets.append((relative, expected_identity))

    # Validation is deliberately complete before the first unlink. A mixed
    # plan containing one unsafe target must preserve every otherwise-safe
    # image so the caller can fail closed without a partial regeneration set.
    if not errors:
        for relative, expected_identity in deletion_targets:
            was_deleted, error = _unlink_regeneration_output_nofollow(
                run_dir,
                relative,
                expected_identity=expected_identity,
            )
            if was_deleted:
                deleted.append(relative)
            elif error:
                errors.append(f"{error}: {relative}")
                break
    preserved, preserved_error = _preserved_image_outputs_nofollow(
        run_dir,
        image_suffixes=image_suffixes,
    )
    if preserved_error:
        errors.append(preserved_error)
    return {
        "deletedCount": len(deleted),
        "deleted": deleted[:200],
        "preservedCount": len(preserved),
        "preserved": preserved[:200],
        "errors": errors[:200],
        "requiresCanonicalP500": classification.requires_canonical_p500,
        "assetTargets": sorted(classification.asset_targets)[:200],
        "regenerationActions": sorted(classification.actions),
        "reason": (
            "hash-aware partial resume deletes only current request paths named "
            "by the p680 visual regeneration plan"
        ),
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
                # Current cinematic authoring owns cut counts explicitly. The legacy
                # beat-per-cut minima are not part of that contract.
                cinematic = (data.get('video_metadata') or {}).get('cinematic_direction_contract') == 'cinematic_direction_v1'
                if cinematic:
                    distinct_minimum, event_minimum = selected_minimum, 0
                    if selected_minimum != len(cuts):
                        issues.append(f"scene {scene_id}: authored cut count differs from actual cuts")
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


def _prepare_image_prompt_request_revision(
    run_dir: Path,
    *,
    provider_ready: bool = True,
) -> str:
    """Bind concrete reference bytes to the current provider request."""

    snapshot_path = run_dir / "image_generation_request_snapshot.json"
    try:
        draft_snapshot = load_request_snapshot(
            snapshot_path,
            run_dir=run_dir,
            verify_references=False,
        )
        if not provider_ready:
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    "generation.image_prompt.request_freeze.status": "draft",
                    "generation.image_prompt.request_freeze.reference_mode": "deferred_references",
                    "generation.image_prompt.request_freeze.draft_revision": draft_snapshot.request_revision,
                },
            )
            return draft_snapshot.request_revision
        state = parse_state_file(run_dir / "state.txt")
        is_frozen = state.get("generation.image_prompt.request_freeze.status") == "frozen"
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
                    "generation.image_prompt.request_freeze.status": "draft",
                    "generation.image_prompt.request_freeze.provider_ready_revision": (
                        provider_snapshot.request_revision
                    ),
                    "generation.image_prompt.request_freeze.references_bound_at": now_iso(),
                },
            )
    except ImageRequestSnapshotError as exc:
        raise RuntimeError(
            f"ToC run did not reach p650: unresolved image request reference: {exc}"
        ) from exc
    return provider_snapshot.request_revision


def _validate_p650_run_core(
    run_id: str,
    *,
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
        "asset_generation_request_snapshot.json",
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
    if require_generated_asset_outputs:
        try:
            _validate_generated_outputs(run_dir, "asset")
        except MediaOutputError:
            raise
        except RuntimeError as exc:
            raise RuntimeError(f"ToC run did not reach p650: {exc}") from exc

    state = parse_state_file(run_dir / "state.txt")
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
            and slot in {"p550", "p560", "p570", "p650"}
            and (state.get(f"slot.{slot}.status") or "").lower() == "pending"
        )
    ]
    if incomplete_slots:
        raise RuntimeError(f"ToC run did not reach p650: incomplete fixed slot states {', '.join(incomplete_slots)}")


def _validate_p650_run(run_id: str) -> None:
    _validate_p650_run_core(
        run_id,
        require_provider_ready_freeze=True,
        require_generated_asset_outputs=True,
    )


def _validate_materialized_p650_run(run_id: str) -> None:
    _validate_p650_run_core(
        run_id,
        require_provider_ready_freeze=False,
        require_generated_asset_outputs=False,
    )


def _source_title_from_run_id(run_id: str) -> str:
    title = re.sub(r"_\d{8}_\d{4}(?:_\d+)?$", "", run_id).strip("_")
    return title or run_id


def _world_walk_title_from_source_run_id(source_run_id: str) -> str:
    return f"{_source_title_from_run_id(source_run_id)}の世界観を散歩してみた"


def _validate_world_walk_source_run(source_run_id: str) -> Path:
    run_dir, _relative = validate_world_walk_source_path(ROOT, Path("output") / source_run_id)
    _validate_p650_run(source_run_id)
    return run_dir


def _require_world_walk_source_run(source_run_id: str) -> Path:
    try:
        return _validate_world_walk_source_run(source_run_id)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"source run is not selectable: {exc}",
        ) from exc


def _list_world_walk_source_runs() -> list[dict[str, Any]]:
    base = ROOT / "output"
    if not base.exists():
        return []
    candidates: list[Path] = []
    for path in base.iterdir():
        if path.is_symlink() or not path.is_dir():
            continue
        try:
            candidates.append(_validate_world_walk_source_run(path.name))
        except (FileNotFoundError, ValueError, RuntimeError):
            continue
    sources: list[dict[str, Any]] = []
    for run_dir in sorted(
        candidates,
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    ):
        title = _source_title_from_run_id(run_dir.name)
        sources.append(
            {
                "id": run_dir.name,
                "title": title,
                "worldWalkTitle": f"{title}の世界観を散歩してみた",
                "path": f"output/{run_dir.name}",
                "hasAssetRequests": (
                    run_dir / "asset_generation_requests.md"
                ).is_file(),
                "hasSceneRequests": (
                    run_dir / "image_generation_requests.md"
                ).is_file(),
            }
        )
    return sources


def _validate_frontend_create_run(run_id: str, *, strict_visual_quality: bool = True) -> None:
    _validate_p650_run(run_id)
    run_dir = safe_run_dir(run_id, ROOT)
    _validate_generated_outputs(run_dir, "asset")
    _validate_generated_outputs(run_dir, "scene")


def _cleanup_unscaffolded_run(
    run_id: str,
    *,
    expected_run_identity: tuple[int, int] | None = None,
    reservation: _FrontendCreateRunReservation | None = None,
) -> None:
    if reservation is not None:
        acquired = False
        try:
            lease = reservation.lease
            if lease.name != run_id:
                return
            fcntl.flock(
                lease.descriptor,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
            acquired = True
            current = _frontend_create_named_stat(
                lease.parent_descriptor,
                lease.name,
            )
            if (
                current is None
                or _frontend_create_entry_identity(current)
                != lease.identity
            ):
                return
            if not _frontend_create_run_has_scaffold(lease):
                _quarantine_frontend_create_run(lease)
        except (FrontendCreateLockError, OSError):
            return
        finally:
            if acquired:
                with suppress(OSError):
                    fcntl.flock(
                        reservation.descriptor,
                        fcntl.LOCK_UN,
                    )
        return
    if expected_run_identity is None:
        return
    if (
        not run_id
        or "/" in run_id
        or "\\" in run_id
        or run_id in {".", ".."}
    ):
        return
    run_dir = output_root(ROOT) / run_id
    try:
        with _frontend_create_directory_lock(
            run_dir,
            expected_identity=expected_run_identity,
        ) as lease:
            if _frontend_create_run_has_scaffold(lease):
                return
            _quarantine_frontend_create_run(lease)
    except (FrontendCreateLockError, OSError):
        return


def _write_cli_process_logs(
    run_dir: Path,
    log_name: str,
    stdout: bytes,
    stderr: bytes,
    *,
    expected_run_identity: tuple[int, int] | None = None,
) -> None:
    if expected_run_identity is not None:
        try:
            write_regular_file_nofollow(
                destination_root=run_dir,
                destination_relative=f"logs/{log_name}/stdout.log",
                data=stdout.decode(
                    "utf-8",
                    errors="replace",
                ).encode("utf-8"),
                expected_destination_root_identity=expected_run_identity,
            )
            write_regular_file_nofollow(
                destination_root=run_dir,
                destination_relative=f"logs/{log_name}/stderr.log",
                data=stderr.decode(
                    "utf-8",
                    errors="replace",
                ).encode("utf-8"),
                expected_destination_root_identity=expected_run_identity,
            )
        except (OSError, ValueError) as exc:
            raise FrontendCreateLockError(
                "frontend-create run directory identity changed before "
                "CLI log publication"
            ) from exc
        return
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


class FrontendCreateLockError(RuntimeError):
    """The frontend-create ownership or path-identity check failed."""


class FrontendCreateLockOwnedError(FrontendCreateLockError):
    """Another process holds the frontend-create directory lease."""


@dataclass(frozen=True)
class _FrontendCreateDirectoryLease:
    """Retained descriptors for one verified frontend-create run entry."""

    descriptor: int
    parent_descriptor: int
    name: str
    identity: tuple[int, int]


@dataclass
class _FrontendCreateRunReservation:
    """Owned descriptors for one atomically published fresh run."""

    run_id: str
    run_dir: Path
    identity: tuple[int, int]
    descriptor: int
    parent_descriptor: int
    _closed: bool = False

    @property
    def lease(self) -> _FrontendCreateDirectoryLease:
        if self._closed:
            raise FrontendCreateLockError(
                "frontend-create reservation is already closed"
            )
        return _FrontendCreateDirectoryLease(
            descriptor=self.descriptor,
            parent_descriptor=self.parent_descriptor,
            name=self.run_id,
            identity=self.identity,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        descriptor = self.descriptor
        parent_descriptor = self.parent_descriptor
        self.descriptor = -1
        self.parent_descriptor = -1
        try:
            if descriptor >= 0:
                os.close(descriptor)
        finally:
            if parent_descriptor >= 0:
                os.close(parent_descriptor)

    def __iter__(self):
        """Preserve the former tuple contract for read-only callers."""

        yield self.run_id
        yield self.run_dir
        yield self.identity

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()


def _frontend_create_entry_identity(
    entry: os.stat_result,
) -> tuple[int, int]:
    return entry.st_dev, entry.st_ino


def _frontend_create_named_stat(
    parent_descriptor: int,
    name: str,
) -> os.stat_result | None:
    try:
        return os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise FrontendCreateLockError(
            f"frontend-create entry became unsafe: {name}"
        ) from exc


def _frontend_create_run_has_scaffold(
    lease: _FrontendCreateDirectoryLease,
) -> bool:
    """Inspect cleanup sentinels relative to the retained run descriptor."""

    try:
        opened = os.fstat(lease.descriptor)
    except OSError as exc:
        raise FrontendCreateLockError(
            "frontend-create cleanup lease became unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(opened.st_mode)
        or _frontend_create_entry_identity(opened) != lease.identity
    ):
        raise FrontendCreateLockError(
            "frontend-create cleanup lease identity changed"
        )
    return any(
        _frontend_create_named_stat(lease.descriptor, name) is not None
        for name in ("state.txt", "video_manifest.md")
    )


def _frontend_create_private_name(prefix: str) -> str:
    return f".{prefix}-{uuid.uuid4().hex}.quarantine"


def _frontend_create_public_candidate(
    slug: str,
    stamp: str,
    *,
    suffix: int | None,
    name_max: int,
) -> str:
    collision_suffix = "" if suffix is None else f"_{suffix}"
    timestamp_suffix = f"_{stamp}{collision_suffix}"
    encoded_slug = os.fsencode(slug)
    encoded_tail = os.fsencode(timestamp_suffix)
    if len(encoded_slug) + len(encoded_tail) <= name_max:
        return f"{slug}{timestamp_suffix}"

    digest_suffix = (
        "_" + hashlib.sha256(encoded_slug).hexdigest()[:12]
    )
    fixed_bytes = len(os.fsencode(digest_suffix)) + len(encoded_tail)
    budget = name_max - fixed_bytes
    if budget < 1:
        raise FrontendCreateLockError(
            "frontend-create filesystem name limit is too small"
        )
    filesystem_encoding = sys.getfilesystemencoding() or "utf-8"
    bounded_slug = encoded_slug[:budget].decode(
        filesystem_encoding,
        errors="ignore",
    ).rstrip("._-")
    if not bounded_slug:
        bounded_slug = "run"
    candidate = f"{bounded_slug}{digest_suffix}{timestamp_suffix}"
    while len(os.fsencode(candidate)) > name_max and bounded_slug:
        bounded_slug = bounded_slug[:-1].rstrip("._-")
        candidate = f"{bounded_slug or 'run'}{digest_suffix}{timestamp_suffix}"
    if len(os.fsencode(candidate)) > name_max:
        raise FrontendCreateLockError(
            "frontend-create public run name cannot fit filesystem limit"
        )
    return candidate


def _frontend_create_rename_noreplace(
    *,
    source_parent_descriptor: int,
    source_name: str,
    destination_parent_descriptor: int,
    destination_name: str,
) -> None:
    """Atomically rename without clobbering a raced destination entry."""

    libc = ctypes.CDLL(None, use_errno=True)
    encoded_source = os.fsencode(source_name)
    encoded_destination = os.fsencode(destination_name)
    if sys.platform == "darwin":
        operation = getattr(libc, "renameatx_np", None)
        flags = 0x00000004  # RENAME_EXCL
    elif sys.platform.startswith("linux"):
        operation = getattr(libc, "renameat2", None)
        flags = 0x00000001  # RENAME_NOREPLACE
    else:
        operation = None
        flags = 0
    if operation is None:
        raise FrontendCreateLockError(
            "frontend-create cleanup requires atomic no-clobber rename"
        )
    operation.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    operation.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = operation(
        source_parent_descriptor,
        encoded_source,
        destination_parent_descriptor,
        encoded_destination,
        flags,
    )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(
            error_number,
            f"{os.strerror(error_number)}: "
            f"{source_name} -> {destination_name}",
        )


def _reserve_frontend_create_run_dir(
    title: str,
) -> _FrontendCreateRunReservation:
    """Publish a new run directory while retaining its original identity."""

    directory_flag = getattr(os, "O_DIRECTORY", 0)
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    if not directory_flag or not nofollow_flag:
        raise FrontendCreateLockError(
            "frontend-create reservation requires no-follow directory opens"
        )

    base = output_root(ROOT)
    try:
        base.mkdir(parents=True, exist_ok=True)
        expected_parent = os.stat(base, follow_symlinks=False)
    except OSError as exc:
        raise FrontendCreateLockError(
            f"frontend-create output directory is unavailable: {base}"
        ) from exc
    if not stat.S_ISDIR(expected_parent.st_mode):
        raise FrontendCreateLockError(
            f"frontend-create output path is not a directory: {base}"
        )
    expected_parent_identity = _frontend_create_entry_identity(
        expected_parent
    )

    open_flags = (
        os.O_RDONLY
        | directory_flag
        | nofollow_flag
        | getattr(os, "O_CLOEXEC", 0)
    )
    parent_descriptor = -1
    run_descriptor = -1
    staging_name = f".toc-reservation-{uuid.uuid4().hex}.private"
    owned_name = staging_name
    staging_entry: os.stat_result | None = None
    reservation_transferred = False
    try:
        parent_descriptor = os.open(base, open_flags)
        opened_parent = os.fstat(parent_descriptor)
        current_parent = os.stat(base, follow_symlinks=False)
        if (
            not stat.S_ISDIR(opened_parent.st_mode)
            or not stat.S_ISDIR(current_parent.st_mode)
            or _frontend_create_entry_identity(opened_parent)
            != expected_parent_identity
            or _frontend_create_entry_identity(current_parent)
            != expected_parent_identity
        ):
            raise FrontendCreateLockError(
                f"frontend-create output directory identity changed: {base}"
            )

        # The unguessable mode-0700 directory is the run itself. Retain its
        # descriptor before publishing it under the predictable public name.
        os.mkdir(
            staging_name,
            0o700,
            dir_fd=parent_descriptor,
        )
        staging_entry = _frontend_create_named_stat(
            parent_descriptor,
            staging_name,
        )
        if staging_entry is None or not stat.S_ISDIR(staging_entry.st_mode):
            raise FrontendCreateLockError(
                "frontend-create private reservation became unavailable"
            )
        expected_run_identity = _frontend_create_entry_identity(staging_entry)
        run_descriptor = os.open(
            staging_name,
            open_flags,
            dir_fd=parent_descriptor,
        )
        opened_run = os.fstat(run_descriptor)
        current_run = _frontend_create_named_stat(
            parent_descriptor,
            staging_name,
        )
        if (
            current_run is None
            or not stat.S_ISDIR(opened_run.st_mode)
            or not stat.S_ISDIR(current_run.st_mode)
            or _frontend_create_entry_identity(opened_run)
            != expected_run_identity
            or _frontend_create_entry_identity(current_run)
            != expected_run_identity
        ):
            raise FrontendCreateLockError(
                "frontend-create private reservation identity changed"
            )

        stamp = time.strftime("%Y%m%d_%H%M")
        slug = sanitize_run_title(title)
        try:
            name_max = int(os.fpathconf(parent_descriptor, "PC_NAME_MAX"))
        except (OSError, ValueError) as exc:
            raise FrontendCreateLockError(
                "frontend-create filesystem name limit is unavailable"
            ) from exc
        suffix: int | None = None
        while True:
            candidate_id = _frontend_create_public_candidate(
                slug,
                stamp,
                suffix=suffix,
                name_max=name_max,
            )
            try:
                _frontend_create_rename_noreplace(
                    source_parent_descriptor=parent_descriptor,
                    source_name=staging_name,
                    destination_parent_descriptor=parent_descriptor,
                    destination_name=candidate_id,
                )
                owned_name = candidate_id
                break
            except OSError as exc:
                if exc.errno not in {errno.EEXIST, errno.ENOTEMPTY}:
                    raise FrontendCreateLockError(
                        "frontend-create run publication failed"
                    ) from exc
                suffix = 2 if suffix is None else suffix + 1

        published = _frontend_create_named_stat(
            parent_descriptor,
            candidate_id,
        )
        retained = os.fstat(run_descriptor)
        if (
            published is None
            or not stat.S_ISDIR(published.st_mode)
            or not stat.S_ISDIR(retained.st_mode)
            or _frontend_create_entry_identity(published)
            != expected_run_identity
            or _frontend_create_entry_identity(retained)
            != expected_run_identity
        ):
            # Never adopt whatever appeared at the public name; leave every
            # raced entry untouched on failure.
            raise FrontendCreateLockError(
                "frontend-create published run identity changed"
            )
        os.fchmod(run_descriptor, 0o755)
        published = _frontend_create_named_stat(
            parent_descriptor,
            candidate_id,
        )
        retained = os.fstat(run_descriptor)
        if (
            published is None
            or not stat.S_ISDIR(published.st_mode)
            or not stat.S_ISDIR(retained.st_mode)
            or _frontend_create_entry_identity(published)
            != expected_run_identity
            or _frontend_create_entry_identity(retained)
            != expected_run_identity
        ):
            raise FrontendCreateLockError(
                "frontend-create published run identity changed"
            )
        reservation = _FrontendCreateRunReservation(
            run_id=candidate_id,
            run_dir=base / candidate_id,
            identity=expected_run_identity,
            descriptor=run_descriptor,
            parent_descriptor=parent_descriptor,
        )
        reservation_transferred = True
        run_descriptor = -1
        parent_descriptor = -1
        return reservation
    except FrontendCreateLockError:
        raise
    except OSError as exc:
        raise FrontendCreateLockError(
            "frontend-create run reservation failed"
        ) from exc
    finally:
        if (
            not reservation_transferred
            and parent_descriptor >= 0
            and staging_entry is not None
        ):
            try:
                current_staging = _frontend_create_named_stat(
                    parent_descriptor,
                    owned_name,
                )
                if (
                    current_staging is not None
                    and _frontend_create_entry_identity(current_staging)
                    == _frontend_create_entry_identity(staging_entry)
                ):
                    _frontend_create_rename_verified_entry(
                        parent_descriptor=parent_descriptor,
                        source_name=owned_name,
                        expected=staging_entry,
                        quarantine_name=_frontend_create_private_name(
                            "toc-reservation-failed"
                        ),
                    )
            except (FrontendCreateLockError, OSError):
                pass
        if run_descriptor >= 0:
            os.close(run_descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)


def _frontend_create_rename_verified_entry(
    *,
    parent_descriptor: int,
    source_name: str,
    expected: os.stat_result,
    quarantine_name: str,
) -> None:
    """Move an entry to a private name and retain it only on identity match."""

    current = _frontend_create_named_stat(
        parent_descriptor,
        source_name,
    )
    expected_identity = _frontend_create_entry_identity(expected)
    if (
        current is None
        or _frontend_create_entry_identity(current) != expected_identity
    ):
        raise FrontendCreateLockError(
            f"frontend-create cleanup entry identity changed: {source_name}"
        )
    try:
        _frontend_create_rename_noreplace(
            source_parent_descriptor=parent_descriptor,
            source_name=source_name,
            destination_parent_descriptor=parent_descriptor,
            destination_name=quarantine_name,
        )
    except OSError as exc:
        raise FrontendCreateLockError(
            f"frontend-create cleanup could not quarantine: {source_name}"
        ) from exc
    quarantined = _frontend_create_named_stat(
        parent_descriptor,
        quarantine_name,
    )
    if (
        quarantined is None
        or _frontend_create_entry_identity(quarantined)
        != expected_identity
    ):
        # The moved name is deliberately left behind. Its identity is not
        # trusted, so attempting rollback or deletion could target a raced
        # replacement.
        raise FrontendCreateLockError(
            f"frontend-create cleanup quarantine identity changed: {source_name}"
        )


def _quarantine_frontend_create_run(
    lease: _FrontendCreateDirectoryLease,
) -> None:
    try:
        opened = os.fstat(lease.descriptor)
    except OSError as exc:
        raise FrontendCreateLockError(
            "frontend-create cleanup lease became unavailable"
        ) from exc
    if (
        not stat.S_ISDIR(opened.st_mode)
        or _frontend_create_entry_identity(opened) != lease.identity
    ):
        raise FrontendCreateLockError(
            "frontend-create cleanup lease identity changed"
        )
    if _frontend_create_run_has_scaffold(lease):
        return
    quarantine_name = _frontend_create_private_name("toc-cleanup")
    _frontend_create_rename_verified_entry(
        parent_descriptor=lease.parent_descriptor,
        source_name=lease.name,
        expected=opened,
        quarantine_name=quarantine_name,
    )
    quarantined = _frontend_create_named_stat(
        lease.parent_descriptor,
        quarantine_name,
    )
    if (
        quarantined is None
        or not stat.S_ISDIR(quarantined.st_mode)
        or _frontend_create_entry_identity(quarantined) != lease.identity
    ):
        raise FrontendCreateLockError(
            "frontend-create cleanup run quarantine identity changed"
        )
    # POSIX offers no portable unlink-by-descriptor or conditional unlink.
    # Leave the verified tree under its private quarantine name: deleting it
    # by pathname would reintroduce a final identity-check/use race. A future
    # explicit GC may reclaim these residues only under exclusive ownership.


@contextmanager
def _frontend_create_directory_lock(
    run_dir: Path,
    *,
    expected_identity: tuple[int, int] | None = None,
):
    """Hold the frontend runner's lock on a verified run-directory inode."""

    directory_flag = getattr(os, "O_DIRECTORY", 0)
    nofollow_flag = getattr(os, "O_NOFOLLOW", 0)
    if not directory_flag or not nofollow_flag:
        raise FrontendCreateLockError(
            "frontend-create locking requires no-follow directory opens"
        )

    if not run_dir.name or run_dir.name in {".", ".."}:
        raise FrontendCreateLockError(
            f"frontend-create run path is not a direct child: {run_dir}"
        )

    try:
        expected = os.stat(run_dir, follow_symlinks=False)
    except OSError as exc:
        raise FrontendCreateLockError(
            f"frontend-create run directory is unavailable: {run_dir}"
        ) from exc
    named_identity = expected.st_dev, expected.st_ino
    if stat.S_ISLNK(expected.st_mode):
        raise FrontendCreateLockError(
            f"frontend-create run path must not be a symlink: {run_dir}"
        )
    if not stat.S_ISDIR(expected.st_mode):
        raise FrontendCreateLockError(
            f"frontend-create run path is not a directory: {run_dir}"
        )
    if (
        expected_identity is not None
        and named_identity != expected_identity
    ):
        raise FrontendCreateLockError(
            f"frontend-create run directory identity changed: {run_dir}"
        )
    lease_identity = expected_identity or named_identity

    parent_path = run_dir.parent
    try:
        expected_parent = os.stat(parent_path, follow_symlinks=False)
    except OSError as exc:
        raise FrontendCreateLockError(
            f"frontend-create output directory is unavailable: {parent_path}"
        ) from exc
    if not stat.S_ISDIR(expected_parent.st_mode):
        raise FrontendCreateLockError(
            f"frontend-create output path is not a directory: {parent_path}"
        )
    expected_parent_identity = _frontend_create_entry_identity(
        expected_parent
    )

    try:
        parent_descriptor = os.open(
            parent_path,
            os.O_RDONLY
            | directory_flag
            | nofollow_flag
            | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as exc:
        raise FrontendCreateLockError(
            f"frontend-create output directory is unavailable: {parent_path}"
        ) from exc
    descriptor = -1
    try:
        opened_parent = os.fstat(parent_descriptor)
        current_parent = os.stat(parent_path, follow_symlinks=False)
        if (
            not stat.S_ISDIR(opened_parent.st_mode)
            or not stat.S_ISDIR(current_parent.st_mode)
            or _frontend_create_entry_identity(opened_parent)
            != expected_parent_identity
            or _frontend_create_entry_identity(current_parent)
            != expected_parent_identity
        ):
            raise FrontendCreateLockError(
                "frontend-create output directory identity changed: "
                f"{parent_path}"
            )
        descriptor = os.open(
            run_dir.name,
            os.O_RDONLY
            | directory_flag
            | nofollow_flag
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent_descriptor,
        )
    except FrontendCreateLockError:
        os.close(parent_descriptor)
        raise
    except OSError as exc:
        os.close(parent_descriptor)
        raise FrontendCreateLockError(
            f"frontend-create run directory is unavailable: {run_dir}"
        ) from exc
    acquired = False
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != lease_identity
        ):
            raise FrontendCreateLockError(
                f"frontend-create run directory identity changed: {run_dir}"
            )
        try:
            fcntl.flock(
                descriptor,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as exc:
            raise FrontendCreateLockOwnedError(
                f"another frontend-create process owns this run: {run_dir}"
            ) from exc
        except OSError as exc:
            raise FrontendCreateLockError(
                f"frontend-create run directory could not be locked: {run_dir}"
            ) from exc
        acquired = True

        try:
            current = os.stat(
                run_dir.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise FrontendCreateLockError(
                f"frontend-create run directory identity changed: {run_dir}"
            ) from exc
        if (
            not stat.S_ISDIR(current.st_mode)
            or (current.st_dev, current.st_ino) != lease_identity
        ):
            raise FrontendCreateLockError(
                f"frontend-create run directory identity changed: {run_dir}"
            )
        yield _FrontendCreateDirectoryLease(
            descriptor=descriptor,
            parent_descriptor=parent_descriptor,
            name=run_dir.name,
            identity=lease_identity,
        )
    finally:
        try:
            if acquired:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            try:
                os.close(descriptor)
            finally:
                os.close(parent_descriptor)


def _probe_frontend_create_directory_lock(
    run_dir: Path,
    *,
    expected_identity: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Return the unlocked-but-identity-bound run inode after a lock probe."""

    with _frontend_create_directory_lock(
        run_dir,
        expected_identity=expected_identity,
    ) as lease:
        return lease.identity


def _retain_frontend_create_run(
    run_dir: Path,
    *,
    expected_identity: tuple[int, int] | None = None,
) -> _FrontendCreateRunReservation:
    """Probe an existing run once and retain its exact descriptors."""

    with _frontend_create_directory_lock(
        run_dir,
        expected_identity=expected_identity,
    ) as lease:
        return _FrontendCreateRunReservation(
            run_id=lease.name,
            run_dir=run_dir,
            identity=lease.identity,
            descriptor=os.dup(lease.descriptor),
            parent_descriptor=os.dup(lease.parent_descriptor),
        )


async def _run_toc_immersive_frontend_cli_helper(
    *,
    topic: str,
    source: str | None = None,
    run_id: str,
    stop_target: str = "p680",
    experience: str = "cinematic_story",
    source_run_id: str | None = None,
    target_duration_seconds: int = 300,
    review_mode: Literal["standard", "preapproved"] = "standard",
    materialize_only: bool = False,
    expected_run_identity: tuple[int, int] | None = None,
    run_descriptor: int | None = None,
) -> str:
    if review_mode not in {"standard", "preapproved"}:
        raise ValueError("review_mode must be standard or preapproved")
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
        "--experience",
        experience,
    ]
    if source_run_id:
        cmd.extend(["--source-run", f"output/{source_run_id}"])
    if materialize_only:
        cmd.append("--materialize-only")
    env = dict(os.environ)
    env.setdefault("CODEX_HOME", str(Path.home() / ".codex"))
    if expected_run_identity is None:
        run_dir = safe_run_dir(run_id, ROOT)
    else:
        if (
            not run_id
            or "/" in run_id
            or "\\" in run_id
            or run_id in {".", ".."}
        ):
            raise ValueError("invalid run_id")
        run_dir = output_root(ROOT) / run_id
    if run_descriptor is None:
        expected_run_identity = _probe_frontend_create_directory_lock(
            run_dir,
            expected_identity=expected_run_identity,
        )
    else:
        opened = os.fstat(run_descriptor)
        descriptor_identity = opened.st_dev, opened.st_ino
        if (
            not stat.S_ISDIR(opened.st_mode)
            or expected_run_identity is None
            or descriptor_identity != expected_run_identity
        ):
            raise FrontendCreateLockError(
                "frontend-create inherited run descriptor identity changed"
            )
        cmd.extend(
            [
                "--inherited-run-fd",
                str(run_descriptor),
            ]
        )
    cmd.extend(
        [
            "--expected-run-device",
            str(expected_run_identity[0]),
            "--expected-run-inode",
            str(expected_run_identity[1]),
        ]
    )
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(ROOT),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
        **(
            {"pass_fds": (run_descriptor,)}
            if run_descriptor is not None
            else {}
        ),
    )
    communicate_task = asyncio.create_task(proc.communicate())
    try:
        stdout, stderr = await asyncio.wait_for(
            asyncio.shield(communicate_task),
            timeout=FRONTEND_CREATE_HELPER_TIMEOUT_SECONDS,
        )
    except asyncio.CancelledError as cancellation:
        with suppress(asyncio.CancelledError):
            await _await_resume_process_cleanup(proc, communicate_task)
        raise cancellation
    except asyncio.TimeoutError:
        stdout, stderr = await _await_resume_process_cleanup(
            proc,
            communicate_task,
        )
        _write_cli_process_logs(
            run_dir,
            "frontend_create_cli",
            stdout,
            stderr,
            expected_run_identity=expected_run_identity,
        )
        raise
    if proc.returncode != 0:
        detail = stderr.decode("utf-8", errors="replace").strip() or stdout.decode("utf-8", errors="replace").strip()
        if "another frontend-create process owns this run:" in detail:
            raise FrontendCreateLockOwnedError(detail)
        if any(
            marker in detail
            for marker in (
                "destination run identity changed after server reservation",
                "destination run could not be opened safely",
                "frontend-create run directory identity changed",
            )
        ):
            raise FrontendCreateLockError(detail)
        _write_cli_process_logs(
            run_dir,
            "frontend_create_cli",
            stdout,
            stderr,
            expected_run_identity=expected_run_identity,
        )
        raise RuntimeError(detail or f"toc-immersive-frontend-run exited with status {proc.returncode}")
    _write_cli_process_logs(
        run_dir,
        "frontend_create_cli",
        stdout,
        stderr,
        expected_run_identity=expected_run_identity,
    )
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


async def _run_toc_skill_helper(
    *,
    topic: str,
    source: str | None = None,
    run_id: str,
    stop_target: str = "p680",
    experience: str = "cinematic_story",
    source_run_id: str | None = None,
    target_duration_seconds: int = 300,
    review_mode: Literal["standard", "preapproved"] = "standard",
) -> None:
    if app_server_disabled():
        raise RuntimeError("Codex app-server is disabled")
    skill_path = _toc_immersive_skill_path()
    if not skill_path.is_file():
        raise RuntimeError(f"Codex skill not found: {skill_path}")
    run_dir = safe_run_dir(run_id, ROOT)
    client = create_codex_app_server_client(cwd=ROOT)
    skill_text = _toc_immersive_command(
        topic=topic,
        source=source,
        run_id=run_id,
        stop_target=stop_target,
        experience=experience,
        source_run_id=source_run_id,
        target_duration_seconds=target_duration_seconds,
    )
    try:
        await client.start()
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="skill_start",
            status="started",
            item_id="toc-immersive-runner",
            request={
                "topic": topic,
                "experience": experience,
                "stopTarget": stop_target,
                "skillPath": str(skill_path.relative_to(ROOT)),
            },
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
            if experience == CREATE_MODE_WORLD_WALK:
                raise RuntimeError(
                    "world_walk skill completed without reaching the requested "
                    f"{stop_target} contract"
                )
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
        if experience == CREATE_MODE_WORLD_WALK:
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
    review_mode: Literal["standard", "preapproved"] = "standard",
) -> None:
    task = asyncio.create_task(
        _run_toc_skill_helper(
            topic=topic,
            source=source,
            run_id=run_id,
            stop_target=stop_target,
        )
    )
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
        raise ValueError("materialized video request section hash is invalid")
    if re.fullmatch(r"[0-9a-f]{64}", design_digest) is None:
        raise ValueError("materialized video prompt source digest is invalid")
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


def _current_video_candidate_provenance(
    run_dir: Path,
    item_id: str,
    *,
    manifest_data: dict[str, Any] | None = None,
) -> dict[str, str] | None:
    """Resolve the candidate namespace bound to the current materialized request."""

    try:
        binding = _video_request_binding(run_dir, item_id)
        data = manifest_data
        if data is None:
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
        DEFAULT_ELEVENLABS_MODEL_ID,
        DEFAULT_ELEVENLABS_VOICE_ID,
        normalize_elevenlabs_model_id,
        normalize_elevenlabs_voice_settings,
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
    model_id = normalize_elevenlabs_model_id(
        narration.get("model_id")
        or os.environ.get("ELEVENLABS_MODEL_ID")
        or DEFAULT_ELEVENLABS_MODEL_ID
    )
    voice_settings = normalize_elevenlabs_voice_settings(
        narration.get("voice_settings"),
        model_id=model_id,
    )
    public = {
        "voice_id": str(narration.get("voice_id") or os.environ.get("ELEVENLABS_VOICE_ID") or DEFAULT_ELEVENLABS_VOICE_ID),
        "model_id": model_id,
        "voice_settings": voice_settings,
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
    native_audio_mode: str = 'off',
) -> dict[str, Any]:
    load_env_files(repo_root=ROOT)
    if native_audio_mode != 'off' and tool != 'higgsfield':
        raise ValueError('同期音声を使うには対応するHiggsfieldモデルを選んでください')
    if tool == 'higgsfield':
        from toc.providers.higgsfield import IMAGE_MODEL, REFERENCE_MODEL
        if has_first_frame and has_reference_images:
            raise ValueError('Higgsfield frame/reference inputs cannot be combined')
        return {'backend': 'higgsfield', 'model': IMAGE_MODEL if has_first_frame else REFERENCE_MODEL,
                'generate_audio': native_audio_mode != 'off'}
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
            f"{label}: reference image count {int(reference_count)} is outside the "
            f"{tool if capabilities.reference_limit_verified else 'ToC application input'} "
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
    if request.tool == 'higgsfield':
        if request.quality not in {'480p', '720p', '1080p'}:
            raise ValueError('Higgsfield Seedance 2.5 supports 480p, 720p, 1080p')
        if request.references and (request.first_reference or request.last_reference):
            raise ValueError('Higgsfield frame/reference inputs cannot be combined')
        if request.last_reference and not request.first_reference:
            raise ValueError('Higgsfield end frame requires a first frame')


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
        elif request.tool == 'higgsfield':
            from toc.providers.higgsfield import HiggsfieldClient
            from toc.providers.video_validation import verify_generated_video
            load_env_files(repo_root=ROOT)
            options = request.provider_execution_options
            identity = hashlib.sha256((destination.relative_to(run_dir).as_posix() + ':' +
                str(request.prompt_source_digest)).encode()).hexdigest()
            pending = destination.with_name('.' + destination.stem + '.unverified.mp4')
            try:
                provider_result = HiggsfieldClient.from_env().generate_video(
                    model=str(options.get('model') or ''), prompt=request.prompt,
                    duration_seconds=request.duration_seconds, aspect_ratio=request.aspect_ratio, resolution=request.quality,
                    input_image=provider_input_image, last_frame_image=provider_last_frame_image,
                    reference_images=provider_reference_images, generate_audio=bool(options.get('generate_audio', False)),
                    out_path=pending, journal_path=run_dir / 'logs/providers/higgsfield' / f'{identity}.json',
                    request_digest=identity, poll_every_seconds=_video_poll_every_seconds(), timeout_seconds=_video_timeout_seconds())
                if provider_result.get('status') != 'completed':
                    raise RuntimeError(f"Higgsfield generation status: {provider_result.get('status')}; request {provider_result.get('request_id')}")
                provider_result['validation'] = verify_generated_video(pending,
                    duration_seconds=request.duration_seconds, aspect_ratio=request.aspect_ratio,
                    require_audio=bool(options.get('generate_audio')))
                os.replace(pending, destination)
                provider_result['out_path'] = destination.relative_to(run_dir).as_posix()
            finally:
                pending.unlink(missing_ok=True)
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
    """Copy materialized reference bytes before the provider reads them.

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
            current_revision = _current_video_candidate_provenance(
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
                        "video candidate completed after its materialized prompt "
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
            "materialized video duration is shorter than the current narration; "
            "create video prompts again before generation"
        )
    async def candidate(index):
        return await _run_media_item(f"video:{req.item_id}:{index}", req.model_dump(mode="json"),
            lambda: _generate_video_one(run_dir, req, index))
    candidates = await asyncio.gather(*(candidate(index) for index in range(1, req.candidate_count + 1)))
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
    """Bind a generation request to the exact materialized provider prompt.

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

    request_binding = _video_request_binding(run_dir, request.item_id)
    negative_prompt = str(payload.get("negative_prompt") or "")
    request_expected = {
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
    request_mismatches = [
        field
        for field, expected in request_expected.items()
        if str(request_binding.get(field) or "") != str(expected)
    ]
    if request_mismatches:
        raise ValueError(
            "materialized video generation request is stale or changed: "
            + ", ".join(request_mismatches)
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
            request_section_sha256=request_binding["request_section_sha256"],
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


def _canonical_image_request_owner(
    run_dir: Path,
    output: str,
) -> tuple[str, str] | None:
    for kind in ("asset", "scene"):
        try:
            items = load_request_items(run_dir, kind)
        except (FileNotFoundError, ValueError):
            continue
        for item in items:
            if item.output == output:
                return kind, str(item.id)
    return None


def _validate_candidate_matches_output(
    run_dir: Path,
    candidate: Path,
    output: str,
) -> tuple[str, str] | None:
    owner = _canonical_image_request_owner(run_dir, output)
    if owner is None:
        return None
    _kind, expected_item_id = owner
    expected_dir = candidate_path(run_dir, expected_item_id, 1).parent.name
    actual_dir = candidate.parent.name
    if actual_dir != expected_dir:
        raise ValueError(
            f"candidate item mismatch: {candidate.relative_to(run_dir).as_posix()} cannot be inserted into {output}; "
            f"expected candidate directory {expected_dir}"
        )
    return owner


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


class _FileTransactionSnapshot(dict[Path, bytes | None]):
    """Recoverable artifact bytes plus append-only state cursors at capture."""

    def __init__(
        self,
        files: dict[Path, bytes | None],
        state_cursors: dict[Path, tuple[int, int, int] | None],
    ) -> None:
        super().__init__(files)
        self.state_cursors = state_cursors


def _capture_file_transaction(
    paths: Iterable[Path],
    *,
    state_paths: Iterable[Path] = (),
) -> _FileTransactionSnapshot:
    unique_paths = tuple(dict.fromkeys(paths))
    tracked_state_paths = tuple(
        dict.fromkeys(
            [path for path in unique_paths if path.name == "state.txt"]
            + list(state_paths)
        )
    )

    def state_cursor(path: Path) -> tuple[int, int, int] | None:
        try:
            info = path.stat(follow_symlinks=False)
        except FileNotFoundError:
            return None
        return info.st_dev, info.st_ino, info.st_size

    return _FileTransactionSnapshot(
        {
            path: path.read_bytes() if path.is_file() else None
            for path in unique_paths
        },
        {path: state_cursor(path) for path in tracked_state_paths},
    )


def _restore_file_transaction(snapshot: _FileTransactionSnapshot) -> None:
    for state_path, captured_cursor in snapshot.state_cursors.items():
        try:
            info = state_path.stat(follow_symlinks=False)
            current_cursor: tuple[int, int, int] | None = (
                info.st_dev,
                info.st_ino,
                info.st_size,
            )
        except FileNotFoundError:
            current_cursor = None
        if current_cursor != captured_cursor:
            warnings.warn(
                "artifact rollback skipped because append-only state already "
                f"advanced: {state_path}",
                RuntimeWarning,
                stacklevel=2,
            )
            return
    for path, previous_content in snapshot.items():
        if path.name in {
            "state.txt",
            "state.current.json",
            "run_status.json",
            "p000_index.md",
        }:
            # Canonical state is append-only.  The other three files are
            # derived projections and are rebuilt from the committed head.
            continue
        from toc.media_resume import ACTIVE_MEDIA_JOURNAL
        journal = ACTIVE_MEDIA_JOURNAL.get()
        tracked = journal is not None and path.parent == journal.root and path.name in {"script.md", "video_manifest.md"}
        if tracked:
            journal.authorize_manifest_update(previous_content.decode() if previous_content is not None else None, path.name)
        if previous_content is None:
            path.unlink(missing_ok=True)
        else:
            _atomic_write_bytes(path, previous_content)
        if tracked:
            journal.confirm_manifest_update(path.name)


def _render_manifest_data(original_text: str, data: dict[str, Any]) -> str:
    yaml_text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    if "```yaml" not in original_text:
        return f"```yaml\n{yaml_text}```\n"
    start = original_text.find("```yaml")
    yaml_start = original_text.find("\n", start)
    if yaml_start == -1:
        return f"```yaml\n{yaml_text}```\n"
    yaml_start += 1
    yaml_end = original_text.find("```", yaml_start)
    if yaml_end == -1:
        return original_text[:yaml_start] + yaml_text
    return original_text[:yaml_start] + yaml_text + original_text[yaml_end:]


def _write_manifest_data(manifest_path: Path, original_text: str, data: dict[str, Any]) -> None:
    from toc.media_resume import ACTIVE_MEDIA_JOURNAL
    text = _render_manifest_data(original_text, data)
    journal = ACTIVE_MEDIA_JOURNAL.get()
    if journal is not None and manifest_path.parent == journal.root and manifest_path.name in {"script.md", "video_manifest.md"}:
        journal.authorize_manifest_update(text, manifest_path.name)
    _atomic_write_text(manifest_path, text)
    if journal is not None and manifest_path.parent == journal.root and manifest_path.name in {"script.md", "video_manifest.md"}:
        journal.confirm_manifest_update(manifest_path.name)


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


def _narration_summary(target: dict[str, Any]) -> dict[str, Any]:
    node = _dict_value(target.get("cut"))
    narration = _dict_value(_dict_value(node.get("audio")).get("narration"))
    revision = _dict_value(narration.get("revision"))
    generation = _dict_value(narration.get("generation"))
    audio_selection = _dict_value(narration.get("audio_selection"))
    candidates = [candidate for candidate in _list_value(narration.get("candidates")) if isinstance(candidate, dict)]
    current_candidate = next(
        (
            candidate
            for candidate in reversed(candidates)
            if str(candidate.get("candidate_id") or "") == str(generation.get("candidate_id") or "")
        ),
        None,
    )
    selected_candidate = current_audio_candidate(narration)
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
        "audioSelection": audio_selection,
        "candidate": current_candidate,
        "selectedCandidate": selected_candidate,
        # Keep this response key for older clients; selection is no longer an
        # approval certificate or a readiness gate.
        "approvedCandidate": selected_candidate,
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
    selection = _dict_value(narration.get("audio_selection"))
    selection.update(
        {
            "status": "unselected",
            "candidate_id": "",
            "revision": 0,
            "text_hash": "",
            "tts_hash": "",
            "selected_at": "",
        }
    )
    narration["audio_selection"] = selection
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
            "stage.narration.status": "in_progress",
        },
    )


def _append_narration_preview_state(
    run_dir: Path,
    *,
    note: str,
    runtime_stage: str = "narration_audio_candidate_preview",
) -> None:
    """Record an alternate TTS preview without changing the current selection."""

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
                phase="authoring",
                note=(
                    "frontend narration text revision saved; current audio selection "
                    "was invalidated when hashes changed"
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


def _video_source_context_for_server_target(
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


def _silence_contract_payload(contract: dict[str, Any], *, reason: str | None = None) -> dict[str, Any]:
    silence_reason = _first_non_empty(reason, contract.get("silence_reason"), "このcutは映像だけで意味が成立するため")
    return {
        "intentional": True,
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


def _has_existing_narration_content(narration: dict[str, Any]) -> bool:
    if not narration:
        return False
    status = str(narration.get("status") or "").strip().lower()
    if status in {"pending", "approved", "audio_ready", "candidate", "generating"}:
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
        "audio_selection",
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
        if not replace and _has_existing_narration_content(previous):
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
            "silence_contract": _silence_contract_payload(contract) if is_silent else {
                "intentional": False,
                "kind": "spoken",
                "reason": "",
            },
            "tool": "silent" if is_silent else str(previous.get("tool") or "elevenlabs"),
            # ``output`` is the currently selected audio file. A planned
            # destination must never look like an existing output.
            "output": "",
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
            "slot.p720.note": "awaiting p700 narration writer before TTS generation",
            "slot.p730.status": "pending",
            "slot.p740.status": "pending",
            "slot.p750.status": "pending",
            "stage.narration.status": "in_progress",
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
    silence_contract = _silence_contract_payload(contract, reason=reason)
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
                "status": "selected",
                "candidate_id": f"silent-revision-{int(revision.get('number') or 0)}",
                "generated_from_tts_hash": str(revision.get("tts_hash") or ""),
            },
            "audio_selection": {
                "status": "selected",
                "candidate_id": f"silent-revision-{int(revision.get('number') or 0)}",
                "revision": int(revision.get("number") or 0),
                "text_hash": str(revision.get("text_hash") or ""),
                "tts_hash": str(revision.get("tts_hash") or ""),
                "selected_at": now_iso(),
                "source": "frontend",
            },
        }
    )
    audio["narration"] = narration
    node["audio"] = audio
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
            if str(narration.get("tool") or "").strip().lower() == "silent":
                if current_audio_is_ready(narration):
                    ready.append({"itemId": selector, "kind": "silent"})
                else:
                    missing.append({"itemId": selector, "reason": "intentional_silence_not_configured"})
                continue
            candidate = current_audio_candidate(narration)
            output = str(narration.get("output") or (candidate or {}).get("output") or "").strip()
            if not current_audio_is_ready(narration):
                missing.append({"itemId": selector, "reason": "current_audio_candidate_not_ready"})
                continue
            try:
                _validate_run_relative_audio_path(run_dir, output, must_exist=True)
                output_path = resolve_run_relative(run_dir, output)
                if not _narration_candidate_context_is_current(
                    data,
                    selector=selector,
                    candidate=candidate,
                ):
                    missing.append({"itemId": selector, "reason": "audio_tts_context_stale"})
                    continue
                expected_sha256 = str((candidate or {}).get("output_sha256") or "")
                if (
                    output_path.is_file()
                    and expected_sha256
                    and _audio_file_sha256(output_path) == expected_sha256
                ):
                    ready.append({"itemId": selector, "kind": "audio_file"})
                    continue
            except ValueError:
                pass
            missing.append({"itemId": selector, "reason": "audio_file_missing_or_hash_mismatch"})
            continue
        if _narration_has_intentional_silence(narration):
            ready.append({"itemId": selector, "kind": "silent_ok"})
            continue
        output = str(narration.get("output") or "").strip()
        if output:
            try:
                _validate_run_relative_audio_path(run_dir, output, must_exist=True)
                if resolve_run_relative(run_dir, output).is_file():
                    ready.append({"itemId": selector, "kind": "audio_file"})
                    continue
            except ValueError:
                pass
        missing.append({"itemId": selector, "reason": "missing_audio_file_or_silent"})
    return {"ready": not missing and bool(ready), "readyItems": ready, "missingItems": missing}


def _narration_has_intentional_silence(narration: dict[str, Any]) -> bool:
    if _dict_value(narration.get("revision")).get("schema_version") == REVISION_SCHEMA_VERSION:
        return current_audio_is_ready(narration)
    tool = str(narration.get("tool") or "").strip().lower()
    silence_contract = _dict_value(narration.get("silence_contract"))
    return (
        tool == "silent"
        and silence_contract.get("intentional") is True
        and bool(str(silence_contract.get("kind") or "").strip())
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
            "duration_fit.status": "failed",
            "duration_fit.note": str(readiness.get("durationError") or "duration contract is invalid"),
            "duration_fit.at": now_iso(),
        }

    def measurement_value(key: str, default: Any = 0) -> Any:
        return getattr(measurement, key, default)

    return {
        "duration_fit.status": "passed" if readiness.get("durationPassed") else "failed",
        "duration_fit.target_seconds": str(duration_audit.target_seconds),
        "duration_fit.minimum_seconds": _duration_state_value(duration_audit.minimum_seconds),
        "duration_fit.actual_seconds": _duration_state_value(duration_audit.actual_seconds),
        "duration_fit.ratio": f"{duration_audit.ratio:.6f}",
        "duration_fit.measurement_layer": duration_audit.measurement_layer,
        "duration_fit.measurement_complete": str(bool(measurement_value("complete", True))).lower(),
        "duration_fit.spoken_audio_seconds": _duration_state_value(
            float(measurement_value("spoken_audio_seconds", 0))
        ),
        "duration_fit.intentional_silence_seconds": _duration_state_value(
            float(measurement_value("intentional_silence_seconds", 0))
        ),
        "duration_fit.audio_timeline_seconds": _duration_state_value(
            float(measurement_value("audio_timeline_seconds", 0))
        ),
        "duration_fit.video_timeline_seconds": _duration_state_value(
            float(measurement_value("video_timeline_seconds", 0))
        ),
        "duration_fit.video_timeline_source": str(measurement_value("video_timeline_source", "unknown")),
        "duration_fit.missing_items": json.dumps(
            list(measurement_value("missing_items", [])), ensure_ascii=False
        ),
        "duration_fit.invalid_items": json.dumps(
            list(measurement_value("invalid_items", [])), ensure_ascii=False
        ),
        "duration_fit.at": now_iso(),
    }


def _append_narration_ready_state(run_dir: Path) -> dict[str, Any]:
    readiness = _narration_duration_readiness(run_dir)
    if not readiness["audioReady"]:
        return readiness
    measurement = readiness.get("measurement")
    duration_audit = readiness.get("audit")
    if measurement is None or duration_audit is None:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "duration_fit.status": "failed",
                "duration_fit.note": str(readiness.get("durationError") or "duration contract is invalid"),
                "duration_fit.at": now_iso(),
                "slot.p740.status": "failed",
                "slot.p740.note": "duration contract could not be evaluated",
            },
        )
        return readiness

    duration_updates = _narration_duration_state_updates(readiness)
    if not readiness["durationPassed"]:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                **duration_updates,
                "duration_fit.note": "measured audio/video timeline is below 80% of target or incomplete",
                "slot.p740.status": "failed",
                "slot.p740.note": "measured narration timeline did not pass the 80% duration gate",
            },
        )
        return readiness
    append_state_snapshot(
        run_dir / "state.txt",
        {
            **duration_updates,
            "duration_fit.note": "measured audio/video timeline satisfies at least 80% of target",
            "slot.p720.status": "done",
            "slot.p720.note": "narration text and TTS payload are ready",
            "slot.p730.status": "done",
            "slot.p730.note": "all cuts have usable audio or intentional silence",
            "slot.p740.status": "done",
            "slot.p740.note": "duration and current per-cut audio files passed",
            "stage.narration.status": "done",
        },
    )
    return readiness


def _require_narration_ready_for_video(run_dir: Path) -> dict[str, Any]:
    readiness = _append_narration_ready_state(run_dir)
    if readiness["ready"]:
        return readiness
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
        "video generation requires audio files or intentional silence for all cuts: " + (missing or "none")
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


def _candidate_video_output_for_item(
    run_dir: Path, item_id: str, *, manifest_data: dict[str, Any] | None = None,
) -> str | None:
    if (run_dir / 'production_selections.json').is_file():
        from server.production_tools_api import selected_video_path
        selected = selected_video_path(run_dir, item_id, manifest_data)
        if selected:
            return selected
    if not (run_dir / "assets/test/video_gen_candidates" / _safe_artifact_id(item_id)).is_dir():
        return None
    revision = _current_video_candidate_provenance(run_dir, item_id, manifest_data=manifest_data)
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


def _display_candidate_video_output_for_item(run_dir: Path, item_id: str, *, manifest_data=None):
    try:
        return _candidate_video_output_for_item(run_dir, item_id, manifest_data=manifest_data)
    except (ValueError, FileNotFoundError):
        # A stale selection must still allow opening the workspace and selecting
        # its replacement. Rendering/sound use the strict resolver directly.
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
    current = _current_video_candidate_provenance(run_dir, item_id)
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
        )
        revision = _dict_value(narration.get("revision"))
        revision_aware = revision.get("schema_version") == REVISION_SCHEMA_VERSION
        generation = _dict_value(narration.get("generation"))
        narration_candidates = [value for value in _list_value(narration.get("candidates")) if isinstance(value, dict)]
        narration_candidate = next(
            (
                value
                for value in reversed(narration_candidates)
                if str(value.get("candidate_id") or "") == str(generation.get("candidate_id") or "")
            ),
            None,
        )
        selected_candidate = current_audio_candidate(narration)
        narration_candidate_output = str((narration_candidate or {}).get("output") or "").strip()
        resolved_narration_candidate = (
            resolve_run_relative(run_dir, narration_candidate_output)
            if narration_candidate_output
            else run_dir / "__missing_narration_candidate__"
        )
        raw_narration_output = str(narration.get("output") or "").strip()
        selected_narration_output = str((selected_candidate or {}).get("output") or "").strip()
        narration_output = raw_narration_output or (
            selected_narration_output
            if revision_aware
            else ("" if narration_silent_ok else _default_narration_output_for_target(target))
        )
        video_output = str(video_generation.get("output") or _default_video_output_for_target(target)).strip()
        candidate_output = _display_candidate_video_output_for_item(run_dir, selector, manifest_data=data)
        resolved_audio = resolve_run_relative(run_dir, narration_output) if narration_output else run_dir / "__missing_narration__"
        resolved_video = resolve_run_relative(run_dir, candidate_output or video_output)
        audio_duration = _probe_media_duration_seconds(resolved_audio)
        video_duration = _probe_media_duration_seconds(resolved_video)
        narration_audio_ready = bool(
            revision_aware
            and _narration_grounding_is_current(target, narration)
            and current_audio_is_ready(narration)
            and (
                narration_tool == "silent"
                or _narration_candidate_context_is_current(
                    data,
                    selector=selector,
                    candidate=selected_candidate,
                )
            )
        )
        if narration_audio_ready and narration_tool != "silent":
            expected_output_sha256 = str((selected_candidate or {}).get("output_sha256") or "")
            narration_audio_ready = bool(
                resolved_audio.is_file()
                and expected_output_sha256
                and _audio_file_sha256(resolved_audio) == expected_output_sha256
            )
        elif not revision_aware:
            narration_audio_ready = bool(
                narration_silent_ok or resolved_audio.is_file()
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
                "videoNativeAudioMode": _dict_value(video_generation.get("native_audio")).get("mode", "off"),
                "videoHasDialogue": bool(_dict_value(video_generation.get("native_audio")).get("dialogue")),
                "cinematicDirection": _dict_value(_dict_value(node.get("cut_contract")).get("cinematic_contract")).get("execution"),
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
                        (selected_candidate if narration_audio_ready else narration_candidate)
                        or {}
                    ).get("generated_from_tts_hash")
                    or ""
                ),
                "narrationAudioReady": narration_audio_ready,
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
        video_input_mode = str(input_contract.get("input_mode") or video_generation.get("input_mode") or "").strip()
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
        candidate_output = _display_candidate_video_output_for_item(run_dir, selector, manifest_data=data)
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
                "videoNativeAudioMode": _dict_value(video_generation.get("native_audio")).get("mode", "off"),
                "videoHasDialogue": bool(_dict_value(video_generation.get("native_audio")).get("dialogue")),
                "cinematicDirection": _dict_value(_dict_value(node.get("cut_contract")).get("cinematic_contract")).get("execution"),
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
                f"narration grounding changed; save the current text before generation: {item.item_id}"
            )
        if item.tool != "silent":
            from toc.narration_audio import DEFAULT_LEAD_IN_SECONDS
            node.setdefault("render", {}).setdefault("narration_offset_seconds", DEFAULT_LEAD_IN_SECONDS)
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
        offset = max(0.0, _float_value(_dict_value(node.get("render")).get("narration_offset_seconds") or 0))
        min_duration = max(1, math.ceil(duration + offset))
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
        audio_selection = _dict_value(narration.get("audio_selection"))
        audio_selection["note"] = (
            note or "frontend selected this narration audio candidate"
        ).strip()
        narration["audio_selection"] = audio_selection
        _backup_run_file(run_dir, "video_manifest.md", label="before_narration_audio_approve")
        _write_manifest_data(manifest_path, original_text, data)
        duration = approved.get("duration_seconds")
        duration_updated = _apply_audio_duration_to_manifest(
            run_dir,
            {str(target["selector"]): float(duration)} if duration is not None else {},
        )
        _append_narration_ready_state(run_dir)
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
        candidate = current_audio_candidate(narration)
        if not _narration_candidate_context_is_current(
            data,
            selector=str(target["selector"]),
            candidate=candidate,
        ):
            return False
    return True


def _manifest_narration_audio_set_hash(data: dict[str, Any]) -> str:
    payload: list[dict[str, Any]] = []
    for target in _manifest_scene_targets(data):
        narration = _dict_value(_dict_value(_dict_value(target["cut"]).get("audio")).get("narration"))
        revision = _dict_value(narration.get("revision"))
        selection = _dict_value(narration.get("audio_selection"))
        selected_candidate_id = str(selection.get("candidate_id") or "")
        candidate = current_audio_candidate(narration)
        selected_candidate_id = str((candidate or {}).get("candidate_id") or "") or selected_candidate_id
        payload.append(
            {
                "candidate_id": selected_candidate_id,
                "duration_seconds": candidate.get("duration_seconds") if candidate else None,
                "output": str(narration.get("output") or (candidate or {}).get("output") or ""),
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
    """Validate/synchronize render-unit durations against the cut timeline."""

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
                issues.append(f"scene{scene_id}_cut{cut_id}: video duration is missing")
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
                    f"{selector}: duration {actual_duration}s does not match source-cut total "
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


def _apply_narration_timeline(
    data: dict[str, Any], timeline: list[NarrationTimelineItem], *, preserve_generation_items=()
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
        selected_candidate = current_audio_candidate(narration)
        raw_audio_duration = (selected_candidate or {}).get("duration_seconds")
        revision_aware_spoken = bool(
            _dict_value(narration.get("revision")).get("schema_version") == REVISION_SCHEMA_VERSION
            and str(narration.get("tool") or "").strip().lower() != "silent"
        )
        audio_duration = _float_value(raw_audio_duration)
        if revision_aware_spoken and (not math.isfinite(audio_duration) or audio_duration <= 0):
            raise NarrationRevisionConflict(
                f"narration candidate has no positive measured duration: {item.item_id}"
            )
        required_duration = max(
            1,
            math.ceil(audio_duration + float(item.narration_offset_seconds)),
        )
        if item.video_duration_seconds < required_duration:
            raise NarrationRevisionConflict(
                f"narration timeline would truncate audio for {item.item_id}: "
                f"required={required_duration}s requested={item.video_duration_seconds}s"
            )
        if item.item_id not in preserve_generation_items:
            video_generation["duration_seconds"] = item.video_duration_seconds
        node["video_generation"] = video_generation
        render["video_duration_seconds"] = item.video_duration_seconds
        render["narration_offset_seconds"] = float(item.narration_offset_seconds)
        node["render"] = render
    render_unit_issues = _render_unit_timeline_issues(data, synchronize=True)
    if render_unit_issues:
        raise NarrationRevisionConflict("invalid render-unit timeline: " + "; ".join(render_unit_issues[:20]))
    return _manifest_narration_timeline_hash(data)


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
    selected_candidate = current_audio_candidate(narration)
    output = str(narration.get("output") or (selected_candidate or {}).get("output") or "").strip()
    if not output:
        return None
    try:
        _validate_run_relative_audio_path(run_dir, output, must_exist=True)
    except ValueError:
        return None
    duration = _probe_media_duration_seconds(resolve_run_relative(run_dir, output))
    if duration is None:
        return None
    offset = max(0.0, _float_value(_dict_value(node.get("render")).get("narration_offset_seconds") or 0))
    return duration + offset


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
        raise ValueError(f"{label} duration could not be measured after render preparation: {path}")
    if abs(float(actual_seconds) - float(expected_seconds)) > 0.35:
        raise ValueError(
            f"{label} duration does not match the render timeline: "
            f"actual={actual_seconds:.3f}s expected={expected_seconds:.3f}s"
        )


def _prepare_render_video_clip(
    run_dir: Path,
    source: Path,
    item: RenderInputItem,
    *,
    strict: bool = False,
) -> Path:
    from toc.media_resume import ACTIVE_MEDIA_JOURNAL
    journal = ACTIVE_MEDIA_JOURNAL.get()
    if journal is not None:
        journal.bind_file(source.relative_to(run_dir).as_posix())
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
    from toc.media_resume import ACTIVE_MEDIA_JOURNAL
    journal = ACTIVE_MEDIA_JOURNAL.get()
    if journal is not None:
        journal.bind_file(source.relative_to(run_dir).as_posix())
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
            "-i",
            str(source),
            "-filter_complex",
            f"[0:a]adelay={offset * 1000:.3f}:all=1,apad,atrim=duration={duration:.3f}[a]",
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
    audio_set_hash = _manifest_narration_audio_set_hash(data)
    timeline_hash = _manifest_narration_timeline_hash(data)
    if revision_aware:
        _require_narration_ready_for_video(run_dir)
        expected_item_ids = [str(target["selector"]) for target in manifest_targets]
        requested_item_ids = [str(item.item_id) for item in req.items]
        if requested_item_ids != expected_item_ids:
            raise NarrationRevisionConflict(
                "revision-aware render inputs must include every manifest cut exactly once in canonical order"
            )
    selected_ids = set()
    if (run_dir / 'production_selections.json').is_file():
        from server.production_tools_api import selected_video_path
        for target in _manifest_video_targets(data):
            if selected_video_path(run_dir, str(target['selector']), data):
                selected_ids.add(str(target['selector']))
    timeline_hash = _apply_narration_timeline(data, req.items, preserve_generation_items=selected_ids)
    for item in req.items:
        if item.video_path:
            _assert_current_video_candidate_path(run_dir, item.item_id, item.video_path)
    from server.sound_design_api import freeze as freeze_sound
    from toc import sound_design
    sound_snapshot = freeze_sound(run_dir, data)
    approved_videos = {v["item_id"]: v for v in _sound_design_api.video_context(run_dir, data)["videos"]}
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
                    raise NarrationRevisionConflict(f"render unit has no configured duration: {unit_selector}")
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
                f"scene{scene_id}: using {len(render_units)} render unit video clip(s) for the configured cut timeline"
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
            approved_video = approved_videos[selector]
            if video_path != approved_video["path"] or item.video_duration_seconds != approved_video["duration_seconds"]:
                raise ValueError("結合する動画・尺がp860の動画承認と異なります")
            _validate_run_relative_video_path(run_dir, video_path, must_exist=True)
            video_source = resolve_run_relative(run_dir, video_path)
            clips.append(
                _prepare_render_video_clip(run_dir, video_source, item, strict=True)
                if revision_aware
                else _prepare_render_video_clip(run_dir, video_source, item)
            )
            if item.item_id not in selected_ids:
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
        selected_candidate = current_audio_candidate(narration)
        selected_narration_path = str(
            narration.get("output") or (selected_candidate or {}).get("output") or ""
        )
        if revision_aware:
            is_silent = str(narration.get("tool") or "").strip().lower() == "silent"
            if is_silent and item.narration_path:
                raise NarrationRevisionConflict("revision-aware silent render audio is materialized by the server")
            if not is_silent and item.narration_path and item.narration_path != selected_narration_path:
                raise NarrationRevisionConflict(
                    f"render narration path differs from the current narration output: {item.item_id}"
                )
            narration_path = "" if is_silent else selected_narration_path
        else:
            narration_path = item.narration_path or selected_narration_path
            if item.narration_path and item.narration_path != selected_narration_path:
                raise ValueError("結合するナレーションがp860で承認した音声と異なります")
        if _narration_has_intentional_silence(narration) and not narration_path:
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
    audio_set_hash = _manifest_narration_audio_set_hash(data)
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
    sound_plan_path = review_dir / (f"sound_render_{safe_snapshot}.json" if snapshot_id else "sound_render_latest.json")
    clips_text = "\n".join(_concat_list_line(path) for path in clips) + ("\n" if clips else "")
    narration_text = "\n".join(_concat_list_line(path) for path in narrations) + ("\n" if narrations else "")
    plan_text = (
        json.dumps(
            {
                "output": req.output,
                "clips": [str(path) for path in clips],
                "narrations": [str(path) for path in narrations],
                "items": [_model_dump(item) for item in req.items],
                "audioSetHash": audio_set_hash,
                "timelineHash": timeline_hash,
                "soundHash": sound_snapshot["sound_hash"],
                "soundPlan": sound_plan_path.relative_to(run_dir).as_posix(),
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
        sound_plan_path,
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
        sound_design.write_json(run_dir, sound_plan_path.relative_to(run_dir).as_posix(), sound_snapshot)
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
        "audioSetHash": audio_set_hash,
        "timelineHash": timeline_hash,
        "soundHash": sound_snapshot["sound_hash"],
        "soundPlan": sound_plan_path.relative_to(run_dir).as_posix(),
    }


def _require_frozen_render_narration_current(run_dir: Path, freeze_result: dict[str, Any]) -> None:
    expected_audio_set_hash = str(freeze_result.get("audioSetHash") or "")
    expected_timeline_hash = str(freeze_result.get("timelineHash") or "")
    if not expected_audio_set_hash and not expected_timeline_hash:
        return
    _require_narration_ready_for_video(run_dir)
    _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    if (
        _manifest_narration_audio_set_hash(data) != expected_audio_set_hash
        or _manifest_narration_timeline_hash(data) != expected_timeline_hash
    ):
        raise NarrationRevisionConflict(
            "narration audio set or timeline changed while final render was running; render is stale"
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
    if freeze_result.get("soundPlan"):
        command.extend(["--sound-plan", str(run_dir / freeze_result["soundPlan"])])
    binding = _assert_bound_run_root(run_dir)
    # A surviving renderer keeps the directory lease even if its server dies.
    stdout, stderr = await _run_resume_subprocess_command(command, timeout_seconds=3600,
        pass_fds=(binding.descriptor,) if binding is not None else ())
    async with _serialized_run_write(run_dir, "run_artifacts"):
        try:
            _require_frozen_render_narration_current(run_dir, freeze_result)
            if freeze_result.get("soundHash"):
                _, _, current_manifest = _read_manifest_data(run_dir)
                try:
                    current_sound_hash = _sound_design_api.freeze(run_dir, current_manifest)["sound_hash"]
                except ValueError as exc:
                    raise NarrationRevisionConflict(str(exc)) from exc
                if current_sound_hash != freeze_result["soundHash"]:
                    raise NarrationRevisionConflict("BGM・SEまたは動画がレンダー中に変更されました。再結合してください")
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


def _scene_visualizable_action(scene: dict[str, Any]) -> Any:
    """Return scene-wide action context without exposing provider-only fields."""

    top_level = scene.get("visualizable_action")
    if isinstance(top_level, str) and top_level.strip():
        return top_level
    if not isinstance(top_level, str) and top_level:
        return top_level
    return None


def _review_native_audio(generation: dict[str, Any], item: FrontendReviewItem) -> dict[str, Any]:
    from toc.cinematic_language import normalize_native_audio
    audio = deepcopy(_dict_value(generation.get('native_audio')) or {'mode': 'off'})
    if item.video_native_audio_mode is not None:
        audio['mode'] = item.video_native_audio_mode
        if audio['mode'] == 'off':
            audio = {'mode': 'off', 'sound_events': [], 'dialogue': []}
        elif audio['mode'] == 'natural_sound':
            audio['dialogue'] = []
    return normalize_native_audio(audio)


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
    video_generation = deepcopy(node.get("video_generation")) if isinstance(node.get("video_generation"), dict) else {}
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
    selected_input_mode = item.video_input_mode or video_generation.get('input_mode')
    if input_contract and selected_input_mode and selected_input_mode != input_contract.get('input_mode'):
        raise ValueError('render-unit input mode must preserve its canonical input contract')
    reference_image_mode = input_contract.get('input_mode') == 'reference_images' or selected_input_mode == 'reference_images'
    if reference_image_mode:
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
    if reference_image_mode:
        if (item.video_first_reference or '').strip() or (item.video_last_reference or '').strip():
            raise ValueError('reference-image mode cannot include frame boundaries')
        last_frame = ''
    native_audio = _review_native_audio(video_generation, item)
    if 'native_audio' in video_generation or item.video_native_audio_mode is not None:
        video_generation['native_audio'] = native_audio
    execution_options = _server_video_execution_options(
        tool=tool,
        has_first_frame=bool(first_frame),
        has_reference_images=bool(item.video_references),
        native_audio_mode=native_audio['mode'],
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
        source_context=_video_source_context_for_server_target(
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
            _scene_visualizable_action(scene)
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
            or (effective_item.video_input_mode or generation.get('input_mode')) == 'reference_images'
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
            native_audio_mode=_review_native_audio(generation, effective_item)['mode'],
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
    reference_image_mode = (input_contract.get("input_mode") == "reference_images"
        or item.video_input_mode == 'reference_images'
        or _dict_value(target_node.get('video_generation')).get('input_mode') == 'reference_images')
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


def _video_request_binding(
    run_dir: Path,
    item_id: str,
) -> dict[str, Any]:
    path = run_dir / "video_generation_requests.md"
    if not path.is_file():
        raise ValueError("video generation request is missing")
    _prefix, sections = _split_video_request_sections(path.read_text(encoding="utf-8"))
    matches = [lines for title, lines in sections if title == item_id]
    if len(matches) != 1:
        raise ValueError("video generation request is missing or duplicated")
    # Section separators add/remove trailing blank lines during partial merges.
    # Bind approval to the canonical section content, not file-layout whitespace.
    body = "\n".join(matches[0]).strip()

    def scalar(name: str) -> str:
        matches = re.findall(
            rf"(?m)^- {re.escape(name)}: `([^`]*)`\s*$",
            body,
        )
        if len(matches) > 1:
            raise ValueError(
                f"video generation request duplicates {name}"
            )
        return matches[0].strip() if matches else ""

    def fenced(name: str) -> tuple[str, int]:
        matches = re.findall(
            rf"(?ms)```{re.escape(name)}\s*\n(.*?)\n```",
            body,
        )
        if len(matches) > 1:
            raise ValueError(
                f"video generation request duplicates {name}"
            )
        return (
            matches[0].strip() if matches else "",
            len(matches),
        )

    def list_values(name: str) -> list[str]:
        matches = re.findall(
            rf"(?ms)^- {re.escape(name)}:\s*\n"
            r"((?:  - `[^`]*`\s*(?:\n|$))*)",
            body,
        )
        if len(matches) > 1:
            raise ValueError(
                f"video generation request duplicates {name}"
            )
        if not matches:
            return []
        return [
            value.strip()
            for value in re.findall(
                r"(?m)^  - `([^`]*)`\s*$",
                matches[0],
            )
            if value.strip()
        ]

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
        "storyboard_image",
    )
    video_prompt, video_prompt_count = fenced("video_prompt")
    api_prompt, api_prompt_count = fenced("api_prompt")
    if video_prompt_count and api_prompt_count:
        raise ValueError(
            "video generation request has both video_prompt and api_prompt"
        )
    negative_prompt, _negative_prompt_count = fenced(
        "negative_prompt"
    )
    return {
        **{field: scalar(field) for field in fields},
        "prompt": video_prompt or api_prompt,
        "negative_prompt": negative_prompt,
        "source_cuts": list_values("source_cuts"),
        "references": list_values("references"),
        "request_section_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


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
        video_input_mode=generation.get('input_mode'),
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

    binding = _video_request_binding(run_dir, selector)
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
    _prefix, _existing_sections = _split_video_request_sections(existing_text)
    if replace_all or not path.exists():
        text = "\n\n".join(["# Video Generation Requests", *sections_by_id.values()]).rstrip() + "\n"
    else:
        text = _merge_video_request_sections(
            existing_text,
            sections_by_id,
            canonical_item_ids=canonical_item_ids,
        )
    path.write_text(text, encoding="utf-8")
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


def _storyboard_cut_id(
    cut: dict[str, Any],
    _cut_index: int,
    used_cut_ids: set[str],
) -> str:
    raw = str(cut.get("cut_id") or "").strip()
    normalized = normalize_dotted_id(raw)
    if normalized is None:
        raise RuntimeError(
            "storyboard create failed: active cut has a missing or invalid "
            f"canonical cut_id: {raw or '(missing)'}"
        )
    if normalized in used_cut_ids:
        raise RuntimeError(f"storyboard create failed: duplicate cut_id {normalized}")
    used_cut_ids.add(normalized)
    return _require_markdown_scalar(normalized, field="source_cut_id")


def _storyboard_cut_duration(cut: dict[str, Any]) -> int:
    duration = cut.get("duration_seconds")
    if (
        not isinstance(duration, int)
        or isinstance(duration, bool)
        or duration <= 0
    ):
        raise RuntimeError(
            "storyboard create failed: active cut has a missing or invalid "
            "canonical duration_seconds"
        )
    return duration


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

    temporary = out_path.with_name(
        f".{out_path.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        canvas.save(temporary, format="PNG")
        validate_image_bytes(temporary)
        os.replace(temporary, out_path)
        validate_image_bytes(out_path)
    finally:
        temporary.unlink(missing_ok=True)


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
    _atomic_write_text(path, "\n".join(lines).rstrip() + "\n")
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


def _materialize_scene_storyboard_video_requests_unchecked(
    run_id: str,
    *,
    run_dir_override: Path | None = None,
    canonical_run_dir: Path | None = None,
    write_state: bool = True,
) -> dict[str, Any]:
    run_dir = (
        run_dir_override
        if run_dir_override is not None
        else safe_run_dir(run_id, ROOT)
    )
    artifact_run_dir = canonical_run_dir or run_dir
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
        # Detach the direct scene mapping before adding the execution overlay.
        # YAML aliases otherwise let this assignment mutate a second,
        # non-scene manifest location through shared object identity.
        scene = dict(scene)
        scenes[scene_index - 1] = scene
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
            source_context = {
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
                source_context=source_context,
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
                    _scene_visualizable_action(scene)
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
                    "source_cut_image_sha256s": (
                        _video_reference_content_sha256(
                            run_dir,
                            group_outputs,
                        )
                    ),
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
    state_updates = {
        "runtime.create_mode": CREATE_MODE_SCENE_STORYBOARD,
        "runtime.stage": "scene_storyboard_video_requests_ready",
        "review.frontend.storyboard.status": "ready",
        "slot.p830.status": "done",
        "slot.p830.note": "storyboard video prompts are materialized and ready",
        "stage.video_generation.status": "ready",
        "artifact.scene_storyboards": ",".join(storyboard_paths),
        "artifact.video_generation_requests": str(
            (artifact_run_dir / "video_generation_requests.md").resolve()
        ),
    }
    if write_state:
        append_state_snapshot(
            run_dir / "state.txt",
            state_updates,
        )
    return {
        "storyboards": storyboard_paths,
        "videoRequestPath": request_path.relative_to(run_dir).as_posix(),
        "unitCount": len(units),
        "_stateUpdates": state_updates,
    }


def _validate_unique_storyboard_scene_selectors(
    data: dict[str, Any],
) -> None:
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        raise RuntimeError(
            "storyboard create failed: video_manifest.md scenes must be a list"
        )
    seen: dict[str, tuple[int, str]] = {}
    for scene_index, scene in enumerate(scenes, start=1):
        if (
            not isinstance(scene, dict)
            or str(scene.get("kind") or "").strip().endswith("_reference")
        ):
            continue
        selector = _storyboard_scene_selector(scene, scene_index)
        collision_key = unicodedata.normalize("NFC", selector).casefold()
        previous = seen.get(collision_key)
        if previous is not None:
            previous_index, previous_selector = previous
            raise RuntimeError(
                "storyboard create failed: duplicate storyboard scene selector "
                f"{selector!r} for scene {previous_index} "
                f"({previous_selector!r}) and scene {scene_index}"
            )
        seen[collision_key] = (scene_index, selector)


STORYBOARD_TRANSACTION_REL = Path(
    "logs/transactions/storyboard_create_pending"
)
STORYBOARD_TRANSACTION_CORE_TARGETS = {
    "video_manifest.md",
    "video_generation_requests.md",
}


def _validate_storyboard_storage_paths(run_dir: Path) -> None:
    for relative in (
        Path("assets"),
        Path("assets/storyboards"),
        Path("logs"),
        Path("logs/transactions"),
        STORYBOARD_TRANSACTION_REL,
    ):
        current = run_dir
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise RuntimeError(
                    "storyboard storage path must not be a symlink: "
                    f"{current.relative_to(run_dir)}"
                )


def _storyboard_transaction_target_allowed(relative: str) -> bool:
    path = Path(relative)
    if (
        not relative
        or path.is_absolute()
        or path.as_posix() != relative
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return False
    normalized = path.as_posix()
    return (
        normalized in STORYBOARD_TRANSACTION_CORE_TARGETS
        or (
            path.parent == Path("assets/storyboards")
            and path.suffix.lower() == ".png"
        )
    )


def _storyboard_transaction_target_path(
    run_dir: Path,
    relative: str,
) -> Path:
    if not _storyboard_transaction_target_allowed(relative):
        raise RuntimeError(
            "storyboard transaction target is outside the allowed set"
        )
    current = run_dir
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise RuntimeError(
                "storyboard transaction target path must not contain symlinks"
            )
    return current


def _storyboard_transaction_dir(run_dir: Path) -> Path:
    return run_dir / STORYBOARD_TRANSACTION_REL


def _recover_storyboard_transaction(run_dir: Path) -> None:
    _validate_storyboard_storage_paths(run_dir)
    transaction_dir = _storyboard_transaction_dir(run_dir)
    if not transaction_dir.exists():
        return
    if not transaction_dir.is_dir() or transaction_dir.is_symlink():
        raise RuntimeError(
            "storyboard transaction path must be a real directory"
        )
    marker_path = transaction_dir / "marker.json"
    if not marker_path.is_file():
        shutil.rmtree(transaction_dir)
        return
    if marker_path.is_symlink():
        raise RuntimeError(
            "storyboard transaction marker must not be a symlink"
        )
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(marker_path, flags)
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            marker = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "storyboard transaction marker is unreadable"
        ) from exc
    targets = marker.get("targets")
    if (
        marker.get("schemaVersion") != "storyboard_transaction_v1"
        or not isinstance(targets, list)
    ):
        raise RuntimeError(
            "storyboard transaction marker is invalid"
        )
    for item in targets:
        if not isinstance(item, dict):
            raise RuntimeError(
                "storyboard transaction target is invalid"
            )
        relative = str(item.get("path") or "")
        if relative in {
            "state.txt",
            "state.current.json",
            "run_status.json",
            "p000_index.md",
        }:
            # Older pending markers may list state artifacts.  Never restore
            # or unlink a committed append-only log or its projections.
            continue
        target = _storyboard_transaction_target_path(
            run_dir,
            relative,
        )
        existed = item.get("existed")
        if existed is True:
            backup_name = str(item.get("backup") or "")
            backup = transaction_dir / backup_name
            if (
                Path(backup_name).name != backup_name
                or not backup.is_file()
                or backup.is_symlink()
            ):
                raise RuntimeError(
                    "storyboard transaction backup is missing or unsafe"
                )
            _atomic_write_bytes(target, backup.read_bytes())
        elif existed is False:
            target.unlink(missing_ok=True)
        else:
            raise RuntimeError(
                "storyboard transaction target existence flag is invalid"
            )
    shutil.rmtree(transaction_dir)


def _prepare_storyboard_transaction(
    run_dir: Path,
    relative_targets: Iterable[str],
) -> Path:
    _recover_storyboard_transaction(run_dir)
    transaction_dir = _storyboard_transaction_dir(run_dir)
    transaction_dir.mkdir(parents=True, exist_ok=False)
    entries: list[dict[str, Any]] = []
    try:
        for index, relative in enumerate(
            dict.fromkeys(relative_targets)
        ):
            if not _storyboard_transaction_target_allowed(relative):
                raise RuntimeError(
                    "storyboard transaction target is outside the allowed set"
                )
            target = _storyboard_transaction_target_path(
                run_dir,
                relative,
            )
            existed = target.is_file()
            backup_name = ""
            if existed:
                backup_name = f"backup_{index:04d}.bin"
                _atomic_write_bytes(
                    transaction_dir / backup_name,
                    target.read_bytes(),
                )
            entries.append(
                {
                    "path": relative,
                    "existed": existed,
                    "backup": backup_name,
                }
            )
        _atomic_write_text(
            transaction_dir / "marker.json",
            json.dumps(
                {
                    "schemaVersion": "storyboard_transaction_v1",
                    "status": "committing",
                    "targets": entries,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
        )
    except Exception:
        shutil.rmtree(transaction_dir, ignore_errors=True)
        raise
    return transaction_dir


def _copy_storyboard_stage_file(source: str, destination: str) -> str:
    """Copy a canonical input into the mutable storyboard workspace.

    Hard-linking made the supposedly isolated staging tree share canonical
    inodes.  Besides violating the single-link invariant used by retained-FD
    readers, any in-place staged edit could mutate the canonical run before
    the transaction committed.
    """

    return shutil.copy2(source, destination)


def _materialize_scene_storyboard_video_requests(
    run_id: str,
) -> dict[str, Any]:
    run_dir = safe_run_dir(run_id, ROOT)
    _recover_storyboard_transaction(run_dir)
    _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    _validate_unique_storyboard_scene_selectors(data)
    review_projection_before = (
        manifest_source_sha256(
            run_dir / "video_manifest.md"
        )
    )
    with tempfile.TemporaryDirectory(
        prefix=f".{run_id}.storyboard-stage-",
        dir=run_dir.parent,
    ) as staging_tmp:
        staging_run_dir = Path(staging_tmp)
        shutil.copytree(
            run_dir,
            staging_run_dir,
            dirs_exist_ok=True,
            copy_function=_copy_storyboard_stage_file,
            symlinks=True,
        )
        staged_result = (
            _materialize_scene_storyboard_video_requests_unchecked(
                run_id,
                run_dir_override=staging_run_dir,
                canonical_run_dir=run_dir,
                write_state=False,
            )
        )
        staged_review_projection = (
            manifest_source_sha256(
                staging_run_dir / "video_manifest.md"
            )
        )
        if staged_review_projection != review_projection_before:
            raise RuntimeError(
                "storyboard materialization review projection changed before "
                "transaction commit"
            )
        _validate_scene_storyboard_create_run(
            run_id,
            strict_visual_quality=False,
            run_dir_override=staging_run_dir,
            validate_base=False,
        )
        storyboard_paths = [
            str(path)
            for path in staged_result.get("storyboards", [])
        ]
        relative_targets = [
            *storyboard_paths,
            "video_generation_requests.md",
            "video_manifest.md",
        ]
        transaction_dir = _prepare_storyboard_transaction(
            run_dir,
            relative_targets,
        )
        try:
            for relative in storyboard_paths:
                staged_path = resolve_run_relative(
                    staging_run_dir,
                    relative,
                )
                validate_image_bytes(staged_path)
                _atomic_write_bytes(
                    _storyboard_transaction_target_path(
                        run_dir,
                        relative,
                    ),
                    staged_path.read_bytes(),
                )
            for relative in (
                "video_generation_requests.md",
                "video_manifest.md",
            ):
                _atomic_write_bytes(
                    _storyboard_transaction_target_path(
                        run_dir,
                        relative,
                    ),
                    resolve_run_relative(
                        staging_run_dir,
                        relative,
                    ).read_bytes(),
                )
            if (
                manifest_source_sha256(
                    run_dir / "video_manifest.md"
                )
                != review_projection_before
            ):
                raise RuntimeError(
                    "storyboard materialization review projection changed "
                    "during transaction commit"
                )
            state_updates = staged_result.get("_stateUpdates")
            if not isinstance(state_updates, dict):
                raise RuntimeError(
                    "storyboard staging did not return state updates"
                )
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    str(key): str(value)
                    for key, value in state_updates.items()
                },
            )
        except Exception:
            _recover_storyboard_transaction(run_dir)
            raise
        shutil.rmtree(transaction_dir)
        return {
            key: value
            for key, value in staged_result.items()
            if not key.startswith("_")
        }


def _validate_scene_storyboard_create_run(
    run_id: str,
    *,
    strict_visual_quality: bool = True,
    run_dir_override: Path | None = None,
    validate_base: bool = True,
) -> None:
    run_dir = (
        run_dir_override
        if run_dir_override is not None
        else safe_run_dir(run_id, ROOT)
    )
    if run_dir_override is None:
        _recover_storyboard_transaction(run_dir)
    if validate_base:
        _validate_frontend_create_run(
            run_id,
            strict_visual_quality=strict_visual_quality,
        )
    _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        raise RuntimeError("storyboard create incomplete: video_manifest.md scenes must be a list")
    _validate_unique_storyboard_scene_selectors(data)
    render_unit_issues = _render_unit_timeline_issues(data)
    if render_unit_issues:
        raise RuntimeError(
            "storyboard create incomplete: invalid render-unit timeline: "
            + "; ".join(render_unit_issues[:20])
        )
    expected_units: list[str] = []
    expected_bindings: dict[str, dict[str, Any]] = {}
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
            try:
                _validate_run_relative_image_path(
                    run_dir,
                    storyboard,
                    must_exist=True,
                )
                storyboard_path = resolve_run_relative(
                    run_dir,
                    storyboard,
                )
                validate_image_bytes(storyboard_path)
                from PIL import Image  # type: ignore[import-not-found]

                with Image.open(storyboard_path) as storyboard_image:
                    storyboard_size = storyboard_image.size
                    storyboard_image.verify()
            except Exception as exc:
                raise RuntimeError(
                    "storyboard create incomplete: "
                    f"{scene_selector} render_unit storyboard image is invalid: "
                    f"{exc}"
                ) from exc
            if storyboard_size != (1920, 1080):
                raise RuntimeError(
                    "storyboard create incomplete: "
                    f"{scene_selector} render_unit storyboard image must be "
                    f"1920x1080, got {storyboard_size[0]}x{storyboard_size[1]}"
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
            request_id = f"{scene_selector}_unit{normalized_unit_id}"
            if request_id in expected_bindings:
                raise RuntimeError(
                    "storyboard create incomplete: duplicate render unit request id "
                    f"{request_id}"
                )
            source_cut_ids = [
                str(value).strip()
                for value in _list_value(unit.get("source_cut_ids"))
                if str(value).strip()
            ]
            payload = _dict_value(
                video_generation.get("api_prompt_payload")
            )
            prompt = str(payload.get("prompt") or "")
            negative_prompt = str(payload.get("negative_prompt") or "")
            declared_prompt_sha256 = str(payload.get("sha256") or "")
            actual_prompt_sha256 = hashlib.sha256(
                prompt.encode("utf-8")
            ).hexdigest()
            if declared_prompt_sha256 != actual_prompt_sha256:
                raise RuntimeError(
                    "storyboard create incomplete: "
                    f"{request_id} manifest prompt_sha256 mismatch"
                )
            expected_units.append(request_id)
            expected_bindings[request_id] = {
                "tool": str(video_generation.get("tool") or "").strip(),
                "output": str(video_generation.get("output") or "").strip(),
                "duration_seconds": str(
                    int(video_generation.get("duration_seconds") or 0)
                ),
                "quality": str(
                    video_generation.get("quality") or ""
                ).strip(),
                "aspect_ratio": str(
                    video_generation.get("aspect_ratio") or ""
                ).strip(),
                "first_frame": "",
                "storyboard_image": storyboard,
                "prompt_policy_version": str(
                    payload.get("policy_version") or ""
                ).strip(),
                "compiler_version": str(
                    payload.get("compiler_version") or ""
                ).strip(),
                "source_digest": str(
                    payload.get("source_digest") or ""
                ).strip(),
                "prompt_sha256": declared_prompt_sha256,
                "negative_prompt_sha256": hashlib.sha256(
                    negative_prompt.encode("utf-8")
                ).hexdigest(),
                "references_digest": sha256_canonical_json(references),
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "source_cuts": source_cut_ids,
                "references": references,
            }
    if not expected_units:
        raise RuntimeError("storyboard create incomplete: no storyboard render_units found")
    request_path = run_dir / "video_generation_requests.md"
    if not request_path.is_file():
        raise RuntimeError("storyboard create incomplete: missing video_generation_requests.md")
    request_text = request_path.read_text(encoding="utf-8", errors="replace")
    _prefix, sections = _split_video_request_sections(request_text)
    actual_units = [title for title, _lines in sections]
    if actual_units != expected_units:
        raise RuntimeError(
            "storyboard create incomplete: video_generation_requests.md section "
            f"identity/order mismatch: expected={expected_units}, got={actual_units}"
        )
    for request_id, expected in expected_bindings.items():
        try:
            binding = _video_request_binding(
                run_dir,
                request_id,
            )
        except ValueError as exc:
            raise RuntimeError(
                "storyboard create incomplete: "
                f"{request_id} request section is missing or duplicated"
            ) from exc
        mismatches = [
            field
            for field, expected_value in expected.items()
            if binding.get(field) != expected_value
        ]
        if mismatches:
            raise RuntimeError(
                "storyboard create incomplete: "
                f"{request_id} request binding mismatch: "
                + ", ".join(mismatches)
            )


def _scene_storyboard_source_bindings_are_current(run_dir: Path) -> bool:
    """Bind currentness to every source cut and compiled reference byte."""

    try:
        _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    except (FileNotFoundError, OSError, TypeError, ValueError):
        return False
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        return False
    found_unit = False
    for scene in scenes:
        if (
            not isinstance(scene, dict)
            or str(scene.get("kind") or "").strip().endswith("_reference")
        ):
            continue
        render_units = scene.get("render_units")
        if not isinstance(render_units, list) or not render_units:
            return False
        cuts_by_id: dict[str, dict[str, Any]] = {}
        for cut in _list_value(scene.get("cuts")):
            if (
                not isinstance(cut, dict)
                or str(cut.get("cut_status") or "active").strip().lower()
                == "deleted"
            ):
                continue
            cut_id = normalize_dotted_id(cut.get("cut_id"))
            if cut_id is None or cut_id in cuts_by_id:
                return False
            cuts_by_id[cut_id] = cut
        for unit in render_units:
            if not isinstance(unit, dict):
                return False
            found_unit = True
            source_ids = [
                normalize_dotted_id(value)
                for value in _list_value(unit.get("source_cut_ids"))
            ]
            if (
                not source_ids
                or any(source_id is None for source_id in source_ids)
                or len(source_ids) != len(set(source_ids))
            ):
                return False
            source_outputs: list[str] = []
            for source_id in source_ids:
                cut = cuts_by_id.get(source_id or "")
                if cut is None:
                    return False
                generation = _dict_value(cut.get("image_generation"))
                output = str(generation.get("output") or "").strip()
                if not output:
                    return False
                source_outputs.append(output)
            stored_source_hashes = unit.get("source_cut_image_sha256s")
            if not isinstance(stored_source_hashes, dict):
                return False
            current_source_hashes = _video_reference_content_sha256(
                run_dir,
                source_outputs,
            )
            if (
                len(current_source_hashes) != len(source_outputs)
                or {
                    str(key): str(value)
                    for key, value in stored_source_hashes.items()
                }
                != current_source_hashes
            ):
                return False

            video_generation = _dict_value(unit.get("video_generation"))
            references = [
                str(value).strip()
                for value in _list_value(video_generation.get("references"))
                if str(value).strip()
            ]
            payload = _dict_value(
                video_generation.get("api_prompt_payload")
            )
            request_binding = _dict_value(
                payload.get("provider_request_binding")
            )
            execution_options = _dict_value(
                request_binding.get("execution_options")
            )
            stored_reference_hashes = execution_options.get(
                "reference_content_sha256"
            )
            if not isinstance(stored_reference_hashes, dict):
                return False
            current_reference_hashes = _video_reference_content_sha256(
                run_dir,
                references,
            )
            if (
                len(current_reference_hashes) != len(references)
                or {
                    str(key): str(value)
                    for key, value in stored_reference_hashes.items()
                }
                != current_reference_hashes
            ):
                return False
    return found_unit


def _scene_storyboard_materialization_is_current(run_id: str) -> bool:
    run_dir = safe_run_dir(run_id, ROOT)
    try:
        _validate_scene_storyboard_create_run(
            run_id,
            strict_visual_quality=False,
            validate_base=False,
        )
    except (FileNotFoundError, OSError, RuntimeError, TypeError, ValueError):
        return False
    return (
        _scene_storyboard_source_bindings_are_current(run_dir)
        and _video_prompt_stage_materialization_complete(run_dir)
    )


def _finalize_scene_storyboard_p680(run_id: str) -> dict[str, Any]:
    """Finalize one storyboard p680 handoff without changing reviewed inputs."""

    run_dir = safe_run_dir(run_id, ROOT)
    _validate_frontend_create_run(
        run_id,
        strict_visual_quality=True,
    )
    if _scene_storyboard_materialization_is_current(run_id):
        _validate_frontend_create_run(
            run_id,
            strict_visual_quality=True,
        )
        return {"alreadyCurrent": True}

    review_projection_before = (
        manifest_source_sha256(
            run_dir / "video_manifest.md"
        )
    )
    result = dict(
        _materialize_scene_storyboard_video_requests(run_id)
    )
    review_projection_after = (
        manifest_source_sha256(
            run_dir / "video_manifest.md"
        )
    )
    if review_projection_after != review_projection_before:
        raise RuntimeError(
            "storyboard p680 finalizer changed the review projection"
        )
    _validate_scene_storyboard_create_run(
        run_id,
        strict_visual_quality=False,
        validate_base=False,
    )
    _validate_frontend_create_run(
        run_id,
        strict_visual_quality=True,
    )
    result["alreadyCurrent"] = False
    return result


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
        reference_image_mode = (input_contract.get("input_mode") == "reference_images"
            or (item.video_input_mode or video_generation.get('input_mode')) == 'reference_images')
        if item.video_input_mode is not None:
            video_generation['input_mode'] = item.video_input_mode
        if item.video_native_audio_mode is not None:
            video_generation['native_audio'] = _review_native_audio(video_generation, item)
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
        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            character_ids=character_ids,
            object_ids=object_ids,
            location_ids=location_ids,
            reference_images=references,
            story_time=story_time,
            scene_time_of_day=scene_time_of_day,
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


def _recompile_image_prompt_payloads_from_plans(run_dir: Path) -> list[str]:
    """Rebuild every compiled-v2 payload from the repaired visual-plan source."""

    if current_run_root_binding() is None:
        named = os.stat(run_dir, follow_symlinks=False)
        with bind_run_root(
            run_dir,
            expected_identity=(named.st_dev, named.st_ino),
        ):
            return _recompile_image_prompt_payloads_from_plans(run_dir)
    _assert_bound_run_root(run_dir)
    manifest_path = run_dir / "video_manifest.md"
    try:
        original_text = read_run_file_bytes(
            run_dir,
            "video_manifest.md",
        ).decode("utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError("video_manifest.md not found") from exc
    except UnicodeDecodeError as exc:
        raise ValueError("video_manifest.md must be UTF-8") from exc
    data = yaml.safe_load(_extract_manifest_yaml_text(original_text)) or {}
    if not isinstance(data, dict):
        raise ValueError("video_manifest.md YAML root must be a mapping")
    story_time = str(_dict_value(data.get("video_metadata")).get("time") or "").strip()
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
        payload = compile_image_api_prompt_v2(
            first_frame_visual_plan=plan,
            character_ids=character_ids,
            object_ids=object_ids,
            location_ids=location_ids,
            reference_images=references,
            story_time=story_time,
            scene_time_of_day=scene_time_of_day,
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
        write_run_file_text(
            run_dir,
            manifest_path.name,
            _render_manifest_data(original_text, data),
        )
    return changed_selectors


def _synchronize_image_prompt_requests(
    run_dir: Path,
    *,
    precompiled_selectors: Iterable[str] | None = None,
) -> None:
    """Compile repaired plans and atomically rematerialize request + snapshot files."""

    _assert_bound_run_root(run_dir)

    tracked_paths = (
        run_dir / "video_manifest.md",
        run_dir / "image_generation_requests.md",
        run_dir / "image_generation_request_snapshot.json",
        run_dir / "asset_generation_requests.md",
        run_dir / "asset_generation_request_snapshot.json",
        run_dir / "asset_generation_manifest.md",
        run_dir / "asset_plan.md",
    )
    before = _capture_file_transaction(
        tracked_paths,
        state_paths=(run_dir / "state.txt",),
    )
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
        compiled_selectors = (
            list(precompiled_selectors)
            if precompiled_selectors is not None
            else _recompile_image_prompt_payloads_from_plans(run_dir)
        )
        _write_asset_request_files(run_dir)
        result = _run_bound_subprocess(
            run_dir,
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
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(detail or "image prompt request rematerialization failed")
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
            "generation.image_prompt.request_sync.status": "done",
            "generation.image_prompt.request_sync.compiled_count": str(len(compiled_selectors)),
            "generation.image_prompt.request_sync.compiled_selectors": ", ".join(compiled_selectors),
            "generation.image_prompt.request_sync.synced_at": now_iso(),
            "generation.image_prompt.asset_refresh_required": str(asset_request_changed).lower(),
            "generation.image_prompt.request_freeze.status": "draft",
            "artifact.image_generation_requests": str(tracked_paths[1].resolve()),
            "artifact.image_generation_request_snapshot": str(tracked_paths[2].resolve()),
        },
    )


def _assert_image_prompt_request_revision_unchanged(
    run_dir: Path,
    *,
    expected_request_revision: str,
    require_resolved_references: bool,
) -> str:
    """Fail when the request reviewed by the agent is no longer current."""

    expected = str(expected_request_revision or "").strip()
    if not expected:
        raise RuntimeError(
            "image prompt semantic review is missing its expected request revision"
        )
    _manifest_path, _original_text, manifest_data = _read_manifest_data(run_dir)
    current = _validate_image_prompt_request_revision(
        run_dir,
        manifest_data,
        require_resolved_references=require_resolved_references,
        require_compiled_v2=True,
    )
    if current != expected:
        raise RuntimeError(
            "image prompt request revision changed during semantic review "
            f"(expected={expected}, current={current})"
        )
    return current


def _mark_image_prompt_request_freeze_done(
    run_dir: Path, *, expected_request_revision: str | None = None,
) -> None:
    """Freeze the current provider payload and resolved reference bytes."""
    _prepare_image_prompt_request_revision(run_dir)
    _manifest_path, _manifest_text, manifest = _read_manifest_data(run_dir)
    revision = _validate_image_prompt_request_revision(
        run_dir, manifest,
        require_resolved_references=True, require_compiled_v2=True,
    )
    if expected_request_revision is not None and revision != expected_request_revision:
        raise RuntimeError("image request revision changed before freeze")
    _finalize_p600_supervisor_result(
        run_dir, completed_slots=("p610", "p620", "p650"),
        terminal_slot="p650", terminal_status="done",
    )
    append_state_snapshot(run_dir / "state.txt", {
        "generation.image_prompt.request_freeze.status": "frozen",
        "generation.image_prompt.request_freeze.request_revision": revision,
        "generation.image_prompt.request_freeze.frozen_at": now_iso(),
        "slot.p650.status": "done",
        "slot.p650.note": "compiled requests and reference bytes frozen",
    })


def _finalize_p600_supervisor_result(
    run_dir: Path,
    *,
    completed_slots: Iterable[str],
    terminal_slot: str,
    terminal_status: str,
) -> None:
    """Advance the p600 supervisor artifact to the latest truthful handoff."""

    result_path = run_dir / "logs/orchestration/p600.supervisor_result.json"
    if not result_path.is_file():
        raise RuntimeError(
            "p600 supervisor result is missing; refusing to publish a later handoff"
        )
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "p600 supervisor result is malformed; refusing to publish a later handoff"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(
            "p600 supervisor result is malformed; refusing to publish a later handoff"
        )
    completed = _dedupe_preserve_order(
        [
            *[str(value).strip() for value in payload.get("completed_slots") or [] if str(value).strip()],
            *[str(value).strip() for value in completed_slots if str(value).strip()],
        ]
    )
    payload.pop("review_outputs", None)
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
        if (
            payload.get("provenanceInvalidation") is True
            and str(payload.get("operation") or "") == "candidate_insertion"
            and str(payload.get("status") or "").lower() == "invalidated"
        ):
            # The log directory is reverse chronological.  A later canonical
            # generation receipt may re-establish provenance, but an insertion
            # receipt always supersedes every older provider receipt—even when
            # the candidate is byte-identical to the previous output.
            return False
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


async def _generate_request_item_output(
    *,
    run_dir: Path,
    kind: str,
    item: Any,
) -> str:
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
        repair = RepairSession(run_dir, 'p560' if kind == 'asset' else 'p660',
            binding={'item': str(item.id), 'request': str(getattr(item, 'request_digest', '') or ''), 'prompt': str(item.prompt)},
            stage_limit=100000, run_limit=100000, unit_limit=2, budget_group='media')
        while True:
            repair.claim(str(item.id))
            try:
                outcome = await _generate_request_item_output_with_slot(run_dir=run_dir, kind=kind, item=item)
                repair.complete(str(item.id))
                return outcome
            except MediaOutputError as exc:
                repair.feedback(str(item.id), {'output': str(item.output), 'prompt': str(item.prompt)}, [str(exc)])


def _prepare_bound_image_provider_workspace(
    *,
    run_dir: Path,
    destination: Path,
    references: list[Path],
    binding: RunRootBinding | None,
) -> tuple[
    tempfile.TemporaryDirectory[str] | None,
    Path,
    Path,
    list[Path],
]:
    """Detach external provider inputs from a mutable run pathname."""

    if binding is None:
        return None, run_dir, destination, references
    _assert_bound_run_root(run_dir)
    workspace_lease = tempfile.TemporaryDirectory(
        prefix="toc-image-provider-",
    )
    workspace = Path(workspace_lease.name)
    provider_references: list[Path] = []
    try:
        for index, reference in enumerate(references, start=1):
            try:
                relative = reference.relative_to(run_dir)
            except ValueError as exc:
                raise RunRootBindingError(
                    f"provider reference escapes the bound run: {reference}"
                ) from exc
            data = read_regular_file_nofollow(
                Path(binding.lexical_root),
                relative,
                expected_root_identity=binding.identity,
            )
            private_parent = workspace / "references" / f"{index:03d}"
            private_parent.mkdir(parents=True, exist_ok=False)
            private_reference = private_parent / reference.name
            private_reference.write_bytes(data)
            require_image_file(private_reference)
            validate_image_bytes(private_reference)
            provider_references.append(private_reference)
        provider_output = (
            workspace
            / "generated"
            / f"candidate{destination.suffix.lower()}"
        )
        provider_output.parent.mkdir(parents=True, exist_ok=False)
        _assert_bound_run_root(run_dir)
        return (
            workspace_lease,
            workspace,
            provider_output,
            provider_references,
        )
    except BaseException:
        workspace_lease.cleanup()
        raise


def _assert_bound_generation_item_is_current(
    *,
    run_dir: Path,
    kind: str,
    item: Any,
    binding: RunRootBinding | None,
) -> None:
    """Rebind a provider item to the descriptor-read canonical snapshot."""

    if binding is None or not str(
        getattr(item, "request_revision", "") or ""
    ).strip():
        return
    current_items = load_request_items(run_dir, kind)
    current = next(
        (
            candidate
            for candidate in current_items
            if str(getattr(candidate, "id", "") or "")
            == str(getattr(item, "id", "") or "")
        ),
        None,
    )
    if current is None:
        raise RunRootBindingError(
            f"provider item disappeared from the bound snapshot: {item.id}"
        )
    fields = (
        "prompt",
        "output",
        "references",
        "prompt_sha256",
        "reference_sha256s",
        "request_revision",
        "request_digest",
        "compiler_version",
        "source_digest",
    )
    changed = [
        field
        for field in fields
        if getattr(current, field, None) != getattr(item, field, None)
    ]
    if changed:
        raise RunRootBindingError(
            f"provider item changed after review for {item.id}: "
            + ", ".join(changed)
        )


async def _generate_request_item_output_with_slot(
    *,
    run_dir: Path,
    kind: str,
    item: Any,
) -> str:
    run_dir = Path(os.path.abspath(os.fspath(run_dir)))
    binding = _assert_bound_run_root(run_dir)
    if not getattr(item, "output", None):
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="request_item_generation",
            status="skipped",
            item_id=str(getattr(item, "id", "")),
            request={"kind": kind, "reason": "missing output"},
        )
        return "skipped"
    if not str(getattr(item, "prompt", "") or "").strip():
        raise RuntimeError(f"{kind} request has no prompt: {item.id}")
    try:
        _destination_relative, destination = _validate_generation_destination_nofollow(
            run_dir,
            str(item.output),
            kind=kind,
        )
    except ValueError as exc:
        raise RuntimeError(
            f"unsafe {kind} request output for {item.id}: {exc}"
        ) from exc
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
    destination_decodes = False
    if destination.exists():
        try:
            validate_image_bytes(destination)
            from PIL import Image
            with Image.open(destination) as existing:
                existing.verify()
            destination_decodes = True
        except (ValueError, OSError):
            pass
        if destination_decodes and _has_completed_app_server_image_provenance(
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
            return "reused"
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
    (
        provider_workspace_lease,
        provider_run_dir,
        provider_destination,
        provider_references,
    ) = _prepare_bound_image_provider_workspace(
        run_dir=run_dir,
        destination=destination,
        references=references,
        binding=binding,
    )
    _assert_bound_generation_item_is_current(
        run_dir=run_dir,
        kind=kind,
        item=item,
        binding=binding,
    )
    if binding is not None:
        isolated_reference_sha256s = [
            _file_sha256(reference)
            for reference in provider_references
        ]
        if isolated_reference_sha256s != reference_sha256s:
            provider_workspace_lease.cleanup()
            raise RunRootBindingError(
                "provider reference snapshot changed while isolating inputs"
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
        cwd=provider_run_dir,
        scrub_sensitive_env=True,
        require_chatgpt_account=True,
        require_chatgpt_pro=True,
    )
    result = None
    debug_log = None
    retention_record: dict[str, Any] | None = None
    copy_receipt: _GenerationDestinationCopyReceipt | None = None
    try:
        _assert_bound_run_root(run_dir)
        await asyncio.wait_for(client.start(), timeout=CODEX_APP_SERVER_START_TIMEOUT_SECONDS)
        async with _generated_images_fallback_claim_scope(allow_generated_images_fallback):
            generated_root = client.generated_images_root() if hasattr(client, "generated_images_root") else None
            fallback_cutoff_ns = latest_generated_image_mtime_ns(generated_root) if allow_generated_images_fallback else None
            for attempt in range(1, IMAGE_GENERATION_ITEM_MAX_ATTEMPTS + 1):
                try:
                    # This is the last root-identity check before an
                    # irreversible external submission. Provider inputs and
                    # cwd are private copies, so a later lexical rename cannot
                    # redirect the in-flight request into another run.
                    _assert_bound_run_root(run_dir)
                    _assert_bound_generation_item_is_current(
                        run_dir=run_dir,
                        kind=kind,
                        item=item,
                        binding=binding,
                    )
                    result = await asyncio.wait_for(
                        client.generate_image(
                            prompt=item.prompt,
                            output_path=provider_destination,
                            reference_images=provider_references,
                            item_id=item.id,
                            run_dir=provider_run_dir,
                            fallback_cutoff_ns=fallback_cutoff_ns,
                            generation_job_id=generation_job_id,
                            allow_generated_images_fallback=allow_generated_images_fallback,
                            provenance_policy=provenance_policy,
                            timeout_seconds=max(1, int(IMAGE_GENERATION_ITEM_TIMEOUT_SECONDS)),
                        ),
                        timeout=_image_generation_outer_timeout_seconds(),
                    )
                    if result.saved_path is None:
                        raise MediaOutputError(f"Codex app-server did not return an image for {item.id}")
                    reject_local_raster_image_result(result, item_id=item.id)
                    if provenance_policy == IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2 and not bool(getattr(result, "provenance_authoritative", False)):
                        raise RuntimeError(f"Codex app-server did not return authoritative request-bound provenance for {item.id}")
                    if provenance_policy == IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2:
                        _validate_request_bound_image_result(
                            result,
                            generation_job_id=generation_job_id,
                            item_id=str(item.id),
                            destination=provider_destination,
                            prompt_sha256=prompt_sha256,
                            reference_sha256s=reference_sha256s,
                        )
                    _assert_bound_run_root(run_dir)
                    try:
                        validate_image_bytes(Path(result.saved_path))
                        from PIL import Image
                        with Image.open(result.saved_path) as produced:
                            produced.verify()
                    except (ValueError, FileNotFoundError) as exc:
                        raise MediaOutputError(f"{item.id}: generated image is invalid: {exc}") from exc
                    except OSError as exc:
                        # Pillow decode errors have no errno; real disk/permission errors propagate.
                        if exc.errno is not None:
                            raise
                        raise MediaOutputError(f"{item.id}: generated image cannot be decoded: {exc}") from exc
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
                    client = create_codex_app_server_client(
                        cwd=provider_run_dir,
                        scrub_sensitive_env=True,
                        require_chatgpt_account=True,
                        require_chatgpt_pro=True,
                    )
                    await asyncio.wait_for(client.start(), timeout=CODEX_APP_SERVER_START_TIMEOUT_SECONDS)
        if result.saved_path is None:
            raise MediaOutputError(f"Codex app-server did not return an image for {item.id}")
        _assert_bound_run_root(run_dir)
        try:
            _destination_relative, destination = _validate_generation_destination_nofollow(
                run_dir,
                str(item.output),
                kind=kind,
            )
        except ValueError as exc:
            raise RuntimeError(
                f"unsafe {kind} request output before copy for {item.id}: {exc}"
            ) from exc
        try:
            copy_receipt = (
                _copy_saved_image_to_generation_destination_nofollow(
                    run_dir=run_dir,
                    saved_path=result.saved_path,
                    output=str(item.output),
                    kind=kind,
                )
            )
            destination = copy_receipt.destination
        except _UnsafeGenerationDestinationError as exc:
            raise RuntimeError(
                f"unsafe {kind} request output destination during copy "
                f"for {item.id}: {exc}"
            ) from exc
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
            inspect_destination=False,
            trusted_output_sha256=copy_receipt.output_sha256,
            trusted_destination_size_bytes=copy_receipt.size_bytes,
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
                "destinationExists": True,
                "outputSha256": copy_receipt.output_sha256,
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
            inspect_destination=False,
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
        try:
            await client.stop()
        finally:
            if provider_workspace_lease is not None:
                provider_workspace_lease.cleanup()
    return "provider_submitted"


async def _generate_request_outputs(*, run_dir: Path, kind: str) -> None:
    # Keep the immutable request snapshot stable from load through provider
    # submission. Prompt edits/materialization use this same revision lock.
    _assert_bound_run_root(run_dir)
    async with _serialized_run_write(run_dir, f"{kind}_request_revision"):
        await _generate_request_outputs_unlocked(run_dir=run_dir, kind=kind)
    _assert_bound_run_root(run_dir)


async def _generate_request_outputs_unlocked(*, run_dir: Path, kind: str) -> None:
    _assert_bound_run_root(run_dir)
    items = load_request_items(run_dir, kind)
    if not items:
        raise RuntimeError(f"{kind} request file has no {kind} items")
    if app_server_disabled():
        raise RuntimeError("Codex app-server is disabled")
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
    generation_outcomes: dict[str, str] = {}
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
                    outcome = await _generate_request_item_output(
                        run_dir=run_dir,
                        kind=kind,
                        item=item,
                    )
                    generation_outcomes[
                        str(getattr(item, "id", "") or "")
                    ] = outcome
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
    failed_items: list[str] = []
    snapshot_filename = {
        "asset": "asset_generation_request_snapshot.json",
        "scene": "image_generation_request_snapshot.json",
    }.get(kind)
    if snapshot_filename is None:
        raise ValueError("kind must be asset or scene")
    snapshot_path = run_dir / snapshot_filename
    if not snapshot_path.is_file():
        raise RuntimeError(
            f"{kind} image generation incomplete: missing {snapshot_filename}"
        )
    try:
        request_items = load_request_items(run_dir, kind)
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            f"{kind} image generation incomplete: invalid {snapshot_filename}: {exc}"
        ) from exc
    if not request_items:
        raise RuntimeError(f"{kind} image generation incomplete: no {kind} requests")
    for item in request_items:
        before_issues = len(issues)
        if not item.output:
            raise RuntimeError(f"{item.id}: request has no output path")
        try:
            output = resolve_run_relative(run_dir, item.output)
            require_image_file(output)
            if not output.is_file():
                issues.append(item.output)
                failed_items.append(str(item.id))
                continue
            validate_image_bytes(output)
            from PIL import Image
            with Image.open(output) as image:
                image.verify()
            if (
                kind == "asset"
                or str(
                    getattr(item, "prompt_policy_version", "") or ""
                )
                == "image_api_prompt_v2"
            ):
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
        if len(issues) > before_issues:
            failed_items.append(str(item.id))
    if issues:
        raise MediaOutputError(f"{kind} image generation incomplete: {', '.join(issues)}", kind=kind, item_ids=failed_items)


async def _validate_or_repair_image_outputs(run_dir: Path, validator) -> None:
    """Recheck the same terminal gate, regenerating only diagnosed current items."""
    while True:
        try:
            validator()
            return
        except MediaOutputError as exc:
            if exc.kind not in {'asset', 'scene'} or not exc.item_ids:
                raise
            items = {str(item.id): item for item in load_request_items(run_dir, exc.kind)}
            if not set(exc.item_ids) <= items.keys():
                raise RuntimeError('image repair target is not in current requests') from exc
            for item_id in dict.fromkeys(exc.item_ids):
                item = items[item_id]
                repair = RepairSession(run_dir, 'p560' if exc.kind == 'asset' else 'p660',
                    binding={'item': item_id, 'request': str(getattr(item, 'request_digest', '') or '')},
                    stage_limit=100000, run_limit=100000, unit_limit=2, budget_group='media')
                repair.feedback(item_id, {'output': item.output}, [str(exc)])
                repair.claim(item_id)
                await _generate_request_item_output(run_dir=run_dir, kind=exc.kind, item=item)
                repair.complete(item_id)


def _validate_p680_outputs(run_dir: Path, *, mode: str = "terminal") -> None:
    """Validate generated outputs without subjective scores or certificates."""
    _assert_bound_run_root(run_dir)
    _validate_generated_outputs(run_dir, "asset")
    _validate_generated_outputs(run_dir, "scene")


def _mark_asset_generation_handoff(run_dir: Path, *, asset_quality_passed: bool = True) -> None:
    """Record the completed output boundary; selection remains available in UI."""
    _validate_generated_outputs(run_dir, "asset")
    append_state_snapshot(run_dir / "state.txt", {
        "slot.p550.status": "done", "slot.p560.status": "done",
        "slot.p570.status": "done", "slot.p570.note": "asset outputs validated",
        "stage.asset.status": "done", "runtime.stage": "asset_images_generated",
    })


def _finalize_p500_supervisor_result(
    run_dir: Path,
    *,
    terminal_status: str,
) -> None:
    """Publish the truthful p500 handoff only after asset generation returns."""

    result_path = run_dir / "logs/orchestration/p500.supervisor_result.json"
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
            *[
                str(value).strip()
                for value in payload.get("completed_slots") or []
                if str(value).strip()
            ],
            "p510",
            "p520",
            "p530",
            "p540",
            "p550",
            "p560",
            "p570",
        ]
    )
    finished_at = now_iso()
    result_relpath = "logs/orchestration/p500.supervisor_result.json"
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "orchestration.p500.supervisor.call_status": "returned",
            "orchestration.p500.supervisor.status": "done",
            "orchestration.p500.supervisor.finished_at": finished_at,
            "orchestration.p500.supervisor.result": result_relpath,
        },
    )
    payload.update(
        {
            "bucket": "p500",
            "status": "done",
            "completed_slots": completed,
            "state_keys": {
                "orchestration.p500.supervisor.call_status": "returned",
                "orchestration.p500.supervisor.status": "done",
                "orchestration.p500.supervisor.result": result_relpath,
                "slot.p570.status": terminal_status,
            },
            "next_bucket": "p600",
            "finished_at": finished_at,
        }
    )
    _atomic_write_text(
        result_path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def _mark_image_generation_complete(run_id: str) -> None:
    """Publish generated scene outputs without an approval prerequisite."""
    run_dir = safe_run_dir(run_id, ROOT)
    _validate_generated_outputs(run_dir, "asset")
    _validate_generated_outputs(run_dir, "scene")
    generated_count = sum(1 for item in load_request_items(run_dir, "scene") if item.output)
    _finalize_p600_supervisor_result(
        run_dir, completed_slots=("p610", "p620", "p650", "p660", "p670", "p680"),
        terminal_slot="p680", terminal_status="done",
    )
    append_state_snapshot(run_dir / "state.txt", {
        "status": "P680", "runtime.stage": "scene_images_generated",
        "slot.p660.status": "done", "slot.p670.status": "done", "slot.p680.status": "done",
        "slot.p660.note": "scene images generated", "slot.p670.note": "output bytes and provenance validated",
        "slot.p680.note": "scene images available", "stage.scene_implementation.status": "done",
        "image_generation.status": "completed", "image_generation.started": "true",
        "image_generation.generated_count": str(generated_count),
        "image_generation.blocked_by": "", "image_generation.block_reason": "",
        "image_generation.finished_at": now_iso(),
    })


def _state_list_value(state: dict[str, str], key: str) -> list[str]:
    raw = str(state.get(key, "") or "").strip()
    if not raw:
        return []
    return [item.strip().strip("`\"'") for item in raw.split(",") if item.strip()]


_frontend_authoring_runner_module: Any | None = None
_frontend_authoring_runner_lock = threading.Lock()


def _load_frontend_authoring_runner() -> Any:
    """Load the frontend authoring helpers without executing their CLI entrypoint."""

    global _frontend_authoring_runner_module
    with _frontend_authoring_runner_lock:
        if _frontend_authoring_runner_module is not None:
            return _frontend_authoring_runner_module
        path = APP_ROOT / "scripts" / "toc-immersive-frontend-run.py"
        spec = importlib.util.spec_from_file_location(
            "toc_immersive_frontend_review_reconciliation",
            path,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load frontend review runner: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(spec.name, None)
            raise
        required_helpers = ("_require_fresh_p400_readiness",)
        missing = [
            name
            for name in required_helpers
            if not callable(getattr(module, name, None))
        ]
        if missing:
            raise RuntimeError(
                "frontend review runner is missing reconciliation helpers: "
                + ", ".join(missing)
            )
        _frontend_authoring_runner_module = module
        return module


def _validate_pre_asset_provider_gate(run_dir: Path) -> None:
    """Validate authored data and concrete asset requests before submission."""
    _assert_bound_run_root(run_dir)
    frontend = _load_frontend_authoring_runner()
    frontend._require_fresh_p400_readiness(run_dir)
    if not load_request_items(run_dir, "asset"):
        raise RuntimeError("asset generation requests are missing")


async def _generate_scene_outputs_after_p650_preflight(job_id: str, *, run_id: str, run_dir: Path, scene_revision_lock_held: bool=False) -> None:
    """Validate, submit, and hand off one immutable scene request revision."""
    _assert_bound_run_root(run_dir)
    async with AsyncExitStack() as lock_stack:
        if not scene_revision_lock_held:
            await lock_stack.enter_async_context(_serialized_run_write(run_dir, 'scene_request_revision'))
        try:
            _mark_image_prompt_request_freeze_done(run_dir)
            _validate_p650_run(run_id)
        except Exception as exc:
            append_state_snapshot(run_dir / 'state.txt', {'runtime.stage': 'p650_gate_failed_before_scene_generation', 'runtime.failure.stage': 'p650', 'runtime.failure.phase': 'scene_generation_preflight', 'runtime.failure.error_kind': 'p650_validation_failed', 'slot.p660.status': 'pending', 'slot.p660.note': 'blocked before scene image generation by p650 revision validation', 'slot.p680.status': 'pending', 'image_generation.status': 'not_started', 'image_generation.started': 'false', 'image_generation.generated_count': '0', 'image_generation.blocked_by': 'p650_revision_gate', 'image_generation.block_reason': str(exc)[:2000]})
            raise RuntimeError(f'scene image generation blocked by p650 gate: {exc}') from exc
        await _set_create_job(job_id, {'message': 'シーン画像を生成中'})
        append_state_snapshot(run_dir / 'state.txt', {'runtime.stage': 'scene_images_generating', 'slot.p660.status': 'in_progress', 'slot.p660.note': 'scene image generation started after request validation', 'slot.p680.status': 'pending', 'slot.p680.note': 'waiting for current revision output, provenance, and visual validation', 'image_generation.status': 'in_progress', 'image_generation.started': 'true', 'image_generation.generated_count': '0', 'image_generation.blocked_by': '', 'image_generation.block_reason': ''})
        failure_phase = 'media_generation'
        try:
            await _generate_request_outputs_unlocked(run_dir=run_dir, kind='scene')
            failure_phase = 'validation'
            _validate_p650_run(run_id)
            await _validate_or_repair_image_outputs(run_dir, lambda: _validate_generated_outputs(run_dir, 'asset'))
            await _validate_or_repair_image_outputs(run_dir, lambda: _validate_generated_outputs(run_dir, 'scene'))
            await _validate_or_repair_image_outputs(run_dir, lambda: _validate_p680_outputs(run_dir, mode='terminal'))
        except Exception as exc:
            generated_count = 0
            with suppress(Exception):
                generated_count = sum((1 for item in load_request_items(run_dir, 'scene') if item.output and resolve_run_relative(run_dir, item.output).is_file()))
            append_state_snapshot(run_dir / 'state.txt', {'runtime.stage': 'scene_image_generation_failed' if failure_phase == 'media_generation' else 'p680_pre_handoff_gate_failed', 'runtime.failure.stage': 'p660' if failure_phase == 'media_generation' else 'p680', 'runtime.failure.phase': failure_phase, 'runtime.failure.error_kind': 'media_generation_failed' if failure_phase == 'media_generation' else 'validation_failed', 'slot.p660.status': 'failed', 'slot.p660.note': 'scene generation or pre-handoff validation failed', 'slot.p670.status': 'pending', 'slot.p670.note': 'waiting for successful scene output validation', 'slot.p680.status': 'pending', 'slot.p680.note': 'generated image handoff is not ready because the pre-handoff gate failed', 'stage.scene_implementation.status': 'failed', 'image_generation.status': 'failed', 'image_generation.started': 'true', 'image_generation.generated_count': str(generated_count), 'image_generation.blocked_by': 'scene_image_generation' if failure_phase == 'media_generation' else 'p680_pre_handoff_gate', 'image_generation.block_reason': 'media_generation_failed' if failure_phase == 'media_generation' else 'pre_handoff_validation_failed', 'image_generation.error': str(exc)[:2000]})
            raise
        _mark_image_generation_complete(run_id)


async def _generate_create_images(job_id: str, *, run_id: str) -> bool:
    run_dir = safe_run_dir(run_id, ROOT)
    _assert_bound_run_root(run_dir)
    _validate_pre_asset_provider_gate(run_dir)
    await _set_create_job(job_id, {"message": "素材画像を生成中"})
    await _generate_request_outputs(run_dir=run_dir, kind="asset")
    await _validate_or_repair_image_outputs(run_dir, lambda: _validate_generated_outputs(run_dir, "asset"))
    _mark_asset_generation_handoff(run_dir, asset_quality_passed=True)
    await _generate_scene_outputs_after_p650_preflight(
        job_id, run_id=run_id, run_dir=run_dir,
    )
    return True


def _invalidate_p600_supervisor_result(run_dir: Path, *, invalidated_by: str) -> None:
    result_path = run_dir / "logs/orchestration/p600.supervisor_result.json"
    payload: dict[str, Any]
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {
            "bucket": "p600",
            "previous_status": "missing_or_malformed",
        }
    if not isinstance(payload, dict):
        payload = {
            "bucket": "p600",
            "previous_status": "malformed",
        }
    if payload.get("status") == "invalidated":
        return
    payload.setdefault(
        "previous_status",
        str(payload.get("status") or "unknown"),
    )
    payload["bucket"] = "p600"
    payload["status"] = "invalidated"
    payload["invalidated_at"] = now_iso()
    payload["invalidated_by"] = invalidated_by
    _atomic_write_text(result_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _invalidate_image_generation_handoff(run_dir: Path, *, invalidated_by: str, reason: str) -> None:
    """Demote a p680 review handoff that no longer verifies."""
    _invalidate_p600_supervisor_result(run_dir, invalidated_by=invalidated_by)
    append_state_snapshot(run_dir / 'state.txt', {'status': 'P650', 'runtime.stage': 'p680_terminal_verification_failed', 'runtime.failure.stage': 'p680', 'runtime.failure.phase': 'terminal_verification', 'runtime.failure.error_kind': 'validation_failed', 'slot.p680.status': 'pending', 'slot.p680.note': 'generated image handoff is unavailable because strict p680 terminal verification failed', 'stage.scene_implementation.status': 'failed', 'image_generation.status': 'failed', 'image_generation.blocked_by': 'p680_terminal_verification', 'image_generation.block_reason': str(reason)[:2000], 'orchestration.p600.supervisor.status': 'invalidated', 'orchestration.p600.supervisor.invalidated_by': invalidated_by})


def _invalidate_published_image_generation_handoff(
    run_dir: Path,
    *,
    invalidated_by: str,
    reason: str,
) -> bool:
    state = parse_state_file(run_dir / "state.txt")
    published = (
        state.get("slot.p680.status") in {"awaiting_approval", "done"}
        or state.get("orchestration.p600.supervisor.status") == "done"
    )
    if not published:
        return False
    _invalidate_image_generation_handoff(
        run_dir,
        invalidated_by=invalidated_by,
        reason=reason,
    )
    return True


CREATION_SLOT_BY_STAGE = {"research": "p120", "story": "p220", "scene_set": "p410", "scene_detail": "p410", "cut_blueprint": "p420", "asset_plan": "p530", "image_prompt": "p620", "narration": "p710"}


def _reject_duplicate_json_object_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate JSON key: {key}")
        payload[key] = value
    return payload


def _reject_non_finite_json_constant(value: str) -> Any:
    raise ValueError(f"non-finite JSON value: {value}")


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


def _create_run_error_message(exc: Exception, *, max_length: int = 1800) -> str:
    raw = str(exc).strip()
    if not raw:
        raw = type(exc).__name__
    normalized = " ".join(raw.split())
    normalized_lower = normalized.lower()
    if isinstance(exc, CanonicalP500ResumeRequiredError):
        prefix = "Canonical p500 resume is required"
    elif "401 unauthorized" in normalized_lower or "missing bearer or basic authentication" in normalized_lower:
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
    elif (
        "legacy p500 resume requires" in normalized_lower
        or "legacy world_walk p500 resume requires" in normalized_lower
    ):
        prefix = "p500再開に必要な入力契約が不足しています"
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
    review_mode: Literal["standard", "preapproved"] = "standard",
    expected_run_identity: tuple[int, int] | None = None,
    reservation: _FrontendCreateRunReservation | None = None,
) -> None:
    """Keep every server-side create step bound to the reserved run inode."""

    if reservation is not None:
        if reservation.run_id != run_id:
            raise FrontendCreateLockError(
                "frontend-create reservation run id changed"
            )
        expected_run_identity = reservation.identity
    if expected_run_identity is None:
        await _run_create_job_bound(
            job_id,
            title=title,
            source=source,
            run_id=run_id,
            generate_images=generate_images,
            create_mode=create_mode,
            stop_target=stop_target,
            target_duration_seconds=target_duration_seconds,
            expected_run_identity=None,
        )
        return
    if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
        raise ValueError("invalid run_id")
    run_dir = output_root(ROOT) / run_id
    try:
        with bind_run_root(
            run_dir,
            expected_identity=expected_run_identity,
            descriptor=(
                reservation.descriptor
                if reservation is not None
                else None
            ),
        ):
            await _run_create_job_bound(
                job_id,
                title=title,
                source=source,
                run_id=run_id,
                generate_images=generate_images,
                create_mode=create_mode,
                stop_target=stop_target,
                target_duration_seconds=target_duration_seconds,
                expected_run_identity=expected_run_identity,
                retained_reservation=reservation,
            )
    except asyncio.CancelledError:
        await _set_create_job(
            job_id,
            {
                "status": "failed",
                "error": "ToC作成がキャンセルされました",
                "errorCode": "CancelledError",
                "message": "作成中断",
            },
            write_run_log=False,
        )
        raise
    except Exception as exc:
        await _set_create_job(
            job_id,
            {
                "status": "failed",
                "error": _create_run_error_message(exc),
                "errorCode": type(exc).__name__,
                "message": "作成失敗",
            },
            write_run_log=False,
        )
    finally:
        await _release_run_execution_lease(job_id)
        if reservation is not None:
            _cleanup_unscaffolded_run(
                run_id,
                expected_run_identity=reservation.identity,
                reservation=reservation,
            )
            reservation.close()


async def _run_create_job_bound(
    job_id: str,
    *,
    title: str,
    source: str,
    run_id: str,
    generate_images: bool = True,
    create_mode: str = CREATE_MODE_NORMAL,
    stop_target: str = "p680",
    target_duration_seconds: int = 300,
    review_mode: Literal["standard", "preapproved"] = "standard",
    expected_run_identity: tuple[int, int] | None = None,
    retained_reservation: _FrontendCreateRunReservation | None = None,
) -> None:
    if review_mode not in {"standard", "preapproved"}:
        raise ValueError("review_mode must be standard or preapproved")
    if stop_target not in CREATE_STOP_TARGETS:
        raise ValueError("stop_target must be p650 or p680")
    if (
        create_mode == CREATE_MODE_SCENE_STORYBOARD
        and stop_target != "p680"
    ):
        raise ValueError(
            "scene_storyboard create requires stop_target p680"
        )
    if not 300 <= target_duration_seconds <= 1200:
        raise ValueError("target_duration_seconds must be between 300 and 1200")
    run_dir_for_log = safe_run_dir(run_id, ROOT)
    job_started = time.monotonic()
    try:
        async with _run_execution_leases_guard:
            execution_lease = _run_execution_leases.get(job_id)
        if execution_lease is None:
            execution_lease = await _acquire_run_execution_lease(
                job_id,
                run_dir_for_log,
                **(
                    {
                        "run_descriptor": retained_reservation.descriptor,
                        "expected_run_identity": retained_reservation.identity,
                    }
                    if retained_reservation is not None
                    else {
                        "expected_run_identity": expected_run_identity,
                    }
                ),
            )
        helper_identity = (
            execution_lease.identity
            if isinstance(execution_lease, _RunExecutionLease)
            else expected_run_identity
        )
        helper_binding = {
            "expected_run_identity": helper_identity,
            **(
                {"run_descriptor": execution_lease.run_descriptor}
                if isinstance(execution_lease, _RunExecutionLease)
                else {}
            ),
        } if helper_identity is not None else {}
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
                "reviewMode": review_mode,
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
                **helper_binding,
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
                **helper_binding,
            )
        await _sync_process_current_process(job_id, run_id)
        if generate_images and create_mode == CREATE_MODE_SCENE_STORYBOARD:
            storyboard_started = time.monotonic()
            await _set_create_job(job_id, {"message": "cutストーリーボードを作成中"})
            storyboard_result = _finalize_scene_storyboard_p680(run_id)
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
            await _validate_or_repair_image_outputs(run_dir_for_log, lambda: _validate_frontend_create_run(run_id, strict_visual_quality=True))
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
    except FrontendCreateLockError as exc:
        detail = _create_run_error_message(exc)
        await _set_create_job(
            job_id,
            {
                "status": "failed",
                "error": detail,
                "errorCode": type(exc).__name__,
                "message": "作成失敗",
            },
            write_run_log=False,
        )
    except Exception as exc:
        with suppress(Exception):
            _invalidate_published_image_generation_handoff(
                run_dir_for_log,
                invalidated_by="create_job.post_handoff_failure",
                reason=str(exc),
            )
        with suppress(Exception):
            await _sync_process_current_process(job_id, run_id)
        if retained_reservation is None:
            _cleanup_unscaffolded_run(
                run_id,
                expected_run_identity=expected_run_identity,
            )
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
                    "p570_non_visual_gate_failed",
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


async def _run_world_walk_create_job(
    job_id: str,
    *,
    title: str,
    source_run_id: str,
    run_id: str,
    target_duration_seconds: int = 300,
    review_mode: Literal["standard", "preapproved"] = "standard",
    expected_run_identity: tuple[int, int] | None = None,
    reservation: _FrontendCreateRunReservation | None = None,
) -> None:
    """Keep world-walk orchestration on its atomically reserved run inode."""

    if reservation is not None:
        if reservation.run_id != run_id:
            raise FrontendCreateLockError(
                "frontend-create reservation run id changed"
            )
        expected_run_identity = reservation.identity
    if expected_run_identity is None:
        await _run_world_walk_create_job_bound(
            job_id,
            title=title,
            source_run_id=source_run_id,
            run_id=run_id,
            target_duration_seconds=target_duration_seconds,
            expected_run_identity=None,
        )
        return
    if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
        raise ValueError("invalid run_id")
    run_dir = output_root(ROOT) / run_id
    try:
        with bind_run_root(
            run_dir,
            expected_identity=expected_run_identity,
            descriptor=(
                reservation.descriptor
                if reservation is not None
                else None
            ),
        ):
            await _run_world_walk_create_job_bound(
                job_id,
                title=title,
                source_run_id=source_run_id,
                run_id=run_id,
                target_duration_seconds=target_duration_seconds,
                expected_run_identity=expected_run_identity,
                retained_reservation=reservation,
            )
    except asyncio.CancelledError:
        await _set_create_job(
            job_id,
            {
                "status": "failed",
                "error": "ToC作成がキャンセルされました",
                "errorCode": "CancelledError",
                "message": "作成中断",
            },
            write_run_log=False,
        )
        raise
    except Exception as exc:
        await _set_create_job(
            job_id,
            {
                "status": "failed",
                "error": _create_run_error_message(exc),
                "errorCode": type(exc).__name__,
                "message": "作成失敗",
            },
            write_run_log=False,
        )
    finally:
        await _release_run_execution_lease(job_id)
        if reservation is not None:
            _cleanup_unscaffolded_run(
                run_id,
                expected_run_identity=reservation.identity,
                reservation=reservation,
            )
            reservation.close()


async def _run_world_walk_create_job_bound(
    job_id: str,
    *,
    title: str,
    source_run_id: str,
    run_id: str,
    target_duration_seconds: int = 300,
    review_mode: Literal["standard", "preapproved"] = "standard",
    expected_run_identity: tuple[int, int] | None = None,
    retained_reservation: _FrontendCreateRunReservation | None = None,
) -> None:
    if review_mode not in {"standard", "preapproved"}:
        raise ValueError("review_mode must be standard or preapproved")
    run_dir = safe_run_dir(run_id, ROOT)
    started = time.monotonic()
    try:
        _require_world_walk_source_run(source_run_id)
        async with _run_execution_leases_guard:
            execution_lease = _run_execution_leases.get(job_id)
        if execution_lease is None:
            execution_lease = await _acquire_run_execution_lease(
                job_id,
                run_dir,
                **(
                    {
                        "run_descriptor": retained_reservation.descriptor,
                        "expected_run_identity": retained_reservation.identity,
                    }
                    if retained_reservation is not None
                    else {
                        "expected_run_identity": expected_run_identity,
                    }
                ),
            )
        helper_identity = (
            execution_lease.identity
            if isinstance(execution_lease, _RunExecutionLease)
            else expected_run_identity
        )
        await _set_create_job(
            job_id,
            {
                "message": "世界観散歩モードをp680まで実行中",
                "currentProcess": "p000",
            },
        )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="world_walk_create_job",
            status="started",
            item_id=job_id,
            request={
                "title": title,
                "runId": run_id,
                "sourceRunId": source_run_id,
                "targetDurationSeconds": target_duration_seconds,
                "reviewMode": review_mode,
            },
        )
        await _run_toc_immersive_frontend_cli_helper(
            topic=title,
            run_id=run_id,
            experience=CREATE_MODE_WORLD_WALK,
            source_run_id=source_run_id,
            target_duration_seconds=target_duration_seconds,
            **(
                {
                    "expected_run_identity": helper_identity,
                    **(
                        {"run_descriptor": execution_lease.run_descriptor}
                        if isinstance(execution_lease, _RunExecutionLease)
                        else {}
                    ),
                }
                if helper_identity is not None
                else {}
            ),
        )
        await _sync_process_current_process(job_id, run_id)
        _validate_created_run(run_id)
        _validate_frontend_create_run(run_id, strict_visual_quality=True)
        await _set_create_job(
            job_id,
            {
                "status": "completed",
                "message": "作成完了",
                "currentProcess": "p680",
            },
        )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="world_walk_create_job",
            status="completed",
            item_id=job_id,
            request={
                "runId": run_id,
                "sourceRunId": source_run_id,
            },
            response={
                "elapsedMs": int((time.monotonic() - started) * 1000),
            },
        )
    except FrontendCreateLockError as exc:
        detail = _create_run_error_message(exc)
        await _set_create_job(
            job_id,
            {
                "status": "failed",
                "error": detail,
                "errorCode": type(exc).__name__,
                "message": "作成失敗",
            },
            write_run_log=False,
        )
    except Exception as exc:
        with suppress(Exception):
            await _sync_process_current_process(job_id, run_id)
        if retained_reservation is None:
            _cleanup_unscaffolded_run(
                run_id,
                expected_run_identity=expected_run_identity,
            )
        detail = _create_run_error_message(exc)
        await _set_create_job(
            job_id,
            {
                "status": "failed",
                "error": detail,
                "errorCode": type(exc).__name__,
                "message": "作成失敗",
            },
            write_run_log=False,
        )
    finally:
        await _release_run_execution_lease(job_id)


def _track_create_task(job_id: str, coroutine: Any) -> asyncio.Task[None]:
    try:
        task = asyncio.create_task(coroutine)
    except BaseException:
        close = getattr(coroutine, "close", None)
        if callable(close):
            close()
        raise
    _create_tasks[job_id] = task
    task.add_done_callback(
        lambda completed, current_job_id=job_id: (
            _create_tasks.pop(current_job_id, None)
            if _create_tasks.get(current_job_id) is completed
            else None
        )
    )
    return task


def _cleanup_resume_task(completed: asyncio.Task[Any], current_job_id: str) -> None:
    if _resume_tasks.get(current_job_id) is completed:
        _resume_tasks.pop(current_job_id, None)
        _create_job_failure_baselines.pop(current_job_id, None)


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


@router.get("/api/image-gen/runs/world-walk-sources")
async def api_world_walk_sources() -> dict[str, Any]:
    return {"sources": await asyncio.to_thread(_list_world_walk_source_runs)}


@router.post("/api/image-gen/runs/create")
async def api_create_run(req: CreateRunRequest) -> dict[str, Any]:
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must not be blank")
    source = (req.source or "").strip() or title
    stop_target = req.stop_target
    target_duration_seconds = req.target_duration_seconds
    review_mode = req.review_mode
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
        reservation = _reserve_frontend_create_run_dir(title)
        run_id = reservation.run_id
        _run_dir = reservation.run_dir
        job = {
            "jobId": job_id,
            "runId": run_id,
            "path": f"output/{run_id}",
            "status": "running",
            "title": title,
            "createMode": CREATE_MODE_NORMAL,
            "targetDurationSeconds": target_duration_seconds,
            "reviewMode": review_mode,
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
    lease_reserved = False
    task_scheduled = False
    try:
        try:
            with bind_run_root(
                _run_dir,
                expected_identity=reservation.identity,
                descriptor=reservation.descriptor,
            ):
                await _acquire_run_execution_lease(
                    job_id,
                    _run_dir,
                    run_descriptor=reservation.descriptor,
                    expected_run_identity=reservation.identity,
                )
                lease_reserved = True
                cinematic_preferences = (getattr(req, 'cinematic_preferences', None) or '').strip()
                if cinematic_preferences:
                    write_regular_file_nofollow(destination_root=_run_dir,
                        destination_relative='cinematic_preferences.md', data=(cinematic_preferences + '\n').encode('utf-8'),
                        expected_destination_root_identity=reservation.identity)
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
                        "reviewMode": review_mode,
                        "processStore": process_store_result,
                    },
                    response={"path": f"output/{run_id}"},
                )
        except FileLockUnavailable as exc:
            raise HTTPException(
                status_code=409,
                detail="run create/resume is already active",
            ) from exc
        _track_create_task(
            job_id,
            _run_create_job(
            job_id,
            title=title,
            source=source,
            run_id=run_id,
            generate_images=bool(req.generate_images),
            create_mode=CREATE_MODE_NORMAL,
            stop_target=stop_target,
            target_duration_seconds=target_duration_seconds,
            reservation=reservation,
            ),
        )
        task_scheduled = True
        return job
    except BaseException:
        if not task_scheduled:
            await _release_run_execution_lease(job_id)
            async with _create_jobs_lock:
                _create_jobs.pop(job_id, None)
            _cleanup_unscaffolded_run(
                run_id,
                expected_run_identity=reservation.identity,
                reservation=reservation,
            )
            reservation.close()
        raise


@router.post("/api/image-gen/runs/create/storyboard")
async def api_create_storyboard_run(req: CreateStoryboardRunRequest) -> dict[str, Any]:
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must not be blank")
    source = (req.source or "").strip() or title
    stop_target = req.stop_target
    target_duration_seconds = req.target_duration_seconds
    review_mode = req.review_mode
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
        reservation = _reserve_frontend_create_run_dir(
            f"{title}_{CREATE_MODE_SCENE_STORYBOARD_RUN_SUFFIX}"
        )
        run_id = reservation.run_id
        _run_dir = reservation.run_dir
        job = {
            "jobId": job_id,
            "runId": run_id,
            "path": f"output/{run_id}",
            "status": "running",
            "title": title,
            "createMode": CREATE_MODE_SCENE_STORYBOARD,
            "targetDurationSeconds": target_duration_seconds,
            "reviewMode": review_mode,
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
    lease_reserved = False
    task_scheduled = False
    try:
        try:
            with bind_run_root(
                _run_dir,
                expected_identity=reservation.identity,
                descriptor=reservation.descriptor,
            ):
                await _acquire_run_execution_lease(
                    job_id,
                    _run_dir,
                    run_descriptor=reservation.descriptor,
                    expected_run_identity=reservation.identity,
                )
                lease_reserved = True
                cinematic_preferences = (getattr(req, 'cinematic_preferences', None) or '').strip()
                if cinematic_preferences:
                    write_regular_file_nofollow(destination_root=_run_dir,
                        destination_relative='cinematic_preferences.md', data=(cinematic_preferences + '\n').encode('utf-8'),
                        expected_destination_root_identity=reservation.identity)
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
                        "reviewMode": review_mode,
                        "processStore": process_store_result,
                    },
                    response={"path": f"output/{run_id}"},
                )
        except FileLockUnavailable as exc:
            raise HTTPException(
                status_code=409,
                detail="run create/resume is already active",
            ) from exc
        _track_create_task(
            job_id,
            _run_create_job(
            job_id,
            title=title,
            source=source,
            run_id=run_id,
            generate_images=True,
            create_mode=CREATE_MODE_SCENE_STORYBOARD,
            stop_target=stop_target,
            target_duration_seconds=target_duration_seconds,
            reservation=reservation,
            ),
        )
        task_scheduled = True
        return job
    except BaseException:
        if not task_scheduled:
            await _release_run_execution_lease(job_id)
            async with _create_jobs_lock:
                _create_jobs.pop(job_id, None)
            _cleanup_unscaffolded_run(
                run_id,
                expected_run_identity=reservation.identity,
                reservation=reservation,
            )
            reservation.close()
        raise


@router.post("/api/image-gen/runs/create-world-walk")
async def api_create_world_walk_run(
    req: CreateWorldWalkRunRequest,
) -> dict[str, Any]:
    source_run_id = req.source_run_id.strip()
    _require_world_walk_source_run(source_run_id)
    title = (
        (req.title or "").strip()
        or _world_walk_title_from_source_run_id(source_run_id)
    )
    if not title:
        raise HTTPException(status_code=400, detail="title must not be blank")
    target_duration_seconds = req.target_duration_seconds
    review_mode = req.review_mode
    job_id = uuid.uuid4().hex
    async with _create_jobs_lock:
        running_count = sum(
            1
            for existing in _create_jobs.values()
            if existing.get("status") == "running"
        )
        if running_count >= MAX_RUNNING_CREATE_JOBS:
            raise HTTPException(
                status_code=429,
                detail="too many create jobs are running",
            )
        if len(_create_jobs) >= MAX_CREATE_JOBS:
            terminal_job_id = next(
                (
                    existing_id
                    for existing_id, existing in _create_jobs.items()
                    if existing.get("status") in {"completed", "failed"}
                ),
                None,
            )
            if terminal_job_id:
                _create_jobs.pop(terminal_job_id)
            else:
                raise HTTPException(
                    status_code=503,
                    detail="too many create jobs are running",
                )
        reservation = _reserve_frontend_create_run_dir(title)
        run_id = reservation.run_id
        run_dir = reservation.run_dir
        job = {
            "jobId": job_id,
            "runId": run_id,
            "path": f"output/{run_id}",
            "status": "running",
            "title": title,
            "createMode": CREATE_MODE_WORLD_WALK,
            "sourceRunId": source_run_id,
            "sourceRunPath": f"output/{source_run_id}",
            "targetDurationSeconds": target_duration_seconds,
            "reviewMode": review_mode,
            "stopTarget": "p680",
            "stopTargetNumber": _process_number("p680"),
            "currentProcess": "p000",
            "currentProcessNumber": 0,
            "pid": os.getpid(),
            "error": None,
            "errorCode": None,
            "message": "フォルダを作成中",
        }
        _create_jobs[job_id] = job
    lease_reserved = False
    task_scheduled = False
    try:
        try:
            with bind_run_root(
                run_dir,
                expected_identity=reservation.identity,
                descriptor=reservation.descriptor,
            ):
                await _acquire_run_execution_lease(
                    job_id,
                    run_dir,
                    run_descriptor=reservation.descriptor,
                    expected_run_identity=reservation.identity,
                )
                lease_reserved = True
                cinematic_preferences = (getattr(req, 'cinematic_preferences', None) or '').strip()
                if cinematic_preferences:
                    write_regular_file_nofollow(destination_root=_run_dir,
                        destination_relative='cinematic_preferences.md', data=(cinematic_preferences + '\n').encode('utf-8'),
                        expected_destination_root_identity=reservation.identity)
                process_store_result = await asyncio.to_thread(
                    _create_process_record_best_effort,
                    job=job,
                    title=title,
                    source=f"output/{source_run_id}",
                    stop_target="p680",
                    generate_images=True,
                )
                if process_store_result:
                    job["processStore"] = process_store_result
                write_app_server_debug_log(
                    run_dir=run_dir,
                    operation="create_job_start",
                    status="running",
                    item_id=job_id,
                    request={
                        "title": title,
                        "runId": run_id,
                        "sourceRunId": source_run_id,
                        "createMode": CREATE_MODE_WORLD_WALK,
                        "stopTarget": "p680",
                        "targetDurationSeconds": target_duration_seconds,
                        "reviewMode": review_mode,
                        "processStore": process_store_result,
                    },
                    response={"path": f"output/{run_id}"},
                )
        except FileLockUnavailable as exc:
            raise HTTPException(
                status_code=409,
                detail="run create/resume is already active",
            ) from exc
        _track_create_task(
            job_id,
            _run_world_walk_create_job(
            job_id,
            title=title,
            source_run_id=source_run_id,
            run_id=run_id,
            target_duration_seconds=target_duration_seconds,
            reservation=reservation,
            ),
        )
        task_scheduled = True
        return job
    except BaseException:
        if not task_scheduled:
            await _release_run_execution_lease(job_id)
            async with _create_jobs_lock:
                _create_jobs.pop(job_id, None)
            _cleanup_unscaffolded_run(
                run_id,
                expected_run_identity=reservation.identity,
                reservation=reservation,
            )
            reservation.close()
        raise


@router.get("/api/image-gen/runs/create/{job_id}")
async def api_create_run_status(job_id: str) -> dict[str, Any]:
    async with _create_jobs_lock:
        job = _create_jobs.get(job_id)
        if job:
            return _reconcile_create_job_with_run_state(dict(job))
    try:
        record = await asyncio.to_thread(process_store.get_process_run, job_id=job_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"create job not found; process DB unavailable: {exc}") from exc
    if not record:
        raise HTTPException(status_code=404, detail="create job not found")
    return _reconcile_create_job_with_run_state(record.to_api())


@router.get("/api/image-gen/runs/{run_id}/process")
async def api_run_process(run_id: str) -> dict[str, Any]:
    safe_run_dir(run_id, ROOT)
    current_process_number = _current_process_number_for_run(run_id)
    current_process = _process_label(current_process_number)
    try:
        record = await asyncio.to_thread(process_store.get_process_run, run_id=run_id)
    except Exception as exc:
        try:
            progress = read_run_progress(safe_run_dir(run_id, ROOT), validate_request_outputs=False)
        except (FileNotFoundError, OSError, ValueError):
            progress = {}
        failure = progress.get("failure") if isinstance(progress, dict) else None
        failure = failure if isinstance(failure, dict) else {}
        fallback_status = str(progress.get("status") or "") if isinstance(progress, dict) else ""
        fallback_stage = str(failure.get("stage") or "")
        return {
            "runId": run_id,
            "status": "failed" if failure.get("terminal") else fallback_status,
            "error": str(failure.get("message") or "") if failure.get("terminal") else None,
            "currentProcess": fallback_stage or current_process,
            "currentProcessNumber": _process_number(fallback_stage) if fallback_stage else current_process_number,
            "processStore": {"enabled": process_store.enabled(), "error": str(exc)},
        }
    if record:
        payload = _reconcile_create_job_with_run_state(record.to_api())
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
    from toc.authoring_resume import read_create_input
    saved_path = run_dir / "logs/orchestration/create_input.json"
    if saved_path.exists() or saved_path.is_symlink():
        return read_create_input(run_dir)["target_duration_seconds"]
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


def _resume_create_mode_for_run(run_dir: Path, record: Any | None) -> str:
    state = parse_state_file(run_dir / "state.txt")
    state_mode = str(state.get("runtime.create_mode") or "").strip()
    manifest_mode = ""
    if (run_dir / "video_manifest.md").is_file():
        try:
            _path, _original_text, manifest = _read_manifest_data(run_dir)
            metadata = _dict_value(manifest.get("video_metadata"))
            manifest_mode = str(
                metadata.get("create_mode")
                or metadata.get("experience")
                or ""
            ).strip()
        except (OSError, TypeError, ValueError):
            manifest_mode = ""
    if manifest_mode == "cinematic_story":
        manifest_mode = CREATE_MODE_NORMAL
    record_mode = str(getattr(record, "create_mode", "") or "").strip()
    for candidate in (state_mode, manifest_mode, record_mode):
        if candidate in {
            CREATE_MODE_NORMAL,
            CREATE_MODE_SCENE_STORYBOARD,
            CREATE_MODE_WORLD_WALK,
        }:
            return candidate
    return CREATE_MODE_NORMAL


def _validate_current_p680_run(run_id: str, *, create_mode: str) -> None:
    if create_mode == CREATE_MODE_SCENE_STORYBOARD:
        _validate_scene_storyboard_create_run(
            run_id,
            strict_visual_quality=True,
        )
        return
    _validate_frontend_create_run(run_id, strict_visual_quality=True)


def _signal_resume_process_group(
    proc: asyncio.subprocess.Process,
    signal_number: int,
) -> None:
    try:
        os.killpg(proc.pid, signal_number)
    except ProcessLookupError:
        return
    except OSError:
        if proc.returncode is not None:
            return
        try:
            if signal_number == signal.SIGTERM:
                proc.terminate()
            else:
                proc.kill()
        except ProcessLookupError:
            return


def _resume_process_group_exists(proc: asyncio.subprocess.Process) -> bool:
    try:
        os.killpg(proc.pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def _terminate_resume_process_group(
    proc: asyncio.subprocess.Process,
    communicate_task: asyncio.Task[tuple[bytes, bytes]],
) -> tuple[bytes, bytes]:
    _signal_resume_process_group(proc, signal.SIGTERM)
    result: tuple[bytes, bytes] | None = None
    try:
        result = await asyncio.wait_for(
            asyncio.shield(communicate_task),
            timeout=RESUME_SUBPROCESS_TERMINATION_GRACE_SECONDS,
        )
    except asyncio.TimeoutError:
        pass
    if _resume_process_group_exists(proc):
        _signal_resume_process_group(proc, signal.SIGKILL)
    if result is not None:
        return result
    # communicate() reaps the direct child after the helper session and all
    # descendants have been terminated.
    return await asyncio.shield(communicate_task)


async def _await_resume_process_cleanup(
    proc: asyncio.subprocess.Process,
    communicate_task: asyncio.Task[tuple[bytes, bytes]],
) -> tuple[bytes, bytes]:
    cleanup_task = asyncio.create_task(
        _terminate_resume_process_group(proc, communicate_task)
    )
    pending_cancellation: asyncio.CancelledError | None = None
    while not cleanup_task.done():
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError as cancellation:
            pending_cancellation = cancellation
    result = cleanup_task.result()
    if pending_cancellation is not None:
        raise pending_cancellation
    return result


async def _run_resume_subprocess_command(
    command: list[str],
    *,
    pass_fds: tuple[int, ...] = (),
    timeout_seconds: float | None = None,
) -> tuple[bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
        **({"pass_fds": pass_fds} if pass_fds else {}),
    )
    communicate_task = asyncio.create_task(proc.communicate())
    try:
        stdout, stderr = await asyncio.wait_for(
            asyncio.shield(communicate_task),
            timeout=FRONTEND_CREATE_HELPER_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds,
        )
    except asyncio.CancelledError as cancellation:
        with suppress(asyncio.CancelledError):
            await _await_resume_process_cleanup(proc, communicate_task)
        raise cancellation
    except asyncio.TimeoutError as exc:
        stdout, stderr = await _await_resume_process_cleanup(
            proc,
            communicate_task,
        )
        detail = (
            stderr.decode("utf-8", errors="replace").strip()
            or stdout.decode("utf-8", errors="replace").strip()
        )
        raise TimeoutError(
            "resume subprocess timed out"
            + (f": {detail}" if detail else "")
        ) from exc
    if proc.returncode != 0:
        detail = (
            stderr.decode("utf-8", errors="replace").strip()
            or stdout.decode("utf-8", errors="replace").strip()
        )
        raise RuntimeError(
            detail
            or f"resume subprocess exited with status {proc.returncode}"
        )
    return stdout, stderr


def _p500_resume_plan_token(stdout: bytes, *, checkpoint_id: str) -> str:
    try:
        payload = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "resume-from-p500 dry-run did not return exact JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("resume-from-p500 dry-run JSON must be an object")
    returned_checkpoint_id = payload.get("checkpoint_id")
    if (
        not isinstance(returned_checkpoint_id, str)
        or returned_checkpoint_id != checkpoint_id
    ):
        raise RuntimeError(
            "resume-from-p500 dry-run checkpoint_id is missing or mismatched"
        )
    plan_token = payload.get("plan_token")
    if (
        not isinstance(plan_token, str)
        or re.fullmatch(r"[0-9a-f]{64}", plan_token) is None
    ):
        raise RuntimeError(
            "resume-from-p500 dry-run plan_token is missing or malformed"
        )
    return plan_token


async def _run_authoring_resume_subprocess(*, job_id: str, run_dir: Path) -> None:
    from toc.authoring_resume import read_create_input
    saved = read_create_input(run_dir)
    command = [sys.executable, str(ROOT / "scripts" / "toc-immersive-frontend-run.py"),
        "--run-dir", str(run_dir), "--topic", saved["topic"],
        "--resume-authoring", "--stop-target", "p450"]
    binding = _assert_bound_run_root(run_dir)
    pass_fds: tuple[int, ...] = ()
    if binding is not None:
        async with _run_execution_leases_guard:
            lease = _run_execution_leases.get(job_id)
        if not isinstance(lease, _RunExecutionLease):
            raise RuntimeError("authoring resume is missing its execution lease")
        command.extend(["--expected-run-device", str(binding.identity[0]),
            "--expected-run-inode", str(binding.identity[1]),
            "--inherited-run-fd", str(lease.run_descriptor)])
        pass_fds = (lease.run_descriptor,)
    await _run_resume_subprocess_command(command, pass_fds=pass_fds)


def _requires_authoring_resume(run_dir: Path) -> bool:
    from toc.authoring_resume import needs_authoring_resume, read_create_input
    contract = run_dir / "logs/orchestration/create_input.json"
    if not contract.exists() and not contract.is_symlink():
        return False  # Legacy p500 can recover its exact input from the process record.
    read_create_input(run_dir)
    return needs_authoring_resume(run_dir)


async def _run_p500_resume_subprocess(
    *,
    job_id: str,
    run_dir: Path,
    source: str | None = None,
) -> dict[str, str]:
    checkpoint_id = f"api-{job_id}"
    base_command = [
        sys.executable,
        str(ROOT / "scripts" / "resume-from-p500.py"),
        "--run-dir",
        str(run_dir),
        "--checkpoint-id",
        checkpoint_id,
    ]
    binding = _assert_bound_run_root(run_dir)
    inherited_descriptors: tuple[int, ...] = ()
    if binding is not None:
        base_command.extend(
            [
                "--expected-run-device",
                str(binding.identity[0]),
                "--expected-run-inode",
                str(binding.identity[1]),
            ]
        )
        async with _run_execution_leases_guard:
            execution_lease = _run_execution_leases.get(job_id)
        if not isinstance(execution_lease, _RunExecutionLease):
            raise RuntimeError(
                "p500 resume is missing its retained execution lease"
            )
        base_command.extend(
            [
                "--inherited-run-fd",
                str(execution_lease.run_descriptor),
                "--inherited-runtime-lock-fd",
                str(execution_lease.runtime_lease.file.fileno()),
                "--lock-already-held",
            ]
        )
        inherited_descriptors = (
            execution_lease.run_descriptor,
            execution_lease.runtime_lease.file.fileno(),
        )
    if source is not None:
        base_command.extend(["--source", source])
    dry_stdout, _dry_stderr = await _run_resume_subprocess_command(
        base_command,
        pass_fds=inherited_descriptors,
    )
    plan_token = _p500_resume_plan_token(
        dry_stdout,
        checkpoint_id=checkpoint_id,
    )

    # This boundary intentionally contains no run/state/debug write. Apply must
    # consume the exact plan that the dry-run inspected.
    apply_command = [
        *base_command,
        "--plan-token",
        plan_token,
        "--apply",
        "--continue-to",
        "p680",
    ]
    apply_stdout, _apply_stderr = await _run_resume_subprocess_command(
        apply_command,
        pass_fds=inherited_descriptors,
    )
    return {
        "checkpointId": checkpoint_id,
        "planToken": plan_token,
        "stdout": apply_stdout.decode("utf-8", errors="replace").strip(),
    }


async def _run_blocking_with_cancel_barrier(
    function: Callable[..., Any],
    *args: Any,
) -> Any:
    """Keep a blocking mutation inside its caller's lease even if cancelled."""

    worker = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError as cancellation:
        while not worker.done():
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                continue
        try:
            worker.result()
        except BaseException:
            # Cancellation remains the externally visible outcome, but the
            # mutation has reached a terminal state before its lease is freed.
            pass
        raise cancellation


async def _run_image_only_resume_job(
    job_id: str,
    *,
    run_id: str,
    create_mode: str,
    expected_run_identity: tuple[int, int] | None = None,
    retained_run: _FrontendCreateRunReservation | None = None,
) -> None:
    if retained_run is not None:
        if retained_run.run_id != run_id:
            raise FrontendCreateLockError(
                "resume retained run id changed"
            )
        expected_run_identity = retained_run.identity
    if expected_run_identity is None:
        await _run_image_only_resume_job_bound(
            job_id,
            run_id=run_id,
            create_mode=create_mode,
        )
        return
    if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
        raise ValueError("invalid run_id")
    run_dir = output_root(ROOT) / run_id
    try:
        with bind_run_root(
            run_dir,
            expected_identity=expected_run_identity,
            descriptor=(
                retained_run.descriptor
                if retained_run is not None
                else None
            ),
        ):
            await _run_image_only_resume_job_bound(
                job_id,
                run_id=run_id,
                create_mode=create_mode,
            )
    except asyncio.CancelledError:
        await _set_create_job(
            job_id,
            {
                "status": "failed",
                "error": "ToC再開がキャンセルされました",
                "errorCode": "CancelledError",
                "message": "再開中断",
            },
            write_run_log=False,
        )
        raise
    except Exception as exc:
        await _set_create_job(
            job_id,
            {
                "status": "failed",
                "error": _create_run_error_message(exc),
                "errorCode": type(exc).__name__,
                "message": "再開失敗",
            },
            write_run_log=False,
        )
    finally:
        await _release_run_execution_lease(job_id)
        if retained_run is not None:
            retained_run.close()


async def _run_image_only_resume_job_bound(
    job_id: str,
    *,
    run_id: str,
    create_mode: str,
) -> None:
    run_dir = safe_run_dir(run_id, ROOT)
    started = time.monotonic()
    try:
        async with _run_execution_leases_guard:
            lease_already_reserved = job_id in _run_execution_leases
        if not lease_already_reserved:
            await _acquire_run_execution_lease(job_id, run_dir)
        try:
            current_record = await asyncio.to_thread(
                process_store.get_process_run,
                run_id=run_id,
            )
        except Exception:
            current_record = None
        create_mode = _resume_create_mode_for_run(run_dir, current_record)
        await _set_create_job(
            job_id,
            {
                "message": "p650成果物を維持してシーン画像だけ再開中",
                "currentProcess": "p650",
                "currentProcessNumber": 650,
            },
        )
        async with AsyncExitStack() as revision_locks:
            for resource in (
                "run_artifacts",
                "asset_request_revision",
                "scene_request_revision",
            ):
                await revision_locks.enter_async_context(
                    _serialized_run_write(run_dir, resource)
                )

            _validate_p650_run(run_id)
            regeneration_plan = _classify_p680_regeneration_plan(run_dir)
            if regeneration_plan.errors:
                raise RuntimeError(
                    "image-only resume preflight rejected unsafe regeneration targets: "
                    + "; ".join(regeneration_plan.errors[:20])
                )
            if regeneration_plan.requires_canonical_p500:
                raise CanonicalP500ResumeRequiredError(
                    "canonical p500 resume is required because the current p680 "
                    "regeneration plan contains asset/reference repair targets"
                )
            resume_images = await _run_blocking_with_cancel_barrier(
                _delete_existing_images_for_image_resume,
                run_dir,
            )
            resume_errors = resume_images.get("errors")
            if resume_errors is None:
                resume_errors = []
            if not isinstance(resume_errors, list):
                raise RuntimeError(
                    "image-only resume preflight returned an invalid errors contract"
                )
            normalized_resume_errors = [
                str(error).strip()
                for error in resume_errors
                if str(error).strip()
            ]
            if normalized_resume_errors:
                raise RuntimeError(
                    "image-only resume preflight rejected unsafe regeneration targets: "
                    + "; ".join(normalized_resume_errors[:20])
                )
            await _set_create_job(
                job_id,
                {
                    "message": "既存画像を照合して差分だけ再生成中",
                    "metadata": {
                        "resumeMode": "image_only",
                        "resumePolicy": "hash_aware_partial",
                        "deletedImagesCount": resume_images.get("deletedCount", 0),
                        "preservedImagesCount": resume_images.get("preservedCount", 0),
                    },
                },
            )
            await _generate_scene_outputs_after_p650_preflight(
                job_id,
                run_id=run_id,
                run_dir=run_dir,
                scene_revision_lock_held=True,
            )
            if create_mode == CREATE_MODE_SCENE_STORYBOARD:
                await _run_blocking_with_cancel_barrier(
                    _finalize_scene_storyboard_p680,
                    run_id,
                )
            _validate_current_p680_run(
                run_id,
                create_mode=create_mode,
            )
        await _sync_process_current_process(job_id, run_id)
        await _set_create_job(
            job_id,
            {
                "status": "completed",
                "message": "再開完了",
                "currentProcess": "p680",
                "currentProcessNumber": 680,
            },
        )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="create_job_resume_image_only",
            status="completed",
            item_id=job_id,
            request={
                "runId": run_id,
                "createMode": create_mode,
                "resumePolicy": "hash_aware_partial",
            },
            response={
                "elapsedMs": int((time.monotonic() - started) * 1000),
                "resumeImages": resume_images,
            },
        )
    except Exception as exc:
        with suppress(Exception):
            _invalidate_published_image_generation_handoff(
                run_dir,
                invalidated_by="image_only_resume.post_handoff_failure",
                reason=str(exc),
            )
        with suppress(Exception):
            await _sync_process_current_process(job_id, run_id)
        detail = _create_run_error_message(exc)
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="create_job_resume_image_only",
            status="failed",
            item_id=job_id,
            request={"runId": run_id, "createMode": create_mode},
            response={
                "elapsedMs": int((time.monotonic() - started) * 1000),
                **_create_job_failure_diagnostics(run_dir),
            },
            error=f"{type(exc).__name__}: {exc}",
        )
        await _set_create_job(
            job_id,
            {
                "status": "failed",
                "error": detail,
                "errorCode": (
                    "canonical_p500_required"
                    if isinstance(exc, CanonicalP500ResumeRequiredError)
                    else type(exc).__name__
                ),
                "message": "再開失敗",
            },
        )
    finally:
        await _release_run_execution_lease(job_id)


async def _run_p500_resume_job(
    job_id: str,
    *,
    run_id: str,
    create_mode: str,
    expected_run_identity: tuple[int, int] | None = None,
    retained_run: _FrontendCreateRunReservation | None = None,
) -> None:
    if retained_run is not None:
        if retained_run.run_id != run_id:
            raise FrontendCreateLockError(
                "resume retained run id changed"
            )
        expected_run_identity = retained_run.identity
    if expected_run_identity is None:
        try:
            await _run_p500_resume_job_bound(
                job_id,
                run_id=run_id,
                create_mode=create_mode,
            )
        except asyncio.CancelledError:
            with suppress(Exception):
                await _record_p500_resume_failure_state(
                    safe_run_dir(run_id, ROOT),
                    asyncio.CancelledError("ToC再開がキャンセルされました"),
                )
            await _set_create_job(
                job_id,
                {
                    "status": "failed",
                    "error": "ToC再開がキャンセルされました",
                    "errorCode": "CancelledError",
                    "message": "再開中断",
                },
                write_run_log=False,
            )
            raise
        except Exception as exc:
            with suppress(Exception):
                await _record_p500_resume_failure_state(
                    safe_run_dir(run_id, ROOT),
                    exc,
                )
            await _set_create_job(
                job_id,
                {
                    "status": "failed",
                    "error": _create_run_error_message(exc),
                    "errorCode": type(exc).__name__,
                    "message": "再開失敗",
                },
                write_run_log=False,
            )
        return
    if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
        raise ValueError("invalid run_id")
    run_dir = output_root(ROOT) / run_id
    try:
        with bind_run_root(
            run_dir,
            expected_identity=expected_run_identity,
            descriptor=(
                retained_run.descriptor
                if retained_run is not None
                else None
            ),
        ):
            try:
                await _run_p500_resume_job_bound(
                    job_id,
                    run_id=run_id,
                    create_mode=create_mode,
                )
            except asyncio.CancelledError as exc:
                with suppress(Exception):
                    await _record_p500_resume_failure_state(run_dir, exc)
                raise
            except Exception as exc:
                with suppress(Exception):
                    await _record_p500_resume_failure_state(run_dir, exc)
                raise
    except asyncio.CancelledError:
        await _set_create_job(
            job_id,
            {
                "status": "failed",
                "error": "ToC再開がキャンセルされました",
                "errorCode": "CancelledError",
                "message": "再開中断",
            },
            write_run_log=False,
        )
        raise
    except Exception as exc:
        await _set_create_job(
            job_id,
            {
                "status": "failed",
                "error": _create_run_error_message(exc),
                "errorCode": type(exc).__name__,
                "message": "再開失敗",
            },
            write_run_log=False,
        )
    finally:
        await _release_run_execution_lease(job_id)
        if retained_run is not None:
            retained_run.close()


async def _record_p500_resume_failure_state(
    run_dir: Path,
    exc: BaseException,
) -> None:
    """Publish a resumable run's terminal failure on the canonical state log."""

    detail = _create_run_error_message(exc if isinstance(exc, Exception) else RuntimeError(str(exc)))
    async with _serialized_run_write(run_dir, "p500_resume_failure"):
        current = parse_state_file(run_dir / "state.txt")
        runtime_stage = str(current.get("runtime.stage") or "").strip()
        concrete_failure = (
            "failed" in runtime_stage.lower()
            or runtime_stage == "semantic_review_blocked_transport"
            or bool(str(current.get("runtime.failure.stage") or "").strip())
            or bool(str(current.get("runtime.failure.phase") or "").strip())
        )
        updates = {
            "status": "FAILED",
            "runtime.create_job.status": "failed",
            "runtime.create_job.error_code": type(exc).__name__,
            "runtime.resume.p500.status": "failed",
            "runtime.resume.p500.error": detail,
        }
        if not str(current.get("last_error") or "").strip():
            updates["last_error"] = detail
        if not concrete_failure:
            updates["runtime.stage"] = "p500_resume_failed"
        append_state_snapshot(run_dir / "state.txt", updates)


async def _run_p500_resume_job_bound(
    job_id: str,
    *,
    run_id: str,
    create_mode: str,
) -> None:
    run_dir = safe_run_dir(run_id, ROOT)
    started = time.monotonic()
    try:
        operation_id = (_create_jobs.get(job_id) or {}).get("mediaOperationId")
        if not operation_id and (_create_jobs.get(job_id) or {}).get("resumeMode") == "narration_start":
            from toc.media_resume import MediaJournal
            try:
                journal = MediaJournal.create(
                    run_dir, "narration_drafts",
                    NarrationDraftCreateRequest(run_id=run_id, replace=False).model_dump(mode="json"),
                )
            except Exception:
                append_state_snapshot(run_dir / "state.txt", {
                    "status": "FAILED", "runtime.stage": "narration_preparation_failed",
                    "runtime.failure.stage": "p710", "slot.p710.status": "failed",
                    "runtime.resume.narration.status": "journal_setup_failed",
                })
                raise
            append_state_snapshot(run_dir / "state.txt", {"runtime.resume.narration.status": "running"})
            operation_id = journal.id
            await _set_create_job(job_id, {
                "mediaOperationId": operation_id,
                "currentProcess": "p710", "currentProcessNumber": 710,
                "message": "ナレーション準備を開始中",
            })
        if operation_id:
            narration_start = (_create_jobs.get(job_id) or {}).get("stopTarget") == "p710"
            if narration_start:
                append_state_snapshot(run_dir / "state.txt", {
                    "status": "P710", "runtime.stage": "narration_preparing",
                    "slot.p710.status": "in_progress", "last_error": "",
                    "runtime.failure.stage": "", "runtime.failure.phase": "",
                })
            try:
                result = await _resume_saved_media_operation(run_dir, operation_id)
            except BaseException as exc:
                if narration_start:
                    append_state_snapshot(run_dir / "state.txt", {
                        "status": "FAILED", "runtime.stage": "narration_preparation_failed",
                        "runtime.failure.stage": "p710", "slot.p710.status": "failed",
                        "runtime.resume.narration.status": "failed",
                        "last_error": _create_run_error_message(
                            exc if isinstance(exc, Exception) else RuntimeError("narration preparation interrupted")
                        ),
                    })
                raise
            if narration_start:
                append_state_snapshot(run_dir / "state.txt", {"runtime.resume.narration.status": "completed"})
            await _set_create_job(job_id, {
                "status": "completed", "message": "保存済みの設定で再開完了",
                "resumeMode": "media_operation", "result": result,
            })
            return
        await _set_create_job(
            job_id,
            {
                "message": "p500再開計画を検証中",
                "metadata": {"resumeMode": "p500_subprocess"},
            },
        )
        try:
            current_record = await asyncio.to_thread(
                process_store.get_process_run,
                run_id=run_id,
            )
        except Exception:
            current_record = None
        create_mode = _resume_create_mode_for_run(run_dir, current_record)
        create_input_path = (
            run_dir / "logs" / "orchestration" / "create_input.json"
        )
        has_canonical_create_input = (
            create_input_path.exists() or create_input_path.is_symlink()
        )
        source: str | None = None
        if not has_canonical_create_input:
            record_mode = str(
                getattr(current_record, "create_mode", "") or ""
            ).strip()
            if (
                create_mode == CREATE_MODE_WORLD_WALK
                or record_mode == CREATE_MODE_WORLD_WALK
            ):
                raise RuntimeError(
                    "legacy world_walk p500 resume requires canonical exact "
                    "create input; the process source is only a run path"
                )
            record_source = getattr(current_record, "source", None)
            if (
                not isinstance(record_source, str)
                or not record_source.strip()
            ):
                raise RuntimeError(
                    "legacy p500 resume requires the exact source from its "
                    "current process record"
                )
            source = record_source
        if _requires_authoring_resume(run_dir):
            await _set_create_job(job_id, {
                "resumeMode": "authoring_subprocess",
                "message": "検証済みの前工程を保持して執筆を再開中",
                "metadata": {"resumeMode": "authoring_subprocess"},
            })
            await _run_authoring_resume_subprocess(job_id=job_id, run_dir=run_dir)
        subprocess_result = await _run_p500_resume_subprocess(
            job_id=job_id,
            run_dir=run_dir,
            source=source,
        )
        await _set_create_job(
            job_id,
            {
                "message": "p680成果物を検証中",
                "metadata": {
                    "resumeMode": "p500_subprocess",
                    "checkpointId": subprocess_result["checkpointId"],
                },
            },
        )
        try:
            current_record = await asyncio.to_thread(
                process_store.get_process_run,
                run_id=run_id,
            )
        except Exception:
            current_record = None
        create_mode = _resume_create_mode_for_run(run_dir, current_record)
        _validate_current_p680_run(
            run_id,
            create_mode=create_mode,
        )
        await _sync_process_current_process(job_id, run_id)
        await _set_create_job(
            job_id,
            {
                "status": "completed",
                "message": "再開完了",
                "currentProcess": "p680",
                "currentProcessNumber": 680,
            },
        )
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="create_job_resume_p500_subprocess",
            status="completed",
            item_id=job_id,
            request={"runId": run_id, "createMode": create_mode},
            response={
                "elapsedMs": int((time.monotonic() - started) * 1000),
                "checkpointId": subprocess_result["checkpointId"],
            },
        )
    except Exception as exc:
        # The subprocess owns both the create/resume lease and canonical resume
        # state. Preserve its semantic failure and applied checkpoint verbatim.
        with suppress(Exception):
            await _record_p500_resume_failure_state(run_dir, exc)
        failed_job = _create_jobs.get(job_id) or {}
        if not failed_job.get("mediaOperationId") and failed_job.get("resumeMode") != "narration_start":
            with suppress(Exception):
                _invalidate_published_image_generation_handoff(
                    run_dir,
                    invalidated_by="p500_resume.post_handoff_failure",
                    reason=str(exc),
                )
        with suppress(Exception):
            await _sync_process_current_process(job_id, run_id)
        detail = _create_run_error_message(exc)
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="create_job_resume_p500_subprocess",
            status="failed",
            item_id=job_id,
            request={"runId": run_id, "createMode": create_mode},
            response={
                "elapsedMs": int((time.monotonic() - started) * 1000),
                **_create_job_failure_diagnostics(run_dir),
            },
            error=f"{type(exc).__name__}: {exc}",
        )
        await _set_create_job(
            job_id,
            {
                "status": "failed",
                "error": detail,
                "errorCode": type(exc).__name__,
                "message": "再開失敗",
            },
        )


@router.post("/api/image-gen/runs/{run_id}/resume")
async def api_resume_run(run_id: str, req: ResumeRunRequest) -> dict[str, Any]:
    if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
        raise ValueError("invalid run_id")
    run_dir = output_root(ROOT) / run_id
    try:
        retained_run = _retain_frontend_create_run(run_dir)
    except FrontendCreateLockOwnedError as exc:
        # A live worker can own the directory before this API reaches the
        # in-memory active-job check (including workers from another process).
        raise HTTPException(
            status_code=409,
            detail="このrunの作成・再開処理はすでに実行中です。進捗を確認してください。",
        ) from exc
    job_id = uuid.uuid4().hex
    job_reserved = False
    task_scheduled = False
    try:
        async with _create_jobs_lock:
            same_run_active = any(
                str(existing.get("runId") or "") == run_id
                and str(existing.get("status") or "")
                not in {"completed", "failed", "paused"}
                for existing in _create_jobs.values()
            )
            if same_run_active:
                raise HTTPException(
                    status_code=409,
                    detail="run create/resume is already active",
                )
            _create_jobs[job_id] = {
                "jobId": job_id,
                "runId": run_id,
                "path": f"output/{run_id}",
                "status": "inspecting",
            }
            job_reserved = True

        with bind_run_root(
            run_dir,
            expected_identity=retained_run.identity,
            descriptor=retained_run.descriptor,
        ):
            try:
                await _acquire_run_execution_lease(
                    job_id,
                    run_dir,
                    run_descriptor=retained_run.descriptor,
                    expected_run_identity=retained_run.identity,
                )
            except FileLockUnavailable as exc:
                raise HTTPException(
                    status_code=409,
                    detail="run create/resume is already active",
                ) from exc

            try:
                record = await asyncio.to_thread(
                    process_store.get_process_run,
                    run_id=run_id,
                )
            except Exception:
                record = None
            create_mode = _resume_create_mode_for_run(run_dir, record)

            from toc.media_resume import MediaJournal
            try:
                media_operation = (
                    MediaJournal.load(run_dir, req.operation_id) if req.operation_id
                    else MediaJournal.latest_incomplete(run_dir)
                )
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail="saved media operation was not found") from exc
            except (ValueError, KeyError, TypeError) as exc:
                raise HTTPException(status_code=409, detail="saved media operation is invalid: " + str(exc)) from exc
            if media_operation is not None:
                try:
                    media_operation.verify_inputs()
                except ValueError as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
                resume_mode = "media_operation"
                p650_complete = False
            else:
                try:
                    _validate_current_p680_run(
                        run_id,
                        create_mode=create_mode,
                    )
                except Exception:
                    p680_complete = False
                else:
                    p680_complete = True
                if p680_complete:
                    state = parse_state_file(run_dir / "state.txt")
                    waiting = (
                        str(state.get("status") or "").upper() == "P680"
                        and state.get("slot.p710.status") in {"pending", "not_started"}
                        and state.get("runtime.repair.phase") != "repairing"
                    )
                    setup_retry = (
                        state.get("status") == "FAILED"
                        and state.get("slot.p710.status") == "failed"
                        and state.get("runtime.resume.narration.status") == "journal_setup_failed"
                    )
                    if not (req.continue_waiting and waiting) and not setup_retry:
                        raise HTTPException(
                            status_code=409,
                            detail="run already reached strict p680 completion; no requested waiting stage is available",
                        )
                    resume_mode = "narration_start"
                    p650_complete = False

                if not p680_complete:
                    try:
                        _validate_p650_run(run_id)
                    except Exception:
                        p650_complete = False
                    else:
                        p650_complete = True
                    if p650_complete:
                        regeneration_plan = _classify_p680_regeneration_plan(run_dir)
                        if regeneration_plan.errors:
                            raise HTTPException(
                                status_code=409,
                                detail=(
                                    "image-only resume preflight rejected unsafe "
                                    "regeneration targets: "
                                    + "; ".join(regeneration_plan.errors[:20])
                                ),
                            )
                        resume_mode = (
                            "p500_subprocess"
                            if regeneration_plan.requires_canonical_p500
                            else "image_only"
                        )
                    else:
                        resume_mode = "authoring_subprocess" if _requires_authoring_resume(run_dir) else "p500_subprocess"
            current_process_number = _current_process_number_for_run(run_id)
            if current_process_number == 0 and record is not None:
                current_process_number = int(record.current_process_number)
            if p650_complete:
                current_process_number = max(650, current_process_number)
            current_process = _process_label(current_process_number)
            title = record.title if record else run_id
            source = record.source if record and record.source else title
            saved_path = run_dir / "logs/orchestration/create_input.json"
            if saved_path.exists() or saved_path.is_symlink():
                from toc.authoring_resume import read_create_input
                saved = read_create_input(run_dir)
                title, source = saved["topic"], saved["source"]
            resume_failure_baseline: tuple[str, str, str] | None = None
            try:
                baseline_progress = read_run_progress(
                    run_dir,
                    validate_request_outputs=False,
                )
            except (FileNotFoundError, OSError, ValueError):
                baseline_progress = None
            if isinstance(baseline_progress, dict):
                baseline_failure = baseline_progress.get("failure")
                if isinstance(baseline_failure, dict) and baseline_failure.get("terminal"):
                    resume_failure_baseline = (
                        str(baseline_failure.get("stage") or ""),
                        str(baseline_failure.get("runtimeStage") or ""),
                        str(baseline_failure.get("message") or ""),
                    )
            try:
                target_duration_seconds = _target_duration_seconds_for_run(run_dir)
            except ValueError as exc:
                raise HTTPException(
                    status_code=409,
                    detail=f"run target duration is invalid: {exc}",
                ) from exc

            effective_stop = "p710" if resume_mode == "narration_start" else req.stop_target
            if media_operation is not None:
                effective_stop = {
                    "narration_drafts": "p710", "narration": "p730", "narration_bulk": "p730",
                    "video_prompts": "p830", "video": "p840", "video_bulk": "p840",
                    "sound": "p860",
                    "render_freeze": "p910", "render": "p920",
                }[media_operation.data["kind"]]
            job = {
                "jobId": job_id,
                "runId": run_id,
                "path": f"output/{run_id}",
                "status": "running",
                "title": title,
                "createMode": create_mode,
                "resumeMode": resume_mode,
                "mediaOperationId": media_operation.id if media_operation else None,
                "targetDurationSeconds": target_duration_seconds,
                "stopTarget": effective_stop,
                "stopTargetNumber": _process_number(effective_stop),
                "currentProcess": current_process,
                "currentProcessNumber": current_process_number,
                "pid": os.getpid(),
                "error": None,
                "errorCode": None,
                "message": f"{current_process}から{effective_stop}へ再開中",
            }
            async with _create_jobs_lock:
                running_count = sum(
                    1
                    for existing_id, existing in _create_jobs.items()
                    if existing_id != job_id
                    and existing.get("status") == "running"
                )
                if running_count >= MAX_RUNNING_CREATE_JOBS:
                    raise HTTPException(
                        status_code=429,
                        detail="too many create jobs are running",
                    )
                if len(_create_jobs) > MAX_CREATE_JOBS:
                    terminal_job_id = next(
                        (
                            existing_id
                            for existing_id, existing in _create_jobs.items()
                            if existing_id != job_id
                            and existing.get("status")
                            in {"completed", "failed", "paused"}
                        ),
                        None,
                    )
                    if terminal_job_id:
                        _create_jobs.pop(terminal_job_id)
                    else:
                        raise HTTPException(
                            status_code=503,
                            detail="too many create jobs are running",
                        )
                _create_jobs[job_id] = job
                if resume_failure_baseline is not None:
                    _create_job_failure_baselines[job_id] = resume_failure_baseline

            process_store_result = await asyncio.to_thread(
                _create_process_record_best_effort,
                job=job,
                title=title,
                source=source,
                stop_target=effective_stop,
                generate_images=media_operation is None and resume_mode != "narration_start",
            )
            if process_store_result:
                job["processStore"] = process_store_result
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="create_job_resume",
                status="running",
                item_id=job_id,
                request={
                    "runId": run_id,
                    "fromProcess": current_process,
                    "fromProcessNumber": current_process_number,
                    "stopTarget": effective_stop,
                    "targetDurationSeconds": target_duration_seconds,
                    "resumeMode": resume_mode,
                    "resumePolicy": (
                        "hash_aware_partial"
                        if resume_mode == "image_only"
                        else ("authoring_checkpoints_then_p500" if resume_mode == "authoring_subprocess"
                              else "p500_checkpoint_plan_apply")
                    ),
                    "processStore": process_store_result,
                },
                response={"path": f"output/{run_id}"},
            )

        if resume_mode == "image_only":
            resume_coro = _run_image_only_resume_job(
                job_id,
                run_id=run_id,
                create_mode=create_mode,
                retained_run=retained_run,
            )
        else:
            resume_coro = _run_p500_resume_job(
                job_id,
                run_id=run_id,
                create_mode=create_mode,
                retained_run=retained_run,
            )
        try:
            resume_task = asyncio.create_task(resume_coro)
        except BaseException:
            resume_coro.close()
            raise
        _resume_tasks[job_id] = resume_task
        resume_task.add_done_callback(
            lambda completed, current_job_id=job_id: _cleanup_resume_task(completed, current_job_id)
        )
        task_scheduled = True
        return job
    except BaseException:
        if not task_scheduled:
            await _release_run_execution_lease(job_id)
            if job_reserved:
                async with _create_jobs_lock:
                    _create_jobs.pop(job_id, None)
                _create_job_failure_baselines.pop(job_id, None)
            retained_run.close()
        raise


def _request_gallery_payload(
    *,
    run_dir: Path,
    run_id: str,
    kind: str,
    restore_retained_candidates: bool,
) -> dict[str, Any]:
    """Build the read-only gallery without generation-grade verification."""

    items = []
    request_items = load_request_items_for_display(run_dir, kind)
    for item in request_items:
        payload = item_to_api(item)
        persisted_candidates = list_candidate_items(run_dir, item.id)
        if (
            restore_retained_candidates
            or (
                not persisted_candidates
                and not item.existing_image
            )
        ):
            rehydrate_retained_first_image(
                run_dir,
                root=ROOT,
                kind=kind,
                item_id=str(item.id),
            )
            persisted_candidates = list_candidate_items(run_dir, item.id)
        payload["candidates"] = persisted_candidates
        items.append(payload)
    if not request_items and restore_retained_candidates:
        for retention in list_restored_first_image_items(
            run_dir,
            kind=kind,
        ):
            item_id = str(retention["itemId"])
            output = (
                str(retention.get("destination") or "")
                if retention.get("storageRole") == "canonical"
                else None
            )
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
    references = [
        reference_to_api(option)
        for option in list_reference_options(run_dir)
    ]
    return {
        "run": {"id": run_id, "path": f"output/{run_id}"},
        "kind": kind,
        "items": items,
        "references": references,
        "progress": read_run_progress(
            run_dir,
            validate_request_outputs=False,
        ),
    }


@router.get("/api/image-gen/requests")
async def api_requests(run_id: str, kind: str = Query(pattern="^(asset|scene)$")) -> dict[str, Any]:
    try:
        run_dir = safe_run_dir(run_id, ROOT)
    except FileNotFoundError:
        restored = await asyncio.to_thread(
            restore_first_image_retention_run,
            run_id,
            root=ROOT,
        )
        if restored is None:
            raise
        run_dir = restored
    restore_retained_candidates = is_first_image_retention_restored_run(run_dir)
    from server.display_reads import shared_read
    return await shared_read(_display_read_key(run_dir, "images:" + kind), lambda: asyncio.to_thread(
        _request_gallery_payload,
        run_dir=run_dir,
        run_id=run_id,
        kind=kind,
        restore_retained_candidates=restore_retained_candidates,
    ))


def _display_read_key(run_dir: Path, kind: str) -> tuple:
    from server.display_reads import file_version
    root = run_dir.stat()
    return (str(run_dir), root.st_dev, root.st_ino, kind, *(
        file_version(run_dir / name) for name in (
            "video_manifest.md", "state.txt", "state.current.json",
            "video_generation_requests.md", "image_generation_requests.md",
        )
    ))


def _narration_display_payload(run_dir: Path) -> dict[str, Any]:
    from server.display_reads import read_manifest
    data = read_manifest(run_dir / "video_manifest.md", _extract_manifest_yaml_text)
    return {
        "run": {"id": run_dir.name, "path": f"output/{run_dir.name}"},
        "items": _manifest_narration_items(run_dir, data),
        "audioSetHash": _manifest_narration_audio_set_hash(data),
        "progress": read_run_progress(run_dir, validate_request_outputs=False),
    }


@router.get("/api/image-gen/narration-items")
async def api_narration_items(run_id: str) -> dict[str, Any]:
    from server.display_reads import shared_read
    run_dir = safe_run_dir(run_id, ROOT)
    async def read():
        async with _serialized_run_write(run_dir, "run_artifacts"):
            return await _run_blocking_with_cancel_barrier(_narration_display_payload, run_dir)
    try:
        return await shared_read(_display_read_key(run_dir, "narration"), read)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _video_display_payload(run_dir: Path) -> dict[str, Any]:
    from server.display_reads import read_manifest
    data = read_manifest(run_dir / "video_manifest.md", _extract_manifest_yaml_text)
    return {
        "run": {"id": run_dir.name, "path": f"output/{run_dir.name}"},
        "items": _manifest_video_items(run_dir, data),
        "references": [reference_to_api(option) for option in list_reference_options(run_dir)],
        "progress": read_run_progress(run_dir, validate_request_outputs=False),
    }


@router.get("/api/image-gen/video-items")
async def api_video_items(run_id: str) -> dict[str, Any]:
    from server.display_reads import shared_read
    run_dir = safe_run_dir(run_id, ROOT)
    try:
        return await shared_read(_display_read_key(run_dir, "video"),
                                 lambda: asyncio.to_thread(_video_display_payload, run_dir))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/image-gen/progress")
async def api_progress(run_id: str) -> dict[str, Any]:
    run_dir = safe_run_dir(run_id, ROOT)
    return {
        "run": {"id": run_id, "path": f"output/{run_id}"},
        "progress": await asyncio.to_thread(read_run_progress, run_dir, validate_request_outputs=False),
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
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    "status": "P830",
                    "runtime.stage": "video_prompts_ready",
                    "slot.p810.status": "done",
                    "slot.p810.note": "frontend video prompt settings saved",
                    "slot.p830.status": "done",
                    "slot.p830.note": "video generation requests are materialized and ready",
                    "stage.video_generation.status": "ready",
                    "artifact.video_generation_requests": str(request_path.resolve()),
                    "review.frontend.video_prompt.design": design_path.relative_to(run_dir).as_posix(),
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
        "readyForGeneration": True,
        "progress": read_run_progress(run_dir),
    }


async def _run_media_item(key: str, request: dict[str, Any], action: Callable) -> dict[str, Any]:
    from toc.media_resume import ACTIVE_MEDIA_JOURNAL, output_paths
    journal = ACTIVE_MEDIA_JOURNAL.get()
    if journal is None:
        return await action()
    journal.verify_inputs()
    cached = journal.cached(key, request)
    if cached is not None:
        if all(_probe_media_duration_seconds(journal.root / path) is not None for path in output_paths(cached)):
            return cached
    result = await action()
    journal.complete_item(key, request, result)
    return result


async def _dispatch_media_operation(kind: str, req: BaseModel, function: Callable) -> dict[str, Any]:
    if kind in {"video_bulk", "narration_drafts", "video_prompts", "render_freeze"}:
        return await function(req)
    if kind == "narration_bulk":
        if len({item.item_id for item in req.items}) != len(req.items):
            raise ValueError("bulk narration generation contains duplicate item_id values")
        semaphore = asyncio.Semaphore(req.concurrency)
        async def one(item):
            async with semaphore:
                try:
                    return await api_narration_generate(NarrationGenerateRequest(run_id=req.run_id, **item.model_dump()))
                except Exception as exc:
                    return {"itemId": item.item_id, "status": "failed", "error": str(exc), "candidates": []}
        results = await asyncio.gather(*(one(item) for item in req.items))
        from toc.media_resume import result_failed
        payload = {"runId": req.run_id, "status": "partial_failure" if result_failed(results) else "completed"}
        payload.update({"results": [r.get("item", r) for r in results],
            "updated": [selector for r in results for selector in r.get("updated", [])],
            "audioReadyUpdated": [], "durationUpdated": [], "durationReady": False,
            "progress": read_run_progress(safe_run_dir(req.run_id, ROOT))})
        return payload
    if kind == "video":
        # Each candidate is checkpointed inside _generate_video_candidates.
        return await function(req)
    key = kind + ":" + str(getattr(req, "item_id", "final"))
    return await _run_media_item(key, req.model_dump(mode="json"), lambda: function(req))


async def _finish_media_operation(journal, action: Callable) -> dict[str, Any]:
    """Persist provider completion before releasing a lease on disconnect/cancellation."""
    from toc.media_resume import result_failed
    worker = asyncio.create_task(action())
    cancellation = None
    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError as exc:
            cancellation = exc
        except Exception:
            break
    try:
        result = worker.result()
        success = not result_failed(result) and all(
            item.get("status") == "completed" for item in journal.data["items"].values()
        )
        journal.finish(success)
        if journal.data["status"] != "completed" and not result_failed(result):
            raise RuntimeError("media result could not be verified; operation remains resumable")
    except BaseException:
        journal.finish(False)
        raise
    if cancellation is not None:
        raise cancellation
    return result


def _durable_media_operation(kind: str):
    from functools import wraps
    def decorate(function):
        @wraps(function)
        async def wrapped(req):
            from toc.media_resume import ACTIVE_MEDIA_JOURNAL, MediaJournal
            current = ACTIVE_MEDIA_JOURNAL.get()
            if current is not None:
                if current.request.get("run_id") != req.run_id:
                    raise ValueError("media operation run changed")
                return await _dispatch_media_operation(kind, req, function)
            run_dir = safe_run_dir(req.run_id, ROOT)
            lease_id = "media-" + uuid.uuid4().hex
            try:
                lease = await _acquire_run_execution_lease(lease_id, run_dir)
            except FileLockUnavailable as exc:
                raise HTTPException(status_code=409, detail="run generation/resume is already active") from exc
            try:
                with bind_run_root(run_dir, expected_identity=lease.identity, descriptor=lease.run_descriptor):
                    journal = MediaJournal.create(run_dir, kind, req.model_dump(mode="json"))
                    token = ACTIVE_MEDIA_JOURNAL.set(journal)
                    try:
                        result = await _finish_media_operation(journal,
                            lambda: _dispatch_media_operation(kind, req, function))
                        return {**result, "operationId": journal.id}
                    finally:
                        ACTIVE_MEDIA_JOURNAL.reset(token)
            finally:
                await _release_run_execution_lease(lease_id)
        return wrapped
    return decorate


async def _resume_saved_media_operation(run_dir: Path, operation_id: str) -> dict[str, Any]:
    from toc.media_resume import ACTIVE_MEDIA_JOURNAL, MediaJournal
    journal = MediaJournal.load(run_dir, operation_id)
    journal.verify_inputs()
    handlers = {
        "sound": (_sound_design_api.durable_generate, _sound_design_api.SoundGenerateRequest),
        "narration": (api_narration_generate, NarrationGenerateRequest),
        "narration_bulk": (api_narration_generate_bulk, BulkNarrationGenerateRequest),
        "video": (api_video_generate, VideoGenerateRequest),
        "video_bulk": (api_video_generate_bulk, BulkVideoGenerateRequest),
        "render": (api_final_render, FinalRenderRequest),
        "narration_drafts": (api_create_narration_drafts, NarrationDraftCreateRequest),
        "video_prompts": (api_create_video_prompts, VideoPromptCreateRequest),
        "render_freeze": (api_render_inputs_freeze, RenderFreezeRequest),
    }
    handler, model = handlers[journal.data["kind"]]
    request = model.model_validate(journal.request)
    if request.run_id != run_dir.name:
        raise ValueError("saved media operation belongs to another run")
    journal.data["status"] = "running"
    journal.save()
    token = ACTIVE_MEDIA_JOURNAL.set(journal)
    try:
        result = await _finish_media_operation(journal, lambda: handler(request))
        if journal.data["status"] != "completed":
            raise RuntimeError("media operation still has failed items; completed items were preserved")
        return {**result, "operationId": journal.id}
    finally:
        ACTIVE_MEDIA_JOURNAL.reset(token)


@router.post("/api/image-gen/video-prompts/create")
@_durable_media_operation("video_prompts")
async def api_create_video_prompts(req: VideoPromptCreateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    # Keep request materialization and provider binding in one revision
    # transaction so another request cannot replace the manifest mid-write.
    async with _serialized_run_write(run_dir, "video_prompt_revision"):
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
async def api_audio_file(run_id: str, path: str, preview_item: str | None = None) -> FileResponse:
    run_dir = safe_run_dir(run_id, ROOT)
    try:
        _validate_run_relative_audio_path(run_dir, path, must_exist=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    target = resolve_run_relative(run_dir, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    if preview_item is not None:
        from toc.narration_audio import narration_preview, DEFAULT_LEAD_IN_SECONDS
        _manifest, _text, data = _read_manifest_data(run_dir)
        item = _target_by_item_id(data, preview_item)
        if item is None:
            raise HTTPException(status_code=404, detail="narration item not found")
        node = _dict_value(item.get("cut"))
        narration = _dict_value(_dict_value(node.get("audio")).get("narration"))
        allowed = {str(narration.get("output") or "")}
        allowed.update(str(c.get("output") or "") for c in _list_value(narration.get("candidates")) if isinstance(c, dict))
        if path not in allowed:
            raise HTTPException(status_code=400, detail="audio does not belong to this narration item")
        if narration.get("tool") == "silent":
            return FileResponse(target)
        offset = float(_dict_value(node.get("render")).get("narration_offset_seconds", DEFAULT_LEAD_IN_SECONDS))
        measured = await asyncio.to_thread(_probe_media_duration_seconds, target)
        if measured is None:
            raise HTTPException(status_code=422, detail="narration duration could not be measured")
        duration = max(float(_dict_value(node.get("video_generation")).get("duration_seconds") or 0), math.ceil(measured + offset))
        try:
            target = await asyncio.to_thread(narration_preview, target,
                _render_asset_dir(run_dir, "narration_preview"), offset_seconds=offset, duration_seconds=duration)
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
            raise HTTPException(status_code=422, detail="narration preview preparation failed") from exc
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
@_durable_media_operation("narration_drafts")
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
                _append_narration_ready_state(run_dir)
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
@_durable_media_operation("narration")
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
@_durable_media_operation("narration_bulk")
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
    return {"runId": req.run_id, "status": "selected", **result, "progress": progress}

@router.post("/api/image-gen/video-generate")
@_durable_media_operation("video")
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
@_durable_media_operation("video_bulk")
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
@_durable_media_operation("render_freeze")
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
@_durable_media_operation("render")
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


async def _run_bulk_generation_job_bound(
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


async def _run_bulk_generation_job(
    *,
    job_id: str,
    run_dir: Path,
    groups: list[list[_BulkGenerationPlanItem]],
    requested_concurrency: int,
    run_descriptor: int,
    expected_run_identity: tuple[int, int],
) -> None:
    """Keep every background provider call on the leased run inode."""

    try:
        with bind_run_root(
            run_dir,
            expected_identity=expected_run_identity,
            descriptor=run_descriptor,
        ):
            await _run_bulk_generation_job_bound(
                job_id=job_id,
                run_dir=run_dir,
                groups=groups,
                requested_concurrency=requested_concurrency,
            )
    finally:
        _bulk_generation_tasks.pop(job_id, None)
        await _release_run_execution_lease(job_id)


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
        try:
            execution_lease = await _acquire_run_execution_lease(
                str(job["jobId"]),
                run_dir,
            )
        except FileLockUnavailable as exc:
            raise HTTPException(
                status_code=409,
                detail="run create/resume is already active",
            ) from exc
        try:
            with bind_run_root(
                run_dir,
                expected_identity=execution_lease.identity,
                descriptor=execution_lease.run_descriptor,
            ):
                _bulk_generation_jobs[str(job["jobId"])] = job
                _persist_bulk_generation_job(job)
        except Exception:
            _bulk_generation_jobs.pop(str(job["jobId"]), None)
            await _release_run_execution_lease(str(job["jobId"]))
            raise

    job_id = str(job["jobId"])
    generation_coro = _run_bulk_generation_job(
        job_id=job_id,
        run_dir=run_dir,
        groups=groups,
        requested_concurrency=int(req.concurrency),
        run_descriptor=execution_lease.run_descriptor,
        expected_run_identity=execution_lease.identity,
    )
    try:
        task = asyncio.create_task(generation_coro)
    except BaseException:
        generation_coro.close()
        await _release_run_execution_lease(job_id)
        raise
    _bulk_generation_tasks[job_id] = task
    task.add_done_callback(
        lambda completed, current_job_id=job_id: (
            _bulk_generation_tasks.pop(current_job_id, None)
            if _bulk_generation_tasks.get(current_job_id) is completed
            else None
        )
    )
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
    lease_id = f"image-foreground-{uuid.uuid4().hex}"
    try:
        execution_lease = await _acquire_run_execution_lease(
            lease_id,
            run_dir,
        )
    except FileLockUnavailable as exc:
        raise HTTPException(
            status_code=409,
            detail="run create/resume is already active",
        ) from exc
    try:
        with bind_run_root(
            run_dir,
            expected_identity=execution_lease.identity,
            descriptor=execution_lease.run_descriptor,
        ):
            candidates = await asyncio.gather(
                *(
                    _generate_one(run_dir, req, index)
                    for index in range(1, req.candidate_count + 1)
                )
            )
            return {"itemId": req.item_id, "candidates": candidates}
    finally:
        await _release_run_execution_lease(lease_id)


async def _run_foreground_bulk_generation(
    *,
    run_dir: Path,
    req: BulkGenerateRequest,
    total_candidates: int,
) -> dict[str, Any]:
    normalized_items = [
        item.model_copy(update={"run_id": req.run_id, "kind": req.kind})
        for item in req.items
    ]
    candidates_by_item: list[list[dict[str, Any]]] = [[] for _ in normalized_items]
    semaphore = asyncio.Semaphore(min(req.concurrency, max(total_candidates, 1)))
    jobs = [
        (item_position, item, candidate_index)
        for item_position, item in enumerate(normalized_items)
        for candidate_index in range(1, item.candidate_count + 1)
    ]

    async def guarded(
        item_position: int,
        item: GenerateRequest,
        candidate_index: int,
    ) -> tuple[int, dict[str, Any]]:
        async with semaphore:
            try:
                return item_position, await _generate_one(
                    run_dir,
                    item,
                    candidate_index,
                )
            except Exception as exc:
                return item_position, {
                    "index": candidate_index,
                    "status": "failed",
                    "path": None,
                    "error": str(exc),
                }

    for item_position, candidate in await asyncio.gather(
        *(guarded(*job) for job in jobs)
    ):
        candidates_by_item[item_position].append(candidate)

    payload = []
    for item, candidates in zip(
        normalized_items,
        candidates_by_item,
        strict=False,
    ):
        candidates.sort(key=lambda candidate: int(candidate.get("index") or 0))
        has_error = candidates and not any(
            candidate.get("path") for candidate in candidates
        )
        result: dict[str, Any] = {
            "itemId": item.item_id,
            "candidates": candidates,
        }
        if has_error:
            result["error"] = "generation failed"
        payload.append(result)
    return {"runId": req.run_id, "kind": req.kind, "results": payload}


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
    lease_id = f"bulk-foreground-{uuid.uuid4().hex}"
    try:
        execution_lease = await _acquire_run_execution_lease(
            lease_id,
            run_dir,
        )
    except FileLockUnavailable as exc:
        raise HTTPException(
            status_code=409,
            detail="run create/resume is already active",
        ) from exc
    try:
        with bind_run_root(
            run_dir,
            expected_identity=execution_lease.identity,
            descriptor=execution_lease.run_descriptor,
        ):
            return await _run_foreground_bulk_generation(
                run_dir=run_dir,
                req=req,
                total_candidates=total_candidates,
            )
    finally:
        await _release_run_execution_lease(lease_id)


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
        raise HTTPException(status_code=503, detail='Codex app-server is disabled')
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
            raise HTTPException(status_code=400, detail={'unknownItemIds': missing_ids})
        items = [item for item in items if item.id in requested_ids]
    if not items:
        raise HTTPException(status_code=400, detail='no matching prompt items')
    v2_items = [item for item in items if str(getattr(item, 'prompt_policy_version', '') or '') == 'image_api_prompt_v2']
    if v2_items and kind != 'scene':
        raise HTTPException(status_code=409, detail='compiled_v2_recompile_is_supported_for_scene_items_only')
    manifest_plans: dict[str, dict[str, Any]] = {}
    if v2_items:
        try:
            _manifest_path, _manifest_original, manifest_data = _read_manifest_data(run_dir)
            for item in v2_items:
                target = _target_by_item_id(manifest_data, item.id)
                if target is None:
                    raise ValueError(f'video manifest target not found: {item.id}')
                image_generation = _dict_value(_dict_value(target.get('cut')).get('image_generation'))
                plan = _dict_value(image_generation.get('first_frame_visual_plan'))
                if not plan:
                    raise ValueError(f'compiled_v2_first_frame_visual_plan_missing: {item.id}')
                manifest_plans[item.id] = deepcopy(plan)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    semaphore = asyncio.Semaphore(req.concurrency)

    async def regenerate_one(item: Any) -> dict[str, Any]:
        async with semaphore:
            client = create_codex_app_server_client(cwd=ROOT)
            try:
                await _start_app_server_with_log(client, run_dir=run_dir, operation='prompt_regeneration', item_id=item.id)
                if item.id in manifest_plans:
                    patch = await _revise_v2_visual_plan_with_log(client, run_dir=run_dir, item=item_to_api(item), current_plan=manifest_plans[item.id], instruction=req.instruction, setting_content=setting['content'])
                    return {'itemId': item.id, 'operation': 'recompiled', 'patch': patch, 'expectedPlanHash': _json_hash(manifest_plans[item.id])}
                prompt = await _regenerate_prompt_with_log(client, run_dir=run_dir, item=item_to_api(item), target=req.target, instruction=req.instruction, setting_content=setting['content'], operation='prompt_regeneration')
                return {'itemId': item.id, 'prompt': prompt, 'operation': 'direct_update'}
            finally:
                await client.stop()
    results = await asyncio.gather(*(regenerate_one(item) for item in items), return_exceptions=True)
    failures: list[dict[str, str]] = []
    prompts: dict[str, str] = {}
    v2_revisions: dict[str, dict[str, Any]] = {}
    for item, result in zip(items, results, strict=False):
        if isinstance(result, Exception):
            failures.append({'itemId': item.id, 'error': str(result)})
        else:
            item_id = str(result['itemId'])
            if result.get('operation') == 'recompiled':
                v2_revisions[item_id] = {'patch': _dict_value(result.get('patch')), 'expected_plan_hash': str(result.get('expectedPlanHash') or '')}
            else:
                prompts[item_id] = str(result['prompt'])
    if failures:
        raise HTTPException(status_code=500, detail={'status': 'failed', 'failures': failures})
    try:
        async with _serialized_run_write(run_dir, 'run_artifacts'):
            async with _serialized_run_write(run_dir, f'{kind}_request_revision'):
                rollback_paths = (run_dir / 'video_manifest.md', run_dir / 'image_generation_requests.md', run_dir / 'image_generation_request_snapshot.json', run_dir / 'asset_generation_requests.md', run_dir / 'asset_generation_request_snapshot.json')
                before = _capture_file_transaction(rollback_paths, state_paths=(run_dir / 'state.txt',))
                try:
                    compiled = _recompile_v2_scene_manifest(run_dir, v2_revisions) if v2_revisions else {}
                    if v2_revisions:
                        await _materialize_scene_requests(req.run_id)
                    update_result = update_request_prompts(run_dir, kind, prompts) if prompts else {'updated': [], 'missing': []}
                    reloaded = {item.id: item for item in load_request_items(run_dir, kind)}
                    missing_recompiled = sorted(set(v2_revisions) - set(reloaded))
                    if missing_recompiled:
                        raise ValueError(f'recompiled request items missing: {', '.join(missing_recompiled)}')
                    if v2_revisions:
                        append_state_snapshot(run_dir / 'state.txt', {'runtime.stage': 'prompt_recompiled', 'generation.image_prompt.request_freeze.status': 'draft', 'slot.p650.status': 'pending', 'slot.p650.note': 'compiled-v2 draft rematerialized; semantic image-prompt review must pass before freeze', 'slot.p660.status': 'pending', 'slot.p670.status': 'pending', 'slot.p680.status': 'pending', 'artifact.video_manifest': str((run_dir / 'video_manifest.md').resolve()), 'artifact.image_generation_requests': str((run_dir / 'image_generation_requests.md').resolve()), 'artifact.image_generation_request_snapshot': str((run_dir / 'image_generation_request_snapshot.json').resolve())})
                except Exception:
                    _restore_file_transaction(before)
                    raise
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        status_code = 409 if 'conflict' in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    if update_result['missing']:
        raise HTTPException(status_code=400, detail={'missingPromptSections': update_result['missing']})
    response_prompts = [{'itemId': item_id, 'prompt': str(reloaded[item_id].prompt), 'promptPolicyVersion': str(reloaded[item_id].prompt_policy_version or ''), 'operation': 'recompiled', 'requestRevision': str(reloaded[item_id].request_revision or ''), 'sourceDigest': str(compiled[item_id].get('source_digest') or ''), 'compilerVersion': str(compiled[item_id].get('compiler_version') or '')} for item_id in v2_revisions] + [{'itemId': item_id, 'prompt': prompt, 'operation': 'direct_update'} for item_id, prompt in prompts.items()]
    return {'runId': req.run_id, 'target': req.target, 'kind': kind, 'status': 'completed', 'operation': 'recompiled' if v2_revisions else 'direct_update', 'prompts': response_prompts, 'updated': [*v2_revisions.keys(), *update_result['updated']], 'missing': update_result['missing']}


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
    lease_ids: list[str] = []
    try:
        run_dirs = {item.run_id: safe_run_dir(item.run_id, ROOT) for item in req.items}
        ordered_runs = sorted(run_dirs.items(), key=lambda entry: str(entry[1]))
        for run_id, run_dir in ordered_runs:
            lease_id = f'candidate-insert-{uuid.uuid4().hex}-{run_id}'
            await _acquire_run_execution_lease(lease_id, run_dir)
            lease_ids.append(lease_id)
        async with AsyncExitStack() as lock_stack:
            for _run_id, run_dir in ordered_runs:
                await lock_stack.enter_async_context(_serialized_run_write(run_dir, 'run_artifacts'))
                await lock_stack.enter_async_context(_serialized_run_write(run_dir, 'asset_request_revision'))
                await lock_stack.enter_async_context(_serialized_run_write(run_dir, 'scene_request_revision'))
            planned: list[dict[str, Any]] = []
            for position, item in enumerate(req.items):
                run_dir = run_dirs[item.run_id]
                candidate = resolve_run_relative(run_dir, item.candidate_path)
                if not candidate.is_file():
                    raise FileNotFoundError(f'candidate not found: {item.candidate_path}')
                target = validate_candidate_insertion(run_dir, candidate, item.output)
                owner = _validate_candidate_matches_output(run_dir, candidate, item.output)
                planned.append({'position': position, 'run_dir': run_dir, 'candidate': candidate, 'output': item.output, 'target': target, 'owner': owner})
            target_keys = [(str(plan['run_dir']), str(plan['target'])) for plan in planned]
            if len(set(target_keys)) != len(target_keys):
                raise ValueError('bulk candidate insertion contains duplicate canonical outputs')
            before_outputs = None
            try:
                owners_by_run: dict[Path, list[tuple[str, str, Path, Path]]] = {}
                for plan in planned:
                    owner = plan['owner']
                    if owner is None:
                        continue
                    kind, item_id = owner
                    owners_by_run.setdefault(plan['run_dir'], []).append((kind, item_id, plan['target'], plan['candidate']))
                for run_dir, owners in owners_by_run.items():
                    invalidated_at = now_iso()
                    state_updates = {'status': 'P650', 'runtime.stage': 'candidate_insertion_requires_revalidation', 'generation.image_prompt.request_freeze.status': 'draft', 'generation.image_prompt.request_freeze.invalidated_by': 'candidate_insertion', 'generation.image_prompt.request_freeze.invalidated_at': invalidated_at, 'orchestration.p600.supervisor.status': 'invalidated', 'orchestration.p600.supervisor.invalidated_by': 'candidate_insertion', 'slot.p650.status': 'pending', 'slot.p650.note': 'candidate insertion changed canonical image bytes; request freeze must be revalidated', 'slot.p660.status': 'pending', 'slot.p660.note': 'canonical image provenance must be regenerated or rebound', 'slot.p670.status': 'pending', 'slot.p670.note': 'waiting for current canonical image validation', 'slot.p680.status': 'pending', 'slot.p680.note': 'candidate insertion invalidated the previous image-review handoff', 'stage.scene_implementation.status': 'pending', 'image_generation.status': 'not_started', 'image_generation.started': 'false', 'image_generation.generated_count': '0', 'image_generation.blocked_by': 'candidate_insertion_revalidation'}
                    for kind, item_id, target, candidate in owners:
                        safe_item_id = re.sub('[^A-Za-z0-9_.-]+', '_', item_id).strip('._') or 'item'
                        state_updates[f'image_generation.provenance.{kind}.{safe_item_id}.status'] = 'invalidated'
                        state_updates[f'image_generation.provenance.{kind}.{safe_item_id}.invalidated_at'] = invalidated_at
                        write_app_server_image_provenance_invalidation_log(run_dir=run_dir, kind=kind, item_id=item_id, destination=target, candidate=candidate)
                    append_state_snapshot(run_dir / 'state.txt', state_updates)
                    _invalidate_p600_supervisor_result(run_dir, invalidated_by='candidate_insertion')
                # Capture after our own invalidation events so rollback checks
                # distinguish later concurrent writes from this transaction.
                before_outputs = _capture_file_transaction(
                    (plan['target'] for plan in planned),
                    state_paths=(planned_run_dir / 'state.txt' for planned_run_dir in run_dirs.values()),
                )
                inserted: list[dict[str, Any]] = []
                for plan in planned:
                    result = dict(insert_candidate(plan['run_dir'], plan['candidate'], plan['output']))
                    if plan['owner'] is not None:
                        result['kind'], result['itemId'] = plan['owner']
                        result['provenanceInvalidated'] = True
                    inserted.append(result)
            except Exception:
                if before_outputs is not None:
                    _restore_file_transaction(before_outputs)
                raise
    except FileLockUnavailable as exc:
        raise HTTPException(status_code=409, detail=f'candidate insertion conflict: {exc}') from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f'candidate insertion failed: {exc}') from exc
    finally:
        for lease_id in reversed(lease_ids):
            await _release_run_execution_lease(lease_id)
    return {'inserted': inserted}


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


# Register p860 after the shared runtime and render helpers are defined.
from server import sound_design_api as _sound_design_api
_sound_design_api.install(sys.modules[__name__])
from server import production_tools_api as _production_tools_api
_production_tools_api.install(sys.modules[__name__])
