from __future__ import annotations

from copy import deepcopy

from toc.asset_prompt_compiler import compile_asset_prompt
from toc.cast_design import (
    CAST_APPEARANCE_FIELDS,
    CAST_DESIGN_SCHEMA_VERSION,
    appearance_contract_from_design,
    bind_legacy_cast_context,
    validate_cast_design,
)


def _provenance(*, fact: str = "", interpretation: str = "", choice: str = ""):
    return {
        "source_facts": [fact] if fact else [],
        "interpretation": [interpretation] if interpretation else [],
        "creative_choices": [choice] if choice else [],
    }


def _appearance(**overrides):
    result = {field: f"species-appropriate {field}" for field in CAST_APPEARANCE_FIELDS}
    result.update(overrides)
    return result


def whole_cast_fixture():
    resources = {
        "characters": {
            "heir": {
                "name": "the heir",
                "subject_contract": {"identity_scope": "individual", "subject_count": 1, "member_ids": []},
            },
            "envoy": {
                "name": "the envoy",
                "subject_contract": {"identity_scope": "individual", "subject_count": 1, "member_ids": []},
            },
            "siblings": {
                "name": "the siblings",
                "references": ["assets/characters/siblings.png"],
                "subject_contract": {"identity_scope": "individual", "subject_count": 1, "member_ids": []},
            },
        },
        "objects": {},
        "locations": {},
    }
    design = {
        "schema_version": CAST_DESIGN_SCHEMA_VERSION,
        "source_bindings": {"research": "r", "story": "s", "visual_value": "v"},
        "characters": {
            "heir": {
                "character_id": "heir", "name": "the heir", "subject_contract": deepcopy(resources["characters"]["heir"]["subject_contract"]),
                "role": "successor in a ruling household", "role_basis": "the story names the succession role",
                "relationships": [{"character_id": "envoy", "relation": "receives the envoy", "source_basis": "the envoy brings a message"}],
                "personality_provenance": _provenance(fact="asks for an answer", interpretation="careful before acting"),
                "behavior_baseline": ["waits until the other speaker finishes"],
                "appearance": _appearance(
                    age_impression="young adult", face_shape="long oval face", hair="short dark curls",
                    build_silhouette="slim upright silhouette", palette_costume="deep blue formal coat with silver edging",
                    identifying_features="narrow silver clasp at the left shoulder"),
                "appearance_provenance": _provenance(choice="formal dress signals public status"),
                "intentional_similarities": [],
                "distinguish_from": [{"with_id": "envoy", "visual_differences": "the heir wears a blue formal coat and has short curls", "behavior_differences": "the heir waits for the other speaker to finish"}],
            },
            "envoy": {
                "character_id": "envoy", "name": "the envoy", "subject_contract": deepcopy(resources["characters"]["envoy"]["subject_contract"]),
                "role": "messenger from another household", "role_basis": "the story identifies the person as a messenger",
                "relationships": [{"character_id": "heir", "relation": "delivers a message to", "source_basis": "the story places the envoy before the heir"}],
                "personality_provenance": _provenance(fact="delivers a message", interpretation="measured under pressure"),
                "behavior_baseline": ["keeps both hands visible when speaking"],
                "appearance": _appearance(
                    age_impression="middle-aged", face_shape="broad angular face", hair="close-cropped silver hair",
                    build_silhouette="broad shoulders and a grounded stance", palette_costume="ochre travel mantle over charcoal clothing",
                    identifying_features="creased leather dispatch tube across the chest"),
                "appearance_provenance": _provenance(choice="travel wear distinguishes the working messenger"),
                "intentional_similarities": [],
                "distinguish_from": [{"with_id": "heir", "visual_differences": "the envoy wears an ochre travel mantle and has close-cropped silver hair", "behavior_differences": "the envoy keeps both hands visible while speaking"}],
            },
            "siblings": {
                "character_id": "siblings", "name": "the siblings",
                "subject_contract": {"identity_scope": "ensemble", "subject_count": 2, "member_ids": ["elder", "younger"]},
                "role": "two siblings who share a household uniform", "role_basis": "the story identifies them as siblings in the same household",
                "relationships": [],
                "personality_provenance": _provenance(fact="they are siblings", interpretation="their presentation may share family traits"),
                "behavior_baseline": ["each reacts independently to the same conversation"],
                "shared_appearance": {"palette_costume": "matching pale blue household tunics"},
                "shared_appearance_provenance": _provenance(choice="the household uniform is intentionally shared"),
                "members": [
                    {
                        "member_id": "elder", "name": "older sibling", "role": "older sister", "role_basis": "the source distinguishes the older sibling",
                        "relationships": [{"character_id": "younger", "relation": "older sibling of", "source_basis": "the story names the family relationship"}],
                        "personality_provenance": _provenance(fact="speaks first", interpretation="more deliberate"),
                        "behavior_baseline": ["stands tall and speaks after a measured pause"],
                        "appearance": _appearance(
                            age_impression="slightly older adolescent", face_shape="soft oval face", hair="long dark braid",
                            build_silhouette="taller, straight-backed silhouette", palette_costume="pale blue tunic with a green sash",
                            identifying_features="small freckle near the right cheek"),
                        "appearance_provenance": _provenance(choice="green sash separates the older sibling within the shared uniform"),
                        "intentional_similarities": [{"with_id": "younger", "shared_cues": "similar eye shape and family brow", "basis": "the source establishes close kinship"}],
                        "distinguish_from": [{"with_id": "younger", "visual_differences": "taller stance, long braid, and green sash", "behavior_differences": "waits a beat before speaking"}],
                    },
                    {
                        "member_id": "younger", "name": "younger sibling", "role": "younger sister", "role_basis": "the source distinguishes the younger sibling",
                        "relationships": [{"character_id": "elder", "relation": "younger sibling of", "source_basis": "the story names the family relationship"}],
                        "personality_provenance": _provenance(fact="answers quickly", interpretation="more impulsive"),
                        "behavior_baseline": ["leans forward and answers with little pause"],
                        "appearance": _appearance(
                            age_impression="younger adolescent", face_shape="soft oval face", hair="short dark braid",
                            build_silhouette="shorter, forward-leaning silhouette", palette_costume="pale blue tunic with a rust-red sash",
                            identifying_features="small freckle near the left cheek"),
                        "appearance_provenance": _provenance(choice="rust-red sash distinguishes the younger sibling while keeping the family uniform"),
                        "intentional_similarities": [{"with_id": "elder", "shared_cues": "similar eye shape and family brow", "basis": "the source establishes close kinship"}],
                        "distinguish_from": [{"with_id": "elder", "visual_differences": "shorter stance, short braid, and rust-red sash", "behavior_differences": "leans forward and answers with little pause"}],
                    },
                ],
            },
        },
    }
    for character_id, record in design["characters"].items():
        record["contract_reconciliation"] = {
            "status": "contradicted" if character_id == "siblings" else "consistent",
            "source_basis": "the story describes the cast roles and sibling relationship",
            "explanation": "the source distinguishes two siblings, overriding the legacy single-identity contract"
            if character_id == "siblings" else "the existing single-identity contract agrees with the source",
        }
    design = bind_legacy_cast_context(design, resources)
    return resources, design


def test_whole_cast_design_keeps_roles_and_intentional_sibling_similarity():
    resources, design = whole_cast_fixture()
    assert validate_cast_design(design, resources, expected_source_bindings=design["source_bindings"]) == []
    assert design["characters"]["siblings"]["contract_reconciliation"]["legacy_subject_contract"] == {
        "identity_scope": "individual", "subject_count": 1, "member_ids": []
    }
    assert design["characters"]["siblings"]["contract_reconciliation"]["existing_reference_images"] == [
        "assets/characters/siblings.png"
    ]
    assert design["characters"]["siblings"]["subject_contract"]["identity_scope"] == "ensemble"

    siblings = design["characters"]["siblings"]
    prompt = compile_asset_prompt(
        {
            "asset_type": "character_reference",
            "story_purpose": siblings["role"],
            "subject_contract": siblings["subject_contract"],
            "appearance_contract": appearance_contract_from_design(
                siblings, all_records=design["characters"]),
            "visual_spec": {"subject": "two siblings in one reference sheet"},
            "generation_plan": {"reference_inputs": []},
        },
        topic_label="generic ensemble",
    )

    assert "older siblingの個別デザイン" in prompt
    assert "younger siblingの個別デザイン" in prompt
    assert "similar eye shape and family brow" in prompt
    assert "pale blue tunic with a green sash" in prompt
    assert "pale blue tunic with a rust-red sash" in prompt
    assert "taller stance, long braid, and green sash" in prompt
    assert "shorter stance, short braid, and rust-red sash" in prompt
    assert "共通点は保つ" in prompt


def test_role_specific_design_is_generic_and_uses_nonhuman_identity_cues():
    resources, design = whole_cast_fixture()
    heir = design["characters"]["heir"]
    prompt = compile_asset_prompt(
        {
            "asset_type": "character_reference",
            "story_purpose": heir["role"],
            "subject_contract": heir["subject_contract"],
            "appearance_contract": appearance_contract_from_design(heir, all_records=design["characters"]),
            "visual_spec": {"subject": "one character reference"},
            "generation_plan": {"reference_inputs": []},
        },
        topic_label="generic role comparison",
    )
    assert "successor in a ruling household" in prompt
    assert "deep blue formal coat with silver edging" in prompt
    assert "the envoyとの視覚的な区別" in prompt
    assert "natural skin" not in prompt

    animal_resources = {"characters": {"bird": {"name": "bird character"}}, "objects": {}, "locations": {}}
    animal_design = {
        "schema_version": CAST_DESIGN_SCHEMA_VERSION,
        "source_bindings": {},
        "characters": {
            "bird": {
                "character_id": "bird", "name": "bird character",
                "subject_contract": {"identity_scope": "individual", "subject_count": 1, "member_ids": []},
                "role": "messenger bird", "role_basis": "the story identifies it as a messenger",
                "relationships": [], "personality_provenance": _provenance(fact="carries a note"),
                "behavior_baseline": ["tilts its head before taking flight"],
                "appearance": _appearance(
                    age_impression="mature adult bird", face_shape="short hooked beak profile",
                    hair="blue-gray feathers with a pale throat", build_silhouette="compact body and long tail",
                    palette_costume="blue-gray plumage, no clothing", identifying_features="white feather stripe above the right eye"),
                "appearance_provenance": _provenance(choice="the feather stripe is a stable identity marker"),
                "intentional_similarities": [], "distinguish_from": [],
            },
        },
    }
    animal_design["characters"]["bird"]["contract_reconciliation"] = {
        "status": "consistent", "source_basis": "the story names one messenger bird",
        "explanation": "the single-identity contract agrees with the source",
    }
    animal_design = bind_legacy_cast_context(animal_design, animal_resources)
    assert validate_cast_design(animal_design, animal_resources) == []
    animal_prompt = compile_asset_prompt(
        {
            "asset_type": "character_reference", "story_purpose": "messenger bird",
            "subject_contract": animal_design["characters"]["bird"]["subject_contract"],
            "appearance_contract": appearance_contract_from_design(animal_design["characters"]["bird"], all_records=animal_design["characters"]),
            "visual_spec": {"subject": "bird full view"}, "generation_plan": {"reference_inputs": []},
        },
        topic_label="nonhuman character",
    )
    assert "blue-gray feathers with a pale throat" in animal_prompt
    assert "同一個体として識別できる" in animal_prompt
