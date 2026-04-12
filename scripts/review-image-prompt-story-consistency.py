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
}

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

REQUIRED_PROMPT_BLOCKS = (
    "GLOBAL / INVARIANTS",
    "CHARACTERS",
    "PROPS / SETPIECES",
    "SCENE",
    "CONTINUITY",
    "AVOID",
)

PROMPT_BLOCK_ALIASES = {
    "GLOBAL / INVARIANTS": ["GLOBAL / INVARIANTS", "全体 / 不変条件", "全体/不変条件", "グローバル / 不変条件"],
    "CHARACTERS": ["CHARACTERS", "登場人物", "キャラクター"],
    "PROPS / SETPIECES": ["PROPS / SETPIECES", "小道具 / 舞台装置", "小道具/舞台装置", "プロップ / 舞台装置"],
    "SCENE": ["SCENE", "シーン"],
    "CONTINUITY": ["CONTINUITY", "連続性", "つながり"],
    "AVOID": ["AVOID", "禁止", "避けること", "NG"],
}

PROMPT_BLOCK_LABELS = {
    "GLOBAL / INVARIANTS": "全体 / 不変条件",
    "CHARACTERS": "登場人物",
    "PROPS / SETPIECES": "小道具 / 舞台装置",
    "SCENE": "シーン",
    "CONTINUITY": "連続性",
    "AVOID": "禁止",
}

REQUIRED_PROMPT_BLOCKS = [
    "GLOBAL / INVARIANTS",
    "CHARACTERS",
    "PROPS / SETPIECES",
    "SCENE",
    "CONTINUITY",
    "AVOID",
]

PROMPT_SELF_CONTAINED_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"scene\d+(?:_cut\d+)?", re.I), "prompt references another scene/cut directly."),
    (re.compile(r"前カット|次カット|前scene|次scene|前シーン|次シーン|前の\s*cut|次の\s*cut|前のシーン|次のシーン|前回の?プロンプト|前のprompt|次のprompt", re.I), "prompt depends on another shot or prompt instead of being self-contained."),
    (re.compile(r"rideable", re.I), "prompt uses English term `rideable`; use Japanese such as `騎乗可能` instead."),
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
    re.compile(r"最初の1フレーム"),
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
    "image_prompt_production_readiness_weak",
}

HARD_FINDING_CODES = {
    "image_contract_missing",
    "image_contract_must_include_unmet",
    "missing_required_prompt_block",
    "prompt_not_self_contained",
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
        prompt_match = TEXT_BLOCK_RE.search(body)
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
                prompt=(prompt_match.group("prompt").strip() if prompt_match else ""),
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


def find_prompt_independence_issues(prompt: str) -> list[str]:
    issues: list[str] = []
    for pattern, message in PROMPT_SELF_CONTAINED_PATTERNS:
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
            prompt = str(image_generation.get("prompt") or "").strip()
            output = str(image_generation.get("output") or "").strip()
            if not prompt or not output:
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
                )
            )
    return entries


def find_missing_required_blocks(prompt: str) -> list[str]:
    return missing_required_prompt_blocks(prompt)


def _score_from_count(*, total: int, missing: int) -> float:
    if total <= 0:
        return 1.0
    return max(0.0, min(1.0, (total - missing) / total))


def _contract_string_list(contract: dict[str, Any], key: str) -> list[str]:
    value = contract.get(key)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


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
    length_bonus = 0.05 if len((prompt or "").splitlines()) >= 8 else 0.0
    return round(max(0.0, min(1.0, block_score - issue_penalty + length_bonus)), 3)


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

        findings: list[Finding] = []

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
            violated_avoid = [item for item in must_avoid if item in entry.prompt]
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

        missing_blocks = find_missing_required_blocks(entry.prompt)
        for block in missing_blocks:
            findings.append(
                Finding(
                    code="missing_required_prompt_block",
                    message=f"prompt is missing required block `[{block}]`.",
                )
            )
        for issue in find_prompt_independence_issues(entry.prompt):
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
            independence_issues=find_prompt_independence_issues(entry.prompt),
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
        if entry.agent_review_reason_keys:
            lines.append(f"- agent_review_reason_keys: `{', '.join(entry.agent_review_reason_keys)}`")
        else:
            lines.append("- agent_review_reason_keys: ``")
        lines.append("- agent_review_reason_messages:")
        if entry.agent_review_reason_messages:
            lines.extend(f"  - `{message}`" for message in entry.agent_review_reason_messages)
        else:
            lines.append("  - ``")
        lines.extend(
            [
                "",
                "```text",
                entry.prompt.rstrip(),
                "```",
                "",
            ]
        )
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
