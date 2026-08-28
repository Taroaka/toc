"""Scene and cut semantic review pack collectors."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from toc.cut_context_packet import cut_context_packet_for_review
from toc.harness import load_structured_document
from toc.immersive_manifest import make_scene_cut_selector
from toc.run_root_binding import read_run_file_bytes
from toc.scene_acceptance_contract import (
    criterion_registry_digest,
    digest_contract,
    digest_scene_draft,
    domain_separated_digest,
    validate_scene_draft,
    validate_scene_set_authoring_contract,
    validate_scene_set_preflight,
)


SUPPORTED_STAGES = {"scene_set", "scene_detail", "cut_blueprint"}


class SceneAcceptanceValidationError(ValueError):
    """A marked scene artifact failed its mandatory acceptance binding."""


def _strict_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SceneAcceptanceValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def collect_entries(
    stage: str,
    run_dir: Path,
    manifest: dict[str, Any] | None = None,
    *,
    source_document: tuple[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Collect semantic-review-ready scene or cut entries for a run.

    The generic semantic pack builder calls this function with one of the
    supported scene/cut stages. `script.md` is the source of truth when present;
    `manifest` or `video_manifest.md` is used only as a fallback for tests and
    partially materialized runs.
    """

    if stage not in SUPPORTED_STAGES:
        raise ValueError(f"Unsupported scene semantic stage: {stage}")

    resolved_run_dir = Path(run_dir)
    source_path, data = (
        source_document
        if source_document is not None
        else _load_scene_source(resolved_run_dir, manifest)
    )
    scenes = _extract_scenes(data)
    time_of_day_contract_declared = _time_of_day_contract_declared(data, scenes)
    scene_acceptance_context = _validated_scene_acceptance_context(
        data,
        scenes,
        run_dir=resolved_run_dir,
    )

    if stage in {"scene_set", "scene_detail"}:
        canonical_event_coverage_matrix = _dict_value(data.get("canonical_event_coverage_matrix"))
        return [
            _scene_entry(
                stage=stage,
                scene=scene,
                scene_index=index,
                source_path=source_path,
                canonical_event_coverage_matrix=canonical_event_coverage_matrix,
                time_of_day_contract_declared=time_of_day_contract_declared,
                scene_acceptance_context=scene_acceptance_context,
            )
            for index, scene in enumerate(scenes)
        ]

    return [
        _cut_entry(
            scene=scene,
            scene_index=scene_index,
            cut=cut,
            cut_index=cut_index,
            scene_cuts=[item for item in _list_value(scene.get("cuts")) if isinstance(item, dict)],
            source_path=source_path,
            time_of_day_contract_declared=time_of_day_contract_declared,
            scene_acceptance_context=scene_acceptance_context,
        )
        for scene_index, scene in enumerate(scenes)
        for cut_index, cut in enumerate(_list_value(scene.get("cuts")))
        if isinstance(cut, dict)
    ]


def _load_scene_source(run_dir: Path, manifest: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    script_path = run_dir / "script.md"
    if script_path.exists():
        _, data = load_structured_document(script_path)
        return "script.md", data

    if manifest is not None:
        return "manifest", manifest

    manifest_path = run_dir / "video_manifest.md"
    if manifest_path.exists():
        _, data = load_structured_document(manifest_path)
        return "video_manifest.md", data

    return "script.md", {}


def _extract_scenes(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        data.get("scenes"),
        _dict_value(data.get("script")).get("scenes"),
        data.get("scene_set"),
    ]
    for candidate in candidates:
        scenes = [scene for scene in _list_value(candidate) if isinstance(scene, dict)]
        if scenes:
            return scenes
    return []


def _validated_scene_acceptance_context(
    data: dict[str, Any],
    scenes: list[dict[str, Any]],
    *,
    run_dir: Path,
) -> dict[str, Any]:
    metadata = _dict_value(data.get("script_metadata"))
    marker = _text(metadata.get("scene_acceptance_contract"))
    if not marker:
        return {}
    contract = _dict_value(data.get("scene_set_authoring_contract"))
    source_artifacts = _load_scene_acceptance_source_artifacts(
        run_dir,
        contract,
    )
    validation = validate_scene_set_authoring_contract(
        data,
        source_artifacts=source_artifacts or None,
    )
    if not validation.valid:
        raise SceneAcceptanceValidationError(
            "invalid scene acceptance contract in semantic source: "
            + ", ".join(validation.reason_keys)
        )
    preflight = _dict_value(data.get("authoring_preflight"))
    contract_digest = digest_contract(contract)
    if _text(contract.get("contract_digest")) != contract_digest:
        raise SceneAcceptanceValidationError("stale scene acceptance contract digest in semantic source")
    if _text(contract.get("criterion_registry_sha256")) != criterion_registry_digest():
        raise SceneAcceptanceValidationError("stale scene acceptance criterion registry digest")
    drafts = [
        _dict_value(scene.get("scene_acceptance_draft"))
        for scene in scenes
    ]
    if not drafts or any(not draft for draft in drafts):
        raise SceneAcceptanceValidationError("scene acceptance draft set is incomplete")
    for draft in drafts:
        draft_validation = validate_scene_draft(draft, contract)
        if not draft_validation.valid:
            raise SceneAcceptanceValidationError(
                f"invalid scene acceptance draft {draft.get('scene_id')}: "
                + ", ".join(draft_validation.reason_keys)
            )
    set_validation = validate_scene_set_preflight(
        contract,
        drafts,
        source_artifacts=source_artifacts or None,
    )
    if not set_validation.valid:
        raise SceneAcceptanceValidationError(
            "scene acceptance preflight is no longer current: "
            + ", ".join(set_validation.reason_keys)
        )
    if _text(preflight.get("status")) != "passed":
        raise SceneAcceptanceValidationError("scene acceptance preflight has not passed")
    if _text(preflight.get("contract_digest")) != contract_digest:
        raise SceneAcceptanceValidationError("scene acceptance preflight contract digest is stale")
    if _text(preflight.get("criterion_registry_digest")) != criterion_registry_digest():
        raise SceneAcceptanceValidationError("scene acceptance preflight registry digest is stale")
    expected_preflight_digest = _text(
        set_validation.metadata.get("preflight_digest")
    )
    expected_draft_digests = [digest_scene_draft(draft) for draft in drafts]
    if _text(preflight.get("generation_id")) != _text(contract.get("generation_id")):
        raise SceneAcceptanceValidationError(
            "scene acceptance preflight generation is stale"
        )
    if _text(preflight.get("preflight_digest")) != expected_preflight_digest:
        raise SceneAcceptanceValidationError(
            "scene acceptance preflight digest is stale"
        )
    if preflight.get("scene_draft_digests") != expected_draft_digests:
        raise SceneAcceptanceValidationError(
            "scene acceptance preflight draft digests are stale"
        )
    if preflight.get("source_digest") != domain_separated_digest(
        "toc.scene_acceptance.sources.v1",
        contract.get("source_bindings") or {},
    ):
        raise SceneAcceptanceValidationError(
            "scene acceptance preflight source digest is stale"
        )
    if preflight.get("checks") not in ([], None) or preflight.get(
        "blocking_reason_keys"
    ) not in ([], None):
        raise SceneAcceptanceValidationError(
            "passed scene acceptance preflight contains blocking findings"
        )
    return {
        "contract": contract,
        "preflight": preflight,
        "contract_scene_by_id": {
            _text(item.get("scene_id")): item
            for item in _list_value(contract.get("scenes"))
            if isinstance(item, dict) and _text(item.get("scene_id"))
        },
        "draft_by_scene_id": {
            _text(item.get("scene_id")): item
            for item in drafts
            if _text(item.get("scene_id"))
        },
    }


def scene_acceptance_currentness_issues(
    data: dict[str, Any],
    run_dir: Path,
    *,
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    """Return fail-closed publication binding issues for stage evaluators."""

    metadata = _dict_value(data.get("script_metadata"))
    marker = _text(metadata.get("scene_acceptance_contract"))
    if not marker:
        return ["scene_acceptance.marker_missing"]
    if marker != "required_v1":
        return [f"scene_acceptance.marker_unsupported:{marker}"]
    scenes = _extract_scenes(data)
    try:
        context = _validated_scene_acceptance_context(
            data,
            scenes,
            run_dir=Path(run_dir),
        )
    except SceneAcceptanceValidationError as exc:
        return [f"scene_acceptance.currentness:{exc}"]
    if manifest is None:
        return []
    projection = _dict_value(manifest.get("scene_acceptance_contract"))
    contract = _dict_value(context.get("contract"))
    preflight = _dict_value(context.get("preflight"))
    drafts = [
        _dict_value(scene.get("scene_acceptance_draft"))
        for scene in scenes
        if isinstance(scene, dict)
    ]
    expected = {
        "schema_version": contract.get("schema_version"),
        "canonical_script_path": "script.md",
        "generation_id": contract.get("generation_id"),
        "contract_digest": contract.get("contract_digest"),
        "criterion_registry_sha256": contract.get(
            "criterion_registry_sha256"
        ),
        "preflight_status": "passed",
        "preflight_digest": preflight.get("preflight_digest"),
        "scene_slice_digests": {
            str(draft.get("scene_id")): draft.get("scene_slice_digest")
            for draft in drafts
        },
    }
    if projection != expected:
        return ["scene_acceptance.manifest_projection_stale"]
    return []


def _load_scene_acceptance_source_artifacts(
    run_dir: Path,
    contract: dict[str, Any],
) -> dict[str, Any]:
    bindings = _dict_value(contract.get("source_bindings"))
    if not bindings:
        raise SceneAcceptanceValidationError(
            "scene acceptance source bindings are missing"
        )
    artifacts: dict[str, Any] = {}
    for binding_name, raw_binding in bindings.items():
        binding = _dict_value(raw_binding)
        relative = _text(binding.get("path"))
        if not relative:
            raise SceneAcceptanceValidationError(
                f"scene acceptance source path is missing: {binding_name}"
            )
        try:
            raw = read_run_file_bytes(run_dir, relative)
        except (FileNotFoundError, OSError, RuntimeError, ValueError):
            raise SceneAcceptanceValidationError(
                f"scene acceptance source artifact is missing: {binding_name}"
            )
        expected_digest = _text(binding.get("sha256"))
        raw_digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if Path(relative).suffix.lower() == ".json":
            try:
                value: Any = json.loads(
                    raw.decode("utf-8"),
                    object_pairs_hook=_strict_json_object,
                )
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SceneAcceptanceValidationError(
                    f"scene acceptance source JSON is invalid: {binding_name}"
                ) from exc
            if raw_digest != expected_digest:
                raise SceneAcceptanceValidationError(
                    f"scene acceptance source digest is stale: {binding_name}"
                )
            artifacts[str(binding_name)] = raw
        else:
            if raw_digest != expected_digest:
                raise SceneAcceptanceValidationError(
                    f"scene acceptance source digest is stale: {binding_name}"
                )
            artifacts[str(binding_name)] = raw
    return artifacts


def _scene_entry(
    *,
    stage: str,
    scene: dict[str, Any],
    scene_index: int,
    source_path: str,
    canonical_event_coverage_matrix: dict[str, Any] | None = None,
    time_of_day_contract_declared: bool = False,
    scene_acceptance_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scene_id = _text(scene.get("scene_id"), default=str(scene_index + 1))
    cuts = _list_value(scene.get("cuts"))
    include_scene_detail_payload = stage == "scene_detail"
    semantic_contract_source = _scene_semantic_contract(scene)
    semantic_contract = (
        semantic_contract_source
        if include_scene_detail_payload
        else _without_scene_event(semantic_contract_source)
    )
    normalized_contract = _normalize_scene_contract(
        scene,
        semantic_contract,
        include_scene_event=include_scene_detail_payload,
    )
    scene_intent = _dict_value(scene.get("scene_intent"))
    scene_event = _dict_value(scene.get("scene_event"))
    acceptance_context = scene_acceptance_context or {}
    contract = _dict_value(acceptance_context.get("contract"))
    preflight = _dict_value(acceptance_context.get("preflight"))
    scene_contract_slice = _dict_value(
        _dict_value(acceptance_context.get("contract_scene_by_id")).get(scene_id)
    )
    acceptance_draft = _dict_value(
        _dict_value(acceptance_context.get("draft_by_scene_id")).get(scene_id)
    )
    contract_bound = bool(contract and scene_contract_slice and acceptance_draft)
    location_mode, location_sequence, location_segments = (
        _scene_location_evidence(scene)
    )
    missing_fields = _missing_required_fields(
        normalized_contract,
        ("dramatic_question", "value_shift", "causal_turn", "done_when"),
    )
    entry: dict[str, Any] = {
        "stage": stage,
        "id": f"scene:{scene_id}",
        "selector": _scene_selector(scene_id),
        "canonical_selector": make_scene_cut_selector(scene_id),
        "source_path": source_path,
        "source_section": f"scenes[{scene_index}]",
        "source_json_pointer": f"/scenes/{scene_index}",
        "scene_id": scene_id,
        "time_of_day_contract_declared": time_of_day_contract_declared,
        **_time_of_day_review_fields(scene),
        "phase": scene.get("phase"),
        "importance": scene.get("importance"),
        "summary": _scene_summary(scene),
        "semantic_contract": semantic_contract,
        "semantic_contract_present": bool(semantic_contract),
        "semantic_contract_missing": bool(missing_fields),
        "normalized_semantic_contract": normalized_contract,
        "contract_required_fields_missing": missing_fields,
        "scene_intent": scene.get("scene_intent"),
        "scene_event": scene.get("scene_event"),
        "location_mode": location_mode,
        "location_sequence": location_sequence,
        "location_segments": location_segments,
        "participants": (
            acceptance_draft.get("participants")
            if contract_bound
            else _scene_participant_evidence(scene)
        ),
        "role_coverage": (
            {
                "source": "scene_set_authoring_contract.scenes[].role_bindings",
                "role_bindings": scene_contract_slice.get("role_bindings"),
            }
            if contract_bound
            else scene_intent.get("role_coverage")
            or scene.get("role_coverage")
            or scene_event.get("role_coverage")
        ),
        "canonical_event_coverage_matrix": canonical_event_coverage_matrix,
        "coverage_review": scene.get("coverage_review"),
        "handoff_to_next_scene": (
            acceptance_draft.get("handoff_refs")
            if contract_bound
            else scene.get("handoff_to_next_scene")
        ),
        "terminal_resolution": scene.get("terminal_resolution"),
        "cut_count": len(cuts),
    }
    if contract_bound:
        entry.update(
            {
                "scene_acceptance_binding": {
                    "schema_version": contract.get("schema_version"),
                    "generation_id": contract.get("generation_id"),
                    "contract_digest": contract.get("contract_digest"),
                    "criterion_registry_version": contract.get(
                        "criterion_registry_version"
                    ),
                    "criterion_registry_sha256": contract.get(
                        "criterion_registry_sha256"
                    ),
                    "preflight_digest": preflight.get("preflight_digest"),
                    "preflight_status": preflight.get("status"),
                    "scene_slice_digest": acceptance_draft.get(
                        "scene_slice_digest"
                    ),
                },
                "scene_contract_slice": scene_contract_slice,
                "scene_acceptance_draft": acceptance_draft,
                "reveal_state_before": scene_contract_slice.get(
                    "reveal_state_before"
                ),
                "allowed_reveal_transition_ids": scene_contract_slice.get(
                    "allowed_reveal_transition_ids"
                ),
                "reveal_state_after": scene_contract_slice.get(
                    "reveal_state_after"
                ),
            }
        )
    if include_scene_detail_payload:
        entry.update(
            {
                "scene_generation": scene.get("scene_generation"),
                "scene_character_state_timeline": scene.get("scene_character_state_timeline"),
                "scene_film_coverage_plan": scene.get("scene_film_coverage_plan"),
            }
        )
        entry["cut_summaries"] = [
            _cut_summary(scene_id=scene_id, cut=cut, cut_index=cut_index)
            for cut_index, cut in enumerate(cuts)
            if isinstance(cut, dict)
        ]
    return _without_empty_values(entry)


def _cut_entry(
    *,
    scene: dict[str, Any],
    scene_index: int,
    cut: dict[str, Any],
    cut_index: int,
    scene_cuts: list[dict[str, Any]],
    source_path: str,
    time_of_day_contract_declared: bool = False,
    scene_acceptance_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scene_id = _text(scene.get("scene_id"), default=str(scene_index + 1))
    cut_id = _text(cut.get("cut_id"), default=f"{cut_index + 1:02d}")
    selector = _text(cut.get("selector"), default=_cut_selector(scene_id, cut_id))
    blueprint = _dict_value(cut.get("cut_blueprint"))
    scene_contract = _dict_value(cut.get("scene_contract"))
    cut_contract = _dict_value(cut.get("cut_contract"))
    semantic_contract_source = (
        cut.get("semantic_contract")
        or cut_contract
        or scene_contract
        or _contract_from_blueprint(blueprint)
    )
    normalized_contract = _normalize_cut_contract(
        cut,
        semantic_contract_source,
        blueprint,
        scene_contract,
    )
    semantic_contract = cut.get("semantic_contract") or {
        key: normalized_contract[key]
        for key in ("target_beat", "must_show", "must_avoid", "done_when")
        if key in normalized_contract
    }
    review_cut_contract = {
        key: value
        for key, value in cut_contract.items()
        if key
        not in {
            "event_context_for_cut",
            "cut_context_packet",
            "cut_context_packet_diagnostics",
        }
    }
    missing_fields = _missing_required_fields(
        normalized_contract,
        ("target_beat", "must_show", "must_avoid", "done_when"),
    )
    previous_cut = scene_cuts[cut_index - 1] if cut_index > 0 else None
    next_cut = scene_cuts[cut_index + 1] if cut_index + 1 < len(scene_cuts) else None
    cut_context_packet, cut_context_packet_diagnostics = cut_context_packet_for_review(
        scene,
        cut,
        previous_cut=previous_cut,
        next_cut=next_cut,
    )
    acceptance_context = scene_acceptance_context or {}
    acceptance_contract = _dict_value(acceptance_context.get("contract"))
    acceptance_preflight = _dict_value(acceptance_context.get("preflight"))
    acceptance_draft = _dict_value(
        _dict_value(acceptance_context.get("draft_by_scene_id")).get(scene_id)
    )

    return _without_empty_values(
        {
            "stage": "cut_blueprint",
            "id": f"cut:{selector}",
            "selector": selector,
            "canonical_selector": make_scene_cut_selector(scene_id, cut_id),
            "source_path": source_path,
            "source_section": f"scenes[{scene_index}].cuts[{cut_index}]",
            "source_json_pointer": f"/scenes/{scene_index}/cuts/{cut_index}",
            "scene_id": scene_id,
            "cut_id": cut_id,
            "scene_acceptance_binding": (
                {
                    "generation_id": acceptance_contract.get("generation_id"),
                    "contract_digest": acceptance_contract.get("contract_digest"),
                    "preflight_digest": acceptance_preflight.get(
                        "preflight_digest"
                    ),
                    "scene_slice_digest": acceptance_draft.get(
                        "scene_slice_digest"
                    ),
                    "currentness_check": "passed",
                }
                if acceptance_contract and acceptance_draft
                else None
            ),
            "time_of_day_contract_declared": time_of_day_contract_declared,
            **_time_of_day_review_fields(scene),
            "summary": _text(
                blueprint.get("target_beat")
                or scene_contract.get("target_beat")
                or blueprint.get("visual_beat")
                or cut.get("visual_beat")
            ),
            "semantic_contract": semantic_contract,
            "cut_contract": review_cut_contract or None,
            "source_event_contract": _dict_value(cut_contract.get("source_event_contract")) or None,
            "cut_character_emotion_transition": _dict_value(cut_contract.get("cut_character_emotion_transition")) or None,
            "cut_film_grammar_contract": _dict_value(cut_contract.get("cut_film_grammar_contract")) or None,
            "event_context_for_cut": _event_context_for_cut(scene, cut),
            "cut_context_packet": cut_context_packet,
            "cut_context_packet_diagnostics": cut_context_packet_diagnostics,
            "semantic_contract_present": bool(semantic_contract_source),
            "semantic_contract_missing": bool(missing_fields),
            "normalized_semantic_contract": normalized_contract,
            "contract_required_fields_missing": missing_fields,
            "cut_blueprint": blueprint or None,
            "scene_contract": scene_contract or None,
            "asset_dependency_hint": blueprint.get("asset_dependency_hint"),
            "previous_cut_summary": _neighbor_cut_summary(scene_id=scene_id, cuts=scene_cuts, cut_index=cut_index - 1),
            "next_cut_summary": _neighbor_cut_summary(scene_id=scene_id, cuts=scene_cuts, cut_index=cut_index + 1),
            "human_review": cut.get("human_review"),
            "implementation_trace": cut.get("implementation_trace"),
        }
    )


def _scene_summary(scene: dict[str, Any]) -> str:
    intent = _dict_value(scene.get("scene_intent"))
    candidates = [
        intent.get("dramatic_question"),
        intent.get("value_shift"),
        intent.get("causal_turn"),
        scene.get("purpose"),
        scene.get("visualizable_action"),
        scene.get("narration"),
        scene.get("visual"),
    ]
    return " / ".join(_text(value) for value in candidates if _text(value))


def _scene_semantic_contract(scene: dict[str, Any]) -> Any:
    if scene.get("semantic_contract"):
        return scene.get("semantic_contract")
    if scene.get("scene_contract"):
        return scene.get("scene_contract")

    intent = _dict_value(scene.get("scene_intent"))
    scene_event = _dict_value(scene.get("scene_event"))
    contract: dict[str, Any] = {}
    if scene_event:
        contract["scene_event"] = scene_event
    for key in ("dramatic_question", "value_shift", "causal_turn", "done_when"):
        if intent.get(key):
            contract[key] = intent[key]
    for key in ("handoff_to_next_scene", "terminal_resolution"):
        if scene.get(key):
            contract[key] = scene[key]
    return contract or None


def _normalize_scene_contract(
    scene: dict[str, Any],
    semantic_contract: Any,
    *,
    include_scene_event: bool = True,
) -> dict[str, Any]:
    contract = _dict_value(semantic_contract)
    scene_contract = _dict_value(scene.get("scene_contract"))
    intent = _dict_value(scene.get("scene_intent"))
    scene_event = _dict_value(scene.get("scene_event"))
    normalized_contract = {
        "dramatic_question": contract.get("dramatic_question")
        or scene_contract.get("dramatic_question")
        or intent.get("dramatic_question"),
        "value_shift": contract.get("value_shift") or scene_contract.get("value_shift") or intent.get("value_shift"),
        "causal_turn": contract.get("causal_turn") or scene_contract.get("causal_turn") or intent.get("causal_turn"),
        "done_when": contract.get("done_when") or scene_contract.get("done_when") or scene.get("done_when") or intent.get("done_when"),
    }
    if include_scene_event:
        normalized_contract["scene_event"] = contract.get("scene_event") or scene_event
    return _without_empty_values(normalized_contract)


def _without_scene_event(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return {key: item for key, item in value.items() if key != "scene_event"}


def _scene_location_evidence(
    scene: dict[str, Any],
) -> tuple[Any, Any, Any]:
    location = _dict_value(scene.get("location"))
    return (
        scene.get("location_mode") or location.get("mode"),
        scene.get("location_sequence") or location.get("sequence"),
        scene.get("location_segments") or location.get("segments"),
    )


def _scene_participant_evidence(scene: dict[str, Any]) -> Any:
    explicit = scene.get("participants") or scene.get("characters")
    if explicit not in (None, "", [], {}):
        return explicit

    timeline = _dict_value(scene.get("scene_character_state_timeline"))
    participants: list[dict[str, Any]] = []
    for raw_character in _list_value(timeline.get("characters")):
        if not isinstance(raw_character, dict):
            continue
        participant = _without_empty_values(
            {
                "character_id": raw_character.get("character_id"),
                "character_name": raw_character.get("character_name"),
                "scene_role": raw_character.get("scene_role"),
                "appearance_asset_ids": raw_character.get(
                    "appearance_asset_ids"
                ),
            }
        )
        if participant:
            participants.append(participant)
    return participants


def _normalize_cut_contract(
    cut: dict[str, Any],
    semantic_contract: Any,
    blueprint: dict[str, Any],
    scene_contract: dict[str, Any],
) -> dict[str, Any]:
    contract = _dict_value(semantic_contract)
    cut_contract = _dict_value(cut.get("cut_contract"))
    source_event_contract = _dict_value(cut_contract.get("source_event_contract"))
    viewer_contract = _dict_value(cut_contract.get("viewer_contract"))
    return _without_empty_values(
        {
            "source_event_contract": source_event_contract,
            "primary_event_beat_id": source_event_contract.get("primary_event_beat_id"),
            "source_event_beat_ids": source_event_contract.get("source_event_beat_ids"),
            "event_facts_to_preserve": source_event_contract.get("event_facts_to_preserve"),
            "event_facts_not_to_invent": source_event_contract.get("event_facts_not_to_invent"),
            "target_beat": viewer_contract.get("target_beat")
            or contract.get("target_beat")
            or scene_contract.get("target_beat")
            or blueprint.get("target_beat")
            or cut.get("target_beat")
            or cut.get("visual_beat"),
            "must_show": viewer_contract.get("must_show") or contract.get("must_show") or scene_contract.get("must_show") or blueprint.get("must_show"),
            "must_avoid": viewer_contract.get("must_avoid") or contract.get("must_avoid") or scene_contract.get("must_avoid") or blueprint.get("must_avoid"),
            "done_when": viewer_contract.get("done_when") or contract.get("done_when") or scene_contract.get("done_when") or blueprint.get("done_when"),
        }
    )


def _missing_required_fields(contract: dict[str, Any], required_fields: tuple[str, ...]) -> list[str]:
    return [field for field in required_fields if field not in contract]


def _contract_from_blueprint(blueprint: dict[str, Any]) -> dict[str, Any] | None:
    if not blueprint:
        return None
    keys = ("target_beat", "must_show", "must_avoid", "done_when", "visual_beat", "narration_role")
    contract = {key: blueprint[key] for key in keys if key in blueprint and blueprint[key] not in (None, "", [])}
    return contract or None


def _cut_summary(*, scene_id: str, cut: dict[str, Any], cut_index: int) -> dict[str, Any]:
    cut_id = _text(cut.get("cut_id"), default=f"{cut_index + 1:02d}")
    selector = _text(cut.get("selector"), default=_cut_selector(scene_id, cut_id))
    blueprint = _dict_value(cut.get("cut_blueprint"))
    scene_contract = _dict_value(cut.get("scene_contract"))
    cut_contract = _dict_value(cut.get("cut_contract"))
    source_event_contract = _dict_value(cut_contract.get("source_event_contract"))
    viewer_contract = _dict_value(cut_contract.get("viewer_contract"))
    return _without_empty_values(
        {
            "selector": selector,
            "cut_id": cut_id,
            "primary_event_beat_id": source_event_contract.get("primary_event_beat_id"),
            "source_event_beat_ids": source_event_contract.get("source_event_beat_ids"),
            "cut_character_emotion_transition": _dict_value(cut_contract.get("cut_character_emotion_transition")) or None,
            "cut_film_grammar_contract": _dict_value(cut_contract.get("cut_film_grammar_contract")) or None,
            "target_beat": viewer_contract.get("target_beat") or blueprint.get("target_beat") or scene_contract.get("target_beat"),
            "visual_beat": blueprint.get("visual_beat") or cut.get("visual_beat"),
            "must_show": blueprint.get("must_show") or scene_contract.get("must_show"),
            "semantic_contract": cut.get("semantic_contract") or scene_contract or _contract_from_blueprint(blueprint),
        }
    )


def _event_context_for_cut(scene: dict[str, Any], cut: dict[str, Any]) -> dict[str, Any]:
    scene_event = _dict_value(scene.get("scene_event"))
    sequence = [beat for beat in _list_value(scene_event.get("event_sequence")) if isinstance(beat, dict)]
    cut_contract = _dict_value(cut.get("cut_contract"))
    source_contract = _dict_value(cut_contract.get("source_event_contract"))
    primary_id = _text(source_contract.get("primary_event_beat_id"))
    source_ids = [_text(item) for item in _list_value(source_contract.get("source_event_beat_ids")) if _text(item)]
    if primary_id and primary_id not in source_ids:
        source_ids = [primary_id, *source_ids]
    by_id = {_text(beat.get("beat_id")): beat for beat in sequence if _text(beat.get("beat_id"))}
    if not by_id:
        return {}
    neighbor_ids: list[str] = []
    for source_id in source_ids:
        for index, beat in enumerate(sequence):
            if _text(beat.get("beat_id")) != source_id:
                continue
            for neighbor_index in (index - 1, index + 1):
                if 0 <= neighbor_index < len(sequence):
                    neighbor_id = _text(sequence[neighbor_index].get("beat_id"))
                    if neighbor_id and neighbor_id not in source_ids and neighbor_id not in neighbor_ids:
                        neighbor_ids.append(neighbor_id)
    reveal_constraints = _dict_value(cut_contract.get("viewer_contract")).get("reveal_constraints")
    if not reveal_constraints:
        reveal_constraints = _dict_value(scene.get("scene_intent")).get("reveal_constraints")
    return _without_empty_values(
        {
            "derived_from": ["scene_event.event_sequence[]", "cut_contract.source_event_contract"],
            "editable": False,
            "primary_event_beat": by_id.get(primary_id),
            "source_event_beats": [by_id[source_id] for source_id in source_ids if source_id in by_id],
            "neighboring_event_beats": [by_id[neighbor_id] for neighbor_id in neighbor_ids if neighbor_id in by_id],
            "forbidden_event_changes": scene_event.get("forbidden_event_changes"),
            "reveal_constraints_for_this_cut": reveal_constraints,
        }
    )


def _neighbor_cut_summary(*, scene_id: str, cuts: list[dict[str, Any]], cut_index: int) -> dict[str, Any] | None:
    if cut_index < 0 or cut_index >= len(cuts):
        return None
    return _cut_summary(scene_id=scene_id, cut=cuts[cut_index], cut_index=cut_index)


def _scene_selector(scene_id: str) -> str:
    return f"scene{scene_id}"


def _cut_selector(scene_id: str, cut_id: str) -> str:
    normalized_cut = f"{int(cut_id):02d}" if cut_id.isdigit() else cut_id
    return f"scene{scene_id}_cut{normalized_cut}"


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _time_of_day_contract_declared(data: dict[str, Any], scenes: list[dict[str, Any]]) -> bool:
    del scenes
    metadata_candidates = (
        data.get("story_metadata"),
        data.get("script_metadata"),
        data.get("video_metadata"),
    )
    return any(
        isinstance(metadata, dict)
        and _text(metadata.get("scene_time_of_day_contract")) == "required_v1"
        for metadata in metadata_candidates
    )


def _time_of_day_review_fields(scene: dict[str, Any]) -> dict[str, Any]:
    if "time_of_day" not in scene:
        return {"time_of_day_status": "missing"}
    raw = scene.get("time_of_day")
    if not isinstance(raw, str):
        return {
            "time_of_day_status": "invalid_type",
            "time_of_day_raw": raw,
        }
    value = raw.strip()
    if not value:
        return {"time_of_day_status": "blank"}
    return {
        "time_of_day": value,
        "time_of_day_status": "valid",
    }


def _without_empty_values(entry: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in entry.items() if value not in (None, "", [], {})}
