import copy
import math

import pytest

from toc import spatial_previs as spatial


def geometry():
    return {
        "schema_version": "shot_geometry_v1",
        "camera": {
            "position": [0, -6, 2],
            "target": [0, 0, 1],
            "vertical_fov_degrees": 50,
            "aspect_ratio": 16 / 9,
        },
        "subjects": [
            {"asset_id": "hero", "name": "旅人", "position": [0, 0, 1], "size": [1, 1, 2]},
            {"asset_id": "prop", "name": "箱", "position": [2, 1, 0.5], "size": [0.5, 0.5, 1]},
        ],
        "lights": [{"name": "key", "position": [-2, -3, 4], "range_m": 5}],
    }


def test_validate_normalizes_metric_geometry_and_uses_allowed_asset_names():
    value = geometry()
    normalized = spatial.validate_geometry(value, allowed_assets={"hero": "主人公", "prop": "小箱"})
    assert normalized["schema_version"] == "shot_geometry_v1"
    assert normalized["subjects"][0]["name"] == "主人公"
    assert normalized["subjects"][0]["position"] == [0.0, 0.0, 1.0]
    assert normalized["camera"]["vertical_fov_degrees"] == 50.0
    assert value["subjects"][0]["name"] == "旅人"  # validation does not mutate its input


@pytest.mark.parametrize("mutate", [
    lambda g: g["camera"].update(position=[0, 0, float("nan")]),
    lambda g: g["camera"].update(position=[0, 0]),
    lambda g: g["camera"].update(target=[0, -6, 2]),
    lambda g: g["camera"].update(vertical_fov_degrees=1),
    lambda g: g["camera"].update(vertical_fov_degrees=179),
    lambda g: g["subjects"][0].update(size=[1, 0, 2]),
    lambda g: g["subjects"].append(copy.deepcopy(g["subjects"][0])),
    lambda g: g["lights"][0].update(range_m=0),
])
def test_invalid_geometry_is_rejected(mutate):
    value = geometry()
    mutate(value)
    with pytest.raises(ValueError):
        spatial.validate_geometry(value)


def test_unknown_subject_asset_id_is_rejected_when_allowlist_is_supplied():
    with pytest.raises(ValueError, match="asset"):
        spatial.validate_geometry(geometry(), allowed_assets={"hero": "主人公"})


@pytest.mark.parametrize("mutate", [
    lambda g: g["camera"].update(position=[1e308, 0, 0]),
    lambda g: g["camera"].update(aspect_ratio=1e-300),
    lambda g: g["camera"].update(aspect_ratio=101),
    lambda g: g["subjects"][0].update(size=[1e7, 1, 1]),
    lambda g: g["lights"][0].update(range_m=1e7),
    lambda g: g["subjects"].extend(
        {"asset_id": f"extra-{i}", "name": "追加", "position": [0, 0, 0], "size": [1, 1, 1]}
        for i in range(63)
    ),
    lambda g: g["lights"].extend({"name": f"extra-{i}", "position": [0, 0, 0], "range_m": 1} for i in range(32)),
    lambda g: g.update(unexpected=True),
    lambda g: g["camera"].update(unexpected=True),
    lambda g: g["subjects"][0].update(unexpected=True),
    lambda g: g["lights"][0].update(unexpected=True),
])
def test_practical_bounds_and_unknown_fields_are_rejected(mutate):
    value = geometry()
    mutate(value)
    with pytest.raises(ValueError):
        spatial.validate_geometry(value)


def test_geometry_format_documents_projection_safety_bounds():
    camera_properties = spatial.GEOMETRY_FORMAT["properties"]["camera"]["properties"]
    assert camera_properties["aspect_ratio"]["minimum"] == 0.01
    assert camera_properties["aspect_ratio"]["maximum"] == 100
    assert spatial.GEOMETRY_FORMAT["properties"]["subjects"]["maxItems"] == 64
    assert spatial.GEOMETRY_FORMAT["properties"]["lights"]["maxItems"] == 32


def test_camera_and_top_projections_return_normalized_schematic_rectangles():
    result = spatial.project_geometry(spatial.validate_geometry(geometry()))
    assert result["camera_view_aspect_ratio"] == pytest.approx(16 / 9)
    assert result["camera_view"][0]["asset_id"] == "hero"
    assert result["camera_view"][0]["visible"] is True
    assert 0 <= result["camera_view"][0]["x"] <= 1
    assert 0 <= result["camera_view"][0]["y"] <= 1
    assert result["camera_view"][0]["width"] > 0
    assert result["camera_view"][0]["height"] > 0
    assert result["camera_view"][0]["depth"] > 0
    assert result["top_view"]["subjects"][0]["asset_id"] == "hero"
    assert result["top_view"]["lights"][0]["range_m"] == 5.0
    assert result["top_view"]["lights"][0]["range_is_schematic"] is True


def test_projection_handles_vertical_camera_aim_and_marks_behind_subject_hidden():
    value = geometry()
    value["camera"].update(position=[0, 0, 0], target=[0, 0, 5])
    value["subjects"][0].update(position=[0, 0, -3])
    value["subjects"][1].update(position=[0, 0, 2])
    result = spatial.project_geometry(spatial.validate_geometry(value))
    assert result["camera_view"][0]["visible"] is False
    assert result["camera_view"][0]["depth"] < 0
    assert all(math.isfinite(item) for item in (result["camera_view"][1]["x"], result["camera_view"][1]["y"]))


def test_prompt_uses_names_and_concrete_metric_instructions_without_internal_ids():
    value = spatial.validate_geometry(geometry())
    prompt = spatial.geometry_prompt(value)
    assert prompt.startswith("開始時の撮影配置")
    assert "旅人" in prompt
    assert "箱" in prompt
    assert "hero" not in prompt
    assert "Z軸" in prompt
    assert "50" in prompt


def test_geometry_format_exposes_versioned_contract_schema():
    assert spatial.GEOMETRY_FORMAT["properties"]["schema_version"]["const"] == "shot_geometry_v1"
    assert "camera" in spatial.GEOMETRY_FORMAT["required"]
