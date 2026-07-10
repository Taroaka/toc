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


IMAGE_API_PROMPT_POLICY_VERSION = "image_api_prompt_v2"
IMAGE_PROMPT_COMPILER_VERSION = "conditional_drawable_prompt_compiler_v1"
DRAWABLE_PROMPT_IR_SCHEMA_VERSION = "drawable_prompt_ir_v1"

FRAGMENT_GROUP_ORDER = (
    "style",
    "references",
    "current_moment",
    "primary_subject",
    "characters",
    "objects",
    "location",
    "composition",
    "light_material",
    "current_state_delta",
    "constraints",
)

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
_OPAQUE_IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_WHITESPACE_RE = re.compile(r"\s+")
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
    required_groups: tuple[str, ...]

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "character_ids": list(self.character_ids),
            "object_ids": list(self.object_ids),
            "location_ids": list(self.location_ids),
            "references": list(self.references),
            "required_groups": list(self.required_groups),
        }


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
    review_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an ``image_api_prompt_v2`` payload from drawable plan fields only."""

    characters = _dedupe_strings(character_ids)
    objects = _dedupe_strings(object_ids)
    locations = _dedupe_strings(location_ids)
    references = _dedupe_strings(reference_images)
    ir = build_drawable_prompt_ir(
        first_frame_visual_plan=first_frame_visual_plan,
        character_ids=characters,
        object_ids=objects,
        location_ids=locations,
        reference_images=references,
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
) -> str:
    source = {
        "first_frame_visual_plan": dict(first_frame_visual_plan),
        "dependencies": {
            "character_ids": list(character_ids),
            "object_ids": list(object_ids),
            "location_ids": list(location_ids),
            "reference_images": list(reference_images),
        },
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
) -> DrawablePromptIR:
    """Extract only the groups that this image can actually draw."""

    plan = _mapping(first_frame_visual_plan)
    characters = _dedupe_strings(character_ids)
    objects = _dedupe_strings(object_ids)
    locations = _dedupe_strings(location_ids)
    references = _dedupe_strings(reference_images)

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

    reference_text = _reference_fragment(references)
    _append_fragment(fragments, "references", reference_text)
    current_moment_lines = [f"画面には、{_sentence_body(current_moment)}。"]
    remaining_evidence = [
        value
        for value in visual_evidence
        if value not in current_moment and current_moment not in value
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
            f"観客が最初に読む主被写体は、{_sentence_body(primary_subject)}。",
        )

    if characters:
        character_text = _character_fragment(plan)
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
    _append_fragment(fragments, "light_material", _light_material_fragment(material))
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

    included_groups = {fragment.group for fragment in fragments}
    required_groups = [
        group for group in FRAGMENT_GROUP_ORDER if group in included_groups
    ]
    dependencies = DrawablePromptDependencies(
        character_ids=characters,
        object_ids=objects,
        location_ids=locations,
        references=references,
        required_groups=tuple(required_groups),
    )
    omitted = tuple(group for group in FRAGMENT_GROUP_ORDER if group not in included_groups)
    return DrawablePromptIR(
        dependencies=dependencies,
        included_fragments=tuple(fragments),
        omitted_groups=omitted,
    )


def render_drawable_prompt(ir: DrawablePromptIR) -> str:
    by_group = {fragment.group: fragment.text for fragment in ir.included_fragments}
    sections: list[str] = []

    if by_group.get("style"):
        sections.append("[全体 / 不変条件]\n" + by_group["style"])
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


def _character_fragment(plan: Mapping[str, Any]) -> str:
    state = _mapping(plan.get("character_state_gate"))
    labels = (
        ("衣装", "costume_state"),
        ("姿勢", "pose"),
        ("視線", "gaze"),
        ("表情", "expression"),
        ("手元", "hand_position"),
        ("足元", "foot_position"),
        ("身体の状態", "physical_state"),
    )
    lines = []
    for label, key in labels:
        value = _clean_drawable_text(state.get(key))
        if value:
            lines.append(f"{label}は、{_sentence_body(value)}。")
    return "\n".join(_dedupe_strings(lines))


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


def _light_material_fragment(material: Mapping[str, Any]) -> str:
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


def _reference_fragment(references: tuple[str, ...]) -> str:
    counters: dict[str, int] = {"character": 0, "object": 0, "location": 0, "style": 0, "generic": 0}
    lines: list[str] = []
    for reference in references:
        normalized = reference.replace("\\", "/").lower()
        if "/characters/" in f"/{normalized}":
            kind, label, preserved = "character", "人物参照画像", "顔、髪、体格、衣装の同一性"
        elif "/objects/" in f"/{normalized}":
            kind, label, preserved = "object", "小道具参照画像", "形状、素材、縮尺の同一性"
        elif "/locations/" in f"/{normalized}":
            kind, label, preserved = "location", "場所参照画像", "空間構造、素材、光の同一性"
        elif "/styles/" in f"/{normalized}":
            kind, label, preserved = "style", "スタイル参照画像", "実写の質感と色調"
        else:
            kind, label, preserved = "generic", "参照画像", "写っている対象の同一性"
        counters[kind] += 1
        lines.append(
            f"{label}{counters[kind]}は{preserved}だけを保ち、構図と状態はこの画像の描写に合わせる。"
        )
    return "\n".join(lines)


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
    text = _WHITESPACE_RE.sub(" ", str(value or "")).strip(" 、。:：/\n\t")
    if not text:
        return ""
    if _INTERNAL_META_RE.search(text):
        return ""
    if _ABSTRACT_STORY_RE.search(text):
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
