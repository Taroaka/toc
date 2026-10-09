"""Append-only, byte-bound human observations about media candidates."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.world_walk_source import read_regular_file_nofollow
from toc.image_request_snapshot import write_run_file_atomic_nofollow


class CandidateNotesError(ValueError):
    """Candidate note data is invalid, stale, or has a revision conflict."""


NOTES_FILENAME = "candidate_notes.json"
SCHEMA_VERSION = "candidate_notes_v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ITEM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_path(root: Path, value: str | Path, *, field: str) -> tuple[str, Path]:
    raw = str(value)
    relative = PurePosixPath(raw)
    if not raw or relative.is_absolute() or "\\" in raw or any(p in ("", ".", "..") for p in relative.parts):
        raise CandidateNotesError(f"{field} must be a safe run-relative path")
    if relative.parts and ":" in relative.parts[0]:
        raise CandidateNotesError(f"{field} must be a safe run-relative path")
    base = Path(root).absolute()
    target = base.joinpath(*relative.parts)
    current = base
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise CandidateNotesError(f"{field} must not traverse symlinks")
    try:
        target.resolve(strict=False).relative_to(base.resolve(strict=True))
    except (ValueError, FileNotFoundError) as exc:
        raise CandidateNotesError(f"{field} escapes the run directory") from exc
    return relative.as_posix(), target


def _read_document(root: Path) -> dict[str, Any]:
    _safe_path(root, NOTES_FILENAME, field="notes path")
    try:
        raw = read_regular_file_nofollow(root, NOTES_FILENAME)
    except FileNotFoundError:
        return {"schema_version": SCHEMA_VERSION, "revision": 0, "entries": []}
    except (OSError, ValueError) as exc:
        raise CandidateNotesError("candidate_notes.json is unreadable or unsafe") from exc
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidateNotesError("candidate_notes.json is unreadable or invalid") from exc
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != SCHEMA_VERSION
        or not isinstance(document.get("revision"), int)
        or isinstance(document.get("revision"), bool)
        or not isinstance(document.get("entries"), list)
        or document["revision"] != len(document["entries"])
    ):
        raise CandidateNotesError("candidate_notes.json has an invalid schema or revision")
    for expected_revision, entry in enumerate(document["entries"], start=1):
        if not isinstance(entry, dict):
            raise CandidateNotesError(f"candidate_notes.json entry {expected_revision} must be an object")
        required_text = (
            "note_id", "created_at", "item_id", "kind", "candidate_path",
            "candidate_sha256", "request_revision", "disposition", "problem",
            "change", "result",
        )
        if any(not isinstance(entry.get(key), str) for key in required_text):
            raise CandidateNotesError(f"candidate_notes.json entry {expected_revision} has invalid fields")
        if (
            entry.get("revision") != expected_revision
            or not isinstance(entry.get("revision"), int)
            or isinstance(entry.get("revision"), bool)
            or not _ITEM_ID.fullmatch(entry["item_id"])
            or entry["kind"] not in {"image", "video"}
            or entry["disposition"] not in {"keep", "reject", "undecided"}
            or not _SHA256.fullmatch(entry["candidate_sha256"])
        ):
            raise CandidateNotesError(f"candidate_notes.json entry {expected_revision} has invalid values")
        try:
            uuid.UUID(entry["note_id"])
        except ValueError as exc:
            raise CandidateNotesError(f"candidate_notes.json entry {expected_revision} has invalid note_id") from exc
        _safe_path(root, entry["candidate_path"], field="candidate_path")
    return document


def _with_staleness(root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    result = dict(entry)
    try:
        _, path = _safe_path(root, result["candidate_path"], field="candidate_path")
        current = _sha256(read_regular_file_nofollow(root, result["candidate_path"]))
    except (OSError, ValueError, CandidateNotesError, KeyError, TypeError):
        current = None
    result["is_stale"] = current != result.get("candidate_sha256")
    return result


def load_notes(root: Path, item_id: str | None = None) -> dict[str, Any]:
    """Load notes, dynamically marking missing or replaced candidate bytes as stale."""
    document = _read_document(Path(root).absolute())
    entries = document["entries"]
    if item_id is not None:
        entries = [entry for entry in entries if entry.get("item_id") == item_id]
    return {
        "schema_version": document["schema_version"],
        "revision": document["revision"],
        "entries": [_with_staleness(Path(root).absolute(), entry) for entry in entries],
    }


def add_note(
    root: Path,
    *,
    item_id: str,
    kind: str,
    candidate_path: str | Path,
    candidate_sha256: str,
    expected_revision: int,
    disposition: str,
    problem: str,
    change: str,
    result: str,
    request_revision: str = "",
) -> dict[str, Any]:
    """Append one human observation if the global notes revision is current."""
    if not isinstance(item_id, str) or not _ITEM_ID.fullmatch(item_id):
        raise CandidateNotesError("item_id is invalid")
    if kind not in {"image", "video"}:
        raise CandidateNotesError("kind must be image or video")
    if disposition not in {"keep", "reject", "undecided"}:
        raise CandidateNotesError("disposition must be keep, reject, or undecided")
    if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 0:
        raise CandidateNotesError("expected_revision must be a non-negative integer")
    if not isinstance(candidate_sha256, str) or not _SHA256.fullmatch(candidate_sha256):
        raise CandidateNotesError("candidate_sha256 must be 64 lowercase hexadecimal characters")
    for name, value in (("problem", problem), ("change", change), ("result", result)):
        if not isinstance(value, str):
            raise CandidateNotesError(f"{name} must be text")
    if not isinstance(request_revision, str):
        raise CandidateNotesError("request_revision must be text")
    run = Path(root).absolute()
    candidate_rel, _ = _safe_path(run, candidate_path, field="candidate_path")
    try:
        raw = read_regular_file_nofollow(run, candidate_rel)
    except (OSError, ValueError) as exc:
        raise CandidateNotesError("candidate_path must identify an existing readable file") from exc
    if _sha256(raw) != candidate_sha256:
        raise CandidateNotesError("candidate_sha256 does not match current candidate bytes")
    notes_path = run / NOTES_FILENAME
    document = _read_document(run)
    if document["revision"] != expected_revision:
        raise CandidateNotesError(
            f"revision conflict: expected {expected_revision}, current {document['revision']}"
        )
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "note_id": str(uuid.uuid4()),
        "revision": expected_revision + 1,
        "created_at": now,
        "item_id": item_id,
        "kind": kind,
        "candidate_path": candidate_rel,
        "candidate_sha256": candidate_sha256,
        "request_revision": request_revision,
        "disposition": disposition,
        "problem": problem,
        "change": change,
        "result": result,
    }
    updated = {
        "schema_version": SCHEMA_VERSION,
        "revision": expected_revision + 1,
        "entries": [*document["entries"], entry],
    }
    payload = (json.dumps(updated, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    try:
        write_run_file_atomic_nofollow(notes_path, payload, run_dir=run)
    except Exception as exc:
        raise CandidateNotesError(f"could not safely publish candidate_notes.json: {exc}") from exc
    return {
        "schema_version": updated["schema_version"],
        "revision": updated["revision"],
        "entries": [_with_staleness(run, item) for item in updated["entries"]],
    }
