"""Compile first-frame design data into a conditional drawable image prompt.

The compiler deliberately accepts a derived ``first_frame_visual_plan`` rather
than a full cut contract.  This keeps motion, event ids, review metadata, and
other authoring fields outside the provider-facing prompt by construction.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from toc.image_prompt_projection_registry import (
    DRAWABLE_PROMPT_GROUP_ORDER,
    normalize_drawable_prompt_text,
    render_projection_value_marker,
)


IMAGE_API_PROMPT_POLICY_VERSION = "image_api_prompt_v2"
IMAGE_PROMPT_COMPILER_VERSION = "conditional_drawable_prompt_compiler_v3"
DRAWABLE_PROMPT_IR_SCHEMA_VERSION = "drawable_prompt_ir_v1"

FRAGMENT_GROUP_ORDER = DRAWABLE_PROMPT_GROUP_ORDER

_OPAQUE_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")

@dataclass(frozen=True)
class DrawablePromptFragment:
    group: str
    text: str

    def as_dict(self) -> dict[str, str]:
        return {"group": self.group, "text": self.text}


@dataclass(frozen=True)
class DrawablePromptDependencies:
    character_ids: tuple[str, ...]
    object_ids: tuple[str, ...]
    location_ids: tuple[str, ...]
    references: tuple[str, ...]
    story_time: str
    time_of_day: str
    required_groups: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "character_ids": list(self.character_ids),
            "object_ids": list(self.object_ids),
            "location_ids": list(self.location_ids),
            "references": list(self.references),
            "required_groups": list(self.required_groups),
        }
        if self.story_time:
            payload["story_time"] = self.story_time
        if self.time_of_day:
            payload["time_of_day"] = self.time_of_day
        return payload


@dataclass(frozen=True)
class DrawablePromptIR:
    dependencies: DrawablePromptDependencies
    included_fragments: tuple[DrawablePromptFragment, ...]
    omitted_groups: tuple[str, ...]
    schema_version: str = DRAWABLE_PROMPT_IR_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dependencies": self.dependencies.as_dict(),
            "included_fragments": [fragment.as_dict() for fragment in self.included_fragments],
            "omitted_groups": list(self.omitted_groups),
        }


def compile_image_api_prompt_v2(
    *,
    first_frame_visual_plan: Mapping[str, Any],
    character_ids: Iterable[str] = (),
    object_ids: Iterable[str] = (),
    location_ids: Iterable[str] = (),
    reference_images: Iterable[str] = (),
    story_time: str = "",
    scene_time_of_day: str = "",
    review_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an ``image_api_prompt_v2`` payload from drawable plan fields only."""

    characters = _dedupe_strings(character_ids)
    objects = _dedupe_strings(object_ids)
    locations = _dedupe_strings(location_ids)
    references = _dedupe_strings(reference_images)
    normalized_story_time = _normalize_contract_string(story_time)
    normalized_scene_time_of_day = _normalize_contract_string(scene_time_of_day)
    ir = build_drawable_prompt_ir(
        first_frame_visual_plan=first_frame_visual_plan,
        character_ids=characters,
        object_ids=objects,
        location_ids=locations,
        reference_images=references,
        story_time=normalized_story_time,
        scene_time_of_day=normalized_scene_time_of_day,
    )
    prompt = render_drawable_prompt(ir)
    reference_text = "\n".join(
        fragment.text for fragment in ir.included_fragments if fragment.group == "references"
    )
    payload: dict[str, Any] = {
        "policy_version": IMAGE_API_PROMPT_POLICY_VERSION,
        "compiler_version": IMAGE_PROMPT_COMPILER_VERSION,
        "source_digest": _source_digest(
            first_frame_visual_plan=first_frame_visual_plan,
            character_ids=characters,
            object_ids=objects,
            location_ids=locations,
            reference_images=references,
            story_time=normalized_story_time,
            scene_time_of_day=normalized_scene_time_of_day,
        ),
        "prompt": prompt,
        "negative_prompt": "画面内テキスト、字幕、ロゴ、ウォーターマーク、アニメ、漫画、イラスト",
        "reference_instructions": reference_text,
        "reference_images": list(references),
        "sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "drawable_prompt_ir": ir.as_dict(),
    }
    for key, value in dict(review_metadata or {}).items():
        if key not in payload:
            payload[key] = value
    return payload


def _source_digest(
    *,
    first_frame_visual_plan: Mapping[str, Any],
    character_ids: tuple[str, ...],
    object_ids: tuple[str, ...],
    location_ids: tuple[str, ...],
    reference_images: tuple[str, ...],
    story_time: str,
    scene_time_of_day: str,
) -> str:
    dependencies: dict[str, Any] = {
        "character_ids": list(character_ids),
        "object_ids": list(object_ids),
        "location_ids": list(location_ids),
        "reference_images": list(reference_images),
    }
    if story_time:
        dependencies["story_time"] = story_time
    if scene_time_of_day:
        dependencies["time_of_day"] = scene_time_of_day
    source = {
        "first_frame_visual_plan": dict(first_frame_visual_plan),
        "dependencies": dependencies,
    }
    canonical = json.dumps(
        source,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_drawable_prompt_ir(
    *,
    first_frame_visual_plan: Mapping[str, Any],
    character_ids: Iterable[str] = (),
    object_ids: Iterable[str] = (),
    location_ids: Iterable[str] = (),
    reference_images: Iterable[str] = (),
    story_time: str = "",
    scene_time_of_day: str = "",
) -> DrawablePromptIR:
    """Extract only the groups that this image can actually draw."""

    plan = _mapping(first_frame_visual_plan)
    characters = _dedupe_strings(character_ids)
    objects = _dedupe_strings(object_ids)
    locations = _dedupe_strings(location_ids)
    references = _dedupe_strings(reference_images)
    normalized_story_time = _normalize_contract_string(story_time)
    normalized_scene_time_of_day = _normalize_contract_string(scene_time_of_day)

    temporal = _mapping(plan.get("temporal_boundary"))
    subjects = _mapping(plan.get("subject_binding"))
    primary_node = _mapping(subjects.get("primary_subject"))
    composition = _mapping(plan.get("spatial_composition"))
    material = _mapping(plan.get("scene_material_pack"))
    progression = _mapping(plan.get("scene_state_progression"))
    visual_evidence = _visual_evidence_values(plan)

    current_moment = _first_drawable_text(
        temporal.get("event_fact_visible_in_still"),
        temporal.get("first_visible_moment"),
        *visual_evidence,
    )
    if not current_moment:
        raise ValueError("drawable_prompt_current_moment_missing")

    primary_subject = _first_drawable_text(primary_node.get("name"), primary_node.get("label"))
    if not primary_subject or primary_subject in {*characters, *objects, *locations}:
        primary_subject = ""

    fragments: list[DrawablePromptFragment] = []
    _append_fragment(fragments, "style", "実写映画調、自然な映画照明、実物セットとして見える質感。")
    if normalized_story_time:
        _append_fragment(
            fragments,
            "story_time",
            f"{render_projection_value_marker('story_time', _sentence_body(normalized_story_time))}。衣装、髪型、建築、生活道具、素材、技術水準をこの時代に整合させる。",
        )
    if normalized_scene_time_of_day:
        _append_fragment(
            fragments,
            "time_of_day",
            f"{render_projection_value_marker('time_of_day', _sentence_body(normalized_scene_time_of_day))}。空の明るさ、自然光と人工光、影、色温度をこの時間帯に整合させる。",
        )

    reference_text = _reference_fragment(
        references,
        plan=plan,
        time_of_day=normalized_scene_time_of_day,
    )
    _append_fragment(fragments, "references", reference_text)
    current_moment_lines = [f"画面には、{_sentence_body(current_moment)}。"]
    structural_evidence = {
        value
        for value in (
            primary_subject,
            *(
                _clean_drawable_text(composition.get(key))
                for key in ("foreground", "midground", "background")
            ),
        )
        if value
    }
    if _clean_drawable_text(material.get("light_source") or material.get("light_direction")):
        structural_evidence.update({"光", "照明", "自然光", "人工光"})
    remaining_evidence = [
        value
        for value in visual_evidence
        if value not in current_moment and current_moment not in value
        and value not in structural_evidence
    ]
    if remaining_evidence:
        current_moment_lines.append(
            "同じ画面に、" + "、".join(remaining_evidence[:8]) + "が明確に見える。"
        )
    _append_fragment(fragments, "current_moment", "\n".join(current_moment_lines))
    if primary_subject:
        _append_fragment(
            fragments,
            "primary_subject",
            f"画面内の主被写体は、{_sentence_body(primary_subject)}。",
        )

    character_text = _character_fragment(plan, characters)
    if characters:
        if not character_text:
            raise ValueError("drawable_prompt_character_state_missing")
        _append_fragment(fragments, "characters", character_text)
    if objects:
        object_text = _object_fragment(plan, current_moment, objects)
        if not object_text:
            raise ValueError("drawable_prompt_object_state_missing")
        _append_fragment(fragments, "objects", object_text)
    if locations:
        location_text = _location_fragment(composition)
        if not location_text:
            raise ValueError("drawable_prompt_location_state_missing")
        _append_fragment(fragments, "location", location_text)

    _append_fragment(fragments, "composition", _composition_fragment(composition))
    _append_fragment(
        fragments,
        "light_material",
        _light_material_fragment(
            material,
            scene_time_of_day=normalized_scene_time_of_day,
        ),
    )
    _append_fragment(fragments, "current_state_delta", _current_state_delta_fragment(progression))

    not_yet = [
        value
        for value in (_clean_drawable_text(item) for item in _list(temporal.get("not_yet_happened_in_still")))
        if value
    ]
    constraint_lines = [
        "画面内テキスト、字幕、ロゴ、ウォーターマーク、アニメ、漫画、イラストを入れない。"
    ]
    if not_yet:
        constraint_lines.append("まだ描かないものは、" + "、".join(not_yet) + "。")
    _append_fragment(fragments, "constraints", "\n".join(constraint_lines))

    dependency_ids = (*characters, *objects, *locations)
    sanitized_fragments: list[DrawablePromptFragment] = []
    for fragment in fragments:
        sanitized_text = _strip_dependency_ids(fragment.text, dependency_ids)
        if sanitized_text:
            sanitized_fragments.append(
                DrawablePromptFragment(group=fragment.group, text=sanitized_text)
            )
    fragments = sanitized_fragments
    _validate_positive_drawable_fragments(fragments)

    included_groups = {fragment.group for fragment in fragments}
    required_groups = [
        group for group in FRAGMENT_GROUP_ORDER if group in included_groups
    ]
    dependencies = DrawablePromptDependencies(
        character_ids=characters,
        object_ids=objects,
        location_ids=locations,
        references=references,
        story_time=normalized_story_time,
        time_of_day=normalized_scene_time_of_day,
        required_groups=tuple(required_groups),
    )
    conditional_groups = {
        "story_time": normalized_story_time,
        "time_of_day": normalized_scene_time_of_day,
    }
    omitted = tuple(
        group
        for group in FRAGMENT_GROUP_ORDER
        if group not in included_groups
        and (group not in conditional_groups or bool(conditional_groups[group]))
    )
    return DrawablePromptIR(
        dependencies=dependencies,
        included_fragments=tuple(fragments),
        omitted_groups=omitted,
    )


def render_drawable_prompt(ir: DrawablePromptIR) -> str:
    by_group = {fragment.group: fragment.text for fragment in ir.included_fragments}
    sections: list[str] = []

    if by_group.get("style"):
        style_lines = [by_group["style"]]
        if by_group.get("story_time"):
            style_lines.append(by_group["story_time"])
        if by_group.get("time_of_day"):
            style_lines.append(by_group["time_of_day"])
        sections.append("[全体 / 不変条件]\n" + "\n".join(style_lines))
    if by_group.get("references"):
        sections.append("[参照画像]\n" + by_group["references"])

    scene_lines = [by_group[group] for group in ("current_moment", "primary_subject") if by_group.get(group)]
    sections.append("[シーン]\n" + "\n".join(scene_lines))

    if by_group.get("characters"):
        sections.append("[登場人物]\n" + by_group["characters"])
    if by_group.get("objects"):
        sections.append("[小道具 / 舞台装置]\n" + by_group["objects"])

    spatial_lines = [by_group[group] for group in ("location", "composition") if by_group.get(group)]
    if spatial_lines:
        sections.append("[場所と構図]\n" + "\n".join(spatial_lines))

    if by_group.get("light_material"):
        sections.append("[光 / 質感]\n" + by_group["light_material"])
    if by_group.get("current_state_delta"):
        sections.append("[現在の状態差分]\n" + by_group["current_state_delta"])
    sections.append("[禁止]\n" + by_group["constraints"])
    return "\n\n".join(sections).strip()


def _character_fragment(
    plan: Mapping[str, Any], character_ids: tuple[str, ...]
) -> str:
    state = _mapping(plan.get("character_state_gate"))
    lines = _bound_character_state_lines(
        state,
        character_ids,
        reference_binding=_mapping(plan.get("reference_binding")),
    )
    labels = (
        ("衣装", "costume_state"),
        ("姿勢", "pose"),
        ("視線", "gaze"),
        ("表情", "expression"),
        ("手元", "hand_position"),
        ("足元", "foot_position"),
        ("身体の状態", "physical_state"),
    )
    for label, key in labels:
        if key == "costume_state" and lines:
            # A named per-character binding is more precise than the legacy
            # unscoped scalar, especially when two or more people share a cut.
            continue
        value = _clean_drawable_text(state.get(key))
        if value:
            lines.append(f"{label}は、{_sentence_body(value)}。")
    return "\n".join(_dedupe_strings(lines))


def _bound_character_state_lines(
    state: Mapping[str, Any],
    character_ids: tuple[str, ...],
    *,
    reference_binding: Mapping[str, Any],
) -> list[str]:
    raw_bindings = state.get("character_states")
    if raw_bindings is None:
        return []
    if not isinstance(raw_bindings, (list, tuple)):
        raise ValueError("drawable_prompt_character_state_bindings_require_sequence")

    visible_ids = set(character_ids)
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    canonical_name_by_id: dict[str, str] = {}
    for raw_reference in _list(reference_binding.get("character_references")):
        if not isinstance(raw_reference, Mapping):
            continue
        reference_id = str(
            raw_reference.get("target_character_id") or ""
        ).strip()
        canonical_name = _clean_drawable_text(
            raw_reference.get("target_identity_name")
            or raw_reference.get("target_character_name")
        )
        if reference_id and canonical_name:
            canonical_name_by_id[reference_id] = canonical_name
    lines: list[str] = []
    for raw_binding in raw_bindings:
        if not isinstance(raw_binding, Mapping):
            raise ValueError("drawable_prompt_character_state_binding_invalid")
        if not isinstance(raw_binding.get("character_id"), str):
            raise ValueError("drawable_prompt_character_state_binding_invalid")
        character_id = raw_binding["character_id"].strip()
        if not character_id or character_id not in visible_ids:
            raise ValueError("drawable_prompt_character_state_binding_unbound")
        if character_id in seen_ids:
            raise ValueError("drawable_prompt_character_state_binding_duplicate")
        seen_ids.add(character_id)

        if not isinstance(raw_binding.get("character_name"), str):
            raise ValueError("drawable_prompt_character_state_binding_invalid")
        character_name = _clean_drawable_text(raw_binding.get("character_name"))
        if character_name in seen_names:
            raise ValueError("drawable_prompt_character_state_binding_identity_conflict")
        seen_names.add(character_name)
        canonical_name = canonical_name_by_id.get(character_id)
        if canonical_name and canonical_name != character_name:
            raise ValueError(
                "drawable_prompt_character_state_binding_identity_mismatch"
            )

        raw_appearance = raw_binding.get("appearance_continuity")
        if not isinstance(raw_appearance, Mapping):
            raise ValueError("drawable_prompt_character_appearance_state_missing")
        appearance = raw_appearance
        if not isinstance(appearance.get("costume_state"), str):
            raise ValueError("drawable_prompt_character_appearance_state_invalid")
        costume_state = _clean_drawable_text(appearance.get("costume_state"))
        raw_forbidden = appearance.get("forbidden_costume_states", [])
        if not isinstance(raw_forbidden, (list, tuple)):
            raise ValueError(
                "drawable_prompt_forbidden_costume_states_require_sequence"
            )
        forbidden_states = [
            _clean_drawable_text(item) for item in raw_forbidden
        ]
        if any(
            not isinstance(item, str) or not item.strip()
            for item in raw_forbidden
        ) or any(not value for value in forbidden_states):
            raise ValueError("drawable_prompt_forbidden_costume_state_invalid")
        if not character_name or not costume_state:
            raise ValueError("drawable_prompt_character_appearance_state_missing")
        if costume_state in forbidden_states:
            raise ValueError("drawable_prompt_character_appearance_state_conflict")

        line = f"{character_name}の衣装は、{_sentence_body(costume_state)}を維持し"
        if forbidden_states:
            line += "、" + "、".join(
                f"{_sentence_body(value)}には変えない" for value in forbidden_states
            )
        else:
            line += "続ける"
        lines.append(line + "。")
    return lines


def _object_fragment(
    plan: Mapping[str, Any], current_moment: str, object_ids: tuple[str, ...]
) -> str:
    gate = _mapping(plan.get("object_visibility_gate"))
    lines: list[str] = []
    for item in _list(gate.get("objects")):
        if not isinstance(item, Mapping):
            continue
        raw_id = str(item.get("object_id") or "").strip()
        name = _first_drawable_text(item.get("object_name"), item.get("name"))
        if name in object_ids or name == raw_id:
            name = ""
        state = _clean_drawable_text(item.get("object_state"))
        meaning = _clean_drawable_text(item.get("story_meaning_in_this_cut"))
        position = _localized_position(item.get("required_screen_position"))
        subject = name or "小道具"
        details = [value for value in (state, meaning) if value and value != current_moment]
        if position:
            details.append(f"{position}に置く")
        if details:
            lines.append(f"{subject}は、" + "。".join(_sentence_body(value) for value in details) + "。")
    return "\n".join(_dedupe_strings(lines))


def _location_fragment(composition: Mapping[str, Any]) -> str:
    layers = []
    for label, key in (("前景", "foreground"), ("中景", "midground"), ("背景", "background")):
        value = _clean_drawable_text(composition.get(key))
        if value:
            layers.append(f"{label}に{_sentence_body(value)}")
    if not layers:
        return ""
    return "場所は、" + "、".join(layers) + "。"


def _composition_fragment(composition: Mapping[str, Any]) -> str:
    lines: list[str] = []
    priority = [
        value
        for value in (_clean_drawable_text(item) for item in _list(composition.get("subject_priority_order")))
        if value
    ]
    if priority:
        lines.append("視線の優先順位は、" + "、次に".join(priority[:3]) + "。")
    shot_size = _localized_shot(composition.get("shot_size"))
    camera = _clean_drawable_text(composition.get("camera_angle") or composition.get("camera_height"))
    if shot_size:
        lines.append(f"画面は{shot_size}。")
    if camera:
        lines.append(f"カメラは{_sentence_body(camera)}。")
    return "\n".join(_dedupe_strings(lines))


def _light_material_fragment(
    material: Mapping[str, Any],
    *,
    scene_time_of_day: str = "",
) -> str:
    _validate_material_time_of_day(
        material,
        scene_time_of_day=scene_time_of_day,
    )
    lines: list[str] = []
    light_source = _clean_drawable_text(material.get("light_source"))
    light_direction = _clean_drawable_text(material.get("light_direction"))
    materials = [
        value
        for value in (_clean_drawable_text(item) for item in _list(material.get("dominant_materials")))
        if value
    ]
    texture = _clean_drawable_text(material.get("story_specific_texture"))
    if light_source:
        lines.append(f"光源は{_sentence_body(light_source)}。")
    if light_direction:
        lines.append(f"光は{_sentence_body(light_direction)}。")
    if materials:
        lines.append("素材は" + "、".join(materials) + "。")
    if texture and texture not in materials:
        lines.append(f"質感は{_sentence_body(texture)}。")
    return "\n".join(_dedupe_strings(lines))


def _current_state_delta_fragment(progression: Mapping[str, Any]) -> str:
    if str(progression.get("progression_mode") or "").strip() != "sequential_state_progression":
        return ""
    state = _clean_drawable_text(
        progression.get("state_visible_in_first_frame") or progression.get("state_visible_in_this_cut")
    )
    delta = _clean_drawable_text(progression.get("visible_state_delta_from_previous_cut"))
    lines = []
    if state:
        lines.append(f"現在の画面では、{_sentence_body(state)}。")
    if delta and delta != state:
        lines.append(f"現在見える変化は、{_sentence_body(delta)}。")
    return "\n".join(lines)


def _reference_fragment(
    references: tuple[str, ...],
    *,
    plan: Mapping[str, Any] | None = None,
    time_of_day: str = "",
) -> str:
    binding = _mapping(_mapping(plan).get("reference_binding"))
    character_names_by_path: dict[str, str] = {}
    for item in _list(binding.get("character_references")):
        if not isinstance(item, Mapping):
            continue
        path = str(item.get("path") or item.get("reference") or "").strip()
        name = _clean_drawable_text(
            item.get("target_character_name") or item.get("character_name")
        )
        if path and name:
            character_names_by_path[path.replace("\\", "/")] = name
    counters: dict[str, int] = {"character": 0, "object": 0, "location": 0, "style": 0, "generic": 0}
    lines: list[str] = []
    for reference in references:
        normalized = reference.replace("\\", "/").lower()
        if "/characters/" in f"/{normalized}":
            kind, label, preserved = "character", "人物参照画像", "顔、髪、体格、衣装の同一性"
        elif "/objects/" in f"/{normalized}":
            kind, label, preserved = "object", "小道具参照画像", "形状、素材、縮尺の同一性"
        elif "/locations/" in f"/{normalized}":
            kind, label, preserved = "location", "場所参照画像", "空間構造、固定素材の同一性"
        elif "/styles/" in f"/{normalized}":
            kind, label, preserved = "style", "スタイル参照画像", "実写の質感と色調"
        else:
            kind, label, preserved = "generic", "参照画像", "写っている対象の同一性"
        counters[kind] += 1
        subject_suffix = ""
        if kind == "character":
            character_name = character_names_by_path.get(reference.replace("\\", "/"), "")
            if character_name:
                subject_suffix = f"（{character_name}）"
        lines.append(
            f"{label}{counters[kind]}{subject_suffix}は{preserved}だけを保ち、構図と状態はこの画像の描写に合わせる。"
            + (
                "光と色温度はこのシーンの時間帯を優先する。"
                if kind == "location" and time_of_day
                else ""
            )
        )
    return "\n".join(lines)


def _validate_material_time_of_day(
    material: Mapping[str, Any],
    *,
    scene_time_of_day: str,
) -> None:
    """Reject explicit positive light markers that oppose the canonical daypart."""

    daypart = str(scene_time_of_day or "").strip()
    if not daypart:
        return
    if "真夜中" in daypart or "深夜" in daypart or daypart == "夜":
        opposing = ("朝日", "真昼", "昼光", "日中", "夕日")
    elif "夕" in daypart or "日没" in daypart:
        opposing = ("朝日", "真昼", "昼光", "真夜中", "深夜")
    elif "昼" in daypart or "日中" in daypart:
        opposing = ("朝日", "夕方", "日没", "夜", "真夜中", "深夜", "月光")
    elif "朝" in daypart:
        opposing = ("朝夕", "夕方", "夕刻", "夕日", "日没", "夜", "真夜中", "深夜", "月光")
    else:
        return
    probe = json.dumps(dict(material), ensure_ascii=False, sort_keys=True)
    for marker in opposing:
        sanitized = re.sub(
            rf"{re.escape(marker)}(?:は|を)?(?:なし|入れない|出さない|使わない)",
            "",
            probe,
        )
        if marker in sanitized:
            raise ValueError(
                f"drawable_prompt_time_of_day_conflict:{daypart}:{marker}"
            )


def _validate_positive_drawable_fragments(
    fragments: Iterable[DrawablePromptFragment],
) -> None:
    positive_groups = {
        "current_moment",
        "primary_subject",
        "characters",
        "objects",
        "location",
        "composition",
        "light_material",
        "current_state_delta",
    }
    text = "\n".join(
        fragment.text for fragment in fragments if fragment.group in positive_groups
    )
    alternative = re.search(r"(?:または|もしくは|いずれか|\bor\b)", text, re.IGNORECASE)
    if alternative:
        context = text[max(0, alternative.start() - 40) : alternative.end() + 40]
        raise ValueError(
            f"drawable_prompt_unresolved_alternative:{alternative.group(0)}:{context}"
        )
    sequential_overview = re.search(r"(?:→|⇒|->|=>)", text)
    if sequential_overview:
        context = text[
            max(0, sequential_overview.start() - 40) : sequential_overview.end() + 40
        ]
        raise ValueError(
            "drawable_prompt_sequential_overview:"
            f"{sequential_overview.group(0)}:{context}"
        )
    abstract_markers = (
        "変化点",
        "変化の証拠",
        "空間の締めつけ",
        "人物の制約",
        "sceneの前提",
        "次cut",
        "内面の変化",
    )
    for marker in abstract_markers:
        if marker in text:
            raise ValueError(f"drawable_prompt_abstract_placeholder:{marker}")


def _visual_evidence_values(plan: Mapping[str, Any]) -> tuple[str, ...]:
    translation = _mapping(plan.get("visual_translation"))
    values: list[str] = []
    for item in _list(translation.get("concrete_visible_evidence")):
        if isinstance(item, Mapping):
            value = _first_drawable_text(
                item.get("must_be_drawn_as"),
                item.get("visible_substitute"),
            )
        else:
            value = _clean_drawable_text(item)
        if value:
            values.append(value)
    return _dedupe_strings(values)


def _append_fragment(
    fragments: list[DrawablePromptFragment], group: str, text: str
) -> None:
    cleaned = text.strip()
    if cleaned:
        fragments.append(DrawablePromptFragment(group=group, text=cleaned))


def _clean_drawable_text(value: Any) -> str:
    return normalize_drawable_prompt_text(value)


def _normalize_contract_string(value: Any) -> str:
    """Trim only the boundary of an authored open-string contract value."""

    return str(value or "").strip()


def _strip_dependency_ids(text: str, dependency_ids: Iterable[str]) -> str:
    cleaned = text
    for dependency_id in sorted(
        (str(value or "").strip() for value in dependency_ids),
        key=len,
        reverse=True,
    ):
        if not dependency_id:
            continue
        if not _OPAQUE_IDENTIFIER_RE.fullmatch(dependency_id):
            continue
        cleaned = re.sub(
            rf"(?<![A-Za-z0-9_]){re.escape(dependency_id)}(?![A-Za-z0-9_])",
            "",
            cleaned,
        )
    cleaned = re.sub(r"、\s*を", "、", cleaned)
    cleaned = re.sub(r"(?m)^\s*を", "", cleaned)
    cleaned = re.sub(r"[ \t]+([、。])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def _first_drawable_text(*values: Any) -> str:
    for value in values:
        cleaned = _clean_drawable_text(value)
        if cleaned:
            return cleaned
    return ""


def _localized_position(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return {
        "foreground": "前景",
        "midground": "中景",
        "background": "背景",
    }.get(raw, _clean_drawable_text(value))


def _localized_shot(value: Any) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return {
        "wide": "広い引き",
        "medium_wide": "やや引いた中広",
        "medium": "中景",
        "medium_closeup": "近めの中景",
        "closeup": "寄り",
        "extreme_closeup": "極端な寄り",
    }.get(raw, _clean_drawable_text(value))


def _sentence_body(value: str) -> str:
    return value.strip().rstrip("。")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    if value is None:
        return []
    return [value]


def _dedupe_strings(values: Iterable[Any]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)
