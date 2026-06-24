from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import re
import shutil
import socket
import tempfile
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class CodexAppServerError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        transcript: list[dict[str, Any]] | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.transcript = transcript or []
        self.diagnostics = diagnostics or {}


class CodexAppServerTransportError(CodexAppServerError):
    """Raised when the Codex app-server cannot reach the ChatGPT backend."""


_claimed_generated_images: set[str] = set()
_claimed_generated_images_lock = asyncio.Lock()
_NETWORK_PREFLIGHT_CACHE_SECONDS = 60.0
_network_preflight_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_CODEX_HOME_FALLBACK_FILES = {
    ".codex-global-state.json",
    "auth.json",
    "config.toml",
    "installation_id",
    "internal_storage.json",
    "models_cache.json",
    "version.json",
}
_CODEX_HOME_FALLBACK_RELATIVE_FILES = {
    Path("browser") / "config.toml",
}


@dataclass(frozen=True)
class ImageGenerationResult:
    saved_path: Path | None
    revised_prompt: str | None
    status: str
    transcript: list[dict[str, Any]]
    source: str = "app_server"
    generation_job_id: str | None = None
    item_id: str | None = None
    turn_id: str | None = None
    prompt_sha256: str | None = None
    reference_sha256s: list[str] | None = None
    destination: str | None = None
    provenance_authoritative: bool = False
    provenance_policy: str | None = None


@dataclass(frozen=True)
class CodexAppServerRuntimeContract:
    codex_bin: str
    cwd: Path
    requested_codex_home: Path
    codex_home: Path
    codex_home_source: str
    fallback_used: bool
    fallback_allowed: bool
    generated_images_root: Path
    proxy_env: dict[str, str]
    network_preflight: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "codexBin": self.codex_bin,
            "cwd": str(self.cwd),
            "requestedCodexHome": str(self.requested_codex_home),
            "codexHome": str(self.codex_home),
            "codexHomeSource": self.codex_home_source,
            "fallbackUsed": self.fallback_used,
            "fallbackAllowed": self.fallback_allowed,
            "generatedImagesRoot": str(self.generated_images_root),
            "proxyEnv": self.proxy_env,
            "networkPreflight": self.network_preflight,
        }


def reject_local_raster_image_result(result: ImageGenerationResult, *, item_id: str) -> None:
    source = str(getattr(result, "source", "") or "").strip().lower()
    if source.startswith("local_raster") or "local_raster" in source:
        raise CodexAppServerError(
            f"unsupported local raster fallback for {item_id}: {result.source}; "
            "retry with Codex built-in image generation instead"
        )


def _consume_task_exception(task: asyncio.Task[Any]) -> None:
    if task.cancelled():
        return
    with contextlib.suppress(Exception):
        task.exception()


class CodexAppServerClient:
    def __init__(self, *, cwd: Path, codex_bin: str = "codex") -> None:
        self.cwd = cwd
        self.codex_bin = os.environ.get("TOC_CODEX_BIN", "").strip() or codex_bin
        self.proc: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._notifications: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._write_lock = asyncio.Lock()
        self._stderr_tail: deque[str] = deque(maxlen=80)
        self._codex_home: Path | None = None
        self._requested_codex_home: Path | None = None
        self._codex_home_source = ""
        self._codex_home_fallback_used = False
        self._runtime_contract: CodexAppServerRuntimeContract | None = None
        self._network_preflight: dict[str, Any] = {}

    def _resolve_codex_home(self, env: dict[str, str] | None = None) -> Path:
        if self._codex_home is not None:
            return self._codex_home
        env = env or os.environ
        raw_codex_home = env.get("CODEX_HOME", "").strip()
        codex_home = Path(raw_codex_home) if raw_codex_home else Path.home() / ".codex"
        self._requested_codex_home = codex_home
        self._codex_home_source = "env" if raw_codex_home else "default"
        if not _is_writable_directory(codex_home):
            if not app_server_codex_home_fallback_allowed():
                raise CodexAppServerError(
                    "Codex app-server CODEX_HOME is not writable; refusing silent fallback. "
                    f"Set CODEX_HOME to a writable Codex home or set TOC_CODEX_HOME_FALLBACK_ALLOWED=1 explicitly: {codex_home}"
                )
            source_home = codex_home
            fallback_home = Path(tempfile.gettempdir()) / "toc-codex-home"
            fallback_home.mkdir(parents=True, exist_ok=True)
            with contextlib.suppress(OSError):
                fallback_home.chmod(0o700)
            _copy_codex_home_portable_files(source_home, fallback_home)
            codex_home = fallback_home
            self._codex_home_source = "fallback"
            self._codex_home_fallback_used = True
        self._codex_home = codex_home
        return codex_home

    def _subprocess_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["CODEX_HOME"] = str(self._resolve_codex_home(env))
        return env

    def runtime_contract(self) -> CodexAppServerRuntimeContract:
        if self._runtime_contract is not None:
            return self._runtime_contract
        codex_home = self._resolve_codex_home()
        requested = self._requested_codex_home or codex_home
        self._runtime_contract = CodexAppServerRuntimeContract(
            codex_bin=self.codex_bin,
            cwd=self.cwd,
            requested_codex_home=requested,
            codex_home=codex_home,
            codex_home_source=self._codex_home_source or "resolved",
            fallback_used=self._codex_home_fallback_used,
            fallback_allowed=app_server_codex_home_fallback_allowed(),
            generated_images_root=codex_home / "generated_images",
            proxy_env=_proxy_env_snapshot(),
            network_preflight=self._network_preflight,
        )
        return self._runtime_contract

    def preflight_runtime(self, *, require_network: bool | None = None) -> dict[str, Any]:
        codex_bin_path = shutil.which(self.codex_bin)
        if codex_bin_path is None:
            raise CodexAppServerError("codex executable not found")
        codex_home = self._resolve_codex_home()
        checks: dict[str, Any] = {
            "status": "passed",
            "codexBinPath": codex_bin_path,
            "codexHomeWritable": True,
            "network": {"status": "skipped"},
        }
        should_check_network = app_server_network_preflight_enabled() if require_network is None else require_network
        if should_check_network:
            checks["network"] = preflight_codex_backend_network()
        self._network_preflight = checks
        self._runtime_contract = None
        self.runtime_contract()
        if not codex_home.is_dir():
            raise CodexAppServerError(f"Codex app-server CODEX_HOME does not exist after resolution: {codex_home}")
        return checks

    def generated_images_root(self) -> Path:
        return self._resolve_codex_home() / "generated_images"

    async def start(self) -> None:
        if self.proc is not None:
            return
        self.preflight_runtime()
        self.proc = await asyncio.create_subprocess_exec(
            self.codex_bin,
            "app-server",
            "--listen",
            "stdio://",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.cwd),
            env=self._subprocess_env(),
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
        error = CodexAppServerError(self._format_process_error("Codex app-server closed stdout"))
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

    async def _drain_stderr(self) -> None:
        assert self.proc and self.proc.stderr
        while True:
            line = await self.proc.stderr.readline()
            if not line:
                break
            self._stderr_tail.append(line.decode("utf-8", errors="replace").rstrip())

    def _stderr_summary(self) -> str:
        tail = "\n".join(line for line in self._stderr_tail if line)
        return tail.strip()

    def diagnostics(self) -> dict[str, Any]:
        proc = self.proc
        contract = self.runtime_contract().as_dict()
        return {
            **contract,
            "codexBin": self.codex_bin,
            "cwd": str(self.cwd),
            "pid": proc.pid if proc is not None else None,
            "returncode": proc.returncode if proc is not None else None,
            "codexHome": str(self._resolve_codex_home()),
            "generatedImagesRoot": str(self.generated_images_root()),
            "pendingRequestIds": sorted(self._pending.keys()),
            "stderrTail": list(self._stderr_tail),
            "transportErrorKind": classify_codex_transport_error(self._stderr_summary()),
        }

    def _format_process_error(self, prefix: str) -> str:
        proc = self.proc
        returncode = proc.returncode if proc is not None else None
        details = [prefix]
        if returncode is not None:
            details.append(f"returncode={returncode}")
        stderr = self._stderr_summary()
        if stderr:
            details.append(f"stderr:\n{stderr}")
        return "; ".join(details)

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
            try:
                self.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
                await self.proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as exc:
                self._pending.pop(request_id, None)
                message = self._format_process_error(f"Codex app-server pipe closed during {method}")
                error_cls = CodexAppServerTransportError if classify_codex_transport_error(message) else CodexAppServerError
                raise error_cls(message, diagnostics=self.diagnostics()) from exc
        try:
            response = await asyncio.wait_for(future, timeout=120)
        except asyncio.TimeoutError as exc:
            self._pending.pop(request_id, None)
            message = self._format_process_error(f"Codex app-server timed out during {method}")
            error_cls = CodexAppServerTransportError if method.startswith("turn/") else CodexAppServerError
            raise error_cls(message, diagnostics=self.diagnostics()) from exc
        if response.get("error"):
            message = str(response["error"])
            error_cls = CodexAppServerTransportError if classify_codex_transport_error(message) else CodexAppServerError
            raise error_cls(message, diagnostics=self.diagnostics())
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
        reset_timeout_on_notification: bool = False,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
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
        deadline = time.monotonic() + max(1, timeout_seconds)
        while True:
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise asyncio.TimeoutError
                notification = await asyncio.wait_for(self._notifications.get(), timeout=remaining)
            except asyncio.TimeoutError as exc:
                raise CodexAppServerTransportError("turn timed out", transcript=transcript, diagnostics=self.diagnostics()) from exc
            transcript.append(notification)
            if progress_callback is not None:
                progress_callback(notification)
            if reset_timeout_on_notification:
                deadline = time.monotonic() + max(1, timeout_seconds)
            params = notification.get("params") or {}
            if turn_id and params.get("turnId") not in {None, turn_id}:
                continue
            method = str(notification.get("method") or "").lower()
            if "approval" in method:
                raise CodexAppServerError(
                    f"turn requested interactive approval: {notification.get('method')}",
                    transcript=transcript,
                    diagnostics=self.diagnostics(),
                )
            if notification.get("method") == "turn/completed":
                turn = params.get("turn") or {}
                if (turn.get("status") or "").lower() == "failed":
                    error = turn.get("error") or {}
                    message = str(error.get("message") or "turn failed")
                    error_cls = CodexAppServerTransportError if classify_codex_transport_error(message) else CodexAppServerError
                    raise error_cls(
                        message,
                        transcript=transcript,
                        diagnostics=self.diagnostics(),
                    )
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
        generation_job_id: str | None = None,
        allow_generated_images_fallback: bool = True,
        provenance_policy: str | None = None,
        timeout_seconds: int = 900,
    ) -> ImageGenerationResult:
        thread_id = await self.start_thread(cwd=run_dir)
        generated_root = self.generated_images_root()
        cutoff_ns = fallback_cutoff_ns if fallback_cutoff_ns is not None else latest_generated_image_mtime_ns(generated_root)
        prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        reference_sha256s = [_sha256_file(path) for path in reference_images]
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
                timeout_seconds=timeout_seconds,
            )
        )
        turn_task.add_done_callback(_consume_task_exception)
        fallback_task: asyncio.Task[Path | None] | None = None
        tasks: set[asyncio.Task[Any]] = {turn_task}
        if allow_generated_images_fallback:
            fallback_task = asyncio.create_task(
                wait_for_unclaimed_generated_image_after(
                    cutoff_ns,
                    root=generated_root,
                    timeout_seconds=timeout_seconds,
                )
            )
            tasks.add(fallback_task)
        done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        if fallback_task is not None and fallback_task in done:
            fallback = fallback_task.result()
            if fallback:
                turn_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, CodexAppServerError, asyncio.TimeoutError):
                    await turn_task
                return ImageGenerationResult(
                    saved_path=fallback,
                    revised_prompt=None,
                    status="completed",
                    transcript=[],
                    source="generated_images_early_fallback",
                    generation_job_id=generation_job_id,
                    item_id=item_id,
                    prompt_sha256=prompt_sha256,
                    reference_sha256s=reference_sha256s,
                    destination=str(output_path),
                    provenance_authoritative=False,
                    provenance_policy=provenance_policy,
                )
        if fallback_task is not None and not fallback_task.done():
            fallback_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await fallback_task
        transcript = await turn_task
        turn_id = _extract_turn_id(transcript)
        image_items: list[dict[str, Any]] = []
        for message in transcript:
            image_items.extend(find_image_generation_items(message))
        latest = image_items[-1] if image_items else {}
        saved = image_generation_saved_path(latest)
        source = "app_server"
        if not saved:
            fallback = await claim_latest_generated_image_after(cutoff_ns, root=generated_root) if allow_generated_images_fallback else None
            if fallback:
                saved = str(fallback)
                source = "generated_images_fallback"
        authoritative = bool(saved and source == "app_server")
        return ImageGenerationResult(
            saved_path=Path(saved) if saved else None,
            revised_prompt=latest.get("revisedPrompt") or latest.get("revised_prompt"),
            status=str(latest.get("status") or ("completed" if saved else "missing")),
            transcript=transcript,
            source=source,
            generation_job_id=generation_job_id,
            item_id=item_id,
            turn_id=turn_id,
            prompt_sha256=prompt_sha256,
            reference_sha256s=reference_sha256s,
            destination=str(output_path),
            provenance_authoritative=authoritative,
            provenance_policy=provenance_policy,
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


def create_codex_app_server_client(*, cwd: Path, codex_bin: str = "codex") -> CodexAppServerClient:
    return CodexAppServerClient(cwd=cwd, codex_bin=codex_bin)


def app_server_disabled() -> bool:
    return os.environ.get("TOC_IMAGE_GEN_DISABLE_CODEX_APP_SERVER", "").lower() in {"1", "true", "yes"}


def app_server_codex_home_fallback_allowed() -> bool:
    return os.environ.get("TOC_CODEX_HOME_FALLBACK_ALLOWED", "").strip().lower() in {"1", "true", "yes", "on"}


def app_server_network_preflight_enabled() -> bool:
    return os.environ.get("TOC_CODEX_APP_SERVER_PREFLIGHT_NETWORK", "1").strip().lower() not in {"0", "false", "no", "off"}


def default_app_server_model() -> str:
    return os.environ.get("TOC_CODEX_APP_SERVER_MODEL", "").strip()


def classify_codex_transport_error(message: str) -> str:
    normalized = " ".join(str(message or "").lower().split())
    if not normalized:
        return ""
    if any(
        marker in normalized
        for marker in (
            "codex_home is not writable",
            "codex home is not writable",
            "refusing silent fallback",
            "effective codex_home is not writable",
        )
    ):
        return "runtime_environment_failed"
    if any(marker in normalized for marker in ("failed to lookup", "nodename nor servname", "name or service not known", "dns")):
        return "dns_resolution_failed"
    if any(marker in normalized for marker in ("stream disconnected", "backend-api/codex/responses")):
        return "backend_stream_disconnected"
    if any(marker in normalized for marker in ("connection reset", "broken pipe", "pipe closed")):
        return "connection_reset"
    if "timed out" in normalized or "timeout" in normalized:
        return "timeout"
    return ""


def is_codex_transport_error(exc: Exception) -> bool:
    if isinstance(exc, CodexAppServerTransportError):
        return True
    diagnostics = getattr(exc, "diagnostics", None)
    if isinstance(diagnostics, dict) and diagnostics.get("transportErrorKind"):
        return True
    return bool(classify_codex_transport_error(str(exc)))


def _proxy_env_snapshot() -> dict[str, str]:
    keys = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy")
    return {key: os.environ[key] for key in keys if os.environ.get(key)}


def preflight_codex_backend_network(*, timeout_seconds: float = 10.0) -> dict[str, Any]:
    cache_key = json.dumps({"proxy": _proxy_env_snapshot(), "timeout": timeout_seconds}, sort_keys=True)
    cached = _network_preflight_cache.get(cache_key)
    now = time.monotonic()
    if cached and now - cached[0] <= _NETWORK_PREFLIGHT_CACHE_SECONDS:
        return {**cached[1], "cached": True}

    result: dict[str, Any] = {
        "status": "passed",
        "host": "chatgpt.com",
        "url": "https://chatgpt.com/backend-api/codex/responses",
        "dns": {"status": "pending"},
        "https": {"status": "pending"},
        "cached": False,
    }
    try:
        addresses = socket.getaddrinfo("chatgpt.com", 443, type=socket.SOCK_STREAM)
        result["dns"] = {
            "status": "passed",
            "addressCount": len(addresses),
            "sample": sorted({str(entry[4][0]) for entry in addresses})[:3],
        }
    except OSError as exc:
        result["status"] = "failed"
        result["dns"] = {"status": "failed", "error": str(exc)}
        _network_preflight_cache[cache_key] = (now, result)
        raise CodexAppServerTransportError(
            "Codex app-server network preflight failed during chatgpt.com DNS resolution",
            diagnostics={"networkPreflight": result, "transportErrorKind": "dns_resolution_failed"},
        ) from exc

    request = urllib.request.Request(
        result["url"],
        method="HEAD",
        headers={"User-Agent": "toc-codex-app-server-preflight/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            result["https"] = {"status": "passed", "statusCode": int(response.status)}
    except urllib.error.HTTPError as exc:
        if exc.code in {400, 401, 403, 404, 405}:
            result["https"] = {"status": "passed", "statusCode": int(exc.code), "reachableWithHttpError": True}
        else:
            result["status"] = "failed"
            result["https"] = {"status": "failed", "statusCode": int(exc.code), "error": str(exc)}
            _network_preflight_cache[cache_key] = (now, result)
            raise CodexAppServerTransportError(
                "Codex app-server network preflight failed during chatgpt.com HTTPS reachability",
                diagnostics={"networkPreflight": result, "transportErrorKind": "backend_http_failed"},
            ) from exc
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        result["status"] = "failed"
        result["https"] = {"status": "failed", "error": str(exc)}
        _network_preflight_cache[cache_key] = (now, result)
        raise CodexAppServerTransportError(
            "Codex app-server network preflight failed during chatgpt.com HTTPS reachability",
            diagnostics={"networkPreflight": result, "transportErrorKind": classify_codex_transport_error(str(exc)) or "backend_http_failed"},
        ) from exc

    _network_preflight_cache[cache_key] = (now, result)
    return result


def _is_writable_directory(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".toc_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _copy_codex_home_portable_files(source_home: Path, fallback_home: Path) -> None:
    if not source_home.exists() or source_home.resolve() == fallback_home.resolve():
        return
    for name in _CODEX_HOME_FALLBACK_FILES:
        source = source_home / name
        if source.is_file():
            _copy_codex_home_file(source, fallback_home / name)
    for relative in _CODEX_HOME_FALLBACK_RELATIVE_FILES:
        source = source_home / relative
        if source.is_file():
            _copy_codex_home_file(source, fallback_home / relative)


def _copy_codex_home_file(source: Path, destination: Path) -> None:
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        source_mode = source.stat().st_mode & 0o777
        if source_mode:
            destination.chmod(source_mode)
    except OSError:
        return


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_turn_id(transcript: list[dict[str, Any]]) -> str | None:
    def visit(value: Any) -> str | None:
        if isinstance(value, dict):
            method = str(value.get("method") or "")
            params = value.get("params")
            if method in {"turn/started", "turn/completed"} and isinstance(params, dict):
                turn_id = params.get("turnId") or params.get("turn_id")
                if isinstance(turn_id, str) and turn_id.strip():
                    return turn_id.strip()
                turn = params.get("turn")
                if isinstance(turn, dict):
                    turn_id = turn.get("id") or turn.get("turnId") or turn.get("turn_id")
                    if isinstance(turn_id, str) and turn_id.strip():
                        return turn_id.strip()
            for key in ("turnId", "turn_id"):
                turn_id = value.get(key)
                if isinstance(turn_id, str) and turn_id.strip():
                    return turn_id.strip()
            turn = value.get("turn")
            if isinstance(turn, dict):
                turn_id = turn.get("id") or turn.get("turnId") or turn.get("turn_id")
                if isinstance(turn_id, str) and turn_id.strip():
                    return turn_id.strip()
            for child in value.values():
                found = visit(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = visit(child)
                if found:
                    return found
        return None

    for message in transcript:
        found = visit(message)
        if found:
            return found
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
