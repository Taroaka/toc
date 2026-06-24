from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
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

import yaml
try:
    from fastapi import APIRouter, HTTPException, Query
    from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
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
from toc.immersive_manifest import make_scene_cut_selector, normalize_dotted_id, selector_aliases
from toc.harness import append_state_snapshot, now_iso, parse_state_file
from toc import process_store
from toc.providers.kling import KlingClient, KlingConfig
from toc.providers.seedance import SeedanceClient, SeedanceConfig
from toc.script_narration import materialize_elevenlabs_tts_text
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
    IMAGE_SUFFIXES,
    build_zip,
    candidate_path,
    copy_saved_image,
    insert_candidate,
    item_to_api,
    list_reference_options,
    list_candidate_items,
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
    repo_root,
    resolve_run_relative,
    safe_run_dir,
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
IMAGE_GENERATION_PROVENANCE_POLICY_SERIAL_FALLBACK = "serial_fallback"
IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2 = "request_bound_v2"
IMAGE_GENERATION_ITEM_MAX_ATTEMPTS = max(1, int(os.environ.get("TOC_IMAGE_GEN_ITEM_MAX_ATTEMPTS", "3") or "3"))
IMAGE_GENERATION_ITEM_TIMEOUT_SECONDS = max(
    1.0,
    float(os.environ.get("TOC_IMAGE_GEN_ITEM_TIMEOUT_SECONDS", "900") or "900"),
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
    concurrency: int = Field(default=2, ge=1, le=100)


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


class CreateStoryboardRunRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    source: str | None = Field(default=None, max_length=4000)
    stop_target: str = Field(default="p680", pattern="^(p650|p680)$")


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


class NarrationDraftCreateRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)
    replace: bool = False


class NarrationSilentOkRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    item_id: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=2000)


class VideoGenerateItem(BaseModel):
    item_id: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=40000)
    first_reference: str | None = Field(default=None, max_length=500)
    last_reference: str | None = Field(default=None, max_length=500)
    references: list[str] = Field(default_factory=list, max_length=32)
    quality: str = Field(default="1080p", pattern="^(720p|1080p|4K)$")
    aspect_ratio: str = Field(default="16:9", pattern="^(16:9|9:16|1:1|4:3)$")
    duration_seconds: int = Field(default=8, ge=1, le=VIDEO_GENERATION_DURATION_MAX_SECONDS)
    tool: str = Field(default="kling_3_0", pattern="^(kling_3_0|kling_3_0_omni|seedance)$")
    candidate_count: int = Field(default=3, ge=1, le=8)


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


class NarrationGenerateRequest(NarrationGenerateItem):
    run_id: str = Field(min_length=1, max_length=200)


class BulkNarrationGenerateRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    items: list[NarrationGenerateItem] = Field(min_length=1, max_length=256)
    concurrency: int = Field(default=2, ge=1, le=8)


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
_codex_client: CodexAppServerClient | None = None
_client_lock = asyncio.Lock()
_create_jobs_lock = asyncio.Lock()
_generation_semaphore = asyncio.Semaphore(100)
_video_generation_semaphore = asyncio.Semaphore(4)
_narration_generation_semaphore = asyncio.Semaphore(4)
_generated_images_cutoff_lock = asyncio.Lock()
_chat_turn_lock = asyncio.Lock()
_chat_semaphore = asyncio.Semaphore(2)
_scene_detail_canonical_progress_lock = threading.Lock()
_run_write_locks: dict[tuple[str, str], asyncio.Lock] = {}
_run_write_locks_guard = asyncio.Lock()
MAX_ZIP_BYTES = 250 * 1024 * 1024
MAX_CREATE_JOBS = 64
MAX_RUNNING_CREATE_JOBS = 2


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


def _asset_prompt(*, topic: str, asset_kind: str, asset_id: str, output: str, fixed_prompts: list[str]) -> str:
    details = "\n".join(f"- {item}" for item in fixed_prompts if item.strip()) or "- 後続cutで同じ参照画像として使える一貫した外観"
    if asset_kind == "character":
        target = "キャラクター参照画像"
        rules = "顔、髪型、衣装、年齢感、体格、シルエットを固定する。"
    elif asset_kind == "object":
        target = "アイテム参照画像"
        rules = "silhouette、材質、装飾、縮尺感、物語上の役割が一目で分かるように固定する。"
    elif asset_kind == "style":
        target = "スタイル参照画像"
        rules = "後続cutが共有する画調、光、色、質感、レンズ感を固定する。特定人物や読める文字は入れない。"
    else:
        target = "場所参照画像"
        rules = "spatial identity、主要構造、光環境、場所固有の空気を固定する。人物は入れない。"
    return "\n".join(
        [
            "[素材設計]",
            f"この画像は物語「{topic}」で後続cutが参照する{target}。",
            "",
            "[対象]",
            f"{asset_id} / {output}",
            "",
            "[不変条件]",
            details,
            "",
            "[生成方針]",
            rules,
            "実写、シネマティック。文字なし、ロゴなし、ウォーターマークなし。",
            "",
            "[禁止]",
            "別物化、字幕、説明的UI、ロゴ、ウォーターマーク、読める文字。",
        ]
    )


def _asset_entries_from_manifest(run_dir: Path) -> list[dict[str, Any]]:
    manifest_path = run_dir / "video_manifest.md"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    data = yaml.safe_load(_extract_manifest_yaml_text(manifest_text)) or {}
    if not isinstance(data, dict):
        return []
    topic = str((data.get("video_metadata") or {}).get("topic") or data.get("topic") or run_dir.name)
    assets = data.get("assets") if isinstance(data.get("assets"), dict) else {}
    entries: list[dict[str, Any]] = []

    def append_refs(kind: str, nodes: Any, id_key: str) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            asset_id = str(node.get(id_key) or node.get("asset_id") or "").strip() or kind
            fixed = [str(item) for item in node.get("fixed_prompts") or [] if str(item).strip()]
            for ref in node.get("reference_images") or []:
                output = str(ref or "").strip()
                if not output:
                    continue
                selector = Path(output).stem
                entries.append(
                    {
                        "selector": selector,
                        "tool": "codex_builtin_image",
                        "asset_type": f"{kind}_reference" if kind != "location" else "location_anchor",
                        "execution_lane": "bootstrap_builtin",
                        "reference_count": 0,
                        "output": output,
                        "prompt": _asset_prompt(topic=topic, asset_kind=kind, asset_id=asset_id, output=output, fixed_prompts=fixed),
                    }
                )

    append_refs("character", assets.get("character_bible"), "character_id")
    append_refs("object", assets.get("object_bible"), "object_id")
    append_refs("location", assets.get("location_bible"), "location_id")
    style_guide = assets.get("style_guide") if isinstance(assets.get("style_guide"), dict) else {}
    style_prompts = [str(style_guide.get("visual_style") or "").strip()]
    style_prompts.extend(str(item) for item in style_guide.get("forbidden") or [] if str(item).strip())
    for ref in style_guide.get("reference_images") or []:
        output = str(ref or "").strip()
        if not output:
            continue
        selector = Path(output).stem
        entries.append(
            {
                "selector": selector,
                "tool": "codex_builtin_image",
                "asset_type": "style_reference",
                "execution_lane": "bootstrap_builtin",
                "reference_count": 0,
                "output": output,
                "prompt": _asset_prompt(topic=topic, asset_kind="style", asset_id="style_guide", output=output, fixed_prompts=style_prompts),
            }
        )
    return entries


def _write_asset_request_files(run_dir: Path) -> list[dict[str, Any]]:
    entries = _asset_entries_from_manifest(run_dir)
    lines = ["# Asset Generation Requests", ""]
    for entry in entries:
        lines.extend(
            [
                f"## {entry['selector']}",
                "",
                f"- tool: `{entry['tool']}`",
                f"- asset_type: `{entry['asset_type']}`",
                f"- execution_lane: `{entry['execution_lane']}`",
                f"- reference_count: `{entry['reference_count']}`",
                f"- output: `{entry['output']}`",
                "- references: `[]`",
                "",
                "```text",
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
    deleted: list[str] = []
    errors: list[str] = []
    if not assets_dir.exists():
        return {"deletedCount": 0, "deleted": [], "errors": []}
    for path in sorted(assets_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in image_suffixes:
            continue
        try:
            rel = path.relative_to(run_dir).as_posix()
            path.unlink()
            deleted.append(rel)
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    for directory in sorted((path for path in assets_dir.rglob("*") if path.is_dir()), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    return {"deletedCount": len(deleted), "deleted": deleted[:200], "errors": errors[:50]}


def _validate_created_run(run_id: str) -> None:
    run_dir = safe_run_dir(run_id, ROOT)
    required = ["state.txt", "video_manifest.md"]
    missing = [name for name in required if not (run_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"ToC run was not scaffolded: missing {', '.join(missing)}")


def _manifest_cut_contract(data: dict[str, Any], *, min_cuts_per_scene: int = 3) -> tuple[list[str], set[str]]:
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


def _validate_p650_run_core(
    run_id: str,
    *,
    require_semantic_reviews: bool,
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
    cut_issues, required_scene_outputs = _manifest_cut_contract(manifest_data, min_cuts_per_scene=3)
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
    if require_semantic_reviews:
        _validate_semantic_reviews(run_dir, ("scene_set", "scene_detail", "cut_blueprint", "asset_plan", "image_prompt"))
    if require_generated_asset_outputs:
        missing_asset_outputs = [
            str(item.output)
            for item in asset_items
            if item.output and not resolve_run_relative(run_dir, item.output).is_file()
        ]
        if missing_asset_outputs:
            raise RuntimeError(f"ToC run did not reach p650: missing generated asset outputs {', '.join(missing_asset_outputs)}")

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
    _validate_p650_run_core(run_id, require_semantic_reviews=True, require_generated_asset_outputs=True)


def _validate_materialized_p650_run(run_id: str) -> None:
    _validate_p650_run_core(run_id, require_semantic_reviews=False, require_generated_asset_outputs=False)


def _validate_frontend_create_run(run_id: str, *, strict_visual_quality: bool = True) -> None:
    _validate_p650_run(run_id)
    run_dir = safe_run_dir(run_id, ROOT)
    _validate_semantic_reviews(run_dir, ("scene_set", "scene_detail", "cut_blueprint", "asset_plan", "image_prompt"))
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
    result = check_image_prompt_judgment(run_dir)
    if not result.passed:
        raise RuntimeError("image prompt semantic review incomplete: " + "; ".join(result.errors))


def _validate_semantic_reviews(run_dir: Path, stages: Iterable[str]) -> None:
    errors: list[str] = []
    for stage in stages:
        result = check_image_prompt_judgment(run_dir) if stage == "image_prompt" else check_semantic_review(run_dir, stage)
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


def _video_candidate_dir(run_dir: Path, item_id: str) -> Path:
    return run_dir / "assets" / "test" / "video_gen_candidates" / _safe_artifact_id(item_id)


def _video_candidate_path(run_dir: Path, item_id: str, index: int) -> Path:
    return _video_candidate_dir(run_dir, item_id) / f"candidate_{index:02d}.mp4"


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


def _generate_elevenlabs_audio(path: Path, text: str) -> None:
    if not text.strip():
        raise ValueError("narration text is required for elevenlabs")
    from toc.providers.elevenlabs import ElevenLabsClient, ElevenLabsConfig

    load_env_files(repo_root=ROOT)
    client = ElevenLabsClient(ElevenLabsConfig.from_env())
    alias_file = os.environ.get("TOC_TTS_PRONUNCIATION_ALIAS_FILE") or str(ROOT / "config" / "tts-pronunciation-aliases.tsv")
    aliases = load_pronunciation_aliases(alias_file)
    prepared = prepare_elevenlabs_tts_text(text, pronunciation_aliases=aliases)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(client.tts(text=prepared.text))


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
        "status": "failed" if error else "completed",
        "error": error,
        "provider": provider_result or {},
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return log_path


def _generate_kling_video_file(
    *,
    request: VideoGenerateItem,
    input_image: Path | None,
    last_frame_image: Path | None,
    out_path: Path,
) -> dict[str, Any]:
    load_env_files(repo_root=ROOT)
    is_omni = request.tool == "kling_3_0_omni"
    model = (
        os.environ.get("KLING_OMNI_VIDEO_MODEL", "kling-3.0-omni")
        if is_omni
        else os.environ.get("KLING_VIDEO_MODEL", "kling-3.0")
    )
    extra_payload = _parse_optional_json_env("KLING_OMNI_EXTRA_JSON", "KLING_EXTRA_JSON") if is_omni else _parse_optional_json_env("KLING_EXTRA_JSON")
    client = KlingClient(KlingConfig.from_env(video_model=model))
    submit = client.start_video_generation(
        prompt=request.prompt,
        duration_seconds=int(request.duration_seconds),
        aspect_ratio=request.aspect_ratio,
        resolution=request.quality,
        input_image=input_image,
        last_frame_image=last_frame_image,
        negative_prompt=(os.environ.get("VIDEO_NEGATIVE_PROMPT") or "").strip() or None,
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
    if input_image is not None:
        model = os.environ.get("ARK_SEEDANCE_I2V_MODEL") or os.environ.get("SEEDANCE_I2V_MODEL") or "seedance-1-0-lite-i2v-250428"
    else:
        model = os.environ.get("ARK_SEEDANCE_T2V_MODEL") or os.environ.get("SEEDANCE_T2V_MODEL") or "seedance-1-0-pro-250528"
    extra_payload = _parse_optional_json_env("ARK_EXTRA_JSON")
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
        generate_audio=False,
        watermark=False,
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
    destination.parent.mkdir(parents=True, exist_ok=True)
    if request.tool in {"kling_3_0", "kling_3_0_omni"}:
        provider_result = _generate_kling_video_file(
            request=request,
            input_image=input_image,
            last_frame_image=last_frame_image,
            out_path=destination,
        )
    elif request.tool == "seedance":
        provider_result = _generate_seedance_video_file(
            request=request,
            input_image=input_image,
            last_frame_image=last_frame_image,
            reference_images=reference_images,
            out_path=destination,
        )
    else:
        raise ValueError(f"unsupported video tool: {request.tool}")
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
    input_image = _resolve_video_reference_image(run_dir, req.first_reference, field="first_reference")
    last_frame_image = _resolve_video_reference_image(run_dir, req.last_reference, field="last_reference")
    reference_images = [
        image
        for image in (_resolve_video_reference_image(run_dir, ref, field="references") for ref in req.references)
        if image is not None
    ]
    destination = _video_candidate_path(run_dir, req.item_id, index)
    async with _video_generation_semaphore:
        try:
            return await asyncio.to_thread(
                _generate_video_file_blocking,
                run_dir=run_dir,
                request=req,
                index=index,
                destination=destination,
                input_image=input_image,
                last_frame_image=last_frame_image,
                reference_images=reference_images,
            )
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
    min_duration = _narration_min_duration_seconds(run_dir, req.item_id)
    if min_duration is not None and req.duration_seconds < math.ceil(min_duration):
        req = req.model_copy(update={"duration_seconds": math.ceil(min_duration)})
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


def _write_manifest_data(manifest_path: Path, original_text: str, data: dict[str, Any]) -> None:
    yaml_text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    if "```yaml" not in original_text:
        manifest_path.write_text(f"```yaml\n{yaml_text}```\n", encoding="utf-8")
        return
    start = original_text.find("```yaml")
    yaml_start = original_text.find("\n", start)
    if yaml_start == -1:
        manifest_path.write_text(f"```yaml\n{yaml_text}```\n", encoding="utf-8")
        return
    yaml_start += 1
    yaml_end = original_text.find("```", yaml_start)
    if yaml_end == -1:
        manifest_path.write_text(original_text[:yaml_start] + yaml_text, encoding="utf-8")
        return
    manifest_path.write_text(original_text[:yaml_start] + yaml_text + original_text[yaml_end:], encoding="utf-8")


def _manifest_scene_targets(data: dict[str, Any]) -> list[dict[str, Any]]:
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        return []
    targets: list[dict[str, Any]] = []
    for scene_index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        scene_id = normalize_dotted_id(scene.get("scene_id"))
        if not scene_id:
            continue
        cuts = scene.get("cuts")
        if isinstance(cuts, list) and cuts:
            for cut_index, cut in enumerate(cuts):
                if not isinstance(cut, dict):
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


def _default_narration_output_for_target(target: dict[str, Any]) -> str:
    selector = str(target["selector"])
    return f"assets/audio/{selector}/{selector}_narration.mp3"


def _json_hash(value: Any) -> str:
    text = json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _fallback_narration_text(node: dict[str, Any], contract: dict[str, Any]) -> str:
    explicit = _first_non_empty(contract.get("text"), contract.get("narration"), node.get("narration_text"))
    if explicit:
        return explicit
    role = _first_non_empty(contract.get("role"), "emotion")
    target = _first_non_empty(contract.get("target_function"), _cut_summary(node), "このcutの物語上の意味を補う")
    return f"{target}。"


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
        if not replace and _has_existing_narration_review(previous):
            skipped.append(str(target["selector"]))
            continue
        contract = _cut_narration_contract(node)
        cut_contract = _dict_value(node.get("cut_contract"))
        source_event_contract = _dict_value(cut_contract.get("source_event_contract"))
        event_context = _dict_value(cut_contract.get("event_context_for_cut"))
        is_silent = _is_silent_role(contract)
        text = "" if is_silent else _fallback_narration_text(node, contract)
        elevenlabs_prompt = _elevenlabs_prompt_payload(text=text, scene=scene, node=node, contract=contract) if not is_silent else {
            "spoken_context": _scene_logline(scene),
            "voice_tags": [],
            "spoken_body": "",
            "stability": "creative",
            "materialized": "",
        }
        tts_text = "" if is_silent else _first_non_empty(contract.get("tts_text"), elevenlabs_prompt.get("materialized"), text)
        output = str(previous.get("output") or _default_narration_output_for_target(target)).strip()
        narration = {
            **previous,
            "status": "review_pending",
            "source": "p710_p720_narration_drafts_create",
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
            "output": "" if is_silent else output,
            "review": {
                "status": "pending",
                "human_review_ok": False,
                "approved_at": "",
                "note": "frontend review required before p800",
            },
            "normalize_to_scene_duration": False,
        }
        audio["narration"] = narration
        node["audio"] = audio
        updated.append(str(target["selector"]))

    _write_manifest_data(manifest_path, original_text, data)
    report_path = _write_narration_authoring_report(run_dir, updated=updated, skipped=skipped, replace=replace)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "status": "P720",
            "runtime.stage": "narration_text_ready_for_frontend_review",
            "slot.p710.status": "done",
            "slot.p710.note": "narration grounding and scene_narration_plan created from video_manifest",
            "slot.p720.status": "awaiting_approval",
            "slot.p720.note": "narration text drafts ready for frontend TTS review",
            "slot.p730.status": "pending",
            "slot.p740.status": "pending",
            "slot.p750.status": "pending",
            "stage.narration.status": "awaiting_frontend_review",
            "review.narration.status": "pending",
            "gate.narration_review": "required",
            "artifact.narration_authoring_report": report_path.relative_to(run_dir).as_posix(),
        },
    )
    return {"updated": updated, "skipped": skipped, "reportPath": report_path.relative_to(run_dir).as_posix()}


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
    narration.update(
        {
            "tool": "silent",
            "status": "audio_ready",
            "text": "",
            "tts_text": "",
            "output": "",
            "silence_contract": _silence_contract_payload(contract, confirmed_by_human=True, reason=reason),
            "review": {
                **_dict_value(narration.get("review")),
                "status": "approved",
                "human_review_ok": True,
                "approved_at": _now_stamp(),
                "note": "frontend marked this cut as intentional silence",
            },
        }
    )
    audio["narration"] = narration
    node["audio"] = audio
    _write_manifest_data(manifest_path, original_text, data)
    return {"itemId": str(target["selector"]), "status": "silent_ok"}


def _narration_audio_readiness(run_dir: Path) -> dict[str, Any]:
    _manifest_path, _original_text, data = _read_manifest_data(run_dir)
    ready: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    for target in _manifest_scene_targets(data):
        selector = str(target["selector"])
        node = target["cut"]
        audio = _dict_value(node.get("audio"))
        narration = _dict_value(audio.get("narration"))
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
    tool = str(narration.get("tool") or "").strip().lower()
    silence_contract = _dict_value(narration.get("silence_contract"))
    return (
        tool == "silent"
        and silence_contract.get("intentional") is True
        and silence_contract.get("confirmed_by_human") is True
        and bool(str(silence_contract.get("kind") or "").strip())
        and bool(str(silence_contract.get("reason") or "").strip())
    )


def _append_narration_review_approved_if_ready(run_dir: Path) -> dict[str, Any]:
    readiness = _narration_audio_readiness(run_dir)
    if not readiness["ready"]:
        return readiness
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "slot.p720.status": "done",
            "slot.p720.note": "frontend narration text review completed through TTS/silent review",
            "slot.p730.status": "done",
            "slot.p730.note": "all cuts have audio files or intentional silence approvals",
            "slot.p740.status": "done",
            "slot.p740.note": "audio readiness accepted before video generation",
            "slot.p750.status": "approved",
            "slot.p750.note": "frontend audio QA cleared before p800",
            "stage.narration.status": "approved",
            "review.narration.status": "approved",
            "gate.narration_review": "cleared",
        },
    )
    return readiness


def _require_narration_ready_for_video(run_dir: Path) -> dict[str, Any]:
    readiness = _append_narration_review_approved_if_ready(run_dir)
    if readiness["ready"]:
        return readiness
    missing = ", ".join(item["itemId"] for item in readiness["missingItems"][:20])
    raise ValueError("video generation requires audio files or silent approvals for all cuts: " + (missing or "none"))


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
    candidate = _video_candidate_path(run_dir, item_id, 1)
    if candidate.is_file():
        return candidate.relative_to(run_dir).as_posix()
    return None


def _manifest_narration_items(run_dir: Path) -> list[dict[str, Any]]:
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
        raw_narration_output = str(narration.get("output") or "").strip()
        narration_output = raw_narration_output or ("" if narration_silent_ok else _default_narration_output_for_target(target))
        video_output = str(video_generation.get("output") or _default_video_output_for_target(target)).strip()
        candidate_output = _candidate_video_output_for_item(run_dir, selector)
        resolved_audio = resolve_run_relative(run_dir, narration_output) if narration_output else run_dir / "__missing_narration__"
        resolved_video = resolve_run_relative(run_dir, candidate_output or video_output)
        audio_duration = _probe_media_duration_seconds(resolved_audio)
        video_duration = _probe_media_duration_seconds(resolved_video)
        api_prompt_payload = image_generation.get("api_prompt_payload") if isinstance(image_generation.get("api_prompt_payload"), dict) else {}
        api_prompt_policy = str(api_prompt_payload.get("policy_version") or "").strip()
        api_prompt = str(api_prompt_payload.get("prompt") or "")
        legacy_prompt = str(image_generation.get("prompt") or "")
        prompt = api_prompt if api_prompt_policy == IMAGE_API_PROMPT_POLICY_VERSION else api_prompt or legacy_prompt
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
                "videoPrompt": str(video_generation.get("motion_prompt") or ""),
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
        "status": "failed" if error else "completed",
        "durationSeconds": duration_seconds,
        "error": error,
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return log_path


def _update_manifest_narration_items(run_dir: Path, items: list[NarrationGenerateItem]) -> dict[str, Any]:
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    targets_by_id: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    normalized: list[dict[str, Any]] = []
    for item in items:
        target = _target_by_item_id(data, item.item_id)
        if target is None:
            missing.append(item.item_id)
            continue
        output = item.output or _default_narration_output_for_target(target)
        _validate_run_relative_audio_path(run_dir, output, must_exist=False)
        targets_by_id[item.item_id] = target
        normalized.append({"item": item, "target": target, "output": output})
    if missing:
        raise ValueError(f"video manifest targets not found: {', '.join(missing)}")
    _backup_run_file(run_dir, "video_manifest.md", label="before_narration_generate")
    updated: list[str] = []
    for entry in normalized:
        item = entry["item"]
        target = entry["target"]
        node = target["cut"]
        audio = node.get("audio") if isinstance(node.get("audio"), dict) else {}
        narration = audio.get("narration") if isinstance(audio.get("narration"), dict) else {}
        narration.update(
            {
                "tool": item.tool,
                "text": item.text,
                "tts_text": item.tts_text or item.text,
                "output": entry["output"],
                "normalize_to_scene_duration": False,
            }
        )
        audio["narration"] = narration
        node["audio"] = audio
        updated.append(item.item_id)
    _write_manifest_data(manifest_path, original_text, data)
    return {"updated": updated, "missing": []}


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


def _mark_manifest_narration_audio_ready(run_dir: Path, results: list[dict[str, Any]]) -> list[str]:
    completed = [result for result in results if result.get("status") == "completed" and result.get("itemId")]
    if not completed:
        return []
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    updated: list[str] = []
    for result in completed:
        item_id = str(result["itemId"])
        target = _target_by_item_id(data, item_id)
        if target is None:
            continue
        node = target["cut"]
        audio = _dict_value(node.get("audio"))
        narration = _dict_value(audio.get("narration"))
        if result.get("path"):
            narration["output"] = str(result["path"])
        narration["status"] = "audio_ready"
        review = _dict_value(narration.get("review"))
        review.update(
            {
                "status": "approved",
                "human_review_ok": True,
                "approved_at": _now_stamp(),
                "note": "frontend generated and accepted this narration audio",
            }
        )
        narration["review"] = review
        if str(narration.get("tool") or "").strip().lower() == "silent":
            silence_contract = _dict_value(narration.get("silence_contract"))
            if silence_contract:
                silence_contract["confirmed_by_human"] = True
                narration["silence_contract"] = silence_contract
        audio["narration"] = narration
        node["audio"] = audio
        updated.append(str(target["selector"]))
    _write_manifest_data(manifest_path, original_text, data)
    return updated


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
        _generate_elevenlabs_audio(destination, spoken_text)
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


def _prepare_render_video_clip(run_dir: Path, source: Path, item: RenderInputItem) -> Path:
    duration = max(1, int(item.video_duration_seconds))
    if not shutil.which("ffmpeg"):
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
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return source
    return output if output.is_file() else source


def _prepare_render_narration(run_dir: Path, source: Path, item: RenderInputItem) -> Path:
    offset = max(0.0, float(item.narration_offset_seconds))
    duration = max(1.0, float(item.video_duration_seconds))
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
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
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return source
    return output if output.is_file() else source


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
    _backup_run_file(run_dir, "video_manifest.md", label="before_render_freeze")
    clips: list[Path] = []
    narrations: list[Path] = []
    warnings: list[str] = []
    updated: list[str] = []
    for item in req.items:
        target = _target_by_item_id(data, item.item_id)
        if target is None:
            raise ValueError(f"video manifest target not found: {item.item_id}")
        node = target["cut"]
        video_generation = node.get("video_generation") if isinstance(node.get("video_generation"), dict) else {}
        audio = node.get("audio") if isinstance(node.get("audio"), dict) else {}
        narration = audio.get("narration") if isinstance(audio.get("narration"), dict) else {}
        video_path = item.video_path or _candidate_video_output_for_item(run_dir, item.item_id) or str(video_generation.get("output") or "")
        narration_path = item.narration_path or str(narration.get("output") or "")
        _validate_run_relative_video_path(run_dir, video_path, must_exist=True)
        if _narration_has_confirmed_silence(narration) and not narration_path:
            narration_path = _silent_render_narration_path(run_dir, item)
            narration["output"] = narration_path
            audio["narration"] = narration
            node["audio"] = audio
        _validate_run_relative_audio_path(run_dir, narration_path, must_exist=True)
        video_source = resolve_run_relative(run_dir, video_path)
        narration_source = resolve_run_relative(run_dir, narration_path)
        audio_duration = _probe_media_duration_seconds(narration_source)
        if audio_duration is not None and item.video_duration_seconds < math.ceil(audio_duration + item.narration_offset_seconds):
            warnings.append(
                f"{item.item_id}: narration starts at {item.narration_offset_seconds:.1f}s and may exceed {item.video_duration_seconds}s clip"
            )
        render = node.get("render") if isinstance(node.get("render"), dict) else {}
        render.update(
            {
                "video_path": video_path,
                "narration_path": narration_path,
                "video_duration_seconds": item.video_duration_seconds,
                "narration_offset_seconds": item.narration_offset_seconds,
            }
        )
        node["render"] = render
        video_generation["duration_seconds"] = item.video_duration_seconds
        video_generation["output"] = video_path
        node["video_generation"] = video_generation
        clips.append(_prepare_render_video_clip(run_dir, video_source, item))
        narrations.append(_prepare_render_narration(run_dir, narration_source, item))
        updated.append(item.item_id)
    _write_manifest_data(manifest_path, original_text, data)
    if snapshot_id:
        list_dir = _frontend_review_dir(run_dir) / "render_inputs"
        list_dir.mkdir(parents=True, exist_ok=True)
        safe_snapshot = re.sub(r"[^A-Za-z0-9_.-]+", "_", snapshot_id).strip("._") or _now_stamp()
        clips_path = list_dir / f"{safe_snapshot}_video_clips.txt"
        narration_path = list_dir / f"{safe_snapshot}_video_narration_list.txt"
    else:
        clips_path = run_dir / "video_clips.txt"
        narration_path = run_dir / "video_narration_list.txt"
    clips_path.write_text("\n".join(_concat_list_line(path) for path in clips) + ("\n" if clips else ""), encoding="utf-8")
    narration_path.write_text("\n".join(_concat_list_line(path) for path in narrations) + ("\n" if narrations else ""), encoding="utf-8")
    review_dir = _frontend_review_dir(run_dir)
    review_dir.mkdir(parents=True, exist_ok=True)
    plan_path = review_dir / (f"render_plan_{safe_snapshot}.json" if snapshot_id else "render_plan_latest.json")
    plan_path.write_text(
        json.dumps(
            {
                "output": req.output,
                "clips": [str(path) for path in clips],
                "narrations": [str(path) for path in narrations],
                "items": [_model_dump(item) for item in req.items],
                "warnings": warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
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
    return {
        "runId": run_dir.name,
        "status": "frozen",
        "updated": updated,
        "warnings": warnings,
        "clipList": clips_path.relative_to(run_dir).as_posix(),
        "narrationList": narration_path.relative_to(run_dir).as_posix(),
        "planPath": plan_path.relative_to(run_dir).as_posix(),
        "output": req.output,
    }


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
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "status": "P930",
                "runtime.stage": "final_render_ready_for_qa",
                "slot.p920.status": "done",
                "slot.p920.note": "final video rendered",
                "slot.p930.status": "awaiting_approval",
                "slot.p930.note": "final QA ready in frontend",
                "artifact.final_video": str(out_path.resolve()),
                "review.final.status": "pending",
            },
        )
    return {
        **freeze_result,
        "status": "rendered",
        "finalOutput": out_path.relative_to(run_dir).as_posix(),
        "stdout": stdout.decode("utf-8", errors="replace").strip(),
    }


def _default_video_prompt(item: FrontendReviewItem) -> str:
    if item.video_prompt and item.video_prompt.strip():
        return item.video_prompt.strip()
    parts = [
        "静止画の人物・構図・光を保ったまま、自然なカメラ移動と小さな環境変化だけで動かす。",
    ]
    if item.prompt.strip():
        parts.extend(["", "シーン説明:", item.prompt.strip()])
    return "\n".join(parts).strip()


def _video_prompt_for_request(item: FrontendReviewItem) -> str:
    return _require_no_code_fence(_default_video_prompt(item), field="video_prompt")


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
        prompt = _video_prompt_for_request(item)
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
        lines.extend(["", "```text", prompt, "```", ""])
    path = _frontend_review_dir(run_dir) / "video_prompt_design.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _video_generation_request_section(run_dir: Path, item: FrontendReviewItem) -> tuple[str, str]:
    item_id = _require_markdown_scalar(item.item_id, field="item_id")
    video_tool = _require_markdown_scalar(item.video_tool or "kling_3_0", field="video_tool")
    video_quality = _require_markdown_scalar(item.video_quality or "1080p", field="video_quality")
    video_aspect_ratio = _require_markdown_scalar(item.video_aspect_ratio or "16:9", field="video_aspect_ratio")
    prompt = _video_prompt_for_request(item)
    output = _default_video_output(item)
    _require_asset_video_output(run_dir, output)
    first_frame = _default_first_frame(item)
    last_frame = (item.video_last_reference or "").strip()
    for frame in [first_frame, last_frame, *item.video_references]:
        if frame:
            _validate_run_relative_image_path(run_dir, frame, must_exist=False)
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
    ]
    if last_frame:
        lines.append(f"- last_frame: `{last_frame}`")
    lines.append("- source_cuts:")
    lines.append(f"  - `{item.item_id}`")
    refs = list(dict.fromkeys([ref for ref in item.video_references if ref.strip()]))
    if refs:
        lines.append("- references:")
        for ref in refs:
            lines.append(f"  - `{ref}`")
    lines.extend(["", "```text", prompt, "```"])
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


def _merge_video_request_sections(existing_text: str, sections_by_id: dict[str, str]) -> str:
    prefix, existing_sections = _split_video_request_sections(existing_text)
    header = "\n".join(prefix).strip() or "# Video Generation Requests"
    output_sections: list[str] = []
    used: set[str] = set()
    for title, lines in existing_sections:
        if title in sections_by_id:
            output_sections.append(sections_by_id[title])
            used.add(title)
        else:
            output_sections.append("\n".join(lines).strip())
    for title, section in sections_by_id.items():
        if title not in used:
            output_sections.append(section)
    return "\n\n".join([header, *output_sections]).rstrip() + "\n"


def _write_video_generation_requests(run_dir: Path, items: list[FrontendReviewItem], *, replace_all: bool = True) -> Path:
    _backup_run_file(run_dir, "video_generation_requests.md", label="before_video_prompt_create")
    path = run_dir / "video_generation_requests.md"
    sections_by_id = dict(_video_generation_request_section(run_dir, item) for item in items)
    if replace_all or not path.exists():
        text = "\n\n".join(["# Video Generation Requests", *sections_by_id.values()]).rstrip() + "\n"
    else:
        text = _merge_video_request_sections(path.read_text(encoding="utf-8"), sections_by_id)
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


def _storyboard_motion_prompt(scene: dict[str, Any], scene_selector: str, cuts: list[dict[str, Any]]) -> str:
    scene_intent = scene.get("scene_intent") if isinstance(scene.get("scene_intent"), dict) else {}
    scene_event = scene.get("scene_event") if isinstance(scene.get("scene_event"), dict) else {}
    lines = [
        "この1枚のストーリーボード画像を scene 全体の設計図として読み、分割された一覧画像をそのまま映すのではなく、連続した1本の映画的 scene 動画へ翻訳する。",
        "各コマは cut の順番と意味を示す。cut ごとの人物・場所・小道具・光・視線方向を保ち、scene 内の因果と感情変化が左上から右下へ自然につながるように動かす。",
        "画面内テキスト、字幕、ロゴ、パネル枠、分割画面表現を最終動画へ残さない。",
    ]
    for key in ("dramatic_question", "scene_spine", "handoff_to_next_scene", "terminal_resolution"):
        value = str(scene_intent.get(key) or "").strip()
        if value:
            lines.append(f"{key}: {value}")
    event_logline = str(scene_event.get("logline") or scene_event.get("scene_event_logline") or "").strip()
    if event_logline:
        lines.append(f"scene_event: {event_logline}")
    motion_briefs: list[str] = []
    for cut in cuts:
        video_generation = cut.get("video_generation") if isinstance(cut.get("video_generation"), dict) else {}
        cut_contract = cut.get("cut_contract") if isinstance(cut.get("cut_contract"), dict) else {}
        motion_contract = cut_contract.get("motion_contract") if isinstance(cut_contract.get("motion_contract"), dict) else {}
        motion = str(video_generation.get("motion_prompt") or motion_contract.get("motion_brief") or "").strip()
        if motion:
            motion_briefs.append(motion)
    if motion_briefs:
        lines.append("cut_motion_order:")
        for index, motion in enumerate(motion_briefs[:8], start=1):
            lines.append(f"- cut {index}: {motion}")
    lines.append(f"render_unit: {scene_selector}_unit1")
    return "\n".join(lines).strip()


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
        output = str(unit["output"])
        _validate_run_relative_image_path(run_dir, first_frame, must_exist=True)
        _require_asset_video_output(run_dir, output)
        references = [str(ref) for ref in unit.get("references", []) if str(ref).strip()]
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
                f"- storyboard_image: `{first_frame}`",
                "- source_cuts:",
            ]
        )
        lines.extend(f"  - `{source}`" for source in source_cuts)
        if references:
            lines.append("- references:")
            lines.extend(f"  - `{ref}`" for ref in references)
        lines.extend(["", "```text", _require_no_code_fence(str(unit["motion_prompt"]), field="motion_prompt"), "```", ""])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def _materialize_scene_storyboard_video_requests(run_id: str) -> dict[str, Any]:
    run_dir = safe_run_dir(run_id, ROOT)
    manifest_path, original_text, data = _read_manifest_data(run_dir)
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        raise RuntimeError("storyboard create failed: video_manifest.md scenes must be a list")

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
        duration_seconds = 0
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
            duration_seconds += _storyboard_cut_duration(cut)
        if not cut_outputs:
            raise RuntimeError(f"storyboard create failed: {scene_selector} has no active cut images")
        storyboard_output = f"assets/storyboards/{scene_selector}_storyboard.png"
        _compose_storyboard_image(run_dir, inputs=cut_outputs, output=storyboard_output)
        unit_id = "1"
        request_id = f"{scene_selector}_unit1"
        video_output = f"assets/scenes/{scene_selector}/{request_id}.mp4"
        motion_prompt = _storyboard_motion_prompt(scene, scene_selector, active_cuts)
        video_duration_seconds = min(max(1, duration_seconds), VIDEO_GENERATION_DURATION_MAX_SECONDS)
        video_generation = {
            "tool": "kling_3_0_omni",
            "duration_seconds": video_duration_seconds,
            "first_frame": storyboard_output,
            "input_image": storyboard_output,
            "references": [storyboard_output],
            "motion_prompt": motion_prompt,
            "output": video_output,
            "quality": "1080p",
            "aspect_ratio": "16:9",
        }
        scene["render_units"] = [
            {
                "unit_id": unit_id,
                "source_cut_ids": source_cut_ids,
                "storyboard_image": storyboard_output,
                "video_generation": video_generation,
            }
        ]
        units.append(
            {
                "unit_id": unit_id,
                "request_id": request_id,
                "source_cuts": source_cut_ids,
                "first_frame": storyboard_output,
                "references": [storyboard_output],
                "motion_prompt": motion_prompt,
                "output": video_output,
                "duration_seconds": video_duration_seconds,
                "tool": video_generation["tool"],
            }
        )
        storyboard_paths.append(storyboard_output)

    if not units:
        raise RuntimeError("storyboard create failed: no scene storyboard units were created")

    _backup_run_file(run_dir, "video_manifest.md", label="before_scene_storyboard_create")
    _write_manifest_data(manifest_path, original_text, data)
    request_path = _write_scene_storyboard_video_generation_requests(run_dir, units)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "runtime.create_mode": CREATE_MODE_SCENE_STORYBOARD,
            "runtime.stage": "scene_storyboard_video_requests_ready",
            "review.frontend.storyboard.status": "ready",
            "review.video_prompt.status": "pending",
            "gate.video_prompt_review": "required",
            "artifact.scene_storyboards": ",".join(storyboard_paths),
            "artifact.video_generation_requests": str(request_path.resolve()),
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
        if not isinstance(render_units, list) or len(render_units) != 1:
            raise RuntimeError(f"storyboard create incomplete: {scene_selector} must have one render_unit")
        unit = render_units[0]
        if not isinstance(unit, dict):
            raise RuntimeError(f"storyboard create incomplete: {scene_selector} render_unit is invalid")
        unit_id = str(unit.get("unit_id") or "").strip()
        normalized_unit_id = normalize_dotted_id(unit_id)
        storyboard = str(unit.get("storyboard_image") or "").strip()
        video_generation = unit.get("video_generation") if isinstance(unit.get("video_generation"), dict) else {}
        first_frame = str(video_generation.get("first_frame") or video_generation.get("input_image") or "").strip()
        if not unit_id or not storyboard or first_frame != storyboard:
            raise RuntimeError(f"storyboard create incomplete: {scene_selector} render_unit is missing storyboard video input")
        _validate_run_relative_image_path(run_dir, storyboard, must_exist=True)
        if not isinstance(unit.get("source_cut_ids"), list) or not unit.get("source_cut_ids"):
            raise RuntimeError(f"storyboard create incomplete: {scene_selector} render_unit has no source_cut_ids")
        if normalized_unit_id is None:
            raise RuntimeError(f"storyboard create incomplete: {scene_selector} render_unit has invalid unit_id")
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
        target = _target_by_item_id(data, item.item_id)
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
        output = _default_video_output(item)
        _require_asset_video_output(run_dir, output)
        video_generation.update(
            {
                "tool": item.video_tool or video_generation.get("tool") or "kling_3_0",
                "duration_seconds": item.video_duration_seconds or video_generation.get("duration_seconds") or 8,
                "first_frame": _default_first_frame(item),
                "motion_prompt": _video_prompt_for_request(item),
                "output": output,
                "quality": item.video_quality or video_generation.get("quality") or "1080p",
                "aspect_ratio": item.video_aspect_ratio or video_generation.get("aspect_ratio") or "16:9",
            }
        )
        if item.video_last_reference:
            video_generation["last_frame"] = item.video_last_reference
        elif "last_frame" in video_generation:
            video_generation.pop("last_frame", None)
        if item.video_references:
            video_generation["references"] = list(dict.fromkeys(item.video_references))
        node["video_generation"] = video_generation
        updated.append(item.item_id)
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
    existing_aliases = {alias for target_info in _manifest_scene_targets(data) for alias in target_info["aliases"]}
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
        for ref in getattr(item, "references", []) or []:
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
            for ref in getattr(item, "references", []) or []:
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


def _has_completed_app_server_image_provenance(run_dir: Path, *, item_id: str, destination: Path) -> bool:
    log_dir = run_dir / "logs" / "app_server" / "image_gen"
    if not log_dir.exists():
        return False
    destination_key = _run_relative_key(run_dir, str(destination))
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
        source = str(payload.get("source") or "").lower()
        if "local_raster" in source:
            continue
        return True
    return False


async def _generate_request_item_output(*, run_dir: Path, kind: str, item: Any) -> None:
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
    if destination.exists():
        if _has_completed_app_server_image_provenance(run_dir, item_id=str(item.id), destination=destination):
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
        destination.unlink()
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="request_item_generation",
            status="retrying",
            item_id=str(item.id),
            request={
                "kind": kind,
                "reason": "removed existing destination without completed app-server provenance",
                "output": str(item.output),
                "destination": str(destination),
            },
        )
    started = time.monotonic()
    generation_job_id = uuid.uuid4().hex
    provenance_policy = _image_generation_provenance_policy()
    allow_generated_images_fallback = provenance_policy != IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2
    references: list[Path] = []
    for ref in getattr(item, "references", []) or []:
        reference = resolve_run_relative(run_dir, str(ref))
        if not reference.exists() or not reference.is_file():
            raise RuntimeError(f"{kind} reference not found for {item.id}: {ref}")
        require_image_file(reference)
        references.append(reference)
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
            "executionLane": str(getattr(item, "execution_lane", "") or ""),
            "assetType": str(getattr(item, "asset_type", "") or ""),
            "timeoutSeconds": IMAGE_GENERATION_ITEM_TIMEOUT_SECONDS,
            "maxAttempts": IMAGE_GENERATION_ITEM_MAX_ATTEMPTS,
            "generationJobId": generation_job_id,
            "provenancePolicy": provenance_policy,
            "allowGeneratedImagesFallback": allow_generated_images_fallback,
        },
    )
    client = create_codex_app_server_client(cwd=ROOT)
    result = None
    debug_log = None
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
                        timeout=IMAGE_GENERATION_ITEM_TIMEOUT_SECONDS,
                    )
                    if result.saved_path is None:
                        raise RuntimeError(f"Codex app-server did not return an image for {item.id}")
                    reject_local_raster_image_result(result, item_id=item.id)
                    if provenance_policy == IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2 and not bool(getattr(result, "provenance_authoritative", False)):
                        raise RuntimeError(f"Codex app-server did not return authoritative request-bound provenance for {item.id}")
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
            result=result,
        )
        if result.saved_path is None:
            raise RuntimeError(f"Codex app-server did not return an image for {item.id}; see {debug_log}")
        copy_saved_image(result.saved_path, destination)
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
                "generationJobId": generation_job_id,
                "turnId": getattr(result, "turn_id", None),
                "provenancePolicy": provenance_policy,
                "provenanceAuthoritative": bool(getattr(result, "provenance_authoritative", False)),
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
    async with _serialized_run_write(run_dir, f"{kind}_generation"):
        await _generate_request_outputs_unlocked(run_dir=run_dir, kind=kind)


async def _generate_request_outputs_unlocked(*, run_dir: Path, kind: str) -> None:
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
    for item in load_request_items(run_dir, kind):
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
    await _set_create_job(job_id, {"message": "シーン画像を生成中"})
    await _generate_request_outputs(run_dir=run_dir, kind="scene")
    if semantic_failures:
        failure_updates = {
            "runtime.stage": "semantic_review_failed_after_media_generation",
            "slot.p660.status": "done",
            "slot.p660.note": "scene images generated; semantic gate still failed",
            "slot.p670.status": "skipped",
            "slot.p670.note": "scene image semantic QA removed; upstream semantic QA failed",
            "slot.p680.status": "pending",
            "review.image.status": "needs_semantic_review",
            "review.semantic.create_media_generated": "true",
            "review.semantic.create_failure_count": str(len(semantic_failures)),
            "review.semantic.create_failures": " | ".join(semantic_failures)[:2000],
        }
        for stage in sorted(failed_semantic_stages):
            slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
            if slot:
                failure_updates[f"slot.{slot}.status"] = "failed"
                failure_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} review failed; media generated but p680 is blocked"
        append_state_snapshot(
            run_dir / "state.txt",
            failure_updates,
        )
        raise RuntimeError("semantic review failed after media generation: " + " | ".join(semantic_failures))
    _mark_image_generation_review_ready(run_id)
    return asset_quality_passed


async def _run_image_prompt_semantic_review(job_id: str, *, run_dir: Path) -> None:
    await _run_semantic_review(job_id, run_dir=run_dir, stage="image_prompt")


async def _run_semantic_review_for_media_generation(job_id: str, *, run_dir: Path, stage: str) -> str | None:
    try:
        await _run_semantic_review(job_id, run_dir=run_dir, stage=stage)
        return None
    except Exception as exc:
        if is_codex_transport_error(exc):
            transport_kind = classify_codex_transport_error(str(exc)) or "unknown"
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    f"review.semantic.{stage}.transport.status": "failed",
                    f"review.semantic.{stage}.transport.error_kind": transport_kind,
                    f"review.semantic.{stage}.transport.error": str(exc)[:2000],
                    f"review.semantic.{stage}.loop.status": "blocked_transport",
                    "runtime.stage": "app_server_transport_failed",
                    "runtime.app_server.transport.status": "failed",
                    "runtime.app_server.transport.error_kind": transport_kind,
                },
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
            }
        )
        state_updates.update(_semantic_review_failure_state(run_dir, stage))
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
    "scene_set": "p410",
    "scene_detail": "p410",
    "cut_blueprint": "p420",
    "asset_plan": "p540",
    "image_prompt": "p640",
    "narration": "p720",
    "video_motion": "p820",
}


async def _run_semantic_review(job_id: str, *, run_dir: Path, stage: str, max_attempts: int | None = None) -> None:
    attempts = max(1, max_attempts or semantic_review_max_attempts())
    reusable_result = _reusable_passed_semantic_review(run_dir, stage)
    if reusable_result is not None:
        _record_reused_semantic_review(run_dir, stage, reusable_result, max_attempts=attempts)
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
    if last_result is not None and not last_result.passed:
        raise RuntimeError(f"{stage} semantic review failed: " + "; ".join(last_result.errors))


def _reusable_passed_semantic_review(run_dir: Path, stage: str) -> SemanticReviewStatus | None:
    if os.environ.get("TOC_SEMANTIC_REVIEW_REUSE_PASSED", "1").strip().lower() in {"0", "false", "no"}:
        return None
    result = check_image_prompt_judgment(run_dir) if stage == "image_prompt" else check_semantic_review(run_dir, stage)
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
    last_progress_at = time.monotonic()
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
                last_progress_at = time.monotonic()
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        f"review.semantic.{stage}.watchdog.status": "progress_observed",
                        f"review.semantic.{stage}.watchdog.operation": operation,
                        f"review.semantic.{stage}.watchdog.last_progress_at": now_iso(),
                        f"review.semantic.{stage}.watchdog.fingerprint": _json_hash(current_fingerprint),
                    },
                )
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
                append_state_snapshot(run_dir / "state.txt", pending_state(time.monotonic() - started_at))
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
    result = check_image_prompt_judgment(run_dir) if stage == "image_prompt" else check_semantic_review(run_dir, stage)
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
    return (
        prompt.rstrip()
        + "\n\n"
        + f"{marker}\n\n"
        + f"This is the final semantic review attempt for `{stage}`. If this report is `failed`, the project run will stop before downstream generation.\n"
        + "Use `status: passed` unless you find a fatal defect that would break the story meaning, source identity, reveal order, safety, or the next downstream stage.\n"
        + "Treat non-fatal polish issues, minor wording weakness, and repairable prompt-strengthening suggestions as notes rather than blockers.\n"
        + "If you pass with reservations, include the reservations in `notes` and keep `blocked_entries` and `failed_selectors` empty.\n"
    )


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
                "Gate this scene_detail entry on scene necessity, internal pressure, value_shift visibility, causal_turn visibility, scene_event sequence, turning_event/end_situation alignment, cut summary support, reveal order, and neighbor handoff.",
                "Do not require a fixed cut count. Judge whether this scene's actual visual obligations are sufficiently represented by its cut summaries and contracts.",
                "Do not fail solely because generated image/video/audio files do not exist yet.",
                "",
                "Report format:",
                "status: passed|failed",
                "reviewed_entries: [...]",
                "blocked_entries: [...]",
                "findings: [...]",
                "failed_selectors: [...]",
                "reason_keys: [semantic_subject_mismatch|semantic_location_mismatch|semantic_timeline_mismatch|semantic_reveal_order_mismatch|scene_detail_obligation_missing|scene_detail_cut_support_weak|scene_detail_handoff_weak|...]",
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
    elif "semantic review failed after media generation" in normalized_lower:
        prefix = "semantic QA に失敗しました。asset/scene 画像生成は実行済みですが p680 承認には進めません"
    elif "semantic review failed" in normalized_lower:
        prefix = "semantic QA に失敗しました"
    elif "transport failure" in normalized_lower or "blocked by codex app-server transport" in normalized_lower:
        prefix = "Codex app-server の通信確認に失敗したため semantic QA を実行できませんでした"
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


async def _run_create_job(
    job_id: str,
    *,
    title: str,
    source: str,
    run_id: str,
    generate_images: bool = True,
    create_mode: str = CREATE_MODE_NORMAL,
    stop_target: str = "p680",
) -> None:
    if stop_target not in CREATE_STOP_TARGETS:
        raise ValueError("stop_target must be p650 or p680")
    run_dir_for_log = safe_run_dir(run_id, ROOT)
    job_started = time.monotonic()
    try:
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
            },
        )
        if generate_images:
            await _set_create_job(job_id, {"message": f"本家ToC工程を{stop_target}まで実行中", "stopTarget": stop_target, "currentProcess": "p000"})
            await _run_toc_immersive_frontend_cli_helper(
                topic=title,
                source=source,
                run_id=run_id,
                stop_target=stop_target,
            )
        else:
            await _set_create_job(job_id, {"message": f"本家ToC工程を画像生成なしで{stop_target}まで実行中", "stopTarget": stop_target, "currentProcess": "p000"})
            await _run_toc_immersive_frontend_cli_helper(
                topic=title,
                source=source,
                run_id=run_id,
                stop_target=stop_target,
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
            request={"step": "frontend_create_cli", "runId": run_id, "createMode": create_mode, "stopTarget": stop_target},
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
                request={"runId": run_id, "title": title, "sourceLength": len(source), "createMode": create_mode, "stopTarget": stop_target},
                response={"elapsedMs": int((time.monotonic() - job_started) * 1000)},
                error=f"{type(exc).__name__}: {exc}",
            )
            if (run_dir / "state.txt").exists():
                append_state_snapshot(
                    run_dir / "state.txt",
                    {
                        "status": "FAILED",
                        "runtime.stage": "create_run_failed",
                        "runtime.create_job.status": "failed",
                        "runtime.create_job.error_code": type(exc).__name__,
                        "runtime.create_job.stop_target": stop_target,
                        "last_error": detail,
                    },
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
    job_id = uuid.uuid4().hex
    job = {
        "jobId": job_id,
        "runId": run_id,
        "path": f"output/{run_id}",
        "status": "running",
        "title": title,
        "createMode": create_mode,
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
    deleted_images: dict[str, Any] | None = None
    if req.stop_target == "p680" and current_process_number >= 650:
        deleted_images = await asyncio.to_thread(_delete_existing_images_for_image_resume, run_dir)
        await _set_create_job(
            job_id,
            {
                "message": f"{current_process}から{req.stop_target}へ再開中: 既存画像を削除しました",
                "metadata": {
                    "resumeFromProcessNumber": current_process_number,
                    "deletedImagesCount": deleted_images.get("deletedCount", 0),
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
            "deletedImages": deleted_images,
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
        )
    )
    return job


@router.get("/api/image-gen/requests")
async def api_requests(run_id: str, kind: str = Query(pattern="^(asset|scene)$")) -> dict[str, Any]:
    run_dir = safe_run_dir(run_id, ROOT)
    items = []
    for item in load_request_items(run_dir, kind):
        payload = item_to_api(item)
        payload["candidates"] = list_candidate_items(run_dir, item.id)
        items.append(payload)
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
        items = _manifest_narration_items(run_dir)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "run": {"id": run_id, "path": f"output/{run_id}"},
        "items": items,
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
            manifest_path = run_dir / "video_manifest.md"
            request_path = run_dir / "image_generation_requests.md"
            manifest_before = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else None
            request_before = request_path.read_text(encoding="utf-8") if request_path.exists() else None
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
                    },
                )
            except (FileNotFoundError, RuntimeError, ValueError):
                if manifest_before is not None:
                    manifest_path.write_text(manifest_before, encoding="utf-8")
                if request_before is not None:
                    request_path.write_text(request_before, encoding="utf-8")
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


@router.post("/api/image-gen/video-prompts/create")
async def api_create_video_prompts(req: VideoPromptCreateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            review_path = _write_frontend_review_draft(
                run_id=req.run_id,
                run_dir=run_dir,
                kind="video",
                note=req.note,
                items=req.items,
                state_status="saved_for_video_prompt",
            )
            design_path = _write_video_prompt_design(run_dir=run_dir, review_path=review_path, items=req.items)
            manifest_update = _update_manifest_video_generation(run_dir, req.items)
            request_path = _write_video_generation_requests(run_dir, req.items, replace_all=req.replace_all)
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    "status": "P830",
                    "runtime.stage": "video_prompts_ready_for_review",
                    "slot.p810.status": "done",
                    "slot.p810.note": "frontend image review saved before video prompt creation",
                    "slot.p820.status": "done",
                    "slot.p820.note": "video prompts created from frontend settings",
                    "slot.p830.status": "awaiting_approval",
                    "slot.p830.note": "video generation requests await human review",
                    "stage.video_generation.status": "awaiting_approval",
                    "review.video_prompt.status": "pending",
                    "gate.video_prompt_review": "required",
                    "artifact.video_generation_requests": str(request_path.resolve()),
                    "review.frontend.video_prompt.design": design_path.relative_to(run_dir).as_posix(),
                },
            )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "runId": req.run_id,
        "status": "completed",
        "reviewPath": review_path.relative_to(run_dir).as_posix(),
        "designPath": design_path.relative_to(run_dir).as_posix(),
        "videoRequestsPath": request_path.relative_to(run_dir).as_posix(),
        "updated": manifest_update["updated"],
        "missing": manifest_update["missing"],
        "progress": read_run_progress(run_dir),
    }


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
async def api_candidates(run_id: str, item_id: str = Query(min_length=1, max_length=200)) -> dict[str, Any]:
    run_dir = safe_run_dir(run_id, ROOT)
    return {"itemId": item_id, "candidates": list_candidate_items(run_dir, item_id)}


@router.post("/api/image-gen/narration-drafts/create")
async def api_create_narration_drafts(req: NarrationDraftCreateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            result = _create_narration_drafts_in_manifest(run_dir, replace=req.replace)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "runId": req.run_id,
        "status": "completed",
        **result,
        "progress": read_run_progress(run_dir),
    }


@router.post("/api/image-gen/narration-silent-ok")
async def api_narration_silent_ok(req: NarrationSilentOkRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            result = _narration_silent_ok(run_dir, item_id=req.item_id, reason=req.reason)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "runId": req.run_id,
        **result,
        "progress": read_run_progress(run_dir),
    }


@router.post("/api/image-gen/narration-generate")
async def api_narration_generate(req: NarrationGenerateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    item = NarrationGenerateItem.model_validate(req.model_dump(exclude={"run_id"}))
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            update_result = _update_manifest_narration_items(run_dir, [item])
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = await _generate_narration_one(run_dir, item)
    durations = {result["itemId"]: float(result["durationSeconds"])} if result.get("durationSeconds") else {}
    async with _serialized_run_write(run_dir, "run_artifacts"):
        audio_ready_updates = _mark_manifest_narration_audio_ready(run_dir, [result])
        duration_updates = _apply_audio_duration_to_manifest(run_dir, durations)
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "status": "P750" if result.get("status") == "completed" else "P730",
                "runtime.stage": "narration_audio_frontend_review_in_progress" if result.get("status") == "completed" else "narration_generation_failed",
                "slot.p710.status": "done",
                "slot.p710.note": "frontend narration grounding loaded from video_manifest",
                "slot.p720.status": "done" if result.get("status") == "completed" else "awaiting_approval",
                "slot.p720.note": "frontend narration text reviewed through TTS generation",
                "slot.p730.status": "done" if result.get("status") == "completed" else "failed",
                "slot.p730.note": "narration audio generated from frontend",
                "slot.p740.status": "done" if duration_updates or result.get("status") == "completed" else "pending",
                "slot.p740.note": "video duration minimum synced from generated narration",
                "slot.p750.status": "awaiting_approval" if result.get("status") == "completed" else "pending",
                "slot.p750.note": "narration audio review is complete per-cut when every cut has audio or silent ok",
            },
        )
    return {
        "runId": req.run_id,
        "status": result.get("status"),
        "updated": update_result["updated"],
        "audioReadyUpdated": audio_ready_updates,
        "durationUpdated": duration_updates,
        "item": result,
        "progress": read_run_progress(run_dir),
    }


@router.post("/api/image-gen/narration-generate-bulk")
async def api_narration_generate_bulk(req: BulkNarrationGenerateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            update_result = _update_manifest_narration_items(run_dir, req.items)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    semaphore = asyncio.Semaphore(req.concurrency)

    async def guarded(item: NarrationGenerateItem) -> dict[str, Any]:
        async with semaphore:
            return await _generate_narration_one(run_dir, item)

    results = await asyncio.gather(*(guarded(item) for item in req.items))
    durations = {str(result["itemId"]): float(result["durationSeconds"]) for result in results if result.get("durationSeconds")}
    failed = [result for result in results if result.get("status") != "completed"]
    async with _serialized_run_write(run_dir, "run_artifacts"):
        audio_ready_updates = _mark_manifest_narration_audio_ready(run_dir, results)
        duration_updates = _apply_audio_duration_to_manifest(run_dir, durations)
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "status": "P750" if not failed else "P730",
                "runtime.stage": "narration_audio_frontend_review_in_progress" if not failed else "narration_generation_partial_failure",
                "slot.p710.status": "done",
                "slot.p710.note": "frontend narration grounding loaded from video_manifest",
                "slot.p720.status": "done",
                "slot.p720.note": "frontend narration text reviewed through TTS generation",
                "slot.p730.status": "done" if not failed else "failed",
                "slot.p730.note": f"generated {len(results) - len(failed)}/{len(results)} narration files",
                "slot.p740.status": "done" if durations else "pending",
                "slot.p740.note": "video duration minimum synced from generated narration",
                "slot.p750.status": "awaiting_approval" if not failed else "pending",
                "slot.p750.note": "narration audio review is complete when every cut has audio or silent ok",
            },
        )
    return {
        "runId": req.run_id,
        "status": "completed" if not failed else "partial_failure",
        "updated": update_result["updated"],
        "audioReadyUpdated": audio_ready_updates,
        "durationUpdated": duration_updates,
        "results": results,
        "progress": read_run_progress(run_dir),
    }


@router.post("/api/image-gen/video-generate")
async def api_video_generate(req: VideoGenerateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    item = VideoGenerateItem.model_validate(req.model_dump(exclude={"run_id"}))
    _validate_video_request_reference_paths(run_dir, item)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            _require_narration_ready_for_video(run_dir)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return await _generate_video_candidates(run_dir, item)


@router.post("/api/image-gen/video-generate-bulk")
async def api_video_generate_bulk(req: BulkVideoGenerateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    for item in req.items:
        _validate_video_request_reference_paths(run_dir, item)
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            _require_narration_ready_for_video(run_dir)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    total_candidates = sum(item.candidate_count for item in req.items)
    if total_candidates > 96:
        raise HTTPException(status_code=400, detail="bulk video generation is limited to 96 total candidates")
    semaphore = asyncio.Semaphore(req.concurrency)

    async def guarded(item: VideoGenerateItem) -> dict[str, Any]:
        async with semaphore:
            return await _generate_video_candidates(run_dir, item)

    results = await asyncio.gather(*(guarded(item) for item in req.items), return_exceptions=True)
    payload = []
    for item, result in zip(req.items, results, strict=False):
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
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {**result, "runId": req.run_id, "progress": read_run_progress(run_dir)}


async def _generate_one(run_dir: Path, req: GenerateRequest, index: int) -> dict[str, Any]:
    if not req.prompt.strip():
        detail = (
            "api_prompt_missing_for_new_prompt_policy"
            if req.prompt_policy_version == IMAGE_API_PROMPT_POLICY_VERSION
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
    async with _generation_semaphore:
        client = create_codex_app_server_client(cwd=ROOT)
        result = None
        debug_log = None
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
            )
            reject_local_raster_image_result(result, item_id=req.item_id)
            if (
                result.saved_path is not None
                and provenance_policy == IMAGE_GENERATION_PROVENANCE_POLICY_REQUEST_BOUND_V2
                and not bool(getattr(result, "provenance_authoritative", False))
            ):
                raise RuntimeError(f"Codex app-server did not return authoritative request-bound provenance for {req.item_id}")
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
    copy_saved_image(result.saved_path, destination)
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
    }


@router.post("/api/image-gen/generate")
async def api_generate(req: GenerateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    candidates = await asyncio.gather(*(_generate_one(run_dir, req, index) for index in range(1, req.candidate_count + 1)))
    return {"itemId": req.item_id, "candidates": candidates}


@router.post("/api/image-gen/generate-bulk")
async def api_generate_bulk(req: BulkGenerateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    total_candidates = sum(item.candidate_count for item in req.items)
    if total_candidates > 100:
        raise HTTPException(status_code=400, detail="bulk generation is limited to 100 total candidates")
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
    semaphore = asyncio.Semaphore(req.concurrency)

    async def regenerate_one(item: Any) -> dict[str, Any]:
        async with semaphore:
            client = create_codex_app_server_client(cwd=ROOT)
            try:
                await _start_app_server_with_log(client, run_dir=run_dir, operation="prompt_regeneration", item_id=item.id)
                prompt = await _regenerate_prompt_with_log(
                    client,
                    run_dir=run_dir,
                    item=item_to_api(item),
                    target=req.target,
                    instruction=req.instruction,
                    setting_content=setting["content"],
                    operation="prompt_regeneration",
                )
                return {"itemId": item.id, "prompt": prompt}
            finally:
                await client.stop()

    results = await asyncio.gather(*(regenerate_one(item) for item in items), return_exceptions=True)
    failures: list[dict[str, str]] = []
    prompts: dict[str, str] = {}
    for item, result in zip(items, results, strict=False):
        if isinstance(result, Exception):
            failures.append({"itemId": item.id, "error": str(result)})
        else:
            prompts[str(result["itemId"])] = str(result["prompt"])
    if failures:
        raise HTTPException(status_code=500, detail={"status": "failed", "failures": failures})
    try:
        async with _serialized_run_write(run_dir, "run_artifacts"):
            update_result = update_request_prompts(run_dir, kind, prompts)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if update_result["missing"]:
        raise HTTPException(status_code=400, detail={"missingPromptSections": update_result["missing"]})
    return {
        "runId": req.run_id,
        "target": req.target,
        "kind": kind,
        "status": "completed",
        "prompts": [{"itemId": item_id, "prompt": prompt} for item_id, prompt in prompts.items()],
        "updated": update_result["updated"],
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
