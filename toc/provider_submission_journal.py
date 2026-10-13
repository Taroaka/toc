"""Crash-safe, request-scoped submit receipts for paid video providers.

The journal intentionally stores only a provider name, a request digest, and an
accepted operation id. Request bodies, credentials, provider responses, and
media URLs never enter the journal.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import urlsplit

from scripts.world_walk_source import (
    directory_identity_nofollow,
    ensure_directory_relative_nofollow,
    open_directory_nofollow,
    read_regular_file_nofollow,
    write_regular_file_nofollow,
)
from toc.run_root_binding import require_bound_run_root
from toc.runtime_locks import sync_file_lock


_SCHEMA = "toc.provider_submission.v1"
_PROVIDERS = {"kling", "seedance"}
_ACTIVE_SCOPE: ContextVar["ProviderSubmissionScope | None"] = ContextVar(
    "toc_provider_submission_scope", default=None
)


class ProviderSubmissionJournalError(RuntimeError):
    """The saved provider submission receipt is invalid or unsafe to use."""


class UnknownSubmissionStateError(ProviderSubmissionJournalError):
    """A POST may have reached the provider, but no durable id was saved."""


class ProviderSubmissionScope:
    """Run-root-bound context for one candidate's provider submission."""

    def __init__(self, run_dir: Path, *, provider: str, scope: str):
        if provider not in _PROVIDERS:
            raise ValueError(f"unsupported provider submission journal: {provider}")
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError("provider submission scope must be non-empty")
        self.run_dir = Path(run_dir)
        binding = require_bound_run_root(self.run_dir)
        self.root_identity = (
            binding.identity if binding is not None else directory_identity_nofollow(self.run_dir)
        )
        self.provider = provider
        # Scope is used only as a hash input and is never written to disk.
        self.scope = scope

    def request_hash(self, *, payload: dict[str, Any], endpoint: str) -> str:
        if not isinstance(payload, dict):
            raise ValueError("provider submission payload must be an object")
        material = {
            "provider": self.provider,
            "scope": self.scope,
            "endpoint": str(endpoint),
            "payload": payload,
        }
        canonical = json.dumps(
            material,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def submit_or_resume(
        self,
        *,
        payload: dict[str, Any],
        endpoint: str,
        submit: Callable[[], dict[str, Any]],
        extract_id: Callable[[dict[str, Any]], str],
    ) -> tuple[dict[str, Any], str]:
        request_hash = self.request_hash(payload=payload, endpoint=endpoint)
        relative_dir = f"logs/providers/{self.provider}_submissions"
        journal_relative = f"{relative_dir}/{request_hash}.json"
        lock_path = self.run_dir / ".locks" / "provider-submission" / self.provider / f"{request_hash}.lock"

        ensure_directory_relative_nofollow(
            self.run_dir,
            relative_dir,
            expected_root_identity=self.root_identity,
        )
        with self._run_scoped_lock(lock_path):
            existing = self._read_record(journal_relative, request_hash)
            if existing is not None:
                if existing["state"] == "accepted":
                    operation_id = str(existing["operation_id"])
                    # Keep the adapter's ordinary submit-response contract so
                    # its returned result remains compatible after a restart.
                    resumed_response: dict[str, Any] = (
                        {"data": {"id": operation_id}}
                        if self.provider == "kling"
                        else {"id": operation_id}
                    )
                    return resumed_response, operation_id
                raise UnknownSubmissionStateError(
                    "provider submission outcome is unknown; automatic resubmission is disabled"
                )

            self._write_record(
                journal_relative,
                {
                    "schema": _SCHEMA,
                    "provider": self.provider,
                    "request_hash": request_hash,
                    "state": "intent",
                    "operation_id": None,
                },
            )

            # Keep the cross-process lock through POST and id persistence. If
            # this raises or the process dies before the id is saved, the
            # durable intent makes the next attempt fail closed.
            response = submit()
            try:
                operation_id = extract_id(response)
            except Exception as exc:
                raise UnknownSubmissionStateError(
                    "provider accepted or may have accepted the request, but its operation id could not be read"
                ) from exc
            operation_id = _validate_operation_id(operation_id)
            self._write_record(
                journal_relative,
                {
                    "schema": _SCHEMA,
                    "provider": self.provider,
                    "request_hash": request_hash,
                    "state": "accepted",
                    "operation_id": operation_id,
                },
            )
            return response, operation_id

    def _read_record(
        self, relative_path: str, request_hash: str
    ) -> dict[str, Any] | None:
        try:
            raw = read_regular_file_nofollow(
                self.run_dir,
                relative_path,
                expected_root_identity=self.root_identity,
            )
        except FileNotFoundError:
            return None
        if len(raw) > 16 * 1024:
            raise ProviderSubmissionJournalError("provider submission journal is too large")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderSubmissionJournalError("provider submission journal is invalid") from exc
        if (
            not isinstance(data, dict)
            or set(data)
            != {"schema", "provider", "request_hash", "state", "operation_id"}
            or data.get("schema") != _SCHEMA
            or data.get("provider") != self.provider
            or data.get("request_hash") != request_hash
            or data.get("state") not in {"intent", "accepted"}
        ):
            raise ProviderSubmissionJournalError("provider submission journal does not match its request")
        if data["state"] == "intent" and data["operation_id"] is not None:
            raise ProviderSubmissionJournalError("provider submission intent has an unexpected operation id")
        if data["state"] == "accepted":
            try:
                data["operation_id"] = _validate_operation_id(data["operation_id"])
            except ValueError as exc:
                raise ProviderSubmissionJournalError("provider submission journal has an invalid operation id") from exc
        return data

    def _write_record(self, relative_path: str, data: dict[str, Any]) -> None:
        encoded = (json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        write_regular_file_nofollow(
            destination_root=self.run_dir,
            destination_relative=relative_path,
            expected_destination_root_identity=self.root_identity,
            data=encoded,
        )

    @contextmanager
    def _run_scoped_lock(self, lock_path: Path) -> Iterator[None]:
        root_descriptor = open_directory_nofollow(
            self.run_dir,
            expected_identity=self.root_identity,
        )
        try:
            with sync_file_lock(
                lock_path,
                run_root_descriptor=root_descriptor,
                expected_run_root_identity=self.root_identity,
            ):
                yield
        finally:
            os.close(root_descriptor)


def _validate_operation_id(value: Any) -> str:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError("provider operation id must be a string or integer")
    operation_id = str(value).strip()
    if not operation_id or len(operation_id) > 1024 or any(ord(char) < 32 for char in operation_id):
        raise ValueError("provider operation id is empty or malformed")
    parsed = urlsplit(operation_id)
    if parsed.scheme.lower() in {"http", "https"} or "?" in operation_id or "#" in operation_id:
        raise ValueError("provider operation id must not be a URL or contain query data")
    return operation_id


@contextmanager
def provider_submission_scope(
    run_dir: Path, *, provider: str, scope: str
) -> Iterator[ProviderSubmissionScope]:
    journal_scope = ProviderSubmissionScope(run_dir, provider=provider, scope=scope)
    token: Token[ProviderSubmissionScope | None] = _ACTIVE_SCOPE.set(journal_scope)
    try:
        yield journal_scope
    finally:
        _ACTIVE_SCOPE.reset(token)


def current_provider_submission_scope() -> ProviderSubmissionScope | None:
    return _ACTIVE_SCOPE.get()


def submit_provider_request(
    *,
    provider: str,
    payload: dict[str, Any] | None,
    endpoint: str,
    submit: Callable[[], dict[str, Any]],
    extract_id: Callable[[dict[str, Any]], str],
) -> tuple[dict[str, Any], str]:
    """Submit once or return a saved accepted id for the active candidate."""

    scope = current_provider_submission_scope()
    if scope is None:
        response = submit()
        return response, str(extract_id(response))
    if provider != scope.provider:
        raise ProviderSubmissionJournalError("provider does not match active submission scope")
    if payload is None:
        raise ValueError("provider request payload is required for journaled submission")
    return scope.submit_or_resume(
        payload=payload,
        endpoint=endpoint,
        submit=submit,
        extract_id=extract_id,
    )
