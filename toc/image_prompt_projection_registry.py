"""Canonical key-to-prompt projection and review registry.

The registry separates upstream design keys from provider prose.  It tells the
compiler and reviewers which drawable group owns a key, when that group is
active, and which deterministic and semantic checks must accompany it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping


PROMPT_PROJECTION_REGISTRY_VERSION = "prompt_projection_registry_v2"
PROMPT_PROJECTION_RELEVANCE = {"required", "conditional", "none"}
_OPAQUE_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_WHITESPACE_RE = re.compile(r"\s+")
_INTERNAL_META_RE = re.compile(
    r"(?:first_frame_visual_plan|cut_contract|scene_event|source_event_contract|"
    r"event_context_for_cut|validation_gates|source_event_beat_id|event_time_position|"
    r"what_happens|visible_action|motion_brief|debug_prompt_source|api_prompt_payload|"
    r"drawable_prompt_ir|dependencies|included_fragments|omitted_groups|required_groups|compiler_version|"
    r"shot_design_contract|cut_location_frame_plan|cut_visual_delta|blocking_and_interaction|"
    r"scene_state_progression_plan|cut_state_progression|"
    r"\bscene\d+(?:\.\d+)?(?:[_-](?:cut|event)[A-Za-z0-9_.-]*)?\b)",
    re.IGNORECASE,
)
_ABSTRACT_STORY_RE = re.compile(
    r"場面の核|観客理解|因果の証明|価値変化|場所の圧力|場のルール|主人公の制限"
)
_GENERIC_TEXT_MARKERS = (
    "この項目は、他の具体描写",
    "scene固有の自然な光源",
    "人物と小道具の形が読める方向",
    "場所固有の床、壁、衣服、小道具の質感",
    "映画的だが場所に固有の光質",
    "場所の空気感が読める",
    "足元の床または地面の質感",
    "背景の壁、床、空、建築の質感",
    "参照画像とcutの時点に合う",
    "参照画像とcut時点に合う",
    "主要な出来事の証拠へ向く",
    "このcutの圧力や選択が読める表情",
    "scene内の現在の感情状態",
    "行為が始まる直前または途中だと読める手の位置",
    "次に動き出せる足元の重心",
    "主要な小道具、足元、手元などの近景証拠",
    "主要人物の姿勢、表情、視線",
    "場所が読める建築、床、壁、空気感",
    "動き出す方向に余白",
    "主役と物語上の証拠",
    "approved_story_evidence",
    "primary_visible_object",
    "primary_visible_zone",
    "TODO",
    "TBD",
    "placeholder",
)
_LOCALIZED_SHOT_VALUES = {
    "wide",
    "medium_wide",
    "medium",
    "medium_closeup",
    "closeup",
    "extreme_closeup",
}

INVARIANT_PROMPT_AUTHORING_PRINCIPLES = (
    "one_visible_moment: 一枚には一つの時間的瞬間だけを描く",
    "drawable_translation: 抽象概念を人物、物、姿勢、距離、光、素材へ変換する",
    "resolve_choices: または等の未確定選択をprovider promptへ残さない",
    "exclude_future_motion: motionや次cutの結果を静止画へ先取りしない",
    "bind_references: 参照画像を人物、物、場所の役割へ結び付ける",
    "show_cut_delta: 前cutとの差分を具体的な画面変化として示す",
    "exclude_production_meta: ID、設計key、制作目的をprovider promptへ流さない",
    "exclude_scene_overview: story/scene全体の出来事列をcutの一枚へ流さない",
)


@dataclass(frozen=True)
class PromptProjectionRule:
    source_keys: tuple[str, ...]
    relevance: str
    transform: str
    deterministic_checks: tuple[str, ...]
    semantic_checks: tuple[str, ...]
    group: str | None = None
    activation_dependency: str = ""
    value_prompt_template: str = ""
    exclusion_reason: str = ""

    def as_review_dict(self, *, expected_value: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_keys": list(self.source_keys),
            "relevance": self.relevance,
            "transform": self.transform,
            "deterministic_checks": list(self.deterministic_checks),
            "semantic_checks": list(self.semantic_checks),
        }
        if self.group:
            payload["target_group"] = self.group
        if self.activation_dependency:
            payload["activation_dependency"] = self.activation_dependency
        if expected_value:
            payload["expected_value"] = expected_value
        if self.exclusion_reason:
            payload["exclusion_reason"] = self.exclusion_reason
        return payload


@dataclass(frozen=True)
class ProjectionTraceIssue:
    code: str
    message: str


_DRAWABLE_RULES = (
    PromptProjectionRule(
        group="style",
        source_keys=("video_manifest.assets.style_guide",),
        relevance="required",
        transform="render_live_action_style_invariants",
        deterministic_checks=("required_group", "single_nonempty_fragment", "fragment_rendered"),
        semantic_checks=("実写、映画照明、実物セット感がcut固有情報を妨げていないか",),
    ),
    PromptProjectionRule(
        group="story_time",
        source_keys=("video_metadata.time",),
        relevance="conditional",
        activation_dependency="story_time",
        transform="historical_visual_consistency",
        deterministic_checks=(
            "exact_value_binding",
            "required_group",
            "single_nonempty_fragment",
            "fragment_rendered",
        ),
        semantic_checks=("衣装、髪型、建築、生活道具、素材、技術水準が同じ時代に整合するか",),
        value_prompt_template="物語の時代背景は{value}",
    ),
    PromptProjectionRule(
        group="time_of_day",
        source_keys=("scenes[].time_of_day",),
        relevance="conditional",
        activation_dependency="time_of_day",
        transform="daypart_lighting_consistency",
        deterministic_checks=(
            "exact_value_binding",
            "required_group",
            "single_nonempty_fragment",
            "fragment_rendered",
        ),
        semantic_checks=("空の明るさ、自然光、人工光、影、色温度がscene時間帯と矛盾しないか",),
        value_prompt_template="このシーンの時間帯は{value}",
    ),
    PromptProjectionRule(
        group="references",
        source_keys=("image_generation.references",),
        relevance="conditional",
        activation_dependency="references",
        transform="bind_reference_roles_only",
        deterministic_checks=("dependency_binding", "required_group", "single_nonempty_fragment", "fragment_rendered"),
        semantic_checks=("各参照が人物、物、場所のどの同一性を拘束するか明示されているか",),
    ),
    PromptProjectionRule(
        group="current_moment",
        source_keys=(
            "first_frame_visual_plan.temporal_boundary.event_fact_visible_in_still",
            "first_frame_visual_plan.temporal_boundary.first_visible_moment",
        ),
        relevance="required",
        transform="single_drawable_first_frame_moment",
        deterministic_checks=("required_group", "single_nonempty_fragment", "fragment_rendered"),
        semantic_checks=("一つの静止状態へ確定され、後続motionや完了結果を含まないか",),
    ),
    PromptProjectionRule(
        group="primary_subject",
        source_keys=("first_frame_visual_plan.subject_binding.primary_subject",),
        relevance="conditional",
        transform="resolve_primary_subject_hierarchy",
        deterministic_checks=("required_group", "single_nonempty_fragment", "fragment_rendered"),
        semantic_checks=("観客が最初に読む主被写体が一意で、構図と一致するか",),
    ),
    PromptProjectionRule(
        group="characters",
        source_keys=(
            "image_generation.character_ids",
            "image_generation.character_variant_ids",
            "assets.character_bible[].appearance_continuity",
            "assets.character_bible[].reference_variants[].appearance_continuity",
            "first_frame_visual_plan.character_state_gate",
        ),
        relevance="conditional",
        activation_dependency="character_ids",
        transform="translate_character_state_to_visible_behavior",
        deterministic_checks=(
            "dependency_binding",
            "required_group",
            "single_nonempty_fragment",
            "fragment_rendered",
            "per_character_appearance_value_binding",
        ),
        semantic_checks=("人物状態が人物別の衣装、表情、視線、姿勢、手足、距離として描画可能か",),
    ),
    PromptProjectionRule(
        group="objects",
        source_keys=("image_generation.object_ids", "first_frame_visual_plan.object_visibility_gate"),
        relevance="conditional",
        activation_dependency="object_ids",
        transform="translate_object_state_and_contact",
        deterministic_checks=("dependency_binding", "required_group", "single_nonempty_fragment", "fragment_rendered"),
        semantic_checks=("物の状態、接触、位置、物語上の証拠が一枚で読めるか",),
    ),
    PromptProjectionRule(
        group="location",
        source_keys=("image_generation.location_ids", "first_frame_visual_plan.spatial_composition"),
        relevance="conditional",
        activation_dependency="location_ids",
        transform="translate_location_to_screen_geography",
        deterministic_checks=("dependency_binding", "required_group", "single_nonempty_fragment", "fragment_rendered"),
        semantic_checks=("場所の前景、中景、背景と人物の導線が具体的か",),
    ),
    PromptProjectionRule(
        group="composition",
        source_keys=("first_frame_visual_plan.spatial_composition",),
        relevance="conditional",
        transform="translate_subject_priority_and_camera",
        deterministic_checks=("required_group", "single_nonempty_fragment", "fragment_rendered"),
        semantic_checks=("画角、主被写体の優先順位、前景中景背景が同じ狙いを支えるか",),
    ),
    PromptProjectionRule(
        group="light_material",
        source_keys=("first_frame_visual_plan.scene_material_pack",),
        relevance="conditional",
        transform="translate_cut_local_light_and_material",
        deterministic_checks=("required_group", "single_nonempty_fragment", "fragment_rendered"),
        semantic_checks=("光源と素材がstory_time、time_of_day、参照場所と矛盾しないか",),
    ),
    PromptProjectionRule(
        group="current_state_delta",
        source_keys=("first_frame_visual_plan.scene_state_progression",),
        relevance="conditional",
        transform="translate_previous_cut_delta",
        deterministic_checks=("required_group", "single_nonempty_fragment", "fragment_rendered"),
        semantic_checks=("前cutとの差が画角だけでなく具体的な人物、物、位置、状態の変化になっているか",),
    ),
    PromptProjectionRule(
        group="constraints",
        source_keys=(
            "first_frame_visual_plan.temporal_boundary.not_yet_happened_in_still",
            "image_prompt.global_constraints",
        ),
        relevance="required",
        transform="render_drawable_constraints_without_positive_conflict",
        deterministic_checks=("required_group", "single_nonempty_fragment", "fragment_rendered"),
        semantic_checks=("must-showとnot-yetが同じ人物、物、状態を同時に要求禁止していないか",),
    ),
)

_EXCLUDED_RULES = (
    PromptProjectionRule(
        source_keys=("story.script.scenes[].visualizable_action",),
        relevance="none",
        transform="review_scene_overview_but_project_cut_local_drawable_evidence",
        deterministic_checks=(
            "must_not_render_scene_overview",
            "reject_sequential_notation_in_positive_fragment",
        ),
        semantic_checks=(
            "story/scene全体の出来事列をreview contextに留め、担当cutの一瞬だけをfirst-frame planへ投影しているか",
        ),
        exclusion_reason="scene overview may span multiple beats; cut-local event evidence is canonical for one still",
    ),
    PromptProjectionRule(
        source_keys=(
            "cut_contract.source_event_contract.forbidden_reveal_info_ids",
            "cut_contract.viewer_contract.reveal_constraints.forbidden_until_later_scene",
        ),
        relevance="none",
        transform="resolve_known_drawable_asset_names_into_temporal_not_yet",
        deterministic_checks=(
            "raw_values_must_not_render",
            "resolved_name_does_not_activate_dependency",
        ),
        semantic_checks=(
            "既知の人物・物assetへ完全一致で解決できる値だけがnot-yet禁止文へ入り、抽象情報IDはreview metadataに留まるか",
        ),
        exclusion_reason="raw reveal IDs are review metadata; only resolved drawable names may enter the constraints group",
    ),
    PromptProjectionRule(
        source_keys=("cut_contract.motion_contract.motion_brief",),
        relevance="none",
        transform="exclude_video_motion_from_still_prompt",
        deterministic_checks=("must_not_render",),
        semantic_checks=("動画内の後続動作や完了状態がfirst-frame promptへ漏れていないか",),
        exclusion_reason="p800 video generation only",
    ),
    PromptProjectionRule(
        source_keys=("scenes[].time_of_day_visual_basis",),
        relevance="none",
        transform="review_derived_daypart_basis_without_duplicate_prompt_source",
        deterministic_checks=("must_not_create_second_authoring_root",),
        semantic_checks=(
            "scene.time_of_dayから導いた光源、明るさ、影、色温度の根拠が矛盾しないか",
        ),
        exclusion_reason="derived review evidence; scenes[].time_of_day remains canonical",
    ),
    PromptProjectionRule(
        source_keys=(
            "scenes[].location_mode",
            "scenes[].location_sequence",
            "scenes[].location_segments",
        ),
        relevance="none",
        transform="review_scene_location_sequence_but_project_one_cut_location",
        deterministic_checks=("one_cut_one_location_dependency",),
        semantic_checks=("sceneの場所順序を保ちつつ、静止画には担当cutの一場所だけを投影しているか",),
        exclusion_reason="scene routing metadata; cut location dependency is canonical for one still",
    ),
)


DRAWABLE_PROMPT_GROUP_ORDER = tuple(rule.group for rule in _DRAWABLE_RULES if rule.group)
PROMPT_PROJECTION_RULES = (*_DRAWABLE_RULES, *_EXCLUDED_RULES)


def registered_drawable_group_order() -> tuple[str, ...]:
    return DRAWABLE_PROMPT_GROUP_ORDER


def drawable_projection_rules() -> tuple[PromptProjectionRule, ...]:
    return _DRAWABLE_RULES


def excluded_projection_rules() -> tuple[PromptProjectionRule, ...]:
    return _EXCLUDED_RULES


def rule_for_group(group: str) -> PromptProjectionRule | None:
    return next((rule for rule in _DRAWABLE_RULES if rule.group == group), None)


def rule_for_source_key(source_key: str) -> PromptProjectionRule | None:
    return next((rule for rule in PROMPT_PROJECTION_RULES if source_key in rule.source_keys), None)


def render_projection_value_marker(group: str, value: str) -> str:
    rule = rule_for_group(group)
    normalized = str(value or "").strip()
    if rule is None or not rule.value_prompt_template or not normalized:
        return ""
    return rule.value_prompt_template.format(value=normalized)


def normalize_drawable_prompt_text(value: Any) -> str:
    """Normalize one scalar with the same drawable boundary used by projection review."""

    text = _WHITESPACE_RE.sub(" ", str(value or "")).strip(" 、。:：/\n\t")
    if not text:
        return ""
    if _INTERNAL_META_RE.search(text) or _ABSTRACT_STORY_RE.search(text):
        return ""
    if any(marker.lower() in text.lower() for marker in _GENERIC_TEXT_MARKERS):
        return ""
    text = text.replace("このcut", "この画像").replace("この cut", "この画像")
    text = text.replace("scene固有", "場面固有").replace("scene内", "場面内")
    if re.search(r"(?:前|次|後続)\s*(?:cut|scene)", text, re.IGNORECASE):
        return ""
    if _OPAQUE_IDENTIFIER_RE.fullmatch(text):
        return ""
    return text.strip(" 、。:：/\n\t")


def projection_registry_contract_issues() -> list[str]:
    issues: list[str] = []
    groups = [rule.group for rule in _DRAWABLE_RULES]
    if len(groups) != len(set(groups)):
        issues.append("duplicate_drawable_group")
    source_targets: list[tuple[str, str]] = []
    for rule in PROMPT_PROJECTION_RULES:
        if rule.relevance not in PROMPT_PROJECTION_RELEVANCE:
            issues.append(f"invalid_relevance:{rule.relevance}")
        if not rule.source_keys:
            issues.append(f"missing_source_keys:{rule.group or rule.transform}")
        if not rule.transform:
            issues.append(f"missing_transform:{rule.group or rule.source_keys[0]}")
        if not rule.deterministic_checks or not rule.semantic_checks:
            issues.append(f"missing_review_checks:{rule.group or rule.source_keys[0]}")
        if rule.relevance == "none" and (rule.group or not rule.exclusion_reason):
            issues.append(f"invalid_excluded_rule:{rule.source_keys[0]}")
        if rule.relevance != "none" and not rule.group:
            issues.append(f"missing_target_group:{rule.source_keys[0]}")
        source_targets.extend((source, rule.group or "none") for source in rule.source_keys)
    if len(source_targets) != len(set(source_targets)):
        issues.append("duplicate_source_target")
    return issues


def build_projection_review_contract(
    *,
    story_time: str = "",
    time_of_day: str = "",
    dependencies: Mapping[str, Any] | None = None,
    first_frame_visual_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    dependencies = dict(dependencies or {})
    plan = dict(first_frame_visual_plan or {})
    expected_values = {
        "story_time": str(story_time or "").strip(),
        "time_of_day": str(time_of_day or "").strip(),
    }
    active_rules: list[dict[str, Any]] = []
    inactive_rules: list[dict[str, Any]] = []
    for rule in _DRAWABLE_RULES:
        expected_value = expected_values.get(rule.group or "", "")
        active = _rule_is_active(
            rule,
            expected_value=expected_value,
            dependencies=dependencies,
            plan=plan,
        )
        target = active_rules if active else inactive_rules
        target.append(rule.as_review_dict(expected_value=expected_value))
    return {
        "registry_version": PROMPT_PROJECTION_REGISTRY_VERSION,
        "invariant_principles": list(INVARIANT_PROMPT_AUTHORING_PRINCIPLES),
        "active_rules": active_rules,
        "inactive_rules": inactive_rules,
        "excluded_rules": [rule.as_review_dict() for rule in _EXCLUDED_RULES],
        "expected_required_groups": [item["target_group"] for item in active_rules],
        "review_operations": ["include", "omit", "add", "replace"],
    }


def projection_trace_issues(
    *,
    prompt: str,
    dependencies: Mapping[str, Any],
    included_fragments: Any,
    expected_story_time: str | None = None,
    expected_time_of_day: str | None = None,
    first_frame_visual_plan: Mapping[str, Any] | None = None,
) -> list[ProjectionTraceIssue]:
    """Validate source -> dependency -> required group -> fragment -> prompt.

    Callers retain their own manifest/dependency type checks.  This helper owns
    the registry-specific completeness and exact-value trace so deterministic
    and semantic review cannot silently diverge when a design key is added.
    """

    normalized_dependencies = dict(dependencies or {})
    raw_required_groups = [
        str(value).strip()
        for value in _as_list(normalized_dependencies.get("required_groups"))
        if str(value).strip()
    ]
    required_groups = set(raw_required_groups)
    raw_fragments = included_fragments if isinstance(included_fragments, list) else []
    texts_by_group: dict[str, list[str]] = {}
    for fragment in raw_fragments:
        if not isinstance(fragment, Mapping):
            continue
        group = str(fragment.get("group") or "").strip()
        if not group:
            continue
        texts_by_group.setdefault(group, []).append(str(fragment.get("text") or "").strip())

    resolved_story_time = (
        str(expected_story_time).strip()
        if expected_story_time is not None
        else str(normalized_dependencies.get("story_time") or "").strip()
    )
    resolved_time_of_day = (
        str(expected_time_of_day).strip()
        if expected_time_of_day is not None
        else str(normalized_dependencies.get("time_of_day") or "").strip()
    )
    contract = build_projection_review_contract(
        story_time=resolved_story_time,
        time_of_day=resolved_time_of_day,
        dependencies=normalized_dependencies,
        first_frame_visual_plan=first_frame_visual_plan,
    )
    active_groups = {item["target_group"] for item in contract["active_rules"]}
    issues: list[ProjectionTraceIssue] = []

    if len(raw_required_groups) != len(set(raw_required_groups)):
        issues.append(
            ProjectionTraceIssue(
                code="api_prompt_v2_required_groups_duplicate",
                message="dependencies.required_groups must not contain duplicate groups.",
            )
        )
    known_required_groups = [
        group for group in raw_required_groups if group in DRAWABLE_PROMPT_GROUP_ORDER
    ]
    canonical_required_groups = sorted(
        dict.fromkeys(known_required_groups), key=_group_sort_key
    )
    if known_required_groups != canonical_required_groups:
        issues.append(
            ProjectionTraceIssue(
                code="api_prompt_v2_required_groups_order",
                message="dependencies.required_groups must follow the canonical registry order.",
            )
        )

    dependency_story_time = str(normalized_dependencies.get("story_time") or "").strip()
    dependency_time_of_day = str(normalized_dependencies.get("time_of_day") or "").strip()
    if expected_story_time is not None and dependency_story_time != resolved_story_time:
        issues.append(
            ProjectionTraceIssue(
                code="api_prompt_v2_story_time_dependency_mismatch",
                message="drawable prompt dependency `story_time` must exactly match video_metadata.time.",
            )
        )
    if expected_time_of_day is not None and dependency_time_of_day != resolved_time_of_day:
        issues.append(
            ProjectionTraceIssue(
                code="api_prompt_v2_time_of_day_dependency_mismatch",
                message="drawable prompt dependency `time_of_day` must exactly match scene.time_of_day.",
            )
        )

    declared_groups = required_groups | set(texts_by_group)
    for group in sorted(declared_groups - active_groups, key=_group_sort_key):
        if rule_for_group(group) is None or not _group_source_is_known(
            group,
            dependencies=normalized_dependencies,
            plan_is_known=first_frame_visual_plan is not None,
            expected_story_time_is_known=expected_story_time is not None,
            expected_time_of_day_is_known=expected_time_of_day is not None,
        ):
            continue
        issue_group = {"characters": "character", "objects": "object"}.get(group, group)
        issues.append(
            ProjectionTraceIssue(
                code=f"api_prompt_v2_unneeded_{issue_group}_fragment",
                message=f"registered prompt group `{group}` is declared without an active canonical source.",
            )
        )

    for group in sorted(active_groups | set(texts_by_group), key=_group_sort_key):
        rule = rule_for_group(group)
        if rule is None:
            continue
        texts = texts_by_group.get(group, [])
        if group not in active_groups:
            continue
        if group not in required_groups:
            issues.append(
                ProjectionTraceIssue(
                    code=f"api_prompt_v2_{group}_required_group_missing",
                    message=f"registered prompt group `{group}` must be present in raw dependencies.required_groups.",
                )
            )
        if len(texts) > 1:
            issues.append(
                ProjectionTraceIssue(
                    code=f"api_prompt_v2_duplicate_{group}_fragment",
                    message=f"registered prompt group `{group}` must have exactly one fragment.",
                )
            )
        if len(texts) != 1 or not texts[0]:
            continue
        text = texts[0]
        if text not in prompt:
            issues.append(
                ProjectionTraceIssue(
                    code=f"api_prompt_v2_fragment_not_rendered:{group}",
                    message=f"registered prompt group `{group}` is not rendered in the provider prompt.",
                )
            )

        expected_value = ""
        if group == "story_time":
            expected_value = resolved_story_time
        elif group == "time_of_day":
            expected_value = resolved_time_of_day
        if expected_value and rule.value_prompt_template:
            marker = render_projection_value_marker(group, expected_value)
            if marker not in text:
                issues.append(
                    ProjectionTraceIssue(
                        code=f"api_prompt_v2_{group}_fragment_value_mismatch",
                        message=f"registered prompt group `{group}` fragment does not render its exact source value.",
                    )
                )
            if text in prompt and marker not in prompt:
                issues.append(
                    ProjectionTraceIssue(
                        code=f"api_prompt_v2_{group}_prompt_value_mismatch",
                        message=f"provider prompt does not render the exact `{group}` source value.",
                    )
                )

    if first_frame_visual_plan is not None:
        character_fragment = "\n".join(texts_by_group.get("characters", []))
        for character_name, appearance_value in _character_appearance_values(
            first_frame_visual_plan
        ):
            for label, haystack in (
                ("fragment", character_fragment),
                ("prompt", prompt),
            ):
                if any(
                    character_name in line and appearance_value in line
                    for line in haystack.splitlines()
                ):
                    continue
                issues.append(
                    ProjectionTraceIssue(
                        code=(
                            "api_prompt_v2_character_appearance_"
                            f"{label}_value_missing"
                        ),
                        message=(
                            "each character_state_gate.character_states[] appearance "
                            f"value must be rendered with its character name in the {label}."
                        ),
                    )
                )
    return issues


def _character_appearance_values(
    first_frame_visual_plan: Mapping[str, Any],
) -> list[tuple[str, str]]:
    state = _path_value(first_frame_visual_plan, "character_state_gate")
    if not isinstance(state, Mapping):
        return []
    values: list[tuple[str, str]] = []
    for raw_binding in _as_sequence(state.get("character_states")):
        if not isinstance(raw_binding, Mapping):
            continue
        character_name = _drawable_scalar(raw_binding.get("character_name"))
        appearance = raw_binding.get("appearance_continuity")
        if not character_name or not isinstance(appearance, Mapping):
            continue
        costume_state = _drawable_scalar(appearance.get("costume_state"))
        if costume_state:
            values.append((character_name, costume_state))
        for raw_forbidden in _as_sequence(
            appearance.get("forbidden_costume_states")
        ):
            forbidden = _drawable_scalar(raw_forbidden)
            if forbidden:
                values.append((character_name, forbidden))
    return values


def _rule_is_active(
    rule: PromptProjectionRule,
    *,
    expected_value: str,
    dependencies: Mapping[str, Any],
    plan: Mapping[str, Any],
) -> bool:
    if rule.relevance == "required":
        return True
    if expected_value:
        return True
    if rule.activation_dependency:
        value = dependencies.get(rule.activation_dependency)
        if isinstance(value, (list, tuple, set)):
            return any(str(item or "").strip() for item in value)
        return bool(str(value or "").strip())
    if rule.group == "primary_subject":
        primary = _path_value(plan, "subject_binding.primary_subject")
        if not isinstance(primary, Mapping):
            return False
        value = _first_drawable_scalar(primary.get("name"), primary.get("label"))
        dependency_ids = {
            str(item or "").strip()
            for key in ("character_ids", "object_ids", "location_ids")
            for item in _as_list(dependencies.get(key))
            if str(item or "").strip()
        }
        return bool(value and value not in dependency_ids)
    if rule.group == "composition":
        composition = _path_value(plan, "spatial_composition")
        if not isinstance(composition, Mapping):
            return False
        priority = any(
            _drawable_scalar(item)
            for item in _as_sequence(composition.get("subject_priority_order"))
        )
        raw_shot = str(composition.get("shot_size") or "").strip().lower().replace("-", "_").replace(" ", "_")
        shot_is_drawable = raw_shot in _LOCALIZED_SHOT_VALUES or bool(
            _drawable_scalar(composition.get("shot_size"))
        )
        return bool(
            priority
            or shot_is_drawable
            or _drawable_scalar(
                composition.get("camera_angle") or composition.get("camera_height")
            )
        )
    if rule.group == "light_material":
        material = _path_value(plan, "scene_material_pack")
        if not isinstance(material, Mapping):
            return False
        return bool(
            _drawable_scalar(material.get("light_source"))
            or _drawable_scalar(material.get("light_direction"))
            or any(
                _drawable_scalar(item)
                for item in _as_sequence(material.get("dominant_materials"))
            )
            or _drawable_scalar(material.get("story_specific_texture"))
        )
    if rule.group == "current_state_delta":
        progression = _path_value(plan, "scene_state_progression")
        if not isinstance(progression, Mapping):
            return False
        if str(progression.get("progression_mode") or "").strip() != "sequential_state_progression":
            return False
        return bool(
            _drawable_scalar(
                progression.get("state_visible_in_first_frame")
                or progression.get("state_visible_in_this_cut")
            )
            or _drawable_scalar(progression.get("visible_state_delta_from_previous_cut"))
        )
    return False


def _group_source_is_known(
    group: str,
    *,
    dependencies: Mapping[str, Any],
    plan_is_known: bool,
    expected_story_time_is_known: bool,
    expected_time_of_day_is_known: bool,
) -> bool:
    if group in {"style", "current_moment", "constraints"}:
        return True
    if group == "story_time":
        return expected_story_time_is_known or "story_time" in dependencies
    if group == "time_of_day":
        return expected_time_of_day_is_known or "time_of_day" in dependencies
    if group in {"references", "characters", "objects", "location"}:
        return True
    return plan_is_known


def _first_drawable_scalar(*values: Any) -> str:
    for value in values:
        normalized = _drawable_scalar(value)
        if normalized:
            return normalized
    return ""


def _drawable_scalar(value: Any) -> str:
    return normalize_drawable_prompt_text(value)


def _as_sequence(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    if value is None:
        return []
    return [value]


def _path_value(value: Mapping[str, Any], path: str) -> Any:
    current: Any = value
    for key in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _has_content(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_content(item) for item in value)
    return bool(str(value or "").strip())


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _group_sort_key(group: str) -> tuple[int, str]:
    try:
        return DRAWABLE_PROMPT_GROUP_ORDER.index(group), group
    except ValueError:
        return len(DRAWABLE_PROMPT_GROUP_ORDER), group
