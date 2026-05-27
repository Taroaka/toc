from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
import fcntl
import json
import math
import os
import re
import time
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable

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
from toc.harness import append_state_snapshot, parse_state_file
from toc.providers.kling import KlingClient, KlingConfig
from toc.providers.seedance import SeedanceClient, SeedanceConfig
from toc.semantic_review import (
    IMAGE_PROMPT_JUDGMENT_REPORT,
    SemanticReviewStatus,
    check_semantic_review,
    check_image_prompt_judgment,
    review_status_to_state,
    semantic_state_updates,
    semantic_review_relpaths,
)
from toc.semantic_review_loop import (
    semantic_loop_state_updates,
    semantic_repair_state_updates,
    semantic_repair_timeout_seconds,
    semantic_review_max_attempts,
    write_semantic_repair_prompt,
)
from toc.tts_text import load_pronunciation_aliases, prepare_elevenlabs_tts_text
from .image_gen import (
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
BOOTSTRAP_ASSET_MAX_ATTEMPTS = 10
IMAGE_GENERATION_PARALLELISM = max(1, int(os.environ.get("TOC_IMAGE_GEN_PARALLELISM", "4") or "4"))
IMAGE_GENERATION_ITEM_MAX_ATTEMPTS = max(1, int(os.environ.get("TOC_IMAGE_GEN_ITEM_MAX_ATTEMPTS", "3") or "3"))
IMAGE_GENERATION_ITEM_TIMEOUT_SECONDS = max(
    1.0,
    float(os.environ.get("TOC_IMAGE_GEN_ITEM_TIMEOUT_SECONDS", "300") or "300"),
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
    prompt: str = Field(min_length=1, max_length=20000)
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
    video_duration_seconds: int | None = Field(default=None, ge=1, le=60)
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


class VideoGenerateItem(BaseModel):
    item_id: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=40000)
    first_reference: str | None = Field(default=None, max_length=500)
    last_reference: str | None = Field(default=None, max_length=500)
    references: list[str] = Field(default_factory=list, max_length=32)
    quality: str = Field(default="1080p", pattern="^(720p|1080p|4K)$")
    aspect_ratio: str = Field(default="16:9", pattern="^(16:9|9:16|1:1|4:3)$")
    duration_seconds: int = Field(default=8, ge=1, le=60)
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
_run_write_locks: dict[tuple[str, str], asyncio.Lock] = {}
_run_write_locks_guard = asyncio.Lock()
MAX_ZIP_BYTES = 250 * 1024 * 1024
MAX_CREATE_JOBS = 64
MAX_RUNNING_CREATE_JOBS = 2


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
    if require_semantic_reviews:
        _validate_semantic_reviews(run_dir, ("asset_output",))

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
    _validate_semantic_reviews(run_dir, ("scene_set", "scene_detail", "cut_blueprint", "asset_plan", "asset_output", "image_prompt", "scene_image"))
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


async def _run_toc_run_helper(*, topic: str, run_id: str) -> str:
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
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=1800)
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
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=7200)
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
            timeout_seconds=7200,
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
        narration_output = str(narration.get("output") or _default_narration_output_for_target(target)).strip()
        video_output = str(video_generation.get("output") or _default_video_output_for_target(target)).strip()
        candidate_output = _candidate_video_output_for_item(run_dir, selector)
        resolved_audio = resolve_run_relative(run_dir, narration_output)
        resolved_video = resolve_run_relative(run_dir, candidate_output or video_output)
        audio_duration = _probe_media_duration_seconds(resolved_audio)
        video_duration = _probe_media_duration_seconds(resolved_video)
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
                "narrationOutput": narration_output,
                "narrationTool": str(narration.get("tool") or "elevenlabs"),
                "narrationExists": resolved_audio.is_file(),
                "narrationDurationSeconds": audio_duration,
                "renderNarrationOffsetSeconds": float(
                    render.get("narration_offset_seconds")
                    or render.get("narration_start_seconds")
                    or 0
                ),
                "prompt": str(image_generation.get("prompt") or ""),
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
        },
    )
    client = create_codex_app_server_client(cwd=ROOT)
    result = None
    debug_log = None
    try:
        await client.start()
        generated_root = client.generated_images_root() if hasattr(client, "generated_images_root") else None
        async with _generated_images_cutoff_lock:
            fallback_cutoff_ns = latest_generated_image_mtime_ns(generated_root)
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
                        timeout_seconds=max(1, int(IMAGE_GENERATION_ITEM_TIMEOUT_SECONDS)),
                    ),
                    timeout=IMAGE_GENERATION_ITEM_TIMEOUT_SECONDS,
                )
                if result.saved_path is None:
                    raise RuntimeError(f"Codex app-server did not return an image for {item.id}")
                break
            except Exception as exc:
                if attempt >= IMAGE_GENERATION_ITEM_MAX_ATTEMPTS or not _is_transient_codex_image_error(exc):
                    raise
                write_app_server_debug_log(
                    run_dir=run_dir,
                    operation="request_item_generation_retry",
                    status="retrying",
                    item_id=str(item.id),
                    request={"kind": kind, "output": str(item.output), "attempt": attempt},
                    response=_codex_failure_context(exc, client=client),
                    error=f"{type(exc).__name__}: {exc}",
                )
                await client.stop()
                client = create_codex_app_server_client(cwd=ROOT)
                await client.start()
        debug_log = write_app_server_image_debug_log(
            run_dir=run_dir,
            item_id=item.id,
            index=1,
            destination=destination,
            references=references,
            prompt=item.prompt,
            kind=kind,
            result=result,
        )
        reject_local_raster_image_result(result, item_id=item.id)
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
                "source": result.source,
                "destinationExists": destination.exists(),
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
    write_app_server_debug_log(
        run_dir=run_dir,
        operation="request_generation_batch",
        status="started",
        item_id=kind,
        request={
            "kind": kind,
            "itemCount": len(items),
            "groupCount": len(groups),
            "parallelism": IMAGE_GENERATION_PARALLELISM,
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
    semaphore = asyncio.Semaphore(IMAGE_GENERATION_PARALLELISM)
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
        request={"kind": kind, "itemCount": len(items), "groupCount": len(groups)},
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
            "slot.p670.status": "done",
            "slot.p670.note": "scene image semantic QA passed; frontend human review is next",
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
    await _set_create_job(job_id, {"message": "素材出力をsemantic QA中"})
    failure = await _run_semantic_review_for_media_generation(job_id, run_dir=run_dir, stage="asset_output")
    if failure:
        semantic_failures.append(failure)
        failed_semantic_stages.add("asset_output")
    await _set_create_job(job_id, {"message": "画像プロンプトをsemantic QA中"})
    failure = await _run_semantic_review_for_media_generation(job_id, run_dir=run_dir, stage="image_prompt")
    if failure:
        semantic_failures.append(failure)
        failed_semantic_stages.add("image_prompt")
    await _set_create_job(job_id, {"message": "シーン画像を生成中"})
    await _generate_request_outputs(run_dir=run_dir, kind="scene")
    await _set_create_job(job_id, {"message": "シーン画像出力をsemantic QA中"})
    failure = await _run_semantic_review_for_media_generation(job_id, run_dir=run_dir, stage="scene_image")
    if failure:
        semantic_failures.append(failure)
        failed_semantic_stages.add("scene_image")
    if semantic_failures:
        failure_updates = {
            "runtime.stage": "semantic_review_failed_after_media_generation",
            "slot.p660.status": "done",
            "slot.p660.note": "scene images generated; semantic gate still failed",
            "slot.p670.status": "failed",
            "slot.p670.note": "scene image semantic QA or upstream semantic QA failed",
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
            raise RuntimeError(f"{stage} semantic review blocked by Codex app-server transport failure: {exc}") from exc
        message = f"{stage}: {type(exc).__name__}: {exc}"
        state_updates = semantic_state_updates(
            stage,
            status="failed",
            entry_count=None,
            error_count=1,
        )
        slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
        if slot:
            state_updates[f"slot.{slot}.status"] = "failed"
            state_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} review failed; media generation continued"
        state_updates[f"review.semantic.{stage}.last_error"] = str(exc)[:2000]
        append_state_snapshot(run_dir / "state.txt", state_updates)
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="semantic_review",
            status="failed_nonblocking_for_media_generation",
            item_id=job_id,
            request={"stage": stage},
            response={"failureContext": _codex_failure_context(exc)},
            error=message,
        )
        return message


SEMANTIC_REVIEW_SLOT_BY_STAGE = {
    "scene_set": "p410",
    "scene_detail": "p410",
    "cut_blueprint": "p420",
    "asset_plan": "p540",
    "asset_output": "p570",
    "image_prompt": "p640",
    "scene_image": "p670",
    "narration": "p720",
    "video_motion": "p820",
    "video_clip": "p850",
    "render": "p930",
}


async def _run_semantic_review(job_id: str, *, run_dir: Path, stage: str, max_attempts: int | None = None) -> None:
    attempts = max(1, max_attempts or semantic_review_max_attempts())
    last_result: SemanticReviewStatus | None = None
    for attempt in range(1, attempts + 1):
        append_state_snapshot(
            run_dir / "state.txt",
            semantic_loop_state_updates(stage, status="reviewing", attempt=attempt, max_attempts=attempts),
        )
        result = await _run_semantic_review_once(
            job_id,
            run_dir=run_dir,
            stage=stage,
            attempt=attempt,
            max_attempts=attempts,
            final_attempt=attempt >= attempts,
        )
        last_result = result
        if result.passed:
            append_state_snapshot(
                run_dir / "state.txt",
                semantic_loop_state_updates(stage, status="passed", attempt=attempt, max_attempts=attempts, error_count=0),
            )
            return
        if attempt >= attempts:
            append_state_snapshot(
                run_dir / "state.txt",
                semantic_loop_state_updates(stage, status="failed", attempt=attempt, max_attempts=attempts, error_count=len(result.errors)),
            )
            raise RuntimeError(f"{stage} semantic review failed after {attempts} attempt(s): " + "; ".join(result.errors))
        await _run_semantic_review_producer_repair(
            job_id,
            run_dir=run_dir,
            stage=stage,
            round_number=attempt,
            max_attempts=attempts,
            errors=result.errors,
        )
    if last_result is not None and not last_result.passed:
        raise RuntimeError(f"{stage} semantic review failed: " + "; ".join(last_result.errors))


async def _run_semantic_review_once(
    job_id: str,
    *,
    run_dir: Path,
    stage: str,
    attempt: int,
    max_attempts: int,
    final_attempt: bool,
) -> SemanticReviewStatus:
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
    prompt = prompt_path.read_text(encoding="utf-8")
    client = create_codex_app_server_client(cwd=ROOT)
    transcript: list[dict[str, Any]] = []
    try:
        thread_id = await client.start_thread(cwd=ROOT, approval_policy="never")
        transcript = await client.run_turn(
            thread_id=thread_id,
            text=prompt,
            cwd=ROOT,
            timeout_seconds=900,
        )
    except Exception as exc:
        transport_kind = classify_codex_transport_error(str(exc))
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
    slot = SEMANTIC_REVIEW_SLOT_BY_STAGE.get(stage)
    if slot:
        state_updates[f"slot.{slot}.status"] = "in_progress"
        state_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} repair round {round_number} in progress"
    append_state_snapshot(run_dir / "state.txt", state_updates)

    prompt = paths["prompt"].read_text(encoding="utf-8")
    client = create_codex_app_server_client(cwd=ROOT)
    transcript: list[dict[str, Any]] = []
    try:
        thread_id = await client.start_thread(cwd=ROOT, approval_policy="never")
        transcript = await client.run_turn(
            thread_id=thread_id,
            text=prompt,
            cwd=ROOT,
            timeout_seconds=semantic_repair_timeout_seconds(),
        )
    except Exception as exc:
        failed_updates = {}
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
        if slot:
            failed_updates[f"slot.{slot}.status"] = "failed"
            failed_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} producer repair failed"
        failed_updates[f"review.semantic.{stage}.repair.last_error"] = str(exc)[:2000]
        append_state_snapshot(run_dir / "state.txt", failed_updates)
        write_app_server_debug_log(
            run_dir=run_dir,
            operation="semantic_review_producer_repair",
            status="app_server_failed",
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

    done_updates = semantic_repair_state_updates(
        stage,
        status="done",
        round_number=round_number,
        max_attempts=max_attempts,
        error_count=len(errors),
    )
    if slot:
        done_updates[f"slot.{slot}.status"] = "in_progress"
        done_updates[f"slot.{slot}.note"] = f"contextless semantic {stage} repair round {round_number} completed; rereview pending"
    append_state_snapshot(run_dir / "state.txt", done_updates)
    write_app_server_debug_log(
        run_dir=run_dir,
        operation="semantic_review_producer_repair",
        status="completed",
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
    else:
        return "ToC作成に失敗しました"
    message = f"{prefix}: {normalized}"
    if len(message) > max_length:
        return message[: max_length - 1] + "…"
    return message


async def _run_create_job(job_id: str, *, title: str, source: str, run_id: str, generate_images: bool = True) -> None:
    run_dir_for_log = safe_run_dir(run_id, ROOT)
    job_started = time.monotonic()
    try:
        write_app_server_debug_log(
            run_dir=run_dir_for_log,
            operation="create_job_step",
            status="started",
            item_id=job_id,
            request={"step": "toc_skill", "title": title, "sourceLength": len(source), "runId": run_id},
        )
        if generate_images:
            await _set_create_job(job_id, {"message": "本家ToC工程をp680まで実行中"})
            await _run_toc_skill_helper_until_stop_target(topic=title, source=source, run_id=run_id, stop_target="p680")
        else:
            await _set_create_job(job_id, {"message": "本家ToC工程を画像生成なしで実行中"})
            await _run_toc_immersive_frontend_cli_helper(
                topic=title,
                source=source,
                run_id=run_id,
                stop_target="p680",
                materialize_only=True,
            )
        write_app_server_debug_log(
            run_dir=run_dir_for_log,
            operation="create_job_step",
            status="completed",
            item_id=job_id,
            request={"step": "toc_skill", "runId": run_id},
            response={"elapsedMs": int((time.monotonic() - job_started) * 1000)},
        )
        validation_started = time.monotonic()
        write_app_server_debug_log(
            run_dir=run_dir_for_log,
            operation="create_job_step",
            status="started",
            item_id=job_id,
            request={"step": "p680_validation", "runId": run_id},
        )
        await _set_create_job(job_id, {"message": "p680成果物を検証中" if generate_images else "画像生成なし成果物を検証中"})
        _validate_created_run(run_id)
        if generate_images:
            _validate_frontend_create_run(run_id, strict_visual_quality=True)
        else:
            _validate_materialized_p650_run(run_id)
        write_app_server_debug_log(
            run_dir=run_dir_for_log,
            operation="create_job_step",
            status="completed",
            item_id=job_id,
            request={"step": "p680_validation", "runId": run_id},
            response={"elapsedMs": int((time.monotonic() - validation_started) * 1000)},
        )
        await _set_create_job(job_id, {"status": "completed"})
    except Exception as exc:
        _cleanup_unscaffolded_run(run_id)
        detail = _create_run_error_message(exc)
        try:
            run_dir = safe_run_dir(run_id, ROOT)
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="create_job_step",
                status="failed",
                item_id=job_id,
                request={"runId": run_id, "title": title, "sourceLength": len(source)},
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
            "error": None,
            "errorCode": None,
            "message": "フォルダを作成中",
        }
        _create_jobs[job_id] = job
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
        },
        response={"path": f"output/{run_id}"},
    )
    asyncio.create_task(_run_create_job(job_id, title=title, source=source, run_id=run_id, generate_images=bool(req.generate_images)))
    return job


@router.get("/api/image-gen/runs/create/{job_id}")
async def api_create_run_status(job_id: str) -> dict[str, Any]:
    async with _create_jobs_lock:
        job = _create_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="create job not found")
        return dict(job)


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
        duration_updates = _apply_audio_duration_to_manifest(run_dir, durations)
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "status": "P750" if result.get("status") == "completed" else "P730",
                "runtime.stage": "narration_ready_for_review" if result.get("status") == "completed" else "narration_generation_failed",
                "slot.p710.status": "done",
                "slot.p710.note": "frontend narration grounding loaded from video_manifest",
                "slot.p720.status": "done",
                "slot.p720.note": "frontend narration text saved to manifest",
                "slot.p730.status": "done" if result.get("status") == "completed" else "failed",
                "slot.p730.note": "narration audio generated from frontend",
                "slot.p740.status": "done" if duration_updates or result.get("status") == "completed" else "pending",
                "slot.p740.note": "video duration minimum synced from generated narration",
                "slot.p750.status": "awaiting_approval" if result.get("status") == "completed" else "pending",
                "slot.p750.note": "narration audio review ready in frontend",
            },
        )
    return {
        "runId": req.run_id,
        "status": result.get("status"),
        "updated": update_result["updated"],
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
        duration_updates = _apply_audio_duration_to_manifest(run_dir, durations)
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "status": "P750" if not failed else "P730",
                "runtime.stage": "narration_ready_for_review" if not failed else "narration_generation_partial_failure",
                "slot.p710.status": "done",
                "slot.p710.note": "frontend narration grounding loaded from video_manifest",
                "slot.p720.status": "done",
                "slot.p720.note": "frontend narration text saved to manifest",
                "slot.p730.status": "done" if not failed else "failed",
                "slot.p730.note": f"generated {len(results) - len(failed)}/{len(results)} narration files",
                "slot.p740.status": "done" if durations else "pending",
                "slot.p740.note": "video duration minimum synced from generated narration",
                "slot.p750.status": "awaiting_approval" if not failed else "pending",
                "slot.p750.note": "narration audio review ready in frontend",
            },
        )
    return {
        "runId": req.run_id,
        "status": "completed" if not failed else "partial_failure",
        "updated": update_result["updated"],
        "durationUpdated": duration_updates,
        "results": results,
        "progress": read_run_progress(run_dir),
    }


@router.post("/api/image-gen/video-generate")
async def api_video_generate(req: VideoGenerateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    item = VideoGenerateItem.model_validate(req.model_dump(exclude={"run_id"}))
    return await _generate_video_candidates(run_dir, item)


@router.post("/api/image-gen/video-generate-bulk")
async def api_video_generate_bulk(req: BulkVideoGenerateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
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
    destination = candidate_path(run_dir, req.item_id, index)
    started = time.monotonic()
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
        },
    )
    async with _generated_images_cutoff_lock:
        fallback_cutoff_ns = latest_generated_image_mtime_ns()
    async with _generation_semaphore:
        client = create_codex_app_server_client(cwd=ROOT)
        result = None
        debug_log = None
        try:
            await client.start()
            result = await client.generate_image(
                prompt=req.prompt,
                output_path=destination,
                reference_images=references,
                item_id=req.item_id,
                run_dir=run_dir,
                fallback_cutoff_ns=fallback_cutoff_ns,
            )
            reject_local_raster_image_result(result, item_id=req.item_id)
            debug_log = write_app_server_image_debug_log(
                run_dir=run_dir,
                item_id=req.item_id,
                index=index,
                destination=destination,
                references=references,
                prompt=req.prompt,
                kind=req.kind,
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
                result=result,
                error=str(exc),
            )
            write_app_server_debug_log(
                run_dir=run_dir,
                operation="candidate_generation",
                status="failed",
                item_id=req.item_id,
                request={"kind": req.kind, "candidateIndex": index, "destination": destination.relative_to(run_dir).as_posix()},
                response={"elapsedMs": int((time.monotonic() - started) * 1000), "debugLog": debug_log.relative_to(run_dir).as_posix() if debug_log else None},
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
            response={"elapsedMs": int((time.monotonic() - started) * 1000), "debugLog": debug_log_path, "source": result_source},
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
        },
    )
    return {
        "index": index,
        "status": "completed",
        "path": destination.relative_to(run_dir).as_posix(),
        "revisedPrompt": result.revised_prompt,
        "debugLog": debug_log_path,
        "source": result_source,
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
