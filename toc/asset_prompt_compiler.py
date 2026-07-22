from __future__ import annotations

import hashlib
import json
from typing import Any


ASSET_PROMPT_POLICY_VERSION = "image_api_prompt_v1"
ASSET_PROMPT_COMPILER_VERSION = "asset_final_image_prompt_compiler_v2"

_ASSET_REUSE_MODES = {"neutral_anchor", "time_variant", "state_variant"}
_SCENE_TIME_MARKERS = (
    "夜明け",
    "朝日",
    "朝の光",
    "昼光",
    "日中",
    "夕方",
    "夕日",
    "日没",
    "夜の",
    "真夜中",
    "深夜",
    "月光",
    "月明かり",
)


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))


def _extra_visual_constraints(entry: dict[str, Any], *, subject: str) -> list[str]:
    visual_spec = entry.get("visual_spec") if isinstance(entry.get("visual_spec"), dict) else {}
    fixed_prompts = [item for item in _text_list(entry.get("fixed_prompts")) if item != subject]
    style = str(visual_spec.get("style") or "").strip()
    lines: list[str] = []
    if fixed_prompts or style:
        lines.extend(["", "[見た目の追加固定条件]"])
        lines.extend(fixed_prompts)
        if style:
            lines.append(f"画調: {style}")
    return lines


def _individual_forbidden(entry: dict[str, Any]) -> list[str]:
    visual_spec = entry.get("visual_spec") if isinstance(entry.get("visual_spec"), dict) else {}
    forbidden = _text_list(visual_spec.get("forbidden"))
    if not forbidden:
        return []
    return ["", "[個別禁止]", "、".join(forbidden)]


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _reuse_contract(entry: dict[str, Any]) -> dict[str, str]:
    raw = _mapping(entry.get("reuse_contract"))
    if not raw:
        return {"mode": "", "time_of_day": "", "derived_from_asset_id": ""}
    mode = str(raw.get("mode") or "").strip()
    time_of_day = str(raw.get("time_of_day") or "").strip()
    derived_from = str(raw.get("derived_from_asset_id") or "").strip()
    if mode not in _ASSET_REUSE_MODES:
        raise ValueError(f"asset_prompt_reuse_mode_invalid:{mode or 'missing'}")
    if mode == "neutral_anchor" and (time_of_day or derived_from):
        raise ValueError("asset_prompt_neutral_anchor_contract_conflict")
    if mode == "time_variant" and (not time_of_day or not derived_from):
        raise ValueError("asset_prompt_time_variant_contract_incomplete")
    if mode == "state_variant" and not derived_from:
        raise ValueError("asset_prompt_state_variant_contract_incomplete")
    return {
        "mode": mode,
        "time_of_day": time_of_day,
        "derived_from_asset_id": derived_from,
    }


def _validate_neutral_asset_lighting(entry: dict[str, Any], reuse: dict[str, str]) -> None:
    if reuse.get("mode") != "neutral_anchor":
        return
    visual_spec = _mapping(entry.get("visual_spec"))
    probe_values = [
        entry.get("generation_prompt"),
        visual_spec.get("subject"),
        *_text_list(entry.get("fixed_prompts")),
    ]
    probe = "\n".join(str(value or "") for value in probe_values)
    for marker in _SCENE_TIME_MARKERS:
        if marker in probe:
            raise ValueError(f"asset_prompt_scene_time_leak:{marker}")


def _reuse_prompt_lines(reuse: dict[str, str], *, asset_type: str) -> list[str]:
    mode = reuse.get("mode") or ""
    if mode == "time_variant":
        reference_label = "場所参照画像" if asset_type == "location_reference" else "対象参照画像"
        return [
            "",
            "[時間帯variant]",
            f"この素材の時間帯は{reuse['time_of_day']}。空の明るさ、自然光と人工光、影、色温度をこの時間帯に整合させる。",
            f"派生元の{reference_label}から形状、空間構造、固定素材を保ち、時間帯と光だけを変更する。",
        ]
    if mode == "state_variant":
        return [
            "",
            "[状態variant]",
            "派生元の対象参照画像から同一性と主要形状を保ち、明示された状態差分だけを変更する。",
        ]
    return []


def _subject_contract(entry: dict[str, Any]) -> tuple[str, int, list[str]]:
    raw = _mapping(entry.get("subject_contract"))
    if not raw:
        return "individual", 1, []
    scope = str(raw.get("identity_scope") or "").strip()
    try:
        count = int(raw.get("subject_count"))
    except (TypeError, ValueError):
        raise ValueError("asset_prompt_subject_count_invalid") from None
    member_ids = _text_list(raw.get("member_ids"))
    if scope not in {"individual", "ensemble"} or count < 1:
        raise ValueError("asset_prompt_subject_contract_invalid")
    if scope == "individual" and count != 1:
        raise ValueError("asset_prompt_character_cardinality_mismatch")
    if scope == "ensemble" and (count < 2 or len(member_ids) != count):
        raise ValueError("asset_prompt_character_cardinality_mismatch")
    return scope, count, member_ids


def _appearance_lines(entry: dict[str, Any], *, fallback_role: str) -> list[str]:
    appearance = _mapping(entry.get("appearance_contract"))
    labels = (
        ("身分", "social_position"),
        ("役割", "occupation_or_role"),
        ("衣装状態", "occasion_or_state"),
        ("シルエット", "silhouette"),
        ("素材", "materials"),
        ("状態", "condition"),
        ("色", "palette"),
        ("避ける衣装", "must_avoid"),
    )
    lines: list[str] = []
    for label, key in labels:
        raw = appearance.get(key)
        if isinstance(raw, list):
            value = "、".join(_text_list(raw))
        else:
            value = str(raw or "").strip()
        if value:
            lines.append(f"{label}: {value}。")
    if not lines:
        lines.append(
            f"衣装は、{fallback_role or '物語上の役割'}と身分が仕立て、素材、装飾量、手入れの状態から読めるものにする。"
        )
    lines.append("後続画像で衣装の主要形状、素材、配色を保つ。")
    return lines


def compile_asset_prompt(
    entry: dict[str, Any],
    *,
    topic_label: str,
    story_time: str = "",
) -> str:
    """Compile one reusable-asset prompt from a canonical asset-plan entry."""

    normalized_time = str(story_time or "").strip()
    time_constraint = (
        f"物語の時代背景は{normalized_time}。衣装、髪型、建築、生活道具、素材、技術水準をこの時代に整合させる。"
        if normalized_time
        else ""
    )
    asset_type = str(entry.get("asset_type") or "").strip()
    reuse = _reuse_contract(entry)
    _validate_neutral_asset_lighting(entry, reuse)
    explicit_prompt = str(entry.get("generation_prompt") or "").strip()
    if explicit_prompt:
        prefixes = []
        if time_constraint and normalized_time not in explicit_prompt:
            prefixes.append(time_constraint)
        reuse_lines = [line for line in _reuse_prompt_lines(reuse, asset_type=asset_type) if line]
        if reuse_lines and reuse.get("time_of_day") not in explicit_prompt:
            prefixes.extend(reuse_lines)
        return "\n\n".join([*prefixes, explicit_prompt]) if prefixes else explicit_prompt

    generation_plan = entry.get("generation_plan") if isinstance(entry.get("generation_plan"), dict) else {}
    reference_inputs = _text_list(generation_plan.get("reference_inputs"))
    visual_spec = entry.get("visual_spec") if isinstance(entry.get("visual_spec"), dict) else {}
    if asset_type == "character_reference":
        identity_scope, subject_count, _member_ids = _subject_contract(entry)
        subject = str(visual_spec.get("subject") or "登場人物の全身参照画像").strip()
        purpose = str(entry.get("story_purpose") or "後続画像で同じ人物として保つ").strip()
        if identity_scope == "ensemble":
            creation_line = f"{subject}。主対象は{subject_count}人の人物群で、{subject_count}人をそれぞれ別人として固定する。"
            views_line = "1枚の横長画像の中に、各人物の正面・側面・背面の全身3ビューを人物ごとに並べた実写キャラクター参照シートとして作る。"
            identity_line = f"{purpose}。{subject_count}人それぞれの顔、髪、体格、衣装を混同せず、後続画像でも同じ組み合わせとして保つ。"
            global_identity_style = "自然な肌。人物ごとに異なる顔、髪型、体格を安定させる。"
        else:
            creation_line = f"{subject}。主対象は人物1人で、場所参照や空の部屋ではない。"
            views_line = "1枚の横長画像の中に、同じ人物の正面・側面・背面の全身3ビューを並べた実写キャラクター参照シートとして作る。"
            identity_line = f"{purpose}。自然な髪、自然な体格。後続画像で同じ顔、髪、体格を保つ。"
            global_identity_style = "自然な肌、同じ顔と髪型。"
        lines = [
            "[全体 / 不変条件]",
            f"実写、シネマティック、全身、頭からつま先まで。{global_identity_style}画面内テキストなし、字幕なし、ロゴなし。",
            *([time_constraint] if time_constraint else []),
            "",
            "[作成するもの]",
            creation_line,
            views_line,
            "",
            "[人物固定]",
            identity_line + " 正面・側面・背面の全身が頭からつま先まで見える。",
        ]
        if reference_inputs:
            lines.extend(
                [
                    "参照画像が渡される場合は、その人物の顔・髪・体格・年齢感を同一人物として維持し、衣装や状態だけを変更する。",
                    "別人の顔、別人の髪型、体格の大きな変化、年齢の変化は失敗。",
                ]
            )
        lines.extend(
            [
                "",
                "[衣装]",
                *_appearance_lines(entry, fallback_role=purpose),
                *_reuse_prompt_lines(reuse, asset_type=asset_type),
                *_extra_visual_constraints(entry, subject=subject),
                "",
                "[禁止]",
                "人物なし、空の部屋、場所だけ、単一ポートレートのみ、顔が読めない構図、アニメ、漫画、イラスト、文字、ロゴ、ウォーターマーク、途中クロップ、低情報量のポスター風。",
                *_individual_forbidden(entry),
            ]
        )
        return "\n".join(lines)

    if asset_type == "location_reference":
        subject = str(visual_spec.get("subject") or "物語の場所参照。人物なし").strip()
        purpose = str(entry.get("story_purpose") or "後続画像で背景、照明、空気感を固定する").strip()
        lines = [
            "[全体 / 不変条件]",
            (
                "実写、シネマティック、広角の環境参照。時間帯variantで指定された光を厳守し、奥行き、触れられる素材感を出す。画面内テキストなし、字幕なし、ロゴなし。"
                if reuse.get("mode") == "time_variant"
                else "実写、シネマティック、広角の環境参照。特定の朝昼夕夜に固定しない中性的な参照照明で、奥行き、触れられる素材感を出す。画面内テキストなし、字幕なし、ロゴなし。"
            ),
            *([time_constraint] if time_constraint else []),
            "",
            "[作成するもの]",
            f"{subject}。{purpose}。",
            "",
            "[場所固定]",
            "人物を主役にしない。床、壁、出入口、光源、質感が読み取れる。映画のロケーションスチルとして成立させる。reusable locationには物語固有の小道具を焼き込まず、必要な小道具は後続画像のobject referenceで別途置く。",
        ]
        lines.extend(_reuse_prompt_lines(reuse, asset_type=asset_type))
        lines.extend(
            [
                *_extra_visual_constraints(entry, subject=subject),
                "",
                "[禁止]",
                "主要人物、全身ポートレート、人物が画面の中心、物語固有の小道具、未承認の証拠アイテム、アニメ、漫画、イラスト、文字、ロゴ、マーク、署名、ウォーターマーク、低情報量、抽象背景だけの画像。",
                *_individual_forbidden(entry),
            ]
        )
        return "\n".join(lines)

    if asset_type == "style_reference":
        subject = str(visual_spec.get("subject") or "物語全体で共有する画調、光、色、質感、レンズ感").strip()
        lines = [
            "[全体 / 不変条件]",
            "後続画像が共有する実写シネマティックなスタイル参照。画面内テキストなし、字幕なし、ロゴなし。",
            *([time_constraint] if time_constraint else []),
            "",
            "[作成するもの]",
            subject,
            *_extra_visual_constraints(entry, subject=subject),
            "",
            "[禁止]",
            "特定人物の主役化、読める文字、字幕、ロゴ、ウォーターマーク、説明的UI。",
            *_individual_forbidden(entry),
        ]
        return "\n".join(lines)

    subject = str(visual_spec.get("subject") or "物語固有の小道具").strip()
    purpose = str(entry.get("story_purpose") or "物語上の役割").strip()
    return "\n".join(
        [
            "[全体 / 不変条件]",
            "実写、シネマティック、精密な素材感と反射。画面内テキストなし、字幕なし、ロゴなし。",
            *([time_constraint] if time_constraint else []),
            "",
            "[作成するもの]",
            f"{subject}。{purpose}として一目で読める。",
            "",
            "[小道具固定]",
            f"{subject}。実物として置ける重量感。",
            *_reuse_prompt_lines(reuse, asset_type=asset_type),
            *_extra_visual_constraints(entry, subject=subject),
            "",
            "[禁止]",
            "玩具風、プラスチック、文字、ロゴ、ウォーターマーク、イラスト、低情報量。",
            *_individual_forbidden(entry),
        ]
    )


def asset_prompt_source_digest(*, prompt: str, output: str, references: list[str]) -> str:
    canonical = json.dumps(
        {
            "source_prompt": str(prompt),
            "output": str(output),
            "references": [str(value) for value in references],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
