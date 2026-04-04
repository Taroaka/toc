#!/usr/bin/env python3
"""Review narration text quality for TTS readiness and write statuses back into the manifest."""

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

from toc.harness import append_state_snapshot, load_structured_document
from toc.immersive_manifest import normalize_dotted_id

META_MARKER_RE = re.compile(r"\bTODO\b|\bTBD\b|未記入|要修正|メモ|仮文", re.I)
URL_RE = re.compile(r"https?://|www\.", re.I)
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\([^)]+\)")
BACKTICK_RE = re.compile(r"`[^`]*`")
AUDIO_TAG_RE = re.compile(r"\[[A-Za-z][^\]]*\]")
ASCII_ABBREV_RE = re.compile(r"\b[A-Za-z]{2,}\b")
NUMBER_RE = re.compile(r"\d")
SYMBOL_RE = re.compile(r"%|％|/|://|@|#")
PUNCTUATION_RE = re.compile(r"[、。！？!?…]")
SENTENCE_SPLIT_RE = re.compile(r"[。！？!?]\s*|\n+")
JP_TOKEN_RE = re.compile(r"[一-龯ぁ-んァ-ヶー]{2,}")
HIRAGANA_ONLY_RE = re.compile(r"^[ぁ-ゖーゝゞ\s　、。！？!?…「」『』（）()・，,．.]+$")

VISUAL_DIRECTION_TERMS = (
    "カメラ",
    "画角",
    "ズーム",
    "パン",
    "ティルト",
    "トラック",
    "ドリー",
    "引き",
    "寄り",
    "ロングショット",
    "クローズアップ",
    "テロップ",
    "字幕",
)

OPENING_ABSTRACT_TERMS = (
    "心",
    "こころ",
    "運命",
    "うんめい",
    "意味",
    "いみ",
    "予感",
    "よかん",
    "禁忌",
    "きんき",
    "掟",
    "おきて",
    "視点",
    "本当は",
    "ほんとうは",
    "知らない",
    "しらない",
)

MIDDLE_VALUE_TERMS = (
    "ため",
    "ので",
    "だから",
    "やがて",
    "まだ",
    "不安",
    "迷い",
    "願い",
    "恐れ",
    "決意",
    "後悔",
    "気づ",
)

ENDING_VALUE_TERMS = (
    "ついに",
    "ようやく",
    "帰る",
    "戻る",
    "別れ",
    "失う",
    "残る",
    "教訓",
    "余韻",
    "その後",
)

ENDING_MODE_SIGNAL_MAP = {
    "happy": ("達成", "たっせい", "回復", "かいふく", "祝福", "しゅくふく", "報い", "むくい"),
    "bittersweet": ("失う", "うしなう", "残る", "のこる", "別れ", "わかれ", "余韻", "よいん", "代償", "だいしょう"),
    "tragic": ("失う", "うしなう", "戻らない", "もどらない", "喪失", "そうしつ", "取り返し", "とりかえし", "重い", "おもい"),
    "cautionary": ("代償", "だいしょう", "禁忌", "きんき", "取り返し", "とりかえし", "重い", "おもい", "教訓", "きょうくん"),
    "ambiguous": ("余韻", "よいん", "気配", "けはい", "わからない", "わからぬ", "残る", "のこる"),
}

TOKEN_STOPWORDS = {
    "そして",
    "しかし",
    "そこで",
    "それで",
    "ように",
    "ために",
    "こと",
    "もの",
    "ような",
    "ようだ",
    "ここ",
    "そこ",
    "これ",
    "それ",
    "映像",
    "シーン",
    "登場人物",
    "見せ場",
    "構図",
    "舞台",
    "連続性",
    "禁止",
    "全体",
    "不変条件",
    "小道具",
    "舞台装置",
}

RUBRIC_THRESHOLDS = {
    "tts_readiness": 0.70,
    "story_role_fit": 0.55,
    "anti_redundancy": 0.45,
    "pacing_fit": 0.50,
    "spoken_japanese": 0.60,
}

RUBRIC_WEIGHTS = {
    "tts_readiness": 0.30,
    "story_role_fit": 0.30,
    "anti_redundancy": 0.15,
    "pacing_fit": 0.15,
    "spoken_japanese": 0.10,
}

OPENING_PHASES = {"opening", "setup", "ordinary_world", "call_to_adventure", "inciting_incident", "introduction"}
MIDDLE_PHASES = {"development", "middle", "complication", "conflict", "ordeal", "midpoint", "rising_action"}
ENDING_PHASES = {"ending", "climax", "resolution", "return", "aftermath", "transformation", "denouement"}

SEMANTIC_ANCHOR_MAP = {
    "理由": ("理由", "わけ", "ため", "ので", "だから", "なぜなら", "結果"),
    "原因": ("原因", "理由", "ため", "ので", "引き金"),
    "迷い": ("迷い", "ためらい", "戸惑い", "揺れ", "決めきれ", "踏み切れ"),
    "後悔": ("後悔", "悔い", "悔や", "取り返し"),
    "決意": ("決意", "覚悟", "腹を決め", "誓い"),
    "予感": ("予感", "胸騒ぎ", "気配", "兆し"),
    "禁忌": ("禁忌", "掟", "触れてはならない", "破ってはならない"),
    "約束": ("約束", "誓い", "取り決め"),
    "運命": ("運命", "さだめ", "定め"),
    "意味": ("意味", "象徴", "しるし", "示して", "物語って"),
    "視点": ("見える", "感じる", "気づ", "思える", "彼には", "彼女には"),
    "時間": ("まだ", "やがて", "そのころ", "まもなく", "かつて", "ほどなく"),
    "回想": ("かつて", "あの日", "思い出", "記憶"),
    "内面": ("心", "気持ち", "迷い", "願い", "恐れ", "決意", "後悔"),
    "海を見る": ("海を見る", "海を見つめる", "海へ目を向ける", "沖を見る", "海に目を向ける"),
}


@dataclass(frozen=True)
class NarrationEntry:
    scene_id: str
    cut_id: str | None
    selector: str
    text: str
    tts_text: str
    tool: str
    output: str
    duration_seconds: int | None
    image_prompt: str
    motion_prompt: str
    story_role: str
    phase: str
    scene_summary: str
    script_narration: str
    contract: dict[str, Any]
    agent_review_ok: bool
    human_review_ok: bool
    human_review_reason: str
    agent_review_reason_keys: list[str]
    agent_review_reason_messages: list[str]
    rubric_scores: dict[str, float]
    overall_score: float
    ending_mode: str = ""
    narration_distance_policy: str = ""
    narrative_value_mode: str = ""
    narrative_value_targets: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    code: str
    message: str


@dataclass(frozen=True)
class ReviewOutcome:
    entry: NarrationEntry
    findings: list[Finding]
    rubric_scores: dict[str, float]
    overall_score: float


def _replace_yaml_block(text: str, new_yaml: str) -> str:
    return re.sub(r"```yaml\s*\n.*?\n```", f"```yaml\n{new_yaml.rstrip()}\n```", text, count=1, flags=re.S)


def load_manifest(path: Path) -> dict[str, Any]:
    text, data = load_structured_document(path)
    if not data:
        raise SystemExit(f"Failed to parse structured manifest: {path}")
    return data


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _as_dotted_id(value: Any) -> str | None:
    return normalize_dotted_id(value)


def _selector_label(scene_id: Any, cut_id: Any | None = None) -> str:
    scene = str(_as_dotted_id(scene_id) or "unknown")
    scene_label = f"{int(scene):02d}" if re.fullmatch(r"\d+", scene) else scene
    if cut_id is None:
        return f"scene{scene_label}"
    cut = str(_as_dotted_id(cut_id) or "unknown")
    cut_label = f"{int(cut):02d}" if re.fullmatch(r"\d+", cut) else cut
    return f"scene{scene_label}_cut{cut_label}"


def _phase_to_story_role(phase: str, *, scene_index: int, total_scenes: int) -> str:
    normalized = phase.strip().lower()
    if normalized in OPENING_PHASES:
        return "opening"
    if normalized in MIDDLE_PHASES:
        return "middle"
    if normalized in ENDING_PHASES:
        return "ending"
    if total_scenes <= 0:
        return "middle"
    ratio = scene_index / max(1, total_scenes)
    if ratio < 0.2:
        return "opening"
    if ratio >= 0.8:
        return "ending"
    return "middle"


def load_script_context(script_path: Path) -> dict[str, dict[str, Any]]:
    if not script_path.exists():
        return {}
    _, data = load_structured_document(script_path)
    if not isinstance(data, dict):
        return {}
    script_metadata = data.get("script_metadata") if isinstance(data.get("script_metadata"), dict) else {}
    ending_mode = str(script_metadata.get("ending_mode") or "").strip().lower()
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        return {}

    valid_scenes = [scene for scene in scenes if isinstance(scene, dict) and _as_dotted_id(scene.get("scene_id")) is not None]
    total_scenes = len(valid_scenes)
    context: dict[str, dict[str, Any]] = {}
    for idx, scene in enumerate(valid_scenes):
        scene_id = str(_as_dotted_id(scene.get("scene_id")) or "")
        phase = str(scene.get("phase") or "").strip()
        scene_summary = str(scene.get("scene_summary") or "").strip()
        story_role = _phase_to_story_role(phase, scene_index=idx, total_scenes=total_scenes)
        narration_distance_policy = str(scene.get("narration_distance_policy") or "").strip().lower()
        narrative_value_goal = scene.get("narrative_value_goal") if isinstance(scene.get("narrative_value_goal"), dict) else {}
        narrative_value_mode = str(narrative_value_goal.get("mode") or "").strip().lower()
        narrative_value_targets = tuple(str(v).strip() for v in list(narrative_value_goal.get("leave_viewer_with") or []) if str(v).strip())
        cuts = scene.get("cuts")
        if isinstance(cuts, list) and cuts:
            for cut in cuts:
                if not isinstance(cut, dict):
                    continue
                cut_id = _as_dotted_id(cut.get("cut_id"))
                if cut_id is None:
                    continue
                selector = _selector_label(scene_id, cut_id)
                context[selector] = {
                    "phase": phase,
                    "story_role": story_role,
                    "scene_summary": scene_summary,
                    "script_narration": str(cut.get("narration") or "").strip(),
                    "ending_mode": ending_mode,
                    "narration_distance_policy": narration_distance_policy,
                    "narrative_value_mode": narrative_value_mode,
                    "narrative_value_targets": narrative_value_targets,
                }
            continue
        selector = _selector_label(scene_id)
        context[selector] = {
            "phase": phase,
            "story_role": story_role,
            "scene_summary": scene_summary,
            "script_narration": str(scene.get("narration") or "").strip(),
            "ending_mode": ending_mode,
            "narration_distance_policy": narration_distance_policy,
            "narrative_value_mode": narrative_value_mode,
            "narrative_value_targets": narrative_value_targets,
        }
    return context


def _entry_from_node(
    *,
    scene_id: str,
    cut_id: str | None,
    node: dict[str, Any],
    script_context: dict[str, dict[str, str]],
) -> NarrationEntry | None:
    audio = node.get("audio")
    if not isinstance(audio, dict):
        return None
    narration = audio.get("narration")
    if not isinstance(narration, dict):
        return None
    review = narration.get("review") if isinstance(narration.get("review"), dict) else {}
    image_generation = node.get("image_generation") if isinstance(node.get("image_generation"), dict) else {}
    video_generation = node.get("video_generation") if isinstance(node.get("video_generation"), dict) else {}
    selector = _selector_label(scene_id, cut_id)
    script_data = script_context.get(selector, {})
    scores_raw = review.get("rubric_scores") if isinstance(review.get("rubric_scores"), dict) else {}
    rubric_scores = {str(k): float(v) for k, v in scores_raw.items() if _is_number(v)}
    overall_raw = review.get("overall_score")
    return NarrationEntry(
        scene_id=scene_id,
        cut_id=cut_id,
        selector=selector,
        text=str(narration.get("text") or ""),
        tts_text=str(narration.get("tts_text") or ""),
        tool=str(narration.get("tool") or ""),
        output=str(narration.get("output") or ""),
        duration_seconds=_as_int(video_generation.get("duration_seconds")),
        image_prompt=str(image_generation.get("prompt") or ""),
        motion_prompt=str(video_generation.get("motion_prompt") or ""),
        story_role=str(script_data.get("story_role") or "middle"),
        phase=str(script_data.get("phase") or ""),
        scene_summary=str(script_data.get("scene_summary") or ""),
        script_narration=str(script_data.get("script_narration") or ""),
        contract={
            "target_function": str(((narration.get("contract") or {}) if isinstance(narration.get("contract"), dict) else {}).get("target_function") or ""),
            "must_cover": [str(v).strip() for v in list((((narration.get("contract") or {}) if isinstance(narration.get("contract"), dict) else {}).get("must_cover") or [])) if str(v).strip()],
            "must_avoid": [str(v).strip() for v in list((((narration.get("contract") or {}) if isinstance(narration.get("contract"), dict) else {}).get("must_avoid") or [])) if str(v).strip()],
            "done_when": [str(v).strip() for v in list((((narration.get("contract") or {}) if isinstance(narration.get("contract"), dict) else {}).get("done_when") or [])) if str(v).strip()],
        },
        agent_review_ok=bool(review.get("agent_review_ok", True)),
        human_review_ok=bool(review.get("human_review_ok", False)),
        human_review_reason=str(review.get("human_review_reason") or ""),
        agent_review_reason_keys=[str(v) for v in list(review.get("agent_review_reason_keys") or []) if str(v).strip()],
        agent_review_reason_messages=[str(v) for v in list(review.get("agent_review_reason_messages") or []) if str(v).strip()],
        rubric_scores=rubric_scores,
        overall_score=float(overall_raw) if _is_number(overall_raw) else 1.0,
        ending_mode=str(script_data.get("ending_mode") or ""),
        narration_distance_policy=str(script_data.get("narration_distance_policy") or ""),
        narrative_value_mode=str(script_data.get("narrative_value_mode") or ""),
        narrative_value_targets=tuple(script_data.get("narrative_value_targets") or ()),
    )


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except Exception:
        return False


def manifest_narration_entries(manifest: dict[str, Any], *, script_context: dict[str, dict[str, str]] | None = None) -> list[NarrationEntry]:
    scenes = manifest.get("scenes")
    if not isinstance(scenes, list):
        return []
    script_context = script_context or {}

    entries: list[NarrationEntry] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_id = _as_dotted_id(scene.get("scene_id"))
        if scene_id is None:
            continue

        cuts = scene.get("cuts")
        if isinstance(cuts, list) and cuts:
            for cut in cuts:
                if not isinstance(cut, dict):
                    continue
                cut_id = _as_dotted_id(cut.get("cut_id"))
                if cut_id is None:
                    continue
                entry = _entry_from_node(scene_id=scene_id, cut_id=cut_id, node=cut, script_context=script_context)
                if entry is not None:
                    entries.append(entry)
            continue

        entry = _entry_from_node(scene_id=scene_id, cut_id=None, node=scene, script_context=script_context)
        if entry is not None:
            entries.append(entry)
    return entries


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _extract_tokens(text: str) -> set[str]:
    tokens = {token for token in JP_TOKEN_RE.findall(text) if token not in TOKEN_STOPWORDS}
    return {token for token in tokens if len(token) >= 2}


def _semantic_variants(phrase: str) -> set[str]:
    variants = {phrase}
    if phrase in SEMANTIC_ANCHOR_MAP:
        variants.update(SEMANTIC_ANCHOR_MAP[phrase])
    for token in _extract_tokens(phrase):
        if token in SEMANTIC_ANCHOR_MAP:
            variants.update(SEMANTIC_ANCHOR_MAP[token])
    return {variant for variant in variants if variant}


def _semantic_phrase_match(text: str, phrase: str) -> bool:
    phrase = phrase.strip()
    if not phrase:
        return True
    if phrase in text:
        return True
    normalized_text = _normalize_text(text)
    for variant in _semantic_variants(phrase):
        if variant in text or _normalize_text(variant) in normalized_text:
            return True
    phrase_tokens = _extract_tokens(phrase)
    if not phrase_tokens:
        return False
    expanded_tokens = set(phrase_tokens)
    for token in list(phrase_tokens):
        expanded_tokens.update(_extract_tokens(" ".join(_semantic_variants(token))))
    text_tokens = _extract_tokens(text)
    overlap = expanded_tokens & text_tokens
    return len(overlap) / max(1, len(phrase_tokens)) >= 0.6


def _needs_text_normalization(text: str) -> bool:
    if URL_RE.search(text) or EMAIL_RE.search(text):
        return True
    if NUMBER_RE.search(text):
        return True
    if SYMBOL_RE.search(text):
        return True
    if ASCII_ABBREV_RE.search(text):
        return True
    return False


def _has_long_sentence(text: str) -> bool:
    segments = [segment.strip() for segment in SENTENCE_SPLIT_RE.split(text) if segment.strip()]
    return any(len(segment) >= 48 for segment in segments)


def _needs_pause_punctuation(text: str) -> bool:
    compact = _normalize_text(text)
    if len(compact) < 25:
        return False
    punct_count = len(PUNCTUATION_RE.findall(text))
    return punct_count == 0 or (len(compact) >= 40 and punct_count < 2)


def dedupe_findings(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple[str, str]] = set()
    out: list[Finding] = []
    for finding in findings:
        key = (finding.code, finding.message)
        if key in seen:
            continue
        seen.add(key)
        out.append(finding)
    return out


def _score_tts_readiness(text: str) -> float:
    score = 1.0
    if META_MARKER_RE.search(text):
        score -= 0.45
    if URL_RE.search(text) or EMAIL_RE.search(text) or MARKDOWN_LINK_RE.search(text) or BACKTICK_RE.search(text):
        score -= 0.35
    if AUDIO_TAG_RE.search(text):
        score -= 0.25
    if _needs_text_normalization(text):
        score -= 0.20
    return max(0.0, min(1.0, score))


def _token_alignment_score(text: str, basis: str) -> float:
    text_tokens = _extract_tokens(text)
    basis_tokens = _extract_tokens(basis)
    if not text_tokens:
        return 0.0
    if not basis_tokens:
        return 0.65
    overlap = text_tokens & basis_tokens
    if not overlap:
        return 0.20
    precision = len(overlap) / max(1, len(text_tokens))
    recall = len(overlap) / max(1, len(basis_tokens))
    return max(0.0, min(1.0, (2 * precision * recall) / max(0.0001, precision + recall)))


def _story_basis(entry: NarrationEntry) -> str:
    return "\n".join(part for part in (entry.script_narration, entry.scene_summary) if part)


def _effective_distance_policy(entry: NarrationEntry) -> str:
    policy = entry.narration_distance_policy.strip().lower()
    return policy if policy in {"stay_close", "contextual", "meaning_first"} else ""


def _entry_value_signal(entry: NarrationEntry) -> bool:
    text = entry.text
    if any(_semantic_phrase_match(text, target) for target in entry.narrative_value_targets):
        return True
    mode = entry.ending_mode.strip().lower()
    if mode in ENDING_MODE_SIGNAL_MAP:
        return any(_semantic_phrase_match(text, phrase) for phrase in ENDING_MODE_SIGNAL_MAP[mode])
    return False


def _score_story_role_fit(entry: NarrationEntry) -> float:
    basis = _story_basis(entry)
    score = 0.45 + (_token_alignment_score(entry.text, basis) * 0.55)
    policy = _effective_distance_policy(entry)
    value_signal = _entry_value_signal(entry)
    if entry.story_role == "opening":
        if basis and any(term in entry.text and term not in basis for term in OPENING_ABSTRACT_TERMS):
            score -= 0.25
        if basis and _semantic_phrase_match(entry.text, basis):
            score += 0.10
    elif entry.story_role == "middle":
        if any(term in entry.text for term in MIDDLE_VALUE_TERMS):
            score += 0.10
    elif entry.story_role == "ending":
        if any(term in entry.text for term in ENDING_VALUE_TERMS):
            score += 0.10
        elif basis and _token_alignment_score(entry.text, basis) < 0.35:
            score -= 0.10
    if policy == "meaning_first" and value_signal:
        score += 0.12
    elif policy == "stay_close" and basis and _semantic_phrase_match(entry.text, basis):
        score += 0.05
    return max(0.0, min(1.0, score))


def _score_anti_redundancy(
    text: str,
    image_prompt: str,
    motion_prompt: str,
    story_role: str,
    story_role_fit: float,
    *,
    distance_policy: str,
    value_signal: bool,
) -> float:
    narration_tokens = _extract_tokens(text)
    if not narration_tokens:
        return 0.0
    visual_tokens = _extract_tokens(image_prompt + "\n" + motion_prompt)
    if not visual_tokens:
        return 0.80 if story_role == "opening" else 0.65
    overlap = narration_tokens & visual_tokens
    overlap_ratio = len(overlap) / max(1, len(narration_tokens))
    score = 1.0 - overlap_ratio
    if distance_policy == "stay_close":
        score = max(score, min(1.0, 0.78 + (story_role_fit * 0.12)))
    elif story_role == "opening":
        score = max(score, min(1.0, 0.70 + (story_role_fit * 0.20)))
    elif distance_policy == "contextual" and story_role == "ending":
        score = max(score, 0.50 if value_signal else 0.45)
    elif distance_policy == "meaning_first" and value_signal:
        score = max(score, 0.62)
    elif story_role_fit < RUBRIC_THRESHOLDS["story_role_fit"]:
        score -= 0.10
    return max(0.0, min(1.0, score))


def _score_pacing_fit(text: str, duration_seconds: int | None) -> float:
    compact_len = len(_normalize_text(text))
    punct_count = len(PUNCTUATION_RE.findall(text))
    if duration_seconds is None or duration_seconds <= 0:
        score = 0.75
    else:
        cps = compact_len / max(1, duration_seconds)
        if cps <= 4.8:
            score = 1.0
        elif cps <= 6.0:
            score = 0.80
        elif cps <= 7.0:
            score = 0.55
        else:
            score = 0.25
    if _has_long_sentence(text):
        score -= 0.20
    if punct_count == 0 and compact_len >= 25:
        score -= 0.20
    return max(0.0, min(1.0, score))


def _score_spoken_japanese(text: str) -> float:
    score = 1.0
    if _needs_pause_punctuation(text):
        score -= 0.25
    if any(term in text for term in VISUAL_DIRECTION_TERMS):
        score -= 0.25
    if re.search(r"である。|なのだ。|したのである。", text):
        score -= 0.15
    if META_MARKER_RE.search(text):
        score -= 0.20
    return max(0.0, min(1.0, score))


def score_entry(entry: NarrationEntry) -> tuple[dict[str, float], float]:
    spoken_text = entry.tts_text.strip() or entry.text.strip()
    story_role_fit = _score_story_role_fit(entry)
    distance_policy = _effective_distance_policy(entry)
    value_signal = _entry_value_signal(entry)
    scores = {
        "tts_readiness": _score_tts_readiness(spoken_text),
        "story_role_fit": story_role_fit,
        "anti_redundancy": _score_anti_redundancy(
            entry.text,
            entry.image_prompt,
            entry.motion_prompt,
            entry.story_role,
            story_role_fit,
            distance_policy=distance_policy,
            value_signal=value_signal,
        ),
        "pacing_fit": _score_pacing_fit(spoken_text, entry.duration_seconds),
        "spoken_japanese": _score_spoken_japanese(spoken_text),
    }
    overall = 0.0
    for key, weight in RUBRIC_WEIGHTS.items():
        overall += scores[key] * weight
    return scores, round(overall, 4)


def review_entries(entries: list[NarrationEntry]) -> list[ReviewOutcome]:
    outcomes: list[ReviewOutcome] = []
    for entry in entries:
        findings: list[Finding] = []
        tool = entry.tool.strip().lower()
        text = entry.text.strip()
        spoken_text = entry.tts_text.strip() or text

        if tool in {"silent", "tbd", ""}:
            scores = {key: 1.0 for key in RUBRIC_THRESHOLDS}
            outcomes.append(ReviewOutcome(entry=entry, findings=[], rubric_scores=scores, overall_score=1.0))
            continue

        if not text:
            findings.append(Finding(code="narration_empty", message="narration text is empty for a non-silent narration node."))
            scores = {key: 0.0 for key in RUBRIC_THRESHOLDS}
            outcomes.append(ReviewOutcome(entry=entry, findings=findings, rubric_scores=scores, overall_score=0.0))
            continue

        if tool == "elevenlabs" and not entry.tts_text.strip():
            findings.append(Finding(code="narration_tts_text_missing", message="elevenlabs narration should define audio.narration.tts_text as the hiragana TTS payload."))
        if tool == "elevenlabs" and entry.text.strip() and not HIRAGANA_ONLY_RE.fullmatch(entry.text.strip()):
            findings.append(Finding(code="narration_text_not_hiragana_only", message="audio.narration.text should also be kept in hiragana-only spoken form for the current ElevenLabs workflow."))
        if tool == "elevenlabs" and entry.tts_text.strip() and not HIRAGANA_ONLY_RE.fullmatch(entry.tts_text.strip()):
            findings.append(Finding(code="tts_text_not_hiragana_only", message="audio.narration.tts_text should be written in hiragana-only spoken form for the current ElevenLabs workflow."))

        contract = entry.contract or {}
        target_function = str(contract.get("target_function") or "").strip()
        must_cover = [str(v).strip() for v in list(contract.get("must_cover") or []) if str(v).strip()]
        must_avoid = [str(v).strip() for v in list(contract.get("must_avoid") or []) if str(v).strip()]
        done_when = [str(v).strip() for v in list(contract.get("done_when") or []) if str(v).strip()]
        if not target_function and not must_cover and not must_avoid and not done_when:
            findings.append(Finding(code="narration_contract_missing", message="narration contract is missing; define done criteria before writing narration."))
        if must_cover and not all(_semantic_phrase_match(text, term) for term in must_cover):
            findings.append(Finding(code="narration_contract_must_cover_unmet", message="narration text does not yet cover all required contract points."))
        if must_avoid and any(_semantic_phrase_match(text, term) for term in must_avoid):
            findings.append(Finding(code="narration_contract_must_avoid_violated", message="narration text contains a term or phrasing that the contract marks as avoid."))

        if META_MARKER_RE.search(text) or META_MARKER_RE.search(spoken_text):
            findings.append(Finding(code="narration_contains_meta_marker", message="narration text still contains TODO/TBD or memo-style markers."))
        if URL_RE.search(spoken_text) or EMAIL_RE.search(spoken_text) or MARKDOWN_LINK_RE.search(spoken_text) or BACKTICK_RE.search(spoken_text):
            findings.append(Finding(code="tts_unfriendly_literal", message="narration text includes URL/email/markdown-like literals that should be rewritten for speech."))
        if AUDIO_TAG_RE.search(spoken_text):
            findings.append(Finding(code="unsupported_audio_tag_for_v2", message="narration text includes bracketed audio tags that are unsuitable for the repo's v2 narration path."))
        if _needs_text_normalization(spoken_text):
            findings.append(Finding(code="needs_text_normalization", message="narration text contains raw numbers, ASCII abbreviations, or symbols that should be normalized for TTS."))
        if _has_long_sentence(spoken_text):
            findings.append(Finding(code="sentence_too_long_for_tts", message="narration text contains a long sentence; split it into shorter spoken lines."))
        if _needs_pause_punctuation(spoken_text):
            findings.append(Finding(code="missing_pause_punctuation", message="narration text lacks enough punctuation for stable spoken pacing."))
        if any(term in text for term in VISUAL_DIRECTION_TERMS):
            findings.append(Finding(code="visual_direction_leaked_into_narration", message="narration text includes camera or on-screen direction terms that belong in visual prompts, not TTS text."))

        rubric_scores, overall_score = score_entry(entry)
        if target_function:
            if target_function == "opening_setup" and entry.story_role != "opening":
                findings.append(Finding(code="narration_contract_target_function_unmet", message="target_function=opening_setup is set, but this cut is not being treated as an opening role."))
            elif target_function == "middle_complication" and entry.story_role != "middle":
                findings.append(Finding(code="narration_contract_target_function_unmet", message="target_function=middle_complication is set, but this cut is not being treated as a middle role."))
            elif target_function == "ending_resolution" and entry.story_role != "ending":
                findings.append(Finding(code="narration_contract_target_function_unmet", message="target_function=ending_resolution is set, but this cut is not being treated as an ending role."))
            elif target_function == "time" and not _semantic_phrase_match(text, "時間"):
                findings.append(Finding(code="narration_contract_target_function_unmet", message="target_function=time is set, but the text does not clearly add time-layer information."))
            elif target_function == "causality" and not _semantic_phrase_match(text, "理由"):
                findings.append(Finding(code="narration_contract_target_function_unmet", message="target_function=causality is set, but the text does not clearly add causal information."))
            elif target_function == "inner_state" and not _semantic_phrase_match(text, "内面"):
                findings.append(Finding(code="narration_contract_target_function_unmet", message="target_function=inner_state is set, but the text does not clearly add inner-state information."))
            elif target_function == "viewpoint" and not _semantic_phrase_match(text, "視点"):
                findings.append(Finding(code="narration_contract_target_function_unmet", message="target_function=viewpoint is set, but the text does not clearly add viewpoint framing."))
            elif target_function == "rule" and not (_semantic_phrase_match(text, "禁忌") or _semantic_phrase_match(text, "約束")):
                findings.append(Finding(code="narration_contract_target_function_unmet", message="target_function=rule is set, but the text does not clearly add rule/constraint information."))
            elif target_function == "meaning" and not (_semantic_phrase_match(text, "意味") or _semantic_phrase_match(text, "運命") or _semantic_phrase_match(text, "予感")):
                findings.append(Finding(code="narration_contract_target_function_unmet", message="target_function=meaning is set, but the text does not clearly add meaning-layer information."))
        if rubric_scores["story_role_fit"] < RUBRIC_THRESHOLDS["story_role_fit"]:
            findings.append(Finding(code="narration_story_role_mismatch", message="narration text does not fit the cut's story role well enough; opening cuts should feel stable and scene-faithful, middle cuts should sustain development, and ending cuts should land resolution or lingering aftertaste."))
        distance_policy = _effective_distance_policy(entry)
        if distance_policy != "stay_close" and entry.story_role != "opening" and rubric_scores["anti_redundancy"] < RUBRIC_THRESHOLDS["anti_redundancy"]:
            findings.append(Finding(code="narration_too_visual_redundant", message="narration text overlaps too much with the visual prompt and reads like a visual description."))
        if rubric_scores["pacing_fit"] < RUBRIC_THRESHOLDS["pacing_fit"]:
            findings.append(Finding(code="narration_pacing_mismatch", message="narration density looks mismatched to the cut duration or pause structure."))
        if rubric_scores["spoken_japanese"] < RUBRIC_THRESHOLDS["spoken_japanese"]:
            findings.append(Finding(code="narration_spoken_japanese_weak", message="narration text reads weakly as spoken Japanese for voiceover delivery."))

        outcomes.append(
            ReviewOutcome(
                entry=entry,
                findings=dedupe_findings(findings),
                rubric_scores=rubric_scores,
                overall_score=overall_score,
            )
        )
    return outcomes


def reason_keys_from_findings(findings: list[Finding]) -> list[str]:
    return list(dict.fromkeys(f.code for f in findings))


def reason_messages_from_findings(findings: list[Finding]) -> list[str]:
    return [finding.message.replace("`", "'") for finding in findings]


def apply_review_statuses(entries: list[NarrationEntry], outcomes: list[ReviewOutcome]) -> list[NarrationEntry]:
    outcome_map = {outcome.entry.selector: outcome for outcome in outcomes}
    updated: list[NarrationEntry] = []
    for entry in entries:
        outcome = outcome_map.get(entry.selector)
        findings = outcome.findings if outcome else []
        updated.append(
            NarrationEntry(
                scene_id=entry.scene_id,
                cut_id=entry.cut_id,
                selector=entry.selector,
                text=entry.text,
                tts_text=entry.tts_text,
                tool=entry.tool,
                output=entry.output,
                duration_seconds=entry.duration_seconds,
                image_prompt=entry.image_prompt,
                motion_prompt=entry.motion_prompt,
                story_role=entry.story_role,
                phase=entry.phase,
                scene_summary=entry.scene_summary,
                script_narration=entry.script_narration,
                contract=dict(entry.contract),
                agent_review_ok=not bool(findings),
                human_review_ok=entry.human_review_ok,
                human_review_reason=entry.human_review_reason,
                agent_review_reason_keys=reason_keys_from_findings(findings),
                agent_review_reason_messages=reason_messages_from_findings(findings),
                rubric_scores=dict(outcome.rubric_scores) if outcome else {},
                overall_score=float(outcome.overall_score) if outcome else 1.0,
                ending_mode=entry.ending_mode,
                narration_distance_policy=entry.narration_distance_policy,
                narrative_value_mode=entry.narrative_value_mode,
                narrative_value_targets=entry.narrative_value_targets,
            )
        )
    return updated


def apply_human_review_updates(entries: list[NarrationEntry], selectors: list[str], value: bool) -> list[NarrationEntry]:
    if not selectors:
        return entries
    targets = {selector.strip() for selector in selectors if selector.strip()}
    updated: list[NarrationEntry] = []
    for entry in entries:
        is_target = entry.selector in targets
        human_review_reason = "" if (is_target and not value) else entry.human_review_reason
        updated.append(
            NarrationEntry(
                scene_id=entry.scene_id,
                cut_id=entry.cut_id,
                selector=entry.selector,
                text=entry.text,
                tts_text=entry.tts_text,
                tool=entry.tool,
                output=entry.output,
                duration_seconds=entry.duration_seconds,
                image_prompt=entry.image_prompt,
                motion_prompt=entry.motion_prompt,
                story_role=entry.story_role,
                phase=entry.phase,
                scene_summary=entry.scene_summary,
                script_narration=entry.script_narration,
                contract=dict(entry.contract),
                agent_review_ok=entry.agent_review_ok,
                human_review_ok=value if is_target else entry.human_review_ok,
                human_review_reason=human_review_reason,
                agent_review_reason_keys=entry.agent_review_reason_keys,
                agent_review_reason_messages=entry.agent_review_reason_messages,
                rubric_scores=entry.rubric_scores,
                overall_score=entry.overall_score,
                ending_mode=entry.ending_mode,
                narration_distance_policy=entry.narration_distance_policy,
                narrative_value_mode=entry.narrative_value_mode,
                narrative_value_targets=entry.narrative_value_targets,
            )
        )
    return updated


def narration_node_map(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scenes = manifest.get("scenes")
    if not isinstance(scenes, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_id = _as_dotted_id(scene.get("scene_id"))
        if scene_id is None:
            continue
        cuts = scene.get("cuts")
        if isinstance(cuts, list) and cuts:
            for cut in cuts:
                if not isinstance(cut, dict):
                    continue
                cut_id = _as_dotted_id(cut.get("cut_id"))
                if cut_id is None:
                    continue
                narration = ((cut.get("audio") or {}).get("narration")) if isinstance(cut.get("audio"), dict) else None
                if isinstance(narration, dict):
                    out[_selector_label(scene_id, cut_id)] = narration
            continue
        narration = ((scene.get("audio") or {}).get("narration")) if isinstance(scene.get("audio"), dict) else None
        if isinstance(narration, dict):
            out[_selector_label(scene_id)] = narration
    return out


def apply_review_metadata_to_manifest(*, manifest_path: Path, manifest: dict[str, Any], entries: list[NarrationEntry]) -> None:
    if yaml is None:
        raise SystemExit("PyYAML is required to write review metadata back into the manifest.")
    nodes = narration_node_map(manifest)
    changed = False
    for entry in entries:
        narration = nodes.get(entry.selector)
        if not isinstance(narration, dict):
            continue
        review = narration.get("review") if isinstance(narration.get("review"), dict) else {}
        updated_review = {
            "agent_review_ok": bool(entry.agent_review_ok),
            "agent_review_reason_keys": list(entry.agent_review_reason_keys),
            "agent_review_reason_messages": list(entry.agent_review_reason_messages),
            "human_review_ok": bool(entry.human_review_ok),
            "human_review_reason": entry.human_review_reason or "",
            "rubric_scores": {key: round(float(value), 4) for key, value in entry.rubric_scores.items()},
            "overall_score": round(float(entry.overall_score), 4),
        }
        if review != updated_review:
            narration["review"] = updated_review
            changed = True
    if changed:
        original = manifest_path.read_text(encoding="utf-8")
        new_yaml = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
        manifest_path.write_text(_replace_yaml_block(original, new_yaml), encoding="utf-8")


def render_report(outcomes: list[ReviewOutcome], *, manifest_path: Path, unresolved_entries: int) -> str:
    total = len(outcomes)
    findings_count = sum(len(outcome.findings) for outcome in outcomes)
    warned = sum(1 for outcome in outcomes if outcome.findings)
    status = "FAIL" if unresolved_entries else ("WARN" if findings_count else "PASS")
    lines = [
        "# Narration Text Review",
        "",
        f"- manifest: `{manifest_path}`",
        f"- status: `{status}`",
        f"- reviewed_entries: `{total}`",
        f"- entries_with_findings: `{warned}`",
        f"- findings: `{findings_count}`",
        f"- unresolved_entries: `{unresolved_entries}`",
        "",
    ]
    for outcome in outcomes:
        entry = outcome.entry
        lines.extend(
            [
                f"## {entry.selector}",
                "",
                f"- tool: `{entry.tool or '(unset)'}`",
                f"- output: `{entry.output}`",
                f"- overall_score: `{outcome.overall_score:.2f}`",
                f"- story_role: `{entry.story_role}`",
                f"- rubric_scores: `tts_readiness={outcome.rubric_scores['tts_readiness']:.2f}, story_role_fit={outcome.rubric_scores['story_role_fit']:.2f}, anti_redundancy={outcome.rubric_scores['anti_redundancy']:.2f}, pacing_fit={outcome.rubric_scores['pacing_fit']:.2f}, spoken_japanese={outcome.rubric_scores['spoken_japanese']:.2f}`",
                f"- contract.target_function: `{entry.contract.get('target_function', '')}`",
                f"- text: `{entry.text}`" if entry.text else "- text: ``",
                f"- tts_text: `{entry.tts_text}`" if entry.tts_text else "- tts_text: ``",
            ]
        )
        if not outcome.findings:
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
        for finding in outcome.findings:
            lines.append(f"- {finding.code}: {finding.message}")
        lines.append("")
    return "\n".join(lines)


def append_evaluator_state(*, run_dir: Path, outcomes: list[ReviewOutcome], unresolved_entries: int) -> None:
    state_path = run_dir / "state.txt"
    if not state_path.exists() or not outcomes:
        return
    rubric_keys = ("tts_readiness", "story_role_fit", "anti_redundancy", "pacing_fit", "spoken_japanese")
    averages = {
        key: sum(outcome.rubric_scores.get(key, 0.0) for outcome in outcomes) / len(outcomes)
        for key in rubric_keys
    }
    overall_score = sum(outcome.overall_score for outcome in outcomes) / len(outcomes)
    findings_count = sum(len(outcome.findings) for outcome in outcomes)
    updates = {
        "eval.narration.score": f"{overall_score:.4f}",
        "eval.narration.findings": str(findings_count),
        "eval.narration.unresolved_entries": str(unresolved_entries),
    }
    for key, value in averages.items():
        updates[f"eval.narration.rubric.{key}"] = f"{value:.4f}"
    append_state_snapshot(state_path, updates)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review manifest narration text quality for TTS.")
    parser.add_argument("--manifest", required=True, help="Path to video_manifest.md")
    parser.add_argument("--script", default=None, help="Optional path to sibling script.md used for story-role-aware evaluation.")
    parser.add_argument("--out", default=None, help="Output markdown path (default: sibling narration_text_review.md)")
    parser.add_argument("--fail-on-findings", action="store_true", help="Exit non-zero when unresolved review findings exist.")
    parser.add_argument("--set-human-review", action="append", default=[], help='Mark scene/cut as human-reviewed, e.g. "scene02_cut01" or "scene10".')
    parser.add_argument("--human-review-value", choices=["true", "false"], default="true", help="Value used with --set-human-review.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)
    run_dir = manifest_path.parent
    out_path = Path(args.out) if args.out else run_dir / "narration_text_review.md"
    script_path = Path(args.script) if args.script else run_dir / "script.md"
    manifest = load_manifest(manifest_path)
    script_context = load_script_context(script_path)
    entries = manifest_narration_entries(manifest, script_context=script_context)
    if args.set_human_review:
        entries = apply_human_review_updates(entries, args.set_human_review, args.human_review_value == "true")
        apply_review_metadata_to_manifest(manifest_path=manifest_path, manifest=manifest, entries=entries)
        manifest = load_manifest(manifest_path)

    outcomes = review_entries(entries)
    entries = apply_review_statuses(entries, outcomes)
    apply_review_metadata_to_manifest(manifest_path=manifest_path, manifest=manifest, entries=entries)

    outcome_map = {outcome.entry.selector: outcome for outcome in outcomes}
    hydrated: list[ReviewOutcome] = []
    unresolved_entries = 0
    for entry in entries:
        outcome = outcome_map.get(entry.selector)
        if outcome is None:
            continue
        hydrated.append(
            ReviewOutcome(
                entry=entry,
                findings=outcome.findings,
                rubric_scores=dict(outcome.rubric_scores),
                overall_score=outcome.overall_score,
            )
        )
        if outcome.findings and not entry.agent_review_ok and not entry.human_review_ok:
            unresolved_entries += 1

    report = render_report(hydrated, manifest_path=manifest_path, unresolved_entries=unresolved_entries)
    out_path.write_text(report + "\n", encoding="utf-8")
    append_evaluator_state(run_dir=run_dir, outcomes=hydrated, unresolved_entries=unresolved_entries)
    print(out_path)
    findings = sum(len(outcome.findings) for outcome in hydrated)
    if args.fail_on_findings and findings and unresolved_entries:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
