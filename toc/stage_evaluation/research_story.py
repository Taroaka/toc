"""Compatibility exports for research, visual-value, and story structure.

The former module implemented content rubrics and semantic-review gates. The
production path now delegates to deterministic checks in :mod:`pipeline`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
    production_issues = _p300_production_artifact_issues(run_dir) if forbid_production_artifacts else []
    add_check(checks, "visual_value.no_production_artifacts", not production_issues, "visual value stage contains no downstream production files" + (f" (issues: {','.join(production_issues[:8])})" if production_issues else ""))
    if isinstance(data.get("visual_value_metadata"), dict) and "adaptation_value_contract" in data["visual_value_metadata"]:
        contract = data["visual_value_metadata"]["adaptation_value_contract"]
        add_check(checks, "visual_value.adaptation_value_contract_type", isinstance(contract, dict), "declared adaptation value contract is a mapping")
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
