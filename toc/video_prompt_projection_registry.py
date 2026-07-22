"""Canonical design-key projection for provider-facing video prompts.

The manifest keeps story, scene, cut, and provider concerns in one document.
This registry is the boundary between those design keys and the much smaller
set of motion instructions that a video provider should receive.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


VIDEO_PROMPT_PROJECTION_REGISTRY_VERSION = "video_prompt_projection_registry_v5"
VIDEO_PROMPT_GROUP_ORDER = (
    "start_state",
    "primary_motion",
    "camera_motion",
    "environment_motion",
    "emotional_change",
    "end_state",
    "continuity",
    "constraints",
)

_AUTHORING_RELEVANCE = {"required", "conditional", "none"}
_PROVIDER_PROJECTION = {"derive", "may_surface", "must_not_surface"}
_REVIEW_VISIBILITY = {"projection", "review_only", "none"}


@dataclass(frozen=True)
class VideoPromptProjectionRule:
    source_keys: tuple[str, ...]
    authoring_relevance: str
    provider_projection: str
    review_visibility: str
    transform: str
    semantic_checks: tuple[str, ...]
    target_group: str | None = None
    activation_dependency: str = ""
    exclusion_reason: str = ""

    def as_dict(self, *, source_key: str | None = None, value: Any | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_keys": list(self.source_keys),
            "authoring_relevance": self.authoring_relevance,
            "provider_projection": self.provider_projection,
            "review_visibility": self.review_visibility,
            "transform": self.transform,
            "semantic_checks": list(self.semantic_checks),
        }
        if source_key:
            payload["source_key"] = source_key
        if self.target_group:
            payload["target_group"] = self.target_group
        if self.activation_dependency:
            payload["activation_dependency"] = self.activation_dependency
        if value is not None:
            payload["value"] = value
        if self.exclusion_reason:
            payload["exclusion_reason"] = self.exclusion_reason
        return payload


_RULES = (
    VideoPromptProjectionRule(
        ("video_generation.tool",),
        "required",
        "derive",
        "projection",
        "select_provider_specific_motion_policy",
        ("provider固有の尺、camera、continuity制約に整合するか",),
        "constraints",
    ),
    VideoPromptProjectionRule(
        ("manifest.video_metadata.time",),
        "conditional",
        "derive",
        "projection",
        "preserve_historical_world_continuity",
        ("衣装、髪型、建築、生活道具、素材、技術水準を別時代へ変えていないか",),
        "continuity",
    ),
    VideoPromptProjectionRule(
        ("scene.time_of_day",),
        "conditional",
        "derive",
        "projection",
        "preserve_daypart_light_continuity",
        ("空の明るさ、光源、影、色温度を別時間帯へ変えていないか",),
        "continuity",
    ),
    VideoPromptProjectionRule(
        ("scene.time_of_day_visual_basis",),
        "conditional",
        "must_not_surface",
        "review_only",
        "review_daypart_lighting_basis_without_duplicating_provider_prose",
        ("光源、明るさ、影、色温度がscene.time_of_dayを具体化しているか",),
        exclusion_reason="derived scene review evidence",
    ),
    VideoPromptProjectionRule(
        (
            "scene.location_mode",
            "scene.location_sequence",
            "scene.location_segments",
        ),
        "conditional",
        "must_not_surface",
        "review_only",
        "review_scene_route_while_motion_uses_only_the_assigned_cut_location",
        ("複数場所sceneでも1 clipが一つの場所移動または一つの場所内動作に限定されているか",),
        exclusion_reason="scene routing metadata; cut location is the provider-facing anchor",
    ),
    VideoPromptProjectionRule(
        (
            "scene.visualizable_action",
            "scene.review_only_visualizable_action",
        ),
        "none",
        "must_not_surface",
        "review_only",
        "review_scene_overview_but_project_only_cut_local_motion_state",
        (
            "scene全体の出来事列がcutの開始状態、主動作、終了状態へ複製されていないか",
        ),
        exclusion_reason="story/scene overview; cut-local event state owns provider motion prose",
    ),
    VideoPromptProjectionRule(
        ("first_frame_visual_plan",),
        "conditional",
        "must_not_surface",
        "review_only",
        "retain_exact_first_frame_visual_plan_for_review",
        (
            "provider開始状態が承認済みfirst_frame_visual_planの時間境界と一致するか",
        ),
        exclusion_reason="derived visual-plan metadata; selected temporal leaves are projected separately",
    ),
    VideoPromptProjectionRule(
        (
            "first_frame_visual_plan.temporal_boundary.event_fact_visible_in_still",
            "first_frame_visual_plan.temporal_boundary.first_visible_moment",
            "cut.cut_contract.motion_contract.start_from_visible_state",
            "cut.cut_contract.first_frame_contract.visible_start_state.character_state",
            "cut.cut_contract.first_frame_contract.visible_start_state.prop_state",
            "cut.cut_contract.first_frame_contract.visible_start_state.spatial_state",
            "cut.cut_contract.first_frame_contract.visible_start_state.emotional_state",
            "cut.cut_contract.first_frame_contract.visible_start_state.gaze_or_attention",
            "cut.cut_contract.first_frame_contract.first_frame_brief",
            "compiler_normalized.authoring_source.start_state",
        ),
        "required",
        "derive",
        "projection",
        "bind_motion_to_approved_visible_start_state",
        ("承認済み開始画像の人物、構図、光、物の状態から自然に始まるか",),
        "start_state",
    ),
    VideoPromptProjectionRule(
        (
            "video_generation.first_frame",
            "video_generation.input_image",
            "video_generation.last_frame",
        ),
        "conditional",
        "must_not_surface",
        "review_only",
        "bind_frame_paths_without_rendering_paths",
        ("開始・終了frame pathがprovider_request_bindingと一致するか",),
        exclusion_reason="provider binding paths; boundary instructions are rendered without paths",
    ),
    VideoPromptProjectionRule(
        (
            "cut.cut_contract.motion_contract.motion_brief",
            "cut.cut_contract.motion_contract.subject_motion",
            "cut_contract.motion_contract.motion_brief",
            "scene_contract.motion_brief",
            "video_generation.motion_contract.motion_intent",
            "video_generation.motion_contract.intent",
            "video_generation.motion_contract.motion_brief",
            "video_generation.motion_contract.action_intent",
            "compiler_normalized.authoring_source.primary_motion",
            "video_generation.prompt_authoring_source",
            "video_generation.source_motion_prompt",
            "video_generation.motion_prompt",
        ),
        "required",
        "derive",
        "projection",
        "resolve_one_primary_visible_action",
        ("1 clip 1 intentとなり、複数の大きな出来事を詰め込んでいないか",),
        "primary_motion",
    ),
    VideoPromptProjectionRule(
        (
            "cut.cut_contract.motion_contract.camera_motion",
            "cut_contract.motion_contract.camera_motion",
            "video_generation.motion_contract.camera_motion",
            "compiler_normalized.authoring_source.camera_motion",
        ),
        "conditional",
        "derive",
        "projection",
        "limit_camera_to_one_or_two_compatible_moves",
        ("camera指示が1〜2個以内で主動作と競合しないか",),
        "camera_motion",
    ),
    VideoPromptProjectionRule(
        (
            "cut.cut_contract.motion_contract.environment_motion",
            "cut_contract.motion_contract.environment_motion",
            "video_generation.motion_contract.environment_motion",
            "compiler_normalized.authoring_source.environment_motion",
        ),
        "conditional",
        "may_surface",
        "projection",
        "add_only_small_environment_motion_present_in_start_frame",
        ("開始画像にない環境要素を追加せず、主動作を妨げないか",),
        "environment_motion",
    ),
    VideoPromptProjectionRule(
        (
            "cut.cut_contract.motion_contract.emotional_change",
            "cut_contract.motion_contract.emotional_change",
            "cut.cut_contract.viewer_contract.emotional_micro_shift",
            "video_generation.motion_contract.emotional_change",
            "compiler_normalized.authoring_source.emotional_change",
        ),
        "conditional",
        "derive",
        "projection",
        "translate_emotion_to_visible_expression_posture_and_timing",
        ("感情変化が表情、姿勢、視線、速度として見えるか",),
        "emotional_change",
    ),
    VideoPromptProjectionRule(
        (
            "cut.cut_contract.motion_contract.end_state",
            "cut.cut_contract.motion_contract.end_frame_brief",
            "cut_contract.motion_contract.end_state",
            "scene_contract.motion_end_state",
            "cut.cut_contract.continuity_contract.end_state",
            "video_generation.motion_contract.handoff_state",
            "video_generation.motion_contract.end_state",
            "compiler_normalized.authoring_source.end_state",
        ),
        "required",
        "derive",
        "projection",
        "resolve_visible_end_or_handoff_state",
        ("宣言した終了状態に到達し、次の出来事を先取りしていないか",),
        "end_state",
    ),
    VideoPromptProjectionRule(
        (
            "video_generation.motion_contract.must_preserve",
            "video_generation.continuity_notes",
            "video_generation.direction_notes",
            "compiler_normalized.authoring_source.continuity",
        ),
        "conditional",
        "derive",
        "projection",
        "preserve_face_outfit_props_geography_direction_and_light",
        ("人物、衣装、重要物、進行方向、camera高、光源がclip内でdriftしないか",),
        "continuity",
    ),
    VideoPromptProjectionRule(
        (
            "cut.cut_contract.continuity_contract.carry_forward_to_next_cut",
            "cut_contract.continuity_contract.carry_forward_to_next_cut",
            "cut.cut_contract.cut_handoff.receives_from_previous.visible_or_audible_form",
            "cut.cut_contract.cut_handoff.delivers_to_next.visible_or_audible_form",
        ),
        "conditional",
        "must_not_surface",
        "review_only",
        "review_downstream_handoff_without_constraining_current_clip",
        (
            "current clipの終了状態と下流handoffを区別し、到達後の状態をclip全体へ逆投影していないか",
        ),
        exclusion_reason="downstream handoff evidence; current clip continuity uses stable preserve inputs only",
    ),
    VideoPromptProjectionRule(
        (
            "cut.cut_contract.location",
            "cut.cut_contract.continuity_contract.location_ids",
            "cut.cut_contract.asset_dependency.location_ids_required",
            "cut.cut_contract.source_event_contract.source_concrete_events",
        ),
        "required",
        "must_not_surface",
        "review_only",
        "review_cut_local_location_provenance",
        (
            "cutの開始場所がscene route内の担当場所と一致し、sibling場所を混ぜていないか",
        ),
        exclusion_reason="cut-local location provenance; visible spatial state is projected separately",
    ),
    VideoPromptProjectionRule(
        (
            "cut.cut_contract.first_frame_character_asset_overrides",
            "cut.cut_contract.first_frame_excluded_object_ids",
            "cut.cut_blueprint.first_frame_character_asset_overrides",
            "cut.cut_blueprint.first_frame_excluded_object_ids",
            "cut.cut_blueprint.first_frame_asset_policy.character_asset_overrides",
            "cut.cut_blueprint.first_frame_asset_policy.excluded_object_ids",
        ),
        "conditional",
        "must_not_surface",
        "review_only",
        "review_first_frame_asset_boundary_policy",
        (
            "開始人物assetと除外objectが終了側revealを開始画像へ先取りさせていないか",
        ),
        exclusion_reason="first-frame asset dependency policy; provider motion prose uses the approved frame",
    ),
    VideoPromptProjectionRule(
        ("video_generation.reference_roles",),
        "conditional",
        "derive",
        "projection",
        "render_ordered_reference_roles_without_paths",
        ("各参照画像の役割が画像順と一対一に対応しているか",),
        "continuity",
    ),
    VideoPromptProjectionRule(
        ("video_generation.references",),
        "conditional",
        "must_not_surface",
        "review_only",
        "bind_reference_paths_without_rendering_paths",
        ("参照画像pathの順序がreference_rolesと一致しているか",),
        exclusion_reason="provider binding paths; roles are rendered instead",
    ),
    VideoPromptProjectionRule(
        (
            "cut.cut_contract.motion_contract.allowed_new_reveal_elements",
            "cut_contract.motion_contract.allowed_new_reveal_elements",
            "video_generation.motion_contract.allowed_new_reveal_elements",
        ),
        "conditional",
        "derive",
        "projection",
        "render_explicit_primary_motion_reveal_allowlist",
        (
            "主動作が因果的に生成する要素だけが許可され、開始画像との矛盾を作っていないか",
        ),
        "constraints",
    ),
    VideoPromptProjectionRule(
        (
            "cut.cut_contract.source_event_contract.allowed_reveal_info_ids",
            "cut_contract.source_event_contract.allowed_reveal_info_ids",
        ),
        "conditional",
        "must_not_surface",
        "review_only",
        "review_allowed_reveal_information_boundary",
        ("許可IDがcanonical reveal inventoryと当該cutのevent境界に一致するか",),
        exclusion_reason="opaque reveal identifiers",
    ),
    VideoPromptProjectionRule(
        (
            "cut.cut_contract.use_next_cut_first_frame_as_last_frame",
            "cut_contract.use_next_cut_first_frame_as_last_frame",
            "cut.cut_contract.cut_handoff.delivers_to_next.binds_video_last_frame_to_next_first_frame",
        ),
        "conditional",
        "must_not_surface",
        "review_only",
        "review_resolved_next_first_frame_boundary_binding",
        (
            "next first-frame境界が同一または明示許可された場所とrevealに一致するか",
        ),
        exclusion_reason="boundary-resolution metadata; only the resolved last-frame binding reaches the provider",
    ),
    VideoPromptProjectionRule(
        (
            "cut.cut_contract.motion_contract.must_not_add",
            "cut_contract.motion_contract.must_not_add",
            "scene_contract.must_avoid",
            "video_generation.motion_contract.must_not_add",
            "video_generation.motion_contract.must_avoid",
            "video_generation.motion_contract.forbidden_additions",
            "compiler_normalized.authoring_source.constraints",
        ),
        "required",
        "derive",
        "projection",
        "render_minimal_high_risk_negative_constraints",
        ("新しい人物、重要物、reveal、別shot化を防げているか",),
        "constraints",
    ),
    VideoPromptProjectionRule(
        (
            "cut.cut_contract.cut_function",
            "cut.cut_contract.viewer_contract.target_beat",
            "cut.cut_contract.viewer_contract.screen_question",
            "cut.cut_contract.viewer_contract.dramatic_job",
        ),
        "required",
        "must_not_surface",
        "review_only",
        "use_story_job_to_review_motion_without_rendering_design_labels",
        ("動きがcutの物語上の責務を満たすか",),
        exclusion_reason="production design metadata",
    ),
    VideoPromptProjectionRule(
        (
            "cut.cut_contract.source_event_contract.primary_event_beat_id",
            "cut.cut_contract.source_event_contract.source_event_beat_ids",
            "cut.cut_contract.motion_contract.source_event_beat_id",
            "cut_contract.motion_contract.source_event_beat_id",
            "cut.cut_contract.motion_contract.must_not_advance_to_event_beat_ids",
            "cut.cut_contract.source_event_contract.forbidden_reveal_info_ids",
        ),
        "required",
        "must_not_surface",
        "review_only",
        "enforce_event_and_reveal_boundary_without_rendering_internal_ids",
        ("担当eventとreveal境界を越えていないか",),
        exclusion_reason="opaque event and reveal identifiers",
    ),
    VideoPromptProjectionRule(
        (
            "cut.image_generation.prompt",
            "cut.image_generation.api_prompt_payload",
            "cut.audio.narration.text",
            "cut.audio.narration.tts_text",
        ),
        "none",
        "must_not_surface",
        "review_only",
        "keep_image_and_narration_prose_out_of_motion_prompt",
        ("画像promptやnarrationをmotion指示として複製していないか",),
        exclusion_reason="review context only",
    ),
)

_REQUIRED_REGISTRY_SOURCE_KEYS = (
    "scene.visualizable_action",
    "first_frame_visual_plan",
    "first_frame_visual_plan.temporal_boundary.event_fact_visible_in_still",
    "first_frame_visual_plan.temporal_boundary.first_visible_moment",
    "cut.cut_contract.first_frame_contract.visible_start_state.spatial_state",
    "video_generation.motion_contract.motion_brief",
    "video_generation.motion_contract.action_intent",
    "cut.cut_contract.location",
    "cut.cut_contract.continuity_contract.carry_forward_to_next_cut",
    "cut.cut_contract.continuity_contract.location_ids",
    "cut.cut_contract.asset_dependency.location_ids_required",
    "cut.cut_contract.source_event_contract.source_concrete_events",
    "cut.cut_contract.source_event_contract.allowed_reveal_info_ids",
    "cut.cut_contract.use_next_cut_first_frame_as_last_frame",
    "cut.cut_contract.cut_handoff.delivers_to_next.binds_video_last_frame_to_next_first_frame",
    "cut.cut_contract.cut_handoff.receives_from_previous.visible_or_audible_form",
    "cut.cut_contract.cut_handoff.delivers_to_next.visible_or_audible_form",
    "cut.cut_contract.first_frame_character_asset_overrides",
    "cut.cut_contract.first_frame_excluded_object_ids",
    "cut.cut_blueprint.first_frame_character_asset_overrides",
    "cut.cut_blueprint.first_frame_excluded_object_ids",
    "cut.cut_blueprint.first_frame_asset_policy.character_asset_overrides",
    "cut.cut_blueprint.first_frame_asset_policy.excluded_object_ids",
)


def projection_rules() -> tuple[VideoPromptProjectionRule, ...]:
    return _RULES


def video_projection_registry_catalog() -> list[dict[str, Any]]:
    return [rule.as_dict() for rule in _RULES]


def rule_for_source_key(source_key: str) -> VideoPromptProjectionRule | None:
    return next((rule for rule in _RULES if source_key in rule.source_keys), None)


def video_projection_registry_issues() -> list[str]:
    issues: list[str] = []
    if len(VIDEO_PROMPT_GROUP_ORDER) != len(set(VIDEO_PROMPT_GROUP_ORDER)):
        issues.append("duplicate_group_order")
    seen_keys: set[str] = set()
    for rule in _RULES:
        if not rule.source_keys:
            issues.append("rule_without_source_key")
        if rule.authoring_relevance not in _AUTHORING_RELEVANCE:
            issues.append(f"invalid_authoring_relevance:{rule.authoring_relevance}")
        if rule.provider_projection not in _PROVIDER_PROJECTION:
            issues.append(f"invalid_provider_projection:{rule.provider_projection}")
        if rule.review_visibility not in _REVIEW_VISIBILITY:
            issues.append(f"invalid_review_visibility:{rule.review_visibility}")
        if rule.target_group and rule.target_group not in VIDEO_PROMPT_GROUP_ORDER:
            issues.append(f"unknown_target_group:{rule.target_group}")
        if rule.provider_projection in {"derive", "may_surface"} and not rule.target_group:
            # Provider selection is metadata and intentionally has no prose group.
            if rule.source_keys != ("video_generation.tool",):
                issues.append(f"provider_rule_without_group:{rule.source_keys[0]}")
        for source_key in rule.source_keys:
            if source_key in seen_keys:
                issues.append(f"duplicate_source_key:{source_key}")
            seen_keys.add(source_key)
    for source_key in _REQUIRED_REGISTRY_SOURCE_KEYS:
        if source_key not in seen_keys:
            issues.append(f"missing_required_source_key:{source_key}")
    return issues


def build_video_prompt_projection(
    *,
    manifest: Mapping[str, Any] | None = None,
    scene: Mapping[str, Any] | None = None,
    cut: Mapping[str, Any] | None = None,
    video_generation: Mapping[str, Any] | None = None,
    cut_contract: Mapping[str, Any] | None = None,
    scene_contract: Mapping[str, Any] | None = None,
    source_prompt: str = "",
    story_time: str = "",
    time_of_day: str = "",
    tool: str = "",
    first_frame: str = "",
    last_frame: str = "",
    duration_seconds: int | float | None = None,
    direction_notes: Sequence[Any] = (),
    continuity_notes: Sequence[Any] = (),
    first_frame_visual_plan: Mapping[str, Any] | None = None,
    normalized_authoring_groups: Mapping[str, Any] | None = None,
    compact: bool = False,
) -> dict[str, Any]:
    """Project one video target into authoring/review groups.

    Direct keyword values are adapters for CLI and frontend call sites.  They
    are normalized into the same scoped structure used by manifest readers.
    """

    manifest_data = dict(manifest or {})
    metadata = dict(_mapping(manifest_data.get("video_metadata")))
    if story_time:
        metadata["time"] = story_time
    manifest_data["video_metadata"] = metadata

    scene_data = dict(scene or {})
    if time_of_day:
        scene_data["time_of_day"] = time_of_day

    cut_data = dict(cut or {})
    canonical_contract = resolve_video_prompt_contract(
        cut_data,
        cut_contract=cut_contract,
        scene_contract=scene_contract,
    )
    cut_data["cut_contract"] = canonical_contract

    video_data = dict(video_generation or {})
    if source_prompt.strip():
        video_data["prompt_authoring_source"] = source_prompt.strip()
    if tool:
        video_data["tool"] = tool
    if first_frame:
        video_data["first_frame"] = first_frame
    if last_frame:
        video_data["last_frame"] = last_frame
    clean_direction_notes = [value for value in direction_notes if _is_present(value)]
    clean_continuity_notes = [value for value in continuity_notes if _is_present(value)]
    if clean_direction_notes:
        video_data["direction_notes"] = clean_direction_notes
    if clean_continuity_notes:
        video_data["continuity_notes"] = clean_continuity_notes
    if duration_seconds is not None:
        video_data["duration_seconds"] = duration_seconds

    normalization_applied = normalized_authoring_groups is not None
    normalized_groups = {
        group: value
        for group in VIDEO_PROMPT_GROUP_ORDER
        if _is_present(value := _mapping(normalized_authoring_groups).get(group))
    }
    if normalization_applied:
        # Once the compiler has parsed free-form prose, trace only the parsed
        # group values.  Keeping the same raw block active as primary_motion
        # would claim that camera-labelled lines belong to two groups.
        for raw_source_key in (
            "prompt_authoring_source",
            "source_motion_prompt",
            "motion_prompt",
        ):
            video_data.pop(raw_source_key, None)

    scopes: dict[str, Mapping[str, Any]] = {
        "manifest": manifest_data,
        "scene": scene_data,
        "cut": cut_data,
        "video_generation": video_data,
        "compiler_normalized": {"authoring_source": normalized_groups},
        "first_frame_visual_plan": dict(first_frame_visual_plan or {}),
    }
    groups: dict[str, list[dict[str, Any]]] = {group: [] for group in VIDEO_PROMPT_GROUP_ORDER}
    active_rules: list[dict[str, Any]] = []
    inactive_rules: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    review_only_sources: list[dict[str, Any]] = []
    shadowed_sources: list[dict[str, Any]] = []
    canonical_motion = _mapping(canonical_contract.get("motion_contract"))
    authoritative_empty_source_keys = set()
    if (
        "allowed_new_reveal_elements" in canonical_motion
        and not _is_present(canonical_motion.get("allowed_new_reveal_elements"))
    ):
        authoritative_empty_source_keys.add(
            "cut.cut_contract.motion_contract.allowed_new_reveal_elements"
        )

    for rule in _RULES:
        present_sources = [
            (source_key, value)
            for source_key in rule.source_keys
            if _is_present(value := _resolve(source_key, scopes))
        ]
        if rule.provider_projection == "must_not_surface":
            excluded.append(rule.as_dict())
            if rule.review_visibility == "review_only":
                for source_key, value in present_sources:
                    item = rule.as_dict(source_key=source_key, value=value)
                    if compact:
                        item = {
                            key: item[key]
                            for key in (
                                "source_key",
                                "authoring_relevance",
                                "provider_projection",
                                "review_visibility",
                                "value",
                            )
                            if key in item
                        }
                    review_only_sources.append(item)
            continue
        explicit_empty_source = next(
            (
                source_key
                for source_key in rule.source_keys
                if source_key in authoritative_empty_source_keys
            ),
            "",
        )
        if explicit_empty_source:
            selected_sources, shadowed = [], present_sources
            shadow_reason = "higher_priority_design_source_explicitly_empty"
        else:
            selected_sources, shadowed = _select_rule_sources(rule, present_sources)
            shadow_reason = "higher_priority_design_source_present"
        shadowed_sources.extend(
            {
                "source_key": source_key,
                "target_group": rule.target_group,
                "reason": shadow_reason,
            }
            for source_key, _value in shadowed
        )
        matched = False
        for source_key, value in selected_sources:
            matched = True
            item = rule.as_dict(source_key=source_key, value=value)
            if compact:
                item = {
                    key: item[key]
                    for key in (
                        "source_key",
                        "authoring_relevance",
                        "provider_projection",
                        "review_visibility",
                        "target_group",
                        "value",
                    )
                    if key in item
                }
            active_rules.append(item)
            if rule.target_group:
                _append_group_value(groups[rule.target_group], source_key=source_key, value=value)
        if not matched:
            inactive_rules.append(rule.as_dict())

    provider = str(video_data.get("tool") or "").strip()
    if "kling" in provider.lower():
        policy_rule = {
            "source_keys": ["provider_policy.kling.one_clip_one_intent"],
            "source_key": "provider_policy.kling.one_clip_one_intent",
            "authoring_relevance": "required",
            "provider_projection": "derive",
            "review_visibility": "projection",
            "transform": "enforce_kling_single_intent_continuous_shot",
            "semantic_checks": ["主動作が一つで、camera指示が最大2つか"],
            "target_group": "constraints",
            "value": ["主動作は一つ", "単一の連続ショット"],
        }
        active_rules.append(policy_rule)
        _append_group_value(
            groups["constraints"],
            source_key="provider_policy.kling.one_clip_one_intent",
            value=policy_rule["value"],
        )
    first = str(video_data.get("first_frame") or video_data.get("input_image") or "").strip()
    last = str(video_data.get("last_frame") or "").strip()
    has_references = _is_present(video_data.get("references"))
    mode = (
        "first_last_frame"
        if first and last
        else "image_to_video"
        if first
        else "reference_to_video"
        if has_references
        else "text_to_video"
    )
    return {
        "registry_version": VIDEO_PROMPT_PROJECTION_REGISTRY_VERSION,
        "group_order": list(VIDEO_PROMPT_GROUP_ORDER),
        "groups": groups,
        "active_rules": active_rules,
        "inactive_rules": inactive_rules,
        "excluded": excluded,
        "review_only_sources": review_only_sources,
        "shadowed_sources": shadowed_sources,
        "provider": provider,
        "mode": mode,
        "authoring_source_normalization": {
            "applied": normalization_applied,
            "groups": normalized_groups,
        },
    }


def _select_rule_sources(
    rule: VideoPromptProjectionRule,
    present_sources: list[tuple[str, Any]],
) -> tuple[list[tuple[str, Any]], list[tuple[str, Any]]]:
    """Resolve precedence without dropping independent continuity inputs."""

    if not present_sources or not rule.target_group:
        return present_sources, []

    canonical = [item for item in present_sources if item[0].startswith("cut.cut_contract.")]
    visual_plan = [
        item
        for item in present_sources
        if item[0].startswith("first_frame_visual_plan.")
    ]
    flat = [item for item in present_sources if item[0].startswith("video_generation.motion_contract.")]
    free_text = [
        item
        for item in present_sources
        if item[0]
        in {
            "video_generation.prompt_authoring_source",
            "video_generation.source_motion_prompt",
            "video_generation.motion_prompt",
        }
    ]
    normalized = [
        item
        for item in present_sources
        if item[0].startswith("compiler_normalized.authoring_source.")
    ]

    if rule.target_group == "primary_motion":
        selected = canonical or flat or normalized or free_text
    elif rule.target_group in {"camera_motion", "environment_motion", "emotional_change", "constraints"}:
        selected = canonical or flat or normalized or present_sources
    elif rule.target_group == "end_state":
        boundary = [item for item in present_sources if item[0] == "video_generation.last_frame"]
        authored = canonical or flat or normalized
        selected = [*authored, *[item for item in boundary if item not in authored]]
    elif rule.target_group == "start_state":
        selected = visual_plan or canonical or normalized or present_sources
    elif rule.target_group == "continuity":
        supplementary = [
            item
            for item in present_sources
            if item[0]
            in {
                "video_generation.continuity_notes",
                "video_generation.direction_notes",
                "video_generation.reference_roles",
            }
        ]
        authored = canonical or flat or normalized
        selected = (
            [*authored, *[item for item in supplementary if item not in authored]]
            if authored or supplementary
            else present_sources
        )
    else:
        selected = present_sources

    shadowed = [item for item in present_sources if item not in selected]
    return selected, shadowed


def resolve_video_prompt_contract(
    cut: Mapping[str, Any],
    *,
    cut_contract: Mapping[str, Any] | None,
    scene_contract: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Resolve canonical and compatibility contracts per field.

    Higher-priority contracts override conflicts, while a partial canonical
    object does not erase unrelated fields from a lower compatibility source.
    Empty placeholder values normally do not suppress populated lower-priority
    values. An explicit empty reveal allowlist is authoritative and fail-closed.
    """

    resolved: dict[str, Any] = {}
    low_to_high = (
        cut.get("cut_blueprint"),
        cut.get("scene_contract"),
        scene_contract,
        cut.get("cut_contract"),
        cut_contract,
    )
    for candidate in low_to_high:
        if not isinstance(candidate, Mapping) or not candidate:
            continue
        normalized = _normalize_contract_candidate(candidate)
        resolved = _overlay_present_values(resolved, normalized)
    return resolved


def _normalize_contract_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(candidate)
    motion = dict(_mapping(normalized.get("motion_contract")))
    for source_key, target_key in (
        ("motion_brief", "motion_brief"),
        ("motion_end_state", "end_state"),
        ("must_avoid", "must_not_add"),
    ):
        if target_key not in motion and _is_present(normalized.get(source_key)):
            motion[target_key] = normalized.get(source_key)
    if motion:
        normalized["motion_contract"] = motion
    return normalized


def _overlay_present_values(
    base: Mapping[str, Any],
    override: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key == "allowed_new_reveal_elements":
            merged[key] = value
            continue
        if not _is_present(value):
            continue
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _overlay_present_values(current, value)
        else:
            merged[key] = value
    return merged


def _resolve(source_key: str, scopes: Mapping[str, Mapping[str, Any]]) -> Any:
    scope_name, _, path = source_key.partition(".")
    current: Any = scopes.get(scope_name, {})
    for part in path.split(".") if path else ():
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _append_group_value(items: list[dict[str, Any]], *, source_key: str, value: Any) -> None:
    if any(existing.get("value") == value for existing in items):
        return
    items.append({"source_key": source_key, "value": value})
