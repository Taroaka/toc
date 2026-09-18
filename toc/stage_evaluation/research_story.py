"""Compatibility exports for research, visual-value, and story structure.

The former module implemented content rubrics and semantic-review gates. The
production path now delegates to deterministic checks in :mod:`pipeline`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from toc.adaptation_value_contract import (
    source_value_ids as adaptation_source_value_ids,
    visual_value_adaptation_issues,
)
from toc.harness import load_structured_document

from .common import (
    IMAGE_API_PROMPT_POLICY_VERSION,
    IMAGE_API_PROMPT_POLICY_VERSION_V2,
    STORY_REQUIRED_SCENE_FIELDS,
    as_dict,
    as_list,
    flatten_text,
    make_stage,
    nested_get,
    non_empty,
)
from .manifest_nodes import _p300_production_artifact_issues
from .pipeline import (
    check_research,
    check_story,
    compact_research_pack_ok,
    dense_story_scene_count,
    story_scene_coverage_ok,
)


def _image_api_prompt_payload(image_generation: dict[str, Any]) -> dict[str, Any]:
    value = image_generation.get("api_prompt_payload")
    return value if isinstance(value, dict) else {}


def _image_api_prompt_text(image_generation: dict[str, Any]) -> str:
    payload = _image_api_prompt_payload(image_generation)
    return str(payload.get("prompt") or image_generation.get("prompt") or "")


def _image_api_prompt_policy(image_generation: dict[str, Any]) -> str:
    payload = _image_api_prompt_payload(image_generation)
    return str(payload.get("policy_version") or image_generation.get("prompt_policy_version") or "").strip()


def _image_api_prompt_v1_issues(selector: str, image_generation: dict[str, Any]) -> list[str]:
    """Validate only API prompt field shape; semantic prompt quality is absent."""

    policy = _image_api_prompt_policy(image_generation)
    if policy != IMAGE_API_PROMPT_POLICY_VERSION:
        return []
    payload = _image_api_prompt_payload(image_generation)
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return [f"{selector}:api_prompt_missing"]
    return []


def _image_api_prompt_v2_issues(
    selector: str,
    image_generation: dict[str, Any],
    *,
    expected_story_time: str | None = None,
    expected_time_of_day: str | None = None,
) -> list[str]:
    """Validate v2 payload/IR types and declared dependency IDs."""

    del expected_story_time, expected_time_of_day
    policy = _image_api_prompt_policy(image_generation)
    if policy != IMAGE_API_PROMPT_POLICY_VERSION_V2:
        return []
    payload = _image_api_prompt_payload(image_generation)
    issues: list[str] = []
    if not isinstance(payload.get("prompt"), str) or not payload["prompt"].strip():
        issues.append(f"{selector}:api_prompt_missing")
    ir = payload.get("drawable_prompt_ir")
    if not isinstance(ir, dict):
        return issues + [f"{selector}:drawable_prompt_ir_missing"]
    if ir.get("schema_version") != "drawable_prompt_ir_v1":
        issues.append(f"{selector}:drawable_prompt_ir_schema")
    if not isinstance(ir.get("dependencies"), dict):
        issues.append(f"{selector}:drawable_prompt_ir_dependencies")
    if not isinstance(ir.get("included_fragments"), list):
        issues.append(f"{selector}:drawable_prompt_ir_fragments")
    return issues


def _asset_bible_candidate_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return sum(len(items) for items in value.values() if isinstance(items, list))
    return 0


def _scene_key(value: Any) -> str:
    """Normalize authored and runtime scene selectors for ID comparison."""

    text = str(value or "").strip().lower()
    if text.startswith("scene"):
        text = text.removeprefix("scene")
    text = text.replace("_", ".").replace("-", ".")
    parts = [part for part in text.split(".") if part]
    if parts and all(part.isdigit() for part in parts):
        return ".".join(str(int(part)) for part in parts)
    return text


def _visual_scene_coverage_issues(run_dir: Path, data: dict[str, Any]) -> list[str]:
    """Check scene-value projection IDs without assessing creative quality."""

    story_path = run_dir / "story.md"
    if not story_path.is_file():
        return []
    _story_text, story_data = load_structured_document(story_path)
    story_scenes = as_list(nested_get(story_data, ["script", "scenes"], [])) or as_list(story_data.get("scenes"))
    visual_scenes = as_list(data.get("scene_visual_values"))
    if not story_scenes or not visual_scenes:
        return []

    expected = {
        _scene_key(scene.get("scene_id") or index)
        for index, scene in enumerate(story_scenes, start=1)
        if isinstance(scene, dict)
    }
    raw_keys = [
        _scene_key(scene.get("scene_selector") or scene.get("scene_id"))
        if isinstance(scene, dict) else ""
        for scene in visual_scenes
    ]
    runtime_expected = {
        _scene_key(scene.get("canonical_scene_index") or index)
        for index, scene in enumerate(story_scenes, start=1)
        if isinstance(scene, dict)
    }
    runtime_keys = [
        str(int(key) // 10)
        if key.isdigit() and int(key) > 0 and int(key) % 10 == 0 else ""
        for key in raw_keys
    ]
    # Prefer exact authored IDs. Only interpret the legacy runtime numbering
    # when the entire set maps to the canonical scene indices.
    if set(raw_keys) != expected and all(runtime_keys) and set(runtime_keys) == runtime_expected:
        raw_keys = runtime_keys
        expected = runtime_expected
    actual: dict[str, int] = {}
    for index, key in enumerate(raw_keys, start=1):
        if not key:
            return [f"scene_visual_values[{index}]:scene_selector:missing"]
        actual[key] = actual.get(key, 0) + 1

    issues = [
        f"scene_visual_values[{key}]:duplicate_selector"
        for key, count in sorted(actual.items())
        if count > 1
    ]
    issues.extend(f"scene[{key}]:visual_projection_missing" for key in sorted(expected - set(actual)))
    issues.extend(f"scene_visual_values[{key}]:unexpected_projection" for key in sorted(set(actual) - expected))
    return issues


def check_visual_value(
    run_dir: Path,
    profile: str = "standard",
    *,
    forbid_production_artifacts: bool = True,
) -> tuple[dict[str, Any], dict[str, str]]:
    path = run_dir / "visual_value.md"
    checks: list[dict[str, Any]] = []
    from .common import add_check

    add_check(checks, "visual_value.file_exists", path.is_file(), f"{path.name} exists")
    if not path.is_file():
        return make_stage("visual_value", path.name, checks), {}
    _text, data = load_structured_document(path)
    add_check(checks, "visual_value.structured", bool(data), "visual_value.md contains structured YAML output")
    if "scene_visual_values" in data:
        add_check(checks, "visual_value.scene_values_type", isinstance(data.get("scene_visual_values"), list), "scene_visual_values is a list when declared")
    if "handoff" in data:
        add_check(checks, "visual_value.handoff_type", isinstance(data.get("handoff"), dict), "visual_value handoff is a mapping when declared")
    coverage_issues = _visual_scene_coverage_issues(run_dir, data)
    add_check(
        checks,
        "visual_value.scene_coverage",
        not coverage_issues,
        "visual scene-value selectors map to authored story scene IDs"
        + (f" (issues: {','.join(coverage_issues[:8])})" if coverage_issues else ""),
    )
    production_issues = _p300_production_artifact_issues(run_dir) if forbid_production_artifacts else []
    add_check(checks, "visual_value.no_production_artifacts", not production_issues, "visual value stage contains no downstream production files" + (f" (issues: {','.join(production_issues[:8])})" if production_issues else ""))
    if isinstance(data.get("visual_value_metadata"), dict) and "adaptation_value_contract" in data["visual_value_metadata"]:
        story_data = load_structured_document(run_dir / "story.md")[1] if (run_dir / "story.md").is_file() else {}
        issues = visual_value_adaptation_issues(
            data,
            source_value_ids=adaptation_source_value_ids(story_data),
        )
        add_check(
            checks,
            "visual_value.adaptation_value_contract",
            not issues,
            "declared visual-value adaptation contract is structurally consistent"
            + (f" (issues: {','.join(issues[:8])})" if issues else ""),
        )
    return make_stage("visual_value", path.name, checks, details={"scene_value_count": len(as_list(data.get("scene_visual_values")))}), {}


__all__ = [
    "STORY_REQUIRED_SCENE_FIELDS",
    "_asset_bible_candidate_count",
    "_image_api_prompt_policy",
    "_image_api_prompt_text",
    "_image_api_prompt_v1_issues",
    "_image_api_prompt_v2_issues",
    "check_research",
    "check_story",
    "check_visual_value",
    "compact_research_pack_ok",
    "dense_story_scene_count",
    "story_scene_coverage_ok",
]
