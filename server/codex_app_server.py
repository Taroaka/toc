from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CodexAppServerError(RuntimeError):
    pass


_claimed_generated_images: set[str] = set()
_claimed_generated_images_lock = asyncio.Lock()


@dataclass(frozen=True)
class ImageGenerationResult:
    saved_path: Path | None
    revised_prompt: str | None
    status: str
    transcript: list[dict[str, Any]]
    source: str = "app_server"


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

    async def start_thread(
        self,
        *,
        model: str | None = None,
        cwd: Path | None = None,
        approval_policy: str = "on-request",
    ) -> str:
        params: dict[str, Any] = {
            "cwd": str(cwd or self.cwd),
            "approvalPolicy": approval_policy,
            "sandbox": "workspace-write",
        }
        default_model = default_app_server_model()
        if model or default_model:
            params["model"] = model or default_model
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
        skills: list[Path] | None = None,
        timeout_seconds: int = 900,
    ) -> list[dict[str, Any]]:
        input_items: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for skill in skills or []:
            input_items.append({"type": "skill", "name": skill.parent.name, "path": str(skill)})
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
            method = str(notification.get("method") or "").lower()
            if "approval" in method:
                raise CodexAppServerError(f"turn requested interactive approval: {notification.get('method')}")
            if notification.get("method") == "turn/completed":
                turn = params.get("turn") or {}
                if (turn.get("status") or "").lower() == "failed":
                    error = turn.get("error") or {}
                    raise CodexAppServerError(str(error.get("message") or "turn failed"))
                return transcript

    async def run_slash_command(
        self,
        *,
        text: str,
        cwd: Path | None = None,
        timeout_seconds: int = 1800,
    ) -> list[dict[str, Any]]:
        thread_id = await self.start_thread(cwd=cwd or self.cwd)
        return await self.run_turn(thread_id=thread_id, text=text, cwd=cwd or self.cwd, timeout_seconds=timeout_seconds)

    async def list_skills(self, *, cwd: Path | None = None, force_reload: bool = False) -> list[dict[str, Any]]:
        result = await self.request("skills/list", {"cwds": [str(cwd or self.cwd)], "forceReload": force_reload})
        data = result.get("data") or []
        skills: list[dict[str, Any]] = []
        for entry in data:
            if isinstance(entry, dict):
                for skill in entry.get("skills") or []:
                    if isinstance(skill, dict):
                        skills.append(skill)
        return skills

    async def run_skill(
        self,
        *,
        text: str,
        skill_path: Path,
        cwd: Path | None = None,
        timeout_seconds: int = 1800,
    ) -> list[dict[str, Any]]:
        thread_id = await self.start_thread(cwd=cwd or self.cwd, approval_policy="never")
        return await self.run_turn(
            thread_id=thread_id,
            text=text,
            cwd=cwd or self.cwd,
            skills=[skill_path],
            timeout_seconds=timeout_seconds,
        )

    async def generate_image(
        self,
        *,
        prompt: str,
        output_path: Path,
        reference_images: list[Path],
        item_id: str,
        run_dir: Path,
        fallback_cutoff_ns: int | None = None,
    ) -> ImageGenerationResult:
        thread_id = await self.start_thread(cwd=run_dir)
        cutoff_ns = fallback_cutoff_ns if fallback_cutoff_ns is not None else latest_generated_image_mtime_ns()
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
        turn_task = asyncio.create_task(
            self.run_turn(
                thread_id=thread_id,
                text=text,
                cwd=run_dir,
                local_images=reference_images,
            )
        )
        fallback_task = asyncio.create_task(wait_for_unclaimed_generated_image_after(cutoff_ns))
        done, _pending = await asyncio.wait({turn_task, fallback_task}, return_when=asyncio.FIRST_COMPLETED)
        if fallback_task in done:
            fallback = fallback_task.result()
            if fallback:
                turn_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await turn_task
                return ImageGenerationResult(
                    saved_path=fallback,
                    revised_prompt=None,
                    status="completed",
                    transcript=[],
                    source="generated_images_early_fallback",
                )
        if not fallback_task.done():
            fallback_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await fallback_task
        transcript = await turn_task
        image_items: list[dict[str, Any]] = []
        for message in transcript:
            image_items.extend(find_image_generation_items(message))
        latest = image_items[-1] if image_items else {}
        saved = image_generation_saved_path(latest)
        source = "app_server"
        if not saved:
            fallback = await claim_latest_generated_image_after(cutoff_ns)
            if fallback:
                saved = str(fallback)
                source = "generated_images_fallback"
        return ImageGenerationResult(
            saved_path=Path(saved) if saved else None,
            revised_prompt=latest.get("revisedPrompt") or latest.get("revised_prompt"),
            status=str(latest.get("status") or ("completed" if saved else "missing")),
            transcript=transcript,
            source=source,
        )

    async def regenerate_prompt(
        self,
        *,
        item: dict[str, Any],
        target: str,
        instruction: str,
        setting_content: str,
        run_dir: Path,
    ) -> str:
        thread_id = await self.start_thread(cwd=run_dir)
        text = f"""Rewrite one ToC image-generation prompt.

Target tab: {target}
Item metadata JSON:
{json.dumps(item, ensure_ascii=False, indent=2)}

Permanent instruction section:
{setting_content}

User override instruction:
{instruction}

Rules:
- Return exactly one JSON object.
- JSON shape: {{"prompt": "rewritten prompt text"}}
- Do not generate images.
- Do not edit files.
- Keep metadata, output path, references, and item id unchanged.
- The rewritten prompt must be self-contained and ready for image generation.
"""
        transcript = await self.run_turn(thread_id=thread_id, text=text, cwd=run_dir, timeout_seconds=900)
        messages: list[str] = []
        for event in transcript:
            messages.extend(find_agent_message_texts(event))
        response_text = "\n".join(messages).strip()
        return _extract_prompt_from_agent_text(response_text)


def app_server_disabled() -> bool:
    return os.environ.get("TOC_IMAGE_GEN_DISABLE_CODEX_APP_SERVER", "").lower() in {"1", "true", "yes"}


def default_app_server_model() -> str:
    return os.environ.get("TOC_CODEX_APP_SERVER_MODEL", "").strip()


def _extract_prompt_from_agent_text(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise CodexAppServerError("prompt regeneration returned no text")
    candidates = [stripped]
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
    if fence_match:
        candidates.insert(0, fence_match.group(1).strip())
    object_match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if object_match:
        candidates.append(object_match.group(0).strip())
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        prompt = str(payload.get("prompt") or "").strip() if isinstance(payload, dict) else ""
        if prompt:
            return prompt
    raise CodexAppServerError("prompt regeneration did not return JSON with prompt")


def find_image_generation_items(message: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "imageGeneration":
                items.append(value)
                return
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(message)
    return items


def image_generation_saved_path(item: dict[str, Any]) -> str | None:
    for key in ("savedPath", "saved_path", "outputPath", "output_path", "path"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    saved = item.get("saved")
    if isinstance(saved, dict):
        for key in ("path", "savedPath", "saved_path"):
            value = saved.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def generated_images_root() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    return codex_home / "generated_images"


def iter_generated_image_files(root: Path | None = None) -> list[Path]:
    base = root or generated_images_root()
    if not base.exists():
        return []
    return sorted(
        (p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}),
        key=lambda p: p.stat().st_mtime_ns,
        reverse=True,
    )


def latest_generated_image_mtime_ns(root: Path | None = None) -> int:
    images = iter_generated_image_files(root)
    return images[0].stat().st_mtime_ns if images else 0


def latest_generated_image_after(cutoff_ns: int, root: Path | None = None) -> Path | None:
    for image in iter_generated_image_files(root):
        if image.stat().st_mtime_ns > cutoff_ns:
            return image
    return None


async def wait_for_generated_image_after(
    cutoff_ns: int,
    *,
    root: Path | None = None,
    timeout_seconds: int = 300,
    poll_seconds: float = 1.0,
) -> Path | None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while loop.time() < deadline:
        image = latest_generated_image_after(cutoff_ns, root)
        if image and image.exists():
            first_stat = image.stat()
            if first_stat.st_size > 0:
                await asyncio.sleep(0.5)
                if image.exists():
                    second_stat = image.stat()
                    if second_stat.st_size == first_stat.st_size and second_stat.st_mtime_ns == first_stat.st_mtime_ns:
                        return image
        await asyncio.sleep(poll_seconds)
    return None


async def claim_latest_generated_image_after(cutoff_ns: int, root: Path | None = None) -> Path | None:
    async with _claimed_generated_images_lock:
        for image in iter_generated_image_files(root):
            resolved = str(image.resolve())
            if image.stat().st_mtime_ns > cutoff_ns and resolved not in _claimed_generated_images:
                _claimed_generated_images.add(resolved)
                return image
    return None


async def _peek_unclaimed_generated_image_after(cutoff_ns: int, root: Path | None = None) -> Path | None:
    async with _claimed_generated_images_lock:
        for image in iter_generated_image_files(root):
            resolved = str(image.resolve())
            if image.stat().st_mtime_ns > cutoff_ns and resolved not in _claimed_generated_images:
                return image
    return None


async def _claim_generated_image(image: Path) -> bool:
    async with _claimed_generated_images_lock:
        resolved = str(image.resolve())
        if resolved in _claimed_generated_images:
            return False
        _claimed_generated_images.add(resolved)
        return True


async def wait_for_unclaimed_generated_image_after(
    cutoff_ns: int,
    *,
    root: Path | None = None,
    timeout_seconds: int = 300,
    poll_seconds: float = 1.0,
) -> Path | None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while loop.time() < deadline:
        image = await _peek_unclaimed_generated_image_after(cutoff_ns, root)
        if image and image.exists():
            first_stat = image.stat()
            if first_stat.st_size > 0:
                await asyncio.sleep(0.5)
                if image.exists():
                    second_stat = image.stat()
                    if (
                        second_stat.st_size == first_stat.st_size
                        and second_stat.st_mtime_ns == first_stat.st_mtime_ns
                        and await _claim_generated_image(image)
                    ):
                        return image
        await asyncio.sleep(poll_seconds)
    return None


def find_agent_message_texts(message: dict[str, Any]) -> list[str]:
    texts: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "agentMessage" and value.get("text"):
                texts.append(str(value["text"]))
                return
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(message)
    return texts
