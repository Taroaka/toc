"""Full-run narration span projection and TTS continuity helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from toc.immersive_manifest import (
    is_non_renderable_manifest_node,
    make_scene_cut_selector,
    normalize_dotted_id,
    selector_aliases,
)
from toc.script_narration import resolve_script_cut_tts_text


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_non_renderable_node(value: Any) -> bool:
    return is_non_renderable_manifest_node(value)


def _cut_texts(cut: dict[str, Any]) -> tuple[str, str]:
    audio = _dict(cut.get("audio"))
    narration = _dict(audio.get("narration"))
    if narration:
        public_text = _text(narration.get("text"))
        return public_text, _text(narration.get("tts_text")) or public_text
    review = _dict(cut.get("human_review"))
    public_text = _text(review.get("approved_narration")) or _text(cut.get("narration"))
    approved_tts = _text(review.get("approved_tts_text"))
    return public_text, approved_tts or resolve_script_cut_tts_text(cut) or public_text


def narration_cut_index(data: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, str]]:
    """Return canonical cut order, nodes, and every accepted selector alias."""

    order: list[str] = []
    cuts: dict[str, dict[str, Any]] = {}
    aliases: dict[str, str] = {}
    for scene in _list(data.get("scenes")):
        if (
            not isinstance(scene, dict)
            or _is_non_renderable_node(scene)
        ):
            continue
        scene_id = normalize_dotted_id(scene.get("scene_id"))
        if not scene_id:
            continue
        declared_cuts = _list(scene.get("cuts"))
        indexed_cuts = (
            [
                (cut_index, cut)
                for cut_index, cut in enumerate(declared_cuts, start=1)
                if isinstance(cut, dict) and not _is_non_renderable_node(cut)
            ]
            if declared_cuts
            else [(1, scene)]
        )
        for cut_index, cut in indexed_cuts:
            cut_id = normalize_dotted_id(cut.get("cut_id")) if cut is not scene else None
            if cut is not scene and not cut_id:
                cut_id = str(cut_index)
            canonical = make_scene_cut_selector(scene_id, cut_id)
            order.append(canonical)
            cuts[canonical] = cut
            for alias in selector_aliases(scene_id, cut_id):
                aliases[alias] = canonical
            aliases[canonical] = canonical
    return order, cuts, aliases


def narration_span_refs(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Project ordered top-level spans onto their canonical source cuts."""

    _order, _cuts, aliases = narration_cut_index(data)
    refs: dict[str, list[dict[str, Any]]] = {}
    for sequence_index, span in enumerate(_list(data.get("narration_spans")), start=1):
        if not isinstance(span, dict):
            continue
        span_id = _text(span.get("span_id"))
        if not span_id:
            continue
        sources: list[str] = []
        for raw in _list(span.get("source_cut_ids")):
            canonical = aliases.get(_text(raw))
            if canonical and canonical not in sources:
                sources.append(canonical)
        ref = {
            "span_id": span_id,
            "sequence_index": sequence_index,
            "source_cut_ids": sources,
            "story_job": _text(span.get("story_job")),
            "audio_visual_relation": _text(span.get("audio_visual_relation")),
            "tts_generation_group_id": _text(span.get("tts_generation_group_id")),
        }
        for selector in sources:
            refs.setdefault(selector, []).append(dict(ref))
    return refs


def reconcile_audio_story_text(data: dict[str, Any]) -> bool:
    """Refresh derived span/full-draft text after an explicit cut-text edit."""

    _order, cuts, aliases = narration_cut_index(data)
    spans = [span for span in _list(data.get("narration_spans")) if isinstance(span, dict)]
    if not spans:
        return False
    changed = False
    full_draft_parts: list[str] = []
    for span in spans:
        if _text(span.get("audio_visual_relation")) == "voice_silence":
            continue
        public_parts: list[str] = []
        tts_parts: list[str] = []
        for raw in _list(span.get("source_cut_ids")):
            canonical = aliases.get(_text(raw))
            cut = cuts.get(canonical or "")
            if not isinstance(cut, dict):
                continue
            public_text, tts_text = _cut_texts(cut)
            if public_text:
                public_parts.append(public_text)
            if tts_text:
                tts_parts.append(tts_text)
        public_text = "\n".join(public_parts)
        tts_text = "\n".join(tts_parts)
        if span.get("text") != public_text:
            span["text"] = public_text
            changed = True
        if span.get("tts_text") != tts_text:
            span["tts_text"] = tts_text
            changed = True
        if public_text:
            full_draft_parts.append(public_text)
    plan = _dict(data.get("audio_story_plan"))
    if plan:
        continuous = "\n".join(full_draft_parts)
        if plan.get("continuous_full_draft") != continuous:
            plan["continuous_full_draft"] = continuous
            data["audio_story_plan"] = plan
            changed = True
    return changed


def tts_continuity_contexts(data: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Build adjacent-text context hashes for the actual ordered provider chunks."""

    order, cuts, _aliases = narration_cut_index(data)
    refs = narration_span_refs(data)
    groups: dict[str, list[tuple[str, str]]] = {}
    for selector in order:
        cut = cuts[selector]
        audio_narration = _dict(_dict(cut.get("audio")).get("narration"))
        tool = _text(audio_narration.get("tool") if audio_narration else cut.get("narration_tool")).lower()
        if tool == "silent":
            continue
        _public_text, tts_text = _cut_texts(cut)
        if not tts_text:
            continue
        group_ids = {
            _text(ref.get("tts_generation_group_id"))
            for ref in refs.get(selector, [])
            if _text(ref.get("audio_visual_relation")) != "voice_silence"
            and _text(ref.get("tts_generation_group_id"))
        }
        if len(group_ids) != 1:
            continue
        group_id = next(iter(group_ids))
        groups.setdefault(group_id, []).append((selector, tts_text))

    contexts: dict[str, dict[str, str]] = {}
    for group_id, members in groups.items():
        for index, (selector, _tts_text) in enumerate(members):
            previous_text = members[index - 1][1] if index else ""
            next_text = members[index + 1][1] if index + 1 < len(members) else ""
            descriptor = {
                "tts_generation_group_id": group_id,
                "previous_text": previous_text,
                "next_text": next_text,
            }
            descriptor["tts_continuity_hash"] = _hash(descriptor)
            contexts[selector] = descriptor
    return contexts


def invalidate_stale_tts_context_audio(data: dict[str, Any]) -> list[str]:
    """Invalidate generated audio whose frozen adjacent context is no longer current."""

    _order, cuts, _aliases = narration_cut_index(data)
    contexts = tts_continuity_contexts(data)
    invalidated: list[str] = []
    for selector, cut in cuts.items():
        narration = _dict(_dict(cut.get("audio")).get("narration"))
        if not narration:
            continue
        current_hash = _text(_dict(contexts.get(selector)).get("tts_continuity_hash"))
        generation = _dict(narration.get("generation"))
        audio_review = _dict(narration.get("audio_review"))
        active_ids = {
            _text(generation.get("candidate_id")),
            _text(audio_review.get("approved_candidate_id")),
        } - {""}
        active_stale = False
        for candidate in _list(narration.get("candidates")):
            if not isinstance(candidate, dict):
                continue
            frozen_hash = _text(_dict(candidate.get("provider_request")).get("tts_continuity_hash"))
            status = _text(candidate.get("status"))
            if frozen_hash != current_hash and status not in {"failed", "rejected", "stale", "superseded"}:
                candidate["status"] = "stale"
                if _text(candidate.get("candidate_id")) in active_ids or status == "human_approved":
                    active_stale = True
        if not active_stale:
            continue
        narration["output"] = ""
        narration["status"] = "stale"
        narration["generation"] = {
            "status": "stale",
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
        invalidated.append(selector)
    return invalidated
