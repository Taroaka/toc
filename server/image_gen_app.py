from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .codex_app_server import CodexAppServerClient, app_server_disabled
from .image_gen import (
    IMAGE_SUFFIXES,
    build_zip,
    candidate_path,
    copy_saved_image,
    insert_candidate,
    item_to_api,
    list_reference_options,
    list_runs,
    load_request_items,
    reference_to_api,
    require_image_file,
    require_candidate_path,
    repo_root,
    resolve_run_relative,
    safe_run_dir,
    validate_image_bytes,
)


ROOT = repo_root()
WEB_DIR = ROOT / "server" / "web"
DIST_DIR = WEB_DIR / "dist"

router = APIRouter()


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


_chat_threads: dict[str, str] = {}
_codex_client: CodexAppServerClient | None = None
_client_lock = asyncio.Lock()
_generation_semaphore = asyncio.Semaphore(4)
_chat_turn_lock = asyncio.Lock()
_chat_semaphore = asyncio.Semaphore(2)
MAX_ZIP_BYTES = 250 * 1024 * 1024


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


@router.get("/api/image-gen/requests")
async def api_requests(run_id: str, kind: str = Query(pattern="^(asset|scene)$")) -> dict[str, Any]:
    run_dir = safe_run_dir(run_id, ROOT)
    items = [item_to_api(item) for item in load_request_items(run_dir, kind)]
    references = [reference_to_api(option) for option in list_reference_options(run_dir)]
    return {"run": {"id": run_id, "path": f"output/{run_id}"}, "kind": kind, "items": items, "references": references}


@router.get("/api/image-gen/file")
async def api_file(run_id: str, path: str) -> FileResponse:
    run_dir = safe_run_dir(run_id, ROOT)
    target = resolve_run_relative(run_dir, path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    if target.suffix.lower() not in IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="only image files can be served")
    return FileResponse(target)


async def _generate_one(run_dir: Path, req: GenerateRequest, index: int) -> dict[str, Any]:
    destination = candidate_path(run_dir, req.item_id, index)
    references = []
    for ref in req.references:
        reference = resolve_run_relative(run_dir, ref)
        if not reference.exists() or not reference.is_file():
            raise HTTPException(status_code=404, detail=f"reference not found: {ref}")
        require_image_file(reference)
        references.append(reference)
    if app_server_disabled():
        raise HTTPException(status_code=503, detail="Codex app-server is disabled")
    async with _generation_semaphore:
        client = CodexAppServerClient(cwd=ROOT)
        try:
            await client.start()
            result = await client.generate_image(
                prompt=req.prompt,
                output_path=destination,
                reference_images=references,
                item_id=req.item_id,
                run_dir=run_dir,
            )
        finally:
            await client.stop()
    if result.saved_path is None:
        return {
            "index": index,
            "status": "failed",
            "error": "Codex app-server did not return imageGeneration.savedPath",
            "path": None,
            "revisedPrompt": result.revised_prompt,
        }
    copy_saved_image(result.saved_path, destination)
    return {
        "index": index,
        "status": "completed",
        "path": destination.relative_to(run_dir).as_posix(),
        "revisedPrompt": result.revised_prompt,
    }


@router.post("/api/image-gen/generate")
async def api_generate(req: GenerateRequest) -> dict[str, Any]:
    run_dir = safe_run_dir(req.run_id, ROOT)
    candidates = []
    for index in range(1, req.candidate_count + 1):
        candidates.append(await _generate_one(run_dir, req, index))
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
