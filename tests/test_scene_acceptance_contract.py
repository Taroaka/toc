from __future__ import annotations

from copy import deepcopy
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.scene_acceptance_contract import (
    CRITERION_REGISTRY_VERSION,
    SCENE_ACCEPTANCE_CONTRACT_VERSION,
    SCENE_DRAFT_VERSION,
    criterion_registry_digest,
    criterion_registry_payload,
    digest_contract,
    digest_scene_slice,
    domain_separated_digest,
    resolve_criterion,
    validate_scene_draft,
    validate_scene_set_authoring_contract,
    validate_scene_set_preflight,
)


def _valid_contract() -> dict:
    return {
        "schema_version": SCENE_ACCEPTANCE_CONTRACT_VERSION,
        "generation_id": "generation-001",
        "criterion_registry_version": CRITERION_REGISTRY_VERSION,
        "criterion_registry_sha256": criterion_registry_digest(),
        "source_bindings": {"story": {"path": "story.md", "sha256": "sha256:" + "a" * 64}},
        "source_refs": [
            {
                "source_ref_id": "source-event-1",
                "artifact": "story",
                "artifact_sha256": "sha256:" + "a" * 64,
                "pointer": "/events/E01",
                "expected_id": "E01",
            }
        ],
        "canonical_events": [
            {
                "event_id": "E01",
                "canonical_order_index": 1,
                "owner_scene_id": 10,
                "required_beat_ids": ["scene10-beat-01"],
                "source_ref_ids": ["source-event-1"],
            }
        ],
        "evidence_catalog": [
            {
                "evidence_id": "evidence-hearth-ash",
                "owner_scene_id": 10,
                "element_id": "element-hearth-ash",
                "source_ref_ids": ["source-event-1"],
                "visible_form": "灰まみれの炉床",
            }
        ],
        "reveal_ledger": [
            {
                "information_id": "artifact-glass-slipper",
                "initial_state": "withheld",
                "allowed_states": ["withheld", "revealed", "carried", "known"],
                "transitions": [
                    {
                        "reveal_transition_id": "reveal-glass-slipper-10",
                        "from_state": "withheld",
                        "to_state": "revealed",
                        "owner_scene_id": 10,
                        "owner_beat_id": "scene10-beat-01",
                        "evidence_ids": ["evidence-hearth-ash"],
                    }
                ],
            }
        ],
        "handoff_chain": [
            {
                "anchor_id": "handoff-10-20",
                "owner_scene_id": 10,
                "consumer_scene_id": 20,
                "state_id": "state-after-scene-10",
                "producer_beat_id": "scene10-beat-01",
                "consumer_beat_id": "scene20-beat-01",
                "evidence_ids": ["evidence-hearth-ash"],
            }
        ],
        "transition_cues": [
            {
                "transition_cue_id": "cue-10-20-night",
                "owner_scene_id": 20,
                "from_time_of_day": "morning",
                "to_time_of_day": "night",
                "owner_beat_id": "scene20-beat-01",
                "evidence_ids": ["evidence-hearth-ash"],
            }
        ],
        "scenes": [
            {
                "scene_id": 10,
                "owned_event_ids": ["E01"],
                "required_beat_specs": [
                    {
                        "beat_id": "scene10-beat-01",
                        "source_event_ids": ["E01"],
                        "beat_function": "setup",
                        "required_role_ids": ["protagonist"],
                        "required_character_ids": ["character-cinderella"],
                        "required_evidence_ids": ["evidence-hearth-ash"],
                        "required_non_replaceable_element_ids": ["element-hearth-ash"],
                    }
                ],
                "role_bindings": [
                    {
                        "role_id": "protagonist",
                        "character_ids": ["character-cinderella"],
                        "required_for_beat_ids": ["scene10-beat-01"],
                    }
                ],
                "reveal_state_before": {"artifact-glass-slipper": "withheld"},
                "allowed_reveal_transition_ids": ["reveal-glass-slipper-10"],
                "reveal_state_after": {"artifact-glass-slipper": "revealed"},
                "time_location_transition": {
                    "time_of_day": "morning",
                    "continuity_from_previous": "opening",
                    "transition_cue_required": False,
                    "transition_cue_ids": [],
                    "location_sequence": ["location-kitchen"],
                },
                "incoming_handoff_anchor_id": "story-opening",
                "outgoing_handoff_anchor_id": "handoff-10-20",
                "causal_proof_contract": {
                    "cause_beat_id": "scene10-beat-01",
                    "action_beat_id": "scene10-beat-01",
                    "result_state_id": "state-after-scene-10",
                    "required_evidence_ids": ["evidence-hearth-ash"],
                },
                "non_replaceable_elements": [
                    {
                        "element_id": "element-hearth-ash",
                        "source_ref_ids": ["source-event-1"],
                        "required_evidence_ids": ["evidence-hearth-ash"],
                    }
                ],
            },
            {
                "scene_id": 20,
                "owned_event_ids": [],
                "required_beat_specs": [
                    {
                        "beat_id": "scene20-beat-01",
                        "source_event_ids": [],
                        "beat_function": "transition",
                        "required_role_ids": [],
                        "required_character_ids": [],
                        "required_evidence_ids": ["evidence-hearth-ash"],
                        "required_non_replaceable_element_ids": [],
                    }
                ],
                "role_bindings": [],
                "reveal_state_before": {"artifact-glass-slipper": "revealed"},
                "allowed_reveal_transition_ids": [],
                "reveal_state_after": {"artifact-glass-slipper": "revealed"},
                "time_location_transition": {
                    "time_of_day": "night",
                    "continuity_from_previous": "elapsed_time",
                    "transition_cue_required": True,
                    "transition_cue_ids": ["cue-10-20-night"],
                    "location_sequence": ["location-kitchen"],
                },
                "incoming_handoff_anchor_id": "handoff-10-20",
                "outgoing_handoff_anchor_id": "story-ending",
                "causal_proof_contract": {
                    "cause_beat_id": "scene20-beat-01",
                    "action_beat_id": "scene20-beat-01",
                    "result_state_id": "state-after-scene-10",
                    "required_evidence_ids": ["evidence-hearth-ash"],
                },
                "non_replaceable_elements": [],
            },
        ],
    }


def _valid_draft(contract: dict, scene_id: int = 10) -> dict:
    scene = next(item for item in contract["scenes"] if item["scene_id"] == scene_id)
    beat = scene["required_beat_specs"][0]
    return {
        "schema_version": SCENE_DRAFT_VERSION,
        "generation_id": contract["generation_id"],
        "scene_id": scene_id,
        "contract_digest": digest_contract(contract),
        "scene_slice_digest": digest_scene_slice(contract, scene_id),
        "scene_intent": {"purpose": "灰の中の主人公を示す"},
        "scene_event": {
            "event_sequence": [
                {
                    "beat_id": beat["beat_id"],
                    "source_event_ids": beat["source_event_ids"],
                    "role_ids": beat["required_role_ids"],
                    "participant_character_ids": beat["required_character_ids"],
                    "evidence_ids": beat["required_evidence_ids"],
                    "required_non_replaceable_element_ids": beat[
                        "required_non_replaceable_element_ids"
                    ],
                    "reveal_transition_ids": ["reveal-glass-slipper-10"],
                    "transition_cue_ids": ["cue-10-20-night"] if scene_id == 20 else [],
                    "incoming_handoff_anchor_ids": (
                        ["handoff-10-20"] if scene_id == 20 else []
                    ),
                    "outgoing_handoff_anchor_ids": (
                        ["handoff-10-20"] if scene_id == 10 else []
                    ),
                    "result_state_id": "state-after-scene-10",
                }
            ]
        },
        "participants": [
            {
                "character_id": "character-cinderella",
                "role_ids": ["protagonist"],
                "visibility": "visible",
                "required_for_beat_ids": ["scene10-beat-01"],
                "evidence_ids": ["evidence-hearth-ash"],
            }
        ],
        "handoff_refs": {
            "incoming": [],
            "outgoing": [
                {
                    "anchor_id": "handoff-10-20",
                    "state_id": "state-after-scene-10",
                    "evidence_ids": ["evidence-hearth-ash"],
                }
            ],
        },
    }


def test_registry_and_domain_separated_digests_are_stable() -> None:
    assert criterion_registry_digest() == criterion_registry_digest()
    assert criterion_registry_digest().startswith("sha256:")
    assert domain_separated_digest("toc.test.a", {"x": "é"}) != domain_separated_digest(
        "toc.test.b", {"x": "é"}
    )
    assert domain_separated_digest("toc.test.a", {"x": "é"}) == domain_separated_digest(
        "toc.test.a", {"x": "é"}
    )


def test_criterion_registry_contains_only_deterministic_authoring_rules() -> None:
    criteria = criterion_registry_payload()

    assert criteria
    assert all(item["owner"] == "deterministic" for item in criteria)
    assert all(
        not any(
            key in item
            for key in (
                "first_enforced_stage",
                "semantic_recheck_stages",
                "provider_repair_allowed",
                "reviewer_instruction",
            )
        )
        for item in criteria
    )
    assert resolve_criterion("scene.causal_proof_visually_unconvincing") is None
    assert resolve_criterion("scene_event_concrete_but_not_story_specific") is None


def test_valid_contract_passes_and_digest_excludes_derived_preflight() -> None:
    contract = _valid_contract()
    result = validate_scene_set_authoring_contract(contract)
    assert result.valid, result.to_dict()
    digest = digest_contract(contract)
    contract["authoring_preflight"] = {"status": "failed", "checks": []}
    assert digest_contract(contract) == digest


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda c: c["scenes"][1]["owned_event_ids"].append("E01"), "scene_event_canonical_event_duplicate"),
        (lambda c: c["scenes"][1]["reveal_state_before"].update({"artifact-glass-slipper": "withheld"}), "reveal_state_rollback"),
        (lambda c: c["scenes"][0]["role_bindings"][0].update({"character_ids": []}), "role_binding_character_missing"),
        (lambda c: c["scenes"][1].update({"incoming_handoff_anchor_id": "handoff-unknown"}), "handoff_anchor_unknown"),
        (lambda c: c["scenes"][1]["time_location_transition"].update({"transition_cue_ids": []}), "time_transition_cue_missing"),
        (lambda c: c["scenes"][0]["non_replaceable_elements"][0].update({"source_ref_ids": []}), "source_ref_missing"),
    ],
)
def test_contract_validation_reports_deterministic_reason_keys(mutator, expected: str) -> None:
    contract = _valid_contract()
    mutator(contract)
    result = validate_scene_set_authoring_contract(contract)
    assert not result.valid
    assert expected in result.reason_keys


def test_contract_rejects_source_ref_not_owned_by_source_bindings() -> None:
    contract = _valid_contract()
    contract["source_refs"][0]["artifact"] = "unbound-story"

    result = validate_scene_set_authoring_contract(contract)

    assert not result.valid
    assert "source_ref_missing" in result.reason_keys


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("producer_beat_id", "scene20-beat-01", "handoff_reference_invalid"),
        ("consumer_beat_id", "scene10-beat-01", "handoff_reference_invalid"),
        ("state_id", "state-forged", "handoff_state_mismatch"),
    ],
)
def test_handoff_must_bind_adjacent_scene_beats_and_producer_result(
    field: str,
    value: str,
    expected: str,
) -> None:
    contract = _valid_contract()
    contract["handoff_chain"][0][field] = value

    result = validate_scene_set_authoring_contract(contract)

    assert not result.valid
    assert expected in result.reason_keys


def test_location_discontinuity_requires_exact_cue_endpoints() -> None:
    contract = _valid_contract()
    contract["scenes"][1]["time_location_transition"]["location_sequence"] = [
        "location-ballroom"
    ]

    result = validate_scene_set_authoring_contract(contract)

    assert not result.valid
    assert "time_transition_cue_missing" in result.reason_keys


def test_scene_draft_requires_exact_event_and_visible_role_closure() -> None:
    contract = _valid_contract()
    draft = _valid_draft(contract)
    assert validate_scene_draft(draft, contract).valid

    broken = deepcopy(draft)
    broken["scene_event"]["event_sequence"][0]["evidence_ids"] = []
    broken["participants"][0]["visibility"] = "offscreen_context"
    result = validate_scene_draft(broken, contract)
    assert not result.valid
    assert "scene_event_missing_non_replaceable_elements" in result.reason_keys or "causal_proof_weak" in result.reason_keys
    assert "role_coverage_missing" in result.reason_keys


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (
            lambda draft: draft["scene_event"]["event_sequence"][0].update(
                {"reveal_transition_ids": []}
            ),
            "scene_draft_reference_mismatch",
        ),
        (
            lambda draft: draft["scene_event"]["event_sequence"][0].update(
                {"required_non_replaceable_element_ids": []}
            ),
            "scene_draft_reference_mismatch",
        ),
        (
            lambda draft: draft["scene_event"]["event_sequence"][0].update(
                {"result_state_id": "state-forged"}
            ),
            "causal_proof_weak",
        ),
        (
            lambda draft: draft["participants"][0].update({"evidence_ids": []}),
            "role_coverage_missing",
        ),
    ],
)
def test_scene_draft_requires_exact_frozen_closure(mutator, expected: str) -> None:
    contract = _valid_contract()
    draft = _valid_draft(contract)
    mutator(draft)

    result = validate_scene_draft(draft, contract)

    assert not result.valid
    assert expected in result.reason_keys


def test_whole_set_preflight_checks_handoff_and_reveal_across_drafts() -> None:
    contract = _valid_contract()
    drafts = [_valid_draft(contract, 10), _valid_draft(contract, 20)]
    # Scene 20 has no required role, event, or causal reveal transition. Its draft is built explicitly.
    drafts[1]["scene_event"]["event_sequence"][0]["reveal_transition_ids"] = []
    drafts[1]["scene_event"]["event_sequence"][0]["outgoing_handoff_anchor_ids"] = []
    drafts[1]["participants"] = []
    drafts[1]["handoff_refs"] = {
        "incoming": [
            {"anchor_id": "handoff-10-20", "state_id": "state-after-scene-10", "evidence_ids": ["evidence-hearth-ash"]}
        ],
        "outgoing": [],
    }
    result = validate_scene_set_preflight(contract, drafts)
    assert result.valid, result.to_dict()

    broken = deepcopy(drafts)
    broken[1]["handoff_refs"]["incoming"][0]["state_id"] = "state-wrong"
    result = validate_scene_set_preflight(contract, broken)
    assert not result.valid
    assert "handoff_state_mismatch" in result.reason_keys


def test_whole_set_preflight_rejects_duplicate_scene_drafts() -> None:
    contract = _valid_contract()
    duplicate = _valid_draft(contract, 10)

    result = validate_scene_set_preflight(contract, [duplicate, deepcopy(duplicate)])

    assert not result.valid
    assert "duplicate_scene_id" in result.reason_keys


def test_marker_compatibility_legacy_partial_and_unsupported() -> None:
    legacy = validate_scene_set_authoring_contract({"script_metadata": {}})
    assert legacy.valid
    assert legacy.status == "legacy_not_applicable"

    partial = validate_scene_set_authoring_contract(
        {"script_metadata": {"scene_acceptance_contract": "required_v1"}, "scenes": []}
    )
    assert not partial.valid
    assert "partial_scene_acceptance_contract" in partial.reason_keys

    unsupported = validate_scene_set_authoring_contract(
        {"schema_version": "scene_set_authoring_contract_v99"}
    )
    assert not unsupported.valid
    assert "unsupported_scene_acceptance_contract_version" in unsupported.reason_keys


def test_generic_prose_does_not_replace_required_id_references() -> None:
    contract = _valid_contract()
    draft = _valid_draft(contract)
    draft["scene_event"]["generic_description"] = "人物の手元と床の痕跡"
    draft["scene_event"]["event_sequence"][0]["evidence_ids"] = []
    result = validate_scene_draft(draft, contract)
    assert not result.valid
    assert "scene_event_missing_source_grounding" in result.reason_keys


def test_scene_draft_rejects_unknown_top_level_keys() -> None:
    contract = _valid_contract()
    draft = _valid_draft(contract)
    draft["unexpected_author_override"] = True
    result = validate_scene_draft(draft, contract)
    assert not result.valid
    assert "output_contract_unknown_key" in result.reason_keys
