"""Revision-bound narration authoring and TTS candidate lifecycle.

The public narration text, provider-facing TTS text, semantic review, generated
audio, and human approval are deliberately separate states.  Functions mutate
the supplied narration mapping so existing manifest readers can keep using the
flat ``text`` / ``tts_text`` / ``output`` compatibility fields.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


REVISION_SCHEMA_VERSION = "narration_revision_v1"
ALLOWED_AUTHORING_STATUSES = {"missing", "draft", "human_locked", "reviewed", "silent"}


class NarrationRevisionConflict(ValueError):
    """Raised when a caller acts on an obsolete narration revision or hash."""


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _sha256_payload(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def narration_text_hash(text: str, *, tool: str) -> str:
    mode = "silent" if tool == "silent" else "spoken"
    return _sha256_payload({"mode": mode, "text": _text(text)})


def narration_tts_hash(tts_text: str, *, tool: str, delivery: dict[str, Any] | None = None) -> str:
    return _sha256_payload(
        {
            "delivery": delivery or {},
            "tool": _text(tool).lower() or "elevenlabs",
            "tts_text": _text(tts_text),
        }
    )


def _delivery_payload(narration: dict[str, Any]) -> dict[str, Any]:
    return {
        "elevenlabs_prompt": _dict(narration.get("elevenlabs_prompt")),
        "model_id": _text(narration.get("model_id")),
        "voice_id": _text(narration.get("voice_id")),
        "voice_settings": _dict(narration.get("voice_settings")),
    }


def _current_hashes(narration: dict[str, Any]) -> tuple[str, str, str]:
    tool = _text(narration.get("tool")).lower() or "elevenlabs"
    text_hash = narration_text_hash(_text(narration.get("text")), tool=tool)
    tts_hash = narration_tts_hash(
        _text(narration.get("tts_text")) or _text(narration.get("text")),
        tool=tool,
        delivery=_delivery_payload(narration),
    )
    source_hash = _sha256_payload({"text_hash": text_hash, "tts_hash": tts_hash})
    return text_hash, tts_hash, source_hash


def ensure_narration_revision(narration: dict[str, Any]) -> dict[str, Any]:
    revision = _dict(narration.get("revision"))
    text_hash, tts_hash, source_hash = _current_hashes(narration)
    if revision.get("schema_version") != REVISION_SCHEMA_VERSION:
        revision = {
            "schema_version": REVISION_SCHEMA_VERSION,
            "number": 0,
            "text_revision": 0,
            "tts_revision": 0,
            "text_hash": text_hash,
            "tts_hash": tts_hash,
            "source_hash": source_hash,
            "source": _text(narration.get("source")) or "legacy",
            "updated_at": "",
        }
    else:
        revision.setdefault("number", 0)
        revision.setdefault("text_revision", 0)
        revision.setdefault("tts_revision", 0)
        revision.setdefault("text_hash", text_hash)
        revision.setdefault("tts_hash", tts_hash)
        revision.setdefault("source_hash", source_hash)
        revision.setdefault("source", _text(narration.get("source")) or "legacy")
        revision.setdefault("updated_at", "")
    narration["revision"] = revision
    narration["candidates"] = [item for item in _list(narration.get("candidates")) if isinstance(item, dict)]
    generation = _dict(narration.get("generation"))
    generation.setdefault("status", "missing")
    generation.setdefault("candidate_id", "")
    generation.setdefault("generated_from_tts_hash", "")
    narration["generation"] = generation
    audio_review = _dict(narration.get("audio_review"))
    audio_review.setdefault("status", "pending")
    audio_review.setdefault("approved_candidate_id", "")
    audio_review.setdefault("approved_revision", 0)
    audio_review.setdefault("approved_text_hash", "")
    audio_review.setdefault("approved_tts_hash", "")
    audio_review.setdefault("approved_at", "")
    narration["audio_review"] = audio_review
    review = _dict(narration.get("review"))
    review.setdefault("status", "pending")
    review.setdefault("human_review_ok", False)
    narration["review"] = review
    narration.setdefault("authoring_status", "missing")
    narration.setdefault("output", "")
    return revision


def _revision_hashes_match_flat_fields(narration: dict[str, Any], revision: dict[str, Any]) -> bool:
    """Return whether the stored v1 revision still describes the flat payload."""

    if revision.get("schema_version") != REVISION_SCHEMA_VERSION:
        return False
    text_hash, tts_hash, source_hash = _current_hashes(narration)
    return (
        _text(revision.get("text_hash")) == text_hash
        and _text(revision.get("tts_hash")) == tts_hash
        and _text(revision.get("source_hash")) == source_hash
    )


def _require_revision_hash_integrity(narration: dict[str, Any], revision: dict[str, Any]) -> None:
    if not _revision_hashes_match_flat_fields(narration, revision):
        raise NarrationRevisionConflict("narration revision hash drift: flat authoring fields bypassed revision update")


def _require_expected_revision(revision: dict[str, Any], expected_revision: int | None) -> None:
    current = int(revision.get("number") or 0)
    if expected_revision is not None and expected_revision != current:
        raise NarrationRevisionConflict(f"narration revision conflict: expected={expected_revision} current={current}")


def _require_expected_tts_hash(revision: dict[str, Any], expected_tts_hash: str | None) -> None:
    current = _text(revision.get("tts_hash"))
    if expected_tts_hash is not None and expected_tts_hash != current:
        raise NarrationRevisionConflict(
            f"narration TTS hash conflict: expected={expected_tts_hash or '-'} current={current or '-'}"
        )


def _invalidate_reviews(narration: dict[str, Any], *, semantic_changed: bool, tts_changed: bool) -> None:
    review = _dict(narration.get("review"))
    review["status"] = "pending"
    if semantic_changed:
        review["agent_review_ok"] = None
        review["agent_review_reason_keys"] = []
        review["agent_review_reason_messages"] = []
        review["human_review_ok"] = False
        review["semantic"] = {"status": "stale", "reviewed_text_hash": ""}
        review["arc"] = {"status": "stale", "narration_set_hash": ""}
    if semantic_changed or tts_changed:
        review["human_review_ok"] = False
        review["delivery"] = {"status": "stale", "reviewed_tts_hash": ""}
    narration["review"] = review


def _invalidate_audio(narration: dict[str, Any], *, current_tts_hash: str) -> None:
    had_audio = bool(_text(narration.get("output")))
    for candidate in _list(narration.get("candidates")):
        if not isinstance(candidate, dict):
            continue
        if _text(candidate.get("generated_from_tts_hash")) != current_tts_hash or candidate.get("status") == "human_approved":
            if candidate.get("status") not in {"failed", "rejected"}:
                candidate["status"] = "stale"
            had_audio = True
    narration["output"] = ""
    narration["status"] = "stale" if had_audio else "draft"
    narration["generation"] = {
        "status": "stale" if had_audio else "missing",
        "candidate_id": "",
        "generated_from_tts_hash": "",
    }
    narration["audio_review"] = {
        "status": "pending",
        "approved_candidate_id": "",
        "approved_revision": 0,
        "approved_text_hash": "",
        "approved_tts_hash": "",
        "approved_at": "",
    }


def _unlock_audio_approval(narration: dict[str, Any]) -> None:
    audio_review = _dict(narration.get("audio_review"))
    approved_id = _text(audio_review.get("approved_candidate_id"))
    for candidate in _list(narration.get("candidates")):
        if isinstance(candidate, dict) and _text(candidate.get("candidate_id")) == approved_id:
            candidate["status"] = "candidate"
    narration["output"] = ""
    narration["status"] = "candidate" if approved_id else "draft"
    generation = _dict(narration.get("generation"))
    generation["status"] = "candidate" if approved_id else "missing"
    narration["generation"] = generation
    narration["audio_review"] = {
        "status": "pending",
        "approved_candidate_id": "",
        "approved_revision": 0,
        "approved_text_hash": "",
        "approved_tts_hash": "",
        "approved_at": "",
    }


def apply_authoring_update(
    narration: dict[str, Any],
    *,
    text: str,
    tts_text: str,
    tool: str,
    authoring_status: str,
    source: str,
    expected_revision: int | None,
    now: str,
) -> bool:
    """Apply a compare-and-swap authoring edit and invalidate derived state."""

    revision = ensure_narration_revision(narration)
    _require_expected_revision(revision, expected_revision)
    normalized_status = _text(authoring_status).lower()
    if normalized_status not in ALLOWED_AUTHORING_STATUSES:
        raise ValueError(f"unsupported narration authoring status: {authoring_status}")
    normalized_tool = _text(tool).lower() or "elevenlabs"
    normalized_text = _text(text)
    normalized_tts = _text(tts_text) or normalized_text
    delivery = _delivery_payload(narration)
    new_text_hash = narration_text_hash(normalized_text, tool=normalized_tool)
    new_tts_hash = narration_tts_hash(normalized_tts, tool=normalized_tool, delivery=delivery)
    new_source_hash = _sha256_payload({"text_hash": new_text_hash, "tts_hash": new_tts_hash})
    semantic_changed = new_text_hash != _text(revision.get("text_hash"))
    tts_changed = new_tts_hash != _text(revision.get("tts_hash"))
    status_changed = normalized_status != _text(narration.get("authoring_status"))
    # ``source`` is provenance for an actual authoring transition, not content.
    # A caller-label change alone must remain an idempotent save.
    if not any((semantic_changed, tts_changed, status_changed)):
        return False

    previous_status = _text(narration.get("authoring_status"))
    narration["text"] = normalized_text
    narration["tts_text"] = normalized_tts
    narration["tool"] = normalized_tool
    narration["authoring_status"] = normalized_status
    narration["missing_reason"] = "" if normalized_status != "missing" else "p700_narration_not_written_yet"
    revision.update(
        {
            "number": int(revision.get("number") or 0) + 1,
            "text_revision": int(revision.get("text_revision") or 0) + (1 if semantic_changed else 0),
            "tts_revision": int(revision.get("tts_revision") or 0) + (1 if tts_changed else 0),
            "text_hash": new_text_hash,
            "tts_hash": new_tts_hash,
            "source_hash": new_source_hash,
            "source": _text(source) or "frontend",
            "updated_at": now,
        }
    )
    narration["revision"] = revision
    if semantic_changed or tts_changed:
        _invalidate_reviews(narration, semantic_changed=semantic_changed, tts_changed=tts_changed)
        _invalidate_audio(narration, current_tts_hash=new_tts_hash)
    elif previous_status in {"human_locked", "reviewed", "silent"} and normalized_status == "draft":
        _unlock_audio_approval(narration)
    return True


def prepare_audio_candidate(
    narration: dict[str, Any],
    *,
    candidate_id: str,
    output: str,
    expected_revision: int | None,
    expected_tts_hash: str | None,
    now: str,
    provider_request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Capture an immutable generation snapshot before leaving the run lock."""

    revision = ensure_narration_revision(narration)
    _require_expected_revision(revision, expected_revision)
    _require_expected_tts_hash(revision, expected_tts_hash)
    _require_revision_hash_integrity(narration, revision)
    if _text(narration.get("tool")).lower() != "silent" and not _text(narration.get("tts_text")):
        raise ValueError("narration TTS text is empty")
    candidate_id = _text(candidate_id)
    output = _text(output)
    if not candidate_id or not output:
        raise ValueError("candidate_id and output are required")

    preserve_approved_audio = current_audio_is_human_approved(narration)
    snapshot = {
        "candidate_id": candidate_id,
        "request_revision": int(revision.get("number") or 0),
        "generated_from_text_hash": _text(revision.get("text_hash")),
        "generated_from_tts_hash": _text(revision.get("tts_hash")),
        "output": output,
        "requested_at": now,
    }
    if provider_request:
        snapshot["provider_request"] = provider_request
    snapshot["request_digest"] = _sha256_payload(snapshot)
    candidate = {**snapshot, "status": "generating", "duration_seconds": None, "output_sha256": "", "generated_at": ""}
    narration["candidates"].append(candidate)
    narration["generation"] = {
        "status": "generating",
        "candidate_id": candidate_id,
        "generated_from_tts_hash": snapshot["generated_from_tts_hash"],
    }
    if preserve_approved_audio:
        narration["status"] = "audio_ready"
    else:
        narration["status"] = "generating"
        narration["output"] = ""
        narration["audio_review"] = {
            "status": "pending",
            "approved_candidate_id": "",
            "approved_revision": 0,
            "approved_text_hash": "",
            "approved_tts_hash": "",
            "approved_at": "",
        }
    return snapshot


def _candidate_by_id(narration: dict[str, Any], candidate_id: str) -> dict[str, Any] | None:
    return next(
        (
            candidate
            for candidate in _list(narration.get("candidates"))
            if isinstance(candidate, dict) and _text(candidate.get("candidate_id")) == candidate_id
        ),
        None,
    )


def record_audio_candidate_result(
    narration: dict[str, Any],
    *,
    snapshot: dict[str, Any],
    succeeded: bool,
    duration_seconds: float | None,
    output_sha256: str,
    now: str,
) -> str:
    """Record a provider result without letting an obsolete completion win."""

    revision = ensure_narration_revision(narration)
    revision_hashes_current = _revision_hashes_match_flat_fields(narration, revision)
    candidate_id = _text(snapshot.get("candidate_id"))
    candidate = _candidate_by_id(narration, candidate_id)
    if candidate is None:
        raise NarrationRevisionConflict(f"narration candidate not found: {candidate_id}")
    candidate["generated_at"] = now
    candidate["duration_seconds"] = duration_seconds
    candidate["output_sha256"] = _text(output_sha256)
    generation = _dict(narration.get("generation"))
    is_current = (
        revision_hashes_current
        and _text(snapshot.get("generated_from_text_hash")) == _text(revision.get("text_hash"))
        and _text(snapshot.get("generated_from_tts_hash")) == _text(revision.get("tts_hash"))
        and _text(generation.get("candidate_id")) == candidate_id
    )
    if not succeeded:
        candidate["status"] = "failed"
        if is_current:
            generation["status"] = "failed"
            narration["generation"] = generation
            narration["status"] = "audio_ready" if current_audio_is_human_approved(narration) else "failed"
        return "failed"
    if not is_current:
        candidate["status"] = "stale"
        if _text(generation.get("candidate_id")) == candidate_id:
            generation["status"] = "stale"
            narration["generation"] = generation
            narration["status"] = "stale"
        return "stale"
    candidate["status"] = "candidate"
    generation["status"] = "candidate"
    generation["generated_from_tts_hash"] = _text(snapshot.get("generated_from_tts_hash"))
    narration["generation"] = generation
    narration["status"] = "audio_ready" if current_audio_is_human_approved(narration) else "candidate"
    return "candidate"


def approve_audio_candidate(
    narration: dict[str, Any],
    *,
    candidate_id: str,
    expected_revision: int | None,
    expected_tts_hash: str | None,
    now: str,
) -> dict[str, Any]:
    """Promote a current candidate only after an explicit human listen/approval."""

    revision = ensure_narration_revision(narration)
    _require_expected_revision(revision, expected_revision)
    _require_expected_tts_hash(revision, expected_tts_hash)
    _require_revision_hash_integrity(narration, revision)
    if _text(narration.get("authoring_status")) not in {"human_locked", "reviewed"}:
        raise NarrationRevisionConflict("narration text must be human_locked before audio approval")
    candidate_id = _text(candidate_id)
    candidate = _candidate_by_id(narration, candidate_id)
    if candidate is None or candidate.get("status") != "candidate":
        raise NarrationRevisionConflict(f"narration candidate is not current and approvable: {candidate_id}")
    if _text(candidate.get("generated_from_text_hash")) != _text(revision.get("text_hash")):
        raise NarrationRevisionConflict("narration candidate text hash is stale")
    if _text(candidate.get("generated_from_tts_hash")) != _text(revision.get("tts_hash")):
        raise NarrationRevisionConflict("narration candidate TTS hash is stale")
    if _text(_dict(narration.get("generation")).get("candidate_id")) != candidate_id:
        raise NarrationRevisionConflict("a newer narration candidate exists")

    for item in _list(narration.get("candidates")):
        if isinstance(item, dict) and item is not candidate and item.get("status") == "human_approved":
            item["status"] = "superseded"
    candidate["status"] = "human_approved"
    narration["output"] = _text(candidate.get("output"))
    narration["status"] = "audio_ready"
    narration["generation"] = {
        "status": "human_approved",
        "candidate_id": candidate_id,
        "generated_from_tts_hash": _text(revision.get("tts_hash")),
    }
    narration["audio_review"] = {
        "status": "approved",
        "approved_candidate_id": candidate_id,
        "approved_revision": int(revision.get("number") or 0),
        "approved_text_hash": _text(revision.get("text_hash")),
        "approved_tts_hash": _text(revision.get("tts_hash")),
        "approved_at": now,
    }
    return candidate


def current_audio_is_human_approved(narration: dict[str, Any]) -> bool:
    revision = _dict(narration.get("revision"))
    if not _revision_hashes_match_flat_fields(narration, revision):
        return False
    if _text(narration.get("tool")).lower() == "silent":
        silence = _dict(narration.get("silence_contract"))
        return (
            _text(narration.get("authoring_status")) == "silent"
            and silence.get("intentional") is True
            and silence.get("confirmed_by_human") is True
            and _text(silence.get("revision_hash")) == _text(revision.get("source_hash"))
        )
    audio_review = _dict(narration.get("audio_review"))
    candidate_id = _text(audio_review.get("approved_candidate_id"))
    candidate = _candidate_by_id(narration, candidate_id)
    return bool(
        _text(narration.get("authoring_status")) in {"human_locked", "reviewed"}
        and _text(narration.get("output"))
        and audio_review.get("status") == "approved"
        and _text(audio_review.get("approved_text_hash")) == _text(revision.get("text_hash"))
        and _text(audio_review.get("approved_tts_hash")) == _text(revision.get("tts_hash"))
        and candidate is not None
        and candidate.get("status") == "human_approved"
        and _text(candidate.get("generated_from_text_hash")) == _text(revision.get("text_hash"))
        and _text(candidate.get("generated_from_tts_hash")) == _text(revision.get("tts_hash"))
        and _text(candidate.get("output")) == _text(narration.get("output"))
    )


def narration_audio_set_hash(items: list[tuple[str, dict[str, Any]]]) -> str:
    """Hash the ordered, explicitly approved playback set for p750 approval."""

    payload: list[dict[str, Any]] = []
    for selector, narration in items:
        revision = _dict(narration.get("revision"))
        audio_review = _dict(narration.get("audio_review"))
        candidate = _candidate_by_id(narration, _text(audio_review.get("approved_candidate_id")))
        payload.append(
            {
                "candidate_id": _text(audio_review.get("approved_candidate_id")),
                "duration_seconds": candidate.get("duration_seconds") if candidate else None,
                "output": _text(narration.get("output")),
                "output_sha256": _text(candidate.get("output_sha256")) if candidate else "",
                "selector": selector,
                "source_hash": _text(revision.get("source_hash")),
                "tool": _text(narration.get("tool")),
            }
        )
    return _sha256_payload(payload)
