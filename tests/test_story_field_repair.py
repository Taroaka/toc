from __future__ import annotations

from copy import deepcopy
import json

import pytest

from test_story_author_pipeline import _research, _scene
from toc.story_authoring import build_research_registry
from toc.story_field_repair import (
    FieldPatchError,
    apply_field_patch,
    build_field_patch_schema,
    field_repair_issues,
    scene_digest,
)


def _case() -> tuple[dict, dict, dict]:
    registry = build_research_registry(_research())
    scene = _scene("scene_01", "E01", "state_start", "state_clock_found", None, "scene_02")
    plan = {
        "scene_id": "scene_01",
        "source_event_ids": ["E01"],
    }
    return scene, registry, plan


def test_unknown_id_repairs_one_leaf_and_preserves_everything_else() -> None:
    scene, registry, plan = _case()
    broken = deepcopy(scene)
    broken["event_sequence"][0]["participants"] = ["unknown-character"]
    before = deepcopy(broken)

    issues = field_repair_issues(
        broken,
        registry,
        ["story.scene_unknown_id"],
        scene_plan=plan,
    )

    assert [issue["path"] for issue in issues] == ["/event_sequence/0/participants/0"]
    assert issues[0]["expected_type"] == "string"
    assert issues[0]["current"] == "unknown-character"
    assert issues[0]["exists"] is True
    assert "C01" in issues[0]["allowed_values"]

    patched = apply_field_patch(
        broken,
        {
            "scene_id": "scene_01",
            "base_digest": scene_digest(broken),
            "operations": [
                {
                    "path": "/event_sequence/0/participants/0",
                    "value": "C01",
                }
            ],
        },
        issues,
    )

    expected = deepcopy(before)
    expected["event_sequence"][0]["participants"] = ["C01"]
    assert patched == expected
    assert broken == before


def test_malformed_list_only_allows_whole_field_replacement_with_strings() -> None:
    scene, registry, plan = _case()
    broken = deepcopy(scene)
    broken["source_basis"]["character_ids"] = {"bad": "shape"}
    issues = field_repair_issues(
        broken,
        registry,
        ["story.scene_id_list_invalid"],
        scene_plan=plan,
    )

    assert [issue["path"] for issue in issues] == ["/source_basis/character_ids"]
    assert issues[0]["expected_type"] == "strings"

    with pytest.raises(FieldPatchError):
        apply_field_patch(
            broken,
            {
                "scene_id": "scene_01",
                "base_digest": scene_digest(broken),
                "operations": [
                    {"path": "/source_basis/character_ids", "value": "C01"}
                ],
            },
            issues,
        )

    patched = apply_field_patch(
        broken,
        {
            "scene_id": "scene_01",
            "base_digest": scene_digest(broken),
            "operations": [
                {"path": "/source_basis/character_ids", "value": ["C01"]}
            ],
        },
        issues,
    )
    assert patched["source_basis"]["character_ids"] == ["C01"]
    assert patched["event_sequence"] == scene["event_sequence"]


def test_missing_source_basis_event_list_is_the_only_created_id_field() -> None:
    scene, registry, plan = _case()
    broken = deepcopy(scene)
    broken.pop("source_basis")
    issues = field_repair_issues(
        broken,
        registry,
        ["story.scene_source_event_coverage"],
        scene_plan=plan,
    )

    assert [issue["path"] for issue in issues] == ["/source_basis/event_ids"]
    patched = apply_field_patch(
        broken,
        {
            "scene_id": "scene_01",
            "base_digest": scene_digest(broken),
            "operations": [
                {"path": "/source_basis/event_ids", "value": ["E01"]}
            ],
        },
        issues,
    )
    assert patched["source_basis"] == {"event_ids": ["E01"]}
    assert "event_sequence" in patched


def test_lifecycle_diagnostics_only_expose_missing_or_nonmapping_allowed_maps() -> None:
    scene, registry, plan = _case()
    broken = deepcopy(scene)
    broken["scene_intent"] = "bad"
    broken.pop("start_state")
    broken.pop("preservation")
    broken.pop("reveal_contract", None)

    issues = field_repair_issues(
        broken,
        registry,
        ["story.scene_lifecycle_missing"],
        scene_plan=plan,
    )

    assert {issue["path"] for issue in issues} == {
        "/scene_intent",
        "/start_state",
        "/preservation",
    }
    assert all(issue["expected_type"] == "object" for issue in issues)
    assert "/event_sequence" not in {issue["path"] for issue in issues}

    with pytest.raises(FieldPatchError):
        apply_field_patch(
            broken,
            {
                "scene_id": "scene_01",
                "base_digest": scene_digest(broken),
                "operations": [
                    {"path": "/scene_intent", "value": json.dumps([])}
                ],
            },
            issues,
        )


def test_schema_is_closed_and_binds_original_scene_and_digest() -> None:
    scene, registry, plan = _case()
    broken = deepcopy(scene)
    broken["event_sequence"][0]["source_refs"] = ["missing-source"]
    issues = field_repair_issues(
        broken,
        registry,
        ["story.scene_unknown_id"],
        scene_plan=plan,
    )
    schema = build_field_patch_schema(broken, issues)

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"scene_id", "base_digest", "operations"}
    assert schema["properties"]["scene_id"]["enum"] == ["scene_01"]
    assert schema["properties"]["base_digest"]["enum"] == [scene_digest(broken)]
    operation_schema = schema["properties"]["operations"]["items"]
    assert operation_schema["additionalProperties"] is False
    assert set(operation_schema["required"]) == {"path", "value"}
    assert operation_schema["properties"]["path"]["enum"] == [
        "/event_sequence/0/source_refs/0"
    ]
    assert operation_schema["properties"]["value"] == {
        "anyOf": [
            {"type": "string"},
            {"type": "array", "items": {"type": "string"}},
            {"type": "null"},
        ]
    }


def test_unknown_turning_event_beat_is_a_bounded_scalar_issue() -> None:
    scene, registry, plan = _case()
    broken = deepcopy(scene)
    broken["turning_event"]["beat_id"] = "unknown-beat"
    issues = field_repair_issues(
        broken,
        registry,
        ["story.scene_turning_event_invalid"],
        scene_plan=plan,
    )

    assert [issue["path"] for issue in issues] == ["/turning_event/beat_id"]
    patched = apply_field_patch(
        broken,
        {
            "scene_id": "scene_01",
            "base_digest": scene_digest(broken),
            "operations": [
                {
                    "path": "/turning_event/beat_id",
                    "value": "scene_01_beat_01",
                }
            ],
        },
        issues,
    )
    assert patched["turning_event"]["beat_id"] == "scene_01_beat_01"
    assert patched["event_sequence"] == scene["event_sequence"]


def test_object_patch_rejects_duplicate_keys_and_nonfinite_numbers() -> None:
    scene, registry, plan = _case()
    broken = deepcopy(scene)
    broken.pop("scene_intent")
    issues = field_repair_issues(
        broken,
        registry,
        ["story.scene_lifecycle_missing"],
        scene_plan=plan,
    )
    for encoded in ('{"a": 1, "a": 2}', '{"a": NaN}'):
        with pytest.raises(FieldPatchError):
            apply_field_patch(
                broken,
                {
                    "scene_id": "scene_01",
                    "base_digest": scene_digest(broken),
                    "operations": [{"path": "/scene_intent", "value": encoded}],
                },
                issues,
            )


def test_malformed_array_element_is_a_removable_leaf() -> None:
    scene, registry, plan = _case()
    broken = deepcopy(scene)
    broken["event_sequence"][0]["participants"] = ["C01", {"unregistered": True}]
    issues = field_repair_issues(
        broken,
        registry,
        ["story.scene_id_list_invalid"],
        scene_plan=plan,
    )

    assert [issue["path"] for issue in issues] == ["/event_sequence/0/participants/1"]
    assert issues[0]["expected_type"] == "string"
    assert issues[0]["allow_remove"] is True
    assert all(issue["path"] != "/event_sequence/0/participants" for issue in issues)

    patched = apply_field_patch(
        broken,
        {
            "scene_id": "scene_01",
            "base_digest": scene_digest(broken),
            "operations": [
                {"path": "/event_sequence/0/participants/1", "value": None}
            ],
        },
        issues,
    )
    assert patched["event_sequence"][0]["participants"] == ["C01"]


def test_multiple_removals_use_original_indices_and_preserve_good_neighbors() -> None:
    scene, registry, plan = _case()
    broken = deepcopy(scene)
    broken["event_sequence"][0]["participants"] = ["門番（未登録）", "C01", "六匹の鼠"]
    broken["source_basis"]["place_ids"] = ["unregistered-place", "L01"]
    issues = field_repair_issues(
        broken,
        registry,
        ["story.scene_unknown_id"],
        scene_plan=plan,
    )

    assert {issue["path"] for issue in issues} == {
        "/event_sequence/0/participants/0",
        "/event_sequence/0/participants/2",
        "/source_basis/place_ids/0",
    }
    assert all(issue["allow_remove"] is True for issue in issues)

    patched = apply_field_patch(
        broken,
        {
            "scene_id": "scene_01",
            "base_digest": scene_digest(broken),
            "operations": [
                {"path": "/event_sequence/0/participants/0", "value": None},
                {"path": "/event_sequence/0/participants/2", "value": None},
                {"path": "/source_basis/place_ids/0", "value": "L02"},
            ],
        },
        issues,
    )
    assert patched["event_sequence"][0]["participants"] == ["C01"]
    assert patched["source_basis"]["place_ids"] == ["L02", "L01"]
    assert patched["event_sequence"][0]["source_refs"] == scene["event_sequence"][0]["source_refs"]


def test_removal_rejects_valid_nonlisted_root_and_nonempty_required_list_violations() -> None:
    scene, registry, plan = _case()
    broken = deepcopy(scene)
    broken["event_sequence"][0]["participants"] = ["unknown", "C01"]
    issues = field_repair_issues(
        broken,
        registry,
        ["story.scene_unknown_id"],
        scene_plan=plan,
    )
    issue = next(issue for issue in issues if issue["path"].endswith("/participants/0"))

    valid_issue = dict(issue)
    valid_issue.update(
        path="/event_sequence/0/participants/1",
        current="C01",
        allow_remove=True,
    )
    with pytest.raises(FieldPatchError):
        apply_field_patch(
            broken,
            {
                "scene_id": "scene_01",
                "base_digest": scene_digest(broken),
                "operations": [
                    {"path": "/event_sequence/0/participants/1", "value": None}
                ],
            },
            [valid_issue],
        )

    with pytest.raises(FieldPatchError):
        apply_field_patch(
            broken,
            {
                "scene_id": "scene_01",
                "base_digest": scene_digest(broken),
                "operations": [
                    {"path": "/event_sequence/0/participants/99", "value": None}
                ],
            },
            issues,
        )

    root_issue = dict(issue)
    root_issue.update(
        path="/event_sequence/0/participants",
        expected_type="strings",
        current=["unknown", "C01"],
        allow_remove=True,
    )
    with pytest.raises(FieldPatchError):
        apply_field_patch(
            broken,
            {
                "scene_id": "scene_01",
                "base_digest": scene_digest(broken),
                "operations": [
                    {"path": "/event_sequence/0/participants", "value": None}
                ],
            },
            [root_issue],
        )

    sole = deepcopy(broken)
    sole["event_sequence"][0]["participants"] = ["unknown"]
    sole_issues = field_repair_issues(
        sole,
        registry,
        ["story.scene_unknown_id"],
        scene_plan=plan,
    )
    with pytest.raises(FieldPatchError):
        apply_field_patch(
            sole,
            {
                "scene_id": "scene_01",
                "base_digest": scene_digest(sole),
                "operations": [
                    {"path": "/event_sequence/0/participants/0", "value": None}
                ],
            },
            sole_issues,
        )


def test_null_is_disallowed_for_nonremovable_diagnosed_fields() -> None:
    scene, registry, plan = _case()
    broken = deepcopy(scene)
    broken["turning_event"]["beat_id"] = "unknown-beat"
    issues = field_repair_issues(
        broken,
        registry,
        ["story.scene_turning_event_invalid"],
        scene_plan=plan,
    )
    assert "allow_remove" not in issues[0]
    with pytest.raises(FieldPatchError):
        apply_field_patch(
            broken,
            {
                "scene_id": "scene_01",
                "base_digest": scene_digest(broken),
                "operations": [{"path": "/turning_event/beat_id", "value": None}],
            },
            issues,
        )


@pytest.mark.parametrize(
    "response",
    [
        {
            "scene_id": "other-scene",
            "base_digest": "ignored",
            "operations": [],
        },
        {
            "scene_id": "scene_01",
            "base_digest": "wrong",
            "operations": [],
        },
    ],
)
def test_apply_rejects_scene_identity_or_digest_mismatch(response: dict) -> None:
    scene, registry, plan = _case()
    broken = deepcopy(scene)
    broken["event_sequence"][0]["participants"] = ["unknown-character"]
    issues = field_repair_issues(
        broken,
        registry,
        ["story.scene_unknown_id"],
        scene_plan=plan,
    )
    with pytest.raises(FieldPatchError):
        apply_field_patch(broken, response, issues)


def test_apply_rejects_unrelated_root_noop_and_overlapping_paths() -> None:
    scene, registry, plan = _case()
    broken = deepcopy(scene)
    broken["event_sequence"][0]["participants"] = ["unknown-character"]
    issues = field_repair_issues(
        broken,
        registry,
        ["story.scene_unknown_id"],
        scene_plan=plan,
    )

    base = {"scene_id": "scene_01", "base_digest": scene_digest(broken)}
    with pytest.raises(FieldPatchError):
        apply_field_patch(
            broken,
            {
                **base,
                "operations": [{"path": "/event_sequence", "value": "rewrite"}],
            },
            issues,
        )
    with pytest.raises(FieldPatchError):
        apply_field_patch(
            broken,
            {
                **base,
                "operations": [
                    {
                        "path": "/event_sequence/0/participants/0",
                        "value": "unknown-character",
                    }
                ],
            },
            issues,
        )

    overlap_issues = issues + [
        {
            "path": "/event_sequence/0/participants",
            "code": "story.scene_id_list_invalid",
            "expected_type": "strings",
            "current": ["unknown-character"],
            "exists": True,
            "message": "bad list",
        }
    ]
    with pytest.raises(FieldPatchError):
        apply_field_patch(
            broken,
            {
                **base,
                "operations": [
                    {
                        "path": "/event_sequence/0/participants/0",
                        "value": "C01",
                    },
                    {"path": "/event_sequence/0/participants", "value": ["C01"]},
                ],
            },
            overlap_issues,
        )
