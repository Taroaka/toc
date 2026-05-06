from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CodexAppServerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImageGenerationResult:
    saved_path: Path | None
    revised_prompt: str | None
    status: str
    transcript: list[dict[str, Any]]


class CodexAppServerClient:
    def __init__(self, *, cwd: Path, codex_bin: str = "codex") -> None:
        self.cwd = cwd
        self.codex_bin = codex_bin
        self.proc: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._notifications: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()

    async def start(self) -> None:
        if self.proc is not None:
            return
        if shutil.which(self.codex_bin) is None:
            raise CodexAppServerError("codex executable not found")
        self.proc = await asyncio.create_subprocess_exec(
            self.codex_bin,
            "app-server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.cwd),
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        await self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "toc_image_gen",
                    "title": "ToC Image Gen",
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        await self.notify("initialized", {})

    async def stop(self) -> None:
        if self.proc is None:
            return
        proc = self.proc
        self.proc = None
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None
        if self._stderr_task:
            self._stderr_task.cancel()
            self._stderr_task = None

    async def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            if "id" in message:
                future = self._pending.pop(int(message["id"]), None)
                if future and not future.done():
                    future.set_result(message)
            else:
                await self._notifications.put(message)

    async def _drain_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        while True:
            line = await self.proc.stderr.readline()
            if not line:
                break

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        await self.start() if self.proc is None else None
        assert self.proc and self.proc.stdin
        request_id = self._next_id
        self._next_id += 1
        payload = {"method": method, "id": request_id}
        if params is not None:
            payload["params"] = params
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[request_id] = future
        async with self._write_lock:
            self.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            await self.proc.stdin.drain()
        response = await asyncio.wait_for(future, timeout=120)
        if response.get("error"):
            raise CodexAppServerError(str(response["error"]))
        return response.get("result") or {}

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        await self.start() if self.proc is None else None
        assert self.proc and self.proc.stdin
        payload = {"method": method, "params": params or {}}
        async with self._write_lock:
            self.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            await self.proc.stdin.drain()

    async def start_thread(self, *, model: str | None = None, cwd: Path | None = None) -> str:
        params: dict[str, Any] = {
            "cwd": str(cwd or self.cwd),
            "approvalPolicy": "on-request",
            "sandbox": "workspace-write",
        }
        if model:
            params["model"] = model
        result = await self.request("thread/start", params)
        thread = result.get("thread") or {}
        thread_id = thread.get("id")
        if not thread_id:
            raise CodexAppServerError("thread/start did not return thread id")
        return str(thread_id)

    async def run_turn(
        self,
        *,
        thread_id: str,
        text: str,
        cwd: Path | None = None,
        local_images: list[Path] | None = None,
        timeout_seconds: int = 900,
    ) -> list[dict[str, Any]]:
        input_items: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for image in local_images or []:
            input_items.append({"type": "localImage", "path": str(image)})
        result = await self.request(
            "turn/start",
            {"threadId": thread_id, "cwd": str(cwd or self.cwd), "input": input_items},
        )
        turn_id = str((result.get("turn") or {}).get("id") or "")
        transcript: list[dict[str, Any]] = []
        while True:
            try:
                notification = await asyncio.wait_for(self._notifications.get(), timeout=timeout_seconds)
            except asyncio.TimeoutError as exc:
                raise CodexAppServerError("turn timed out") from exc
            transcript.append(notification)
            params = notification.get("params") or {}
            if turn_id and params.get("turnId") not in {None, turn_id}:
                continue
            if notification.get("method") == "turn/completed":
                return transcript

    async def generate_image(
        self,
        *,
        prompt: str,
        output_path: Path,
        reference_images: list[Path],
        item_id: str,
        run_dir: Path,
    ) -> ImageGenerationResult:
        thread_id = await self.start_thread(cwd=run_dir)
        reference_lines = "\n".join(f"- {p.name}: attached local image" for p in reference_images) or "- none"
        text = f"""Use Codex built-in image generation to create one image candidate.

Item id: {item_id}
Destination after generation: {output_path}
Reference images:
{reference_lines}

Prompt:
{prompt}

Rules:
- Generate exactly one image.
- Use a native landscape 16:9 composition unless the prompt explicitly says otherwise.
- If there are no reference images, keep this as no-reference built-in image generation.
- Do not edit repository files. The host app will import the saved generated image.
- After generating, briefly state whether generation completed.
"""
        transcript = await self.run_turn(
            thread_id=thread_id,
            text=text,
            cwd=run_dir,
            local_images=reference_images,
        )
        image_items: list[dict[str, Any]] = []
        for message in transcript:
            item = ((message.get("params") or {}).get("item") or {})
            if item.get("type") == "imageGeneration":
                image_items.append(item)
        latest = image_items[-1] if image_items else {}
        saved = latest.get("savedPath")
        return ImageGenerationResult(
            saved_path=Path(saved) if saved else None,
            revised_prompt=latest.get("revisedPrompt"),
            status=str(latest.get("status") or "missing"),
            transcript=transcript,
        )


def app_server_disabled() -> bool:
    return os.environ.get("TOC_IMAGE_GEN_DISABLE_CODEX_APP_SERVER", "").lower() in {"1", "true", "yes"}
