"""Canonical delta-event primitives for ToC run state.

It owns the event format, streaming reducer, bounded materialized view, and the
lock-held filesystem transaction used by every production reader and writer.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import uuid
import datetime as dt
import warnings
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Callable, Mapping, TypeVar

from toc.run_root_binding import (
    RunFilePostAppendError,
    current_run_root_binding,
    read_run_file_bytes,
    run_file_append_transaction,
    write_run_file_text,
)


DELTA_MARKER = "# toc.state.delta.v1 "
DELIMITER = b"---\n"
LEGACY_CRLF_DELIMITER = b"---\r\n"
HASH_PREFIX = "sha256:"
HASH_DOMAIN = b"toc.state.delta.v1\0"
CURRENT_VIEW_SCHEMA = "toc.state.current.v1"
CURRENT_VIEW_STATE_DOMAIN = b"toc.state.current.v1.state\0"
REQUEST_HASH_DOMAIN = b"toc.state.delta.v1.request\0"
MAX_BLOCK_BYTES = 16 * 1024 * 1024
MAX_EVENT_COUNT = 100_000
MAX_METADATA_BYTES = 16 * 1024
MAX_KEY_LENGTH = 512
MAX_VALUE_LENGTH = 1_000_000
CURRENT_VIEW_FILENAME = "state.current.json"
RECENT_EVENT_LIMIT = 128
MAX_RECENT_EVENT_INDEX_BYTES = 2 * 1024 * 1024
MAX_CURRENT_VIEW_BYTES = 32 * 1024 * 1024
MAX_CURRENT_STATE_BYTES = 24 * 1024 * 1024
MAX_UPDATE_BYTES = 16 * 1024 * 1024
MAX_STATE_KEYS = 100_000
STATE_KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
LINE_SEPARATOR_RE = re.compile(r"[\r\n\v\f\x1c-\x1e\x85\u2028\u2029]+")
T = TypeVar("T")


class StateLogIntegrityError(ValueError):
    """Raised when a committed state transaction is malformed or tampered."""


class StateViewError(ValueError):
    """Raised when a derived current-state view is stale or malformed."""


class NoStateChange(ValueError):
    """Raised when a normal state update has no effective changed keys."""


@dataclass(frozen=True)
class StateHead:
    sequence: int
    event_hash: str
    committed_bytes: int


@dataclass(frozen=True)
class StateReplay:
    state: dict[str, str]
    head: StateHead
    incomplete_tail: bool
    events: tuple[DeltaCommit, ...] = ()


@dataclass(frozen=True)
class DeltaCommit:
    event_id: str
    sequence: int
    event_hash: str
    event_type: str
    request_hash: str
    changed_keys: tuple[str, ...]
    encoded_bytes: int


def _sha256(data: bytes) -> str:
    return HASH_PREFIX + hashlib.sha256(data).hexdigest()


def _canonical_json(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _event_hash(metadata_without_hash: Mapping[str, object], payload: bytes) -> str:
    return _sha256(
        HASH_DOMAIN
        + DELTA_MARKER.encode("utf-8")
        + _canonical_json(metadata_without_hash)
        + b"\n"
        + payload
        + DELIMITER
    )


def _clean_value(value: object) -> str:
    return LINE_SEPARATOR_RE.sub(" ", str(value)).strip()


def _validate_key(key: object) -> str:
    cleaned = str(key).strip()
    if (
        len(cleaned) > MAX_KEY_LENGTH
        or STATE_KEY_RE.fullmatch(cleaned) is None
    ):
        raise ValueError(f"invalid state key: {key!r}")
    return cleaned


def _validate_parsed_value(value: str) -> str:
    if len(value) > MAX_VALUE_LENGTH or LINE_SEPARATOR_RE.search(value):
        raise StateLogIntegrityError("state value contains an invalid separator")
    return value


def _clean_updates(updates: Mapping[str, object]) -> dict[str, str]:
    if len(updates) > MAX_STATE_KEYS:
        raise ValueError("state update key count exceeds limit")
    cleaned: dict[str, str] = {}
    total_bytes = 0
    for raw_key, raw_value in updates.items():
        key = _validate_key(raw_key)
        value = _clean_value(raw_value)
        if len(value) > MAX_VALUE_LENGTH:
            raise ValueError(f"state value exceeds size limit: {key}")
        total_bytes += len(key.encode("utf-8")) + len(value.encode("utf-8")) + 2
        if total_bytes > MAX_UPDATE_BYTES:
            raise ValueError("state update exceeds aggregate size limit")
        cleaned[key] = value
    return cleaned


def _event_index_size(event: DeltaCommit) -> int:
    return (
        192
        + len(event.event_id.encode("utf-8"))
        + len(event.event_type.encode("utf-8"))
        + sum(len(key.encode("utf-8")) + 4 for key in event.changed_keys)
    )


def _bounded_recent_events(events: tuple[DeltaCommit, ...]) -> tuple[DeltaCommit, ...]:
    bounded: deque[DeltaCommit] = deque(maxlen=RECENT_EVENT_LIMIT)
    total_bytes = 0
    for original in events[-RECENT_EVENT_LIMIT:]:
        event = original
        footprint = _event_index_size(event)
        if footprint > MAX_RECENT_EVENT_INDEX_BYTES:
            event = DeltaCommit(
                event_id=event.event_id,
                sequence=event.sequence,
                event_hash=event.event_hash,
                event_type=event.event_type,
                request_hash=event.request_hash,
                changed_keys=(),
                encoded_bytes=event.encoded_bytes,
            )
            footprint = _event_index_size(event)
        while bounded and total_bytes + footprint > MAX_RECENT_EVENT_INDEX_BYTES:
            total_bytes -= _event_index_size(bounded.popleft())
        bounded.append(event)
        total_bytes += footprint
    return tuple(bounded)


def _metadata_text(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned.encode("utf-8")) > MAX_METADATA_BYTES
        or LINE_SEPARATOR_RE.search(cleaned)
    ):
        raise ValueError(f"{label} is invalid")
    return cleaned


def _request_hash(
    event_type: str,
    updates: Mapping[str, str],
    defaults: Mapping[str, str] | None = None,
) -> str:
    return _sha256(
        REQUEST_HASH_DOMAIN
        + _canonical_json(
            {
                "event_type": event_type,
                "updates": dict(updates),
                "defaults": dict(defaults or {}),
            }
        )
    )


def _parse_assignments(payload: bytes, *, delta: bool) -> dict[str, str]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StateLogIntegrityError("state transaction is not UTF-8") from exc

    if delta and not payload.endswith(b"\n"):
        raise StateLogIntegrityError("delta payload is not newline terminated")

    updates: dict[str, str] = {}
    lines = text[:-1].split("\n") if delta else text.split("\n")
    for raw_line in lines:
        line = raw_line[:-1] if raw_line.endswith("\r") else raw_line
        if not line:
            if delta:
                raise StateLogIntegrityError("delta payload contains a blank line")
            continue
        if line.startswith("#") or "=" not in line:
            if delta:
                raise StateLogIntegrityError(
                    "delta payload contains a malformed assignment"
                )
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            if delta:
                raise StateLogIntegrityError("delta payload has an empty key")
            continue
        try:
            key = _validate_key(key)
        except ValueError as exc:
            if delta:
                raise StateLogIntegrityError(str(exc)) from exc
            continue
        if delta and key in updates:
            raise StateLogIntegrityError(
                f"duplicate key in delta transaction: {key}"
            )
        parsed_value = value.strip()
        try:
            parsed_value = _validate_parsed_value(parsed_value)
        except StateLogIntegrityError:
            if delta:
                raise
            continue
        updates[key] = parsed_value
        if len(updates) > MAX_STATE_KEYS:
            raise StateLogIntegrityError("state key count exceeds limit")
    if delta and "timestamp" not in updates:
        raise StateLogIntegrityError("delta payload is missing timestamp")
    return updates


def _replay_state_stream(
    stream: BinaryIO,
    *,
    retain_event_id: str | None = None,
) -> StateReplay:
    state: dict[str, str] = {}
    state_size_bytes = 0
    committed_bytes = 0
    sequence = 0
    head_hash = _sha256(b"")
    delta_mode = False
    seen_event_ids: set[bytes] = set()
    events: deque[DeltaCommit] = deque(maxlen=RECENT_EVENT_LIMIT)
    retained_event: DeltaCommit | None = None

    prefix_hasher = hashlib.sha256()
    block_buffer = bytearray()
    event_count = 0

    def apply_updates(updates: Mapping[str, str]) -> None:
        nonlocal state_size_bytes
        for key, value in updates.items():
            previous = state.get(key)
            if previous is None:
                state_size_bytes += len(key.encode("utf-8"))
            else:
                state_size_bytes -= len(previous.encode("utf-8"))
            state_size_bytes += len(value.encode("utf-8"))
            if state_size_bytes > MAX_CURRENT_VIEW_BYTES:
                raise StateLogIntegrityError("current state exceeds size limit")
            state[key] = value
        if len(state) > MAX_STATE_KEYS:
            raise StateLogIntegrityError("state key count exceeds limit")

    while True:
        line = stream.readline(MAX_BLOCK_BYTES + 1)
        if not line:
            break
        prefix_hasher.update(line)
        is_lf_delimiter = line == DELIMITER
        is_crlf_legacy_delimiter = line == LEGACY_CRLF_DELIMITER
        if not is_lf_delimiter and not is_crlf_legacy_delimiter:
            block_buffer.extend(line)
            if len(block_buffer) > MAX_BLOCK_BYTES:
                raise StateLogIntegrityError("state transaction exceeds size limit")
            continue

        if delta_mode and is_crlf_legacy_delimiter:
            raise StateLogIntegrityError("CRLF delimiter encountered after delta mode began")
        delimiter = line
        block = bytes(block_buffer)
        block_buffer.clear()
        committed_bytes = stream.tell()
        if not block.strip():
            if delta_mode:
                raise StateLogIntegrityError("empty block encountered after delta mode began")
            head_hash = HASH_PREFIX + prefix_hasher.hexdigest()
            continue

        first_line, separator, payload = block.partition(b"\n")
        marker = DELTA_MARKER.encode("utf-8")
        if not first_line.startswith(marker):
            if delta_mode:
                raise StateLogIntegrityError(
                    "legacy block encountered after delta mode began"
                )
            apply_updates(_parse_assignments(block, delta=False))
            head_hash = HASH_PREFIX + prefix_hasher.hexdigest()
            continue

        if not separator:
            raise StateLogIntegrityError("delta transaction has no payload")
        delta_mode = True
        event_count += 1
        if event_count > MAX_EVENT_COUNT:
            raise StateLogIntegrityError("state event count exceeds limit")
        metadata_bytes = first_line[len(marker) :]
        if len(metadata_bytes) > MAX_METADATA_BYTES:
            raise StateLogIntegrityError("delta transaction metadata exceeds size limit")
        try:
            metadata = json.loads(metadata_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StateLogIntegrityError(
                "delta transaction metadata is invalid"
            ) from exc
        if not isinstance(metadata, dict):
            raise StateLogIntegrityError("delta transaction metadata is not an object")
        if metadata_bytes != _canonical_json(metadata):
            raise StateLogIntegrityError("delta transaction metadata is not canonical")

        required = {
            "committed_at",
            "event_hash",
            "event_id",
            "event_type",
            "occurred_at",
            "prev_hash",
            "request_hash",
            "seq",
            "state_hash",
        }
        if set(metadata) != required:
            raise StateLogIntegrityError(
                "delta transaction metadata keys are invalid"
            )
        string_fields = (
            "committed_at",
            "event_hash",
            "event_id",
            "event_type",
            "occurred_at",
            "prev_hash",
            "request_hash",
            "state_hash",
        )
        if any(
            not isinstance(metadata[field], str)
            or not metadata[field]
            or len(metadata[field]) > MAX_METADATA_BYTES
            or LINE_SEPARATOR_RE.search(metadata[field])
            for field in string_fields
        ):
            raise StateLogIntegrityError("delta transaction metadata values are invalid")
        if any(
            SHA256_RE.fullmatch(metadata[field]) is None
            for field in ("event_hash", "prev_hash", "request_hash", "state_hash")
        ):
            raise StateLogIntegrityError("delta transaction metadata hash is invalid")

        event_id = metadata["event_id"]
        event_id_digest = hashlib.sha256(event_id.encode("utf-8")).digest()
        if event_id_digest in seen_event_ids:
            raise StateLogIntegrityError(f"duplicate delta event_id: {event_id}")
        seen_event_ids.add(event_id_digest)

        event_sequence = metadata["seq"]
        if type(event_sequence) is not int or event_sequence <= 0 or event_sequence != sequence + 1:
            raise StateLogIntegrityError("delta sequence is not monotonic")
        if metadata["prev_hash"] != head_hash:
            raise StateLogIntegrityError("delta previous hash does not match head")

        expected_hash = metadata["event_hash"]
        hash_input = dict(metadata)
        hash_input.pop("event_hash")
        actual_hash = _event_hash(hash_input, payload)
        if expected_hash != actual_hash:
            raise StateLogIntegrityError("delta event hash does not match payload")

        parsed_updates = _parse_assignments(payload, delta=True)
        apply_updates(parsed_updates)
        if metadata["state_hash"] != _state_digest(state):
            raise StateLogIntegrityError("delta state hash does not match reduced state")
        sequence = event_sequence
        head_hash = actual_hash
        commit = DeltaCommit(
            event_id=event_id,
            sequence=event_sequence,
            event_hash=actual_hash,
            event_type=metadata["event_type"],
            request_hash=metadata["request_hash"],
            changed_keys=tuple(
                sorted(key for key in parsed_updates if key != "timestamp")
            ),
            encoded_bytes=len(block) + len(delimiter),
        )
        bounded = _bounded_recent_events(tuple(events) + (commit,))
        events.clear()
        events.extend(bounded)
        if event_id == retain_event_id:
            retained_event = DeltaCommit(
                event_id=commit.event_id,
                sequence=commit.sequence,
                event_hash=commit.event_hash,
                event_type=commit.event_type,
                request_hash=commit.request_hash,
                changed_keys=(),
                encoded_bytes=commit.encoded_bytes,
            )

    incomplete_tail = bool(block_buffer)
    if incomplete_tail and committed_bytes == 0:
        first_line = bytes(block_buffer).partition(b"\n")[0]
        if not first_line.startswith(DELTA_MARKER.encode("utf-8")):
            # Pre-delta fixtures and early ToC runs sometimes stored one
            # delimiter-less legacy mapping.  Treat only that whole-file form
            # as committed; a tail after any delimiter remains incomplete.
            apply_updates(_parse_assignments(bytes(block_buffer), delta=False))
            committed_bytes = stream.tell()
            normalized_hasher = prefix_hasher.copy()
            if not bytes(block_buffer).endswith(b"\n"):
                normalized_hasher.update(b"\n")
            normalized_hasher.update(DELIMITER)
            head_hash = HASH_PREFIX + normalized_hasher.hexdigest()
            incomplete_tail = False

    if len(_canonical_json(state)) > MAX_CURRENT_STATE_BYTES:
        raise StateLogIntegrityError("current state exceeds size limit")
    return StateReplay(
        state=state,
        head=StateHead(
            sequence=sequence,
            event_hash=head_hash,
            committed_bytes=committed_bytes,
        ),
        incomplete_tail=incomplete_tail,
        events=(
            (retained_event,) + tuple(events)
            if retained_event is not None
            and all(event.event_id != retained_event.event_id for event in events)
            else tuple(events)
        ),
    )


def replay_state_bytes(data: bytes) -> StateReplay:
    """Replay legacy snapshot/partial blocks and v1 delta transactions."""

    return _replay_state_stream(io.BytesIO(data))


def _replay_state_descriptor(
    descriptor: int,
    *,
    retain_event_id: str | None = None,
) -> StateReplay:
    """Replay from a duplicated descriptor without materializing full history."""

    duplicate = os.dup(descriptor)
    try:
        os.lseek(duplicate, 0, os.SEEK_SET)
        with os.fdopen(duplicate, "rb", closefd=True) as stream:
            duplicate = -1
            return _replay_state_stream(stream, retain_event_id=retain_event_id)
    finally:
        if duplicate >= 0:
            os.close(duplicate)


def serialize_delta_event(
    *,
    current_state: Mapping[str, str],
    head: StateHead,
    updates: Mapping[str, object],
    event_id: str,
    event_type: str,
    occurred_at: str,
    committed_at: str,
    request_updates: Mapping[str, object] | None = None,
    request_defaults: Mapping[str, object] | None = None,
) -> tuple[bytes, DeltaCommit]:
    """Serialize one atomic multi-key delta transaction."""

    normalized_event_id = _metadata_text(event_id, label="event_id")
    normalized_event_type = _metadata_text(event_type, label="event_type")
    normalized_occurred_at = _metadata_text(occurred_at, label="occurred_at")
    normalized_committed_at = _metadata_text(committed_at, label="committed_at")
    if (
        type(head.sequence) is not int
        or head.sequence < 0
        or type(head.committed_bytes) is not int
        or head.committed_bytes < 0
        or SHA256_RE.fullmatch(head.event_hash) is None
        or head.sequence >= MAX_EVENT_COUNT
    ):
        raise ValueError("state head is invalid")

    cleaned_updates = _clean_updates(updates)
    cleaned_request_updates = _clean_updates(
        updates if request_updates is None else request_updates
    )
    cleaned_request_defaults = _clean_updates(request_defaults or {})
    changed: dict[str, str] = {}
    for key, value in cleaned_updates.items():
        if current_state.get(key) != value:
            changed[key] = value

    if not changed:
        raise NoStateChange("state update has no effective changed keys")

    payload_values = dict(changed)
    payload_values["timestamp"] = normalized_occurred_at
    payload = "".join(
        f"{key}={payload_values[key]}\n" for key in sorted(payload_values)
    ).encode("utf-8")

    metadata_without_hash: dict[str, object] = {
        "committed_at": normalized_committed_at,
        "event_id": normalized_event_id,
        "event_type": normalized_event_type,
        "occurred_at": normalized_occurred_at,
        "prev_hash": head.event_hash,
        "request_hash": _request_hash(
            normalized_event_type,
            cleaned_request_updates,
            cleaned_request_defaults,
        ),
        "seq": head.sequence + 1,
        "state_hash": _state_digest({**current_state, **changed, "timestamp": normalized_occurred_at}),
    }
    event_hash = _event_hash(metadata_without_hash, payload)
    metadata = dict(metadata_without_hash)
    metadata["event_hash"] = event_hash
    encoded = (
        DELTA_MARKER.encode("utf-8")
        + _canonical_json(metadata)
        + b"\n"
        + payload
        + DELIMITER
    )
    if len(metadata_bytes := _canonical_json(metadata)) > MAX_METADATA_BYTES:
        raise ValueError("delta transaction metadata exceeds size limit")
    if len(encoded) - len(DELIMITER) > MAX_BLOCK_BYTES:
        raise ValueError("delta transaction exceeds size limit")
    commit = DeltaCommit(
        event_id=normalized_event_id,
        sequence=head.sequence + 1,
        event_hash=event_hash,
        event_type=normalized_event_type,
        request_hash=metadata_without_hash["request_hash"],
        changed_keys=tuple(sorted(changed)),
        encoded_bytes=len(encoded),
    )
    return encoded, commit


def resolve_idempotent_event(
    replay: StateReplay,
    *,
    event_id: str,
    event_type: str,
    updates: Mapping[str, object],
    defaults: Mapping[str, object] | None = None,
) -> DeltaCommit:
    """Return an existing identical event, rejecting same-ID conflicts."""

    cleaned_updates = _clean_updates(updates)
    cleaned_defaults = _clean_updates(defaults or {})
    expected_request_hash = _request_hash(
        event_type.strip(),
        cleaned_updates,
        cleaned_defaults,
    )
    for event in reversed(replay.events):
        if event.event_id != event_id:
            continue
        if (
            event.event_type != event_type.strip()
            or event.request_hash != expected_request_hash
        ):
            raise StateLogIntegrityError(
                f"conflicting retry for delta event_id: {event_id}"
            )
        return event
    raise KeyError(event_id)


def _state_digest(state: Mapping[str, str]) -> str:
    return _sha256(CURRENT_VIEW_STATE_DOMAIN + _canonical_json(state))


def serialize_current_view(
    *,
    replay: StateReplay,
    run_root_identity: tuple[int, int],
    log_identity: tuple[int, int, int, int, int],
    generated_at: str,
) -> bytes:
    """Serialize a replaceable current-state view bound to one log head."""

    payload = {
        "schema_version": CURRENT_VIEW_SCHEMA,
        "generated_at": _clean_value(generated_at),
        "run_root_identity": [run_root_identity[0], run_root_identity[1]],
        "log_identity": list(log_identity),
        "log_cursor": {
            "committed_bytes": replay.head.committed_bytes,
            "event_hash": replay.head.event_hash,
            "sequence": replay.head.sequence,
        },
        "events": [
            {
                "changed_keys": list(event.changed_keys),
                "encoded_bytes": event.encoded_bytes,
                "event_hash": event.event_hash,
                "event_id": event.event_id,
                "event_type": event.event_type,
                "request_hash": event.request_hash,
                "sequence": event.sequence,
            }
            for event in replay.events[-RECENT_EVENT_LIMIT:]
        ],
        "state": dict(replay.state),
        "state_sha256": _state_digest(replay.state),
    }
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    if len(encoded) > MAX_CURRENT_VIEW_BYTES:
        raise ValueError("current state view exceeds size limit")
    return encoded


def parse_current_view(
    data: bytes,
    *,
    expected_run_root_identity: tuple[int, int],
    expected_head: StateHead,
    expected_log_identity: tuple[int, int, int, int, int] | None = None,
) -> dict[str, str]:
    """Validate a derived view and return a defensive current-state copy."""

    return parse_current_view_replay(
        data,
        expected_run_root_identity=expected_run_root_identity,
        expected_head=expected_head,
        expected_log_identity=expected_log_identity,
    ).state


def parse_current_view_replay(
    data: bytes,
    *,
    expected_run_root_identity: tuple[int, int],
    expected_head: StateHead | None = None,
    expected_committed_bytes: int | None = None,
    expected_log_identity: tuple[int, int, int, int, int] | None = None,
) -> StateReplay:
    """Validate a derived view and recover its state, head, and event index."""

    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateViewError("current state view is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise StateViewError("current state view is not an object")
    required = {
        "events",
        "generated_at",
        "log_cursor",
        "log_identity",
        "run_root_identity",
        "schema_version",
        "state",
        "state_sha256",
    }
    if set(payload) != required:
        raise StateViewError("current state view keys are invalid")
    if payload["schema_version"] != CURRENT_VIEW_SCHEMA:
        raise StateViewError("current state view schema is unsupported")
    if (
        not isinstance(payload["generated_at"], str)
        or not payload["generated_at"]
        or LINE_SEPARATOR_RE.search(payload["generated_at"])
    ):
        raise StateViewError("current state view generated_at is invalid")

    root_identity = payload["run_root_identity"]
    if (
        not isinstance(root_identity, list)
        or len(root_identity) != 2
        or any(type(item) is not int for item in root_identity)
        or tuple(root_identity) != expected_run_root_identity
    ):
        raise StateViewError("current state view run root does not match")

    log_identity = payload["log_identity"]
    if (
        not isinstance(log_identity, list)
        or len(log_identity) != 5
        or any(type(item) is not int or item < 0 for item in log_identity)
        or (
            expected_log_identity is not None
            and tuple(log_identity) != expected_log_identity
        )
    ):
        raise StateViewError("current state view log identity does not match")

    cursor = payload["log_cursor"]
    if not isinstance(cursor, dict) or set(cursor) != {
        "committed_bytes",
        "event_hash",
        "sequence",
    }:
        raise StateViewError("current state view cursor is invalid")
    if expected_head is not None and (
        type(cursor["committed_bytes"]) is not int
        or type(cursor["sequence"]) is not int
        or not isinstance(cursor["event_hash"], str)
        or cursor["committed_bytes"] != expected_head.committed_bytes
        or cursor["sequence"] != expected_head.sequence
        or cursor["event_hash"] != expected_head.event_hash
    ):
        raise StateViewError("current state view cursor is stale")
    if (
        type(cursor["committed_bytes"]) is not int
        or cursor["committed_bytes"] < 0
        or type(cursor["sequence"]) is not int
        or cursor["sequence"] < 0
        or cursor["sequence"] > MAX_EVENT_COUNT
        or not isinstance(cursor["event_hash"], str)
        or SHA256_RE.fullmatch(cursor["event_hash"]) is None
        or (
            expected_committed_bytes is not None
            and cursor["committed_bytes"] != expected_committed_bytes
        )
    ):
        raise StateViewError("current state view cursor is stale")

    state = payload["state"]
    if (
        not isinstance(state, dict)
        or len(state) > MAX_STATE_KEYS
        or any(
            not isinstance(key, str)
            or STATE_KEY_RE.fullmatch(key) is None
            or len(key) > MAX_KEY_LENGTH
            for key in state
        )
        or any(not isinstance(value, str) for value in state.values())
        or any(
            len(value) > MAX_VALUE_LENGTH or LINE_SEPARATOR_RE.search(value)
            for value in state.values()
        )
    ):
        raise StateViewError("current state view state is invalid")
    if len(_canonical_json(state)) > MAX_CURRENT_STATE_BYTES:
        raise StateViewError("current state view state exceeds size limit")
    if payload["state_sha256"] != _state_digest(state):
        raise StateViewError("current state view state digest does not match")

    raw_events = payload["events"]
    if (
        not isinstance(raw_events, list)
        or len(raw_events) > RECENT_EVENT_LIMIT
    ):
        raise StateViewError("current state view events are invalid")
    events: list[DeltaCommit] = []
    seen_ids: set[str] = set()
    previous_sequence: int | None = None
    for raw_event in raw_events:
        if not isinstance(raw_event, dict) or set(raw_event) != {
            "changed_keys",
            "encoded_bytes",
            "event_hash",
            "event_id",
            "event_type",
            "request_hash",
            "sequence",
        }:
            raise StateViewError("current state view event index is invalid")
        strings = (
            raw_event["event_hash"],
            raw_event["event_id"],
            raw_event["event_type"],
            raw_event["request_hash"],
        )
        changed_keys = raw_event["changed_keys"]
        if (
            any(not isinstance(item, str) or not item for item in strings)
            or SHA256_RE.fullmatch(raw_event["event_hash"]) is None
            or SHA256_RE.fullmatch(raw_event["request_hash"]) is None
            or type(raw_event["sequence"]) is not int
            or raw_event["sequence"] < 1
            or raw_event["sequence"] > MAX_EVENT_COUNT
            or (
                previous_sequence is not None
                and raw_event["sequence"] != previous_sequence + 1
            )
            or type(raw_event["encoded_bytes"]) is not int
            or raw_event["encoded_bytes"] <= 0
            or raw_event["encoded_bytes"] > MAX_BLOCK_BYTES + len(DELIMITER)
            or not isinstance(changed_keys, list)
            or any(
                not isinstance(key, str)
                or STATE_KEY_RE.fullmatch(key) is None
                for key in changed_keys
            )
            or raw_event["event_id"] in seen_ids
        ):
            raise StateViewError("current state view event index is invalid")
        previous_sequence = raw_event["sequence"]
        seen_ids.add(raw_event["event_id"])
        events.append(
            DeltaCommit(
                event_id=raw_event["event_id"],
                sequence=raw_event["sequence"],
                event_hash=raw_event["event_hash"],
                event_type=raw_event["event_type"],
                request_hash=raw_event["request_hash"],
                changed_keys=tuple(changed_keys),
                encoded_bytes=raw_event["encoded_bytes"],
            )
        )
    if events:
        if (
            events[-1].sequence != cursor["sequence"]
            or events[-1].event_hash != cursor["event_hash"]
        ):
            raise StateViewError("current state view event head is stale")
    elif cursor["sequence"] != 0:
        raise StateViewError("current state view event index is incomplete")

    return StateReplay(
        state=dict(state),
        head=StateHead(
            sequence=cursor["sequence"],
            event_hash=cursor["event_hash"],
            committed_bytes=cursor["committed_bytes"],
        ),
        incomplete_tail=False,
        events=tuple(events),
    )


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _log_identity(descriptor: int) -> tuple[int, int, int, int, int]:
    opened = os.fstat(descriptor)
    return (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
        opened.st_ctime_ns,
    )


def _validated_tail_head(
    descriptor: int,
    current_size: int,
    replay: StateReplay,
) -> StateHead:
    """Bind a materialized view to the canonical final delta in bounded I/O."""

    if replay.head.sequence == 0:
        return replay.head
    if not replay.events or replay.events[-1].sequence != replay.head.sequence:
        raise StateViewError("current view has no final event index entry")
    read_size = replay.events[-1].encoded_bytes
    if read_size > MAX_BLOCK_BYTES + len(DELIMITER) or read_size > current_size:
        raise StateViewError("canonical delta tail exceeds size limit")
    tail = os.pread(descriptor, read_size, current_size - read_size)
    if not tail.endswith(DELIMITER):
        raise StateViewError("canonical delta tail is not committed")
    block = tail[: -len(DELIMITER)]
    first_line, separator, payload = block.partition(b"\n")
    marker = DELTA_MARKER.encode("utf-8")
    if not separator or not first_line.startswith(marker):
        raise StateViewError("canonical state tail is not a delta event")
    metadata_bytes = first_line[len(marker) :]
    if len(metadata_bytes) > MAX_METADATA_BYTES:
        raise StateViewError("canonical delta tail metadata exceeds size limit")
    try:
        metadata = json.loads(metadata_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateViewError("canonical delta tail metadata is invalid") from exc
    if not isinstance(metadata, dict) or metadata_bytes != _canonical_json(metadata):
        raise StateViewError("canonical delta tail metadata is not canonical")
    required = {
        "committed_at", "event_hash", "event_id", "event_type", "occurred_at",
        "prev_hash", "request_hash", "seq", "state_hash",
    }
    if set(metadata) != required or type(metadata["seq"]) is not int:
        raise StateViewError("canonical delta tail metadata keys are invalid")
    for key in ("event_hash", "prev_hash", "request_hash", "state_hash"):
        if not isinstance(metadata[key], str) or SHA256_RE.fullmatch(metadata[key]) is None:
            raise StateViewError("canonical delta tail hash is invalid")
    hash_input = dict(metadata)
    expected_hash = hash_input.pop("event_hash")
    if _event_hash(hash_input, payload) != expected_hash:
        raise StateViewError("canonical delta tail event hash does not match")
    _parse_assignments(payload, delta=True)
    if metadata["seq"] == 1:
        # The predecessor is an arbitrary-length legacy prefix.  A one-time
        # replay is required until a second delta provides a bounded anchor.
        raise StateViewError("first delta requires canonical predecessor replay")
    if len(replay.events) < 2:
        raise StateViewError("current view has no predecessor event index entry")
    previous_index = replay.events[-2]
    previous_size = previous_index.encoded_bytes
    previous_offset = current_size - read_size - previous_size
    if (
        previous_size <= len(DELIMITER)
        or previous_size > MAX_BLOCK_BYTES + len(DELIMITER)
        or previous_offset < 0
    ):
        raise StateViewError("canonical predecessor frame size is invalid")
    previous_frame = os.pread(descriptor, previous_size, previous_offset)
    if not previous_frame.endswith(DELIMITER):
        raise StateViewError("canonical predecessor frame is not committed")
    previous_first, previous_separator, previous_payload = previous_frame[
        : -len(DELIMITER)
    ].partition(b"\n")
    marker = DELTA_MARKER.encode("utf-8")
    if not previous_separator or not previous_first.startswith(marker):
        raise StateViewError("canonical predecessor is not a delta event")
    try:
        previous_metadata = json.loads(
            previous_first[len(marker) :].decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateViewError("canonical predecessor metadata is invalid") from exc
    if (
        not isinstance(previous_metadata, dict)
        or previous_first[len(marker) :] != _canonical_json(previous_metadata)
        or type(previous_metadata.get("seq")) is not int
        or previous_metadata.get("seq") != metadata["seq"] - 1
    ):
        raise StateViewError("canonical predecessor metadata is invalid")
    previous_hash_input = dict(previous_metadata)
    previous_hash = previous_hash_input.pop("event_hash", None)
    if (
        not isinstance(previous_hash, str)
        or _event_hash(previous_hash_input, previous_payload) != previous_hash
        or previous_hash != metadata["prev_hash"]
    ):
        raise StateViewError("canonical predecessor hash does not match")
    if metadata["seq"] >= 3:
        if len(replay.events) < 3:
            raise StateViewError("current view has no predecessor anchor entry")
        anchor_size = replay.events[-3].encoded_bytes
        anchor_offset = previous_offset - anchor_size
        if (
            anchor_size <= len(DELIMITER)
            or anchor_size > MAX_BLOCK_BYTES + len(DELIMITER)
            or anchor_offset < 0
        ):
            raise StateViewError("canonical predecessor anchor size is invalid")
        anchor_frame = os.pread(descriptor, anchor_size, anchor_offset)
        if not anchor_frame.endswith(DELIMITER):
            raise StateViewError("canonical predecessor anchor is not committed")
        anchor_first, anchor_separator, anchor_payload = anchor_frame[
            : -len(DELIMITER)
        ].partition(b"\n")
        if not anchor_separator or not anchor_first.startswith(marker):
            raise StateViewError("canonical predecessor anchor is not a delta event")
        try:
            anchor_metadata = json.loads(anchor_first[len(marker) :].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StateViewError("canonical predecessor anchor is invalid") from exc
        if (
            not isinstance(anchor_metadata, dict)
            or anchor_first[len(marker) :] != _canonical_json(anchor_metadata)
            or anchor_metadata.get("seq") != metadata["seq"] - 2
        ):
            raise StateViewError("canonical predecessor anchor metadata is invalid")
        anchor_hash_input = dict(anchor_metadata)
        anchor_hash = anchor_hash_input.pop("event_hash", None)
        if (
            not isinstance(anchor_hash, str)
            or _event_hash(anchor_hash_input, anchor_payload) != anchor_hash
            or anchor_hash != previous_metadata.get("prev_hash")
        ):
            raise StateViewError("canonical predecessor anchor hash does not match")
    if (
        metadata["seq"] != replay.head.sequence
        or expected_hash != replay.head.event_hash
        or metadata["state_hash"] != _state_digest(replay.state)
    ):
        raise StateViewError("current state view does not match canonical delta tail")
    return StateHead(
        sequence=metadata["seq"],
        event_hash=expected_hash,
        committed_bytes=current_size,
    )


def _require_state_path(state_path: Path) -> tuple[Path, Path]:
    path = Path(state_path)
    if path.name != "state.txt":
        raise ValueError(f"canonical state path must be state.txt: {path}")
    return path.parent, path


def _load_or_replay_current(
    run_dir: Path,
    descriptor: int,
    current_size: int,
) -> tuple[StateReplay, bool]:
    binding = current_run_root_binding()
    if binding is None:
        raise StateViewError("state transaction has no bound run root")
    try:
        view_stat = os.stat(
            CURRENT_VIEW_FILENAME,
            dir_fd=binding.descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(view_stat.st_mode)
            or view_stat.st_nlink != 1
            or view_stat.st_size > MAX_CURRENT_VIEW_BYTES
        ):
            raise StateViewError("current state view file is unsafe or oversized")
        view_bytes = read_run_file_bytes(
            run_dir,
            CURRENT_VIEW_FILENAME,
            max_bytes=MAX_CURRENT_VIEW_BYTES,
        )
        replay = parse_current_view_replay(
            view_bytes,
            expected_run_root_identity=binding.identity,
            expected_committed_bytes=current_size,
            expected_log_identity=_log_identity(descriptor),
        )
        _validated_tail_head(descriptor, current_size, replay)
        return replay, True
    except (FileNotFoundError, StateViewError, ValueError):
        replay = _replay_state_descriptor(descriptor)
        if replay.incomplete_tail or replay.head.committed_bytes != current_size:
            raise StateLogIntegrityError(
                "canonical state log has an incomplete transaction tail"
            )
        return replay, False


def _publish_current_view(
    run_dir: Path,
    descriptor: int,
    replay: StateReplay,
    *,
    generated_at: str,
) -> None:
    binding = current_run_root_binding()
    if binding is None:
        raise StateViewError("current view publication has no bound run root")
    encoded = serialize_current_view(
        replay=replay,
        run_root_identity=binding.identity,
        log_identity=_log_identity(descriptor),
        generated_at=generated_at,
    )
    write_run_file_text(
        run_dir,
        CURRENT_VIEW_FILENAME,
        encoded.decode("utf-8"),
    )


def with_current_state(
    state_path: Path,
    callback: Callable[[StateReplay], T],
) -> T:
    """Run a reader/projection callback against one lock-held current head."""

    if not callable(callback):
        raise TypeError("current state callback must be callable")
    run_dir, path = _require_state_path(state_path)
    result: T | None = None
    called = False

    def read_locked(descriptor: int, current_size: int) -> None:
        nonlocal result, called
        replay, view_hit = _load_or_replay_current(
            run_dir,
            descriptor,
            current_size,
        )
        if not view_hit:
            _publish_current_view(
                run_dir,
                descriptor,
                replay,
                generated_at=_now_iso(),
            )
        result = callback(replay)
        called = True
        return None

    run_file_append_transaction(run_dir, path.name, read_locked)
    if not called:  # pragma: no cover - callback contract guard
        raise StateViewError("state read transaction produced no result")
    return result  # type: ignore[return-value]


def read_current_state(state_path: Path) -> StateReplay:
    """Read the validated current view, rebuilding it once when necessary."""

    return with_current_state(state_path, lambda replay: replay)


def append_state_delta(
    state_path: Path,
    updates: Mapping[str, object],
    *,
    event_id: str | None = None,
    event_type: str = "state.updated",
    occurred_at: str | None = None,
    committed_at: str | None = None,
    defaults: Mapping[str, object] | None = None,
) -> StateReplay:
    """Atomically merge, append one delta event, and publish its current view."""

    run_dir, path = _require_state_path(state_path)
    effective_event_id = _metadata_text(
        str(uuid.uuid4()) if event_id is None else event_id,
        label="event_id",
    )
    explicit_event_id = event_id is not None
    effective_occurred_at = _metadata_text(
        _now_iso() if occurred_at is None else occurred_at,
        label="occurred_at",
    )
    effective_committed_at = _metadata_text(
        _now_iso() if committed_at is None else committed_at,
        label="committed_at",
    )
    event_type = _metadata_text(event_type, label="event_type")
    requested_updates = _clean_updates(updates)
    requested_defaults = _clean_updates(defaults or {})
    result: StateReplay | None = None
    pending: StateReplay | None = None

    def merge_locked(descriptor: int, current_size: int) -> bytes | None:
        nonlocal result, pending
        current, view_hit = _load_or_replay_current(
            run_dir,
            descriptor,
            current_size,
        )
        has_lf_delimiter = (
            current_size >= len(DELIMITER)
            and os.pread(
                descriptor,
                len(DELIMITER),
                current_size - len(DELIMITER),
            )
            == DELIMITER
        )
        has_crlf_legacy_delimiter = (
            current.head.sequence == 0
            and current_size >= len(LEGACY_CRLF_DELIMITER)
            and os.pread(
                descriptor,
                len(LEGACY_CRLF_DELIMITER),
                current_size - len(LEGACY_CRLF_DELIMITER),
            ) == LEGACY_CRLF_DELIMITER
        )
        has_delimiter = has_lf_delimiter or has_crlf_legacy_delimiter
        if current_size and not has_delimiter and current.head.sequence != 0:
            raise StateLogIntegrityError(
                "delta state log is not terminated by a transaction delimiter"
            )
        legacy_delimiter = b""
        if current_size and not has_delimiter:
            if os.pread(descriptor, 1, current_size - 1) != b"\n":
                legacy_delimiter += b"\n"
            legacy_delimiter += DELIMITER
        if explicit_event_id:
            retry_source = _replay_state_descriptor(
                descriptor,
                retain_event_id=effective_event_id,
            )
            if retry_source.head != current.head:
                raise StateLogIntegrityError(
                    "current view head changed during retry lookup"
                )
            try:
                resolve_idempotent_event(
                    retry_source,
                    event_id=effective_event_id,
                    event_type=event_type,
                    updates=requested_updates,
                    defaults=requested_defaults,
                )
            except KeyError:
                pass
            else:
                result = current
                return None

        effective_updates = {
            key: value
            for key, value in requested_defaults.items()
            if not current.state.get(key, "").strip()
        }
        effective_updates.update(requested_updates)
        try:
            encoded, commit = serialize_delta_event(
                current_state=current.state,
                head=current.head,
                updates=effective_updates,
                event_id=effective_event_id,
                event_type=event_type,
                occurred_at=effective_occurred_at,
                committed_at=effective_committed_at,
                request_updates=requested_updates,
                request_defaults=requested_defaults,
            )
        except NoStateChange:
            if not view_hit:
                _publish_current_view(
                    run_dir,
                    descriptor,
                    current,
                    generated_at=effective_committed_at,
                )
            result = current
            return None
        next_state = dict(current.state)
        next_state.update(effective_updates)
        next_state["timestamp"] = _clean_value(effective_occurred_at)
        if len(_canonical_json(next_state)) > MAX_CURRENT_STATE_BYTES:
            raise ValueError("current state exceeds size limit")
        pending = StateReplay(
            state=next_state,
            head=StateHead(
                sequence=commit.sequence,
                event_hash=commit.event_hash,
                committed_bytes=current_size + len(legacy_delimiter) + len(encoded),
            ),
            incomplete_tail=False,
            events=_bounded_recent_events(current.events + (commit,)),
        )
        return legacy_delimiter + encoded

    def publish_locked(descriptor: int, new_size: int) -> None:
        nonlocal result
        if pending is None or pending.head.committed_bytes != new_size:
            raise StateViewError("committed delta does not match pending current view")
        _publish_current_view(
            run_dir,
            descriptor,
            pending,
            generated_at=effective_committed_at,
        )
        result = pending

    try:
        run_file_append_transaction(
            run_dir,
            path.name,
            merge_locked,
            post_append=publish_locked,
        )
    except RunFilePostAppendError as exc:
        if pending is None:
            raise
        warnings.warn(
            "state delta committed but current view publication failed; the "
            f"view will be rebuilt from canonical history: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        result = pending
    if result is None:  # pragma: no cover - callback contract guard
        raise StateViewError("state append transaction produced no result")
    return result
