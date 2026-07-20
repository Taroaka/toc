"""Canonical design-key projection for narration authoring prompts.

Narration must not receive every upstream value as prose to be spoken.  This
registry classifies design keys by the job they perform during authoring:
background, required content, optional candidates, additions beyond the image,
reveal constraints, visible facts that should not be captioned, delivery, or
explicit exclusion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


NARRATION_PROMPT_PROJECTION_REGISTRY_VERSION = "narration_prompt_projection_registry_v1"
NARRATION_PROMPT_USAGES = {
    "background",
    "required",
    "candidate",
    "preferred_addition",
    "reveal_constraint",
    "do_not_caption",
    "delivery",
    "exclude",
}


@dataclass(frozen=True)
class NarrationPromptProjectionRule:
    source_key: str
    usage: str
    transform: str
    bucket: str | None
    semantic_checks: tuple[str, ...]
    exclusion_reason: str = ""
    authoring_relevance_override: str = ""
    spoken_projection_override: str = ""
    review_visibility_override: str = ""

    @property
    def authoring_relevance(self) -> str:
        if self.authoring_relevance_override:
            return self.authoring_relevance_override
        if self.usage == "exclude":
            return "none"
        if self.usage in {"background", "candidate", "preferred_addition"}:
            return "conditional"
        return "required"

    @property
    def spoken_projection(self) -> str:
        if self.spoken_projection_override:
            return self.spoken_projection_override
        if self.usage in {"exclude", "reveal_constraint", "do_not_caption"}:
            return "must_not_surface"
        if self.usage in {"candidate", "preferred_addition"}:
            return "may_surface"
        return "derive"

    @property
    def review_visibility(self) -> str:
        if self.review_visibility_override:
            return self.review_visibility_override
        return "projection" if self.usage != "exclude" else "none"

    def as_dict(self, *, value: Any | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_key": self.source_key,
            "usage": self.usage,
            "authoring_relevance": self.authoring_relevance,
            "spoken_projection": self.spoken_projection,
            "review_visibility": self.review_visibility,
            "transform": self.transform,
            "semantic_checks": list(self.semantic_checks),
        }
        if self.bucket:
            payload["target_bucket"] = self.bucket
        if value is not None:
            payload["value"] = value
        if self.exclusion_reason:
            payload["exclusion_reason"] = self.exclusion_reason
        return payload


_RULES = (
    NarrationPromptProjectionRule(
        "manifest.video_metadata.time",
        "background",
        "constrain_world_knowledge_and_diction_without_forced_exposition",
        "background_context",
        ("時代固有の制度や道具を現代語彙で誤説明していないか", "時代名を不要に読み上げていないか"),
    ),
    NarrationPromptProjectionRule(
        "manifest.video_metadata.ending_mode",
        "background",
        "shape_payoff_and_aftertaste",
        "background_context",
        ("結末の感情的到着と語り口がending modeに整合するか",),
    ),
    NarrationPromptProjectionRule(
        "scene.time_of_day",
        "candidate",
        "mention_only_when_time_change_or_orientation_needs_voice",
        "conditional_candidates",
        ("画面で明白な時間帯を毎scene読み上げていないか", "時間経過の理解に必要なら補えているか"),
    ),
    NarrationPromptProjectionRule(
        "scene.time_of_day_visual_basis",
        "exclude",
        "review_visual_daypart_basis_without_speaking_it",
        None,
        ("光源、明るさ、影、色温度の視覚設計をナレーションとして読み上げていないか",),
        exclusion_reason="derived visual review evidence",
        review_visibility_override="review_only",
    ),
    NarrationPromptProjectionRule(
        "scene.location_sequence",
        "candidate",
        "mention_spatial_transition_only_when_orientation_needs_voice",
        "conditional_candidates",
        ("場所遷移が画面だけで理解できる場合に地名を列挙せず、理解に必要な遷移だけ補っているか",),
    ),
    NarrationPromptProjectionRule(
        "scene.location_segments",
        "candidate",
        "mention_spatial_transition_only_when_orientation_needs_voice",
        "conditional_candidates",
        ("場所別の責任や動作をそのまま列挙せず、理解に必要な因果だけを補っているか",),
    ),
    NarrationPromptProjectionRule(
        "scene.location_mode",
        "exclude",
        "exclude_location_routing_label_from_spoken_text",
        None,
        ("single/sequence等の設計labelを読み上げていないか",),
        exclusion_reason="scene routing metadata",
        review_visibility_override="review_only",
    ),
    NarrationPromptProjectionRule(
        "scene.scene_intent.story_purpose",
        "required",
        "preserve_scene_story_job",
        "required_content",
        ("sceneの物語責務を声が妨げていないか",),
    ),
    NarrationPromptProjectionRule(
        "scene.scene_intent.audience_information",
        "required",
        "cover_only_information_assigned_to_scene",
        "required_content",
        ("このsceneで観客に渡すべき情報が欠落していないか",),
    ),
    NarrationPromptProjectionRule(
        "scene.scene_intent.withheld_information",
        "reveal_constraint",
        "withhold_until_authorized",
        "reveal_constraints",
        ("後のrevealを先取りしていないか",),
    ),
    NarrationPromptProjectionRule(
        "scene.scene_intent.reveal_constraints",
        "reveal_constraint",
        "preserve_scene_reveal_order",
        "reveal_constraints",
        ("scene設計のreveal制約を破っていないか",),
    ),
    NarrationPromptProjectionRule(
        "scene.scene_intent.handoff_to_next_scene",
        "required",
        "preserve_causal_handoff_without_announcing_next_scene",
        "required_content",
        ("scene間接続が因果として聞こえるか", "次sceneの結果を予告していないか"),
    ),
    NarrationPromptProjectionRule(
        "scene.scene_intent.handoff_notes.p700_narration",
        "preferred_addition",
        "apply_narration_specific_handoff",
        "preferred_additions",
        ("p700向けの補足・禁止が原稿へ反映されているか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.viewer_contract.audience_knowledge_delta",
        "required",
        "advance_listener_understanding_once",
        "required_content",
        ("cut後の観客理解が設計どおり進むか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.source_event_contract.source_event_summary",
        "background",
        "ground_voice_in_current_event_boundary",
        "background_context",
        ("現在cutが担当するeventだけを語っているか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.source_event_contract.event_facts_to_preserve",
        "required",
        "preserve_authorized_event_facts",
        "required_content",
        ("source eventの保持必須事実を改変していないか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.source_event_contract.event_facts_not_to_invent",
        "reveal_constraint",
        "block_unsupported_event_invention",
        "reveal_constraints",
        ("source eventにない因果・事実を捏造していないか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.source_event_contract.allowed_reveal_info_ids",
        "background",
        "authorize_current_reveal_boundary_without_speaking_ids",
        "background_context",
        ("許可された情報境界の内側だけを語っているか", "内部IDを本文へ出していないか"),
        spoken_projection_override="must_not_surface",
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.source_event_contract.forbidden_reveal_info_ids",
        "reveal_constraint",
        "block_forbidden_reveal_ids_without_speaking_ids",
        "reveal_constraints",
        ("禁止情報を直接・含意で先取りしていないか", "内部IDを本文へ出していないか"),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.story_role.voice_function",
        "required",
        "select_voice_job",
        "required_content",
        ("information、emotion、causality等の声の役割が文面と一致するか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.story_role.audience_state_before",
        "background",
        "start_from_current_audience_knowledge",
        "background_context",
        ("観客がすでに知ることを初出のように説明していないか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.story_role.audience_state_after",
        "required",
        "reach_intended_audience_state",
        "required_content",
        ("cut後に到達すべき理解・感情が不足していないか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.story_role.must_cover",
        "required",
        "materialize_required_meaning",
        "required_content",
        ("must_coverが欠落していないか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.story_role.must_not_reveal",
        "reveal_constraint",
        "block_early_reveal",
        "reveal_constraints",
        ("must_not_revealの内容を直接または含意で漏らしていないか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.story_role.done_when",
        "required",
        "bind_completion_criteria",
        "required_content",
        ("原稿の合格条件を満たしているか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.role",
        "required",
        "normalize_legacy_role_to_voice_job",
        "required_content",
        ("legacy roleが現在のvoice jobとして保持されているか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.target_function",
        "required",
        "normalize_legacy_target_function",
        "required_content",
        ("legacy target_functionが原稿の意味目標として保持されているか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.must_cover",
        "required",
        "normalize_legacy_must_cover",
        "required_content",
        ("legacy must_coverが欠落していないか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.must_avoid",
        "reveal_constraint",
        "normalize_legacy_must_avoid",
        "reveal_constraints",
        ("legacy must_avoidへ反していないか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.done_when",
        "required",
        "normalize_legacy_done_when",
        "required_content",
        ("legacy done_whenを満たしているか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.timing_intent",
        "delivery",
        "normalize_legacy_timing_intent",
        "delivery_constraints",
        ("legacy timing intentが発話開始と間へ反映されているか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.downstream_handoff.p700_narration",
        "preferred_addition",
        "apply_cut_level_p700_handoff",
        "preferred_additions",
        ("cut設計からp700へのhandoffが原稿へ反映されているか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.visual_distance.distance_policy",
        "background",
        "set_audio_visual_distance",
        "background_context",
        ("stay_close、contextual、meaning_first、silentの指定と実文が一致するか",),
    ),
    NarrationPromptProjectionRule(
        "cut.visual_beat",
        "do_not_caption",
        "use_as_visual_awareness_not_spoken_copy",
        "do_not_caption",
        ("visual beatを見たまま言い直していないか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.visual_distance.visible_facts_in_frame",
        "do_not_caption",
        "prevent_visible_fact_captioning",
        "do_not_caption",
        ("画面だけで読める事実を重複説明していないか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.visual_distance.narration_should_add",
        "preferred_addition",
        "add_nonvisual_value",
        "preferred_additions",
        ("因果、内面、時間、視点、意味、対比の追加価値があるか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.rhythm_and_timing",
        "delivery",
        "fit_spoken_rhythm_to_cut",
        "delivery_constraints",
        ("発話秒数、開始、終了、間がcut尺と映像理解に整合するか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.narration_contract.tts_readiness",
        "delivery",
        "prepare_pronunciation_and_sentence_length",
        "delivery_constraints",
        ("発音対象と文長制約がtts_textに反映されているか",),
    ),
    NarrationPromptProjectionRule(
        "cut.cut_contract.motion_contract.motion_brief",
        "exclude",
        "exclude_visual_motion_instruction",
        None,
        ("動画の動作指示が読み上げ文へ流入していないか",),
        exclusion_reason="p800 visual motion only",
        review_visibility_override="review_only",
    ),
    NarrationPromptProjectionRule(
        "cut.image_generation.prompt",
        "exclude",
        "exclude_provider_image_prompt_prose",
        None,
        ("画像provider向けの構図・質感文がナレーションへ流入していないか",),
        exclusion_reason="p600 provider prompt; visual facts are supplied separately",
        review_visibility_override="review_only",
    ),
)

_BUCKET_ORDER = (
    "background_context",
    "required_content",
    "conditional_candidates",
    "preferred_additions",
    "reveal_constraints",
    "do_not_caption",
    "delivery_constraints",
)


def projection_rules() -> tuple[NarrationPromptProjectionRule, ...]:
    return _RULES


def narration_projection_registry_catalog() -> list[dict[str, Any]]:
    return [rule.as_dict() for rule in _RULES]


def rule_for_source_key(source_key: str) -> NarrationPromptProjectionRule | None:
    return next((rule for rule in _RULES if rule.source_key == source_key), None)


def narration_projection_registry_issues() -> list[str]:
    issues: list[str] = []
    keys = [rule.source_key for rule in _RULES]
    if len(keys) != len(set(keys)):
        issues.append("duplicate_source_key")
    for rule in _RULES:
        if rule.usage not in NARRATION_PROMPT_USAGES:
            issues.append(f"invalid_usage:{rule.source_key}")
        if rule.authoring_relevance not in {"required", "conditional", "none"}:
            issues.append(f"invalid_authoring_relevance:{rule.source_key}")
        if rule.spoken_projection not in {"derive", "may_surface", "must_not_surface"}:
            issues.append(f"invalid_spoken_projection:{rule.source_key}")
        if rule.review_visibility not in {"projection", "review_only", "none"}:
            issues.append(f"invalid_review_visibility:{rule.source_key}")
        if not rule.transform or not rule.semantic_checks:
            issues.append(f"missing_review_contract:{rule.source_key}")
        if rule.usage == "exclude":
            if rule.bucket or not rule.exclusion_reason:
                issues.append(f"invalid_exclusion:{rule.source_key}")
        elif rule.bucket not in _BUCKET_ORDER:
            issues.append(f"invalid_bucket:{rule.source_key}")
    return issues


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(_is_present(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_is_present(item) for item in value)
    return True


def _resolve(source_key: str, *, manifest: Mapping[str, Any], scene: Mapping[str, Any], cut: Mapping[str, Any]) -> Any:
    root_name, *parts = source_key.split(".")
    current: Any = {"manifest": manifest, "scene": scene, "cut": cut}.get(root_name)
    for index, part in enumerate(parts):
        if not isinstance(current, Mapping):
            return None
        next_value = current.get(part)
        if (
            root_name == "cut"
            and index == 0
            and part == "cut_contract"
            and not isinstance(next_value, Mapping)
        ):
            next_value = current.get("scene_contract")
        current = next_value
    return current


def build_narration_prompt_projection(
    *,
    manifest: Mapping[str, Any],
    scene: Mapping[str, Any],
    cut: Mapping[str, Any],
    scopes: tuple[str, ...] = ("manifest", "scene", "cut"),
    include_inactive: bool = True,
    include_excluded: bool = True,
    compact: bool = False,
) -> dict[str, Any]:
    """Project one cut's design keys into explicit narration-authoring jobs."""

    buckets: dict[str, list[dict[str, Any]]] = {key: [] for key in _BUCKET_ORDER}
    active_rules: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    inactive_rules: list[dict[str, Any]] = []
    for rule in _RULES:
        if rule.source_key.split(".", 1)[0] not in scopes:
            continue
        value = _resolve(rule.source_key, manifest=manifest, scene=scene, cut=cut)
        if rule.usage == "exclude":
            if include_excluded:
                excluded.append(rule.as_dict())
            continue
        if not _is_present(value):
            if include_inactive:
                inactive_rules.append(rule.as_dict())
            continue
        item = rule.as_dict(value=value)
        if compact:
            item = {
                key: item[key]
                for key in (
                    "source_key",
                    "usage",
                    "authoring_relevance",
                    "spoken_projection",
                    "target_bucket",
                    "value",
                )
                if key in item
            }
        active_rules.append(item)
        assert rule.bucket is not None
        buckets[rule.bucket].append(item)
    return {
        "registry_version": NARRATION_PROMPT_PROJECTION_REGISTRY_VERSION,
        "buckets": buckets,
        "active_rules": active_rules,
        "inactive_rules": inactive_rules,
        "excluded": excluded,
    }
