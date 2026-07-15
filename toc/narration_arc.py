"""Full-run narration story contract and revision hashing."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from toc.immersive_manifest import (
    is_non_renderable_manifest_node,
    make_scene_cut_selector,
    normalize_dotted_id,
    selector_aliases,
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _speech_key(value: Any) -> str:
    return re.sub(r"[\s、。！？!?・…—―「」『』（）()]", "", _text(value))


def _script_key(value: Any) -> str:
    """Normalize transport line endings without erasing audible punctuation/spacing."""

    return ("" if value is None else str(value)).replace("\r\n", "\n").replace("\r", "\n").strip()


def _is_non_renderable_node(value: Any) -> bool:
    return is_non_renderable_manifest_node(value)


def _narration_nodes(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    nodes: list[tuple[str, dict[str, Any]]] = []
    for scene in _list(data.get("scenes")):
        if not isinstance(scene, dict):
            continue
        if _is_non_renderable_node(scene):
            continue
        scene_id = normalize_dotted_id(scene.get("scene_id"))
        if not scene_id:
            continue
        cuts = _list(scene.get("cuts"))
        if cuts:
            for cut in cuts:
                if not isinstance(cut, dict) or _is_non_renderable_node(cut):
                    continue
                cut_id = normalize_dotted_id(cut.get("cut_id"))
                if not cut_id:
                    continue
                narration = _dict(_dict(cut.get("audio")).get("narration"))
                nodes.append((make_scene_cut_selector(scene_id, cut_id), narration))
            continue
        narration = _dict(_dict(scene.get("audio")).get("narration"))
        nodes.append((make_scene_cut_selector(scene_id), narration))
    return nodes


def narration_text_set_hash(data: dict[str, Any]) -> str:
    """Hash the global audio-story plan and the exact ordered narration text set."""

    items: list[dict[str, Any]] = []
    for selector, narration in _narration_nodes(data):
        items.append(
            {
                "selector": selector,
                "authoring_status": _text(narration.get("authoring_status")),
                "tool": _text(narration.get("tool")),
                "text": _text(narration.get("text")),
                "tts_text": _text(narration.get("tts_text")),
                "span_refs": _list(narration.get("span_refs")),
            }
        )
    return _hash(
        {
            "audio_story_plan": _dict(data.get("audio_story_plan")),
            "narration_spans": _list(data.get("narration_spans")),
            "items": items,
        }
    )


def validate_audio_story_contract(data: dict[str, Any]) -> list[str]:
    """Return blocking full-run story/voice contract findings."""

    findings: list[str] = []
    plan = _dict(data.get("audio_story_plan"))
    authoring_status = _text(plan.get("authoring_status")).lower()
    authoring_provenance = _text(plan.get("authoring_provenance")).lower()
    if authoring_status not in {"authored", "approved"}:
        findings.append("audio_story_plan requires Audio Story Director review before p720 can pass")
    if authoring_provenance != "audio_story_director":
        findings.append("audio_story_plan.authoring_provenance must be audio_story_director")
    if authoring_provenance == "derived_legacy_cut_projection":
        findings.append("audio_story_plan derived from cut projection requires full-run-first reauthoring")
    if not _text(plan.get("audience_promise")):
        findings.append("audio_story_plan.audience_promise is required")
    narrator_bible = _dict(plan.get("narrator_bible"))
    if not _text(narrator_bible.get("relationship_to_story")):
        findings.append("audio_story_plan.narrator_bible.relationship_to_story is required")
    if not _text(plan.get("continuous_full_draft")):
        findings.append("audio_story_plan.continuous_full_draft is required")
    if not _list(narrator_bible.get("emotional_permission")):
        findings.append("audio_story_plan.narrator_bible.emotional_permission must not be empty")
    if not _list(narrator_bible.get("forbidden_attitudes")):
        findings.append("audio_story_plan.narrator_bible.forbidden_attitudes must not be empty")

    alias_to_selector: dict[str, str] = {}
    narration_by_selector = dict(_narration_nodes(data))
    for scene in _list(data.get("scenes")):
        if not isinstance(scene, dict):
            continue
        if _is_non_renderable_node(scene):
            continue
        scene_id = normalize_dotted_id(scene.get("scene_id"))
        if not scene_id:
            continue
        cuts = _list(scene.get("cuts"))
        if cuts:
            for cut in cuts:
                if not isinstance(cut, dict) or _is_non_renderable_node(cut):
                    continue
                cut_id = normalize_dotted_id(cut.get("cut_id"))
                if not cut_id:
                    continue
                canonical = make_scene_cut_selector(scene_id, cut_id)
                for alias in selector_aliases(scene_id, cut_id):
                    alias_to_selector[alias] = canonical
        else:
            canonical = make_scene_cut_selector(scene_id)
            for alias in selector_aliases(scene_id):
                alias_to_selector[alias] = canonical

    spans = [span for span in _list(data.get("narration_spans")) if isinstance(span, dict)]
    if not spans:
        findings.append("narration_spans must contain at least one full-run span")
    covered: set[str] = set()
    voiced_span_counts: dict[str, int] = {}
    known_span_ids: set[str] = set()
    ordered_span_texts: list[tuple[str, str]] = []
    opened_loop_ids: set[str] = set()
    closed_loop_ids: set[str] = set()
    opened_loop_sources: dict[str, set[str]] = {}
    closed_loop_sources: dict[str, set[str]] = {}
    groups_by_selector: dict[str, set[str]] = {}
    canonical_position = {selector: index for index, selector in enumerate(narration_by_selector)}
    voiced_source_sequence: list[str] = []
    for index, span in enumerate(spans, start=1):
        span_id = _text(span.get("span_id"))
        label = span_id or f"index_{index}"
        if not span_id:
            findings.append(f"narration_spans[{index}].span_id is required")
        elif span_id in known_span_ids:
            findings.append(f"duplicate narration span_id: {span_id}")
        known_span_ids.add(span_id)
        relation = _text(span.get("audio_visual_relation"))
        if relation != "voice_silence" and not _text(span.get("text")):
            findings.append(f"{label}: text is required")
        elif relation != "voice_silence":
            ordered_span_texts.append((label, _text(span.get("text"))))
        if relation != "voice_silence" and not _text(span.get("tts_text")):
            findings.append(f"{label}: tts_text is required")
        if relation != "voice_silence" and not _text(span.get("tts_generation_group_id")):
            findings.append(f"{label}: tts_generation_group_id is required")
        raw_sources = _list(span.get("source_cut_ids"))
        if not raw_sources:
            findings.append(f"{label}: source_cut_ids must not be empty")
        canonical_sources: list[str] = []
        for raw in raw_sources:
            canonical = alias_to_selector.get(_text(raw))
            if not canonical:
                findings.append(f"{label}: unknown source cut {_text(raw) or '<empty>'}")
                continue
            covered.add(canonical)
            canonical_sources.append(canonical)
            group_id = _text(span.get("tts_generation_group_id"))
            if relation != "voice_silence" and group_id:
                groups_by_selector.setdefault(canonical, set()).add(group_id)
            if relation != "voice_silence":
                voiced_span_counts[canonical] = voiced_span_counts.get(canonical, 0) + 1
        if relation != "voice_silence" and canonical_sources:
            source_positions = [canonical_position[selector] for selector in canonical_sources if selector in canonical_position]
            if source_positions != sorted(source_positions):
                findings.append(f"{label}: source_cut_ids must follow canonical cut order")
            voiced_source_sequence.extend(canonical_sources)
            expected_text = "\n".join(
                _text(narration_by_selector.get(selector, {}).get("text"))
                for selector in canonical_sources
                if _text(narration_by_selector.get(selector, {}).get("text"))
            )
            expected_tts = "\n".join(
                _text(narration_by_selector.get(selector, {}).get("tts_text"))
                or _text(narration_by_selector.get(selector, {}).get("text"))
                for selector in canonical_sources
                if _text(narration_by_selector.get(selector, {}).get("tts_text"))
                or _text(narration_by_selector.get(selector, {}).get("text"))
            )
            if _script_key(span.get("text")) != _script_key(expected_text):
                findings.append(f"{label}: text does not equal its source_cut_ids narration in order")
            if _script_key(span.get("tts_text")) != _script_key(expected_tts):
                findings.append(f"{label}: tts_text does not equal its source_cut_ids TTS text in order")
        span_opened_ids = {_text(value) for value in _list(span.get("opened_loop_ids")) if _text(value)}
        span_closed_ids = {_text(value) for value in _list(span.get("closed_loop_ids")) if _text(value)}
        opened_loop_ids.update(span_opened_ids)
        closed_loop_ids.update(span_closed_ids)
        for loop_id in span_opened_ids:
            opened_loop_sources.setdefault(loop_id, set()).update(canonical_sources)
        for loop_id in span_closed_ids:
            closed_loop_sources.setdefault(loop_id, set()).update(canonical_sources)

    continuous_key = _script_key(plan.get("continuous_full_draft"))
    expected_continuous_key = "\n".join(
        _script_key(span_text) for _label, span_text in ordered_span_texts
    )
    if continuous_key and continuous_key != expected_continuous_key:
        findings.append("audio_story_plan.continuous_full_draft must equal narration_spans text in order")
    voiced_positions = [canonical_position[selector] for selector in voiced_source_sequence if selector in canonical_position]
    if voiced_positions != sorted(voiced_positions):
        findings.append("narration_spans must follow canonical cut order across the full run")

    for selector, narration in narration_by_selector.items():
        tool = _text(narration.get("tool")).lower()
        voiced = tool != "silent" and bool(_text(narration.get("text")) or _text(narration.get("tts_text")))
        if voiced and selector not in covered:
            findings.append(f"{selector}: voiced narration is not anchored by narration_spans")
        if voiced and voiced_span_counts.get(selector, 0) != 1:
            findings.append(f"{selector}: voiced narration must belong to exactly one voiced narration_span")
        if len(groups_by_selector.get(selector, set())) > 1:
            findings.append(f"{selector}: voiced narration belongs to more than one tts_generation_group_id")

    repeated_cut_texts: dict[str, list[str]] = {}
    for selector, narration in narration_by_selector.items():
        key = _speech_key(narration.get("text"))
        if key:
            repeated_cut_texts.setdefault(key, []).append(selector)
    for selectors in repeated_cut_texts.values():
        if len(selectors) > 1:
            findings.append("exact narration repetition across cuts: " + ", ".join(selectors))

    scene_ids: set[str] = set()
    for scene in _list(data.get("scenes")):
        if (
            not isinstance(scene, dict)
            or _is_non_renderable_node(scene)
        ):
            continue
        declared_cuts = _list(scene.get("cuts"))
        if declared_cuts and not any(
            isinstance(cut, dict) and not _is_non_renderable_node(cut)
            for cut in declared_cuts
        ):
            continue
        scene_id = normalize_dotted_id(scene.get("scene_id"))
        if scene_id:
            scene_ids.add(scene_id)
    scene_arcs = [arc for arc in _list(plan.get("scene_arcs")) if isinstance(arc, dict)]
    arc_scene_ids = {normalize_dotted_id(arc.get("scene_id")) for arc in scene_arcs}
    for scene_id in sorted(scene_ids - arc_scene_ids):
        findings.append(f"audio_story_plan.scene_arcs is missing scene{scene_id}")
    for arc in scene_arcs:
        scene_id = normalize_dotted_id(arc.get("scene_id")) or "unknown"
        if not _text(arc.get("attention_state")):
            findings.append(f"scene{scene_id}: attention_state is required")
        if not _text(arc.get("audience_state_before")) or not _text(arc.get("audience_state_after")):
            findings.append(f"scene{scene_id}: audience state before/after is required")
        if not _text(arc.get("semantic_load")):
            findings.append(f"scene{scene_id}: semantic_load is required")

    open_loops = _list(plan.get("open_loops"))
    declared_loop_ids: set[str] = set()
    for loop in open_loops:
        if isinstance(loop, dict) and _text(loop.get("loop_id")):
            loop_id = _text(loop.get("loop_id"))
            if loop_id in declared_loop_ids:
                findings.append(f"duplicate audio_story_plan.open_loops loop_id: {loop_id}")
            declared_loop_ids.add(loop_id)
    for undeclared in sorted((opened_loop_ids | closed_loop_ids) - declared_loop_ids):
        findings.append(f"narration span references undeclared open loop: {undeclared}")

    for loop in open_loops:
        if not isinstance(loop, dict):
            findings.append("audio_story_plan.open_loops entries must be mappings")
            continue
        loop_id = _text(loop.get("loop_id")) or "<missing_loop_id>"
        if loop_id == "<missing_loop_id>":
            findings.append("audio_story_plan.open_loops[].loop_id is required")
        opened_at = _text(loop.get("opened_at"))
        if not opened_at:
            findings.append(f"{loop_id}: opened_at is required")
        opened_selector = alias_to_selector.get(opened_at) if opened_at else None
        if opened_at and not opened_selector:
            findings.append(f"{loop_id}: opened_at references unknown cut {opened_at}")
        elif opened_selector and opened_selector not in opened_loop_sources.get(loop_id, set()):
            findings.append(f"{loop_id}: opened_at must belong to a span that opens this loop")
        payoff_type = _text(loop.get("payoff_type"))
        payoff_at = _text(loop.get("payoff_at"))
        if payoff_type != "intentional_unresolved" and not payoff_at:
            findings.append(f"{loop_id}: payoff_at is required unless intentionally unresolved")
        payoff_selector = alias_to_selector.get(payoff_at) if payoff_at else None
        if payoff_at and not payoff_selector:
            findings.append(f"{loop_id}: payoff_at references unknown cut {payoff_at}")
        elif payoff_type != "intentional_unresolved" and payoff_selector and payoff_selector not in closed_loop_sources.get(loop_id, set()):
            findings.append(f"{loop_id}: payoff_at must belong to a span that closes this loop")
        if loop_id not in opened_loop_ids:
            findings.append(f"{loop_id}: no narration span opens this loop")
        if payoff_type != "intentional_unresolved" and loop_id not in closed_loop_ids:
            findings.append(f"{loop_id}: no narration span closes this loop")
        if opened_selector and payoff_selector:
            opened_position = canonical_position.get(opened_selector)
            payoff_position = canonical_position.get(payoff_selector)
            if opened_position is not None and payoff_position is not None and opened_position >= payoff_position:
                findings.append(f"{loop_id}: opened_at must precede payoff_at in canonical cut order")
    if spans:
        final_story_job = _text(spans[-1].get("story_job"))
        if final_story_job not in {"payoff", "reaction", "aftertaste"}:
            findings.append("final narration span must provide payoff, reaction, or aftertaste")
    return findings
