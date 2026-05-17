from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
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
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .codex_app_server import CodexAppServerClient, CodexAppServerError, app_server_disabled, latest_generated_image_mtime_ns
from toc.env import load_env_files
from toc.http import HttpError
from toc.immersive_manifest import make_scene_cut_selector, normalize_dotted_id, selector_aliases
from toc.harness import append_state_snapshot, parse_state_file
from toc.providers.kling import KlingClient, KlingConfig
from toc.providers.seedance import SeedanceClient, SeedanceConfig
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
    write_app_server_image_debug_log,
    write_prompt_setting,
)


ROOT = repo_root()
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


class GenerateRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(asset|scene)$")
    item_id: str = Field(min_length=1, max_length=200)
    output: str | None = Field(default=None, max_length=500)
    prompt: str = Field(min_length=1, max_length=20000)
    references: list[str] = Field(default_factory=list, max_length=16)
    candidate_count: int = Field(default=1, ge=1, le=16)


class BulkGenerateRequest(BaseModel):
    run_id: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern="^(asset|scene)$")
    items: list[GenerateRequest] = Field(min_length=1, max_length=8)
    concurrency: int = Field(default=2, ge=1, le=16)


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
_generation_semaphore = asyncio.Semaphore(16)
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
            _codex_client = CodexAppServerClient(cwd=ROOT)
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


def _toc_immersive_command(*, topic: str, source: str | None = None, run_id: str) -> str:
    source_text = (source or "").strip() or topic
    payload = {
        "topic": topic,
        "source": source_text,
        "run_dir": f"output/{run_id}",
        "stop_target": "p680",
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
            "Run the canonical p100-p680 frontend-review workflow in one skill invocation.",
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
                        "tool": "codex_app_server",
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
                "tool": "codex_app_server",
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
    async with _create_jobs_lock:
        job = _create_jobs.get(job_id)
        if job:
            job.update(patch)


def _validate_created_run(run_id: str) -> None:
    run_dir = safe_run_dir(run_id, ROOT)
    required = ["state.txt", "video_manifest.md"]
    missing = [name for name in required if not (run_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"ToC run was not scaffolded: missing {', '.join(missing)}")


def _manifest_cut_contract(data: dict[str, Any], *, min_cuts_per_scene: int = 2) -> tuple[list[str], set[str]]:
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


def _validate_p650_run(run_id: str) -> None:
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
    cut_issues, required_scene_outputs = _manifest_cut_contract(manifest_data, min_cuts_per_scene=2)
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


def _validate_frontend_create_run(run_id: str) -> None:
    _validate_p650_run(run_id)
    run_dir = safe_run_dir(run_id, ROOT)
    _validate_generated_outputs(run_dir, "asset")
    _validate_generated_outputs(run_dir, "scene")
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


async def _run_toc_skill_helper(*, topic: str, source: str | None = None, run_id: str) -> None:
    if app_server_disabled():
        raise RuntimeError("Codex app-server is disabled")
    skill_path = _toc_immersive_skill_path()
    if not skill_path.is_file():
        raise RuntimeError(f"Codex skill not found: {skill_path}")
    client = CodexAppServerClient(cwd=ROOT)
    try:
        await client.start()
        try:
            skills = await client.list_skills(cwd=ROOT, force_reload=True)
        except CodexAppServerError as exc:
            if not _is_unsupported_method_error(exc):
                raise
        else:
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
        await client.run_skill(
            text=_toc_immersive_command(topic=topic, source=source, run_id=run_id),
            skill_path=skill_path,
            cwd=ROOT,
            timeout_seconds=7200,
        )
    finally:
        await client.stop()


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(client.tts(text=text))


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
            "- tool: `codex_app_server`",
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
            "tool": "google_nanobanana_2",
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


async def _upgrade_initial_request_prompts(job_id: str, *, run_id: str) -> None:
    run_dir = safe_run_dir(run_id, ROOT)
    if app_server_disabled():
        return
    await _set_create_job(job_id, {"message": "画像生成プロンプトを高密度化中"})
    client = CodexAppServerClient(cwd=ROOT)
    try:
        await client.start()
        for kind in ("asset", "scene"):
            items = [item for item in load_request_items(run_dir, kind) if _prompt_needs_quality_upgrade(item)]
            if not items:
                continue
            prompts: dict[str, str] = {}
            for item in items:
                target = _prompt_target_for_item(item)
                setting = read_prompt_setting(target, root=ROOT)
                prompt = await client.regenerate_prompt(
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
                    run_dir=run_dir,
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


async def _generate_request_outputs(*, run_dir: Path, kind: str) -> None:
    items = load_request_items(run_dir, kind)
    if not items:
        raise RuntimeError(f"{kind} request file has no {kind} items")
    if app_server_disabled():
        raise RuntimeError("Codex app-server is disabled")
    client = CodexAppServerClient(cwd=ROOT)
    try:
        await client.start()
        for item in items:
            if not item.output:
                continue
            if not item.prompt.strip():
                raise RuntimeError(f"{kind} request has no prompt: {item.id}")
            destination = resolve_run_relative(run_dir, item.output)
            if destination.exists():
                continue
            references: list[Path] = []
            for ref in item.references:
                reference = resolve_run_relative(run_dir, ref)
                if not reference.exists() or not reference.is_file():
                    raise RuntimeError(f"{kind} reference not found for {item.id}: {ref}")
                require_image_file(reference)
                references.append(reference)
            async with _generated_images_cutoff_lock:
                fallback_cutoff_ns = latest_generated_image_mtime_ns()
            result = await client.generate_image(
                prompt=item.prompt,
                output_path=destination,
                reference_images=references,
                item_id=item.id,
                run_dir=run_dir,
                fallback_cutoff_ns=fallback_cutoff_ns,
            )
            debug_log = write_app_server_image_debug_log(
                run_dir=run_dir,
                item_id=item.id,
                index=1,
                destination=destination,
                references=references,
                result=result,
            )
            if result.saved_path is None:
                raise RuntimeError(f"Codex app-server did not return an image for {item.id}; see {debug_log}")
            copy_saved_image(result.saved_path, destination)
    finally:
        await client.stop()


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
            "slot.p670.note": "automated QA skipped; frontend human review is next",
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


async def _generate_create_images(job_id: str, *, run_id: str) -> None:
    run_dir = safe_run_dir(run_id, ROOT)
    await _set_create_job(job_id, {"message": "素材画像を生成中"})
    await _generate_request_outputs(run_dir=run_dir, kind="asset")
    await _set_create_job(job_id, {"message": "シーン画像を生成中"})
    await _generate_request_outputs(run_dir=run_dir, kind="scene")
    _mark_image_generation_review_ready(run_id)


async def _run_create_job(job_id: str, *, title: str, source: str, run_id: str) -> None:
    try:
        await _set_create_job(job_id, {"message": "本家ToC工程をp680まで実行中"})
        await _run_toc_skill_helper(topic=title, source=source, run_id=run_id)
        _validate_created_run(run_id)
        _validate_frontend_create_run(run_id)
        await _set_create_job(job_id, {"status": "completed"})
    except Exception as exc:
        _cleanup_unscaffolded_run(run_id)
        await _set_create_job(job_id, {"status": "failed", "error": "ToC作成に失敗しました", "errorCode": type(exc).__name__, "message": "作成失敗"})


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
    asyncio.create_task(_run_create_job(job_id, title=title, source=source, run_id=run_id))
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
    client = CodexAppServerClient(cwd=ROOT)
    try:
        await client.start()
        prompt = await client.regenerate_prompt(
            item=item,
            target=target,
            instruction=(
                "Create a new ToC reusable asset image-generation prompt from the title and permanent instruction. "
                "The prompt must describe exactly what to create, preserve continuity with the whole run, and be ready for image generation. "
                f"Asset title: {req.title.strip()}"
            ),
            setting_content=str(setting["content"]),
            run_dir=run_dir,
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
        "item": item_to_api(created) if created else {**item, "prompt": prompt, "existingImage": None, "generationStatus": None, "tool": "codex_app_server"},
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
    destination = candidate_path(run_dir, req.item_id, index, output=req.output)
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
    async with _generated_images_cutoff_lock:
        fallback_cutoff_ns = latest_generated_image_mtime_ns()
    async with _generation_semaphore:
        client = CodexAppServerClient(cwd=ROOT)
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
            debug_log = write_app_server_image_debug_log(
                run_dir=run_dir,
                item_id=req.item_id,
                index=index,
                destination=destination,
                references=references,
                result=result,
            )
        except Exception as exc:
            debug_log = write_app_server_image_debug_log(
                run_dir=run_dir,
                item_id=req.item_id,
                index=index,
                destination=destination,
                references=references,
                result=result,
                error=str(exc),
            )
            raise
        finally:
            await client.stop()
    debug_log_path = debug_log.relative_to(run_dir).as_posix() if debug_log else None
    result_source = getattr(result, "source", "app_server")
    if result.saved_path is None:
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
    if total_candidates > 32:
        raise HTTPException(status_code=400, detail="bulk generation is limited to 32 total candidates")
    semaphore = asyncio.Semaphore(req.concurrency)

    async def guarded(item: GenerateRequest) -> dict[str, Any]:
        normalized = item.model_copy(update={"run_id": req.run_id, "kind": req.kind})
        async with semaphore:
            return await api_generate(normalized)

    results = await asyncio.gather(*(guarded(item) for item in req.items), return_exceptions=True)
    payload = []
    for item, result in zip(req.items, results, strict=False):
        if isinstance(result, Exception):
            payload.append({"itemId": item.item_id, "error": "generation failed", "candidates": []})
        else:
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
            client = CodexAppServerClient(cwd=ROOT)
            try:
                await client.start()
                prompt = await client.regenerate_prompt(
                    item=item_to_api(item),
                    target=req.target,
                    instruction=req.instruction,
                    setting_content=setting["content"],
                    run_dir=run_dir,
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
        inserted.append(insert_candidate(run_dir, candidate, item.output))
    return {"inserted": inserted}


@router.post("/api/chat/turn")
async def api_chat_turn(req: ChatTurnRequest) -> dict[str, Any]:
    async with _chat_semaphore:
        async with _chat_turn_lock:
            client = await get_codex_client()
            cwd = safe_run_dir(req.run_id, ROOT) if req.run_id else ROOT
            thread_id = _chat_threads.get(req.session_id)
            if not thread_id:
                thread_id = await client.start_thread(cwd=cwd)
                if len(_chat_threads) >= 32:
                    _chat_threads.pop(next(iter(_chat_threads)))
                _chat_threads[req.session_id] = thread_id
            transcript = await client.run_turn(thread_id=thread_id, text=req.message, cwd=cwd, timeout_seconds=300)
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
