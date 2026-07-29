from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
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
_DEFAULT_CODEX_APP_SERVER_MODEL = "gpt-5.6-sol"
_DEFAULT_CODEX_APP_SERVER_MIN_VERSION = "0.144.0"
_DEFAULT_CODEX_APP_SERVER_JSONL_LIMIT_BYTES = 32 * 1024 * 1024
_MIN_CODEX_APP_SERVER_JSONL_LIMIT_BYTES = 1024 * 1024
_MAX_CODEX_APP_SERVER_JSONL_LIMIT_BYTES = 64 * 1024 * 1024
_CODEX_CLI_VERSION_RE = re.compile(
    r"^\s*codex(?:-cli)?\s+(?P<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?)\s*$",
    flags=re.IGNORECASE,
)
_SEMVER_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:-(?P<prerelease>[0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$"
)
_SENSITIVE_ENV_NAME_RE = re.compile(
    r"(?:^|_)(?:API_KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIALS?|"
    r"PRIVATE_KEY|DATABASE_URL|DSN|COOKIE)(?:$|_)",
    flags=re.IGNORECASE,
)


def _scrubbed_app_server_env(env: dict[str, str]) -> dict[str, str]:
    """Remove credentials and API-lane overrides from a ChatGPT-auth child."""

    return {
        key: value
        for key, value in env.items()
        if not _SENSITIVE_ENV_NAME_RE.search(key)
        and not key.upper().startswith(("OPENAI_", "AZURE_OPENAI_"))
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
    image_generation_item_id: str | None = None
    image_generation_item_count: int = 0
    destination: str | None = None
    provenance_authoritative: bool = False
    provenance_policy: str | None = None


@dataclass(frozen=True)
class CodexAppServerRuntimeContract:
    codex_bin: str
    codex_version: str
    minimum_codex_version: str
    model: str
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
            "codexVersion": self.codex_version,
            "minimumCodexVersion": self.minimum_codex_version,
            "model": self.model,
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


def app_server_jsonl_limit_bytes() -> int:
    raw = os.environ.get("TOC_CODEX_APP_SERVER_JSONL_LIMIT_BYTES", "").strip()
    try:
        configured = int(raw) if raw else _DEFAULT_CODEX_APP_SERVER_JSONL_LIMIT_BYTES
    except ValueError:
        configured = _DEFAULT_CODEX_APP_SERVER_JSONL_LIMIT_BYTES
    return min(
        _MAX_CODEX_APP_SERVER_JSONL_LIMIT_BYTES,
        max(_MIN_CODEX_APP_SERVER_JSONL_LIMIT_BYTES, configured),
    )


def _compact_image_generation_payload(message: dict[str, Any]) -> dict[str, Any]:
    """Drop the inline base64 image after JSON framing has succeeded.

    The app-server also supplies ``savedPath``. ToC imports from that path, so
    retaining several MiB of base64 in every transcript only increases memory
    and debug-log size without improving provenance.
    """

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "imageGeneration":
                value.pop("result", None)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(message)
    return message


class CodexAppServerClient:
    def __init__(
        self,
        *,
        cwd: Path,
        codex_bin: str = "codex",
        scrub_sensitive_env: bool = False,
        require_chatgpt_account: bool = False,
        require_chatgpt_pro: bool = False,
    ) -> None:
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
        self._codex_version = "unknown"
        self._minimum_codex_version = minimum_app_server_version()
        self._model = default_app_server_model()
        self._scrub_sensitive_env = scrub_sensitive_env
        self._require_chatgpt_account = require_chatgpt_account or require_chatgpt_pro
        self._require_chatgpt_pro = require_chatgpt_pro
        self._account_type: str | None = None
        self._account_plan_type: str | None = None
        self._jsonl_limit_bytes = app_server_jsonl_limit_bytes()
        self._transport_error: CodexAppServerTransportError | None = None
        self._stopping = False

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
        if self._scrub_sensitive_env:
            env = _scrubbed_app_server_env(env)
        codex_home = self._resolve_codex_home(env)
        env["CODEX_HOME"] = str(codex_home)
        if not env.get("CODEX_CODE_MODE_HOST_PATH", "").strip():
            codex_bin_path = shutil.which(self.codex_bin)
            candidates: list[Path] = []
            if codex_bin_path:
                unresolved_bin = Path(codex_bin_path)
                candidates.extend(
                    [
                        unresolved_bin.with_name("codex-code-mode-host"),
                        unresolved_bin.resolve().with_name("codex-code-mode-host"),
                    ]
                )
            candidates.extend(
                [
                    codex_home / "plugins" / ".plugin-appserver" / "codex-code-mode-host",
                    Path("/Applications/ChatGPT.app/Contents/Resources/codex-code-mode-host"),
                ]
            )
            discovered = next(
                (
                    candidate
                    for candidate in dict.fromkeys(candidates)
                    if candidate.is_file() and os.access(candidate, os.X_OK)
                ),
                None,
            )
            if discovered is not None:
                env["CODEX_CODE_MODE_HOST_PATH"] = str(discovered)
        return env

    def runtime_contract(self) -> CodexAppServerRuntimeContract:
        if self._runtime_contract is not None:
            return self._runtime_contract
        codex_home = self._resolve_codex_home()
        requested = self._requested_codex_home or codex_home
        self._runtime_contract = CodexAppServerRuntimeContract(
            codex_bin=self.codex_bin,
            codex_version=self._codex_version,
            minimum_codex_version=self._minimum_codex_version,
            model=self._model,
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
        codex_version = _read_codex_cli_version(codex_bin_path)
        minimum_version = minimum_app_server_version()
        parsed_minimum_version = parse_codex_cli_version(f"codex-cli {minimum_version}")
        self._codex_version = codex_version
        self._minimum_codex_version = parsed_minimum_version
        version_diagnostics = {
            "codexBinPath": codex_bin_path,
            "codexVersion": codex_version,
            "minimumCodexVersion": parsed_minimum_version,
            "model": self._model,
        }
        if not _codex_version_at_least(codex_version, parsed_minimum_version):
            raise CodexAppServerError(
                f"ToC requires Codex CLI >= {parsed_minimum_version}; found {codex_version}. "
                "Upgrade the Codex CLI before starting the app-server (for Homebrew: brew upgrade --cask codex).",
                diagnostics=version_diagnostics,
            )
        codex_home = self._resolve_codex_home()
        checks: dict[str, Any] = {
            "status": "passed",
            **version_diagnostics,
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
        self._stopping = False
        self._transport_error = None
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
            limit=self._jsonl_limit_bytes,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        self._reader_task.add_done_callback(_consume_task_exception)
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
        if self._require_chatgpt_account:
            account_result = await self.request(
                "account/read",
                {"refreshToken": False},
            )
            account = account_result.get("account") if isinstance(account_result, dict) else None
            account_type = str(account.get("type") or "").strip().lower() if isinstance(account, dict) else ""
            plan_type = str(account.get("planType") or "").strip().lower() if isinstance(account, dict) else ""
            self._account_type = account_type or None
            self._account_plan_type = plan_type or None
            if account_type != "chatgpt":
                raise CodexAppServerError(
                    "image generation requires ChatGPT account authentication; API-key authentication is disabled"
                )
            if self._require_chatgpt_pro and "pro" not in plan_type:
                raise CodexAppServerError(
                    f"image generation requires a ChatGPT Pro account; current plan is {plan_type or 'unknown'}"
                )

    async def stop(self) -> None:
        if self.proc is None:
            return
        self._stopping = True
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
            reader_task = self._reader_task
            self._reader_task = None
            if not reader_task.done():
                reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, CodexAppServerError):
                await reader_task
        if self._stderr_task:
            stderr_task = self._stderr_task
            self._stderr_task = None
            if not stderr_task.done():
                stderr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stderr_task

    def _record_transport_error(self, error: CodexAppServerTransportError) -> None:
        if self._transport_error is None:
            self._transport_error = error
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(self._transport_error)
        self._pending.clear()

    async def _read_loop(self) -> None:
        assert self.proc and self.proc.stdout
        frame_bytes = 0
        try:
            while True:
                line = await self.proc.stdout.readline()
                if not line:
                    break
                frame_bytes = len(line)
                try:
                    decoded = json.loads(line.decode("utf-8"))
                except UnicodeDecodeError as exc:
                    raise ValueError(
                        f"Codex app-server emitted a non-UTF-8 JSONL frame ({frame_bytes} bytes)"
                    ) from exc
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Codex app-server emitted an invalid JSONL frame ({frame_bytes} bytes)"
                    ) from exc
                if not isinstance(decoded, dict):
                    raise ValueError(
                        f"Codex app-server emitted a non-object JSONL frame ({frame_bytes} bytes)"
                    )
                message = _compact_image_generation_payload(decoded)
                if "id" in message:
                    future = self._pending.pop(int(message["id"]), None)
                    if future and not future.done():
                        future.set_result(message)
                else:
                    await self._notifications.put(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error = CodexAppServerTransportError(
                self._format_process_error(
                    f"Codex app-server stdout reader failed: {type(exc).__name__}: {exc}"
                ),
                diagnostics={
                    "jsonlReaderLimitBytes": self._jsonl_limit_bytes,
                    "jsonlFrameBytes": frame_bytes,
                },
            )
            self._record_transport_error(error)
            return
        if not self._stopping:
            error = CodexAppServerTransportError(
                self._format_process_error("Codex app-server closed stdout"),
                diagnostics={"jsonlReaderLimitBytes": self._jsonl_limit_bytes},
            )
            self._record_transport_error(error)

    async def _next_notification(self, *, timeout: float) -> dict[str, Any]:
        if not self._notifications.empty():
            return self._notifications.get_nowait()
        if self._transport_error is not None:
            raise self._transport_error

        notification_task = asyncio.create_task(self._notifications.get())
        reader_task = self._reader_task
        waiters: set[asyncio.Task[Any]] = {notification_task}
        if reader_task is not None:
            waiters.add(reader_task)
        done, _pending = await asyncio.wait(
            waiters,
            timeout=max(0.0, timeout),
            return_when=asyncio.FIRST_COMPLETED,
        )
        if notification_task in done:
            return notification_task.result()
        if not self._notifications.empty():
            notification_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await notification_task
            return self._notifications.get_nowait()
        notification_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await notification_task
        if not done:
            raise asyncio.TimeoutError
        if self._transport_error is not None:
            raise self._transport_error
        error = CodexAppServerTransportError(
            self._format_process_error("Codex app-server notification reader stopped"),
            diagnostics={"jsonlReaderLimitBytes": self._jsonl_limit_bytes},
        )
        self._record_transport_error(error)
        raise error

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
            "jsonlReaderLimitBytes": self._jsonl_limit_bytes,
            "readerTaskDone": self._reader_task.done() if self._reader_task is not None else None,
            "transportError": str(self._transport_error) if self._transport_error is not None else None,
            "sensitiveEnvScrubbed": self._scrub_sensitive_env,
            "accountType": self._account_type,
            "accountPlanType": self._account_plan_type,
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
        if self._transport_error is not None:
            raise self._transport_error
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
        if self._transport_error is not None:
            raise self._transport_error
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
        sandbox: str = "workspace-write",
        developer_instructions: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> str:
        if sandbox not in {"read-only", "workspace-write"}:
            raise ValueError(f"unsupported app-server sandbox: {sandbox}")
        params: dict[str, Any] = {
            "cwd": str(cwd or self.cwd),
            "approvalPolicy": approval_policy,
            "sandbox": sandbox,
        }
        effective_model = model or default_app_server_model()
        self._model = effective_model
        self._runtime_contract = None
        params["model"] = effective_model
        if developer_instructions is not None:
            if not developer_instructions.strip():
                raise ValueError("developer_instructions must not be empty")
            params["developerInstructions"] = developer_instructions
        if config is not None:
            params["config"] = json.loads(json.dumps(config))
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
        output_schema: dict[str, Any] | None = None,
        return_on_completed_image_generation: bool = False,
    ) -> list[dict[str, Any]]:
        input_items: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for skill in skills or []:
            input_items.append({"type": "skill", "name": skill.parent.name, "path": str(skill)})
        for image in local_images or []:
            input_items.append({"type": "localImage", "path": str(image)})
        params: dict[str, Any] = {
            "threadId": thread_id,
            "cwd": str(cwd or self.cwd),
            "input": input_items,
        }
        if output_schema is not None:
            params["outputSchema"] = json.loads(json.dumps(output_schema))
        result = await self.request("turn/start", params)
        turn_id = str((result.get("turn") or {}).get("id") or "")
        transcript: list[dict[str, Any]] = []
        deadline = time.monotonic() + max(1, timeout_seconds)
        while True:
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise asyncio.TimeoutError
                notification = await self._next_notification(timeout=remaining)
            except CodexAppServerTransportError as exc:
                recovered_transcript = [*transcript, *getattr(exc, "transcript", [])]
                diagnostics = dict(getattr(exc, "diagnostics", {}) or {})
                diagnostics.update({"threadId": thread_id, "turnId": turn_id})
                raise CodexAppServerTransportError(
                    str(exc),
                    transcript=recovered_transcript,
                    diagnostics=diagnostics,
                ) from exc
            except asyncio.TimeoutError as exc:
                raise CodexAppServerTransportError("turn timed out", transcript=transcript, diagnostics=self.diagnostics()) from exc
            params = notification.get("params") or {}
            if turn_id and params.get("turnId") not in {None, turn_id}:
                continue
            transcript.append(notification)
            if progress_callback is not None:
                progress_callback(notification)
            if reset_timeout_on_notification:
                deadline = time.monotonic() + max(1, timeout_seconds)
            method = str(notification.get("method") or "").lower()
            if "approval" in method:
                raise CodexAppServerError(
                    f"turn requested interactive approval: {notification.get('method')}",
                    transcript=transcript,
                    diagnostics=self.diagnostics(),
                )
            if (
                return_on_completed_image_generation
                and turn_id
                and params.get("turnId") == turn_id
                and notification.get("method") == "item/completed"
            ):
                item = params.get("item")
                if (
                    isinstance(item, dict)
                    and item.get("type") == "imageGeneration"
                    and str(item.get("status") or "").strip().lower() == "completed"
                    and image_generation_saved_path(item)
                ):
                    return transcript
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

    async def _read_thread_for_transport_recovery(self, thread_id: str) -> dict[str, Any]:
        """Read a turn through a fresh transport when the stdout reader died."""

        restarted = False
        if self._transport_error is not None:
            await self.stop()
            await self.start()
            restarted = True
        try:
            return await self.request(
                "thread/read",
                {"threadId": thread_id, "includeTurns": True},
            )
        except CodexAppServerTransportError:
            if restarted:
                raise
            await self.stop()
            await self.start()
            return await self.request(
                "thread/read",
                {"threadId": thread_id, "includeTurns": True},
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
        request_bound_v2 = str(provenance_policy or "").strip().lower() == "request_bound_v2"
        use_generated_images_fallback = allow_generated_images_fallback and not request_bound_v2
        generated_root = self.generated_images_root() if use_generated_images_fallback else None
        cutoff_ns = (
            fallback_cutoff_ns
            if fallback_cutoff_ns is not None
            else latest_generated_image_mtime_ns(generated_root)
            if generated_root is not None
            else 0
        )
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
                return_on_completed_image_generation=True,
            )
        )
        turn_task.add_done_callback(_consume_task_exception)
        fallback_task: asyncio.Task[Path | None] | None = None
        tasks: set[asyncio.Task[Any]] = {turn_task}
        if use_generated_images_fallback and generated_root is not None:
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
        transport_error: CodexAppServerTransportError | None = None
        try:
            transcript = await turn_task
        except CodexAppServerTransportError as exc:
            transport_error = exc
            transcript = list(exc.transcript)

            def completed_saved_item_exists(events: list[dict[str, Any]]) -> bool:
                return any(
                    str(image_item.get("status") or "").strip().lower() == "completed"
                    and bool(image_generation_saved_path(image_item))
                    for event in events
                    for image_item in find_image_generation_items(event)
                )

            if not completed_saved_item_exists(transcript):
                recovered_turn_id = _extract_turn_id(transcript)
                try:
                    thread_result = await asyncio.wait_for(
                        self._read_thread_for_transport_recovery(thread_id),
                        timeout=max(1, min(30, timeout_seconds)),
                    )
                except Exception:
                    thread_result = {}
                thread = thread_result.get("thread") if isinstance(thread_result, dict) else None
                turns = thread.get("turns") if isinstance(thread, dict) else None
                recovered_turn: dict[str, Any] | None = None
                if isinstance(turns, list):
                    if recovered_turn_id:
                        recovered_turn = next(
                            (
                                turn
                                for turn in turns
                                if isinstance(turn, dict)
                                and str(turn.get("id") or "") == recovered_turn_id
                            ),
                            None,
                        )
                    else:
                        recovered_turn = next(
                            (
                                turn
                                for turn in reversed(turns)
                                if isinstance(turn, dict)
                                and any(
                                    str(item.get("status") or "").strip().lower() == "completed"
                                    and bool(image_generation_saved_path(item))
                                    for item in (turn.get("items") or [])
                                    if isinstance(item, dict) and item.get("type") == "imageGeneration"
                                )
                            ),
                            None,
                        )
                if recovered_turn is not None:
                    recovered_turn_id = str(recovered_turn.get("id") or recovered_turn_id or "")
                    transcript.append(
                        {
                            "method": "turn/recovered",
                            "params": {
                                "turnId": recovered_turn_id,
                                "turn": recovered_turn,
                            },
                        }
                    )
            if not completed_saved_item_exists(transcript):
                raise transport_error
        turn_id = _extract_turn_id(transcript)
        image_items: list[dict[str, Any]] = []
        for message in transcript:
            image_items.extend(find_image_generation_items(message))
        distinct_image_items: dict[str, dict[str, Any]] = {}
        for image_item in image_items:
            explicit_id = str(
                image_item.get("id")
                or image_item.get("itemId")
                or image_item.get("item_id")
                or ""
            ).strip()
            identity = explicit_id or hashlib.sha256(
                json.dumps(image_item, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
            distinct_image_items[identity] = image_item
        if len(distinct_image_items) > 1 and not use_generated_images_fallback:
            raise CodexAppServerError(
                "request-bound image generation requires exactly one distinct imageGeneration item",
                diagnostics={
                    "generationJobId": generation_job_id,
                    "itemId": item_id,
                    "turnId": turn_id,
                    "imageGenerationItemCount": len(distinct_image_items),
                    "imageGenerationItemIds": list(distinct_image_items),
                },
            )
        latest = list(distinct_image_items.values())[-1] if distinct_image_items else {}
        image_generation_item_id = str(
            latest.get("id") or latest.get("itemId") or latest.get("item_id") or ""
        ).strip() or None
        saved = image_generation_saved_path(latest)
        source = "app_server"
        if not saved:
            fallback = (
                await claim_latest_generated_image_after(cutoff_ns, root=generated_root)
                if use_generated_images_fallback and generated_root is not None
                else None
            )
            if fallback:
                saved = str(fallback)
                source = "generated_images_fallback"
        authoritative = bool(
            saved
            and source == "app_server"
            and len(distinct_image_items) == 1
            and image_generation_item_id
            and turn_id
        )
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
            image_generation_item_id=image_generation_item_id,
            image_generation_item_count=len(distinct_image_items),
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

    async def revise_first_frame_visual_plan(
        self,
        *,
        item: dict[str, Any],
        current_plan: dict[str, Any],
        instruction: str,
        setting_content: str,
        run_dir: Path,
    ) -> dict[str, Any]:
        thread_id = await self.start_thread(cwd=run_dir)
        patch_properties: dict[str, Any] = {
            key: {"type": "string"}
            for key in (
                "event_fact_visible_in_still",
                "primary_subject_name",
                "costume_state",
                "pose",
                "gaze",
                "foreground",
                "midground",
                "background",
                "light_source",
                "light_direction",
                "story_specific_texture",
            )
        }
        patch_properties["dominant_materials"] = {"type": "array", "items": {"type": "string"}}
        output_schema = {
            "type": "object",
            "properties": {
                "visual_plan_patch": {
                    "type": "object",
                    "properties": patch_properties,
                    "additionalProperties": False,
                }
            },
            "required": ["visual_plan_patch"],
            "additionalProperties": False,
        }
        text = f"""Revise one ToC compiled-v2 first-frame visual plan.

Item metadata JSON:
{json.dumps(item, ensure_ascii=False, indent=2)}

Current first_frame_visual_plan JSON:
{json.dumps(current_plan, ensure_ascii=False, indent=2)}

Permanent instruction section:
{setting_content}

User override instruction:
{instruction}

Rules:
- Return exactly the requested JSON schema.
- Change only visible first-frame presentation fields represented by the schema.
- Preserve story event, reveal timing, not-yet constraints, binding ids, references, and continuity.
- Do not add or remove characters, objects, locations, or references.
- Do not generate images and do not edit files.
"""
        transcript = await self.run_turn(
            thread_id=thread_id,
            text=text,
            cwd=run_dir,
            timeout_seconds=900,
            output_schema=output_schema,
        )
        messages: list[str] = []
        for event in transcript:
            messages.extend(find_agent_message_texts(event))
        response_text = "\n".join(messages).strip()
        match = re.search(r"\{.*\}", response_text, flags=re.DOTALL)
        if not match:
            raise CodexAppServerError("compiled-v2 visual plan revision returned no JSON object")
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise CodexAppServerError("compiled-v2 visual plan revision returned invalid JSON") from exc
        patch = payload.get("visual_plan_patch") if isinstance(payload, dict) else None
        if not isinstance(patch, dict) or not patch:
            raise CodexAppServerError("compiled-v2 visual plan revision returned an empty patch")
        return patch


def create_codex_app_server_client(
    *,
    cwd: Path,
    codex_bin: str = "codex",
    scrub_sensitive_env: bool = False,
    require_chatgpt_account: bool = False,
    require_chatgpt_pro: bool = False,
) -> CodexAppServerClient:
    return CodexAppServerClient(
        cwd=cwd,
        codex_bin=codex_bin,
        scrub_sensitive_env=scrub_sensitive_env,
        require_chatgpt_account=require_chatgpt_account,
        require_chatgpt_pro=require_chatgpt_pro,
    )


def app_server_disabled() -> bool:
    return os.environ.get("TOC_IMAGE_GEN_DISABLE_CODEX_APP_SERVER", "").lower() in {"1", "true", "yes"}


def app_server_codex_home_fallback_allowed() -> bool:
    return os.environ.get("TOC_CODEX_HOME_FALLBACK_ALLOWED", "").strip().lower() in {"1", "true", "yes", "on"}


def app_server_network_preflight_enabled() -> bool:
    return os.environ.get("TOC_CODEX_APP_SERVER_PREFLIGHT_NETWORK", "1").strip().lower() not in {"0", "false", "no", "off"}


def default_app_server_model() -> str:
    return os.environ.get("TOC_CODEX_APP_SERVER_MODEL", "").strip() or _DEFAULT_CODEX_APP_SERVER_MODEL


def minimum_app_server_version() -> str:
    return os.environ.get("TOC_CODEX_APP_SERVER_MIN_VERSION", "").strip() or _DEFAULT_CODEX_APP_SERVER_MIN_VERSION


def parse_codex_cli_version(output: str) -> str:
    match = _CODEX_CLI_VERSION_RE.search(str(output or ""))
    if not match:
        raise CodexAppServerError(
            "Could not parse Codex CLI version output",
            diagnostics={"codexVersionOutput": str(output or "")},
        )
    return str(match.group("version"))


def _parse_semver(version: str) -> tuple[tuple[int, int, int], str | None]:
    match = _SEMVER_RE.fullmatch(version)
    if not match:
        raise CodexAppServerError(
            f"Invalid Codex CLI semantic version: {version}",
            diagnostics={"codexVersion": version},
        )
    core = int(match.group("major")), int(match.group("minor")), int(match.group("patch"))
    return core, match.group("prerelease")


def _prerelease_sort_key(prerelease: str) -> tuple[tuple[int, int | str], ...]:
    return tuple((0, int(part)) if part.isdigit() else (1, part) for part in prerelease.split("."))


def _codex_version_at_least(actual: str, minimum: str) -> bool:
    actual_core, actual_prerelease = _parse_semver(actual)
    minimum_core, minimum_prerelease = _parse_semver(minimum)
    if actual_core != minimum_core:
        return actual_core > minimum_core
    if actual_prerelease is None:
        return True
    if minimum_prerelease is None:
        return False
    return _prerelease_sort_key(actual_prerelease) >= _prerelease_sort_key(minimum_prerelease)


def _read_codex_cli_version(codex_bin_path: str) -> str:
    try:
        completed = subprocess.run(
            [codex_bin_path, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CodexAppServerError(
            f"Could not execute Codex CLI version check: {exc}",
            diagnostics={"codexBinPath": codex_bin_path},
        ) from exc
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        raise CodexAppServerError(
            f"Codex CLI version check failed with exit code {completed.returncode}",
            diagnostics={
                "codexBinPath": codex_bin_path,
                "codexVersionOutput": output,
                "returncode": completed.returncode,
            },
        )
    return parse_codex_cli_version(output)


def classify_codex_transport_error(message: str) -> str:
    normalized = " ".join(str(message or "").lower().split())
    if not normalized:
        return ""
    if "semantic review output contract" in normalized:
        return "output_contract_failed"
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
