from __future__ import annotations

import hashlib
import json
from typing import Any


ASSET_PROMPT_POLICY_VERSION = "image_api_prompt_v1"
ASSET_PROMPT_COMPILER_VERSION = "asset_final_image_prompt_compiler_v4"

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


def _validate_neutral_asset_lighting(
    entry: dict[str, Any], reuse: dict[str, str], *, story_time: str = ""
) -> None:
    if reuse.get("mode") != "neutral_anchor":
        return
    visual_spec = _mapping(entry.get("visual_spec"))
    # The legacy profile adapter embeds the canonical setting verbatim in this
    # period-consistency clause. Its chronology is context, not a light request.
    # Exempt only that exact source-bound clause in descriptive fields; explicit
    # generation instructions and all text outside the clause remain checked.
    context_clause = (
        f"実写映画の同一人物として固定し、{story_time}の衣装・髪型・素材・身分表現を守る"
        if story_time and entry.get("asset_type") == "character_reference"
        else ""
    )
    descriptive_values = [visual_spec.get("subject"), *_text_list(entry.get("fixed_prompts"))]
    probe_values = [str(entry.get("generation_prompt") or "")]
    for value in descriptive_values:
        text = str(value or "")
        if context_clause:
            text = text.replace(context_clause, "")
        probe_values.append(text)
    probe = "\n".join(str(value or "") for value in probe_values)
    for marker in _SCENE_TIME_MARKERS:
        if marker in probe:
            raise ValueError(f"asset_prompt_scene_time_leak:{marker}")


def _reuse_prompt_lines(reuse: dict[str, str], *, asset_type: str) -> list[str]:
    mode = reuse.get("mode") or ""
    if mode == "neutral_anchor":
        return [
            "",
            "[基準参照の照明]",
            "特定の朝昼夕夜に固定しない中性的な参照照明で、形状、素材、配色を読み取れるようにする。",
            "時代背景や物語上の役割に含まれる時間帯の記述を照明指定として使わない。",
        ]
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


_APPEARANCE_LABELS = (
        ("身分", "social_position"),
        ("役割", "occupation_or_role"),
        ("衣装状態", "occasion_or_state"),
        ("年齢感", "age_impression"),
        ("顔立ち", "face_shape"),
        ("髪・毛並みなど", "hair"),
        ("体格・シルエット", "build_silhouette"),
        ("配色・衣装", "palette_costume"),
        ("識別特徴", "identifying_features"),
        ("シルエット", "silhouette"),
        ("素材", "materials"),
        ("状態", "condition"),
        ("色", "palette"),
        ("避ける衣装", "must_avoid"),
    )


def _appearance_value_lines(appearance: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for label, key in _APPEARANCE_LABELS:
        raw = appearance.get(key)
        if isinstance(raw, list):
            value = "、".join(_text_list(raw))
        else:
            value = str(raw or "").strip()
        if value:
            lines.append(f"{label}: {value}。")
    return lines


def _comparison_lines(appearance: dict[str, Any]) -> list[str]:
    lines = []
    for row in appearance.get("intentional_similarities", []) if isinstance(appearance.get("intentional_similarities"), list) else []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("with_name") or row.get("with_id") or "別の人物").strip()
        cues = str(row.get("shared_cues") or "").strip()
        if cues:
            lines.append(f"意図した共通点（{name}）: {cues}。共通点は保つ。")
    for row in appearance.get("distinguish_from", []) if isinstance(appearance.get("distinguish_from"), list) else []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("with_name") or row.get("with_id") or "別の人物").strip()
        differences = str(row.get("visual_differences") or "").strip()
        if differences:
            lines.append(f"混同しやすい{name}との視覚的な区別: {differences}。")
    return lines


def _appearance_lines(entry: dict[str, Any], *, fallback_role: str) -> list[str]:
    appearance = _mapping(entry.get("appearance_contract"))
    if appearance.get("identity_scope") == "ensemble":
        lines = _appearance_value_lines(appearance)
        shared = _mapping(appearance.get("shared_appearance"))
        if shared:
            lines.append("グループで共有する外見: " + "、".join(
                f"{key}: {value}" for key, value in shared.items() if str(value or "").strip()
            ) + "。")
        members = appearance.get("members") if isinstance(appearance.get("members"), list) else []
        for member in members:
            if not isinstance(member, dict):
                continue
            member_name = str(member.get("name") or member.get("member_id") or "group member").strip()
            member_role = str(member.get("role") or "").strip()
            lines.extend([f"[{member_name}の個別デザイン]", f"役割: {member_role or fallback_role}。"])
            lines.extend(_appearance_value_lines(_mapping(member.get("appearance"))))
            lines.extend(_comparison_lines(member))
        if not lines:
            lines.append(f"役割: {fallback_role or '物語上の役割'}。")
        lines.append("各memberの顔・頭部・毛並み/皮膚/羽毛などの個体差を保ち、意図した共通点も残す。")
        return lines

    lines = _appearance_value_lines(appearance)
    lines.extend(_comparison_lines(appearance))
    if not lines:
        lines.append(
            f"衣装は、{fallback_role or '物語上の役割'}と身分が仕立て、素材、装飾量、手入れの状態から読めるものにする。"
        )
    lines.append("後続画像で同一個体の識別特徴、主要な外見、衣装/表面の形状・素材・配色を保つ。")
    return lines


def _state_variant_identity_lines(entry: dict[str, Any]) -> list[str]:
    transition = _mapping(entry.get("state_transition"))
    lines = []
    if str(transition.get("from_state") or "").strip():
        lines.append(f"変化前: {str(transition['from_state']).strip()}。")
    if str(transition.get("to_state") or "").strip():
        lines.append(f"変化後: {str(transition['to_state']).strip()}。")
    lines.append(
        "派生元参照画像は同一人物/個体のidentity anchorとして使う。generation_promptと状態遷移で"
        "明示された特徴変化を優先し、その変更を親参照の見た目で打ち消さない。"
        "変更が指定されていない特徴は参照から連続性を保つ。"
    )
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
    _validate_neutral_asset_lighting(entry, reuse, story_time=normalized_time)
    explicit_prompt = str(entry.get("generation_prompt") or "").strip()
    if explicit_prompt:
        prefixes = []
        if time_constraint and normalized_time not in explicit_prompt:
            prefixes.append(time_constraint)
        reuse_lines = [line for line in _reuse_prompt_lines(reuse, asset_type=asset_type) if line]
        if reuse_lines and not (reuse.get("time_of_day") and reuse.get("time_of_day") in explicit_prompt):
            prefixes.extend(reuse_lines)
        if asset_type == "character_reference" and reuse.get("mode") == "state_variant":
            return "\n\n".join([
                *prefixes,
                explicit_prompt,
                "[状態変化と親参照のidentity continuity]",
                *_state_variant_identity_lines(entry),
            ])
        if asset_type == "character_reference":
            appearance = _mapping(entry.get("appearance_contract"))
            if appearance.get("cast_design_schema_version"):
                identity_lines = _appearance_lines(
                    entry,
                    fallback_role=str(entry.get("story_purpose") or "").strip(),
                )
                suffix = ["[全キャスト比較で決めた個体識別条件]", *identity_lines]
                return "\n\n".join([*prefixes, explicit_prompt, *suffix])
        return "\n\n".join([*prefixes, explicit_prompt]) if prefixes else explicit_prompt

    generation_plan = entry.get("generation_plan") if isinstance(entry.get("generation_plan"), dict) else {}
    reference_inputs = _text_list(generation_plan.get("reference_inputs"))
    visual_spec = entry.get("visual_spec") if isinstance(entry.get("visual_spec"), dict) else {}
    if asset_type == "character_reference":
        identity_scope, subject_count, _member_ids = _subject_contract(entry)
        subject = str(visual_spec.get("subject") or "キャラクターの全体形態が分かる参照画像").strip()
        purpose = str(entry.get("story_purpose") or "後続画像で同じ人物として保つ").strip()
        if identity_scope == "ensemble":
            creation_line = f"{subject}。主対象は{subject_count}体のキャラクター群で、member_idsごとに別々の個体として保つ。"
            views_line = "1枚の横長画像の中に、各memberの正面・側面・背面の全体ビューをmemberごとに並べる。"
            identity_line = f"{purpose}。{subject_count}体それぞれの個体識別特徴、体形、表面、衣装を対応づけ、後続画像でも同じ組み合わせとして保つ。"
            global_identity_style = "memberごとの主要形態と個体識別特徴を安定させる。"
        else:
            creation_line = f"{subject}。主対象はキャラクター1体で、場所参照や空の部屋ではない。"
            views_line = "1枚の横長画像の中に、同一個体の正面・側面・背面の全体ビューを並べた実写キャラクター参照シートとして作る。"
            identity_line = f"{purpose}。後続画像で同じ個体識別特徴、頭部の形、体形、表面と衣装を保つ。"
            global_identity_style = "自然で具体的な素材感。同一個体として識別できる主要形態を固定する。"
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
                    "参照画像が渡される場合は、受け入れ済みの個体識別特徴、種別、頭部/体形、表面を維持し、明示された衣装や状態だけを変更する。",
                    "参照と異なる個体、種別、年齢感、主要形態への変更は失敗。",
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
                "キャラクターなし、空の部屋、場所だけ、単一ポートレートのみ、頭部または主要識別形態が読めない構図、アニメ、漫画、イラスト、文字、ロゴ、ウォーターマーク、途中クロップ、低情報量のポスター風。",
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
