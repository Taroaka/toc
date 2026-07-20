"""Compile canonical video design contracts into provider-facing motion prose."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from toc.video_prompt_projection_registry import (
    VIDEO_PROMPT_GROUP_ORDER,
    build_video_prompt_projection,
    resolve_video_prompt_contract,
)


VIDEO_API_PROMPT_POLICY_VERSION = "video_api_prompt_v1"
VIDEO_PROMPT_COMPILER_VERSION = "conditional_video_prompt_compiler_v4"
VIDEO_PROMPT_IR_SCHEMA_VERSION = "video_prompt_ir_v2"

VIDEO_REFERENCE_ROLE_INSTRUCTIONS = {
    "start_state_visual_anchor": "参照画像{image_index}は開始状態の基準として使う。",
    "ordered_storyboard_sequence_guide": "参照画像{image_index}は順序付き絵コンテの案内として使う。",
}

_WHITESPACE_RE = re.compile(r"\s+")
_OPAQUE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*(?:_[A-Za-z0-9_.-]+)+$")
_EMBEDDED_OPAQUE_ID_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:"
    r"[A-Za-z][A-Za-z0-9.-]*(?:_[A-Za-z0-9.-]+)*(?:_internal|_id)(?:_[A-Za-z0-9.-]+)*"
    r"|(?:evt|event|reveal|asset|character|char|object|obj|location|loc|scene|cut)_[A-Za-z0-9_.-]+"
    r")(?![A-Za-z0-9_.-])",
    re.I,
)
_PATH_RE = re.compile(r"(?:^|[\s`])(?:assets|output|logs|scratch)/|\.(?:png|jpe?g|webp|mp4|mov)\b", re.I)
_INTERNAL_RE = re.compile(
    r"(?:cut_contract|scene_contract|cut_blueprint|source_event|event_beat|target_beat|"
    r"first_frame_contract|motion_contract|api_prompt_payload|drawable_prompt_ir|video_prompt_ir|"
    r"compiler_version|policy_version|source_digest|sha256|validation_gate|\bscene\d+|\bcut\d+)",
    re.I,
)
_PLACEHOLDER_MARKERS = (
    "TODO",
    "TBD",
    "pending",
    "p800 motion prompt",
    "次 cut へ渡す最後の状態",
    "次cutへ渡す最後の状態",
    "derive_from",
    "<cut_contract",
)
_CAMERA_RE = re.compile(
    r"(?:カメラ|camera|dolly|pan(?:ning)?|tilt|truck|crane|orbit|zoom|push[ -]?in|pull[ -]?back|"
    r"寄る|引く|パン|ティルト|追従|回り込|固定|低い位置|高い位置)",
    re.I,
)
_CAMERA_OPERATION_RE = re.compile(
    r"(?:locked[ _-]?off|handheld|dolly|pan(?:ning)?|tilt|truck|crane|orbit|zoom|"
    r"push[ _-]?in|pull[ _-]?back|寄(?:る|り(?!添)|って|せ(?:る)?)|"
    r"引(?:く|き(?!続|出し)|いて|いた|けば)|横移動|上昇|下降|回転|"
    r"パン|ティルト|ズーム|ドリー|トラック|クレーン|オービット|追従|回り込|固定|手持ち)",
    re.I,
)
_EXPLICIT_CAMERA_CONTEXT_RE = re.compile(
    r"(?:カメラ|camera|locked[ _-]?off|handheld|dolly|pan(?:ning)?|tilt|truck|crane|orbit|zoom|"
    r"push[ _-]?in|pull[ _-]?back|パン|ティルト|ズーム|ドリー|トラック|クレーン|"
    r"オービット|手持ち)",
    re.I,
)
_EDIT_RE = re.compile(r"(?:fade|dissolve|montage|shot switch|jump cut|フェード|暗転|ディゾルブ|モンタージュ|別ショット)", re.I)

_LABEL_TO_GROUP = {
    "motion_brief": "primary_motion",
    "motion_intent": "primary_motion",
    "intent": "primary_motion",
    "action": "primary_motion",
    "subject_motion": "primary_motion",
    "camera": "camera_motion",
    "camera_motion": "camera_motion",
    "カメラ": "camera_motion",
    "environment_motion": "environment_motion",
    "emotional_change": "emotional_change",
    "start_from_visible_state": "start_state",
    "first_frame_brief": "start_state",
    "end_state": "end_state",
    "end_frame_brief": "end_state",
    "handoff_state": "end_state",
    "must_preserve": "continuity",
    "continuity": "continuity",
    "continuity_notes": "continuity",
    "direction_notes": "continuity",
    "must_not_add": "constraints",
    "must_avoid": "constraints",
    "avoid": "constraints",
    "negative": "constraints",
}
_DISCARDED_LABELS = {
    "cut_function",
    "target_beat",
    "screen_question",
    "dramatic_job",
    "scene_event",
    "render_unit",
    "source_event_beat_id",
    "event_time_position",
}

_CAMERA_ENUM_INSTRUCTIONS = {
    "static": "カメラを固定する",
    "locked_off": "カメラを固定する",
    "slow_push": "カメラは被写体へゆっくり寄る",
    "slow_push_in": "カメラは被写体へゆっくり寄る",
    "push_in": "カメラは被写体へ寄る",
    "slow_dolly_forward": "カメラは被写体へゆっくり寄る",
    "dolly_forward": "カメラは被写体へ寄る",
    "slow_pull_back": "カメラはゆっくり引く",
    "pull_back": "カメラは引く",
    "pan_left": "カメラはゆっくり左へパンする",
    "pan_right": "カメラはゆっくり右へパンする",
    "tilt_up": "カメラはゆっくり上へティルトする",
    "tilt_down": "カメラはゆっくり下へティルトする",
    "subtle_handheld": "ごく小さな手持ちの揺れだけを加える",
    "gentle_tracking": "カメラは被写体を穏やかに追従する",
}


def compose_video_render_unit_contract(
    source_contracts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compose the canonical boundary contract for a multi-cut render unit.

    A one-cut unit inherits that cut exactly.  A multi-cut unit keeps the first
    visible boundary, the last visible end state, and the union of continuity
    and prohibitions.  Its single primary motion remains an explicit unit-level
    authoring source; individual cut actions are not concatenated.
    """

    contracts = [dict(contract) for contract in source_contracts if contract]
    if not contracts:
        return {}
    if len(contracts) == 1:
        return contracts[0]

    first_contract = contracts[0]
    last_contract = contracts[-1]
    first_frame_contract = dict(
        _mapping(first_contract.get("first_frame_contract"))
    )
    last_motion = _mapping(last_contract.get("motion_contract"))
    must_not_add: list[Any] = []
    allowed_new_reveal_elements: list[Any] = []
    carry_forward: list[Any] = []
    for contract in contracts:
        motion = _mapping(contract.get("motion_contract"))
        continuity = _mapping(contract.get("continuity_contract"))
        must_not_add.extend(_sequence(motion.get("must_not_add")))
        allowed_new_reveal_elements.extend(
            _validated_reveal_allowlist(
                motion.get("allowed_new_reveal_elements")
            )
        )
        carry_forward.extend(
            _sequence(continuity.get("carry_forward_to_next_cut"))
        )
    if _dedupe(allowed_new_reveal_elements):
        raise ValueError(
            "video_render_unit_requires_explicit_reveal_authorization"
        )

    motion_contract = {
        "end_state": last_motion.get("end_state"),
        "end_frame_brief": last_motion.get("end_frame_brief"),
        "must_not_add": list(_dedupe(must_not_add)),
    }
    continuity_contract = {
        "carry_forward_to_next_cut": list(_dedupe(carry_forward)),
    }
    return {
        "first_frame_contract": first_frame_contract,
        "motion_contract": {
            key: value for key, value in motion_contract.items() if value
        },
        "continuity_contract": {
            key: value for key, value in continuity_contract.items() if value
        },
    }


def compile_video_api_prompt_v1(
    *,
    cut_contract: Mapping[str, Any] | None = None,
    scene_contract: Mapping[str, Any] | None = None,
    video_generation: Mapping[str, Any] | None = None,
    source_prompt: str = "",
    story_time: str = "",
    time_of_day: str = "",
    tool: str = "",
    first_frame: str | None = None,
    last_frame: str | None = None,
    duration_seconds: int | float | None = None,
    references: Sequence[Any] | None = None,
    reference_roles: Sequence[Mapping[str, Any]] | None = None,
    quality: str | None = None,
    aspect_ratio: str | None = None,
    execution_options: Mapping[str, Any] | None = None,
    additional_negative_prompt: str = "",
    direction_notes: Sequence[Any] = (),
    continuity_notes: Sequence[Any] = (),
    first_frame_visual_plan: Mapping[str, Any] | None = None,
    review_only_dependencies: Mapping[str, Any] | None = None,
    scene_time_of_day_visual_basis: Any = None,
    scene_location_mode: str = "",
    scene_location_sequence: Sequence[Any] = (),
    scene_location_segments: Sequence[Mapping[str, Any]] = (),
    prefix: str = "",
    suffix: str = "",
) -> dict[str, Any]:
    """Return a deterministic, reviewable provider prompt payload."""

    vg = dict(video_generation or {})
    raw_source = str(source_prompt or vg.get("prompt_authoring_source") or vg.get("source_motion_prompt") or "").strip()
    materialized_payload = _mapping(vg.get("api_prompt_payload"))
    if not raw_source and not str(materialized_payload.get("prompt") or "").strip():
        raw_source = str(vg.get("motion_prompt") or vg.get("prompt") or vg.get("video_prompt") or "").strip()
    provider = str(tool or vg.get("tool") or "kling_3_0").strip()
    first_source = (
        vg.get("first_frame")
        or vg.get("first_frame_image")
        or vg.get("input_image")
        or ""
        if first_frame is None
        else first_frame
    )
    last_source = (
        vg.get("last_frame") or vg.get("last_frame_image") or ""
        if last_frame is None
        else last_frame
    )
    first = str(first_source or "").strip()
    last = str(last_source or "").strip()
    if last and not first:
        raise ValueError("last_frame_requires_first_frame")
    duration = duration_seconds if duration_seconds is not None else vg.get("duration_seconds")
    reference_bindings = _dedupe_raw_strings(
        references if references is not None else _sequence(vg.get("references"))
    )
    reference_role_bindings = _normalize_reference_roles(
        reference_roles
        if reference_roles is not None
        else _sequence(vg.get("reference_roles")),
        reference_count=len(reference_bindings),
    )
    if _is_seedance(provider) and reference_bindings and (first or last):
        raise ValueError("seedance_frame_and_reference_modes_are_mutually_exclusive")
    quality_binding = str(quality if quality is not None else vg.get("quality") or "").strip()
    aspect_ratio_binding = str(
        aspect_ratio if aspect_ratio is not None else vg.get("aspect_ratio") or ""
    ).strip()
    execution_option_bindings = _normalized_digest_source(dict(execution_options or {}))
    direction = _dedupe([*direction_notes, *_sequence(vg.get("direction_notes")), prefix, suffix])
    continuity = _dedupe([*continuity_notes, *_sequence(vg.get("continuity_notes"))])
    parsed_source = _parse_source_prompt(raw_source)

    projection = build_video_prompt_projection(
        manifest={"video_metadata": {"time": story_time}},
        scene={
            "time_of_day": time_of_day,
            "time_of_day_visual_basis": scene_time_of_day_visual_basis,
            "location_mode": str(scene_location_mode or "").strip(),
            "location_sequence": list(scene_location_sequence or ()),
            "location_segments": [
                dict(item)
                for item in scene_location_segments or ()
                if isinstance(item, Mapping)
            ],
        },
        cut={"cut_contract": dict(cut_contract or scene_contract or {})},
        video_generation={
            **vg,
            "tool": provider,
            "first_frame": first,
            "last_frame": last,
            "prompt_authoring_source": raw_source,
            "direction_notes": list(direction),
            "continuity_notes": list(continuity),
            "references": list(reference_bindings),
            "reference_roles": list(reference_role_bindings),
            "quality": quality_binding,
            "aspect_ratio": aspect_ratio_binding,
        },
        cut_contract=cut_contract,
        scene_contract=scene_contract,
        normalized_authoring_groups=parsed_source,
    )

    contract = _normalized_contract(cut_contract=cut_contract, scene_contract=scene_contract)
    motion = _mapping(contract.get("motion_contract"))
    first_contract = _mapping(contract.get("first_frame_contract"))
    continuity_contract = _mapping(contract.get("continuity_contract"))
    viewer = _mapping(contract.get("viewer_contract"))
    vg_motion = _mapping(vg.get("motion_contract"))
    reveal_allowlist_source = (
        motion.get("allowed_new_reveal_elements")
        if "allowed_new_reveal_elements" in motion
        else vg_motion.get("allowed_new_reveal_elements")
    )
    allowed_new_reveal_elements = _validated_reveal_allowlist(
        reveal_allowlist_source
    )
    if len(allowed_new_reveal_elements) > 8:
        raise ValueError("video_reveal_allowlist_exceeds_limit")

    first_frame_plan_start_values = _dedupe(
        _first_frame_plan_start_values(first_frame_visual_plan)
    )
    authored_start_values = first_frame_plan_start_values or _dedupe(
        [
            motion.get("start_from_visible_state"),
            *_flatten_preferred(_mapping(first_contract.get("visible_start_state"))),
            _strip_first_frame_meta(first_contract.get("first_frame_brief")),
        ]
    )
    start_values = authored_start_values or _dedupe(parsed_source["start_state"])
    start_lines: list[str] = []
    if first:
        start_lines.append("入力画像に写る人物、構図、物の位置、光を開始状態として保つ。")
    start_lines.extend(_sentences(start_values, limit=4))

    canonical_primary = _first_clean(
        motion.get("motion_brief"),
        motion.get("subject_motion"),
    )
    parsed_primary = parsed_source["primary_motion"]
    parsed_camera = parsed_source["camera_motion"]
    if canonical_primary:
        primary = canonical_primary
    else:
        primary = _first_clean(
            vg_motion.get("motion_intent"),
            vg_motion.get("intent"),
            vg_motion.get("motion_brief"),
            vg_motion.get("action_intent"),
            *parsed_primary,
        )
    generated_primary_fallback = not bool(primary)
    if generated_primary_fallback:
        if first and last:
            primary = "開始状態から終了画像の状態へ、一つの自然な動きで連続して移る"
        elif first:
            primary = "被写体は自然な呼吸とごく小さな重心移動だけを行う"
        else:
            primary = "一つの明確な動作だけを自然な速度で行う"
    primary = _limit_primary_motion(primary, provider)

    camera = _first_camera_value(
        motion.get("camera_motion"),
        vg_motion.get("camera_motion"),
        *parsed_camera,
    )
    environment = _first_clean(
        motion.get("environment_motion"),
        vg_motion.get("environment_motion"),
        *parsed_source["environment_motion"],
    )
    emotional = _first_clean(
        motion.get("emotional_change"),
        vg_motion.get("emotional_change"),
        *_emotional_shift_values(viewer.get("emotional_micro_shift")),
        *parsed_source["emotional_change"],
    )
    authored_end_values = _dedupe(
        [
            motion.get("end_state"),
            motion.get("end_frame_brief"),
            continuity_contract.get("end_state"),
        ]
    )
    end_values = authored_end_values or _dedupe(
        [
            vg_motion.get("handoff_state"),
            vg_motion.get("end_state"),
            *parsed_source["end_state"],
        ]
    )
    end_lines = _sentences(end_values, limit=2)
    if last:
        end_lines.append("最後は指定された終了画像の人物、構図、物の位置、光へ自然に一致させる。")

    authored_continuity = _dedupe(
        _sequence(continuity_contract.get("carry_forward_to_next_cut"))
    )
    fallback_continuity = _dedupe(
        [
            *_sequence(vg_motion.get("must_preserve")),
            *parsed_source["continuity"],
        ]
    )
    continuity_values = _dedupe(
        [
            *(authored_continuity or fallback_continuity),
            *continuity,
            *direction,
        ]
    )
    continuity_lines: list[str] = []
    if story_time.strip():
        if allowed_new_reveal_elements:
            continuity_lines.append(
                f"主動作で現れる承認済み要素も含め、{_sentence_body(story_time)}の"
                "衣装、髪型、建築、生活道具、素材、技術水準に整合させる。"
            )
        else:
            continuity_lines.append(
                f"{_sentence_body(story_time)}の衣装、髪型、建築、生活道具、素材、技術水準を変えない。"
            )

    if time_of_day.strip():
        continuity_lines.append(
            f"{_sentence_body(time_of_day)}の空の明るさ、自然光と人工光、影、色温度を変えない。"
        )
    continuity_lines.extend(
        VIDEO_REFERENCE_ROLE_INSTRUCTIONS[item["role"]].format(
            image_index=item["image_index"]
        )
        for item in reference_role_bindings
    )
    continuity_lines.extend(_sentences(continuity_values, limit=5))
    if allowed_new_reveal_elements:
        continuity_lines.append(
            "顔、髪、体格、画面内の位置関係、光源方向を一貫させ、"
            "衣装と重要な小道具は承認済み要素以外を変えない。"
        )
    else:
        continuity_lines.append("顔、髪、衣装、体格、重要な小道具、画面内の位置関係、光源方向を一貫させる。")

    authored_forbidden = _dedupe(_sequence(motion.get("must_not_add")))
    fallback_forbidden = _dedupe(
        [
            *_sequence(vg_motion.get("must_not_add")),
            *_sequence(vg_motion.get("must_avoid")),
            *_sequence(vg_motion.get("forbidden_additions")),
            *parsed_source["constraints"],
        ]
    )
    forbidden = authored_forbidden or fallback_forbidden
    if set(allowed_new_reveal_elements) & set(forbidden):
        raise ValueError("video_reveal_allowlist_conflicts_with_forbidden")
    reveal_evidence_text = " ".join(
        [primary, *end_values]
    )
    if any(
        element not in reveal_evidence_text
        for element in allowed_new_reveal_elements
    ):
        raise ValueError("video_reveal_allowlist_not_grounded_in_motion_or_end_state")
    constraint_lines: list[str] = []
    if forbidden:
        constraint_lines.append("追加しないものは、" + "、".join(forbidden[:8]) + "。")
    if allowed_new_reveal_elements:
        constraint_lines.append(
            "主動作によって新しく現れてよいものは、"
            + "、".join(allowed_new_reveal_elements[:8])
            + "。"
        )
        constraint_lines.append(
            "上記の承認済み要素以外は、開始画像にない人物、重要な小道具、"
            "建築、物語上のrevealを新しく出さない。"
        )
    else:
        constraint_lines.append(
            "開始画像にない人物、重要な小道具、建築、物語上のrevealを新しく出さない。"
        )
    if _is_kling(provider):
        constraint_lines.append(
            "主動作は一つに絞り、単一の連続ショットとして見せる。急なcamera回転や視点ジャンプを行わず、フェードしない、暗転しない、ディゾルブしない、別ショットへ切り替えない。"
        )
        constraint_lines.append(
            "画面内テキスト、字幕、ロゴ、ウォーターマーク、顔や手指の崩れ、不自然な四肢を出さない。"
        )
    else:
        constraint_lines.append("画面内テキスト、字幕、ロゴ、ウォーターマーク、急な視点ジャンプを出さない。")

    if last:
        constraint_lines.append(
            "終了フレームを到達境界として扱い、途中でフェードしない、カットしない、別ショットへ切り替えない。"
        )

    additional_negative = _clean_text(additional_negative_prompt)
    negative_prompt_mode = "inline" if _is_seedance(provider) else "separate"
    if additional_negative and negative_prompt_mode == "inline":
        constraint_lines.append(_ensure_sentence(additional_negative))
    negative_prompt_lines = (
        []
        if negative_prompt_mode == "inline"
        else [
            line
            for line in constraint_lines
            if not line.startswith("主動作によって新しく現れてよいものは、")
        ]
    )
    if additional_negative and negative_prompt_mode == "separate":
        negative_prompt_lines.append(_ensure_sentence(additional_negative))
    negative_prompt = " / ".join(_dedupe(negative_prompt_lines))

    if not (
        first
        or story_time.strip()
        or time_of_day.strip()
        or continuity_values
        or reference_role_bindings
    ):
        continuity_lines = []

    non_camera_fragment_values: dict[str, str] = {
        "start_state": "\n".join(_dedupe(start_lines)),
        "primary_motion": _ensure_sentence(primary),
        "environment_motion": _ensure_sentence(environment),
        "emotional_change": _ensure_sentence(emotional),
        "end_state": "\n".join(_dedupe(end_lines)),
        "continuity": "\n".join(_dedupe(continuity_lines)),
        "constraints": "\n".join(_dedupe(constraint_lines)),
    }
    camera_budget = 2
    if _is_kling(provider):
        non_camera_operations = sum(
            _explicit_camera_operation_count(non_camera_fragment_values[group])
            for group in (
                "start_state",
                "primary_motion",
                "environment_motion",
                "emotional_change",
                "end_state",
                "continuity",
            )
        )
        if non_camera_operations > camera_budget:
            raise ValueError("video_api_prompt_exceeds_camera_instruction_limit")
        camera_budget -= non_camera_operations
    fragment_values: dict[str, str] = {
        **non_camera_fragment_values,
        "camera_motion": _ensure_sentence(
            _limit_camera(camera, provider, max_operations=camera_budget)
        ),
    }
    included_fragments = [
        {"group": group, "text": fragment_values[group]}
        for group in VIDEO_PROMPT_GROUP_ORDER
        if fragment_values[group]
    ]
    omitted_groups = [group for group in VIDEO_PROMPT_GROUP_ORDER if not fragment_values[group]]
    prompt = _render_prompt(included_fragments)
    _validate_provider_prompt(prompt)
    quality_issues = _video_prompt_quality_issues(
        fragment_values=fragment_values,
        generated_primary_fallback=generated_primary_fallback,
    )

    mode = (
        "first_last_frame"
        if first and last
        else "image_to_video"
        if first
        else "reference_to_video"
        if reference_bindings
        else "text_to_video"
    )
    provider_policy = {
        "one_clip_one_intent": True,
        "max_camera_instructions": 2 if _is_kling(provider) else None,
        "single_continuous_shot": True,
        "first_last_frame_boundary": bool(first and last),
        "multimodal_reference": bool(reference_bindings),
        "negative_prompt_mode": negative_prompt_mode,
    }
    provider_request_binding = {
        "duration_seconds": duration,
        "quality": quality_binding,
        "aspect_ratio": aspect_ratio_binding,
        "first_frame": first,
        "last_frame": last,
        "references": list(reference_bindings),
    }
    if reference_role_bindings:
        provider_request_binding["reference_roles"] = list(reference_role_bindings)
    if execution_option_bindings:
        provider_request_binding["execution_options"] = execution_option_bindings
    source_payload = {
        "policy_version": VIDEO_API_PROMPT_POLICY_VERSION,
        "compiler_version": VIDEO_PROMPT_COMPILER_VERSION,
        "projection_registry_version": projection["registry_version"],
        "ir_schema_version": VIDEO_PROMPT_IR_SCHEMA_VERSION,
        "provider": provider,
        "mode": mode,
        "duration_seconds": duration,
        "story_time": story_time.strip(),
        "time_of_day": time_of_day.strip(),
        "has_first_frame": bool(first),
        "has_last_frame": bool(last),
        "included_fragments": included_fragments,
        "omitted_groups": omitted_groups,
        "provider_policy": provider_policy,
        "provider_request_binding": provider_request_binding,
        "negative_prompt": negative_prompt,
        "quality_issues": quality_issues,
        "review_only_sources": projection["review_only_sources"],
        "design_source": _normalized_digest_source(
            {
                "contract": contract,
                "video_motion_contract": vg_motion,
                "authoring_source": raw_source,
                "first_frame": first,
                "last_frame": last,
                "direction_notes": direction,
                "continuity_notes": continuity,
                "first_frame_visual_plan": first_frame_visual_plan,
                "review_only_dependencies": review_only_dependencies,
                "scene_time_of_day_visual_basis": scene_time_of_day_visual_basis,
                "scene_location_mode": scene_location_mode,
                "scene_location_sequence": list(scene_location_sequence or ()),
                "scene_location_segments": [
                    dict(item)
                    for item in scene_location_segments or ()
                    if isinstance(item, Mapping)
                ],
                "reference_roles": list(reference_role_bindings),
            }
        ),
    }
    source_digest = _sha256_json(source_payload)
    ir = {
        "schema_version": VIDEO_PROMPT_IR_SCHEMA_VERSION,
        "provider": provider,
        "mode": mode,
        "dependencies": {
            "story_time": story_time.strip(),
            "time_of_day": time_of_day.strip(),
            "has_first_frame": bool(first),
            "has_last_frame": bool(last),
            "has_references": bool(reference_bindings),
            "duration_seconds": duration,
            "required_groups": [item["group"] for item in included_fragments],
            "reference_roles": list(reference_role_bindings),
        },
        "included_fragments": included_fragments,
        "omitted_groups": omitted_groups,
        "quality_issues": quality_issues,
    }
    return {
        "policy_version": VIDEO_API_PROMPT_POLICY_VERSION,
        "compiler_version": VIDEO_PROMPT_COMPILER_VERSION,
        "projection_registry_version": projection["registry_version"],
        "provider": provider,
        "mode": mode,
        "provider_policy": provider_policy,
        "provider_request_binding": provider_request_binding,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "quality_issues": quality_issues,
        "source_digest": source_digest,
        "sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "included_fragments": included_fragments,
        "omitted_groups": omitted_groups,
        "projection_review_contract": projection,
        "video_prompt_ir": ir,
    }


def _parse_source_prompt(value: str) -> dict[str, list[str]]:
    groups = {group: [] for group in VIDEO_PROMPT_GROUP_ORDER}
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip().lstrip("-• ")
        if not line or line.startswith("```") or (line.startswith("[") and line.endswith("]")):
            continue
        label_match = re.match(
            r"^([A-Za-z_][A-Za-z0-9_ -]*|カメラ)\s*[:：]\s*(.+)$",
            line,
        )
        if label_match:
            label = label_match.group(1).strip().lower().replace(" ", "_")
            text = _clean_text(label_match.group(2))
            if not text or label in _DISCARDED_LABELS:
                continue
            group = _LABEL_TO_GROUP.get(label)
            if group:
                groups[group].append(text)
            continue
        text = _clean_text(line)
        if not text:
            continue
        if _EDIT_RE.search(text):
            groups["constraints"].append(text)
        elif _CAMERA_RE.search(text):
            groups["camera_motion"].append(text)
        else:
            groups["primary_motion"].append(text)
    for group in groups:
        groups[group] = list(_dedupe(groups[group]))
    return groups


def _normalized_contract(
    *,
    cut_contract: Mapping[str, Any] | None,
    scene_contract: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return the registry's shared per-field contract resolution."""

    return resolve_video_prompt_contract(
        {},
        cut_contract=cut_contract,
        scene_contract=scene_contract,
    )


def _render_prompt(fragments: list[dict[str, str]]) -> str:
    labels = {
        "start_state": "開始状態",
        "primary_motion": "主動作",
        "camera_motion": "カメラ",
        "environment_motion": "環境の動き",
        "emotional_change": "感情の変化",
        "end_state": "終了状態",
        "continuity": "維持条件",
        "constraints": "禁止",
    }
    return "\n\n".join(f"[{labels[item['group']]}]\n{item['text']}" for item in fragments).strip()


def _validate_provider_prompt(prompt: str) -> None:
    if not prompt.strip():
        raise ValueError("video_api_prompt_empty")
    if (
        _INTERNAL_RE.search(prompt)
        or _PATH_RE.search(prompt)
        or _EMBEDDED_OPAQUE_ID_RE.search(prompt)
    ):
        raise ValueError("video_api_prompt_contains_internal_metadata")


def _clean_text(value: Any) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    text = _WHITESPACE_RE.sub(" ", str(value)).strip(" `\t\r\n、。:：")
    if not text:
        return ""
    text = _replace_production_jargon(text)
    if any(marker.lower() in text.lower() for marker in _PLACEHOLDER_MARKERS):
        return ""
    if (
        _PATH_RE.search(text)
        or _INTERNAL_RE.search(text)
        or _OPAQUE_ID_RE.fullmatch(text)
        or _EMBEDDED_OPAQUE_ID_RE.search(text)
    ):
        return ""
    if re.search(r"(?:次|前|後続)\s*(?:cut|scene)", text, re.I):
        return ""
    return text


def _strip_first_frame_meta(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^動画が動き出す直前に見えている初期状態[。:：\s]*", "", text)
    return _clean_text(text)


def _first_frame_plan_start_values(plan: Mapping[str, Any] | None) -> list[Any]:
    temporal = _mapping(_mapping(plan).get("temporal_boundary"))
    return [temporal.get("event_fact_visible_in_still"), temporal.get("first_visible_moment")]


def _flatten_preferred(value: Mapping[str, Any]) -> list[Any]:
    preferred = ("character_state", "prop_state", "spatial_state", "emotional_state", "gaze_or_attention")
    return [value.get(key) for key in preferred]


def _emotional_shift_values(value: Any) -> list[Any]:
    if not isinstance(value, Mapping):
        return []
    start = _clean_text(value.get("from"))
    end = _clean_text(value.get("to"))
    if start and end:
        return [f"{start}から{end}へ、表情と姿勢が小さく変わる"]
    return [end or start]


def _limit_camera(
    value: str,
    provider: str,
    *,
    max_operations: int = 2,
) -> str:
    token = re.sub(r"[\s-]+", "_", str(value or "").strip().lower())
    text = _CAMERA_ENUM_INSTRUCTIONS.get(token) or _clean_text(value)
    if not text:
        return ""
    if not _is_kling(provider):
        return text
    if max_operations <= 0:
        return ""
    operations = list(_CAMERA_OPERATION_RE.finditer(text))
    if len(operations) <= max_operations:
        return text
    limited = text[: operations[max_operations].start()]
    limited = re.sub(
        r"(?:[、,;；]\s*)?(?:その後|続いて|次に|then|and)?\s*$",
        "",
        limited,
        flags=re.I,
    )
    limited = re.sub(
        r"(?:[、,;；]\s*)?(?:(?:左|右|上|下|前|後|内|外)(?:側)?|被写体)"
        r"(?:へ|に|から|方向へ)\s*$",
        "",
        limited,
    )
    limited = re.sub(r"し\s*$", "する", limited)
    limited = re.sub(r"寄り\s*$", "寄る", limited)
    limited = re.sub(r"引き\s*$", "引く", limited)
    return _clean_text(limited)


def _explicit_camera_operation_count(value: str) -> int:
    text = str(value or "")
    if not _EXPLICIT_CAMERA_CONTEXT_RE.search(text):
        return 0
    return sum(
        not _camera_operation_is_negated(text, operation)
        for operation in _CAMERA_OPERATION_RE.finditer(text)
    )


def _camera_operation_is_negated(text: str, operation: re.Match[str]) -> bool:
    clause_tail = re.split(
        r"[、,。.;；\n]",
        text[operation.end() :],
        maxsplit=1,
    )[0]
    return bool(
        re.search(
            r"(?:は|を|も)?\s*(?:"
            r"しない|せず|行わない|行わず|避ける|禁止(?:する)?|"
            r"加えない|使わない|採用しない"
            r")",
            clause_tail,
        )
    )


def _replace_production_jargon(value: str) -> str:
    text = re.sub(
        r"[^、。]*(?:前|次|後続)\s*(?:cut|scene)[^、。]*を受け[、,]?\s*",
        "",
        value,
        flags=re.I,
    )
    text = re.sub(
        r"(?:次|後続)\s*(?:cut|scene)\s*の\s*reveal",
        "後続の出来事の先取り",
        text,
        flags=re.I,
    )
    text = re.sub(r"前\s*cut\s*から進んだ", "開始画像にある", text, flags=re.I)
    text = re.sub(r"前\s*cut\s*から残る", "開始画像に残る", text, flags=re.I)
    text = re.sub(
        r"次\s*cut\s*へ視線または姿勢が渡る",
        "視線または姿勢が画面内に残る",
        text,
        flags=re.I,
    )
    text = text.replace("次へ渡す証拠", "後まで画面に残す証拠")
    text = text.replace("次に見るべき証拠または導線へ向く", "画面内の証拠または導線へ視線を向ける")
    text = text.replace("不可視から可視へ一段近づく", "内面の変化が視線と表情にわずかに現れる")
    text = text.replace("sceneの圧力", "周囲からの圧力")
    text = text.replace("sceneの変化", "画面内の変化")
    text = text.replace("sceneの前提", "その場の状況")
    text = text.replace("scene全体", "一連の出来事")
    sequence = (
        r"(?:(?:次|前|後続)\s*(?:cut|scene))"
        r"(?:\s*または\s*(?:(?:次|前|後続)\s*)?(?:cut|scene))?"
    )
    text = re.sub(sequence + r"\s*で扱う", "", text, flags=re.I)
    text = re.sub(sequence + r"\s*へ渡る", "", text, flags=re.I)
    text = re.sub(sequence + r"\s*へつながる", "その後へつながる", text, flags=re.I)
    text = re.sub(sequence + r"\s*へ残る", "画面に残る", text, flags=re.I)
    text = re.sub(sequence, "", text, flags=re.I)
    text = text.replace("物語上のreveal", "物語上の未提示の出来事")
    text = text.replace("camera回転", "カメラ回転")
    return _WHITESPACE_RE.sub(" ", text).strip(" `\t\r\n、。:：")


def _limit_primary_motion(value: str, provider: str) -> str:
    text = _clean_text(value)
    if not text or not _is_kling(provider):
        return text
    edit = _EDIT_RE.search(text)
    if edit:
        text = text[: edit.start()]
    text = re.split(
        r"(?:[、,。.]\s*)?(?:その後|続いて|次に|after\s+that\b|then\b)",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]
    return _clean_text(text.rstrip("、, "))


def _sentences(values: Iterable[Any], *, limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _clean_text(value)
        if text:
            result.append(_ensure_sentence(text))
        if len(result) >= limit:
            break
    return result


def _ensure_sentence(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    return text if text.endswith(("。", ".", "！", "!", "？", "?")) else text + "。"


def _sentence_body(value: Any) -> str:
    return _clean_text(value).rstrip("。.!！")


def _first_clean(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _first_camera_value(*values: Any) -> str:
    for value in values:
        raw = str(value or "").strip()
        token = re.sub(r"[\s-]+", "_", raw.lower())
        if token in _CAMERA_ENUM_INSTRUCTIONS:
            return raw
        text = _clean_text(value)
        if text:
            return text
    return ""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if value in (None, ""):
        return []
    return [value]


def _validated_reveal_allowlist(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if not isinstance(value, (list, tuple, set)):
        raise ValueError("video_reveal_allowlist_requires_sequence")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not _clean_text(item):
            raise ValueError("video_reveal_allowlist_requires_nonempty_strings")
        normalized.append(_clean_text(item))
    return _dedupe(normalized)


def _dedupe(values: Iterable[Any]) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return tuple(output)


def _dedupe_raw_strings(values: Iterable[Any]) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return tuple(output)


def _normalize_reference_roles(
    values: Iterable[Any],
    *,
    reference_count: int,
) -> tuple[dict[str, Any], ...]:
    raw_values = list(values)
    if not raw_values:
        return ()
    if len(raw_values) != reference_count:
        raise ValueError(
            "video_reference_roles_count_must_equal_ordered_references"
        )

    normalized: list[dict[str, Any]] = []
    indexes: list[int] = []
    for raw in raw_values:
        if not isinstance(raw, Mapping):
            raise ValueError("video_reference_roles_must_be_mappings")
        raw_index = raw.get("image_index")
        if isinstance(raw_index, bool):
            raise ValueError("video_reference_roles_image_index_must_be_integer")
        try:
            image_index = int(raw_index)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "video_reference_roles_image_index_must_be_integer"
            ) from exc
        if str(raw_index).strip() != str(image_index):
            raise ValueError("video_reference_roles_image_index_must_be_integer")
        role = str(raw.get("role") or "").strip()
        if role not in VIDEO_REFERENCE_ROLE_INSTRUCTIONS:
            raise ValueError(f"video_reference_roles_unsupported_role:{role}")
        indexes.append(image_index)
        normalized.append({"image_index": image_index, "role": role})

    expected_indexes = list(range(1, reference_count + 1))
    if indexes != expected_indexes or len(indexes) != len(set(indexes)):
        raise ValueError(
            "video_reference_roles_image_index_must_be_consecutive_unique_and_ordered"
        )
    return tuple(normalized)


_UNRESOLVED_ALTERNATIVE_RE = re.compile(
    r"(?:または|もしくは|あるいは|\bor\b)",
    re.I,
)
_ABSTRACT_PRIMARY_MOTION_RE = re.compile(
    r"(?:変化点|(?:scene|シーン|画面内|内面)の変化|"
    r"変化を(?:見せる|表す|描く)|何かが変化|動きが起きる|"
    r"change(?:s|d)?\s+(?:occurs?|happens?))",
    re.I,
)
_ABSTRACT_END_STATE_RE = re.compile(
    r"(?:変化点|変化の証拠|変化後の(?:物証|証拠)|物証|"
    r"(?:scene|シーン|画面内|内面)の変化|その後へつながる|"
    r"次へつながる|結果が見える|end\s+state)",
    re.I,
)
_SEQUENTIAL_OVERVIEW_RE = re.compile(r"(?:→|⇒|->|=>)")


def _video_prompt_quality_issues(
    *,
    fragment_values: Mapping[str, str],
    generated_primary_fallback: bool,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    def add(code: str, group: str, message: str, value: str) -> None:
        item = {
            "code": code,
            "blocking": True,
            "group": group,
            "message": message,
            "value": value,
        }
        if item not in issues:
            issues.append(item)

    primary = str(fragment_values.get("primary_motion") or "").strip()
    environment = str(fragment_values.get("environment_motion") or "").strip()
    emotional = str(fragment_values.get("emotional_change") or "").strip()
    end_state = str(fragment_values.get("end_state") or "").strip()

    if generated_primary_fallback:
        add(
            "video_motion_generated_fallback",
            "primary_motion",
            "主動作が設計値から解決できず、compiler fallbackが生成された",
            primary,
        )

    for group in (
        "start_state",
        "primary_motion",
        "environment_motion",
        "emotional_change",
        "end_state",
    ):
        value = str(fragment_values.get(group) or "").strip()
        if value and _UNRESOLVED_ALTERNATIVE_RE.search(value):
            add(
                "video_motion_unresolved_alternative",
                group,
                "providerへ渡す前に一つの画面上の状態へ確定する必要がある",
                value,
            )
        if value and _SEQUENTIAL_OVERVIEW_RE.search(value):
            add(
                "video_motion_sequential_overview",
                group,
                "scene全体の出来事列ではなく、このclip内の一つの開始・動作・終了へ分解する必要がある",
                value,
            )

    if primary and _ABSTRACT_PRIMARY_MOTION_RE.search(primary):
        add(
            "video_motion_abstract_primary",
            "primary_motion",
            "主動作を人物または物の具体的で観察可能な動作へ変換する必要がある",
            primary,
        )
    if end_state and _ABSTRACT_END_STATE_RE.search(end_state):
        add(
            "video_motion_abstract_end_state",
            "end_state",
            "終了状態を静止画でも確認できる具体的な配置・姿勢・物の状態へ変換する必要がある",
            end_state,
        )

    primary_key = _quality_comparison_key(primary)
    for group, value in (
        ("environment_motion", environment),
        ("emotional_change", emotional),
    ):
        if value and primary_key and _quality_comparison_key(value) == primary_key:
            add(
                (
                    "video_motion_duplicate_environment"
                    if group == "environment_motion"
                    else "video_motion_duplicate_emotion"
                ),
                group,
                f"{group}が主動作を重複しており独立した補助情報になっていない",
                value,
            )
    return issues


def _quality_comparison_key(value: str) -> str:
    return re.sub(r"[\s、。,.!！?？;；:：]+", "", str(value or "")).lower()


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_digest_source(value: Any) -> Any:
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, child in value.items():
            item = _normalized_digest_source(child)
            if item not in (None, "", [], {}):
                normalized[str(key)] = item
        return normalized
    if isinstance(value, (list, tuple)):
        return [
            item
            for child in value
            if (item := _normalized_digest_source(child)) not in (None, "", [], {})
        ]
    if isinstance(value, set):
        return sorted(
            (
                item
                for child in value
                if (item := _normalized_digest_source(child)) not in (None, "", [], {})
            ),
            key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True),
        )
    if isinstance(value, str):
        return value.strip()
    return value


def _is_kling(provider: str) -> bool:
    return "kling" in provider.lower()


def _is_seedance(provider: str) -> bool:
    token = re.sub(r"[\s-]+", "_", str(provider or "").strip().lower())
    return token in {
        "seedance",
        "byteplus_seedance",
        "bytedance_seedance",
        "ark_seedance",
        "seadream_video",
        "seedream_video",
        "see_dream",
    }
