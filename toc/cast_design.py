"""Whole-cast character design shared by cinematic and reusable-asset stages."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


CAST_DESIGN_SCHEMA_VERSION = "cast_design_v1"
CAST_DESIGN_AUTHOR_POLICY = "cast_design_author_policy_v1"
CAST_APPEARANCE_FIELDS = (
    "age_impression",
    "face_shape",
    "hair",
    "build_silhouette",
    "palette_costume",
    "identifying_features",
)
PROVENANCE_FIELDS = ("source_facts", "interpretation", "creative_choices")


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _text_list(value: Any) -> bool:
    return isinstance(value, list) and all(_is_text(item) for item in value)


def _provenance_issues(value: Any, path: str) -> list[str]:
    if not isinstance(value, dict) or set(value) != set(PROVENANCE_FIELDS):
        return [f"{path}:provenance_fields_invalid"]
    return [
        f"{path}.{key}:text_list_required"
        for key in PROVENANCE_FIELDS
        if not _text_list(value.get(key))
    ]


def character_subject_contract(resource: Mapping[str, Any]) -> dict[str, Any]:
    raw = resource.get("subject_contract")
    if not isinstance(raw, Mapping):
        return {"identity_scope": "individual", "subject_count": 1, "member_ids": []}
    try:
        count = int(raw.get("subject_count"))
    except (TypeError, ValueError):
        count = 0
    member_ids = raw.get("member_ids")
    if not isinstance(member_ids, list):
        member_ids = []
    return {
        "identity_scope": str(raw.get("identity_scope") or "").strip(),
        "subject_count": count,
        "member_ids": [str(item).strip() for item in member_ids],
    }


def cast_design_output_format(resources: Mapping[str, Any]) -> dict[str, Any]:
    """Build the author-facing shape with one slot for every final cast identity."""
    characters = resources.get("characters") if isinstance(resources, Mapping) else {}
    rows: dict[str, Any] = {}
    for character_id, resource in (characters.items() if isinstance(characters, Mapping) else []):
        rows[str(character_id)] = {
            "character_id": str(character_id),
            "name": str(resource.get("name") or "") if isinstance(resource, Mapping) else "",
            "subject_contract": {
                "identity_scope": "individual|ensemble; decide from source evidence, not a stale legacy default",
                "subject_count": "1 for an individual, or the source-grounded number of ensemble members",
                "member_ids": ["one stable ID for each distinct ensemble member; empty for an individual"],
            },
            "contract_reconciliation": {
                "status": "consistent|contradicted|underdetermined",
                "source_basis": "source pointer or concise source evidence for the effective cardinality",
                "explanation": "whether the legacy subject_contract agrees with source cardinality and why",
            },
            "role": "source-grounded role for the complete story",
            "role_basis": "brief source evidence or explicitly marked interpretation",
            "relationships": [{"character_id": "known character or member ID", "relation": "relationship", "source_basis": "source-grounded basis"}],
            "personality_provenance": {key: [] for key in PROVENANCE_FIELDS},
            "behavior_baseline": ["observable baseline behavior"],
            "appearance": {key: f"{key}; individual only, use species-appropriate cues" for key in CAST_APPEARANCE_FIELDS},
            "appearance_provenance": {key: [] for key in PROVENANCE_FIELDS},
            "intentional_similarities": [],
            "distinguish_from": [],
            "shared_appearance": {"palette_costume": "shared ensemble cue when appropriate; otherwise empty"},
            "shared_appearance_provenance": {key: [] for key in PROVENANCE_FIELDS},
            "members": [{
                "member_id": "exact stable ID from subject_contract.member_ids",
                "name": "source-grounded display name or concise label",
                "role": "member-specific role",
                "role_basis": "source-grounded basis",
                "relationships": [{"character_id": "known character or member ID", "relation": "relationship", "source_basis": "source-grounded basis"}],
                "personality_provenance": {key: [] for key in PROVENANCE_FIELDS},
                "behavior_baseline": ["member-specific observable baseline behavior"],
                "appearance": {key: f"member-specific {key}; use species-appropriate cues" for key in CAST_APPEARANCE_FIELDS},
                "appearance_provenance": {key: [] for key in PROVENANCE_FIELDS},
                "intentional_similarities": [],
                "distinguish_from": [],
            }],
        }
    return {
        "schema_version": CAST_DESIGN_SCHEMA_VERSION,
        "source_bindings": {name: "exact current source binding" for name in ("research", "story", "visual_value")},
        "reference_identity_bindings": "runtime-bound SHA-256 for existing readable character references",
        "characters": rows,
    }


def _similarity_issues(value: Any, *, known_ids: set[str], path: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{path}:list_required"]
    errors = []
    for index, row in enumerate(value):
        row_path = f"{path}/{index}"
        if not isinstance(row, dict) or set(row) != {"with_id", "shared_cues", "basis"}:
            errors.append(f"{row_path}:similarity_fields_invalid")
            continue
        if row.get("with_id") not in known_ids:
            errors.append(f"{row_path}:similarity_target_unknown")
        if not _is_text(row.get("shared_cues")) or not _is_text(row.get("basis")):
            errors.append(f"{row_path}:similarity_text_required")
    return errors


def _distinction_issues(value: Any, *, known_ids: set[str], path: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{path}:list_required"]
    errors = []
    for index, row in enumerate(value):
        row_path = f"{path}/{index}"
        if not isinstance(row, dict) or set(row) != {
            "with_id", "visual_differences", "behavior_differences"
        }:
            errors.append(f"{row_path}:distinction_fields_invalid")
            continue
        if row.get("with_id") not in known_ids:
            errors.append(f"{row_path}:distinction_target_unknown")
        if not _is_text(row.get("visual_differences")) or not _is_text(row.get("behavior_differences")):
            errors.append(f"{row_path}:distinction_text_required")
    return errors


def _appearance_issues(value: Any, path: str) -> list[str]:
    if not isinstance(value, dict) or set(value) != set(CAST_APPEARANCE_FIELDS):
        return [f"{path}:appearance_fields_invalid"]
    return [
        f"{path}.{field}:text_required"
        for field in CAST_APPEARANCE_FIELDS
        if not _is_text(value.get(field))
    ]


def _relationships_issues(value: Any, *, known_ids: set[str], path: str) -> list[str]:
    if not isinstance(value, list):
        return [f"{path}:list_required"]
    errors = []
    for index, row in enumerate(value):
        row_path = f"{path}/{index}"
        if not isinstance(row, dict) or set(row) != {"character_id", "relation", "source_basis"}:
            errors.append(f"{row_path}:relationship_fields_invalid")
            continue
        if row.get("character_id") not in known_ids:
            errors.append(f"{row_path}:relationship_target_unknown")
        if not _is_text(row.get("relation")) or not _is_text(row.get("source_basis")):
            errors.append(f"{row_path}:relationship_text_required")
    return errors


def bind_legacy_cast_context(
    design: dict[str, Any],
    resources: Mapping[str, Any],
    *,
    reference_identity_bindings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach immutable legacy cardinality and reference data for reconciliation."""
    result = deepcopy(design)
    result["reference_identity_bindings"] = deepcopy(dict(reference_identity_bindings or {}))
    records = result.get("characters") if isinstance(result.get("characters"), dict) else {}
    characters = resources.get("characters") if isinstance(resources, Mapping) else {}
    for character_id, record in records.items():
        if not isinstance(record, dict) or not isinstance(characters, Mapping):
            continue
        resource = characters.get(character_id)
        if not isinstance(resource, Mapping):
            continue
        reconciliation = record.get("contract_reconciliation")
        reconciliation = deepcopy(reconciliation) if isinstance(reconciliation, dict) else {}
        reconciliation["legacy_subject_contract"] = character_subject_contract(resource)
        refs = resource.get("references")
        reconciliation["existing_reference_images"] = [
            str(value).strip() for value in refs if isinstance(value, str) and value.strip()
        ] if isinstance(refs, list) else []
        record["contract_reconciliation"] = reconciliation
    return result


def validate_cast_design(
    design: Any,
    resources: Mapping[str, Any],
    *,
    expected_source_bindings: Mapping[str, Any] | None = None,
    expected_reference_identity_bindings: Mapping[str, Any] | None = None,
) -> list[str]:
    """Validate authored coverage and identity boundaries without quality scores."""
    if not isinstance(design, dict):
        return ["cast_design:object_required"]
    if design.get("schema_version") != CAST_DESIGN_SCHEMA_VERSION:
        return ["cast_design:schema_version_invalid"]
    if expected_source_bindings is not None and design.get("source_bindings") != dict(expected_source_bindings):
        return ["cast_design:source_bindings_mismatch"]
    characters = resources.get("characters") if isinstance(resources, Mapping) else None
    records = design.get("characters")
    if not isinstance(characters, Mapping) or not isinstance(records, dict):
        return ["cast_design:character_maps_required"]
    expected_ids = {str(key) for key in characters}
    if set(records) != expected_ids:
        missing = sorted(expected_ids - set(records))
        extra = sorted(set(records) - expected_ids)
        return [f"cast_design:character_coverage_mismatch:missing={missing}:extra={extra}"]
    reference_bindings = design.get("reference_identity_bindings")
    if not isinstance(reference_bindings, dict):
        errors = ["cast_design:reference_identity_bindings_object_required"]
    else:
        errors = []
        if (expected_reference_identity_bindings is not None
                and reference_bindings != dict(expected_reference_identity_bindings)):
            errors.append("cast_design:reference_identity_bindings_mismatch")
        for character_id, bindings in reference_bindings.items():
            resource = characters.get(character_id)
            paths = resource.get("references") if isinstance(resource, Mapping) else []
            paths = {str(value).strip() for value in paths if isinstance(value, str) and value.strip()} if isinstance(paths, list) else set()
            if character_id not in expected_ids or not isinstance(bindings, list):
                errors.append("cast_design:reference_identity_binding_invalid")
                continue
            for binding in bindings:
                if (not isinstance(binding, dict) or set(binding) != {"path", "sha256"}
                        or binding.get("path") not in paths
                        or not isinstance(binding.get("sha256"), str)
                        or len(binding["sha256"]) != 64
                        or any(char not in "0123456789abcdef" for char in binding["sha256"])):
                    errors.append(f"cast_design:reference_identity_binding_invalid:{character_id}")

    member_ids_by_character: dict[str, set[str]] = {}
    contracts = {}
    names = {}
    errors = list(errors)
    for character_id, resource in characters.items():
        names[str(character_id)] = str(resource.get("name") or "").strip() if isinstance(resource, Mapping) else ""
        raw = records[str(character_id)]
        path = f"cast_design.characters.{character_id}"
        if not isinstance(raw, dict):
            errors.append(f"{path}:object_required")
            continue
        raw_contract = raw.get("subject_contract")
        if not isinstance(raw_contract, dict) or set(raw_contract) != {
            "identity_scope", "subject_count", "member_ids"
        }:
            errors.append(f"{path}.subject_contract:fields_required")
        contract = character_subject_contract(raw)
        contracts[str(character_id)] = contract
        member_rows = raw.get("members", [])
        if not isinstance(member_rows, list):
            errors.append(f"{path}.members:list_required")
            member_rows = []
        member_ids = [str(row.get("member_id") or "").strip() for row in member_rows if isinstance(row, dict)]
        member_ids_by_character[str(character_id)] = set(member_ids)
        expected_member_ids = contract["member_ids"]
        scope = contract["identity_scope"]
        if scope == "individual":
            if contract["subject_count"] != 1 or expected_member_ids or member_rows:
                errors.append(f"{path}:individual_cardinality_invalid")
        elif scope == "ensemble":
            if (contract["subject_count"] < 2 or len(expected_member_ids) != contract["subject_count"]
                    or len(set(expected_member_ids)) != len(expected_member_ids)
                    or member_ids != expected_member_ids):
                errors.append(f"{path}:ensemble_member_coverage_mismatch")
        else:
            errors.append(f"{path}:identity_scope_invalid")
    known_ids = set(expected_ids)
    for member_ids in member_ids_by_character.values():
        known_ids.update(member_ids)

    for character_id, resource in characters.items():
        character_id = str(character_id)
        raw = records.get(character_id)
        if not isinstance(raw, dict):
            continue
        path = f"cast_design.characters.{character_id}"
        contract = contracts[character_id]
        expected_name = names[character_id]
        if raw.get("character_id") != character_id or raw.get("name") != expected_name:
            errors.append(f"{path}:identity_binding_mismatch")
        legacy_contract = character_subject_contract(resource if isinstance(resource, Mapping) else {})
        reconciliation = raw.get("contract_reconciliation")
        if not isinstance(reconciliation, dict) or set(reconciliation) != {
            "status", "source_basis", "explanation", "legacy_subject_contract", "existing_reference_images"
        }:
            errors.append(f"{path}.contract_reconciliation:fields_required")
        else:
            if reconciliation.get("status") not in {"consistent", "contradicted", "underdetermined"}:
                errors.append(f"{path}.contract_reconciliation.status:invalid")
            if not _is_text(reconciliation.get("source_basis")) or not _is_text(reconciliation.get("explanation")):
                errors.append(f"{path}.contract_reconciliation:evidence_required")
            refs = resource.get("references") if isinstance(resource, Mapping) else []
            expected_refs = [str(value).strip() for value in refs if isinstance(value, str) and value.strip()] if isinstance(refs, list) else []
            if reconciliation.get("legacy_subject_contract") != legacy_contract or reconciliation.get("existing_reference_images") != expected_refs:
                errors.append(f"{path}.contract_reconciliation:legacy_identity_binding_mismatch")
        if not _is_text(raw.get("role")) or not _is_text(raw.get("role_basis")):
            errors.append(f"{path}:role_and_basis_required")
        errors.extend(_relationships_issues(raw.get("relationships"), known_ids=known_ids, path=f"{path}.relationships"))
        errors.extend(_provenance_issues(raw.get("personality_provenance"), f"{path}.personality_provenance"))
        if not _text_list(raw.get("behavior_baseline")) or not raw.get("behavior_baseline"):
            errors.append(f"{path}.behavior_baseline:text_list_required")
        if contract["identity_scope"] == "individual":
            errors.extend(_appearance_issues(raw.get("appearance"), f"{path}.appearance"))
            errors.extend(_provenance_issues(raw.get("appearance_provenance"), f"{path}.appearance_provenance"))
            errors.extend(_similarity_issues(raw.get("intentional_similarities"), known_ids=known_ids, path=f"{path}.intentional_similarities"))
            errors.extend(_distinction_issues(raw.get("distinguish_from"), known_ids=known_ids, path=f"{path}.distinguish_from"))
        elif contract["identity_scope"] == "ensemble":
            shared = raw.get("shared_appearance", {})
            if not isinstance(shared, dict) or set(shared) - set(CAST_APPEARANCE_FIELDS):
                errors.append(f"{path}.shared_appearance:fields_invalid")
            elif any(not _is_text(value) for value in shared.values()):
                errors.append(f"{path}.shared_appearance:text_required")
            errors.extend(_provenance_issues(raw.get("shared_appearance_provenance"), f"{path}.shared_appearance_provenance"))
            for index, member in enumerate(raw.get("members", []) if isinstance(raw.get("members"), list) else []):
                member_path = f"{path}.members/{index}"
                if not isinstance(member, dict):
                    errors.append(f"{member_path}:object_required")
                    continue
                member_id = str(member.get("member_id") or "").strip()
                if not _is_text(member.get("name")) or not _is_text(member.get("role")) or member_id not in contract["member_ids"]:
                    errors.append(f"{member_path}:identity_and_role_required")
                if not _is_text(member.get("role_basis")):
                    errors.append(f"{member_path}:role_basis_required")
                errors.extend(_relationships_issues(member.get("relationships"), known_ids=known_ids, path=f"{member_path}.relationships"))
                errors.extend(_provenance_issues(member.get("personality_provenance"), f"{member_path}.personality_provenance"))
                if not _text_list(member.get("behavior_baseline")) or not member.get("behavior_baseline"):
                    errors.append(f"{member_path}.behavior_baseline:text_list_required")
                errors.extend(_appearance_issues(member.get("appearance"), f"{member_path}.appearance"))
                errors.extend(_provenance_issues(member.get("appearance_provenance"), f"{member_path}.appearance_provenance"))
                errors.extend(_similarity_issues(member.get("intentional_similarities"), known_ids=known_ids, path=f"{member_path}.intentional_similarities"))
                errors.extend(_distinction_issues(member.get("distinguish_from"), known_ids=known_ids, path=f"{member_path}.distinguish_from"))
    return errors


def cast_design_for_prompt(
    design: Mapping[str, Any] | None,
    character_ids: list[str],
) -> list[dict[str, Any]]:
    """Project only visible cast context to a video cut; never to the still image."""
    if not isinstance(design, Mapping) or not isinstance(design.get("characters"), Mapping):
        return []
    all_characters = design["characters"]
    visible_roots = {str(value) for value in character_ids}
    visible = set(visible_roots)
    for character_id in visible_roots:
        record = all_characters.get(character_id)
        for member in record.get("members", []) if isinstance(record, Mapping) and isinstance(record.get("members"), list) else []:
            if isinstance(member, Mapping) and _is_text(member.get("member_id")):
                visible.add(str(member["member_id"]))
    result = []
    for character_id in character_ids:
        record = all_characters.get(str(character_id))
        if not isinstance(record, Mapping):
            continue
        relationship_rows = record.get("relationships") if isinstance(record.get("relationships"), list) else []
        relationships = [deepcopy(row) for row in relationship_rows
                         if isinstance(row, Mapping) and str(row.get("character_id") or "") in visible]
        row = {
            "character_id": str(character_id),
            "name": str(record.get("name") or ""),
            "role": str(record.get("role") or ""),
            "relationships": relationships,
            "personality_provenance": deepcopy(record.get("personality_provenance") or {}),
            "behavior_baseline": deepcopy(record.get("behavior_baseline") or []),
            "distinguish_from": [
                {key: deepcopy(item.get(key)) for key in ("with_id", "visual_differences", "behavior_differences") if key in item}
                for item in record.get("distinguish_from", [])
                if isinstance(item, Mapping) and str(item.get("with_id") or "") in visible
            ] if isinstance(record.get("distinguish_from"), list) else [],
        }
        if isinstance(record.get("members"), list):
            member_rows = []
            for member in record["members"]:
                if not isinstance(member, Mapping):
                    continue
                member_rows.append({
                    "member_id": member.get("member_id"), "name": member.get("name"),
                    "role": member.get("role"),
                    "relationships": [deepcopy(row) for row in member.get("relationships", [])
                                      if isinstance(row, Mapping) and str(row.get("character_id") or "") in visible]
                    if isinstance(member.get("relationships"), list) else [],
                    "personality_provenance": deepcopy(member.get("personality_provenance") or {}),
                    "behavior_baseline": deepcopy(member.get("behavior_baseline") or []),
                    "distinguish_from": [
                        {key: deepcopy(row.get(key)) for key in ("with_id", "visual_differences", "behavior_differences") if key in row}
                        for row in member.get("distinguish_from", [])
                        if isinstance(row, Mapping) and str(row.get("with_id") or "") in visible
                    ] if isinstance(member.get("distinguish_from"), list) else [],
                })
            row["members"] = member_rows
        result.append(row)
    return result


def _named_comparison_rows(rows: Any, names: Mapping[str, str]) -> list[dict[str, str]]:
    result = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, Mapping):
            continue
        target_id = str(row.get("with_id") or "")
        normalized = {
            "with_id": target_id,
            "with_name": str(names.get(target_id) or target_id),
        }
        for key in ("shared_cues", "basis", "visual_differences", "behavior_differences"):
            if _is_text(row.get(key)):
                normalized[key] = str(row[key]).strip()
        result.append(normalized)
    return result


def _cast_id_names(design: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    records = design.get("characters")
    if not isinstance(records, Mapping):
        return result
    for character_id, record in records.items():
        if not isinstance(record, Mapping):
            continue
        result[str(character_id)] = str(record.get("name") or character_id)
        for member in record.get("members", []) if isinstance(record.get("members"), list) else []:
            if isinstance(member, Mapping):
                member_id = str(member.get("member_id") or "")
                if member_id:
                    result[member_id] = str(member.get("name") or member_id)
    return result


def appearance_contract_from_design(
    record: Mapping[str, Any],
    *,
    all_records: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the imageable subset, keeping performance provenance out of still prompts."""
    names = _cast_id_names({"characters": all_records or {}})
    result: dict[str, Any] = {
        "cast_design_schema_version": CAST_DESIGN_SCHEMA_VERSION,
        "occupation_or_role": str(record.get("role") or ""),
    }
    contract = record.get("subject_contract") if isinstance(record.get("subject_contract"), Mapping) else {}
    result.update({field: str(value) for field, value in (record.get("appearance") or {}).items()
                   if field in CAST_APPEARANCE_FIELDS and _is_text(value)})
    if contract.get("identity_scope") == "ensemble":
        result["identity_scope"] = "ensemble"
        result["shared_appearance"] = deepcopy(record.get("shared_appearance") or {})
        result["members"] = []
        for member in record.get("members", []) if isinstance(record.get("members"), list) else []:
            if not isinstance(member, Mapping):
                continue
            result["members"].append({
                "member_id": str(member.get("member_id") or ""),
                "name": str(member.get("name") or ""),
                "role": str(member.get("role") or ""),
                "appearance": deepcopy(member.get("appearance") or {}),
                "intentional_similarities": _named_comparison_rows(member.get("intentional_similarities"), names),
                "distinguish_from": _named_comparison_rows(member.get("distinguish_from"), names),
            })
    else:
        result["intentional_similarities"] = _named_comparison_rows(record.get("intentional_similarities"), names)
        result["distinguish_from"] = _named_comparison_rows(record.get("distinguish_from"), names)
    return result
