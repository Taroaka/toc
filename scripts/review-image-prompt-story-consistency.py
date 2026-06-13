#!/usr/bin/env python3
"""Review prompt collections for story/script consistency before image generation."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, extract_yaml_block, load_structured_document  # noqa: E402
from toc.immersive_manifest import normalize_dotted_id  # noqa: E402
from toc.reveal_constraints import (  # noqa: E402
    RevealConstraint,
    build_manifest_cut_order_map,
    find_reveal_violations_for_surface,
    load_reveal_constraints,
    parse_selector,
)


PROMPT_ENTRY_RE = re.compile(
    r"^##\s+scene(?P<scene_id>\d+(?:\.\d+)?)_cut(?P<cut_id>\d+(?:\.\d+)?)\n"
    r"(?P<body>.*?)(?=^##\s+scene\d+(?:\.\d+)?_cut\d+(?:\.\d+)?\n|\Z)",
    re.M | re.S,
)
TEXT_BLOCK_RE = re.compile(r"```text\n(?P<prompt>.*?)\n```", re.S)
API_PROMPT_BLOCK_RE = re.compile(r"```api_prompt\n(?P<prompt>.*?)\n```", re.S)
IMAGE_API_PROMPT_POLICY_VERSION = "image_api_prompt_v1"
JP_TOKEN_RE = re.compile(r"[一-龯]{1,8}|[ァ-ヶー]{2,16}")

IMPORTANT_SINGLE_KANJI = {
    "亀",
    "海",
    "浜",
    "村",
    "門",
    "箱",
    "島",
    "姫",
    "鬼",
    "城",
    "煙",
    "桃",
    "翁",
    "帝",
}

EN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")

STOPWORDS = {
    "全体",
    "不変条件",
    "登場人物",
    "小道具",
    "舞台装置",
    "シーン",
    "連続性",
    "禁止",
    "構図",
    "カメラ",
    "画面",
    "前景",
    "中景",
    "背景",
    "遠景",
    "自然",
    "映画",
    "映画照明",
    "実写",
    "実物",
    "セット",
    "実物セット感",
    "シネマティック",
    "テキスト",
    "字幕",
    "ウォーターマーク",
    "ロゴ",
    "アニメ",
    "漫画",
    "イラスト",
    "パース",
    "破綻",
    "指",
    "手",
    "崩れ",
    "増殖",
    "シーン設計",
    "カット",
    "物語",
    "場面",
}

REVIEW_SKIP_KEYS = {
    "scene_id",
    "cut_id",
    "research_refs",
    "source_ids",
    "fact_ids",
    "items",
    "facts",
    "assets",
    "output",
    "output_path",
    "reference_images",
    "references",
    "timestamp",
    "tool",
    "image_generation",
    "video_generation",
    "audio",
    "selection",
    "score_hint",
    "metadata",
    "conflicts",
    "sources",
}

REQUIRED_PROMPT_BLOCKS = [
    "REFERENCE_USAGE",
    "CUT_START_STATE",
    "SINGLE_MOMENT_RULE",
    "MUST_INCLUDE",
    "MUST_NOT_INCLUDE",
    "CHARACTER_STATE",
    "PROPS_SETPIECES",
    "COMPOSITION",
    "LIGHT_MATERIAL",
    "MOTION_START_AFFORDANCE",
    "AVOID",
]

PROMPT_BLOCK_ALIASES = {
    "REFERENCE_USAGE": ["参照画像の使い方", "REFERENCE USAGE"],
    "CUT_START_STATE": ["このcutの開始状態", "このカットの開始状態", "CUT START STATE"],
    "SINGLE_MOMENT_RULE": ["単一瞬間ルール", "SINGLE MOMENT RULE"],
    "MUST_INCLUDE": ["画面に必ず見えるもの", "MUST INCLUDE"],
    "MUST_NOT_INCLUDE": ["画面に入れてはいけないもの", "MUST NOT INCLUDE"],
    "CHARACTER_STATE": ["人物状態", "CHARACTER STATE"],
    "PROPS_SETPIECES": ["小道具 / 舞台装置", "小道具/舞台装置", "PROPS / SETPIECES"],
    "COMPOSITION": ["構図", "COMPOSITION"],
    "LIGHT_MATERIAL": ["光 / 質感", "光/質感", "LIGHT / MATERIAL"],
    "MOTION_START_AFFORDANCE": ["動画化のための開始余地", "MOTION START AFFORDANCE"],
    "AVOID": ["禁止", "AVOID"],
}

PROMPT_BLOCK_LABELS = {
    "REFERENCE_USAGE": "参照画像の使い方",
    "CUT_START_STATE": "このcutの開始状態",
    "SINGLE_MOMENT_RULE": "単一瞬間ルール",
    "MUST_INCLUDE": "画面に必ず見えるもの",
    "MUST_NOT_INCLUDE": "画面に入れてはいけないもの",
    "CHARACTER_STATE": "人物状態",
    "PROPS_SETPIECES": "小道具 / 舞台装置",
    "COMPOSITION": "構図",
    "LIGHT_MATERIAL": "光 / 質感",
    "MOTION_START_AFFORDANCE": "動画化のための開始余地",
    "AVOID": "禁止",
}

PROMPT_SELF_CONTAINED_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"scene\d+(?:_cut\d+)?", re.I), "prompt references another scene/cut directly."),
    (re.compile(r"前カット|次カット|前scene|次scene|前シーン|次シーン|前の\s*cut|次の\s*cut|前のシーン|次のシーン|前回の?プロンプト|前のprompt|次のprompt", re.I), "prompt depends on another shot or prompt instead of being self-contained."),
    (re.compile(r"rideable", re.I), "prompt uses English term `rideable`; use Japanese such as `騎乗可能` instead."),
)

PROMPT_NONVISUAL_METADATA_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\[物語の文脈\]"),
        "prompt contains a review-only context heading; replace it with concrete visual subject wording.",
    ),
    (
        re.compile(r"この画像は物語「[^」]+」(?:の一場面(?:を視覚化する)?|に出てくる場所を表す)"),
        "prompt describes the request as a story artifact instead of naming the concrete visual subject.",
    ),
    (
        re.compile(r"物語「[^」]+」の\s*scene\d+(?:[_\s-]*cut\d+)?", re.I),
        "prompt uses story title plus internal scene id; use concrete wording such as `シンデレラの灰の台所`.",
    ),
    (
        re.compile(r"(?<![A-Za-z0-9_/.-])scene\d+(?:[_-]cut\d+)?(?![A-Za-z0-9_/.-])", re.I),
        "prompt uses an internal scene/cut selector; replace it with the visible place, subject, or action.",
    ),
)

PROMPT_FIRST_FRAME_METADATA_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"最初の\s*1\s*フレーム|1\s*フレーム目|冒頭フレーム|first\s*frame", re.I),
        "prompt contains first-frame authoring metadata. Keep that in review/authoring context, and describe the visible initial state instead.",
    ),
    (
        re.compile(r"動画(?:の)?(?:開始|冒頭).{0,12}フレーム"),
        "prompt describes its production role for video instead of the concrete visible image.",
    ),
)

PROMPT_DESIGN_META_LEAK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\[cut契約からの可視要件\]|場面の核:|画面上の問い:|観客理解の増分:|因果の証明:|映像で成立させる証拠:|必要な役割:"),
        "prompt leaks cut/review design metadata; use concrete visible subjects, blocking, objects, composition, light, and material instead.",
    ),
)

PROMPT_ABSTRACT_STORY_TERMS = (
    "価値変化",
    "場所の圧力",
    "場のルール",
    "証明",
    "結果を渡す",
    "観客理解",
    "因果",
    "主人公の制限",
    "変化の兆し",
)

PROMPT_MOTION_BRIEF_LEAK_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"motion[_\s-]*brief|モーション\s*ブリーフ|p800\s*(?:motion|動画|専用)", re.I),
        "prompt contains motion_brief / p800 authoring metadata. Image prompts must use only the visible initial state.",
    ),
    (
        re.compile(r"このあと|その後|次に(?:は)?|続いて|やがて"),
        "prompt describes future motion after the still. Keep future action in p800 motion prompt, not p600 image prompt.",
    ),
)

IMAGE_REVIEW_RUBRIC_WEIGHTS = {
    "story_alignment": 0.25,
    "subject_specificity": 0.20,
    "prompt_craft": 0.15,
    "continuity_readiness": 0.15,
    "first_frame_readiness": 0.15,
    "production_readiness": 0.10,
}

IMAGE_REVIEW_RUBRIC_THRESHOLDS = {
    "story_alignment": 0.60,
    "subject_specificity": 0.60,
    "prompt_craft": 0.65,
    "continuity_readiness": 0.60,
    "first_frame_readiness": 0.60,
    "production_readiness": 0.60,
}

PROMPT_CRAFT_MIN_CHARS = 220
PROMPT_CRAFT_MIN_VISUAL_CATEGORIES = 4
PROMPT_CRAFT_VISUAL_CATEGORIES = {
    "subject": ("人物", "主人公", "顔", "表情", "視線", "手", "姿勢", "立ち姿"),
    "blocking": ("前景", "中景", "背景", "距離", "向き", "手前", "奥", "横", "斜め", "並ぶ", "向き合う"),
    "setting": ("部屋", "道", "森", "海", "城", "台所", "庭", "階段", "床", "壁", "窓", "扉", "空"),
    "light": ("光", "影", "逆光", "月明かり", "朝日", "夕暮れ", "薄暗", "反射", "陰影"),
    "camera": ("構図", "クローズアップ", "広角", "俯瞰", "ローアングル", "焦点", "被写界深度", "フレーム"),
    "material": ("質感", "布", "木", "石", "金属", "ガラス", "埃", "灰", "水滴", "しわ", "擦り傷"),
}

MID_ACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"話し、"),
    re.compile(r"うなずく"),
    re.compile(r"叩く"),
    re.compile(r"渡す"),
    re.compile(r"差し出す"),
    re.compile(r"受け取る"),
    re.compile(r"泳ぎだす"),
    re.compile(r"歩いていく"),
    re.compile(r"開けます"),
    re.compile(r"あふれ出します"),
)

FIRST_FRAME_SAFE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"動き出す直前"),
    re.compile(r"初期姿勢"),
    re.compile(r"ふと"),
    re.compile(r"視線"),
    re.compile(r"立ち止まる"),
    re.compile(r"構える"),
    re.compile(r"〜しようとする"),
    re.compile(r"しかけ"),
    re.compile(r"前に"),
)

IMAGE_TARGET_FOCUS_TERMS = {
    "character": ("人物", "主人公", "表情", "顔", "視線", "立ち姿", "しぐさ"),
    "relationship": ("向き合う", "見つめる", "距離感", "やり取り", "手渡す", "支える", "並ぶ"),
    "setpiece": ("小道具", "舞台装置", "象徴", "鍵", "乗り物", "玉手箱", "道具"),
    "blocking": ("動き", "導線", "姿勢", "またがる", "歩く", "振り向く", "差し出す", "進む"),
    "environment": ("背景", "風景", "空気感", "地形", "建築", "天候", "海", "森"),
}

SOFT_FINDING_CODES = {
    "image_contract_must_avoid_violated",
    "image_contract_target_focus_unmet",
    "prompt_only_local_mismatch",
    "non_japanese_prompt_term",
    "image_prompt_story_alignment_weak",
    "image_prompt_subject_specificity_weak",
    "image_prompt_continuity_weak",
    "image_prompt_first_frame_readiness_weak",
    "image_prompt_prompt_craft_weak",
    "image_prompt_production_readiness_weak",
}

HARD_FINDING_CODES = {
    "image_contract_missing",
    "image_contract_must_include_unmet",
    "missing_required_prompt_block",
    "prompt_not_self_contained",
    "prompt_contains_nonvisual_metadata",
    "prompt_contains_first_frame_metadata",
    "prompt_leaks_motion_brief",
    "prompt_mentions_character_but_character_ids_empty",
    "missing_character_id",
    "missing_object_id",
    "prompt_missing_expected_character_anchor",
    "prompt_missing_expected_object_anchor",
    "prompt_subject_drift",
    "source_anchor_missing_from_prompt",
    "blocking_drift",
    "script_reveal_constraint_violated",
    "image_prompt_not_first_frame_ready",
}


def is_soft_finding(finding: Finding) -> bool:
    return finding.code in SOFT_FINDING_CODES


def is_hard_finding(finding: Finding) -> bool:
    return finding.code not in SOFT_FINDING_CODES or finding.code in HARD_FINDING_CODES


def _selector_label(scene_id: Any, cut_id: Any) -> str:
    scene = str(normalize_dotted_id(scene_id) or "unknown")
    cut = str(normalize_dotted_id(cut_id) or "unknown")
    scene_label = f"{int(scene):02d}" if re.fullmatch(r"\d+", scene) else scene
    cut_label = f"{int(cut):02d}" if re.fullmatch(r"\d+", cut) else cut
    return f"scene{scene_label}_cut{cut_label}"


@dataclass
class PromptEntry:
    scene_id: str
    cut_id: str
    output: str
    narration: str
    rationale: str
    agent_review_ok: bool
    human_review_ok: bool
    human_review_reason: str
    agent_review_reason_keys: list[str]
    agent_review_reason_messages: list[str]
    rubric_scores: dict[str, float]
    overall_score: float
    contract: dict[str, Any]
    prompt: str
    prompt_policy_version: str | None = None
    legacy_prompt: str = ""


@dataclass
class Finding:
    code: str
    message: str


@dataclass
class ReviewOutcome:
    entry: PromptEntry
    findings: list[Finding]
    suggested_character_ids: list[str]
    suggested_object_ids: list[str]
    rubric_scores: dict[str, float]
    overall_score: float


def parse_prompt_collection(text: str) -> list[PromptEntry]:
    entries: list[PromptEntry] = []
    for match in PROMPT_ENTRY_RE.finditer(text):
        body = match.group("body")
        api_prompt_match = API_PROMPT_BLOCK_RE.search(body)
        text_prompt_match = TEXT_BLOCK_RE.search(body)
        prompt_policy_version = _extract_backtick_bullet(body, "prompt_policy_version") or _extract_backtick_bullet(body, "policy_version")
        prompt = ""
        legacy_prompt = ""
        if api_prompt_match:
            prompt = api_prompt_match.group("prompt").strip()
        if text_prompt_match:
            legacy_prompt = text_prompt_match.group("prompt").strip()
            if not prompt and prompt_policy_version != IMAGE_API_PROMPT_POLICY_VERSION:
                prompt = legacy_prompt
        output = _extract_backtick_bullet(body, "output")
        narration = _extract_backtick_bullet(body, "narration")
        rationale = _extract_backtick_bullet(body, "rationale")
        entries.append(
            PromptEntry(
                scene_id=str(normalize_dotted_id(match.group("scene_id")) or match.group("scene_id")),
                cut_id=str(normalize_dotted_id(match.group("cut_id")) or match.group("cut_id")),
                output=output,
                narration="" if narration == "(silent)" else narration,
                rationale=rationale,
                agent_review_ok=_extract_bool_bullet(body, "agent_review_ok", True),
                human_review_ok=_extract_bool_bullet(body, "human_review_ok", False),
                human_review_reason=_extract_backtick_bullet(body, "human_review_reason"),
                agent_review_reason_keys=_extract_reason_keys(body),
                agent_review_reason_messages=_extract_reason_messages(body),
                rubric_scores={},
                overall_score=0.0,
                contract={},
                prompt=prompt,
                prompt_policy_version=prompt_policy_version or None,
                legacy_prompt=legacy_prompt,
            )
        )
    return entries


def _extract_backtick_bullet(body: str, key: str) -> str:
    match = re.search(rf"^- {re.escape(key)}:\s+`(?P<value>.*)`\s*$", body, re.M)
    return match.group("value") if match else ""


def _extract_bool_bullet(body: str, key: str, default: bool) -> bool:
    match = re.search(rf"^- {re.escape(key)}:\s+`(?P<value>true|false)`\s*$", body, re.M)
    if not match:
        return default
    return match.group("value") == "true"


def _extract_reason_keys(body: str) -> list[str]:
    raw = _extract_backtick_bullet(body, "agent_review_reason_keys").strip()
    if not raw:
        raw = _extract_backtick_bullet(body, "agent_review_reason_codes").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _extract_reason_messages(body: str) -> list[str]:
    match = re.search(
        r"^- agent_review_reason_messages:\s*\n(?P<items>(?:  - `.*?`\n?)*)",
        body,
        re.M | re.S,
    )
    if match:
        items = re.findall(r"^  - `(?P<value>.*)`\s*$", match.group("items"), re.M)
        if items != [""]:
            return [item for item in items if item]
    legacy_summary = _extract_backtick_bullet(body, "agent_review_reason_summary").strip()
    return [legacy_summary] if legacy_summary else []


def load_manifest(path: Path) -> dict[str, Any]:
    text, data = load_structured_document(path)
    if not data:
        raise SystemExit(f"Failed to parse structured manifest: {path}")
    return data


def _normalize_heading_label(label: str) -> str:
    normalized = re.sub(r"\s+", " ", label.strip())
    normalized = re.sub(r"\s*/\s*", " / ", normalized)
    return normalized.upper()


def detect_prompt_blocks(prompt: str) -> set[str]:
    normalized_aliases = {
        canonical: {_normalize_heading_label(alias) for alias in aliases}
        for canonical, aliases in PROMPT_BLOCK_ALIASES.items()
    }
    detected: set[str] = set()
    for raw_line in prompt.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        bracket_match = re.fullmatch(r"\[(?P<label>.+?)\]", line)
        if bracket_match:
            line = bracket_match.group("label").strip()
        elif line.endswith(":"):
            line = line[:-1].strip()
        normalized = _normalize_heading_label(line)
        for canonical, aliases in normalized_aliases.items():
            if normalized in aliases:
                detected.add(canonical)
                break
    return detected


def missing_required_prompt_blocks(prompt: str) -> list[str]:
    present = detect_prompt_blocks(prompt)
    return [PROMPT_BLOCK_LABELS[block] for block in REQUIRED_PROMPT_BLOCKS if block not in present]


def prompt_block_sections(prompt: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    normalized_aliases = {
        _normalize_heading_label(alias): canonical
        for canonical, aliases in PROMPT_BLOCK_ALIASES.items()
        for alias in aliases
    }
    for raw_line in (prompt or "").splitlines():
        line = raw_line.strip()
        bracket_match = re.fullmatch(r"\[(?P<label>.+?)\]", line)
        if bracket_match:
            current = normalized_aliases.get(_normalize_heading_label(bracket_match.group("label")))
            if current:
                sections.setdefault(current, [])
            continue
        if current:
            sections.setdefault(current, []).append(raw_line)
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def prompt_drawable_content(prompt: str) -> str:
    sections = prompt_block_sections(prompt)
    if not sections:
        return prompt or ""
    excluded = {"MUST_NOT_INCLUDE", "AVOID"}
    return "\n".join(body for key, body in sections.items() if key not in excluded)


def prompt_structural_contract_issues(prompt: str) -> list[Finding]:
    sections = prompt_block_sections(prompt)
    findings: list[Finding] = []
    start_state = sections.get("CUT_START_STATE", "")
    if start_state and "event_time_position" not in start_state:
        findings.append(Finding(code="image_prompt_action_window_missing", message="start-state block must include `event_time_position`."))
    if start_state and "not_yet_happened_in_still" not in start_state:
        findings.append(Finding(code="image_prompt_missing_not_yet_state", message="start-state block must include `not_yet_happened_in_still`."))
    if start_state and "action_completion_state" not in start_state:
        findings.append(Finding(code="image_prompt_action_completion_state_missing", message="start-state block must include `action_completion_state`."))
    if start_state and not any(key in start_state for key in ("event_fact_visible_in_still", "visible_action", "visible_reaction")):
        findings.append(Finding(code="image_prompt_start_state_not_drawable", message="start-state block must name a drawable visible action, reaction, or still fact."))
    not_yet_match = re.search(r"not_yet_happened_in_still\s*:\s*(?P<body>.+)", start_state)
    if not_yet_match:
        not_yet_body = not_yet_match.group("body").strip()
        if len(not_yet_body) < 18 or re.fullmatch(r"(次へ進んでいない|まだ起きていない|未完了|なし)[。.]?", not_yet_body):
            findings.append(Finding(code="image_prompt_not_yet_state_too_generic", message="not-yet state must name the specific event, reveal, or outcome not yet visible."))
    single_moment = sections.get("SINGLE_MOMENT_RULE", "")
    if single_moment and not any(term in single_moment for term in ("1つの瞬間", "単一", "モンタージュにしない", "混ぜない")):
        findings.append(Finding(code="image_prompt_time_mixed", message="single-moment block must forbid mixed time or montage."))
    if single_moment and not any(term in single_moment for term in ("visible_moment", "must_not_mix")):
        findings.append(Finding(code="image_prompt_overpacked_visual_intent", message="single-moment block must declare visible_moment or must_not_mix so one still does not pack multiple beats."))
    must_include = sections.get("MUST_INCLUDE", "")
    if must_include and "primary_visual_anchor" not in must_include:
        findings.append(Finding(code="image_prompt_primary_visual_anchor_missing", message="must-include block must identify `primary_visual_anchor`."))
    if must_include and not any(term in must_include for term in ("required_story_evidence", "secondary_visual_anchors", "location_anchor")):
        findings.append(Finding(code="image_prompt_visual_translation_missing", message="must-include block must convert story meaning into concrete visual anchors or evidence."))
    must_not = sections.get("MUST_NOT_INCLUDE", "")
    if must_include and must_not:
        include_tokens = {
            token.strip()
            for token in re.split(r"[/、,。\n]", must_include)
            if len(token.strip()) >= 3 and ":" not in token
        }
        conflict_tokens = [token for token in include_tokens if token and token in must_not]
        if conflict_tokens:
            findings.append(Finding(code="image_prompt_object_visibility_conflict", message="must-include and must-not blocks appear to conflict: " + ", ".join(conflict_tokens[:5]) + "."))
    composition = sections.get("COMPOSITION", "")
    if composition and not all(term in composition for term in ("foreground", "midground", "background")):
        findings.append(Finding(code="image_prompt_camera_composition_weak", message="composition block must describe foreground, midground, and background."))
    if composition and "subject_priority" not in composition:
        findings.append(Finding(code="image_prompt_subject_priority_missing", message="composition block must declare subject_priority."))
    if composition and "frame_edge_handoff" not in composition:
        findings.append(Finding(code="image_prompt_frame_edge_handoff_missing", message="composition block should describe frame_edge_handoff or motion handoff space."))
    light_material = sections.get("LIGHT_MATERIAL", "")
    if light_material and not any(term in light_material for term in ("light_source", "dominant_materials", "質感", "光")):
        findings.append(Finding(code="image_prompt_scene_material_pack_missing", message="light/material block must describe cut-specific light or materials."))
    if light_material and not any(term in light_material for term in ("floor_or_ground_texture", "scene_specific_texture", "story_specific_texture", "dominant_materials")):
        findings.append(Finding(code="image_prompt_scene_material_too_generic", message="light/material block must include scene-specific texture or material fields."))
    character_state = sections.get("CHARACTER_STATE", "")
    if character_state and not any(term in character_state for term in ("costume_state", "pose", "gaze", "expression", "emotional_state")):
        findings.append(Finding(code="image_prompt_character_state_gate_missing", message="character-state block must describe costume, pose, gaze, expression, or emotion."))
    if character_state and not all(term in character_state for term in ("pose", "gaze")) and not any(term in character_state for term in ("hand_position", "foot_position")):
        findings.append(Finding(code="image_prompt_character_pose_too_generic", message="character-state block must specify pose/gaze or hand/foot position, not only generic presence."))
    props = sections.get("PROPS_SETPIECES", "")
    if props and not any(term in props for term in ("visibility", "object_state", "hidden", "hinted", "partially_visible", "clearly_visible", "hero_object")):
        findings.append(Finding(code="image_prompt_object_visibility_missing", message="props/setpieces block must describe object state or visibility boundary."))
    references = sections.get("REFERENCE_USAGE", "")
    if references and "参照" in references and not any(term in references for term in ("人物参照", "場所参照", "小道具参照", "対象", "維持")):
        findings.append(Finding(code="image_prompt_reference_usage_missing", message="reference-usage block must describe what references preserve or target."))
    motion = sections.get("MOTION_START_AFFORDANCE", "")
    if motion and not all(term in motion for term in ("movable_subject", "movement_vector")):
        findings.append(Finding(code="image_prompt_motion_affordance_weak", message="motion-start block must name movable_subject and movement_vector."))
    if motion and "motion_ceiling" not in motion:
        findings.append(Finding(code="image_prompt_motion_ceiling_missing", message="motion-start block must include motion_ceiling or must-not-complete outcomes."))
    drawable = prompt_drawable_content(prompt)
    abstract_hits = [term for term in PROMPT_ABSTRACT_STORY_TERMS if term in drawable]
    if abstract_hits:
        findings.append(Finding(code="image_prompt_visual_translation_missing", message="prompt still contains abstract story terms instead of visible evidence: " + ", ".join(abstract_hits[:6]) + "."))
    return findings


API_PROMPT_FORBIDDEN_GATES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("api_prompt_contains_no_scene_event_ids", re.compile(r"\bscene\d+_event_[A-Za-z0-9_]+\b|\b_event_[A-Za-z0-9_]+\b", re.I)),
    (
        "api_prompt_contains_no_yaml_field_names",
        re.compile(
            r"first_frame_visual_plan|cut_contract|scene_event|source_event_contract|event_context_for_cut|validation_gates|"
            r"source_event_beat_id|event_time_position|what_happens|visible_action|motion_brief|debug_prompt_source|api_prompt_payload",
            re.I,
        ),
    ),
    ("api_prompt_contains_no_boolean_gate_values", re.compile(r"\b(?:true|false|null|none)\b", re.I)),
    ("api_prompt_contains_no_legacy_additional_description", re.compile(r"追加の具体描写|追加具体描写")),
    ("api_prompt_contains_no_abstract_story_terms", re.compile(r"場面の核|観客理解|因果の証明|価値変化|場所の圧力|場のルール|主人公の制限")),
    ("api_prompt_contains_no_unresolved_generic_placeholders", re.compile(r"\b(?:TODO|TBD|placeholder|approved_story_evidence|primary_visible_object|primary_visible_zone)\b", re.I)),
)
API_PROMPT_ABSTRACT_TERM_RE = re.compile(r"場面の核|観客理解|因果の証明|価値変化|場所の圧力|場のルール|主人公の制限")


def api_prompt_structural_contract_issues(prompt: str, *, object_present: bool) -> list[Finding]:
    findings: list[Finding] = []
    if not prompt.strip():
        return [Finding(code="api_prompt_missing_for_new_prompt_policy", message="image_api_prompt_v1 requires ```api_prompt or image_generation.api_prompt_payload.prompt.")]
    for code, pattern in API_PROMPT_FORBIDDEN_GATES:
        if pattern.search(prompt):
            findings.append(Finding(code=code, message=f"API prompt violates v1 gate `{code}`."))
    required = {
        "api_prompt_has_shot_role": "shot_role:",
        "api_prompt_has_location_zone": "location_zone:",
        "api_prompt_has_previous_cut_delta": "this_cut_delta:",
        "api_prompt_has_character_blocking": "hand_position:",
    }
    for code, needle in required.items():
        if needle not in prompt:
            findings.append(Finding(code=code, message=f"API prompt is missing required drawable field `{needle}`."))
    if object_present and "object_contact_state:" not in prompt:
        findings.append(
            Finding(
                code="api_prompt_has_object_contact_state_if_object_present",
                message="API prompt must describe object_contact_state when image_generation.object_ids is non-empty.",
            )
        )
    return findings


def find_prompt_independence_issues(prompt: str) -> list[str]:
    checked_prompt = "\n".join(
        raw
        for raw in (prompt or "").splitlines()
        if not raw.strip().startswith(("source_event_beat_id:", "forbidden_future_event_beat_ids:"))
    )
    issues: list[str] = []
    for pattern, message in PROMPT_SELF_CONTAINED_PATTERNS:
        if pattern.search(checked_prompt):
            issues.append(message)
    return issues


def find_prompt_nonvisual_metadata_issues(prompt: str) -> list[str]:
    issues: list[str] = []
    for pattern, message in PROMPT_NONVISUAL_METADATA_PATTERNS:
        if pattern.search(prompt or ""):
            issues.append(message)
    return issues


def find_prompt_design_meta_leak_issues(prompt: str) -> list[str]:
    issues: list[str] = []
    for pattern, message in PROMPT_DESIGN_META_LEAK_PATTERNS:
        if pattern.search(prompt):
            issues.append(message)
    return issues


def find_prompt_first_frame_metadata_issues(prompt: str) -> list[str]:
    issues: list[str] = []
    for pattern, message in PROMPT_FIRST_FRAME_METADATA_PATTERNS:
        if pattern.search(prompt or ""):
            issues.append(message)
    return issues


def find_prompt_motion_brief_leak_issues(prompt: str) -> list[str]:
    issues: list[str] = []
    for pattern, message in PROMPT_MOTION_BRIEF_LEAK_PATTERNS:
        if pattern.search(prompt or ""):
            issues.append(message)
    return issues


def extract_scene_context_map(data: dict[str, Any]) -> dict[str, str]:
    context: dict[str, str] = {}
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        scenes = ((data.get("script") or {}).get("scenes") if isinstance(data.get("script"), dict) else None)
    if not isinstance(scenes, list):
        return context
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        sid = normalize_dotted_id(scene.get("scene_id"))
        if not sid:
            continue
        context[sid] = flatten_scene_text(scene)
    return context


def flatten_scene_text(value: Any, parent_key: str = "") -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = []
        for key, child in value.items():
            if key in REVIEW_SKIP_KEYS or key.endswith("_ids") or key.endswith("_refs") or key.endswith("_path"):
                continue
            parts.append(flatten_scene_text(child, str(key)))
        return "\n".join(part for part in parts if part)
    if isinstance(value, list):
        parts = [flatten_scene_text(v, parent_key) for v in value]
        return "\n".join(part for part in parts if part)
    return ""


def build_asset_aliases(manifest: dict[str, Any]) -> dict[str, dict[str, set[str]]]:
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), dict) else {}
    result = {"character": {}, "object": {}}
    for kind, field in (("character", "character_bible"), ("object", "object_bible")):
        for asset in assets.get(field, []) if isinstance(assets, dict) else []:
            if not isinstance(asset, dict):
                continue
            asset_id_key = f"{kind}_id"
            asset_id = asset.get(asset_id_key)
            if not isinstance(asset_id, str) or not asset_id.strip():
                continue
            aliases: set[str] = {asset_id}
            for extra_key in ("review_aliases", "aliases"):
                values = asset.get(extra_key)
                if isinstance(values, list):
                    aliases.update(str(v).strip() for v in values if str(v).strip())
            if isinstance(asset.get("display_name"), str):
                aliases.add(str(asset["display_name"]).strip())
            if isinstance(asset.get("name"), str):
                aliases.add(str(asset["name"]).strip())
            result[kind][asset_id] = {alias for alias in aliases if alias}
    return result


def extract_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for token in JP_TOKEN_RE.findall(text or ""):
        normalized = token.strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in STOPWORDS or normalized in STOPWORDS:
            continue
        if re.fullmatch(r"[一-龯]", normalized) and normalized not in IMPORTANT_SINGLE_KANJI:
            continue
        if re.fullmatch(r"[A-Za-z]{1,2}", normalized):
            continue
        terms.add(normalized)
    for token in EN_TOKEN_RE.findall(text or ""):
        normalized = token.strip().lower()
        if not normalized:
            continue
        if len(normalized) <= 2:
            continue
        terms.add(normalized)
    return compact_terms(terms)


def compact_terms(terms: set[str]) -> set[str]:
    compacted: set[str] = set()
    for term in sorted(terms, key=len, reverse=True):
        if any(term != kept and term in kept for kept in compacted):
            continue
        compacted.add(term)
    return compacted


def term_is_covered(term: str, candidates: set[str]) -> bool:
    normalized = (term or "").strip()
    if not normalized:
        return False
    for candidate in candidates:
        probe = (candidate or "").strip()
        if not probe:
            continue
        if normalized == probe:
            return True
        if normalized in probe:
            return True
        if probe in normalized:
            return True
    return False


def find_alias_hits(text: str, aliases: dict[str, set[str]]) -> dict[str, set[str]]:
    hits: dict[str, set[str]] = {}
    normalized = text or ""
    for asset_id, values in aliases.items():
        matched = {alias for alias in values if alias and alias in normalized}
        if matched:
            hits[asset_id] = matched
    return hits


def manifest_cut_map(manifest: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    cuts: dict[tuple[str, str], dict[str, Any]] = {}
    for scene in manifest.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        sid = normalize_dotted_id(scene.get("scene_id"))
        if not sid:
            continue
        for cut in scene.get("cuts", []) if isinstance(scene.get("cuts"), list) else []:
            if not isinstance(cut, dict):
                continue
            cid = normalize_dotted_id(cut.get("cut_id"))
            if cid:
                cuts[(sid, cid)] = cut
        if not isinstance(scene.get("cuts"), list) or not scene.get("cuts"):
            cuts[(sid, "0")] = scene
    return cuts


def manifest_image_node_map(manifest: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    nodes: dict[tuple[str, str], dict[str, Any]] = {}
    for scene in manifest.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        sid = normalize_dotted_id(scene.get("scene_id"))
        if not sid:
            continue
        cuts = scene.get("cuts")
        if isinstance(cuts, list):
            for cut in cuts:
                if not isinstance(cut, dict):
                    continue
                cid = normalize_dotted_id(cut.get("cut_id"))
                if cid:
                    nodes[(sid, cid)] = cut
            continue
        nodes[(sid, "0")] = scene
    return nodes


def _parse_csv_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part.strip().lower() for part in str(value).split(",") if part.strip()}


def _scene_context_lookup(context: dict[Any, str], scene_id: str) -> str:
    if scene_id in context:
        return str(context.get(scene_id) or "")
    try:
        integer_scene_id = int(scene_id)
    except Exception:
        return ""
    return str(context.get(integer_scene_id) or "")


def _is_reference_output(output: str) -> bool:
    normalized = (output or "").replace("\\", "/")
    return normalized.startswith("assets/characters/") or normalized.startswith("assets/objects/")


def _coerce_score_map(value: Any) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    scores: dict[str, float] = {}
    for key, raw in value.items():
        try:
            score = float(raw)
        except (TypeError, ValueError):
            continue
        scores[str(key)] = max(0.0, min(1.0, score))
    return scores


def manifest_prompt_entries(manifest: dict[str, Any], *, allowed_story_modes: set[str]) -> list[PromptEntry]:
    entries: list[PromptEntry] = []
    for scene in manifest.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        sid = normalize_dotted_id(scene.get("scene_id"))
        if not sid:
            continue
        cuts = scene.get("cuts")
        candidate_nodes: list[tuple[str, dict[str, Any]]] = []
        if isinstance(cuts, list):
            for cut in cuts:
                if not isinstance(cut, dict):
                    continue
                cid = normalize_dotted_id(cut.get("cut_id"))
                if cid:
                    candidate_nodes.append((cid, cut))
        else:
            candidate_nodes.append(("0", scene))

        for cid, node in candidate_nodes:
            image_generation = node.get("image_generation")
            if not isinstance(image_generation, dict):
                continue
            api_prompt_payload = image_generation.get("api_prompt_payload") if isinstance(image_generation.get("api_prompt_payload"), dict) else {}
            prompt_policy_version = str(api_prompt_payload.get("policy_version") or image_generation.get("prompt_policy_version") or "").strip()
            legacy_prompt = str(image_generation.get("prompt") or "").strip()
            api_prompt = str(api_prompt_payload.get("prompt") or "").strip()
            if prompt_policy_version == IMAGE_API_PROMPT_POLICY_VERSION:
                prompt = api_prompt
            else:
                prompt = api_prompt or legacy_prompt
            output = str(image_generation.get("output") or "").strip()
            if not output:
                continue
            if not prompt and prompt_policy_version != IMAGE_API_PROMPT_POLICY_VERSION:
                continue
            still_plan = node.get("still_image_plan") if isinstance(node.get("still_image_plan"), dict) else {}
            mode = str(still_plan.get("mode") or "").strip().lower()
            if not _is_reference_output(output):
                if not mode or mode not in allowed_story_modes:
                    continue
            audio = node.get("audio") if isinstance(node.get("audio"), dict) else {}
            narration = ""
            narration_data = audio.get("narration") if isinstance(audio.get("narration"), dict) else {}
            if isinstance(narration_data, dict):
                narration = str(narration_data.get("text") or "").strip()
            review = image_generation.get("review") if isinstance(image_generation.get("review"), dict) else {}
            contract = image_generation.get("contract") if isinstance(image_generation.get("contract"), dict) else {}
            entries.append(
                PromptEntry(
                    scene_id=sid,
                    cut_id=cid,
                    output=output,
                    narration=narration,
                    rationale=mode or ("reference" if _is_reference_output(output) else ""),
                    agent_review_ok=bool(review.get("agent_review_ok", True)),
                    human_review_ok=bool(review.get("human_review_ok", False)),
                    human_review_reason=str(review.get("human_review_reason") or ""),
                    agent_review_reason_keys=[str(v).strip() for v in list(review.get("agent_review_reason_keys") or review.get("agent_review_reason_codes") or []) if str(v).strip()],
                    agent_review_reason_messages=[str(v).strip() for v in list(review.get("agent_review_reason_messages") or []) if str(v).strip()],
                    rubric_scores=_coerce_score_map(review.get("rubric_scores")),
                    overall_score=float(review.get("overall_score") or 0.0),
                    contract=dict(contract),
                    prompt=prompt,
                    prompt_policy_version=prompt_policy_version or None,
                    legacy_prompt=legacy_prompt,
                )
            )
    return entries


def find_missing_required_blocks(prompt: str) -> list[str]:
    return missing_required_prompt_blocks(prompt)


def _score_from_count(*, total: int, missing: int) -> float:
    if total <= 0:
        return 1.0
    return max(0.0, min(1.0, (total - missing) / total))


def _prompt_visual_category_hits(prompt: str) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for category, terms in PROMPT_CRAFT_VISUAL_CATEGORIES.items():
        matched = [term for term in terms if term in prompt]
        if matched:
            hits[category] = matched
    return hits


def prompt_craft_detail_issues(prompt: str) -> list[str]:
    compact = "".join((prompt or "").split())
    category_hits = _prompt_visual_category_hits(prompt)
    issues: list[str] = []
    sections = prompt_block_sections(prompt)
    thin_sections = [
        PROMPT_BLOCK_LABELS.get(key, key)
        for key, body in sections.items()
        if len("".join(body.split())) < 18
    ]
    if len(compact) < PROMPT_CRAFT_MIN_CHARS:
        issues.append(f"prompt body is too short for a cinematic scene image ({len(compact)}/{PROMPT_CRAFT_MIN_CHARS} non-space chars).")
    if len(thin_sections) >= 4:
        issues.append("prompt has too many thin required blocks without concrete drawable detail: " + ", ".join(thin_sections[:6]) + ".")
    if len(category_hits) < PROMPT_CRAFT_MIN_VISUAL_CATEGORIES:
        missing_count = PROMPT_CRAFT_MIN_VISUAL_CATEGORIES - len(category_hits)
        issues.append(
            "prompt lacks enough concrete visual craft categories "
            f"({len(category_hits)}/{PROMPT_CRAFT_MIN_VISUAL_CATEGORIES}; missing at least {missing_count} of subject/blocking/setting/light/camera/material)."
        )
    return issues


def _contract_string_list(contract: dict[str, Any], key: str) -> list[str]:
    value = contract.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _nested_contract_value(contract: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        cur: Any = contract
        ok = True
        for key in path.split("."):
            if not isinstance(cur, dict) or key not in cur:
                ok = False
                break
            cur = cur[key]
        if ok:
            return cur
    return None


def _nested_contract_string(contract: dict[str, Any], *paths: str) -> str:
    value = _nested_contract_value(contract, *paths)
    return str(value).strip() if value is not None else ""


def _nested_contract_list(contract: dict[str, Any], *paths: str) -> list[str]:
    for path in paths:
        value = _nested_contract_value(contract, path)
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
    return []


def _cut_contract_for_node(node: dict[str, Any]) -> dict[str, Any]:
    for key in ("cut_contract", "scene_contract", "cut_blueprint"):
        value = node.get(key) if isinstance(node, dict) else None
        if isinstance(value, dict) and value:
            return value
    return {}


def _text_contains_any(text: str, needles: list[str] | tuple[str, ...]) -> bool:
    probe = text or ""
    return any(needle and needle in probe for needle in needles)


def _score_story_alignment(local_source_text: str, prompt_terms: set[str], missing_source_terms: list[str]) -> float:
    source_terms = extract_terms(local_source_text)
    coverage_score = _score_from_count(total=len(source_terms), missing=len(missing_source_terms))
    return round(coverage_score, 3)


def _score_subject_specificity(
    *,
    character_alias_hits: dict[str, set[str]],
    object_alias_hits: dict[str, set[str]],
    prompt_character_hits: dict[str, set[str]],
    prompt_object_hits: dict[str, set[str]],
) -> float:
    expected = len(character_alias_hits) + len(object_alias_hits)
    covered = len(prompt_character_hits) + len(prompt_object_hits)
    if expected <= 0:
        return 1.0 if covered > 0 else 0.7
    return round(_score_from_count(total=expected, missing=max(0, expected - covered)), 3)


def _score_prompt_craft(prompt: str, missing_blocks: list[str], independence_issues: list[str]) -> float:
    block_score = _score_from_count(total=len(REQUIRED_PROMPT_BLOCKS), missing=len(missing_blocks))
    issue_penalty = min(0.45, 0.15 * len(independence_issues))
    detail_issues = prompt_craft_detail_issues(prompt)
    detail_penalty = min(0.35, 0.18 * len(detail_issues))
    length_bonus = 0.05 if len((prompt or "").splitlines()) >= 8 else 0.0
    return round(max(0.0, min(1.0, block_score - issue_penalty - detail_penalty + length_bonus)), 3)


def _score_continuity_readiness(
    *,
    declared_character_ids: set[str],
    declared_object_ids: set[str],
    suggested_character_ids: set[str],
    suggested_object_ids: set[str],
    blocking_missing: bool,
) -> float:
    total = len(declared_character_ids | declared_object_ids | suggested_character_ids | suggested_object_ids)
    id_score = _score_from_count(total=total or 1, missing=len(suggested_character_ids) + len(suggested_object_ids))
    blocking_penalty = 0.2 if blocking_missing else 0.0
    return round(max(0.0, min(1.0, id_score - blocking_penalty)), 3)


def _assess_first_frame_readiness(prompt: str, output: str) -> tuple[float, list[str]]:
    output_norm = (output or "").replace("\\", "/")
    if "/assets/scenes/" not in f"/{output_norm}":
        return 1.0, []
    text = prompt or ""
    mid_action_hits = [pattern.pattern for pattern in MID_ACTION_PATTERNS if pattern.search(text)]
    safe = any(pattern.search(text) for pattern in FIRST_FRAME_SAFE_PATTERNS)
    if not mid_action_hits:
        return 1.0, []
    if safe:
        return 0.75, []
    return 0.35, mid_action_hits


def _score_production_readiness(findings: list[Finding]) -> float:
    severe_codes = {
        "missing_required_prompt_block",
        "prompt_not_self_contained",
        "prompt_contains_nonvisual_metadata",
        "prompt_contains_first_frame_metadata",
        "image_contract_must_avoid_violated",
        "image_contract_missing",
        "image_reveal_constraint_violated",
        "image_prompt_not_first_frame_ready",
    }
    medium_codes = {
        "non_japanese_prompt_term",
        "prompt_only_local_mismatch",
        "prompt_subject_drift",
        "blocking_drift",
    }
    score = 1.0
    for finding in findings:
        if finding.code in severe_codes:
            score -= 0.2
        elif finding.code in medium_codes:
            score -= 0.1
        else:
            score -= 0.05
    return round(max(0.0, min(1.0, score)), 3)


def _score_prompt_entry(
    *,
    local_source_text: str,
    prompt: str,
    prompt_terms: set[str],
    missing_source_terms: list[str],
    missing_blocks: list[str],
    independence_issues: list[str],
    character_alias_hits: dict[str, set[str]],
    object_alias_hits: dict[str, set[str]],
    prompt_character_hits: dict[str, set[str]],
    prompt_object_hits: dict[str, set[str]],
    declared_character_ids: set[str],
    declared_object_ids: set[str],
    suggested_character_ids: set[str],
    suggested_object_ids: set[str],
    blocking_missing: bool,
    first_frame_readiness: float,
    findings: list[Finding],
) -> tuple[dict[str, float], float]:
    rubric_scores = {
        "story_alignment": _score_story_alignment(local_source_text, prompt_terms, missing_source_terms),
        "subject_specificity": _score_subject_specificity(
            character_alias_hits=character_alias_hits,
            object_alias_hits=object_alias_hits,
            prompt_character_hits=prompt_character_hits,
            prompt_object_hits=prompt_object_hits,
        ),
        "prompt_craft": _score_prompt_craft(prompt, missing_blocks, independence_issues),
        "continuity_readiness": _score_continuity_readiness(
            declared_character_ids=declared_character_ids,
            declared_object_ids=declared_object_ids,
            suggested_character_ids=suggested_character_ids,
            suggested_object_ids=suggested_object_ids,
            blocking_missing=blocking_missing,
        ),
        "first_frame_readiness": first_frame_readiness,
        "production_readiness": _score_production_readiness(findings),
    }
    overall_score = round(
        sum(rubric_scores[key] * IMAGE_REVIEW_RUBRIC_WEIGHTS[key] for key in IMAGE_REVIEW_RUBRIC_WEIGHTS),
        3,
    )
    return rubric_scores, overall_score


def _suppressed_subject_ids_for_entry(
    *,
    scene_id: str,
    cut_id: str,
    reveal_constraints: list[RevealConstraint],
    cut_order_map: dict[tuple[str, str], int],
) -> tuple[set[str], set[str]]:
    suppressed_characters: set[str] = set()
    suppressed_objects: set[str] = set()
    node_order = cut_order_map.get((scene_id, cut_id))
    if node_order is None:
        return suppressed_characters, suppressed_objects
    for constraint in reveal_constraints:
        if constraint.rule != "must_not_appear_before":
            continue
        selector_key = parse_selector(constraint.selector)
        if selector_key is None:
            continue
        selector_order = cut_order_map.get(selector_key)
        if selector_order is None or node_order >= selector_order:
            continue
        if constraint.subject_type == "character":
            suppressed_characters.add(constraint.subject_id)
        elif constraint.subject_type == "object":
            suppressed_objects.add(constraint.subject_id)
    return suppressed_characters, suppressed_objects


def review_entries(
    entries: list[PromptEntry],
    *,
    manifest: dict[str, Any],
    story_scene_map: dict[str, str],
    script_scene_map: dict[str, str],
    story_text: str,
    script_text: str,
    reveal_constraints: list[RevealConstraint] | None = None,
) -> list[ReviewOutcome]:
    cuts = manifest_cut_map(manifest)
    aliases = build_asset_aliases(manifest)
    cut_order_map = build_manifest_cut_order_map(manifest)
    reveal_constraints = reveal_constraints or []
    results: list[ReviewOutcome] = []

    for entry in entries:
        cut = cuts.get((entry.scene_id, entry.cut_id), {})
        image_generation = cut.get("image_generation") if isinstance(cut, dict) else {}
        audio = cut.get("audio") if isinstance(cut, dict) else {}
        is_reference_entry = _is_reference_output(entry.output)
        narration_text = entry.narration or (((audio or {}).get("narration") or {}).get("text") or "")
        local_story = _scene_context_lookup(story_scene_map, entry.scene_id)
        local_script = _scene_context_lookup(script_scene_map, entry.scene_id)
        local_source_text = "\n".join(part for part in [narration_text, local_story, local_script] if part)

        prompt_terms = extract_terms(entry.prompt)
        narration_terms = extract_terms(narration_text)
        character_alias_hits = find_alias_hits(local_source_text, aliases["character"])
        object_alias_hits = find_alias_hits(local_source_text, aliases["object"])
        prompt_character_hits = find_alias_hits(entry.prompt, aliases["character"])
        prompt_object_hits = find_alias_hits(entry.prompt, aliases["object"])
        suppressed_character_ids, suppressed_object_ids = _suppressed_subject_ids_for_entry(
            scene_id=entry.scene_id,
            cut_id=entry.cut_id,
            reveal_constraints=reveal_constraints,
            cut_order_map=cut_order_map,
        )
        if suppressed_character_ids:
            character_alias_hits = {
                asset_id: matched
                for asset_id, matched in character_alias_hits.items()
                if asset_id not in suppressed_character_ids
            }
        if suppressed_object_ids:
            object_alias_hits = {
                asset_id: matched
                for asset_id, matched in object_alias_hits.items()
                if asset_id not in suppressed_object_ids
            }

        declared_character_ids = set(image_generation.get("character_ids") or []) if isinstance(image_generation, dict) else set()
        declared_object_ids = set(image_generation.get("object_ids") or []) if isinstance(image_generation, dict) else set()
        contract = entry.contract if isinstance(entry.contract, dict) and entry.contract else {}
        if not contract and isinstance(image_generation, dict) and isinstance(image_generation.get("contract"), dict):
            contract = dict(image_generation.get("contract") or {})
        cut_contract = _cut_contract_for_node(cut) if isinstance(cut, dict) else {}

        findings: list[Finding] = []
        drawable_prompt = prompt_drawable_content(entry.prompt)
        is_api_prompt_v1 = entry.prompt_policy_version == IMAGE_API_PROMPT_POLICY_VERSION

        if not is_reference_entry and cut_contract:
            cut_must_show = _nested_contract_list(cut_contract, "must_show", "viewer_contract.must_show")
            if is_api_prompt_v1:
                cut_must_show = [term for term in cut_must_show if not API_PROMPT_ABSTRACT_TERM_RE.search(str(term))]
            cut_must_avoid = _nested_contract_list(cut_contract, "must_avoid", "viewer_contract.must_avoid", "motion_contract.must_not_add")
            first_frame_brief = _nested_contract_string(cut_contract, "first_frame_brief", "first_frame_contract.first_frame_brief")
            visual_proof = _nested_contract_string(cut_contract, "visual_beat", "viewer_contract.visual_proof")
            missing_cut_terms = [item for item in cut_must_show if item not in entry.prompt]
            for item in missing_cut_terms:
                findings.append(
                    Finding(
                        code="cut_contract_must_show_unmet",
                        message=f"cut contract requires `{item}` but the image prompt does not include it.",
                    )
                )
            for item in [item for item in cut_must_avoid if item in drawable_prompt]:
                findings.append(
                    Finding(
                        code="cut_contract_must_avoid_violated",
                        message=f"cut contract forbids `{item}` but the image prompt includes it.",
                    )
                )
            if not first_frame_brief:
                findings.append(
                    Finding(
                        code="cut_contract_first_frame_missing",
                        message="cut_contract.first_frame_contract.first_frame_brief is missing; p600 cannot produce a startable still.",
                    )
                )
            if visual_proof and not any(term in entry.prompt for term in extract_terms(visual_proof)):
                findings.append(
                    Finding(
                        code="image_prompt_story_alignment_weak",
                        message="image prompt does not clearly contain terms from cut_contract.viewer_contract.visual_proof.",
                    )
                )

        for violation in find_reveal_violations_for_surface(
            scene_id=entry.scene_id,
            cut_id=entry.cut_id,
            output=entry.output,
            text_fragments=[entry.prompt],
            declared_character_ids=declared_character_ids,
            declared_object_ids=declared_object_ids,
            constraints=reveal_constraints,
            aliases=aliases,
            cut_order_map=cut_order_map,
        ):
            findings.append(
                Finding(
                    code="script_reveal_constraint_violated",
                    message=(
                        f"script reveal constraint forbids `{violation.subject_id}` before `{violation.selector}`, "
                        f"but {_selector_label(entry.scene_id, entry.cut_id)} already reveals it via {', '.join(violation.evidence)}."
                    ),
                )
            )

        if not contract:
            findings.append(
                Finding(
                    code="image_contract_missing",
                    message="image_generation.contract is missing; define target_focus, must_include, must_avoid, and done_when before generation.",
                )
            )
        else:
            must_include = _contract_string_list(contract, "must_include")
            if is_api_prompt_v1:
                must_include = [term for term in must_include if not API_PROMPT_ABSTRACT_TERM_RE.search(str(term))]
            must_avoid = _contract_string_list(contract, "must_avoid")
            target_focus = str(contract.get("target_focus") or "").strip().lower()

            missing_include = [item for item in must_include if item not in entry.prompt]
            for item in missing_include:
                findings.append(
                    Finding(
                        code="image_contract_must_include_unmet",
                        message=f"contract requires `{item}` but the prompt does not clearly include it.",
                    )
                )
            violated_avoid = [item for item in must_avoid if item in drawable_prompt]
            for item in violated_avoid:
                findings.append(
                    Finding(
                        code="image_contract_must_avoid_violated",
                        message=f"contract forbids `{item}` but the prompt still includes it.",
                    )
                )
            focus_terms = IMAGE_TARGET_FOCUS_TERMS.get(target_focus, ())
            if target_focus and focus_terms and not _text_contains_any(entry.prompt, focus_terms):
                findings.append(
                    Finding(
                        code="image_contract_target_focus_unmet",
                        message=f"contract target_focus `{target_focus}` is not clearly represented in the prompt body.",
                    )
                )

        missing_blocks: list[str] = []
        if is_api_prompt_v1:
            findings.extend(
                api_prompt_structural_contract_issues(
                    entry.prompt,
                    object_present=bool(declared_object_ids),
                )
            )
        else:
            missing_blocks = find_missing_required_blocks(entry.prompt)
            for block in missing_blocks:
                findings.append(
                    Finding(
                        code="missing_required_prompt_block",
                        message=f"prompt is missing required block `[{block}]`.",
                    )
                )
            findings.extend(prompt_structural_contract_issues(entry.prompt))
        craft_detail_issues = prompt_craft_detail_issues(entry.prompt)
        for issue in craft_detail_issues:
            findings.append(Finding(code="image_prompt_prompt_craft_weak", message=issue))
        nonvisual_metadata_issues = find_prompt_nonvisual_metadata_issues(entry.prompt)
        for issue in nonvisual_metadata_issues:
            findings.append(Finding(code="prompt_contains_nonvisual_metadata", message=issue))

        design_meta_leak_issues = find_prompt_design_meta_leak_issues(entry.prompt)
        for issue in design_meta_leak_issues:
            findings.append(Finding(code="image_prompt_design_meta_leaked", message=issue))

        first_frame_metadata_issues = find_prompt_first_frame_metadata_issues(entry.prompt)
        for issue in first_frame_metadata_issues:
            findings.append(Finding(code="prompt_contains_first_frame_metadata", message=issue))

        motion_brief_leak_issues = find_prompt_motion_brief_leak_issues(entry.prompt)
        for issue in motion_brief_leak_issues:
            findings.append(Finding(code="prompt_leaks_motion_brief", message=issue))

        independence_issues = find_prompt_independence_issues(entry.prompt)
        if is_api_prompt_v1:
            independence_issues = [
                issue
                for issue in independence_issues
                if issue != "prompt depends on another shot or prompt instead of being self-contained."
            ]
        if nonvisual_metadata_issues or design_meta_leak_issues or first_frame_metadata_issues or motion_brief_leak_issues:
            independence_issues = [
                issue for issue in independence_issues if issue != "prompt references another scene/cut directly."
            ]
        for issue in independence_issues:
            code = "non_japanese_prompt_term" if "rideable" in issue else "prompt_not_self_contained"
            findings.append(Finding(code=code, message=issue))

        if prompt_character_hits and not declared_character_ids:
            findings.append(
                Finding(
                    code="prompt_mentions_character_but_character_ids_empty",
                    message=(
                        "prompt mentions character(s) "
                        f"{sorted(prompt_character_hits.keys())!r}, but `image_generation.character_ids` is empty."
                    ),
                )
            )

        important_source_terms = set(narration_terms)
        for matched in list(character_alias_hits.values()) + list(object_alias_hits.values()):
            important_source_terms.update(matched)
        important_source_terms = compact_terms(important_source_terms)
        for term in sorted(term for term in important_source_terms if not term_is_covered(term, prompt_terms)):
            findings.append(
                Finding(
                    code="source_anchor_missing_from_prompt",
                    message=f"source context mentions `{term}` but the prompt does not.",
                )
            )

        for asset_id, matched in sorted(character_alias_hits.items()):
            if asset_id not in declared_character_ids:
                findings.append(
                    Finding(
                        code="missing_character_id",
                        message=f"source context implies character `{asset_id}` via {sorted(matched)!r}, but `character_ids` does not include it.",
                    )
                )
        for asset_id, matched in sorted(object_alias_hits.items()):
            if asset_id not in declared_object_ids:
                findings.append(
                    Finding(
                        code="missing_object_id",
                        message=f"source context implies object `{asset_id}` via {sorted(matched)!r}, but `object_ids` does not include it.",
                    )
                )

        allowed_prompt_asset_ids = declared_character_ids | declared_object_ids
        for asset_id, matched in sorted({**prompt_character_hits, **prompt_object_hits}.items()):
            if asset_id in allowed_prompt_asset_ids:
                continue
            if asset_id in character_alias_hits or asset_id in object_alias_hits:
                continue
            if is_reference_entry:
                continue
            findings.append(
                Finding(
                    code="prompt_only_local_mismatch",
                    message=f"prompt mentions `{asset_id}` via {sorted(matched)!r}, but the local source context does not.",
                )
            )

        for asset_id, matched in sorted(character_alias_hits.items()):
            if asset_id in declared_character_ids:
                continue
            if asset_id not in prompt_character_hits:
                findings.append(
                    Finding(
                        code="prompt_missing_expected_character_anchor",
                        message=f"source context implies character `{asset_id}` via {sorted(matched)!r}, but the prompt body does not clearly mention it.",
                    )
                )

        for asset_id, matched in sorted(object_alias_hits.items()):
            if asset_id in declared_object_ids:
                continue
            if asset_id not in prompt_object_hits:
                findings.append(
                    Finding(
                        code="prompt_missing_expected_object_anchor",
                        message=f"source context implies object `{asset_id}` via {sorted(matched)!r}, but the prompt body does not clearly mention it.",
                    )
                )

        if character_alias_hits and not prompt_character_hits:
            findings.append(
                Finding(
                    code="prompt_subject_drift",
                    message="source context expects character-driven action, but the prompt body reads like environment-only staging.",
                )
            )

        relation_terms = {
            "またがる",
            "背に乗る",
            "背にまたがる",
            "背に乗って",
            "渡す",
            "手渡す",
            "差し出す",
            "受け取る",
            "耳を傾ける",
            "見上げる",
            "向き合う",
        }
        source_relation_hits = sorted(term for term in relation_terms if term in local_source_text)
        prompt_relation_hits = sorted(term for term in relation_terms if term in entry.prompt)
        blocking_missing = bool(source_relation_hits and not prompt_relation_hits)
        if source_relation_hits and not prompt_relation_hits:
            findings.append(
                Finding(
                    code="blocking_drift",
                    message=f"source context implies blocking/action {source_relation_hits!r}, but the prompt body does not preserve that relation.",
                )
            )

        first_frame_readiness, mid_action_hits = _assess_first_frame_readiness(entry.prompt, entry.output)
        if mid_action_hits:
            findings.append(
                Finding(
                    code="image_prompt_not_first_frame_ready",
                    message=(
                        "scene image prompt reads like the middle of an action instead of the first frame of the video. "
                        f"Rewrite it as a pre-action or initial-pose image; detected action markers: {mid_action_hits!r}."
                    ),
                )
            )

        missing_source_terms = sorted(term for term in important_source_terms if not term_is_covered(term, prompt_terms))
        suggested_character_ids = set(character_alias_hits.keys()) - declared_character_ids
        suggested_object_ids = set(object_alias_hits.keys()) - declared_object_ids
        rubric_scores, overall_score = _score_prompt_entry(
            local_source_text=local_source_text,
            prompt=entry.prompt,
            prompt_terms=prompt_terms,
            missing_source_terms=missing_source_terms,
            missing_blocks=missing_blocks,
            independence_issues=independence_issues + nonvisual_metadata_issues + design_meta_leak_issues + first_frame_metadata_issues,
            character_alias_hits=character_alias_hits,
            object_alias_hits=object_alias_hits,
            prompt_character_hits=prompt_character_hits,
            prompt_object_hits=prompt_object_hits,
            declared_character_ids=declared_character_ids,
            declared_object_ids=declared_object_ids,
            suggested_character_ids=suggested_character_ids,
            suggested_object_ids=suggested_object_ids,
            blocking_missing=blocking_missing,
            first_frame_readiness=first_frame_readiness,
            findings=findings,
        )
        if rubric_scores["story_alignment"] < IMAGE_REVIEW_RUBRIC_THRESHOLDS["story_alignment"]:
            findings.append(
                Finding(
                    code="image_prompt_story_alignment_weak",
                    message="prompt does not preserve enough of the local story/script intent.",
                )
            )
        if rubric_scores["subject_specificity"] < IMAGE_REVIEW_RUBRIC_THRESHOLDS["subject_specificity"]:
            findings.append(
                Finding(
                    code="image_prompt_subject_specificity_weak",
                    message="prompt is too generic about the main subject, character, or setpiece.",
                )
            )
        if rubric_scores["prompt_craft"] < IMAGE_REVIEW_RUBRIC_THRESHOLDS["prompt_craft"]:
            findings.append(
                Finding(
                    code="image_prompt_prompt_craft_weak",
                    message="prompt has the required blocks but is still too thin in cinematic detail, shot design, or visual specificity.",
                )
            )
        if rubric_scores["continuity_readiness"] < IMAGE_REVIEW_RUBRIC_THRESHOLDS["continuity_readiness"]:
            findings.append(
                Finding(
                    code="image_prompt_continuity_weak",
                    message="prompt is not specific enough to preserve asset continuity and blocking across cuts.",
                )
            )
        if rubric_scores["first_frame_readiness"] < IMAGE_REVIEW_RUBRIC_THRESHOLDS["first_frame_readiness"]:
            findings.append(
                Finding(
                    code="image_prompt_first_frame_readiness_weak",
                    message="prompt does not read clearly as the first frame of the intended video shot.",
                )
            )
        if rubric_scores["production_readiness"] < IMAGE_REVIEW_RUBRIC_THRESHOLDS["production_readiness"]:
            findings.append(
                Finding(
                    code="image_prompt_production_readiness_weak",
                    message="prompt still contains structural or operational issues likely to hurt image generation.",
                )
            )

        results.append(
            ReviewOutcome(
                entry=entry,
                findings=dedupe_findings(findings),
                suggested_character_ids=sorted(suggested_character_ids),
                suggested_object_ids=sorted(suggested_object_ids),
                rubric_scores=rubric_scores,
                overall_score=overall_score,
            )
        )
    return results


def load_script_reveal_constraints(script_path: Path) -> list[RevealConstraint]:
    if not script_path.exists():
        return []
    _, data = load_structured_document(script_path)
    return load_reveal_constraints(data if isinstance(data, dict) else {})


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, str]] = set()
    deduped: list[Finding] = []
    for finding in findings:
        key = (finding.code, finding.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped


def reason_keys_from_findings(findings: list[Finding]) -> list[str]:
    return list(dict.fromkeys(f.code for f in findings))


def reason_messages_from_findings(findings: list[Finding]) -> list[str]:
    return [finding.message.replace("`", "'") for finding in findings]


def render_prompt_collection(entries: list[PromptEntry]) -> str:
    lines = [
        "# Image Prompt Collection",
        "",
        f"件数: `{len(entries)}`",
        "",
    ]
    for entry in entries:
        selector = _selector_label(entry.scene_id, entry.cut_id)
        lines.extend(
            [
                f"## {selector}",
                "",
                f"- output: `{entry.output}`",
                f"- narration: `{entry.narration}`" if entry.narration else "- narration: `(silent)`",
                f"- rationale: `{entry.rationale}`",
                f"- agent_review_ok: `{'true' if entry.agent_review_ok else 'false'}`",
                f"- human_review_ok: `{'true' if entry.human_review_ok else 'false'}`",
                f"- human_review_reason: `{entry.human_review_reason}`",
                f"- overall_score: `{entry.overall_score:.3f}`",
            ]
        )
        lines.append(f"- rubric_scores: `{entry.rubric_scores}`")
        if entry.contract:
            lines.append(f"- contract: `{entry.contract}`")
        if entry.prompt_policy_version:
            lines.append(f"- prompt_policy_version: `{entry.prompt_policy_version}`")
        if entry.agent_review_reason_keys:
            lines.append(f"- agent_review_reason_keys: `{', '.join(entry.agent_review_reason_keys)}`")
        else:
            lines.append("- agent_review_reason_keys: ``")
        lines.append("- agent_review_reason_messages:")
        if entry.agent_review_reason_messages:
            lines.extend(f"  - `{message}`" for message in entry.agent_review_reason_messages)
        else:
            lines.append("  - ``")
        fence = "api_prompt" if entry.prompt_policy_version == IMAGE_API_PROMPT_POLICY_VERSION else "text"
        lines.extend(["", f"```{fence}", entry.prompt.rstrip(), "```", ""])
    return "\n".join(lines)


def apply_review_statuses(entries: list[PromptEntry], results: list[ReviewOutcome]) -> list[PromptEntry]:
    outcome_map = {(outcome.entry.scene_id, outcome.entry.cut_id): outcome for outcome in results}
    updated: list[PromptEntry] = []
    for entry in entries:
        outcome = outcome_map.get((entry.scene_id, entry.cut_id))
        hard_findings = [finding for finding in outcome.findings] if outcome else []
        agent_review_ok = not any(is_hard_finding(finding) for finding in hard_findings)
        reason_keys = reason_keys_from_findings(outcome.findings) if outcome and outcome.findings else []
        reason_messages = reason_messages_from_findings(outcome.findings) if outcome and outcome.findings else []
        updated.append(
            PromptEntry(
                scene_id=entry.scene_id,
                cut_id=entry.cut_id,
                output=entry.output,
                narration=entry.narration,
                rationale=entry.rationale,
                agent_review_ok=agent_review_ok,
                human_review_ok=entry.human_review_ok,
                human_review_reason=entry.human_review_reason,
                agent_review_reason_keys=reason_keys,
                agent_review_reason_messages=reason_messages,
                rubric_scores=dict(outcome.rubric_scores) if outcome else dict(entry.rubric_scores),
                overall_score=outcome.overall_score if outcome else entry.overall_score,
                contract=dict(entry.contract),
                prompt=entry.prompt,
                prompt_policy_version=entry.prompt_policy_version,
                legacy_prompt=entry.legacy_prompt,
            )
        )
    return updated


def apply_human_review_updates(entries: list[PromptEntry], selectors: list[str], value: bool) -> list[PromptEntry]:
    if not selectors:
        return entries
    targets: set[tuple[str, str]] = set()
    for selector in selectors:
        parsed = parse_selector(selector.strip())
        if not parsed:
            raise SystemExit(f"Invalid --set-human-review selector: {selector}")
        targets.add(parsed)
    updated: list[PromptEntry] = []
    for entry in entries:
        human_review_ok = value if (entry.scene_id, entry.cut_id) in targets else entry.human_review_ok
        human_review_reason = entry.human_review_reason
        if (entry.scene_id, entry.cut_id) in targets and not value:
            human_review_reason = ""
        updated.append(
            PromptEntry(
                scene_id=entry.scene_id,
                cut_id=entry.cut_id,
                output=entry.output,
                narration=entry.narration,
                rationale=entry.rationale,
                agent_review_ok=entry.agent_review_ok,
                human_review_ok=human_review_ok,
                human_review_reason=human_review_reason,
                agent_review_reason_keys=entry.agent_review_reason_keys,
                agent_review_reason_messages=entry.agent_review_reason_messages,
                rubric_scores=dict(entry.rubric_scores),
                overall_score=entry.overall_score,
                contract=dict(entry.contract),
                prompt=entry.prompt,
                prompt_policy_version=entry.prompt_policy_version,
                legacy_prompt=entry.legacy_prompt,
            )
        )
    return updated


def render_report(
    results: list[ReviewOutcome],
    *,
    manifest_path: Path,
    fixed_character_ids: int = 0,
    fixed_object_ids: int = 0,
    unresolved_entries: int = 0,
) -> str:
    total = len(results)
    warned = sum(1 for outcome in results if outcome.findings)
    hard_findings = sum(1 for outcome in results for finding in outcome.findings if is_hard_finding(finding))
    soft_findings = sum(1 for outcome in results for finding in outcome.findings if is_soft_finding(finding))
    finding_count = sum(len(outcome.findings) for outcome in results)
    status = "FAIL" if unresolved_entries else ("WARN" if finding_count else "PASS")
    lines = [
        "# Image Prompt Story Review",
        "",
        f"- manifest: `{manifest_path}`",
        f"- status: `{status}`",
        f"- reviewed_entries: `{total}`",
        f"- entries_with_findings: `{warned}`",
        f"- findings: `{finding_count}`",
        f"- hard_findings: `{hard_findings}`",
        f"- soft_findings: `{soft_findings}`",
        f"- unresolved_entries: `{unresolved_entries}`",
        f"- fixed_character_ids: `{fixed_character_ids}`",
        f"- fixed_object_ids: `{fixed_object_ids}`",
        "",
    ]
    for outcome in results:
        entry = outcome.entry
        findings = outcome.findings
        selector = _selector_label(entry.scene_id, entry.cut_id)
        lines.extend(
            [
                f"## {selector}",
                "",
                f"- output: `{entry.output}`",
                f"- narration: `{entry.narration}`" if entry.narration else "- narration: `(silent)`",
                f"- overall_score: `{entry.overall_score:.3f}`",
                f"- rubric_scores: `{entry.rubric_scores}`",
            ]
        )
        if not findings:
            lines.extend(["- review: `PASS`", ""])
            continue
        lines.append(f"- agent_review_ok: `{'true' if entry.agent_review_ok else 'false'}`")
        lines.append(f"- human_review_ok: `{'true' if entry.human_review_ok else 'false'}`")
        if entry.human_review_reason:
            lines.append(f"- human_review_reason: `{entry.human_review_reason}`")
        lines.append(f"- review: `{'FAIL' if (not entry.agent_review_ok and not entry.human_review_ok) else 'WARN'}`")
        if entry.agent_review_reason_keys:
            lines.append(f"- agent_review_reason_keys: `{', '.join(entry.agent_review_reason_keys)}`")
        if entry.agent_review_reason_messages:
            lines.append("- agent_review_reason_messages:")
            lines.extend(f"  - `{message}`" for message in entry.agent_review_reason_messages)
        if outcome.suggested_character_ids:
            lines.append(f"- suggested_character_ids: `{', '.join(outcome.suggested_character_ids)}`")
        if outcome.suggested_object_ids:
            lines.append(f"- suggested_object_ids: `{', '.join(outcome.suggested_object_ids)}`")
        for finding in findings:
            lines.append(f"- {finding.code}: {finding.message}")
        lines.append("")
    return "\n".join(lines)


def _replace_yaml_block(text: str, new_yaml: str) -> str:
    return re.sub(r"```yaml\s*\n.*?\n```", f"```yaml\n{new_yaml.rstrip()}\n```", text, count=1, flags=re.S)


def apply_id_fixes(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    results: list[ReviewOutcome],
    fix_character_ids: bool,
    fix_object_ids: bool,
) -> tuple[int, int]:
    if yaml is None:
        raise SystemExit("PyYAML is required for --fix-character-ids/--fix-object-ids.")
    cuts = manifest_image_node_map(manifest)
    fixed_character_ids = 0
    fixed_object_ids = 0
    changed = False
    for outcome in results:
        cut = cuts.get((outcome.entry.scene_id, outcome.entry.cut_id))
        if not isinstance(cut, dict):
            continue
        image_generation = cut.get("image_generation")
        if not isinstance(image_generation, dict):
            continue
        if fix_character_ids and outcome.suggested_character_ids:
            current = list(image_generation.get("character_ids") or [])
            merged = current + [asset_id for asset_id in outcome.suggested_character_ids if asset_id not in current]
            if merged != current:
                image_generation["character_ids"] = merged
                fixed_character_ids += len(merged) - len(current)
                changed = True
        if fix_object_ids and outcome.suggested_object_ids:
            current = list(image_generation.get("object_ids") or [])
            merged = current + [asset_id for asset_id in outcome.suggested_object_ids if asset_id not in current]
            if merged != current:
                image_generation["object_ids"] = merged
                fixed_object_ids += len(merged) - len(current)
                changed = True
    if changed:
        original = manifest_path.read_text(encoding="utf-8")
        new_yaml = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
        manifest_path.write_text(_replace_yaml_block(original, new_yaml), encoding="utf-8")
    return fixed_character_ids, fixed_object_ids


def apply_review_metadata_to_manifest(*, manifest_path: Path, manifest: dict[str, Any], entries: list[PromptEntry]) -> None:
    if yaml is None:
        raise SystemExit("PyYAML is required to write review metadata back into the manifest.")
    nodes = manifest_image_node_map(manifest)
    changed = False
    for entry in entries:
        node = nodes.get((entry.scene_id, entry.cut_id))
        if not isinstance(node, dict):
            continue
        image_generation = node.get("image_generation")
        if not isinstance(image_generation, dict):
            continue
        review = image_generation.get("review") if isinstance(image_generation.get("review"), dict) else {}
        updated_review = {
            "agent_review_ok": bool(entry.agent_review_ok),
            "agent_review_reason_keys": list(entry.agent_review_reason_keys),
            "agent_review_reason_messages": list(entry.agent_review_reason_messages),
            "rubric_scores": dict(entry.rubric_scores),
            "overall_score": round(float(entry.overall_score), 3),
            "human_review_ok": bool(entry.human_review_ok),
            "human_review_reason": entry.human_review_reason or "",
        }
        if review != updated_review:
            image_generation["review"] = updated_review
            changed = True
    if changed:
        original = manifest_path.read_text(encoding="utf-8")
        new_yaml = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
        manifest_path.write_text(_replace_yaml_block(original, new_yaml), encoding="utf-8")


def append_evaluator_state(*, run_dir: Path, outcomes: list[ReviewOutcome], unresolved_entries: int) -> None:
    state_path = run_dir / "state.txt"
    if not state_path.exists() or not outcomes:
        return
    rubric_keys = tuple(IMAGE_REVIEW_RUBRIC_WEIGHTS.keys())
    averages = {
        key: sum(outcome.rubric_scores.get(key, 0.0) for outcome in outcomes) / len(outcomes)
        for key in rubric_keys
    }
    overall_score = sum(outcome.overall_score for outcome in outcomes) / len(outcomes)
    findings_count = sum(len(outcome.findings) for outcome in outcomes)
    updates = {
        "eval.image_prompt.score": f"{overall_score:.4f}",
        "eval.image_prompt.findings": str(findings_count),
        "eval.image_prompt.unresolved_entries": str(unresolved_entries),
    }
    for key, value in averages.items():
        updates[f"eval.image_prompt.rubric.{key}"] = f"{value:.4f}"
    append_state_snapshot(state_path, updates)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review manifest image prompts for story/script consistency.")
    parser.add_argument("--manifest", required=False, help="Path to video_manifest.md")
    parser.add_argument("--prompt-collection", default=None, help="Deprecated compatibility input. When omitted, entries are read directly from the manifest.")
    parser.add_argument("--story", default=None, help="Path to story.md (default: sibling of manifest)")
    parser.add_argument("--script", default=None, help="Path to script.md (default: sibling of manifest)")
    parser.add_argument("--out", default=None, help="Output markdown path (default: sibling image_prompt_story_review.md)")
    parser.add_argument("--fail-on-findings", action="store_true", help="Exit non-zero when review findings exist.")
    parser.add_argument("--fix-character-ids", action="store_true", help="Autofix missing image_generation.character_ids in the manifest.")
    parser.add_argument("--fix-object-ids", action="store_true", help="Autofix missing image_generation.object_ids in the manifest.")
    parser.add_argument("--set-human-review", action="append", default=[], help='Mark scene/cut as human-reviewed, e.g. "scene02_cut01" or "scene3.5_cut04" (repeatable).')
    parser.add_argument("--human-review-value", choices=["true", "false"], default="true", help="Value used with --set-human-review.")
    parser.add_argument(
        "--image-plan-modes",
        default="generate_still",
        help="Comma-separated still_image_plan.mode values to include for story scenes when reading directly from the manifest.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.manifest and not args.prompt_collection:
        raise SystemExit("--manifest is required unless --prompt-collection is provided.")
    manifest_path = Path(args.manifest) if args.manifest else Path(args.prompt_collection).parent / "video_manifest.md"
    prompt_collection_path = Path(args.prompt_collection) if args.prompt_collection else None
    run_dir = manifest_path.parent if args.manifest or manifest_path.exists() else prompt_collection_path.parent
    story_path = Path(args.story) if args.story else run_dir / "story.md"
    script_path = Path(args.script) if args.script else run_dir / "script.md"
    out_path = Path(args.out) if args.out else run_dir / "image_prompt_story_review.md"
    manifest = load_manifest(manifest_path) if manifest_path.exists() else {"scenes": [], "assets": {}}
    if prompt_collection_path:
        entries = parse_prompt_collection(prompt_collection_path.read_text(encoding="utf-8"))
    else:
        entries = manifest_prompt_entries(manifest, allowed_story_modes=_parse_csv_set(args.image_plan_modes))
    if args.set_human_review:
        entries = apply_human_review_updates(entries, args.set_human_review, args.human_review_value == "true")
        if manifest_path.exists():
            apply_review_metadata_to_manifest(manifest_path=manifest_path, manifest=manifest, entries=entries)
            manifest = load_manifest(manifest_path)
        if prompt_collection_path:
            prompt_collection_path.write_text(render_prompt_collection(entries) + "\n", encoding="utf-8")
        if prompt_collection_path and not manifest_path.exists():
            print(prompt_collection_path)
            return 0
    story_text, story_data = load_structured_document(story_path) if story_path.exists() else ("", {})
    script_text, script_data = load_structured_document(script_path) if script_path.exists() else ("", {})
    reveal_constraints = load_script_reveal_constraints(script_path)

    results = review_entries(
        entries,
        manifest=manifest,
        story_scene_map=extract_scene_context_map(story_data),
        script_scene_map=extract_scene_context_map(script_data),
        story_text=story_text,
        script_text=script_text,
        reveal_constraints=reveal_constraints,
    )
    fixed_character_ids = 0
    fixed_object_ids = 0
    if args.fix_character_ids or args.fix_object_ids:
        fixed_character_ids, fixed_object_ids = apply_id_fixes(
            manifest_path=manifest_path,
            manifest=manifest,
            results=results,
            fix_character_ids=bool(args.fix_character_ids),
            fix_object_ids=bool(args.fix_object_ids),
        )
        if fixed_character_ids or fixed_object_ids:
            manifest = load_manifest(manifest_path)
            results = review_entries(
                entries,
                manifest=manifest,
                story_scene_map=extract_scene_context_map(story_data),
                script_scene_map=extract_scene_context_map(script_data),
                story_text=story_text,
                script_text=script_text,
                reveal_constraints=reveal_constraints,
            )
    entries = apply_review_statuses(entries, results)
    if manifest_path.exists():
        apply_review_metadata_to_manifest(manifest_path=manifest_path, manifest=manifest, entries=entries)
        manifest = load_manifest(manifest_path)
    if prompt_collection_path:
        prompt_collection_path.write_text(render_prompt_collection(entries) + "\n", encoding="utf-8")
    outcome_map = {(outcome.entry.scene_id, outcome.entry.cut_id): outcome for outcome in results}
    unresolved_entries = sum(
        1
        for entry in entries
        if outcome_map.get((entry.scene_id, entry.cut_id), None) and outcome_map[(entry.scene_id, entry.cut_id)].findings and not entry.agent_review_ok and not entry.human_review_ok
    )
    hydrated_results: list[ReviewOutcome] = []
    for entry in entries:
        outcome = outcome_map.get((entry.scene_id, entry.cut_id))
        if outcome is None:
            continue
        hydrated_results.append(
            ReviewOutcome(
                entry=entry,
                findings=outcome.findings,
                suggested_character_ids=outcome.suggested_character_ids,
                suggested_object_ids=outcome.suggested_object_ids,
                rubric_scores=outcome.rubric_scores,
                overall_score=outcome.overall_score,
            )
        )
    report = render_report(
        hydrated_results,
        manifest_path=manifest_path,
        fixed_character_ids=fixed_character_ids,
        fixed_object_ids=fixed_object_ids,
        unresolved_entries=unresolved_entries,
    )
    out_path.write_text(report + "\n", encoding="utf-8")
    append_evaluator_state(run_dir=run_dir, outcomes=hydrated_results, unresolved_entries=unresolved_entries)
    print(out_path)
    findings = sum(len(outcome.findings) for outcome in hydrated_results)
    if args.fail_on_findings and findings and unresolved_entries:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
