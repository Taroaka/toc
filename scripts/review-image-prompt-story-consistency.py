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

from toc.harness import extract_yaml_block, load_structured_document  # noqa: E402


PROMPT_ENTRY_RE = re.compile(
    r"^##\s+scene(?P<scene_id>\d+)_cut(?P<cut_id>\d+)\n"
    r"(?P<body>.*?)(?=^##\s+scene\d+_cut\d+\n|\Z)",
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


@dataclass
class PromptEntry:
    scene_id: int
    cut_id: int
    output: str
    narration: str
    rationale: str
    agent_review_ok: bool
    human_review_ok: bool
    human_review_reason: str
    agent_review_reason_keys: list[str]
    agent_review_reason_messages: list[str]
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
                scene_id=int(match.group("scene_id")),
                cut_id=int(match.group("cut_id")),
                output=output,
                narration="" if narration == "(silent)" else narration,
                rationale=rationale,
                agent_review_ok=_extract_bool_bullet(body, "agent_review_ok", True),
                human_review_ok=_extract_bool_bullet(body, "human_review_ok", False),
                human_review_reason=_extract_backtick_bullet(body, "human_review_reason"),
                agent_review_reason_keys=_extract_reason_keys(body),
                agent_review_reason_messages=_extract_reason_messages(body),
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


def extract_scene_context_map(data: dict[str, Any]) -> dict[int, str]:
    context: dict[int, str] = {}
    scenes = data.get("scenes")
    if not isinstance(scenes, list):
        scenes = ((data.get("script") or {}).get("scenes") if isinstance(data.get("script"), dict) else None)
    if not isinstance(scenes, list):
        return context
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        sid = scene.get("scene_id")
        if not isinstance(sid, int):
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


def manifest_cut_map(manifest: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    cuts: dict[tuple[int, int], dict[str, Any]] = {}
    for scene in manifest.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        sid = scene.get("scene_id")
        if not isinstance(sid, int):
            continue
        for cut in scene.get("cuts", []) if isinstance(scene.get("cuts"), list) else []:
            if not isinstance(cut, dict):
                continue
            cid = cut.get("cut_id")
            if isinstance(cid, int):
                cuts[(sid, cid)] = cut
    return cuts


def manifest_image_node_map(manifest: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    nodes: dict[tuple[int, int], dict[str, Any]] = {}
    for scene in manifest.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        sid = scene.get("scene_id")
        if not isinstance(sid, int):
            continue
        cuts = scene.get("cuts")
        if isinstance(cuts, list):
            for cut in cuts:
                if not isinstance(cut, dict):
                    continue
                cid = cut.get("cut_id")
                if isinstance(cid, int):
                    nodes[(sid, cid)] = cut
            continue
        nodes[(sid, 0)] = scene
    return nodes


def _parse_csv_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part.strip().lower() for part in str(value).split(",") if part.strip()}


def _is_reference_output(output: str) -> bool:
    normalized = (output or "").replace("\\", "/")
    return normalized.startswith("assets/characters/") or normalized.startswith("assets/objects/")


def manifest_prompt_entries(manifest: dict[str, Any], *, allowed_story_modes: set[str]) -> list[PromptEntry]:
    entries: list[PromptEntry] = []
    for scene in manifest.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        sid = scene.get("scene_id")
        if not isinstance(sid, int):
            continue
        cuts = scene.get("cuts")
        candidate_nodes: list[tuple[int, dict[str, Any]]] = []
        if isinstance(cuts, list):
            for cut in cuts:
                if not isinstance(cut, dict):
                    continue
                cid = cut.get("cut_id")
                if isinstance(cid, int):
                    candidate_nodes.append((cid, cut))
        else:
            candidate_nodes.append((0, scene))

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
                    prompt=prompt,
                )
            )
    return entries


def find_missing_required_blocks(prompt: str) -> list[str]:
    return missing_required_prompt_blocks(prompt)


def review_entries(
    entries: list[PromptEntry],
    *,
    manifest: dict[str, Any],
    story_scene_map: dict[int, str],
    script_scene_map: dict[int, str],
    story_text: str,
    script_text: str,
) -> list[ReviewOutcome]:
    cuts = manifest_cut_map(manifest)
    aliases = build_asset_aliases(manifest)
    results: list[ReviewOutcome] = []

    for entry in entries:
        cut = cuts.get((entry.scene_id, entry.cut_id), {})
        image_generation = cut.get("image_generation") if isinstance(cut, dict) else {}
        audio = cut.get("audio") if isinstance(cut, dict) else {}
        narration_text = entry.narration or (((audio or {}).get("narration") or {}).get("text") or "")
        local_story = story_scene_map.get(entry.scene_id, "")
        local_script = script_scene_map.get(entry.scene_id, "")
        local_source_text = "\n".join(part for part in [narration_text, local_story, local_script] if part)

        prompt_terms = extract_terms(entry.prompt)
        narration_terms = extract_terms(narration_text)
        character_alias_hits = find_alias_hits(local_source_text, aliases["character"])
        object_alias_hits = find_alias_hits(local_source_text, aliases["object"])
        prompt_character_hits = find_alias_hits(entry.prompt, aliases["character"])
        prompt_object_hits = find_alias_hits(entry.prompt, aliases["object"])

        declared_character_ids = set(image_generation.get("character_ids") or []) if isinstance(image_generation, dict) else set()
        declared_object_ids = set(image_generation.get("object_ids") or []) if isinstance(image_generation, dict) else set()

        findings: list[Finding] = []

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
        if source_relation_hits and not prompt_relation_hits:
            findings.append(
                Finding(
                    code="blocking_drift",
                    message=f"source context implies blocking/action {source_relation_hits!r}, but the prompt body does not preserve that relation.",
                )
            )

        results.append(
            ReviewOutcome(
                entry=entry,
                findings=dedupe_findings(findings),
                suggested_character_ids=sorted(set(character_alias_hits.keys()) - declared_character_ids),
                suggested_object_ids=sorted(set(object_alias_hits.keys()) - declared_object_ids),
            )
        )
    return results


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
        lines.extend(
            [
                f"## scene{entry.scene_id:02d}_cut{entry.cut_id:02d}",
                "",
                f"- output: `{entry.output}`",
                f"- narration: `{entry.narration}`" if entry.narration else "- narration: `(silent)`",
                f"- rationale: `{entry.rationale}`",
                f"- agent_review_ok: `{'true' if entry.agent_review_ok else 'false'}`",
                f"- human_review_ok: `{'true' if entry.human_review_ok else 'false'}`",
                f"- human_review_reason: `{entry.human_review_reason}`",
            ]
        )
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
        agent_review_ok = not bool(outcome and outcome.findings)
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
                prompt=entry.prompt,
            )
        )
    return updated


def apply_human_review_updates(entries: list[PromptEntry], selectors: list[str], value: bool) -> list[PromptEntry]:
    if not selectors:
        return entries
    targets: set[tuple[int, int]] = set()
    for selector in selectors:
        match = re.fullmatch(r"scene(?P<scene_id>\d+)_cut(?P<cut_id>\d+)", selector.strip())
        if not match:
            raise SystemExit(f"Invalid --set-human-review selector: {selector}")
        targets.add((int(match.group("scene_id")), int(match.group("cut_id"))))
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
        f"- unresolved_entries: `{unresolved_entries}`",
        f"- fixed_character_ids: `{fixed_character_ids}`",
        f"- fixed_object_ids: `{fixed_object_ids}`",
        "",
    ]
    for outcome in results:
        entry = outcome.entry
        findings = outcome.findings
        lines.extend(
            [
                f"## scene{entry.scene_id:02d}_cut{entry.cut_id:02d}",
                "",
                f"- output: `{entry.output}`",
                f"- narration: `{entry.narration}`" if entry.narration else "- narration: `(silent)`",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review manifest image prompts for story/script consistency.")
    parser.add_argument("--manifest", required=True, help="Path to video_manifest.md")
    parser.add_argument("--prompt-collection", default=None, help="Deprecated compatibility input. When omitted, entries are read directly from the manifest.")
    parser.add_argument("--story", default=None, help="Path to story.md (default: sibling of manifest)")
    parser.add_argument("--script", default=None, help="Path to script.md (default: sibling of manifest)")
    parser.add_argument("--out", default=None, help="Output markdown path (default: sibling image_prompt_story_review.md)")
    parser.add_argument("--fail-on-findings", action="store_true", help="Exit non-zero when review findings exist.")
    parser.add_argument("--fix-character-ids", action="store_true", help="Autofix missing image_generation.character_ids in the manifest.")
    parser.add_argument("--fix-object-ids", action="store_true", help="Autofix missing image_generation.object_ids in the manifest.")
    parser.add_argument("--set-human-review", action="append", default=[], help='Mark scene/cut as human-reviewed, e.g. "scene02_cut01" (repeatable).')
    parser.add_argument("--human-review-value", choices=["true", "false"], default="true", help="Value used with --set-human-review.")
    parser.add_argument(
        "--image-plan-modes",
        default="generate_still",
        help="Comma-separated still_image_plan.mode values to include for story scenes when reading directly from the manifest.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest_path = Path(args.manifest)
    run_dir = manifest_path.parent
    story_path = Path(args.story) if args.story else run_dir / "story.md"
    script_path = Path(args.script) if args.script else run_dir / "script.md"
    out_path = Path(args.out) if args.out else run_dir / "image_prompt_story_review.md"
    manifest = load_manifest(manifest_path)
    if args.prompt_collection:
        prompt_collection = Path(args.prompt_collection)
        entries = parse_prompt_collection(prompt_collection.read_text(encoding="utf-8"))
    else:
        entries = manifest_prompt_entries(manifest, allowed_story_modes=_parse_csv_set(args.image_plan_modes))
    if args.set_human_review:
        entries = apply_human_review_updates(entries, args.set_human_review, args.human_review_value == "true")
        apply_review_metadata_to_manifest(manifest_path=manifest_path, manifest=manifest, entries=entries)
        manifest = load_manifest(manifest_path)
    story_text, story_data = load_structured_document(story_path) if story_path.exists() else ("", {})
    script_text, script_data = load_structured_document(script_path) if script_path.exists() else ("", {})

    results = review_entries(
        entries,
        manifest=manifest,
        story_scene_map=extract_scene_context_map(story_data),
        script_scene_map=extract_scene_context_map(script_data),
        story_text=story_text,
        script_text=script_text,
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
            )
    entries = apply_review_statuses(entries, results)
    apply_review_metadata_to_manifest(manifest_path=manifest_path, manifest=manifest, entries=entries)
    manifest = load_manifest(manifest_path)
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
    print(out_path)
    findings = sum(len(outcome.findings) for outcome in hydrated_results)
    if args.fail_on_findings and findings and unresolved_entries:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
