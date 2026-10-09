"""Offline validation and schematic projection for metric shot geometry."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


MAX_ABS_METERS = 1_000_000.0
MAX_SUBJECTS = 64
MAX_LIGHTS = 32
MIN_ASPECT_RATIO = 0.01
MAX_ASPECT_RATIO = 100.0


GEOMETRY_FORMAT: dict[str, Any] = {
    "type": "object",
    "required": ["schema_version", "camera", "subjects", "lights"],
    "properties": {
        "schema_version": {"const": "shot_geometry_v1"},
        "camera": {
            "type": "object",
            "required": ["position", "target", "vertical_fov_degrees", "aspect_ratio"],
            "properties": {
                "position": {"$ref": "#/$defs/vector3"},
                "target": {"$ref": "#/$defs/vector3"},
                "vertical_fov_degrees": {"type": "number", "exclusiveMinimum": 1, "exclusiveMaximum": 179},
                "aspect_ratio": {"type": "number", "minimum": MIN_ASPECT_RATIO, "maximum": MAX_ASPECT_RATIO},
            },
            "additionalProperties": False,
        },
        "subjects": {
            "type": "array",
            "maxItems": MAX_SUBJECTS,
            "items": {
                "type": "object",
                "required": ["asset_id", "name", "position", "size"],
                "properties": {
                    "asset_id": {"type": "string", "minLength": 1},
                    "name": {"type": "string", "minLength": 1},
                    "position": {"$ref": "#/$defs/vector3"},
                    "size": {"$ref": "#/$defs/positive_vector3"},
                },
                "additionalProperties": False,
            },
        },
        "lights": {
            "type": "array",
            "maxItems": MAX_LIGHTS,
            "items": {
                "type": "object",
                "required": ["name", "position", "range_m"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "position": {"$ref": "#/$defs/vector3"},
                    "range_m": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_ABS_METERS},
                },
                "additionalProperties": False,
            },
        },
    },
    "$defs": {
        "vector3": {
            "type": "array",
            "items": {"type": "number", "minimum": -MAX_ABS_METERS, "maximum": MAX_ABS_METERS},
            "minItems": 3,
            "maxItems": 3,
        },
        "positive_vector3": {
            "type": "array",
            "items": {"type": "number", "exclusiveMinimum": 0, "maximum": MAX_ABS_METERS},
            "minItems": 3,
            "maxItems": 3,
        },
    },
    "additionalProperties": False,
}


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _require_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    unknown = set(value) - expected
    if unknown:
        raise ValueError(f"{label} contains unknown field(s): {', '.join(sorted(map(str, unknown)))}")


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _vector(value: Any, label: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{label} must contain exactly three finite coordinates")
    vector = [_number(component, f"{label}[{index}]") for index, component in enumerate(value)]
    if any(abs(component) > MAX_ABS_METERS for component in vector):
        raise ValueError(f"{label} coordinates and dimensions must be within ±{MAX_ABS_METERS:g} m")
    return vector


def validate_geometry(value: Any, allowed_assets: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Validate and normalize the versioned Z-up, metric shot geometry contract.

    When an allowlist is supplied, subject IDs must exist in it and its names become
    the canonical display names. The input object is never mutated.
    """
    root = _mapping(value, "geometry")
    _require_keys(root, {"schema_version", "camera", "subjects", "lights"}, "geometry")
    if root.get("schema_version") != "shot_geometry_v1":
        raise ValueError("unsupported geometry schema_version")
    camera = _mapping(root.get("camera"), "camera")
    _require_keys(camera, {"position", "target", "vertical_fov_degrees", "aspect_ratio"}, "camera")
    position = _vector(camera.get("position"), "camera.position")
    target = _vector(camera.get("target"), "camera.target")
    if math.dist(target, position) <= 1e-9:
        raise ValueError("camera position and target must not be identical")
    fov = _number(camera.get("vertical_fov_degrees"), "camera.vertical_fov_degrees")
    if not 1 < fov < 179:
        raise ValueError("camera vertical_fov_degrees must be greater than 1 and less than 179")
    aspect = _number(camera.get("aspect_ratio"), "camera.aspect_ratio")
    if not MIN_ASPECT_RATIO <= aspect <= MAX_ASPECT_RATIO:
        raise ValueError(f"camera aspect_ratio must be between {MIN_ASPECT_RATIO:g} and {MAX_ASPECT_RATIO:g}")

    if not isinstance(root.get("subjects"), list) or not isinstance(root.get("lights"), list):
        raise ValueError("subjects and lights must be arrays")
    if len(root["subjects"]) > MAX_SUBJECTS:
        raise ValueError(f"subjects must contain at most {MAX_SUBJECTS} entries")
    if len(root["lights"]) > MAX_LIGHTS:
        raise ValueError(f"lights must contain at most {MAX_LIGHTS} entries")
    assets = None
    if allowed_assets is not None:
        assets = _mapping(allowed_assets, "allowed_assets")
    subjects: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(root["subjects"]):
        subject = _mapping(raw, f"subjects[{index}]")
        _require_keys(subject, {"asset_id", "name", "position", "size"}, f"subjects[{index}]")
        asset_id = subject.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise ValueError(f"subjects[{index}].asset_id must be a non-empty string")
        if asset_id in seen_ids:
            raise ValueError(f"duplicate subject asset_id: {asset_id}")
        seen_ids.add(asset_id)
        if assets is not None:
            if asset_id not in assets:
                raise ValueError(f"unknown subject asset_id: {asset_id}")
            name = assets[asset_id]
        else:
            name = subject.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"subjects[{index}].name must be a non-empty string")
        size = _vector(subject.get("size"), f"subjects[{index}].size")
        if any(component <= 0 for component in size):
            raise ValueError(f"subjects[{index}].size dimensions must be positive")
        subjects.append({
            "asset_id": asset_id,
            "name": name.strip(),
            "position": _vector(subject.get("position"), f"subjects[{index}].position"),
            "size": size,
        })

    lights: list[dict[str, Any]] = []
    for index, raw in enumerate(root["lights"]):
        light = _mapping(raw, f"lights[{index}]")
        _require_keys(light, {"name", "position", "range_m"}, f"lights[{index}]")
        name = light.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"lights[{index}].name must be a non-empty string")
        range_m = _number(light.get("range_m"), f"lights[{index}].range_m")
        if not 0 < range_m <= MAX_ABS_METERS:
            raise ValueError(f"lights[{index}].range_m must be positive and at most {MAX_ABS_METERS:g} m")
        lights.append({"name": name.strip(), "position": _vector(light.get("position"), f"lights[{index}].position"), "range_m": range_m})

    return {
        "schema_version": "shot_geometry_v1",
        "camera": {"position": position, "target": target, "vertical_fov_degrees": fov, "aspect_ratio": aspect},
        "subjects": subjects,
        "lights": lights,
    }


def project_geometry(geometry: Any) -> dict[str, Any]:
    """Project geometry into normalized camera and top-down rectangles for SVG.

    The result is a schematic layout aid. Light ranges are displayed as circles,
    not as claims about photometric falloff or illumination.
    """
    scene = validate_geometry(geometry)
    camera = scene["camera"]
    direction = [camera["target"][i] - camera["position"][i] for i in range(3)]
    forward = _normalize(direction)
    world_up = [0.0, 0.0, 1.0]
    right = _cross(forward, world_up)
    if _length(right) < 1e-10:  # Vertical aim: choose world Y as a stable reference.
        right = _cross(forward, [0.0, 1.0, 0.0])
    right = _normalize(right)
    up = _normalize(_cross(right, forward))
    tan_half_vertical = math.tan(math.radians(camera["vertical_fov_degrees"]) / 2)
    tan_half_horizontal = tan_half_vertical * camera["aspect_ratio"]
    camera_items = []
    for subject in scene["subjects"]:
        corners = []
        center = subject["position"]
        half = [dimension / 2 for dimension in subject["size"]]
        for sx in (-1, 1):
            for sy in (-1, 1):
                for sz in (-1, 1):
                    world = [center[0] + sx * half[0], center[1] + sy * half[1], center[2] + sz * half[2]]
                    relative = [world[i] - camera["position"][i] for i in range(3)]
                    depth = _dot(relative, forward)
                    if depth > 1e-9:
                        nx = _dot(relative, right) / (depth * tan_half_horizontal)
                        ny = _dot(relative, up) / (depth * tan_half_vertical)
                        corners.append(((1 + nx) / 2, (1 - ny) / 2))
        center_relative = [center[i] - camera["position"][i] for i in range(3)]
        depth = _dot(center_relative, forward)
        if depth <= 1e-9 or not corners:
            x = y = width = height = 0.0
            visible = False
        else:
            left = min(point[0] for point in corners)
            right_edge = max(point[0] for point in corners)
            top = min(point[1] for point in corners)
            bottom = max(point[1] for point in corners)
            visible = right_edge > 0 and left < 1 and bottom > 0 and top < 1
            clipped_left, clipped_right = max(0.0, left), min(1.0, right_edge)
            clipped_top, clipped_bottom = max(0.0, top), min(1.0, bottom)
            x, y = clipped_left, clipped_top
            width, height = max(0.0, clipped_right - clipped_left), max(0.0, clipped_bottom - clipped_top)
        camera_items.append({
            "asset_id": subject["asset_id"], "name": subject["name"],
            "x": x, "y": y, "width": width, "height": height,
            "depth": depth, "visible": visible,
        })

    x_values: list[float] = []
    y_values: list[float] = []
    for subject in scene["subjects"]:
        x, y, width, depth = *subject["position"][:2], *subject["size"][:2]
        x_values.extend((x - width / 2, x + width / 2))
        y_values.extend((y - depth / 2, y + depth / 2))
    for light in scene["lights"]:
        x, y = light["position"][:2]
        radius = light["range_m"]
        x_values.extend((x - radius, x + radius))
        y_values.extend((y - radius, y + radius))
    x_values.extend((camera["position"][0], camera["target"][0]))
    y_values.extend((camera["position"][1], camera["target"][1]))
    if not x_values:
        x_values, y_values = [-1.0, 1.0], [-1.0, 1.0]
    min_x, max_x = min(x_values), max(x_values)
    min_y, max_y = min(y_values), max(y_values)
    if max_x - min_x < 1e-9:
        min_x, max_x = min_x - 0.5, max_x + 0.5
    if max_y - min_y < 1e-9:
        min_y, max_y = min_y - 0.5, max_y + 0.5
    span_x, span_y = max_x - min_x, max_y - min_y
    top_subjects = []
    for subject in scene["subjects"]:
        px, py = subject["position"][:2]
        sx, sy = subject["size"][:2]
        top_subjects.append({
            "asset_id": subject["asset_id"], "name": subject["name"],
            "x": (px - sx / 2 - min_x) / span_x,
            "y": (max_y - (py + sy / 2)) / span_y,
            "width": sx / span_x, "height": sy / span_y,
        })
    top_lights = []
    for light in scene["lights"]:
        px, py = light["position"][:2]
        r = light["range_m"]
        top_lights.append({
            "name": light["name"], "x": (px - min_x) / span_x,
            "y": (max_y - py) / span_y, "range_m": r,
            "range_radius_x": r / span_x, "range_radius_y": r / span_y,
            "range_is_schematic": True,
        })
    return {
        "schema_version": "shot_geometry_projection_v1",
        "camera_view_aspect_ratio": camera["aspect_ratio"],
        "camera_view": camera_items,
        "top_view": {
            "subjects": top_subjects,
            "lights": top_lights,
            "camera": {"x": (camera["position"][0] - min_x) / span_x, "y": (max_y - camera["position"][1]) / span_y},
            "target": {"x": (camera["target"][0] - min_x) / span_x, "y": (max_y - camera["target"][1]) / span_y},
            "bounds_m": {"min_x": min_x, "max_x": max_x, "min_y": min_y, "max_y": max_y},
        },
    }


def geometry_prompt(geometry: Any) -> str:
    """Render validated geometry as concrete Japanese shot instructions."""
    scene = validate_geometry(geometry)
    camera = scene["camera"]
    lines = [
        "開始時の撮影配置を次のメートル単位の幾何指定に合わせる。座標系はZ軸が上、XY平面が地面。",
        f"カメラ位置は {_fmt(camera['position'])} m、注視点は {_fmt(camera['target'])} m。",
        f"垂直画角は {camera['vertical_fov_degrees']:g} 度、画面アスペクト比は {camera['aspect_ratio']:g}。",
    ]
    for subject in scene["subjects"]:
        lines.append(
            f"被写体「{subject['name']}」の中心を {_fmt(subject['position'])} m に置き、幅・奥行き・高さを {_fmt(subject['size'])} m にする。"
        )
    for light in scene["lights"]:
        lines.append(f"ライト「{light['name']}」を {_fmt(light['position'])} m に配置し、指定レンジは {light['range_m']:g} m。")
    lines.append("この配置指定は構図の目安であり、照度や光量の物理的な正確さを表すものではない。")
    return "\n".join(lines)


def _fmt(vector: list[float]) -> str:
    return "(" + ", ".join(f"{value:g}" for value in vector) + ")"


def _dot(a: list[float], b: list[float]) -> float:
    return sum(a[i] * b[i] for i in range(3))


def _cross(a: list[float], b: list[float]) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _length(vector: list[float]) -> float:
    return math.sqrt(_dot(vector, vector))


def _normalize(vector: list[float]) -> list[float]:
    length = _length(vector)
    if length <= 1e-18:
        raise ValueError("cannot normalize a zero-length vector")
    return [component / length for component in vector]
