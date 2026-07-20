from __future__ import annotations

import hashlib
import json
from typing import Any


ASSET_PROMPT_POLICY_VERSION = "image_api_prompt_v1"
ASSET_PROMPT_COMPILER_VERSION = "asset_final_image_prompt_compiler_v2"


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
    explicit_prompt = str(entry.get("generation_prompt") or "").strip()
    if explicit_prompt:
        if time_constraint and normalized_time not in explicit_prompt:
            return f"{time_constraint}\n\n{explicit_prompt}"
        return explicit_prompt

    asset_type = str(entry.get("asset_type") or "").strip()
    generation_plan = entry.get("generation_plan") if isinstance(entry.get("generation_plan"), dict) else {}
    reference_inputs = _text_list(generation_plan.get("reference_inputs"))
    visual_spec = entry.get("visual_spec") if isinstance(entry.get("visual_spec"), dict) else {}
    if asset_type == "character_reference":
        subject = str(visual_spec.get("subject") or "登場人物の全身参照画像").strip()
        purpose = str(entry.get("story_purpose") or "後続画像で同じ人物として保つ").strip()
        lines = [
            "[全体 / 不変条件]",
            "実写、シネマティック、全身、頭からつま先まで。自然な肌、同じ顔と髪型。画面内テキストなし、字幕なし、ロゴなし。",
            *([time_constraint] if time_constraint else []),
            "",
            "[作成するもの]",
            f"{subject}。主対象は人物1人で、場所参照や空の部屋ではない。",
            "1枚の横長画像の中に、同じ人物の正面・側面・背面の全身3ビューを並べた実写キャラクター参照シートとして作る。",
            "",
            "[人物固定]",
            f"{purpose}。自然な髪、自然な体格。後続画像で同じ顔、髪、体格を保つ。正面・側面・背面の全身が頭からつま先まで見える。",
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
                f"{topic_label or '物語'}の世界に合う生活感のある衣装。後続画像で顔、髪、体格、衣装の主要形状を保つ。",
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
            "実写、シネマティック、広角の環境参照。指定された時間帯と光を厳守し、奥行き、触れられる素材感を出す。画面内テキストなし、字幕なし、ロゴなし。",
            *([time_constraint] if time_constraint else []),
            "",
            "[作成するもの]",
            f"{subject}。{purpose}。",
            "",
            "[場所固定]",
            "人物を主役にしない。床、壁、出入口、光源、質感が読み取れる。映画のロケーションスチルとして成立させる。reusable locationには物語固有の小道具を焼き込まず、必要な小道具は後続画像のobject referenceで別途置く。",
        ]
        if any(token in subject for token in ("深夜", "夜", "月明かり", "昼光なし", "太陽なし")):
            lines.extend(
                [
                    "",
                    "[時間帯ゲート]",
                    "深夜または夜として生成する。昼、朝、夕焼け、晴天、太陽光、明るい青空、普通の日中の屋外に見える画像は失敗。",
                ]
            )
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
