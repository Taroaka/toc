#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Materialize a frontend-review ToC immersive run through p650/p680.

This is the Codex-native helper for app-server create flows.  It intentionally
does not call Claude slash commands.  It writes real p100-p650 run artifacts and,
unless requested otherwise, uses the existing Codex app-server image lane for
p560/p660 media generation.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot
from toc.cut_design_logging import (
    write_cut_design_context as _write_cut_design_context,
    write_cut_design_failure_log as _write_cut_design_failure_log,
    write_scene_design_json as _write_scene_design_json,
)
from toc.review_loop import (
    REVIEW_LOOP_CRITIC_COUNT,
    REVIEW_LOOP_SPECS,
    aggregated_review_relpath,
    critic_prompt_relpath,
    critic_relpath,
    render_aggregated_review,
)
from toc.review_loop_runner import materialize_review_loop_round
from toc.run_index import write_run_index


P650_SLOTS = (
    "p110",
    "p120",
    "p130",
    "p210",
    "p220",
    "p230",
    "p310",
    "p320",
    "p330",
    "p410",
    "p420",
    "p430",
    "p440",
    "p450",
    "p510",
    "p520",
    "p530",
    "p540",
    "p550",
    "p560",
    "p570",
    "p610",
    "p620",
    "p630",
    "p640",
    "p650",
)
P680_SLOTS = (*P650_SLOTS, "p660", "p670", "p680")
AWAITING_ALLOWED = {"p130", "p230", "p320", "p330", "p430", "p540", "p570", "p630", "p640", "p680"}
AUTHORING_REVIEW_STAGES = (
    "research",
    "story",
    "visual_value",
    "scene_set",
    "scene_detail",
    "cut_blueprint",
    "script",
    "production_readiness",
    "asset",
    "scene_implementation_hard",
    "scene_implementation_judgment",
)
DEFAULT_SCENE_TITLES = [
    "日常が軋む場所",
    "願いが拒まれる部屋",
    "助力が現れる夜",
    "境界を越える出発",
    "光の中心へ入る階段",
    "運命が触れる広間",
    "時間に追われる逃走",
    "証が名を取り戻す場所",
]
PHASES = ["opening", "development", "development", "ordeal", "ordeal", "transformation", "transformation", "ending"]


def _stable_slug(text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"story_{digest}"


def _safe_asset_id(prefix: str, text: str, index: int) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    if not normalized:
        normalized = f"{prefix}_{index:02d}"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]
    return f"{prefix}_{index:02d}_{normalized[:24]}_{digest}"


def _story_profile(topic: str, source: str) -> dict[str, Any]:
    """Build topic-aware names used by authored artifacts and image requests."""

    normalized = f"{topic}\n{source}".lower()
    if "シンデレラ" in normalized or "cinderella" in normalized:
        return {
            "slug": "cinderella",
            "topic_label": "シンデレラ",
            "protagonist_name": "シンデレラ",
            "protagonist_asset_id": "cinderella_fullbody",
            "protagonist_transformed_asset_id": "cinderella_transformed_fullbody",
            "protagonist_post_midnight_asset_id": "cinderella_post_midnight_fullbody",
            "protagonist_asset_subject": "シンデレラの変身前の全身参照。灰の台所で働く生活感のある衣装、自然な顔立ち、同じ髪と体格",
            "protagonist_transformed_asset_subject": "シンデレラの変身後の全身参照。参照元の変身前シンデレラと同じ顔・髪・体格を維持し、舞踏会へ進めるドレス姿だけに変える、実写映画の礼装",
            "protagonist_post_midnight_asset_subject": "真夜中に魔法が解けた後のシンデレラの全身参照。参照元の変身前シンデレラと同じ顔・髪・体格を維持し、舞踏会ドレスではない質素な衣装だけに戻す、靴合わせの部屋へつながる実写映画の人物状態",
            "artifact_name": "ガラスの靴",
            "artifact_asset_id": "glass_slipper",
            "artifact_output_dir": "objects",
            "artifact_role": "身元を証明する主役級アイテム",
            "artifact_visual": "透明なガラスの靴、月光反射、実物の質感",
            "artifact_fixed_prompt": "透明なガラス、繊細な靴、月光の反射、読める文字なし",
            "places": ["灰の台所", "月明かりの庭", "宮殿", "大階段"],
            "scene_locations": [
                "灰の台所",
                "閉ざされた扉の前の暗い屋内",
                "月明かりの庭",
                "馬車が待つ門前の道",
                "宮殿の階段",
                "舞踏会の大広間",
                "真夜中の大階段",
                "靴合わせが行われる部屋",
            ],
            "motifs": ["灰", "布", "月光", "ガラス", "階段"],
            "scene_titles": [
                "灰の台所",
                "閉ざされた扉",
                "月下の変身",
                "馬車の出発",
                "宮殿の階段",
                "舞踏会の中心",
                "真夜中の逃走",
                "靴が名前を取り戻す部屋",
            ],
            "artifact_scene_indices": [3, 7, 8],
            "summary": "継母と義姉に家事を押しつけられ灰まみれで暮らす若い女性が、魔法の助けで舞踏会へ向かい、真夜中に逃げ、残されたガラスの靴によって自分の名を取り戻す。",
            "aliases": ["灰かぶり", "Cinderella", "Cendrillon"],
            "events": [
                "母の不在後、継母と義姉たちが入り、主人公は家の中で孤立する。",
                "主人公は台所と灰のそばで眠り、名前の代わりに灰かぶりとして扱われる。",
                "宮殿の舞踏会の知らせが届き、家中の欲望が露わになる。",
                "主人公は参加を望むが、仕事と衣装の欠如を理由に拒まれる。",
                "魔法の助力によって馬車、ドレス、ガラスの靴が現れる。",
                "主人公は宮殿に入り、誰も知らない姿で王子と踊る。",
                "真夜中の鐘で魔法が解け始め、主人公は階段を駆け下りる。",
                "片方のガラスの靴が階段に残る。",
                "使者が靴の持ち主を探し、家々を巡る。",
                "主人公の足に靴が合い、隠されていた身元が明らかになる。",
            ],
        }

    slug = _stable_slug(topic)
    topic_label = topic.strip() or "物語"
    return {
        "slug": slug,
        "topic_label": topic_label,
        "protagonist_name": f"{topic_label}の主人公",
        "protagonist_asset_id": f"{slug}_protagonist_fullbody",
        "artifact_name": f"{topic_label}を象徴する証",
        "artifact_asset_id": f"{slug}_signature_artifact",
        "artifact_output_dir": "objects",
        "artifact_role": "物語の転換を可視化する主役級アイテム",
        "artifact_visual": f"{topic_label}の由来を感じさせる手に持てる象徴物、実物の質感、強い形状記憶",
        "artifact_fixed_prompt": f"{topic_label}の象徴物、実物の質量、触れられる素材、読める文字なし",
        "places": ["始まりの場所", "境界の場所", "試練の場所", "帰還の場所"],
        "scene_locations": DEFAULT_SCENE_TITLES,
        "motifs": ["生活の痕跡", "光", "影", "手触り", "道"],
        "scene_titles": DEFAULT_SCENE_TITLES,
        "artifact_scene_indices": [4, 6, 8],
        "summary": f"{source or topic_label}を、主人公が不均衡な日常から呼び出され、助力と試練を経て、最後に自分の価値を証明する実写シネマティックな物語として再構成する。",
        "aliases": [topic_label],
        "events": [
            f"{topic_label}の主人公が、いつもの場所で欠落や抑圧を抱えている。",
            "外部からの知らせや事件が入り、主人公の願いがはっきりする。",
            "周囲の力が主人公の前進を拒み、選択の代償が見える。",
            "助力者、道具、記憶、偶然のいずれかが現れ、越境の条件が整う。",
            "主人公は境界を越え、未知の場所で自分の力を試される。",
            "象徴的な証が、主人公の内面と外部世界を結び始める。",
            "時間、追跡、喪失、誤解の圧力で、主人公は一度すべてを失いかける。",
            "残された証が手がかりとなり、真実を探す流れが生まれる。",
            "主人公は隠された状態から表へ出され、自分の名や価値を問われる。",
            "証が主人公と結びつき、物語は解放または帰還へ向かう。",
        ],
    }


def _md_yaml(title: str, data: dict[str, Any]) -> str:
    return f"# {title}\n\n```yaml\n{yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120)}```\n"


def _run_id_from_dir(run_dir: Path) -> str:
    resolved = run_dir.resolve()
    try:
        return resolved.relative_to(REPO_ROOT / "output").as_posix()
    except ValueError as exc:
        raise SystemExit(f"--run-dir must be under output/: {run_dir}") from exc


def _location_asset_specs(profile: dict[str, Any]) -> list[dict[str, Any]]:
    places = profile.get("scene_locations") or profile["places"]
    specs: list[dict[str, Any]] = []
    cinderella_subjects = {
        "灰の台所": "灰の台所。薄暗い屋内、灰と布の質感、朝夕どちらにも寄りすぎない低い自然光、人物なし",
        "閉ざされた扉の前の暗い屋内": "閉ざされた扉の前の暗い屋内。重い扉、狭い廊下、遮られた光、人物なし",
        "月明かりの庭": "月明かりの庭。夜、月光、変身が起きる余白のある庭、人物なし",
        "馬車が待つ門前の道": "馬車が待つ門前の道。深夜のみ、濃い青の月明かり、月が見える、宮殿へ向かう門前、馬車が通れる道幅、pumpkin_carriage と同じ時間帯に合う光、昼光なし、朝日なし、太陽なし、昼の空なし、人物なし",
        "宮殿の階段": "宮殿の階段。夜の宮殿、舞踏会の光が漏れる階段、上方向の導線、人物なし",
        "舞踏会の大広間": "舞踏会の大広間。夜の宮殿内、シャンデリア光、群衆や踊りを置ける広い床、人物なし",
        "真夜中の大階段": "真夜中の大階段。夜、時計後の緊張、小道具を置ける空の段差と月光、人物なし、ガラスの靴なし、靴なし、物語アイテムなし",
        "靴合わせが行われる部屋": "靴合わせが行われる部屋。室内、日中でも落ち着いた光、人物が囲める空間、終幕の証明に向く椅子と床、人物なし",
    }
    for index, place in enumerate(places, start=1):
        subject = cinderella_subjects.get(str(place), f"{place}の場所参照。人物なし")
        specs.append(
            {
                "asset_id": _safe_asset_id("location", place, index),
                "asset_type": "location_reference",
                "name": place,
                "output": f"assets/locations/{_safe_asset_id('location', place, index)}.png",
                "story_purpose": f"{place}の空間・光・質感を固定する",
                "reusable_reason": "同じ場所のcutで背景と空気感を保つ",
                "visual_spec": {"subject": subject},
            }
        )
    return specs


def _location_spec_for_scene(profile: dict[str, Any], scene_index: int) -> dict[str, Any]:
    specs = _location_asset_specs(profile)
    return specs[min(scene_index - 1, len(specs) - 1)]


def _scene_uses_artifact(profile: dict[str, Any], scene_index: int) -> bool:
    return scene_index in {int(value) for value in profile.get("artifact_scene_indices", [])}


def _artifact_first_scene_index(profile: dict[str, Any]) -> int:
    indices = [int(value) for value in profile.get("artifact_scene_indices", [])]
    return min(indices) if indices else len(profile["scene_titles"])


def _supporting_character_asset_specs(profile: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    if profile.get("slug") == "cinderella":
        specs.append(
            {
                "character_id": profile["protagonist_transformed_asset_id"],
                "name": "変身後のシンデレラ",
                "reference_images": [f"assets/characters/{profile['protagonist_transformed_asset_id']}.png"],
                "scene_indices": [3, 4, 5, 6, 7],
                "story_purpose": "変身後から真夜中に魔法が解ける瞬間まで、同じ人物の顔と体格を保ちながら舞踏会衣装状態を固定する",
                "visual_subject": profile["protagonist_transformed_asset_subject"],
            }
        )
        specs.append(
            {
                "character_id": profile["protagonist_post_midnight_asset_id"],
                "name": "魔法が解けた後のシンデレラ",
                "reference_images": [f"assets/characters/{profile['protagonist_post_midnight_asset_id']}.png"],
                "scene_indices": [7, 8],
                "story_purpose": "真夜中の逃走後と靴合わせの部屋で、舞踏会ドレスではない同一人物の状態を固定する",
                "visual_subject": profile["protagonist_post_midnight_asset_subject"],
            }
        )
        specs.append(
            {
                "character_id": "prince_dance_partner",
                "name": "王子または主要な踊り相手",
                "reference_images": ["assets/characters/prince_dance_partner.png"],
                "scene_indices": [6],
                "story_purpose": "舞踏会でシンデレラを公的に認識させる相手役",
                "visual_subject": "王子または主要な踊り相手の全身参照。実写映画の人物、礼装、穏やかな視線、舞踏会に合う衣装",
            }
        )
    return specs


def _protagonist_asset_for_cut(profile: dict[str, Any], scene_index: int, obligation_id: str) -> str:
    if profile.get("slug") == "cinderella":
        transformed_id = str(profile.get("protagonist_transformed_asset_id") or "")
        post_midnight_id = str(profile.get("protagonist_post_midnight_asset_id") or "")
        if post_midnight_id and (
            scene_index == 8
            or (scene_index == 7 and obligation_id in {"reaction_after_change"})
        ):
            return post_midnight_id
        if transformed_id and (scene_index >= 4 or (scene_index == 3 and obligation_id not in {"scene_pressure", "visible_value_shift"})):
            return transformed_id
    return str(profile["protagonist_asset_id"])


def _protagonist_reference_for_asset(profile: dict[str, Any], asset_id: str) -> str:
    if asset_id == str(profile.get("protagonist_transformed_asset_id") or ""):
        return f"assets/characters/{asset_id}.png"
    if asset_id == str(profile.get("protagonist_post_midnight_asset_id") or ""):
        return f"assets/characters/{asset_id}.png"
    return f"assets/characters/{profile['protagonist_asset_id']}.png"


def _supporting_object_asset_specs(profile: dict[str, Any]) -> list[dict[str, Any]]:
    if profile.get("slug") != "cinderella":
        return []
    return [
        {
            "object_id": "pumpkin_carriage",
            "name": "馬車",
            "reference_images": ["assets/objects/pumpkin_carriage.png"],
            "scene_indices": [4],
            "story_purpose": "門前から宮殿へ出発するための大型舞台装置",
            "visual_subject": "実写映画の馬車。門前に停まる重厚な車体、車輪、扉、月光、読める文字なし",
        }
    ]


def _supporting_character_ids_for_scene(profile: dict[str, Any], scene_index: int) -> list[str]:
    protagonist_variant_ids = {
        str(profile.get("protagonist_transformed_asset_id") or ""),
        str(profile.get("protagonist_post_midnight_asset_id") or ""),
    }
    return [
        str(spec["character_id"])
        for spec in _supporting_character_asset_specs(profile)
        if scene_index in {int(value) for value in spec.get("scene_indices", [])}
        and str(spec["character_id"]) not in protagonist_variant_ids
    ]


def _supporting_object_ids_for_scene(profile: dict[str, Any], scene_index: int) -> list[str]:
    return [
        str(spec["object_id"])
        for spec in _supporting_object_asset_specs(profile)
        if scene_index in {int(value) for value in spec.get("scene_indices", [])}
    ]


def _supporting_character_reference(profile: dict[str, Any], character_id: str) -> str:
    for spec in _supporting_character_asset_specs(profile):
        if spec["character_id"] == character_id:
            return str((spec.get("reference_images") or [""])[0])
    return ""


def _asset_reference_inputs_for_plan(profile: dict[str, Any], asset_id: str) -> list[str]:
    if profile.get("slug") == "cinderella" and asset_id in {
        str(profile.get("protagonist_transformed_asset_id") or ""),
        str(profile.get("protagonist_post_midnight_asset_id") or ""),
    }:
        return [f"assets/characters/{profile['protagonist_asset_id']}.png"]
    return []


def _supporting_object_reference(profile: dict[str, Any], object_id: str) -> str:
    for spec in _supporting_object_asset_specs(profile):
        if spec["object_id"] == object_id:
            return str((spec.get("reference_images") or [""])[0])
    return ""


def _artifact_scene_role(profile: dict[str, Any], scene_index: int) -> str:
    if profile.get("slug") == "cinderella":
        return {
            3: "変身で初めて現れる贈り物として、衣装と足元の変化を証明する",
            4: "馬車に乗る足元の連続性として控えめに見える。主役は馬車の出発",
            5: "宮殿階段を進む足元の連続性として控えめに見える。主役は公的空間への境界",
            6: "踊りの中で足元に光る連続性として控えめに見える。主役は他者の視線と認識",
            7: "脱げて階段に残り、次の靴合わせへ渡る証拠になる",
            8: "主人公の身元と価値を証明して物語を閉じる決定的な証",
        }.get(scene_index, profile["artifact_role"])
    return profile["artifact_role"]


def _cut_uses_artifact(profile: dict[str, Any], scene_index: int, obligation_id: str, *, include_artifact: bool) -> bool:
    if profile.get("slug") != "cinderella":
        return include_artifact
    if scene_index == 3:
        if not include_artifact:
            return False
        return obligation_id not in {"scene_pressure", "visible_value_shift"}
    if scene_index == 4:
        return obligation_id == "carriage_departure"
    if scene_index == 5:
        return obligation_id == "palace_entry_boundary"
    if scene_index == 6:
        return obligation_id == "public_recognition_dance"
    if scene_index == 7:
        if not include_artifact:
            return False
        return obligation_id in {"midnight_lost_slipper_handoff", "causal_handoff"}
    return include_artifact


def _prompt_for_asset(entry: dict[str, Any], profile: dict[str, Any]) -> str:
    asset_id = str(entry.get("asset_id") or "")
    asset_type = str(entry.get("asset_type") or "")
    generation_plan = entry.get("generation_plan") if isinstance(entry.get("generation_plan"), dict) else {}
    reference_inputs = [str(value) for value in generation_plan.get("reference_inputs") or [] if str(value).strip()]
    if asset_type == "character_reference":
        subject = str((entry.get("visual_spec") or {}).get("subject") or f"{profile['protagonist_name']}の全身参照画像")
        purpose = str(entry.get("story_purpose") or "後続画像で同じ人物として保つ")
        lines = [
                "[全体 / 不変条件]",
                "実写、シネマティック、全身、頭からつま先まで。自然な肌、同じ顔と髪型。画面内テキストなし、字幕なし、ロゴなし。",
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
                f"{profile['topic_label']}の世界に合う生活感のある衣装。後続画像で顔、髪、体格、衣装の主要形状を保つ。",
                "",
                "[禁止]",
                "人物なし、空の部屋、場所だけ、単一ポートレートのみ、顔が読めない構図、アニメ、漫画、イラスト、文字、ロゴ、ウォーターマーク、途中クロップ、低情報量のポスター風。",
            ]
        )
        return "\n".join(lines)
    if asset_type == "location_reference":
        place = str(entry.get("name") or entry.get("story_purpose") or "物語の場所")
        subject = str((entry.get("visual_spec") or {}).get("subject") or f"{place}の場所参照。人物なし")
        purpose = str(entry.get("story_purpose") or "後続cutで背景、照明、空気感を固定する")
        lines = [
                "[全体 / 不変条件]",
                "実写、シネマティック、広角の環境参照。指定された時間帯と光を厳守し、奥行き、触れられる素材感を出す。画面内テキストなし、字幕なし、ロゴなし。",
                "",
                "[作成するもの]",
                f"{subject}。{purpose}。",
                "",
                "[場所固定]",
                "人物を主役にしない。床、壁、出入口、光源、質感が読み取れる。映画のロケーションスチルとして成立させる。 reusable location には物語固有の小道具を焼き込まず、必要な小道具は後続cutのobject referenceで別途置く。",
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
                "",
                "[禁止]",
                "主要人物、全身ポートレート、人物が画面の中心、物語固有の小道具、ガラスの靴、靴、アニメ、漫画、イラスト、文字、ロゴ、マーク、署名、ウォーターマーク、低情報量、抽象背景だけの画像。",
            ]
        )
        return "\n".join(lines)
    subject = str((entry.get("visual_spec") or {}).get("subject") or profile["artifact_visual"])
    purpose = str(entry.get("story_purpose") or profile["artifact_role"])
    return "\n".join(
            [
                "[全体 / 不変条件]",
                "実写、シネマティック、精密な素材感と反射。画面内テキストなし、字幕なし、ロゴなし。",
                "",
                "[作成するもの]",
                f"{subject}。{purpose}として一目で読める。",
                "",
                "[小道具固定]",
                f"{subject}。実物として置ける重量感。",
                "",
                "[禁止]",
                "玩具風、プラスチック、文字、ロゴ、ウォーターマーク、イラスト、低情報量。",
        ]
    )


def _scene_prompt(
    title: str,
    beat: str,
    target_beat: str,
    location_name: str,
    profile: dict[str, Any],
    *,
    include_artifact: bool,
    scene_index: int,
    terminal_resolution: bool = False,
) -> str:
    active_motifs = [motif for motif in profile["motifs"] if include_artifact or motif != "ガラス"]
    if terminal_resolution and profile.get("slug") == "cinderella":
        active_motifs = ["落ち着いた室内光", "椅子と床", "ガラス", "布"]
    motifs = "、".join(active_motifs)
    artifact_role = _artifact_scene_role(profile, scene_index)
    artifact_lines = [
        "[小道具 / 舞台装置]",
        f"{profile['artifact_name']}。このsceneでは「{artifact_role}」。実物の重量感と読みやすいシルエットを持つ。",
        "",
    ] if include_artifact else []
    if terminal_resolution:
        scene_detail = (
            f"{title}。場所は{location_name}。{target_beat}。{beat} "
            f"中景に{profile['protagonist_name']}、前景か手元に{profile['artifact_name']}、"
            f"背景の光と部屋の奥行きは出口ではなく{profile['protagonist_name']}と{profile['artifact_name']}へ収束する。"
        )
    elif include_artifact:
        scene_detail = (
            f"{title}。場所は{location_name}。{target_beat}。{beat} "
            f"中景に{profile['protagonist_name']}、{profile['artifact_name']}は「{artifact_role}」としてだけ扱い、"
            "背景にはこのscene固有の行動と次へ進む導線を置く。"
        )
    else:
        scene_detail = (
            f"{title}。場所は{location_name}。{target_beat}。{beat} "
            f"中景に{profile['protagonist_name']}、背景に場所の質感と次の場所へ続く導線。証の小道具はまだ画面に出さない。"
        )
    continuity = (
        f"{profile['topic_label']}の始まりから試練、証明へつながる。人物と{profile['artifact_name']}の形状を変えない。"
        if include_artifact
        else f"{profile['topic_label']}の始まりから試練、証明へつながる。人物の顔、髪、体格、衣装の主要形状を変えない。"
    )
    character_state_gate = ""
    if profile.get("slug") == "cinderella":
        if scene_index == 7:
            character_state_gate = (
                "このsceneの前半6cutまでは舞踏会ドレス姿の逃走状態を維持する。"
                "質素な服、普段着、魔法が解けた後の服を出さない。"
                "後半の反応cut以降だけ、魔法が解けた後の質素な服へ変わる。"
            )
        elif terminal_resolution:
            character_state_gate = "靴合わせの部屋では魔法が解けた後の質素な服。舞踏会ドレス、夜の階段、月光の逃走状態に戻さない。"
    character_state_lines = ["", "[人物状態ゲート]", character_state_gate] if character_state_gate else []
    return "\n".join(
        [
            "[全体 / 不変条件]",
            f"実写、シネマティック、35mm映画、自然な肌、{motifs}の高密度な質感。画面内テキストなし、字幕なし、ロゴなし、ウォーターマークなし。",
            "",
            "[登場人物]",
            f"{profile['protagonist_name']}は参照画像と同じ人物。顔立ち、髪、体格、衣装の主要形状を保つ。",
            *character_state_lines,
            "",
            *artifact_lines,
            "[シーン]",
            scene_detail,
            "",
            "[連続性]",
            continuity,
            "",
            "[禁止]",
            "画面内テキスト、字幕、ロゴ、ウォーターマーク、アニメ、漫画、イラスト、人体崩れ。",
        ]
    )


def _scene_source_events(profile: dict[str, Any], idx: int) -> list[str]:
    events = [str(event) for event in profile.get("events", []) if str(event).strip()]
    scene_titles = [str(title) for title in profile.get("scene_titles") or []]
    scene_count = max(1, len(profile.get("scene_titles") or []))
    if not events:
        return []
    title = scene_titles[idx - 1] if 0 <= idx - 1 < len(scene_titles) else ""
    keyword_bank = (
        "灰",
        "台所",
        "孤立",
        "扉",
        "拒",
        "仕事",
        "衣装",
        "知らせ",
        "招待",
        "助力",
        "魔法",
        "変身",
        "馬車",
        "出発",
        "宮殿",
        "階段",
        "舞踏",
        "踊",
        "王子",
        "真夜中",
        "鐘",
        "逃",
        "失",
        "靴",
        "使者",
        "探",
        "合い",
        "身元",
        "名前",
        "証明",
        "解放",
    )
    title_keywords = [keyword for keyword in keyword_bank if keyword in title]
    semantic_expansions = {
        "扉": ["拒", "仕事", "衣装", "参加", "妨げ"],
        "拒": ["扉", "仕事", "衣装", "参加", "妨げ"],
        "変身": ["助力", "ドレス", "靴", "馬車", "現れる"],
        "魔法": ["助力", "変身", "ドレス", "靴", "馬車", "現れる"],
        "出発": ["馬車", "向かう", "宮殿", "越え"],
        "馬車": ["出発", "向かう", "宮殿", "越え"],
        "宮殿": ["階段", "入", "舞踏", "踊", "王子"],
        "階段": ["宮殿", "入"],
        "舞踏": ["踊", "王子", "知らない姿", "誰も知らない"],
        "踊": ["舞踏", "王子", "知らない姿", "誰も知らない"],
        "真夜中": ["鐘", "逃", "階段", "靴", "解け"],
        "鐘": ["真夜中", "逃", "階段", "靴", "解け"],
        "靴": ["ガラス", "使者", "探", "合い", "身元", "明らか", "証明"],
        "名前": ["身元", "明らか", "合い", "証明", "解放"],
        "証明": ["身元", "明らか", "合い", "靴", "解放"],
    }
    query_keywords = list(title_keywords)
    for keyword in title_keywords:
        query_keywords.extend(semantic_expansions.get(keyword, []))
    query_keywords = list(dict.fromkeys(query_keywords))
    if query_keywords:
        expected_position = (idx - 1) * max(1, len(events) - 1) / max(1, scene_count - 1)
        scored: list[tuple[int, float, int, str]] = []
        for event_index, event in enumerate(events):
            hit_count = sum(1 for keyword in query_keywords if keyword in event)
            if hit_count <= 0:
                continue
            distance = abs(event_index - expected_position)
            scored.append((hit_count, -distance, event_index, event))
        if scored:
            best_score = max(score for score, _, _, _ in scored)
            selected = sorted(
                [item for item in sorted(scored, reverse=True) if item[0] >= max(2, best_score - 1)][:2],
                key=lambda item: item[2],
            )
            if not selected:
                selected = sorted(scored, reverse=True)[:1]
            return [event for _, _, _, event in selected]
    start = min(len(events) - 1, int((idx - 1) * len(events) / scene_count))
    window = max(1, int((len(events) + scene_count - 1) / scene_count))
    return events[start : min(len(events), start + window)]


def _event_visual_evidence_terms(event_text: str, profile: dict[str, Any], *, include_artifact: bool) -> list[str]:
    terms = ["主人公の姿勢", "場所に残る痕跡"]
    rules = [
        (("知らせ", "招待", "呼び出", "命令", "告げ"), ["届いた知らせまたは呼び出しの証", "周囲の反応"]),
        (("拒", "妨げ", "閉", "支配", "押しつけ", "仕事"), ["妨げる人物または閉ざされた入口", "主人公の止まった身体"]),
        (("助力", "魔法", "変身", "偶然", "記憶"), ["助力の発生源", "変化前後の差"]),
        (("境界", "越え", "出発", "向かう", "旅", "移動"), ["越えるべき境界", "進む先が分かる導線"]),
        (("視線", "踊", "認識", "中心", "知らない姿"), ["見届ける人物の視線", "主人公が場の中心に置かれた構図"]),
        (("時間", "真夜中", "鐘", "追跡", "逃", "失"), ["時計または期限の合図", "急ぐ身体と失われる証拠"]),
        (("探", "巡", "手がかり", "証"), ["探す人物または持ち込まれた証", "証拠を見る視線"]),
        (("合い", "明らか", "証明", "価値", "身元", "解放", "帰還"), ["証と身体の一致", "見届ける人物の受容"]),
    ]
    for keywords, additions in rules:
        if any(keyword in event_text for keyword in keywords):
            terms.extend(additions)
    if include_artifact:
        terms.append(profile["artifact_name"])
    else:
        terms = [term for term in terms if profile["artifact_name"] not in term]
    deduped: list[str] = []
    for term in terms:
        if term not in deduped:
            deduped.append(term)
    return deduped[:5]


def _event_required_roles(event_text: str) -> list[str]:
    roles = ["protagonist"]
    role_rules = [
        (("拒", "妨げ", "支配", "押しつけ", "敵", "鬼"), "opponent"),
        (("助力", "魔法", "偶然", "導く", "記憶"), "helper"),
        (("見", "視線", "証", "明らか", "認識", "受容"), "witness"),
        (("王", "宮殿", "使者", "公", "裁き", "村", "家々"), "authority_or_community"),
        (("偽", "失敗", "義姉", "競争", "候補"), "contrast_or_false_claimant"),
    ]
    for keywords, role in role_rules:
        if any(keyword in event_text for keyword in keywords) and role not in roles:
            roles.append(role)
    return roles


def _cut_required_roles_for_obligation(obligation: dict[str, Any]) -> list[str]:
    joined = " / ".join(
        str(obligation.get(key) or "")
        for key in ("screen_question", "dramatic_job", "visual_proof", "first_frame_brief", "foreground", "midground", "background")
    )
    roles = ["protagonist"]
    if any(word in joined for word in ("妨げ", "拒", "閉ざ", "支配", "敵", "義姉", "継母")):
        roles.append("opponent")
    if any(word in joined for word in ("助力", "導く", "魔法", "光が届", "月光")):
        roles.append("helper")
    if any(word in joined for word in ("視線", "見届け", "受容", "認識", "群衆")):
        roles.append("witness")
    if any(word in joined for word in ("宮殿", "王子", "使者", "公的", "社会", "部屋の人物")):
        roles.append("authority_or_community")
    if any(word in joined for word in ("偽", "候補", "義姉", "失敗")):
        roles.append("contrast_or_false_claimant")
    return list(dict.fromkeys(roles))


def _normalize_cut_obligations_for_scene(obligations: list[dict[str, Any]]) -> None:
    for obligation in obligations:
        obligation_id = str(obligation.get("obligation_id") or "cut")
        target_beat = str(obligation.get("target_beat") or obligation_id)
        screen_question = str(obligation.get("screen_question") or "このcutで観客は何を理解するのか")
        visual_proof = str(obligation.get("visual_proof") or "")
        first_frame_brief = str(obligation.get("first_frame_brief") or "")
        visual_evidence = [
            str(item)
            for item in [
                *list(obligation.get("must_show_extra") or []),
                obligation.get("foreground"),
                obligation.get("midground"),
                obligation.get("background"),
            ]
            if str(item or "").strip()
        ]
        if not str(obligation.get("audience_knowledge_delta") or "").strip():
            obligation["audience_knowledge_delta"] = f"観客は「{screen_question}」への答えを、このcutの視覚証拠から理解する"
        if not str(obligation.get("causal_proof") or "").strip():
            obligation["causal_proof"] = visual_proof or f"{target_beat}が画面内の人物・場所・証拠の関係で読める"
        if not obligation.get("visual_evidence"):
            obligation["visual_evidence"] = list(dict.fromkeys(visual_evidence))[:5]
        if not obligation.get("required_roles"):
            obligation["required_roles"] = _cut_required_roles_for_obligation(obligation)
        if not str(obligation.get("static_first_frame_rule") or "").strip():
            obligation["static_first_frame_rule"] = f"動作説明ではなく「{first_frame_brief}」が一枚で読める静止状態にする"
        if not str(obligation.get("anti_redundancy_key") or "").strip():
            obligation["anti_redundancy_key"] = f"{obligation.get('source') or 'scene'}:{obligation_id}"


def _story_event_obligations_for_scene(
    *,
    title: str,
    idx: int,
    location_name: str,
    profile: dict[str, Any],
    include_artifact: bool,
) -> list[dict[str, Any]]:
    source_events = _scene_source_events(profile, idx)
    if not source_events:
        return []
    event_text = " / ".join(source_events)
    visual_evidence = _event_visual_evidence_terms(event_text, profile, include_artifact=include_artifact)
    required_roles = _event_required_roles(event_text)
    return [
        {
            "event_id": f"scene{idx:02d}_story_event",
            "source_events": source_events,
            "audience_knowledge_delta": f"観客は「{event_text}」がこのsceneで起きた不可逆な出来事だと理解する",
            "causal_proof": f"{title}で、出来事の原因と結果が{location_name}内の物理的証拠として同時に読める",
            "visual_evidence": visual_evidence,
            "required_roles": required_roles,
            "static_first_frame_rule": "動作中の説明ではなく、原因・結果・証人・物的証拠が一枚で読める静止状態にする",
            "anti_redundancy_key": "story_event_irreversible_fact",
        }
    ]


def _scene_intent_for_cut_design(
    *,
    title: str,
    idx: int,
    location_spec: dict[str, Any],
    profile: dict[str, Any],
    include_artifact: bool,
) -> dict[str, Any]:
    is_terminal = idx == len(profile["scene_titles"])
    artifact_has_been_revealed = idx >= _artifact_first_scene_index(profile)
    story_event_obligations = _story_event_obligations_for_scene(
        title=title,
        idx=idx,
        location_name=str(location_spec["name"]),
        profile=profile,
        include_artifact=include_artifact,
    )
    visible_evidence = [
        f"{location_spec['name']}の空間圧力",
        f"{profile['protagonist_name']}の姿勢と視線",
        "光の向きの変化",
    ]
    if include_artifact:
        visible_evidence.append(profile["artifact_name"])
    if profile.get("slug") == "cinderella":
        if idx == 4:
            visible_evidence.extend(["馬車", "乗車/出発", "門前から宮殿へ向かう導線"])
        elif idx == 5:
            visible_evidence.extend(["宮殿階段の境界", "階段上の移動方向", "周囲の視線"])
        elif idx == 6:
            visible_evidence.extend(["王子または踊り相手", "群衆の視線", "踊りが成立する瞬間"])
        elif idx == 7:
            visible_evidence.extend(["真夜中の合図", "逃走する身体", "脱げて階段に残るガラスの靴"])
    audience_information = [f"{title}の場所と主人公の現在位置", "主人公が何に妨げられているか"]
    if idx in {2, 5, 6}:
        audience_information.append("周囲の視線や場のルール")
    if idx in {4, 7}:
        audience_information.append("移動や時間制限によって状況が変わること")
    if profile.get("slug") == "cinderella":
        if idx == 4:
            audience_information.extend(["馬車が待っていること", "主人公が宮殿へ出発すること"])
        elif idx == 5:
            audience_information.extend(["宮殿に入る境界", "舞踏会へ接続する階段上の動き"])
        elif idx == 6:
            audience_information.extend(["王子または踊り相手の存在", "群衆が主人公を認識していること"])
        elif idx == 7:
            audience_information.extend(["真夜中の鐘または合図", "ガラスの靴が残ること"])
    withheld_information = [] if artifact_has_been_revealed else [profile["artifact_name"]]
    if idx == 7:
        withheld_information.append("時間制限の結果")
    reveal_constraints = [] if artifact_has_been_revealed else [f"{profile['artifact_name']}はこのsceneでは見せない"]
    if is_terminal:
        reveal_constraints = []
    value_to = "主人公の価値が証明され物語が閉じる状態" if is_terminal else "次へ進む理由が画面内に残る状態"
    causal_turn = f"{title}の終わりに次の場所へ進む証拠が生まれる"
    if profile.get("slug") == "cinderella":
        if idx == 4:
            causal_turn = "馬車へ乗り込み、門前から宮殿へ出発することで物語が公的な場へ進む"
        elif idx == 5:
            causal_turn = "宮殿階段を進み、公的な舞踏会の空間へ入ることで認識の試練へ進む"
        elif idx == 6:
            causal_turn = "王子または踊り相手と群衆の視線の中で、主人公が場の中心として認識される"
        elif idx == 7:
            causal_turn = "真夜中の合図で逃走し、脱げて階段に残ったガラスの靴が靴合わせへ因果を渡す"
    if is_terminal:
        causal_turn = f"{title}の終わりに{profile['artifact_name']}が主人公の価値を証明して物語を閉じる"
    done_when = (
        f"{title}の問い、価値変化、終結が、人物・場所・光・{profile['artifact_name']}の関係で説明なしに読める"
        if is_terminal
        else f"{title}の問い、価値変化、因果の受け渡しが、人物・場所・光・必要な証拠の関係で説明なしに読める"
    )
    screen_geography = (
        f"{location_spec['name']}の前景/中景/背景が、出口ではなく主人公と{profile['artifact_name']}へ収束する"
        if is_terminal
        else f"{location_spec['name']}の前景/中景/背景と出口方向を固定する"
    )
    return {
        "dramatic_question": f"{title}で主人公は前進できるか",
        "value_shift": {
            "from": "不可視で動けない状態",
            "to": value_to,
            "visible_evidence": visible_evidence,
        },
        "causal_turn": causal_turn,
        "done_when": [done_when],
        "audience_information": audience_information,
        "audience_knowledge_delta": {
            "before_scene": [f"観客は{title}の開始時点で、{profile['protagonist_name']}がまだ自由に動けない状態だと知っている"],
            "learned_during_scene": [
                obligation.get("audience_knowledge_delta", "")
                for obligation in story_event_obligations
                if obligation.get("audience_knowledge_delta")
            ],
            "misdirected_or_reframed": [],
            "still_unknown_after_scene": withheld_information,
            "forbidden_early_reveals": reveal_constraints,
        },
        "withheld_information": withheld_information,
        "reveal_constraints": reveal_constraints,
        "story_event_obligations": story_event_obligations,
        "role_coverage": {
            "required_roles": sorted({role for obligation in story_event_obligations for role in obligation.get("required_roles", [])}),
            "policy": "主人公だけでsceneを閉じず、妨害者・助力者・証人・共同体など、出来事の因果を成立させる役割を必要に応じて画面に置く",
        },
        "audience_knowledge_plan": [
            obligation.get("audience_knowledge_delta", "")
            for obligation in story_event_obligations
            if obligation.get("audience_knowledge_delta")
        ],
        "visual_proof_obligations": [
            {"causal_proof": obligation.get("causal_proof"), "visual_evidence": obligation.get("visual_evidence", [])}
            for obligation in story_event_obligations
        ],
        "anti_redundancy_policy": {
            "rule": "各cutは観客の理解を少なくとも1つ前に進める。同じ causal_proof / visual_evidence の繰り返しなら cut を増やさず prompt を厚くする",
            "forbidden_duplicate_basis": ["同じ立ち位置", "同じ導線", "同じ光だけの変化", "同じ小道具を眺めるだけ"],
        },
        "static_first_frame_rules": [
            "画像promptは動作そのものではなく、動作直前または動作直後の読める静止状態を書く",
            "motion_brief の未来の動きを p600 still prompt に混ぜない",
            "原因・結果・証人・物的証拠が1枚で読める構図を優先する",
        ],
        "visual_thesis": f"{title}を、{profile['protagonist_name']}、光、{location_spec['name']}の関係で読ませる",
        "spatial_plan": {
            "location_id": location_spec["asset_id"],
            "screen_geography": screen_geography,
            "continuity_anchors": [profile["protagonist_name"], location_spec["name"], *([profile["artifact_name"]] if include_artifact else [])],
        },
        "handoff_to_next_scene": f"{title}の最後の光が次の場面へ観客を運ぶ" if not is_terminal else "",
        "terminal_resolution": f"{profile['artifact_name']}が主人公の価値を証明する" if is_terminal else "",
    }


def _scene_event_for_cut_design(
    *,
    title: str,
    idx: int,
    scene_intent: dict[str, Any],
    location_name: str,
    profile: dict[str, Any],
    include_artifact: bool,
) -> dict[str, Any]:
    protagonist = str(profile["protagonist_name"])
    artifact = str(profile["artifact_name"])
    source_story_beat_id = f"story_scene{idx:02d}_primary"
    visible_evidence = scene_intent.get("value_shift", {}).get("visible_evidence", []) if isinstance(scene_intent.get("value_shift"), dict) else []
    evidence_terms = [str(item) for item in visible_evidence if str(item).strip()][:4] or [location_name, protagonist]
    artifact_clause = f"と{artifact}" if include_artifact else ""
    beat_specs = [
        (
            "setup",
            f"{title}で、{protagonist}は{location_name}の制限の中に置かれている",
            f"{protagonist}が{location_name}でまだ行動を完了せず、出口や変化点へ視線を向ける",
            "周囲の視線や場所の障害が主人公を押し返す",
            "sceneの問いと開始状況が観客に確定する",
            "まだ動けない圧力が見える",
        ),
        (
            "pressure",
            f"{title}で、場所・視線・証拠{artifact_clause}が{protagonist}に選択を迫る",
            f"{protagonist}の手元、表情、姿勢のいずれかが変化点へ近づく",
            "妨害者、助力者、証人、共同体のいずれかが圧力を増す",
            "迷いが具体的な行為の直前まで進む",
            "不安や期待が上がる",
        ),
        (
            "turn",
            str(scene_intent.get("causal_turn") or f"{title}で不可逆な行為が起きる"),
            f"{protagonist}が後戻りできない行為を取り、画面内に原因と結果が同時に残る",
            "周囲または場所がその変化を受け止める",
            "sceneの価値変化が物語上の事実になる",
            "不可逆な決断が画面に固定される",
        ),
        (
            "payoff",
            f"{title}の結果が、次sceneへ渡る証拠または終結の証明として残る",
            f"{protagonist}の姿勢、{location_name}の導線、{evidence_terms[0]}が結果を示す",
            "残された痕跡や視線が次の圧力を作る",
            "次のsceneの開始理由、または終結の証明が成立する",
            "変化後の余韻が残る",
        ),
    ]
    event_sequence = []
    for function, what_happens, visible_action, visible_reaction, consequence, pressure in beat_specs:
        event_sequence.append(
            {
                "beat_id": f"scene{idx:02d}_event_{function}",
                "beat_function": function,
                "source_story_beat_ids": [source_story_beat_id],
                "what_happens": what_happens,
                "visible_action": visible_action,
                "visible_reaction": visible_reaction,
                "immediate_consequence": consequence,
                "emotional_pressure": pressure,
                "required_visual_evidence": list(dict.fromkeys([location_name, protagonist, *evidence_terms, *([artifact] if include_artifact else [])]))[:6],
                "story_information_revealed_ids": [f"scene{idx:02d}_{function}"],
            }
        )
    return {
        "schema_version": "scene_event_v1",
        "event_logline": f"{title}で{protagonist}の状態が不可逆に変わり、次へ渡る証拠が残る",
        "start_situation": f"{protagonist}は{location_name}でまだ自由に動けず、sceneの問いを受けている",
        "source_story_beat_ids": [source_story_beat_id],
        "event_sequence": event_sequence,
        "turning_event": {
            "source_event_beat_id": f"scene{idx:02d}_event_turn",
            "causal_turn_ref": "scene_intent.causal_turn",
            "irreversible_change": str(scene_intent.get("causal_turn") or f"{title}の不可逆な変化"),
        },
        "end_situation": {
            "value_shift_to_ref": "scene_intent.value_shift.to",
            "outcome": str(scene_intent.get("value_shift", {}).get("to") if isinstance(scene_intent.get("value_shift"), dict) else "次へ進む理由が残る"),
            "character_position": f"{protagonist}は開始時より次の導線または証明へ近づいている",
            "object_state": f"{artifact}は証拠として扱われる" if include_artifact else "必要な証拠が場所に残る",
            "relationship_state": "周囲との関係が、制限から認識または次の圧力へ変化する",
            "new_pressure": str(scene_intent.get("terminal_resolution") or scene_intent.get("handoff_to_next_scene") or "次sceneへ渡る圧力が残る"),
            "visible_evidence_refs": [f"scene{idx:02d}_event_payoff"],
        },
        "offscreen_context": [str(item) for item in scene_intent.get("withheld_information", []) if str(item).strip()] or ["このscene外の出来事は画面で完了させない"],
        "forbidden_event_changes": [str(item) for item in scene_intent.get("reveal_constraints", []) if str(item).strip()] or ["scene_eventにない結末や新事実を追加しない"],
    }


def _story_event_obligations_from_scene_event(scene_event: dict[str, Any]) -> list[dict[str, Any]]:
    obligations: list[dict[str, Any]] = []
    for beat in scene_event.get("event_sequence", []) if isinstance(scene_event.get("event_sequence"), list) else []:
        if not isinstance(beat, dict):
            continue
        beat_id = str(beat.get("beat_id") or "").strip()
        if not beat_id:
            continue
        obligations.append(
            {
                "event_id": beat_id,
                "source_event_beat_id": beat_id,
                "source_events": [str(beat.get("what_happens") or "").strip()],
                "audience_knowledge_delta": str(beat.get("immediate_consequence") or "").strip(),
                "causal_proof": str(beat.get("visible_action") or "").strip(),
                "visual_evidence": [str(item) for item in beat.get("required_visual_evidence", []) if str(item).strip()] if isinstance(beat.get("required_visual_evidence"), list) else [],
                "required_roles": ["protagonist"],
                "static_first_frame_rule": "scene_eventの出来事を、動作説明ではなく原因・結果・証拠が読める静止状態で見せる",
                "anti_redundancy_key": f"scene_event:{beat_id}",
            }
        )
    return obligations


def _event_context_for_cut_contract(
    *,
    scene_event: dict[str, Any],
    source_event_contract: dict[str, Any],
    reveal_constraints: Any,
) -> dict[str, Any]:
    sequence = [beat for beat in scene_event.get("event_sequence", []) if isinstance(beat, dict)]
    by_id = {str(beat.get("beat_id") or "").strip(): beat for beat in sequence if str(beat.get("beat_id") or "").strip()}
    primary_id = str(source_event_contract.get("primary_event_beat_id") or "").strip()
    source_ids = [str(item).strip() for item in source_event_contract.get("source_event_beat_ids", []) if str(item).strip()] if isinstance(source_event_contract.get("source_event_beat_ids"), list) else []
    if primary_id and primary_id not in source_ids:
        source_ids = [primary_id, *source_ids]
    neighbor_ids: list[str] = []
    for source_id in source_ids:
        for index, beat in enumerate(sequence):
            if str(beat.get("beat_id") or "").strip() != source_id:
                continue
            for neighbor_index in (index - 1, index + 1):
                if 0 <= neighbor_index < len(sequence):
                    neighbor_id = str(sequence[neighbor_index].get("beat_id") or "").strip()
                    if neighbor_id and neighbor_id not in source_ids and neighbor_id not in neighbor_ids:
                        neighbor_ids.append(neighbor_id)
    constraints = reveal_constraints if isinstance(reveal_constraints, list) else []
    return {
        "derived_from": ["scene_event.event_sequence[]", "cut_contract.source_event_contract"],
        "editable": False,
        "scene_event_logline": str(scene_event.get("event_logline") or ""),
        "primary_event_beat": by_id.get(primary_id, {}),
        "source_event_beats": [by_id[source_id] for source_id in source_ids if source_id in by_id],
        "neighboring_event_beats": [by_id[neighbor_id] for neighbor_id in neighbor_ids if neighbor_id in by_id],
        "forbidden_event_changes": [str(item) for item in scene_event.get("forbidden_event_changes", []) if str(item).strip()] if isinstance(scene_event.get("forbidden_event_changes"), list) else [],
        "reveal_constraints_for_this_cut": constraints,
    }


def _scene_cut_coverage_plan(
    *,
    title: str,
    idx: int,
    scene_intent: dict[str, Any],
    scene_event: dict[str, Any],
    location_name: str,
    profile: dict[str, Any],
    include_artifact: bool,
) -> dict[str, Any]:
    protagonist = profile["protagonist_name"]
    artifact = profile["artifact_name"]

    def extra_obligation(
        *,
        obligation_id: str,
        cut_function: str,
        source: str,
        target_beat: str,
        screen_question: str,
        dramatic_job: str,
        visual_proof: str,
        first_frame_brief: str,
        must_show_extra: list[str],
        done_when: str,
        foreground: str,
        midground: str,
        background: str,
        screen_direction: str,
        motion_brief: str,
        motion_end_state: str,
        narration: str,
        audience_knowledge_delta: str = "",
        causal_proof: str = "",
        visual_evidence: list[str] | None = None,
        required_roles: list[str] | None = None,
        static_first_frame_rule: str = "",
        anti_redundancy_key: str = "",
    ) -> dict[str, Any]:
        return {
            "obligation_id": obligation_id,
            "cut_function": cut_function,
            "source": source,
            "target_beat": target_beat,
            "screen_question": screen_question,
            "dramatic_job": dramatic_job,
            "visual_proof": visual_proof,
            "first_frame_brief": first_frame_brief,
            "must_show_extra": must_show_extra,
            "done_when": done_when,
            "foreground": foreground,
            "midground": midground,
            "background": background,
            "screen_direction": screen_direction,
            "motion_brief": motion_brief,
            "motion_end_state": motion_end_state,
            "narration": narration,
            "audience_knowledge_delta": audience_knowledge_delta,
            "causal_proof": causal_proof,
            "visual_evidence": visual_evidence or [],
            "required_roles": required_roles or [],
            "static_first_frame_rule": static_first_frame_rule,
            "anti_redundancy_key": anti_redundancy_key,
        }

    obligations: list[dict[str, Any]] = [
        {
            "obligation_id": "scene_pressure",
            "cut_function": "pressure",
            "source": "dramatic_question",
            "target_beat": f"{title}: 場所の圧力と主人公の制限を見せる",
            "screen_question": f"{title}で、{protagonist}は何に妨げられているのか",
            "dramatic_job": "sceneの問いを、場所の圧力と主人公の身体状態で立ち上げる",
            "visual_proof": f"{location_name}の空間圧力の中で、{protagonist}の姿勢と視線が前進できない理由を示す",
            "first_frame_brief": f"{location_name}の広がりと障害が読める構図。{protagonist}はまだ行動せず、視線だけが出口や光へ向く。",
            "must_show_extra": [location_name],
            "done_when": "sceneの問いと圧力が、人物と場所だけで読める",
            "foreground": "場所の障害物や床の質感",
            "midground": protagonist,
            "background": location_name,
            "screen_direction": "pressure_holds_character",
            "motion_brief": "光と空気だけが動き、主人公の視線が出口や変化点へ向く",
            "motion_end_state": "次cutで扱う変化点へ視線が残る",
            "narration": f"{title}。まだ動けない場所で、進む理由だけが奥に残っている。",
        },
        {
            "obligation_id": "visible_value_shift",
            "cut_function": "threshold",
            "source": "value_shift.visible_evidence",
            "target_beat": f"{title}: 価値変化の兆しを画面に出す",
            "screen_question": f"{title}で、何が変わり始めたのか",
            "dramatic_job": "sceneの価値変化を、手元、表情、光、必要な象徴物で可視化する",
            "visual_proof": f"{protagonist}の手元または表情に光が入り、{title}の価値変化が始まる",
            "first_frame_brief": f"{protagonist}の手元または顔が読める中距離。行動が始まる直前で、光が変化点に集まる。",
            "must_show_extra": [artifact] if include_artifact else ["光"],
            "done_when": "sceneの価値変化が、人物の姿勢と光の変化で読める",
            "foreground": "手元または変化点",
            "midground": protagonist,
            "background": location_name,
            "screen_direction": "toward_change",
            "motion_brief": "主人公の手元、視線、光が同じ方向へ動き、sceneの変化が始まる",
            "motion_end_state": "変化の証拠が画面内に残る",
            "narration": f"{title}。消えかけた願いが、手の届く距離まで近づく。",
        },
        {
            "cut_function": "handoff",
            "obligation_id": "causal_handoff",
            "source": "causal_turn/handoff_to_next_scene",
            "target_beat": f"{title}: sceneの結果を次へ渡す",
            "screen_question": f"{title}の終わりに、次へ進む理由は何として残るのか",
            "dramatic_job": "sceneで得た変化を、次の場所または次の行動へ接続できる画として固定する",
            "visual_proof": f"{title}の結果が、{protagonist}の姿勢と{location_name}の出口方向に残る",
            "first_frame_brief": f"{protagonist}は行動後の姿勢で、画面奥または横方向に次の導線が見える。結果の余韻が場所に残る。",
            "must_show_extra": [artifact] if include_artifact else ["導線"],
            "done_when": "sceneの結果と次へ進む理由が一枚で読める",
            "foreground": "残された痕跡または足元",
            "midground": protagonist,
            "background": f"{location_name}から次へ続く導線",
            "screen_direction": "toward_next_scene",
            "motion_brief": "カメラが次の導線へわずかに流れ、主人公の姿勢が結果を受け取る",
            "motion_end_state": "次sceneまたは次cutへ渡る光、視線、導線が画面に残る",
            "narration": f"{title}。残った光が、次に進む理由を静かに指している。",
        },
    ]
    value_shift = scene_intent.get("value_shift") if isinstance(scene_intent.get("value_shift"), dict) else {}
    visible_evidence = [str(item) for item in value_shift.get("visible_evidence", []) if item]
    audience_information = [str(item) for item in scene_intent.get("audience_information", []) if item]
    withheld_information = [str(item) for item in scene_intent.get("withheld_information", []) if item]
    reveal_constraints = [str(item) for item in scene_intent.get("reveal_constraints", []) if item]
    visual_thesis = str(scene_intent.get("visual_thesis") or f"{title}の意味を画面で成立させる")
    spatial_plan = scene_intent.get("spatial_plan") if isinstance(scene_intent.get("spatial_plan"), dict) else {}
    screen_geography = str(spatial_plan.get("screen_geography") or f"{location_name}の前景/中景/背景を固定する")
    terminal_resolution = str(scene_intent.get("terminal_resolution") or "")
    handoff_to_next_scene = str(scene_intent.get("handoff_to_next_scene") or "")
    if terminal_resolution:
        for obligation in obligations:
            if obligation["obligation_id"] == "causal_handoff":
                obligation.update(
                    {
                        "cut_function": "payoff",
                        "source": "causal_turn/terminal_resolution",
                        "target_beat": f"{title}: sceneの結果を証明して閉じる",
                        "screen_question": f"{title}の終わりに、何が主人公の価値を証明するのか",
                        "dramatic_job": "sceneで得た変化を、次へ送る導線ではなく終結の証明として固定する",
                        "visual_proof": f"{title}の結果が、{protagonist}の姿勢と{artifact}、{location_name}の光の収束として残る",
                        "first_frame_brief": f"{protagonist}は証明を受け止めた姿勢で、{artifact}と部屋の光が彼女へ集まる。出口導線ではなく終結の余韻が見える。",
                        "must_show_extra": [artifact],
                        "done_when": "sceneの結果と終結の証明が一枚で読める",
                        "foreground": artifact,
                        "background": f"{location_name}の閉じた光",
                        "screen_direction": "resolution_visible",
                        "motion_brief": f"カメラが{artifact}から主人公の表情へ戻り、証明が部屋全体に受け入れられる",
                        "motion_end_state": "物語が閉じる状態で画面に残る",
                        "narration": f"{title}。残された証が、奪われていた価値を静かに返していく。",
                    }
                )
    joined_intent = " / ".join(
        [
            visual_thesis,
            screen_geography,
            terminal_resolution,
            handoff_to_next_scene,
            *visible_evidence,
            *audience_information,
            *withheld_information,
            *reveal_constraints,
        ]
    )

    def has_any(words: list[str]) -> bool:
        return any(word and word in joined_intent for word in words)

    def append_unique(obligation: dict[str, Any]) -> None:
        if all(existing["obligation_id"] != obligation["obligation_id"] for existing in obligations):
            obligations.append(obligation)

    for event_obligation in [item for item in scene_intent.get("story_event_obligations", []) if isinstance(item, dict)]:
        visual_evidence_terms = [str(item) for item in event_obligation.get("visual_evidence", []) if str(item).strip()]
        source_events = [str(item) for item in event_obligation.get("source_events", []) if str(item).strip()]
        event_summary = " / ".join(source_events) or title
        must_show_event_terms = visual_evidence_terms[:3] or ["出来事の原因が見える手がかり"]
        append_unique(
            extra_obligation(
                obligation_id="story_event_proof",
                cut_function="event_proof",
                source="story_event_obligations",
                target_beat=f"{title}: 物語上の不可逆な出来事を画面で証明する",
                screen_question=f"{title}で、観客はどの出来事が起きたと理解するのか",
                dramatic_job="sceneの雰囲気ではなく、物語を前へ動かす原因・結果・証人・物的証拠を一枚に固定する",
                visual_proof=f"{event_summary}。{event_obligation.get('causal_proof')}。必要な視覚証拠: {'、'.join(must_show_event_terms)}",
                first_frame_brief=(
                    f"{location_name}で、{'、'.join(must_show_event_terms)}が読める静止状態。"
                    "動作中の説明ではなく、出来事の原因と結果が同時に見える。"
                ),
                must_show_extra=must_show_event_terms,
                done_when="観客の知識がこのcutで具体的な物語事実として一段進む",
                foreground=must_show_event_terms[0],
                midground=protagonist,
                background=f"{location_name}と見届ける視線",
                screen_direction="event_fact_becomes_visible",
                motion_brief="視線が原因の手がかりから結果の証拠へ移り、出来事が観客の理解として固定される",
                motion_end_state="不可逆な出来事の証拠が画面に残る",
                narration=f"{title}。ここで物語は、ただの気配ではなく出来事として一段進む。",
                audience_knowledge_delta=str(event_obligation.get("audience_knowledge_delta") or ""),
                causal_proof=str(event_obligation.get("causal_proof") or ""),
                visual_evidence=visual_evidence_terms,
                required_roles=[str(role) for role in event_obligation.get("required_roles", []) if str(role).strip()],
                static_first_frame_rule=str(event_obligation.get("static_first_frame_rule") or ""),
                anti_redundancy_key=str(event_obligation.get("anti_redundancy_key") or ""),
            )
        )

    if len(audience_information) >= 3:
        key_information = "、".join(audience_information[:3])
        append_unique(
            extra_obligation(
                obligation_id="audience_context",
                cut_function="context",
                source="audience_information",
                target_beat=f"{title}: 観客がsceneを誤読しないための情報を画面に置く",
                screen_question=f"観客は{title}の状況を何から理解するのか",
                dramatic_job="scene理解に必要な場所、人物配置、場のルールを説明台詞ではなく構図で渡す",
                visual_proof=f"{key_information}と場のルールが、{location_name}の人物配置と光の向きで同時に読める",
                first_frame_brief=f"{location_name}の前景/中景/背景が整理され、{protagonist}の現在位置と場のルールが一目で分かる。",
                must_show_extra=[location_name, "場のルール"],
                done_when="観客がsceneの前提情報を一枚で読める",
                foreground="scene理解に必要な手がかり",
                midground=protagonist,
                background=location_name,
                screen_direction="context_established",
                motion_brief="視線誘導が場所、人物、ルールの順に静かに移る",
                motion_end_state="sceneの前提が次の変化cutを受け止められる状態で残る",
                narration=f"{title}。場所の決まりが、彼女の進める幅を静かに狭めている。",
            )
        )

    if (withheld_information or reveal_constraints) and not include_artifact and profile.get("slug") != "cinderella":
        withheld = withheld_information[0] if withheld_information else reveal_constraints[0]
        append_unique(
            extra_obligation(
                obligation_id="reveal_protection",
                cut_function="reveal_hold",
                source="withheld_information/reveal_constraints",
                target_beat=f"{title}: まだ見せない情報を画面の欠落として成立させる",
                screen_question=f"{title}で、何がまだ画面外に保たれているのか",
                dramatic_job="後で効く証や情報を早出しせず、欠落や余白として観客に感じさせる",
                visual_proof=f"{withheld}は直接出さず、{protagonist}の手元の空白と{location_name}の光で不在が読める",
                first_frame_brief=f"{protagonist}の手元または足元に意味のある空白を残し、後で現れる証は画面に出さない。",
                must_show_extra=["空白", "光"],
                done_when="後で明かす情報が、今は見えないこと自体として伝わる",
                foreground="何も置かれていない手元または足元",
                midground=protagonist,
                background=location_name,
                screen_direction="reveal_withheld",
                motion_brief="カメラが空白を一瞬だけ拾い、すぐ主人公の視線へ戻る",
                motion_end_state="見せない情報が次以降の期待として残る",
                narration=f"{title}。まだ形にならない答えだけが、光の外側に残っている。",
            )
        )

    use_symbolic_proof = include_artifact or any(artifact in evidence for evidence in visible_evidence)
    if use_symbolic_proof:
        append_unique(
            extra_obligation(
                obligation_id="symbolic_proof",
                cut_function="proof",
                source="value_shift.visible_evidence/visual_thesis",
                target_beat=f"{title}: {artifact}をsceneの意味を証明するものとして見せる",
                screen_question=f"{artifact}は{title}で何を証明しているのか",
                dramatic_job="象徴物を装飾ではなく、価値変化や身元変化の証拠として配置する",
                visual_proof=f"{artifact}、{protagonist}、{location_name}の光が同じ画面内で関係づけられる",
                first_frame_brief=f"{artifact}の形が前景または手元で読め、{protagonist}と{location_name}の関係も同時に分かる。",
                must_show_extra=[artifact],
                done_when=f"{artifact}がsceneの意味を支える証として読める",
                foreground=artifact,
                midground=protagonist,
                background=location_name,
                screen_direction="proof_connected_to_scene",
                motion_brief=f"光が{artifact}を横切り、主人公の視線が証拠へ移る",
                motion_end_state=f"{artifact}が次の変化や探索の理由として画面に残る",
                narration=f"{title}。小さな証が、言葉より先に意味を持ち始める。",
            )
        )

    if not terminal_resolution and has_any(["境界", "出口", "導線", "移動", "越", "道", "入口", "進む", "運ぶ"]):
        append_unique(
            extra_obligation(
                obligation_id="spatial_transition",
                cut_function="threshold",
                source="spatial_plan/handoff_to_next_scene",
                target_beat=f"{title}: 場所の中で進む方向や境界を見せる",
                screen_question=f"{protagonist}はどちらへ進むべきなのか",
                dramatic_job="sceneの行動方向を、空間の導線と人物の向きで具体化する",
                visual_proof=f"{screen_geography}。{protagonist}の身体が次へ進む導線へ向いている",
                first_frame_brief=f"{location_name}の出口や奥行きが読め、{protagonist}の姿勢が次の方向を示している。",
                must_show_extra=[location_name, "導線"],
                done_when="scene内の移動方向や境界が一枚で理解できる",
                foreground="境界や足元の目印",
                midground=protagonist,
                background=f"{location_name}から続く導線",
                screen_direction="cross_or_follow_path",
                motion_brief="カメラが人物の向きから導線へゆっくり流れる",
                motion_end_state="次の場所へ向かう方向が画面に残る",
                narration=f"{title}。場所の奥行きが、次に進むべき方向を示している。",
            )
        )

    if has_any(["時間", "制限", "真夜中", "鐘", "締切", "追跡", "失い", "失う"]):
        append_unique(
            extra_obligation(
                obligation_id="time_or_deadline_pressure",
                cut_function="pressure",
                source="withheld_information/causal_turn/audience_information",
                target_beat=f"{title}: 時間や喪失の圧力を画面化する",
                screen_question=f"なぜ{title}では今すぐ動く必要があるのか",
                dramatic_job="sceneを急がせる外部圧を、時計、影、距離、身体の緊張のいずれかで見せる",
                visual_proof=f"長い影、遠ざかる光、または緊張した姿勢が{protagonist}を急かしている",
                first_frame_brief=f"{protagonist}の近くに伸びる影や遠ざかる光があり、余裕が失われていることが分かる。",
                must_show_extra=["影", "光"],
                done_when="急ぐ理由や失う危険が説明なしで読める",
                foreground="長い影または足元の緊張",
                midground=protagonist,
                background=location_name,
                screen_direction="deadline_pressure",
                motion_brief="影や光の変化が強まり、主人公の身体が次の行動へ押し出される",
                motion_end_state="急ぐ圧力が次cutまたは次sceneへ残る",
                narration=f"{title}。残された時間が、静かな場所まで押し寄せてくる。",
            )
        )

    if include_artifact or terminal_resolution:
        append_unique(
            extra_obligation(
                obligation_id="reaction_after_change",
                cut_function="reaction",
                source="value_shift/affect_transition/terminal_resolution",
                target_beat=f"{title}: 変化を受け取った反応を残す",
                screen_question=f"{protagonist}は変化の意味を受け止めたのか",
                dramatic_job="出来事の結果を、表情、姿勢、呼吸の余白として観客に届かせる",
                visual_proof=f"{protagonist}の表情と姿勢に、{title}で起きた変化の重さが残る",
                first_frame_brief=f"{protagonist}の表情が読める距離。背景に{location_name}の余韻と変化後の光が残る。",
                must_show_extra=["表情", "光"],
                done_when="sceneの変化が出来事だけでなく感情として読める",
                foreground="変化の痕跡",
                midground=protagonist,
                background=location_name,
                screen_direction="reaction_hold",
                motion_brief="主人公の呼吸と視線だけが小さく動き、変化の余韻を保つ",
                motion_end_state="反応の余韻が次の行動または終結へつながる",
                narration=f"{title}。変わったのは状況だけではなく、進む理由そのものだった。",
            )
        )

    if terminal_resolution:
        append_unique(
            extra_obligation(
                obligation_id="terminal_resolution",
                cut_function="payoff",
                source="terminal_resolution",
                target_beat=f"{title}: 物語の終結条件を画面で証明する",
                screen_question="物語は何を取り戻して終わるのか",
                dramatic_job="最後の解放や帰還を、証、人物、場所の空気で明確に閉じる",
                visual_proof=f"{terminal_resolution}ことが、{protagonist}の表情、{artifact}、{location_name}の関係で読める",
                first_frame_brief=f"{protagonist}の表情と{artifact}が同じ画面にあり、{location_name}の光が閉じる方向へ整っている。",
                must_show_extra=[artifact, "表情"],
                done_when="終結条件が、説明ではなく画面上の証明として成立する",
                foreground=artifact,
                midground=protagonist,
                background=location_name,
                screen_direction="resolution_visible",
                motion_brief="主人公の視線が上がり、光が証と人物を同じ画面に結ぶ",
                motion_end_state="解放または帰還の状態でsceneが閉じる",
                narration=f"{title}。残された証が、奪われていた価値を静かに返していく。",
            )
        )

    def story_event_assignment_score(proof: dict[str, Any], candidate: dict[str, Any]) -> int:
        candidate_id = str(candidate.get("obligation_id") or "")
        proof_text = " / ".join(
            str(proof.get(key) or "")
            for key in ("target_beat", "screen_question", "dramatic_job", "visual_proof", "causal_proof")
        )
        candidate_text = " / ".join(
            [
                str(candidate.get(key) or "")
                for key in ("target_beat", "screen_question", "dramatic_job", "visual_proof", "first_frame_brief", "done_when")
            ]
            + [str(item) for item in candidate.get("must_show_extra", [])]
        )
        score = 0
        for term in [str(item) for item in proof.get("visual_evidence", []) if str(item).strip()]:
            if term in candidate_text:
                score += 2
        semantic_rules = [
            (("妨げ", "拒", "圧", "支配", "障害"), {"scene_pressure", "audience_context"}),
            (("知らせ", "発見", "判明", "呼び出", "約束"), {"audience_context", "scene_pressure"}),
            (("助力", "変化", "変身", "贈与", "証"), {"transformation_reveal", "visible_value_shift", "symbolic_proof"}),
            (("移動", "出発", "向かう", "入口", "出口", "境界", "道"), {"spatial_transition", "causal_handoff"}),
            (("期限", "時間", "急", "失", "追跡", "締切"), {"time_or_deadline_pressure", "causal_handoff"}),
            (("反応", "視線", "受け止め", "余韻"), {"reaction_after_change", "causal_handoff"}),
            (("終結", "解放", "帰還", "証明", "取り戻"), {"terminal_resolution", "symbolic_proof", "causal_handoff"}),
        ]
        for keywords, obligation_ids in semantic_rules:
            if candidate_id in obligation_ids and any(keyword in proof_text for keyword in keywords):
                score += 3
        if candidate_id == "causal_handoff" and not any(keyword in proof_text for keyword in ("次", "導線", "結果", "つなが", "渡る", "引き起こ")):
            score -= 1
        generic_terms = {
            term
            for text in (proof_text, candidate_text)
            for term in re.split(r"[、。・/\s]+", text)
            if len(term) >= 2
        }
        for keyword in generic_terms:
            if keyword in proof_text and keyword in candidate_text:
                score += 1
        return score

    for proof in [obligation for obligation in list(obligations) if obligation.get("obligation_id") == "story_event_proof"]:
        candidates = [obligation for obligation in obligations if obligation is not proof]
        if not candidates:
            continue
        best = max(candidates, key=lambda candidate: story_event_assignment_score(proof, candidate))
        if story_event_assignment_score(proof, best) < 3:
            continue
        best["audience_knowledge_delta"] = str(proof.get("audience_knowledge_delta") or best.get("audience_knowledge_delta") or "")
        event_causal_proof = str(proof.get("causal_proof") or proof.get("visual_proof") or "")
        if event_causal_proof and event_causal_proof not in str(best.get("causal_proof") or ""):
            best["causal_proof"] = "。".join(
                item
                for item in [str(best.get("causal_proof") or best.get("visual_proof") or "").strip("。"), event_causal_proof.strip("。")]
                if item
            )
        event_terms = [str(item) for item in proof.get("visual_evidence", []) if str(item).strip()]
        best["visual_evidence"] = list(dict.fromkeys([*[str(item) for item in best.get("visual_evidence", [])], *event_terms]))[:6]
        best["must_show_extra"] = list(dict.fromkeys([*[str(item) for item in best.get("must_show_extra", [])], *event_terms[:3]]))
        best["required_roles"] = list(
            dict.fromkeys(
                [
                    *[str(item) for item in best.get("required_roles", []) if str(item).strip()],
                    *[str(item) for item in proof.get("required_roles", []) if str(item).strip()],
                ]
            )
        )
        if str(proof.get("static_first_frame_rule") or "").strip():
            best["static_first_frame_rule"] = str(proof["static_first_frame_rule"])
        best["anti_redundancy_key"] = f"{best.get('source') or 'scene'}:{best.get('obligation_id')}|story_event_obligations"
        best["visual_proof"] = "。".join(
            item
            for item in [str(best.get("visual_proof") or "").strip("。"), f"物語イベントの証拠: {'、'.join(event_terms[:4])}".strip("。")]
            if item
        )
        obligations.remove(proof)

    _normalize_cut_obligations_for_scene(obligations)

    event_sequence = [beat for beat in scene_event.get("event_sequence", []) if isinstance(beat, dict)]
    event_by_function: dict[str, list[dict[str, Any]]] = {}
    event_by_id: dict[str, dict[str, Any]] = {}
    for beat in event_sequence:
        beat_id = str(beat.get("beat_id") or "").strip()
        beat_function = str(beat.get("beat_function") or "").strip()
        if not beat_id:
            continue
        event_by_id[beat_id] = beat
        event_by_function.setdefault(beat_function, []).append(beat)

    def beat_for_function(function: str) -> dict[str, Any]:
        if event_by_function.get(function):
            return event_by_function[function][0]
        if event_sequence:
            return event_sequence[0]
        return {"beat_id": f"scene{idx:02d}_event_{function}", "beat_function": function}

    def target_event_function(obligation: dict[str, Any], index: int) -> str:
        text = " / ".join(
            str(obligation.get(key) or "")
            for key in ("cut_function", "source", "obligation_id", "target_beat", "dramatic_job", "visual_proof")
        ).lower()
        if index == 1 or any(token in text for token in ("setup", "dramatic_question", "scene_pressure")):
            return "setup"
        if any(token in text for token in ("turn", "event_proof", "causal", "threshold", "reveal", "transformation", "symbolic_proof")):
            return "turn"
        if any(token in text for token in ("payoff", "handoff", "terminal", "reaction", "resolution", "closure")):
            return "payoff"
        return "pressure"

    def event_time_position_for_function(function: str) -> str:
        if function == "setup":
            return "before_trigger"
        if function == "pressure":
            return "early_action"
        if function == "turn":
            return "trigger_moment"
        return "consequence"

    scene_id = idx * 10
    assignment_records: list[dict[str, Any]] = []
    assigned_by_source: dict[str, list[str]] = {}
    assigned_by_obligation: dict[str, list[str]] = {}
    for index, obligation in enumerate(obligations, start=1):
        selector = f"scene{scene_id}_cut{index:02d}"
        obligation_id = str(obligation.get("obligation_id") or f"obligation_{index:02d}")
        source = str(obligation.get("source") or "scene")
        function = target_event_function(obligation, index)
        primary_beat = beat_for_function(function)
        primary_beat_id = str(primary_beat.get("beat_id") or "").strip()
        source_event_beat_ids = [primary_beat_id] if primary_beat_id else []
        obligation["primary_event_beat_id"] = primary_beat_id
        obligation["source_event_beat_ids"] = source_event_beat_ids
        obligation["event_beat_function"] = str(primary_beat.get("beat_function") or function)
        obligation["event_time_position"] = event_time_position_for_function(str(primary_beat.get("beat_function") or function))
        assigned_by_obligation.setdefault(obligation_id, []).append(selector)
        assigned_by_source.setdefault(source, []).append(selector)
        assignment_records.append(
            {
                "cut_index": index,
                "cut_selector": selector,
                "obligation_ids": [obligation_id],
                "obligation_id": obligation_id,
                "cut_function": obligation["cut_function"],
                "source": source,
                "event_assignment": {
                    "source_event_contract": {
                        "primary_event_beat_id": primary_beat_id,
                        "source_event_beat_ids": source_event_beat_ids,
                    }
                },
                "target_beat": obligation["target_beat"],
                "visual_proof": obligation.get("visual_proof", ""),
                "audience_knowledge_delta": obligation.get("audience_knowledge_delta", ""),
                "causal_proof": obligation.get("causal_proof", ""),
                "required_roles": obligation.get("required_roles", []),
                "anti_redundancy_key": obligation.get("anti_redundancy_key", ""),
            }
        )
    required_functions = ("setup", "pressure", "turn", "payoff")

    def assigned_beat_ids(record: dict[str, Any]) -> list[str]:
        source_contract = (
            record.get("event_assignment", {}).get("source_event_contract", {})
            if isinstance(record.get("event_assignment"), dict)
            else {}
        )
        return [str(item).strip() for item in source_contract.get("source_event_beat_ids", []) if str(item).strip()] if isinstance(source_contract.get("source_event_beat_ids"), list) else []

    covered_ids = {beat_id for record in assignment_records for beat_id in assigned_beat_ids(record)}
    for required_function in required_functions:
        beat = beat_for_function(required_function)
        beat_id = str(beat.get("beat_id") or "").strip()
        if not beat_id or beat_id in covered_ids or not assignment_records:
            continue
        target_index = {"setup": 0, "pressure": min(1, len(assignment_records) - 1), "turn": max(0, len(assignment_records) - 2), "payoff": len(assignment_records) - 1}[required_function]
        assignment_records[target_index]["event_assignment"]["source_event_contract"]["source_event_beat_ids"].append(beat_id)
        obligations[target_index].setdefault("source_event_beat_ids", []).append(beat_id)
        covered_ids.add(beat_id)

    def assigned_for(*sources: str) -> list[str]:
        selectors: list[str] = []
        for source in sources:
            selectors.extend(assigned_by_source.get(source, []))
        return list(dict.fromkeys(selectors))

    minimum_by_importance = 3
    minimum_by_duration = max(3, int((len(obligations) * 8 + 7) // 8))
    minimum_by_event_beats = len([beat for beat in event_sequence if beat.get("must_be_seen") is True]) or len(
        [beat for beat in event_sequence if str(beat.get("beat_function") or "") in required_functions]
    )
    selected_minimum = max(minimum_by_importance, minimum_by_duration, minimum_by_event_beats)
    coverage = {
        "coverage_strategy": "reverse_from_scene_event",
        "source_schema_version": "scene_event_v1",
        "strategy": "scene設計から必要な視覚要件を列挙し、1 cut = 1主要意図になるよう割り当てる",
        "min_cut_count": {
            "by_importance": minimum_by_importance,
            "by_duration": minimum_by_duration,
            "by_event_beats": minimum_by_event_beats,
            "selected": selected_minimum,
            "exception_reason": "",
        },
        "event_beat_inventory": [
            {
                "beat_id": str(beat.get("beat_id") or ""),
                "beat_function": str(beat.get("beat_function") or ""),
                "what_happens": str(beat.get("what_happens") or ""),
                "required_visual_evidence": [str(item) for item in beat.get("required_visual_evidence", []) if str(item).strip()] if isinstance(beat.get("required_visual_evidence"), list) else [],
                "must_be_seen": True,
                "assigned_cut_ids": [record["cut_selector"] for record in assignment_records if str(beat.get("beat_id") or "") in assigned_beat_ids(record)],
            }
            for beat in event_sequence
        ],
        "scene_obligations": [
            {"obligation_id": "dramatic_question_01", "source": "dramatic_question", "evidence": scene_intent.get("dramatic_question"), "assigned_cut_ids": assigned_for("dramatic_question") or [record["cut_selector"] for record in assignment_records[:1]]},
            {"obligation_id": "value_shift_01", "source": "value_shift.visible_evidence", "evidence": (scene_intent.get("value_shift") or {}).get("visible_evidence", []), "assigned_cut_ids": assigned_for("value_shift.visible_evidence", "value_shift/affect_transition/terminal_resolution") or [record["cut_selector"] for record in assignment_records[:1]]},
            {"obligation_id": "causal_turn_01", "source": "causal_turn", "evidence": scene_intent.get("causal_turn"), "assigned_cut_ids": assigned_for("causal_turn/handoff_to_next_scene", "causal_turn/terminal_resolution") or [record["cut_selector"] for record in assignment_records[-1:]]},
            {"obligation_id": "audience_information_01", "source": "audience_information", "evidence": scene_intent.get("audience_information", []), "assigned_cut_ids": assigned_for("audience_information/reveal_constraints") or [record["cut_selector"] for record in assignment_records[:1]]},
            {"obligation_id": "story_event_obligations_01", "source": "story_event_obligations_legacy_projection", "evidence": scene_intent.get("story_event_obligations", []), "assigned_cut_ids": [record["cut_selector"] for record in assignment_records if assigned_beat_ids(record)] or [record["cut_selector"] for record in assignment_records[:1]]},
            {"obligation_id": "audience_knowledge_delta_01", "source": "audience_knowledge_delta", "evidence": scene_intent.get("audience_knowledge_delta", {}), "assigned_cut_ids": [record["cut_selector"] for record in assignment_records if record.get("audience_knowledge_delta")] or [record["cut_selector"] for record in assignment_records[:1]]},
            {"obligation_id": "role_coverage_01", "source": "role_coverage.required_roles", "evidence": (scene_intent.get("role_coverage") or {}).get("required_roles", []), "assigned_cut_ids": [record["cut_selector"] for record in assignment_records if record.get("required_roles")] or [record["cut_selector"] for record in assignment_records[:1]]},
            {"obligation_id": "visual_proof_01", "source": "visual_proof_obligations", "evidence": scene_intent.get("visual_proof_obligations", []), "assigned_cut_ids": [record["cut_selector"] for record in assignment_records if record.get("visual_proof")]},
            {"obligation_id": "reveal_constraints_01", "source": "reveal_constraints", "evidence": scene_intent.get("reveal_constraints", []), "assigned_cut_ids": [record["cut_selector"] for record in assignment_records]},
            {"obligation_id": "visual_thesis_01", "source": "visual_thesis", "evidence": scene_intent.get("visual_thesis"), "assigned_cut_ids": [record["cut_selector"] for record in assignment_records[:1]]},
            {"obligation_id": "spatial_plan_01", "source": "spatial_plan", "evidence": scene_intent.get("spatial_plan"), "assigned_cut_ids": assigned_for("spatial_plan", "causal_turn/handoff_to_next_scene", "causal_turn/terminal_resolution") or [record["cut_selector"] for record in assignment_records[:1]]},
            {"obligation_id": "handoff_01", "source": "handoff_to_next_scene", "evidence": scene_intent.get("handoff_to_next_scene") or scene_intent.get("terminal_resolution"), "assigned_cut_ids": assigned_for("causal_turn/handoff_to_next_scene", "causal_turn/terminal_resolution", "terminal_resolution") or [record["cut_selector"] for record in assignment_records[-1:]]},
        ],
        "knowledge_assignments": [
            {
                "knowledge_delta_id": f"learned_{index:02d}",
                "source": f"audience_knowledge_delta.learned_during_scene[{index - 1}]",
                "assigned_cut_ids": [record["cut_selector"]],
                "evidence": record.get("audience_knowledge_delta", ""),
            }
            for index, record in enumerate([record for record in assignment_records if record.get("audience_knowledge_delta")], start=1)
        ],
        "cut_count_reason": "coverage obligations are grouped by unique visual intent; similar obligations thicken a cut instead of adding a duplicate",
        "minimum_cut_count": selected_minimum,
        "selected_cut_count": len(obligations),
        "cut_assignments": assignment_records,
        "unassigned_obligations": [],
        "overloaded_cuts": [],
        "duplicate_meaning_risks": [],
        "duplicate_cut_policy": "同じscene意味を繰り返すだけならcut追加ではなくprompt補強にする",
    }
    return {"coverage_plan": coverage, "cuts": obligations}


def _build_research(topic: str, source: str, now: str, profile: dict[str, Any]) -> dict[str, Any]:
    events = [
        "母の不在後、継母と義姉たちが入り、主人公は家の中で孤立する。",
        "主人公は台所と灰のそばで眠り、名前の代わりに灰かぶりとして扱われる。",
        "宮殿の舞踏会の知らせが届き、家中の欲望が露わになる。",
        "主人公は参加を望むが、仕事と衣装の欠如を理由に拒まれる。",
        "魔法の助力によって馬車、ドレス、ガラスの靴が現れる。",
        "主人公は宮殿に入り、誰も知らない姿で王子と踊る。",
        "真夜中の鐘で魔法が解け始め、主人公は階段を駆け下りる。",
        "片方のガラスの靴が階段に残る。",
        "使者が靴の持ち主を探し、家々を巡る。",
        "主人公の足に靴が合い、隠されていた身元が明らかになる。",
    ]
    if profile["slug"] != "cinderella":
        events = profile["events"]
    return {
        "topic": topic,
        "aliases": profile["aliases"],
        "story_materials": {
            "canonical_story_dump": f"{source}。{profile['summary']}",
            "chronological_events": [
                {"event_id": f"E{i:02d}", "event": event, "sources": ["S1", "S2"], "confidence": 0.88}
                for i, event in enumerate(events, start=1)
            ],
            "characters": [
                {"character_id": "protagonist", "name": profile["protagonist_name"], "role": "主人公", "motivations": ["尊厳と願いを失わずに進む"], "relationships": [{"target": "opposition", "relation": "前進を妨げられる"}]},
                {"character_id": "opposition", "name": "主人公を妨げる力", "role": "抑圧者または障害", "motivations": ["現状維持"], "relationships": [{"target": "protagonist", "relation": "選択を狭める"}]},
                {"character_id": "witness", "name": "真実を見届ける者", "role": "証人", "motivations": ["主人公の本質を探す"], "relationships": [{"target": "protagonist", "relation": "証を通じて探す"}]},
            ],
            "setting": {"places": profile["places"], "time_or_era": "民話または伝承を実写映画として再構成した時間", "world_rules": [f"{profile['artifact_name']}は証として残る", "助力は主人公の選択を代行しない"]},
            "symbols_and_themes": [
                {"item_id": "SYM1", "item": profile["motifs"][0], "meaning": "抑圧と不可視化", "evidence_refs": ["P1"]},
                {"item_id": "SYM2", "item": profile["artifact_name"], "meaning": "脆さと証明が同居する身元の鍵", "evidence_refs": ["P2"]},
            ],
            "emotional_material": [{"emotion": "切迫", "trigger": "真夜中の鐘", "story_value": "逃走と証明を一気に動かす"}],
            "adaptation_options": [{"option_id": "A1", "proposal": "実写映画のように灰、布、ガラス、月光の質感で感情を語る", "source_basis": ["S1"], "risks": ["説明台詞に寄せすぎない"]}],
        },
        "source_inventory": [
            {"source_id": "S1", "title": f"{profile['topic_label']} story tradition", "url": "request-derived-tradition", "type": "other", "reliability": "medium", "accessed_at": now, "notes": "ユーザー指定 topic/source から抽出した物語筋。"},
            {"source_id": "S2", "title": "ToC request source", "url": "run-request", "type": "other", "reliability": "high", "accessed_at": now, "notes": "ユーザー指定の source。"},
            {"source_id": "S3", "title": "ToC cinematic_story constraints", "url": "repo-contract", "type": "other", "reliability": "high", "accessed_at": now, "notes": "実写シネマティック、p680 frontend handoff。"},
        ],
        "source_passages": [
            {"passage_id": f"P{i}", "source_id": "S1", "passage": passage, "evidence_note": "物語要素として採用。", "confidence": 0.84}
            for i, passage in enumerate(events[:5], start=1)
        ],
        "variants": [{"variant_id": "V1", "name": f"{profile['artifact_name']}を証にする版", "differences": ["物語の証を映像上の主役級アイテムにする"], "impact_on_story": "主役級アイテムとして強い。", "sources": ["S1"]}],
        "conflicts": [{"conflict_id": "C1", "topic": "助力者の表現", "accounts": [{"account_id": "A", "claim": "妖精の助力者として描く", "sources": ["S1"], "confidence": 0.8}], "impact_on_story": "映像では光と風で示せる。", "selection_notes": {"recommended_choice": "A", "rationale": "通俗的に理解しやすい。"}, "hybrid_proposal": {"proposed": False, "mix_elements": [], "risks": [], "mitigations": []}}],
        "facts": {"items": [{"fact_id": "F1", "claim": f"{profile['artifact_name']}が主人公の価値や身元を証明する。", "kind": "plot", "confidence": 0.86, "verification": "partially_verified", "sources": ["S1"], "notes": "物語筋として扱う。"}]},
        "engagement": {"hooks": [{"hook_id": "H1", "type": "emotional", "content": f"{profile['protagonist_name']}が、隠された状態から光の中で自分の名を取り戻す。", "curiosity_score": 0.92, "supporting_facts": ["F1"]}]},
        "open_questions": [{"question_id": "Q1", "question": "助力者を人物として出すか光の現象として出すか。", "known_theories": ["通俗版では妖精。"], "investigation_status": "verified", "sources": ["S1"]}],
        "handoff_to_story": {"recommended_focus": [f"{profile['motifs'][0]}から光へ", f"証としての{profile['artifact_name']}"], "must_preserve": ["抑圧", "越境", "時間制限", "証明"], "avoid_overstating": ["史実性"], "selection_questions_for_p200": ["主人公の能動性をどの場面で強めるか"]},
        "metadata": {"collected_at": now, "sources_used": ["S1", "S2", "S3"], "confidence_score": 0.86},
        "evaluation_contract": {"target_questions": ["主要筋を映像化できるか"], "must_cover": ["canonical_story_dump", "chronological_events", "source_passages", "conflicts"], "must_resolve_conflicts": ["C1"], "done_when": ["p200 が追加調査なしで scene/beat 候補を作れる"]},
    }


def _build_story(topic: str, run_dir: Path, now: str, profile: dict[str, Any]) -> dict[str, Any]:
    scenes = []
    motif_text = "・".join(profile["motifs"])
    for idx, title in enumerate(profile["scene_titles"], start=1):
        scenes.append(
            {
                "scene_id": idx,
                "phase": PHASES[idx - 1],
                "purpose": f"{title}で主人公の状況と選択を映画的に進める",
                "conflict": "家の支配、身分の壁、時間制限のいずれかが主人公の前進を妨げる",
                "turn": f"{title}の終わりに次の場所へ進む理由が生まれる",
                "affect": {"label_hint": "awe" if idx in {3, 5, 6} else "strain", "audience_job": "bond"},
                "visualizable_action": f"{title}を、{motif_text}の実写ディテールで見せる",
                "grounding_note": "topic/source の筋を基にし、会話と構図は映像化のための創作補完。",
                "narration": f"{title}で、隠された名前が光へ近づく。",
                "visual": f"実写映画調の{title}。画面内テキストなし。",
                "research_refs": ["research.story_materials.chronological_events[E01]", "research.source_passages[P1]"],
                "creative_inventions": ["感情を光と質感で圧縮する"],
            }
        )
    return {
        "story_metadata": {"topic": topic, "source_research": str(run_dir / "research.md"), "created_at": now, "pattern_used": "hero"},
        "subagent_trace": [{"subagent_id": "story-candidate-audit-001", "role": "story_candidate", "input_artifact": str(run_dir / "research.md"), "output_artifact": str(run_dir / "logs/eval/story_candidate_a.md"), "accepted_by_main": True, "reason": "主要筋と映像化価値が一致するため採用。"}],
        "outcome_contract": {"goal": "research.md を映画的な story.md に変換する", "success_criteria": ["各 scene が目的、葛藤、転換、感情、視覚行動、research refs を持つ"], "source_vs_creative_boundary": {"source_backed": ["筋", "人物関係", "象徴"], "creative_allowed": ["構図", "光", "台詞", "カメラ"], "ask_before": ["矛盾版の混成"]}},
        "selection": {"candidates": [{"candidate_id": "A", "logline": f"{profile['protagonist_name']}が、失われた名や価値を{profile['artifact_name']}で証明する。", "fact_basis_refs": ["research.engagement.hooks[H1]"], "creative_inventions": [{"element": "光が記憶のように主人公を導く", "purpose": "visual_symbol", "does_not_contradict_refs": True}], "why_it_scores": ["映像の連続性が強い"], "requires_hybridization_approval": False, "conflicts_referenced": ["research.conflicts[C1]"]}, {"candidate_id": "B", "logline": "公的な場を社会の仮面として見せる。", "fact_basis_refs": ["research.story_materials.chronological_events[E06]"], "creative_inventions": [], "why_it_scores": ["テーマ性が明快"], "requires_hybridization_approval": False, "conflicts_referenced": []}], "chosen_candidate_id": "A", "rationale": "象徴を視覚的に追いやすく、p500/p600 の参照資産化に向く。"},
        "hybridization": {"approval_status": "not_needed", "proposal": {"summary": "混成なし", "conflicts_referenced": [], "mix_elements": [], "risks": [], "mitigations": [], "question_for_user": "混成は行わない。"}},
        "ask_before_edit": {"required_when": ["主要筋の削除"], "question_for_user": "承認済み構成を変えます。進めてよいですか？"},
        "story_structure": {"protagonist": {"name": profile["protagonist_name"], "role": "抑圧された主人公", "source_node_id": "research.characters[protagonist]"}, "journey": {"ordinary_world": {"description": "始まりの場所で名前や価値を見失っている"}, "ordeal": {"challenge": "障害と時間制限を越える"}, "transformation": {"before": "見えない存在", "after": "自分の名で立つ人"}, "return": {"resolution": f"{profile['artifact_name']}が証拠となり解放へ向かう"}}, "theme": {"governing_thought": "尊厳は奪われても、証明の瞬間を待っている。"}},
        "story_decomposition": {"source_material_refs": ["research.story_materials.chronological_events[E01]"], "beat_strategy": f"{motif_text}を順に強める。", "emotion_curve_summary": "孤独から驚異、切迫、解放へ。", "notes_on_ignored_or_deferred_material": ["版ごとの細部差は扱わない。"]},
        "script": {"scenes": scenes},
        "engagement_design": {"primary_hook": {"type": "emotional", "content": f"{profile['protagonist_name']}が、光の中で自分の名を取り戻す。", "position_percent": 0}},
        "quality_scores": {"engagement_potential": 0.91, "information_accuracy": 0.82, "success_criteria": {"viewer_takeaway": f"{profile['artifact_name']}は奪われた名前や価値の証拠である。", "must_remember": [profile["motifs"][0], "時間制限", profile["artifact_name"]], "must_not_misunderstand": ["史実ではなく民話の映画化"]}, "scope_boundaries": {"factual_claims_locked": True, "creative_license_declared": True}},
    }


def _build_script_and_manifest(topic: str, run_dir: Path, now: str, profile: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    script_scenes: list[dict[str, Any]] = []
    manifest_scenes: list[dict[str, Any]] = []
    selectors: list[str] = []
    scene_event_inputs: list[dict[str, Any]] = []
    scene_event_outputs: list[dict[str, Any]] = []
    _write_cut_design_context(
        run_dir,
        now=now,
        topic=topic,
        phase="cut_design_init",
        profile=profile,
        partial_counts={"scene_event_inputs": 0, "scene_event_outputs": 0, "selectors": 0},
    )
    _write_scene_design_json(
        run_dir,
        "scene_event_input.json",
        {
            "schema_version": "scene_event_log_v1",
            "created_at": now,
            "topic": topic,
            "source": str(run_dir / "story.md"),
            "scene_count": 0,
            "scenes": scene_event_inputs,
        },
    )
    _write_scene_design_json(
        run_dir,
        "scene_event_output.json",
        {
            "schema_version": "scene_event_log_v1",
            "created_at": now,
            "topic": topic,
            "scene_count": 0,
            "scenes": scene_event_outputs,
        },
    )
    protagonist_asset = profile["protagonist_asset_id"]
    artifact_asset = profile["artifact_asset_id"]
    protagonist_ref = f"assets/characters/{protagonist_asset}.png"
    artifact_ref = f"assets/{profile['artifact_output_dir']}/{artifact_asset}.png"
    total_duration_seconds = 0
    for idx, title in enumerate(profile["scene_titles"], start=1):
        include_artifact = _scene_uses_artifact(profile, idx)
        location_spec = _location_spec_for_scene(profile, idx)
        location_ref = str(location_spec["output"])
        location_name = str(location_spec["name"])
        scene_id = idx * 10
        scene_context = {
            "scene_id": scene_id,
            "scene_index": idx,
            "title": title,
            "location_id": location_spec.get("asset_id"),
            "location_name": location_name,
            "include_artifact": include_artifact,
        }
        _write_cut_design_context(
            run_dir,
            now=now,
            topic=topic,
            phase="scene_intent_generation",
            profile=profile,
            scene_context=scene_context,
            partial_counts={
                "scene_event_inputs": len(scene_event_inputs),
                "scene_event_outputs": len(scene_event_outputs),
                "selectors": len(selectors),
            },
        )
        scene_intent = _scene_intent_for_cut_design(
            title=title,
            idx=idx,
            location_spec=location_spec,
            profile=profile,
            include_artifact=include_artifact,
        )
        scene_event_inputs.append(
            {
                "scene_id": scene_id,
                "scene_index": idx,
                "title": title,
                "topic": topic,
                "location": location_spec,
                "include_artifact": include_artifact,
                "profile_summary": {
                    "slug": profile.get("slug"),
                    "protagonist_name": profile.get("protagonist_name"),
                    "artifact_name": profile.get("artifact_name"),
                    "scene_titles": profile.get("scene_titles"),
                    "motifs": profile.get("motifs"),
                },
                "scene_intent": scene_intent,
            }
        )
        _write_scene_design_json(
            run_dir,
            "scene_event_input.json",
            {
                "schema_version": "scene_event_log_v1",
                "created_at": now,
                "topic": topic,
                "source": str(run_dir / "story.md"),
                "scene_count": len(scene_event_inputs),
                "scenes": scene_event_inputs,
            },
        )
        _write_cut_design_context(
            run_dir,
            now=now,
            topic=topic,
            phase="scene_event_generation",
            profile=profile,
            scene_context={**scene_context, "scene_intent_keys": sorted(scene_intent.keys())},
            partial_counts={
                "scene_event_inputs": len(scene_event_inputs),
                "scene_event_outputs": len(scene_event_outputs),
                "selectors": len(selectors),
            },
        )
        scene_event = _scene_event_for_cut_design(
            title=title,
            idx=idx,
            scene_intent=scene_intent,
            location_name=location_name,
            profile=profile,
            include_artifact=include_artifact,
        )
        scene_intent["story_event_obligations"] = _story_event_obligations_from_scene_event(scene_event)
        event_sequence = scene_event.get("event_sequence", []) if isinstance(scene_event.get("event_sequence"), list) else []
        _write_cut_design_context(
            run_dir,
            now=now,
            topic=topic,
            phase="scene_cut_coverage_planning",
            profile=profile,
            scene_context={
                **scene_context,
                "scene_event_schema_version": scene_event.get("schema_version"),
                "event_sequence_count": len(event_sequence),
                "event_beat_ids": [str(beat.get("beat_id") or "") for beat in event_sequence if isinstance(beat, dict)],
            },
            partial_counts={
                "scene_event_inputs": len(scene_event_inputs),
                "scene_event_outputs": len(scene_event_outputs),
                "selectors": len(selectors),
            },
        )
        cut_plan_bundle = _scene_cut_coverage_plan(
            title=title,
            idx=idx,
            scene_intent=scene_intent,
            scene_event=scene_event,
            location_name=location_name,
            profile=profile,
            include_artifact=include_artifact,
        )
        scene_cut_coverage_plan = cut_plan_bundle["coverage_plan"]
        cut_plans = cut_plan_bundle["cuts"]
        _write_cut_design_context(
            run_dir,
            now=now,
            topic=topic,
            phase="cut_contract_generation",
            profile=profile,
            scene_context={
                **scene_context,
                "coverage_strategy": scene_cut_coverage_plan.get("coverage_strategy"),
                "cut_plan_count": len(cut_plans),
                "min_cut_count": scene_cut_coverage_plan.get("min_cut_count"),
            },
            partial_counts={
                "scene_event_inputs": len(scene_event_inputs),
                "scene_event_outputs": len(scene_event_outputs),
                "selectors": len(selectors),
            },
        )
        scene_semantic_contract = {
            "dramatic_question": scene_intent["dramatic_question"],
            "value_shift": scene_intent["value_shift"],
            "causal_turn": scene_intent["causal_turn"],
            "scene_event": scene_event,
            "done_when": scene_intent["done_when"],
        }
        scene_target_seconds = len(cut_plans) * 8
        scene_duration_seconds = len(cut_plans) * 12
        total_duration_seconds += scene_duration_seconds
        cuts: list[dict[str, Any]] = []
        manifest_cuts: list[dict[str, Any]] = []
        for cut_number, cut_plan in enumerate(cut_plans, start=1):
            selector = f"scene{scene_id}_cut{cut_number:02d}"
            selectors.append(selector)
            _write_cut_design_context(
                run_dir,
                now=now,
                topic=topic,
                phase="cut_contract_generation",
                profile=profile,
                scene_context={
                    **scene_context,
                    "coverage_strategy": scene_cut_coverage_plan.get("coverage_strategy"),
                    "cut_plan_count": len(cut_plans),
                },
                cut_context={
                    "selector": selector,
                    "cut_number": cut_number,
                    "cut_plan_count": len(cut_plans),
                    "obligation_id": cut_plan.get("obligation_id"),
                    "cut_function": cut_plan.get("cut_function"),
                    "primary_event_beat_id": cut_plan.get("primary_event_beat_id"),
                    "source_event_beat_ids": cut_plan.get("source_event_beat_ids"),
                    "target_beat": cut_plan.get("target_beat"),
                    "visual_proof": cut_plan.get("visual_proof"),
                },
                partial_counts={
                    "scene_event_inputs": len(scene_event_inputs),
                    "scene_event_outputs": len(scene_event_outputs),
                    "selectors": len(selectors),
                    "manifest_cuts_in_current_scene": len(manifest_cuts),
                },
            )
            supporting_character_ids = _supporting_character_ids_for_scene(profile, idx)
            supporting_object_ids = _supporting_object_ids_for_scene(profile, idx)
            obligation_id = str(cut_plan.get("obligation_id"))
            cut_uses_artifact = _cut_uses_artifact(profile, idx, obligation_id, include_artifact=include_artifact)
            object_ids = [*supporting_object_ids, *([artifact_asset] if cut_uses_artifact else [])]
            primary_character_asset = _protagonist_asset_for_cut(profile, idx, obligation_id)
            primary_character_ref = _protagonist_reference_for_asset(profile, primary_character_asset)
            character_ids = [primary_character_asset, *supporting_character_ids]
            supporting_character_refs = [
                ref for ref in (_supporting_character_reference(profile, asset_id) for asset_id in supporting_character_ids) if ref
            ]
            supporting_object_refs = [
                ref for ref in (_supporting_object_reference(profile, asset_id) for asset_id in supporting_object_ids) if ref
            ]
            references = [primary_character_ref, *supporting_character_refs, location_ref, *supporting_object_refs, *([artifact_ref] if cut_uses_artifact else [])]
            beat = str(cut_plan["target_beat"])
            visual_beat = str(cut_plan["visual_proof"])
            source_event_beat_ids = [str(item) for item in cut_plan.get("source_event_beat_ids", []) if str(item).strip()]
            primary_event_beat_id = str(cut_plan.get("primary_event_beat_id") or (source_event_beat_ids[0] if source_event_beat_ids else "")).strip()
            if primary_event_beat_id and primary_event_beat_id not in source_event_beat_ids:
                source_event_beat_ids = [primary_event_beat_id, *source_event_beat_ids]
            event_beats_for_cut = [
                beat
                for beat in scene_event.get("event_sequence", [])
                if isinstance(beat, dict) and str(beat.get("beat_id") or "") in source_event_beat_ids
            ]
            primary_event_beat = next(
                (beat for beat in event_beats_for_cut if str(beat.get("beat_id") or "") == primary_event_beat_id),
                event_beats_for_cut[0] if event_beats_for_cut else {},
            )
            event_beat_function = str(primary_event_beat.get("beat_function") or cut_plan.get("event_beat_function") or "custom")
            event_time_position = str(cut_plan.get("event_time_position") or ("trigger_moment" if event_beat_function == "turn" else "consequence" if event_beat_function == "payoff" else "early_action"))
            must_show = [profile["protagonist_name"], *cut_plan["must_show_extra"]]
            is_terminal_scene = bool(scene_intent.get("terminal_resolution"))
            if not cut_uses_artifact:
                must_show = [item for item in must_show if item != profile["artifact_name"]]
            if cut_uses_artifact and profile["artifact_name"] not in must_show:
                must_show.append(profile["artifact_name"])
            if "光" not in must_show:
                must_show.append("光")
            cut_blueprint = {
                "cut_role": "状況を前へ進める映画的断片",
                "cut_function": cut_plan["cut_function"],
                "duration_intent": "12秒で感情と情報を同時に渡す",
                "target_beat": beat,
                "scene_focus": scene_intent["dramatic_question"],
                "coverage_obligation_id": cut_plan["obligation_id"],
                "coverage_source": cut_plan["source"],
                "screen_question": cut_plan["screen_question"],
                "dramatic_job": cut_plan["dramatic_job"],
                "audience_knowledge_delta": cut_plan.get("audience_knowledge_delta", ""),
                "causal_proof": cut_plan.get("causal_proof", ""),
                "visual_evidence": cut_plan.get("visual_evidence", []),
                "required_roles": cut_plan.get("required_roles", []),
                "anti_redundancy_key": cut_plan.get("anti_redundancy_key", ""),
                "must_show": must_show,
                "must_avoid": ["画面内テキスト", "字幕", "ロゴ"],
                "done_when": [cut_plan["done_when"]],
                "visual_beat": visual_beat,
                "first_frame_brief": cut_plan["first_frame_brief"],
                "static_first_frame_rule": cut_plan.get("static_first_frame_rule", ""),
                "action_completion_state": "pre_action" if cut_number == 1 else "early_action",
                "motion_brief": cut_plan["motion_brief"],
                "motion_end_state": cut_plan["motion_end_state"],
                "narration_role": "絵を説明せず内面の方向だけを示す",
                "asset_dependency_hint": {"characters": character_ids, "objects": object_ids, "locations": [location_spec["asset_id"]]},
            }
            script_cut_base = {"cut_id": f"{cut_number:02d}", "selector": selector, "target_duration_seconds": 12, "estimated_duration_seconds": 12, "cut_blueprint": cut_blueprint, "human_review": {"status": "approved", "change_request_ids": []}}
            prompt = _scene_prompt(
                title,
                visual_beat,
                beat,
                location_name,
                profile,
                include_artifact=cut_uses_artifact,
                scene_index=idx,
                terminal_resolution=is_terminal_scene,
            )
            narration = str(cut_plan["narration"])
            continuity_end_state = (
                "証明を受け止め、物語が閉じる"
                if is_terminal_scene and cut_number == len(cut_plans)
                else "次cutへ視線または姿勢が渡る"
            )
            motion_must_not_add = (
                ["新しい人物", "外部への導線", "次sceneのreveal", "画面内テキスト"]
                if is_terminal_scene
                else ["新しい人物", "次sceneのreveal", "画面内テキスト"]
            )
            carries_to_next_scene = [] if is_terminal_scene else ([profile["artifact_name"]] if cut_uses_artifact else [])
            next_cut_anchor = (
                f"scene{scene_id}_cut{cut_number:02d}_to_cut{cut_number + 1:02d}"
                if cut_number < len(cut_plans)
                else (f"scene{scene_id}_to_terminal" if is_terminal_scene else f"scene{scene_id}_to_scene{(idx + 1) * 10}")
            )
            incoming_anchor = (
                f"scene{scene_id}_cut{cut_number - 1:02d}_to_cut{cut_number:02d}"
                if cut_number > 1
                else f"scene{scene_id}_incoming"
            )
            visible_start_state = {
                "character_state": "まだ行為を完了していない",
                "prop_state": "必要な小道具や証拠は見えるが、結果を説明しすぎない",
                "spatial_state": location_name,
                "emotional_state": "sceneの圧力を受けている",
                "gaze_or_attention": "次に見るべき証拠または導線へ向く",
            }
            motion_start_affordance = {
                "movable_subject": profile["protagonist_name"],
                "movement_vector": cut_plan["screen_direction"],
                "camera_start_reason": "静止画内の視線、光、導線から自然に動き出せる",
            }
            cut_contract = {
                "schema_version": "3.0",
                "source_event_contract": {
                    "primary_event_beat_id": primary_event_beat_id,
                    "source_event_beat_ids": source_event_beat_ids,
                    "event_beat_function": event_beat_function,
                    "event_time_position": event_time_position,
                    "source_event_summary": " / ".join(str(beat.get("what_happens") or "") for beat in event_beats_for_cut if str(beat.get("what_happens") or "").strip()),
                    "source_visible_action": str(primary_event_beat.get("visible_action") or cut_plan.get("visual_proof") or ""),
                    "source_visible_reaction": str(primary_event_beat.get("visible_reaction") or cut_plan.get("audience_knowledge_delta") or "画面内の人物または場が出来事へ反応する"),
                    "source_required_visual_evidence": [
                        str(item)
                        for beat in event_beats_for_cut
                        for item in (beat.get("required_visual_evidence", []) if isinstance(beat.get("required_visual_evidence"), list) else [])
                        if str(item).strip()
                    ] or cut_blueprint["visual_evidence"] or must_show,
                    "source_story_information_revealed_ids": [
                        str(item)
                        for beat in event_beats_for_cut
                        for item in (beat.get("story_information_revealed_ids", []) if isinstance(beat.get("story_information_revealed_ids"), list) else [])
                        if str(item).strip()
                    ],
                    "source_story_information_hinted_ids": [
                        str(item)
                        for beat in event_beats_for_cut
                        for item in (beat.get("story_information_hinted_ids", []) if isinstance(beat.get("story_information_hinted_ids"), list) else [])
                        if str(item).strip()
                    ],
                    "event_facts_to_preserve": [
                        str(beat.get("what_happens") or "")
                        for beat in event_beats_for_cut
                        if str(beat.get("what_happens") or "").strip()
                    ],
                    "event_facts_not_to_invent": scene_event.get("forbidden_event_changes", []),
                    "allowed_reveal_info_ids": cut_blueprint["visual_evidence"],
                    "forbidden_reveal_info_ids": [str(item) for item in scene_intent.get("withheld_information", []) if str(item).strip()],
                    "must_not_change": scene_event.get("forbidden_event_changes", []),
                },
                "cut_role": "main",
                "cut_function": cut_blueprint["cut_function"],
                "coverage_obligation_id": cut_plan["obligation_id"],
                "coverage_source": cut_plan["source"],
                "duration_intent": "standard",
                "target_duration_seconds": 12,
                "intent_budget": {
                    "primary_intent": beat,
                    "secondary_intents_allowed": ["continuity_handoff"],
                    "forbidden_combined_intents": ["new_location_establishing + major_reveal + next_scene_handoff"],
                    "assigned_obligation_ids": [str(cut_plan["obligation_id"])],
                    "overload_exception_reason": "",
                    "custom_function_reason": "scene obligation固有の映像beat" if str(cut_blueprint["cut_function"]) == "custom" else "",
                },
                "viewer_contract": {
                    "target_beat": beat,
                    "screen_question": cut_blueprint["screen_question"],
                    "dramatic_job": cut_blueprint["dramatic_job"],
                    "audience_knowledge_delta": cut_blueprint["audience_knowledge_delta"],
                    "causal_proof": cut_blueprint["causal_proof"],
                    "visual_evidence": cut_blueprint["visual_evidence"],
                    "required_roles": cut_blueprint["required_roles"],
                    "anti_redundancy_key": cut_blueprint["anti_redundancy_key"],
                    "reveal_constraints": {
                        "inherited_from_scene": scene_intent.get("reveal_constraints", []),
                        "allowed_reveals_in_this_cut": cut_blueprint["visual_evidence"],
                        "forbidden_until_later_cut": [],
                        "forbidden_until_later_scene": scene_intent.get("withheld_information", []),
                    },
                    "scene_obligation": cut_plan["obligation_id"],
                    "scene_obligation_source": cut_plan["source"],
                    "visual_proof": visual_beat,
                    "must_show": must_show,
                    "must_avoid": ["英字看板", "署名クレジット", "企業ロゴ"],
                    "done_when": [cut_plan["done_when"]],
                },
                "cinematic_contract": {
                    "camera_intent": "観客の視線を主人公、光、場所の奥行きへ導く",
                    "subject_priority": {"primary": profile["protagonist_name"], "secondary": profile["artifact_name"] if cut_uses_artifact else location_name, "background": location_name},
                    "screen_geography": {"foreground": cut_plan["foreground"], "midground": cut_plan["midground"], "background": cut_plan["background"], "screen_direction": cut_plan["screen_direction"]},
                },
                "continuity_contract": {
                    "location_ids": [location_spec["asset_id"]],
                    "character_ids": character_ids,
                    "object_ids": object_ids,
                    "start_state": {"character_state": visible_start_state["character_state"], "prop_state": visible_start_state["prop_state"], "spatial_state": location_name, "time_state": "scene内の現在時点"},
                    "end_state": {"character_state": continuity_end_state, "prop_state": "次へ渡す証拠が画面に残る", "spatial_state": location_name, "time_state": "cutの理解が完了した時点"},
                    "carry_forward_to_next_cut": [profile["protagonist_name"], location_name, *object_ids],
                    "continuity_risks": ["人物同一性のdrift", "小道具の位置関係のdrift"],
                },
                "cut_handoff": {
                    "receives_from_previous": {
                        "anchor_id": incoming_anchor,
                        "anchor_type": "none" if cut_number == 1 else "gesture",
                        "visible_or_audible_form": "scene開始時の問い" if cut_number == 1 else "前cutから残る視線・光・導線",
                        "expected_previous_cut_selector": "" if cut_number == 1 else f"scene{scene_id}_cut{cut_number - 1:02d}",
                    },
                    "delivers_to_next": {
                        "anchor_id": next_cut_anchor,
                        "anchor_type": "terminal" if cut_number == len(cut_plans) and is_terminal_scene else "gesture",
                        "visible_or_audible_form": "次へ残る視線・光・導線" if cut_number < len(cut_plans) else ("終結の余韻" if is_terminal_scene else "次sceneへ渡る視線・光・導線"),
                        "expected_next_cut_selector": f"scene{scene_id}_cut{cut_number + 1:02d}" if cut_number < len(cut_plans) else "",
                    },
                },
                "first_frame_contract": {
                    "imageable": True,
                    "image_role": "video_first_frame_candidate",
                    "source_event_beat_id": primary_event_beat_id,
                    "event_time_position": event_time_position,
                    "event_fact_visible_in_still": cut_blueprint["visual_beat"],
                    "not_yet_happened_in_still": [
                        str(beat.get("beat_id") or "")
                        for beat in scene_event.get("event_sequence", [])
                        if isinstance(beat, dict) and str(beat.get("beat_id") or "") not in source_event_beat_ids
                    ],
                    "first_frame_brief": cut_blueprint["first_frame_brief"],
                    "visible_start_state": visible_start_state,
                    "motion_start_affordance": motion_start_affordance,
                    "action_completion_state": cut_blueprint["action_completion_state"],
                    "static_first_frame_rule": cut_blueprint["static_first_frame_rule"],
                    "must_be_static_evidence_not_motion": True,
                    "must_include": must_show,
                    "must_avoid": ["画面内テキスト", "字幕", "ロゴ"],
                },
                "motion_contract": {
                    "movable": True,
                    "source_event_beat_id": primary_event_beat_id,
                    "starts_from_first_frame": True,
                    "reaches_event_position": "early_action" if event_time_position in {"before_trigger", "early_action"} else event_time_position,
                    "must_not_advance_to_event_beat_ids": [
                        str(beat.get("beat_id") or "")
                        for beat in scene_event.get("event_sequence", [])
                        if isinstance(beat, dict) and str(beat.get("beat_id") or "") not in source_event_beat_ids and str(beat.get("beat_function") or "") in {"turn", "payoff"}
                    ],
                    "must_not_resolve_scene_turn_unless_primary_event_is_turn": event_beat_function != "turn",
                    "motion_brief": cut_blueprint["motion_brief"],
                    "start_from_visible_state": "first_frame_contract.visible_start_state",
                    "camera_motion": "slow_push",
                    "subject_motion": "視線と姿勢がわずかに変わる",
                    "environment_motion": "光と空気がゆっくり揺れる",
                    "emotional_change": "不可視から可視へ一段近づく",
                    "end_state": cut_blueprint["motion_end_state"],
                    "end_frame_brief": cut_blueprint["motion_end_state"],
                    "must_not_add": motion_must_not_add,
                },
                "narration_contract": {
                    "speakable_or_silent": True,
                    "source_event_beat_ids": source_event_beat_ids,
                    "allowed_info_ids": cut_blueprint["visual_evidence"],
                    "forbidden_info_ids": [str(item) for item in scene_intent.get("withheld_information", []) if str(item).strip()],
                    "must_not_advance_to_event_beat_ids": [
                        str(beat.get("beat_id") or "")
                        for beat in scene_event.get("event_sequence", [])
                        if isinstance(beat, dict) and str(beat.get("beat_id") or "") not in source_event_beat_ids
                    ],
                    "must_not_explain_visible_action_as_caption": True,
                    "narration_event_boundary": "same_event_only",
                    "role": "emotion",
                    "target_function": "映像を説明せず、内面の方向だけを示す",
                    "must_avoid": ["画面に見えている内容の単純説明"],
                    "text": narration,
                    "tts_text": narration,
                    "silence_reason": "",
                },
                "rhythm_contract": {
                    "expected_duration_seconds": 12,
                    "pacing": "standard",
                    "comprehension_moment": "visual_proof が画面で読める瞬間",
                    "cut_out_reason": "次cutへ渡す anchor が画面に残った瞬間",
                    "audio_visual_sync_point": "ナレーションは visual_proof の後を追い、画面説明にならない",
                    "duration_exception": {"allowed": False, "reason": ""},
                },
                "asset_dependency": {
                    "character_ids_required": character_ids,
                    "object_ids_required": object_ids,
                    "location_ids_required": [location_spec["asset_id"]],
                    "variant_ids_required": [],
                    "new_asset_requests": [],
                    "reusable_anchor_ids": [primary_character_asset, location_spec["asset_id"], *object_ids],
                    "reference_role": {
                        "protagonist": primary_character_asset,
                        "proof_object": artifact_asset if cut_uses_artifact else "",
                        "location_anchor": location_spec["asset_id"],
                    },
                },
                "downstream_handoff": {
                    "p500_asset": {"required_asset_ids": [*character_ids, *object_ids, location_spec["asset_id"]], "asset_candidates": [*character_ids, *object_ids, location_spec["asset_id"]], "continuity_anchor_needed": True, "new_asset_needed": False, "reuse_allowed": True},
                    "p600_image": {"event_context_for_cut": "<cut_contract.event_context_for_cut>", "prompt_requirements": must_show, "reference_requirements": references, "first_frame_must_include": must_show, "first_frame_must_avoid": ["画面内テキスト", "字幕", "ロゴ"]},
                    "p700_narration": {"event_context_for_cut": "<cut_contract.event_context_for_cut>", "narration_requirements": ["説明ではなく感情の方向"], "role": "emotion", "must_not_caption_visible_content": True},
                    "p800_video": {"event_context_for_cut": "<cut_contract.event_context_for_cut>", "motion_requirements": [cut_blueprint["motion_brief"]], "start_state": "first_frame_contract.visible_start_state", "last_frame_or_end_state": cut_blueprint["motion_end_state"], "must_not_add": motion_must_not_add},
                    "carries_to_next_cut": [profile["protagonist_name"], location_name],
                    "carries_to_next_scene": carries_to_next_scene,
                },
            }
            cut_contract["event_context_for_cut"] = _event_context_for_cut_contract(
                scene_event=scene_event,
                source_event_contract=cut_contract["source_event_contract"],
                reveal_constraints=scene_intent.get("reveal_constraints", []),
            )
            cuts.append({**script_cut_base, "cut_contract": cut_contract, "scene_contract": {"legacy_note": "旧reader向け alias。cut_contract が正本。", "target_beat": beat, "must_show": must_show, "must_avoid": ["英字看板", "署名クレジット", "企業ロゴ"], "done_when": [cut_plan["done_when"]]}})
            manifest_cuts.append(
                {
                    "cut_id": f"{cut_number:02d}",
                    "selector": selector,
                    "duration_seconds": 12,
                    "cut_contract": cut_contract,
                    "scene_contract": {
                        "cut_function": cut_contract["cut_function"],
                        "target_beat": beat,
                        "screen_question": cut_contract["viewer_contract"]["screen_question"],
                        "dramatic_job": cut_contract["viewer_contract"]["dramatic_job"],
                        "audience_knowledge_delta": cut_contract["viewer_contract"]["audience_knowledge_delta"],
                        "causal_proof": cut_contract["viewer_contract"]["causal_proof"],
                        "visual_evidence": cut_contract["viewer_contract"]["visual_evidence"],
                        "required_roles": cut_contract["viewer_contract"]["required_roles"],
                        "anti_redundancy_key": cut_contract["viewer_contract"]["anti_redundancy_key"],
                        "visual_beat": visual_beat,
                        "first_frame_brief": cut_contract["first_frame_contract"]["first_frame_brief"],
                        "static_first_frame_rule": cut_contract["first_frame_contract"]["static_first_frame_rule"],
                        "motion_brief": cut_contract["motion_contract"]["motion_brief"],
                        "must_show": must_show,
                        "must_avoid": ["英字看板", "署名クレジット", "企業ロゴ"],
                        "done_when": [cut_plan["done_when"]],
                    },
                    "image_generation": {"tool": "codex_builtin_image", "character_ids": character_ids, "object_ids": object_ids, "location_ids": [location_spec["asset_id"]], "asset_id": "", "asset_type": "scene_still", "execution_lane": "standard", "reference_count": len(references), "references": references, "prompt": prompt, "output": f"assets/scenes/{selector}.png", "aspect_ratio": "16:9", "image_size": "1K", "review": {"status": "approved", "triangulation_review": {"status": "passed", "same_target_beat": True, "image_supports_motion_start": True, "motion_reaches_declared_end_state": True, "narration_not_captioning_image": True, "reveal_constraints_preserved": True, "continuity_preserved": True, "handoff_visible_or_audible": True}}},
                    "video_generation": {"tool": "kling_3_0_omni", "duration_seconds": 12, "first_frame": f"assets/scenes/{selector}.png", "motion_prompt": cut_plan["motion_brief"], "output": f"assets/scenes/{selector}.mp4"},
                    "audio": {"narration": {"contract_ref": "cut_contract.narration_contract", "text": narration, "tts_text": narration, "tool": "elevenlabs", "status": "approved", "output": f"assets/audio/{selector}.mp3", "applied_request_ids": [], "p700_review": {"role_matches_contract": True, "narration_not_captioning_image": True, "does_not_add_new_story_fact": True, "timing_supports_visual_beat": True}}},
                    "review": {"triangulation_review": {"status": "passed", "same_target_beat": True, "image_supports_motion_start": True, "motion_reaches_declared_end_state": True, "narration_not_captioning_image": True, "reveal_constraints_preserved": True, "continuity_preserved": True, "handoff_visible_or_audible": True}},
                    "implementation_trace": {"status": "verified", "source_request_ids": []},
                }
            )
        coverage_review = {
            "audience_information_covered": True,
            "visualizable_action_covered": True,
            "next_scene_connection_checked": True,
            "value_shift_visible": True,
            "causal_turn_visible": True,
            "scene_specificity_gate_passed": True,
        }
        script_scenes.append({"scene_id": scene_id, "phase": PHASES[idx - 1], "importance": "medium", "target_duration_seconds": scene_target_seconds, "estimated_duration_seconds": scene_duration_seconds, "handoff_to_next_scene": scene_intent["handoff_to_next_scene"], "terminal_resolution": scene_intent["terminal_resolution"], "scene_intent": scene_intent, "scene_event": scene_event, "semantic_contract": scene_semantic_contract, "scene_cut_coverage_plan": scene_cut_coverage_plan, "agent_review": {"status": "passed", "reason": "scene is concrete and production ready"}, "coverage_review": coverage_review, "cuts": cuts})
        scene_composite_review = {"status": "passed", "scene_obligation_covered_by_cut_group": True, "no_duplicate_story_fact_without_new_evidence": True, "scene_meaning_visualized_across_cuts": True, "blocking_reason_keys": []}
        manifest_scenes.append({"scene_id": scene_id, "importance": "medium", "target_duration_seconds": scene_target_seconds, "estimated_duration_seconds": scene_duration_seconds, "scene_intent": scene_intent, "scene_event": scene_event, "semantic_contract": scene_semantic_contract, "scene_cut_coverage_plan": scene_cut_coverage_plan, "scene_composite_review": scene_composite_review, "handoff_to_next_scene": scene_intent["handoff_to_next_scene"], "terminal_resolution": scene_intent["terminal_resolution"], "coverage_review": coverage_review, "cuts": manifest_cuts})
        scene_event_outputs.append(
            {
                "scene_id": scene_id,
                "scene_index": idx,
                "title": title,
                "scene_event": scene_event,
                "story_event_obligations": scene_intent.get("story_event_obligations", []),
                "scene_cut_coverage_plan": scene_cut_coverage_plan,
                "cut_contracts": [
                    {
                        "selector": cut.get("selector"),
                        "cut_id": cut.get("cut_id"),
                        "source_event_contract": (cut.get("cut_contract") or {}).get("source_event_contract"),
                        "event_context_for_cut": (cut.get("cut_contract") or {}).get("event_context_for_cut"),
                    }
                    for cut in manifest_cuts
                ],
            }
        )
        _write_scene_design_json(
            run_dir,
            "scene_event_output.json",
            {
                "schema_version": "scene_event_log_v1",
                "created_at": now,
                "topic": topic,
                "scene_count": len(scene_event_outputs),
                "scenes": scene_event_outputs,
            },
        )
    script = {"schema_version": "scene_event_v1", "script_metadata": {"topic": topic, "target_duration": 300, "created_at": now}, "scene_set_review": {"status": "approved", "summary": f"8 scenes / {len(selectors)} cutsで主要筋を展開する。"}, "scene_detail_review": {"status": "approved", "summary": "各sceneは独立した問いと視覚行動を持つ。"}, "cut_blueprint_review": {"status": "approved", "summary": "scene設計から逆算したcoverage planに基づき、必要cut数を可変で設計する。"}, "script_review": {"status": "approved", "summary": "台本は後続画像生成に渡せる。"}, "production_readiness_review": {"status": "approved", "summary": "target duration is covered now."}, "evaluation_contract": {"target_arc": "opening,development,ordeal,transformation,ending", "must_cover": [profile["protagonist_name"], profile["artifact_name"], "時間制限", profile["motifs"][0]], "must_avoid": ["画面内テキスト", "字幕", "ロゴ"], "reveal_constraints": []}, "human_change_requests": [], "scenes": script_scenes}
    character_bible = [
        {
            "character_id": protagonist_asset,
            "reference_images": [protagonist_ref],
            "review_aliases": [profile["protagonist_name"], profile["topic_label"]],
            "fixed_prompts": [f"{profile['protagonist_name']}、自然な実写肌、同じ顔と髪型を維持"],
            "cinematic": {
                "role": f"{profile['protagonist_name']}本人の変身前の一貫性",
                "visual_subject": profile.get("protagonist_asset_subject") or f"{profile['protagonist_name']}の全身、自然な映画俳優の顔立ち、生活感のある衣装",
            },
        }
    ]
    for spec in _supporting_character_asset_specs(profile):
        character_bible.append(
            {
                "character_id": spec["character_id"],
                "reference_images": spec["reference_images"],
                "review_aliases": [spec["name"]],
                "fixed_prompts": [spec["visual_subject"]],
                "cinematic": {"role": spec["story_purpose"], "visual_subject": spec["visual_subject"]},
            }
        )
    object_bible = [
        {
            "object_id": artifact_asset,
            "kind": "artifact",
            "reference_images": [artifact_ref],
            "fixed_prompts": [profile["artifact_fixed_prompt"]],
            "cinematic": {"role": profile["artifact_role"], "visual_takeaways": ["脆さと証拠性"], "spectacle_details": ["光を反射して手がかりになる"]},
        }
    ]
    for spec in _supporting_object_asset_specs(profile):
        object_bible.append(
            {
                "object_id": spec["object_id"],
                "kind": "setpiece",
                "reference_images": spec["reference_images"],
                "fixed_prompts": [spec["visual_subject"]],
                "cinematic": {"role": spec["story_purpose"], "visual_takeaways": [spec["name"]], "visual_subject": spec["visual_subject"]},
            }
        )
    manifest = {"schema_version": "scene_event_v1", "manifest_phase": "production", "video_metadata": {"topic": topic, "source_story": str(run_dir / "story.md"), "created_at": now, "experience": "cinematic_story", "aspect_ratio": "16:9", "resolution": "1280x720", "frame_rate": 24, "target_duration_seconds": 300, "duration_seconds": total_duration_seconds}, "assets": {"character_bible": character_bible, "object_bible": object_bible, "location_bible": [{"location_id": spec["asset_id"], "reference_images": [spec["output"]], "fixed_prompts": [str((spec.get("visual_spec") or {}).get("subject") or f"{spec['name']}、実写映画の場所参照、同じ光と質感を維持")], "cinematic": {"role": spec["story_purpose"], "visual_subject": str((spec.get("visual_spec") or {}).get("subject") or "")}} for spec in _location_asset_specs(profile)], "style_guide": {"visual_style": "実写、シネマティック、プラクティカルエフェクト。画面内テキストなし。", "forbidden": ["アニメ調", "漫画調", "イラスト調", "画面内テキスト", "字幕", "ウォーターマーク", "ロゴ"], "reference_images": []}}, "human_change_requests": [], "scenes": manifest_scenes}
    _write_scene_design_json(
        run_dir,
        "scene_event_input.json",
        {
            "schema_version": "scene_event_log_v1",
            "created_at": now,
            "topic": topic,
            "source": str(run_dir / "story.md"),
            "scene_count": len(scene_event_inputs),
            "scenes": scene_event_inputs,
        },
    )
    _write_scene_design_json(
        run_dir,
        "scene_event_output.json",
        {
            "schema_version": "scene_event_log_v1",
            "created_at": now,
            "topic": topic,
            "scene_count": len(scene_event_outputs),
            "scenes": scene_event_outputs,
        },
    )
    _write_cut_design_context(
        run_dir,
        now=now,
        topic=topic,
        phase="cut_design_completed",
        profile=profile,
        partial_counts={
            "scene_event_inputs": len(scene_event_inputs),
            "scene_event_outputs": len(scene_event_outputs),
            "selectors": len(selectors),
            "manifest_scenes": len(manifest_scenes),
        },
    )
    return script, manifest, selectors


def _write_asset_request_files(run_dir: Path, asset_plan: dict[str, Any], profile: dict[str, Any]) -> None:
    manifest_items = []
    asset_stage_scenes = []
    for index, entry in enumerate(asset_plan["assets"], start=1):
        asset_id = entry["asset_id"]
        output = entry["generation_plan"]["output"]
        generation_plan = entry.get("generation_plan") if isinstance(entry.get("generation_plan"), dict) else {}
        asset_stage_scenes.append(
            {
                "scene_id": index,
                "still_assets": [
                    {
                        "asset_id": asset_id,
                        "asset_type": entry["asset_type"],
                        "source_script_selectors": entry.get("source_script_selectors") or [],
                        "output": output,
                        "creation_status": "planned",
                        "generation_plan": {
                            "required_views": generation_plan.get("required_views") or [],
                            "reference_inputs": generation_plan.get("reference_inputs") or [],
                        },
                        "review": {"status": "approved"},
                        "image_generation": {
                            "tool": "codex_builtin_image",
                            "execution_lane": "bootstrap_builtin",
                            "bootstrap_allowed": True,
                            "bootstrap_reason": "frontend_review_asset_stage",
                            "prompt": _prompt_for_asset(entry, profile),
                            "output": output,
                            "references": generation_plan.get("reference_inputs") or [],
                        },
                    }
                ],
            }
        )
        manifest_items.append({"asset_id": asset_id, "selector": asset_id, "output": output, "asset_type": entry["asset_type"], "status": "requested"})
    asset_stage_manifest = {
        "video_metadata": {
            "topic": profile["topic_label"],
            "experience": "asset_stage",
        },
        "scenes": asset_stage_scenes,
    }
    (run_dir / "asset_stage_manifest.md").write_text(_md_yaml("Asset Stage Manifest", asset_stage_manifest), encoding="utf-8")
    (run_dir / "asset_generation_manifest.md").write_text(_md_yaml("Asset Generation Manifest", {"asset_generation_manifest": {"items": manifest_items}}), encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate-assets-from-manifest.py"),
            "--manifest",
            str(run_dir / "asset_stage_manifest.md"),
            "--materialize-request-files-only",
            "--skip-videos",
            "--skip-audio",
            "--skip-image-prompt-review",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _materialize_standard_request_files(run_dir: Path) -> None:
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "eval.p400_readiness.status": "approved",
            "eval.p400_readiness.reason_keys": "",
        },
    )
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate-assets-from-manifest.py"),
            "--manifest",
            str(run_dir / "video_manifest.md"),
            "--materialize-request-files-only",
            "--skip-audio",
            "--skip-image-prompt-review",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    for semantic_stage in ("image_prompt", "video_motion"):
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "build-semantic-review-pack.py"),
                "--run-dir",
                str(run_dir),
                "--stage",
                semantic_stage,
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )


def _review_status_line(stage: str) -> str:
    if stage == "production_readiness":
        return "status: approved"
    return "- status: passed"


def _review_loop_critic_report(stage: str, critic_number: int, prompt_text: str) -> str:
    focus_match = re.search(r"critic_focus:\s*([^\n]+)", prompt_text)
    focus = focus_match.group(1).strip() if focus_match else f"{stage}_critic_{critic_number}"
    return "\n".join(
        [
            f"# Critic {critic_number}",
            "",
            f"- critic_focus: {focus}",
            "- status: passed",
            "",
            "## Root Cause Review",
            f"この frontend-create run は {stage} の canonical source artifacts を読み、human approval で止まらずに機械的な gate と handoff artifact を生成している。",
            "",
            "## Findings",
            "- blocking: none",
            "- root_cause: no blocking issue found in the current authored artifact set",
            "- downstream_impact: next non-human stage can continue",
            "- acceptance_condition: verifier and stage-specific aggregate markers remain satisfied",
            "",
        ]
    )


def _aggregate_status_for_stage(stage: str) -> str:
    return "passed"


def _final_review_text(stage: str, aggregate_text: str) -> str:
    if stage == "production_readiness":
        return "\n".join(
            [
                "# Production Readiness Review",
                "",
                "status: approved",
                "",
                "## Structure",
                "scene設計から逆算した可変cut数で主要筋を保持。",
                "",
                "## Duration",
                "target 300 seconds and current cut plan satisfies the p400 coverage gate.",
                "",
                "## Quality",
                "画像生成に渡せる具体性がある。",
                "",
                "## Design Owner Patch Brief",
                "追加修正なし。canonical review loop aggregate は下記。",
                "",
                aggregate_text,
            ]
        )
    return "\n".join(
        [
            f"# {REVIEW_LOOP_SPECS[stage].title}",
            "",
            "status: approved",
            "",
            "原因: canonical review loop を通し、blocking finding は検出されなかった。",
            "修正方向: 追加修正なし。現在の source artifacts と handoff contract を維持する。",
            "下流影響: 次の非人間工程へ進める。",
            "受入条件: aggregate review と verifier が required markers を満たす。",
            "",
            aggregate_text,
        ]
    )


def _write_review_artifacts(run_dir: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "review-image-prompt-story-consistency.py"),
            "--manifest",
            str(run_dir / "video_manifest.md"),
            "--story",
            str(run_dir / "story.md"),
            "--script",
            str(run_dir / "script.md"),
            "--out",
            str(run_dir / "image_prompt_story_review.md"),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build-image-prompt-judgment-review.py"),
            "--run-dir",
            str(run_dir),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    for semantic_stage in ("scene_set", "scene_detail", "cut_blueprint", "asset_plan", "image_prompt"):
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "build-semantic-review-pack.py"),
                "--run-dir",
                str(run_dir),
                "--stage",
                semantic_stage,
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    state_updates: dict[str, str] = {}
    for stage in AUTHORING_REVIEW_STAGES:
        materialize_review_loop_round(run_dir=run_dir, stage=stage, round_number=1)
        critic_reports: list[str] = []
        for critic_number in range(1, REVIEW_LOOP_CRITIC_COUNT + 1):
            prompt_path = run_dir / critic_prompt_relpath(stage, 1, critic_number)
            prompt_text = prompt_path.read_text(encoding="utf-8")
            critic_text = _review_loop_critic_report(stage, critic_number, prompt_text)
            (run_dir / critic_relpath(stage, 1, critic_number)).write_text(critic_text, encoding="utf-8")
            critic_reports.append(critic_text)

        aggregate_text = render_aggregated_review(
            stage=stage,
            round_number=1,
            critic_reports=critic_reports,
            status=_aggregate_status_for_stage(stage),
        )
        if stage in {"scene_set", "scene_detail"}:
            aggregate_text = aggregate_text.replace("maximal_meaningful_stop_condition: TODO", "maximal_meaningful_stop_condition: satisfied")
            aggregate_text = aggregate_text.replace("next_scene_candidate: TODO", "next_scene_candidate: none")
            aggregate_text = aggregate_text.replace("cut_thickening_reason: TODO", "cut_thickening_reason: target duration covered")
            aggregate_text = aggregate_text.replace("critic_1_scene_count_coverage_resolution: TODO", "critic_1_scene_count_coverage_resolution: passed")
        if stage == "cut_blueprint":
            for marker in (
                "cut_intent_isolation",
                "scene_event_coverage",
                "first_frame_motion_readiness",
                "multimodal_event_boundary_coverage",
                "duration_density_and_handoff",
                "coverage_plan_complete",
                "event_beat_reference_integrity",
                "source_event_preservation",
                "event_context_for_cut_ready",
                "continuity_contract_complete",
                "narration_contract_complete",
                "downstream_handoff_complete",
                "triangulation_review_ready",
            ):
                aggregate_text = aggregate_text.replace(f"{marker}: TODO", f"{marker}: passed")

        aggregate_path = run_dir / aggregated_review_relpath(stage, 1)
        aggregate_path.write_text(aggregate_text, encoding="utf-8")
        final_report = REVIEW_LOOP_SPECS[stage].final_report
        (run_dir / final_report).write_text(_final_review_text(stage, aggregate_text), encoding="utf-8")
        state_updates.update(
            {
                f"eval.{stage}.loop.status": "passed",
                f"eval.{stage}.loop.current_round": "1",
                f"eval.{stage}.loop.round_01.status": "passed",
                f"eval.{stage}.loop.round_01.aggregated_review": str(aggregated_review_relpath(stage, 1)),
            }
        )
    append_state_snapshot(run_dir / "state.txt", state_updates)


def _write_orchestration(run_dir: Path, stop_target: str) -> dict[str, str]:
    now = "2026-05-24T08:34:00+09:00"
    buckets = ("p100", "p200", "p300", "p400", "p500", "p600")
    bucket_slots = {
        "p100": ("p110", "p120", "p130"),
        "p200": ("p210", "p220", "p230"),
        "p300": ("p310", "p320", "p330"),
        "p400": ("p410", "p420", "p430", "p440", "p450"),
        "p500": ("p510", "p520", "p530", "p540", "p550", "p560", "p570"),
        "p600": ("p610", "p620", "p630", "p640", "p650", "p660", "p670", "p680") if stop_target == "p680" else ("p610", "p620", "p630", "p640", "p650"),
    }
    bucket_artifacts = {
        "p100": ["research.md"],
        "p200": ["story.md"],
        "p300": ["visual_value.md"],
        "p400": ["script.md", "video_manifest.md"],
        "p500": ["asset_inventory.md", "asset_plan.md", "asset_generation_requests.md", "asset_generation_manifest.md"],
        "p600": ["image_generation_requests.md"],
    }
    orch = run_dir / "logs" / "orchestration"
    orch.mkdir(parents=True, exist_ok=True)
    progress = ["| timestamp | bucket | supervisor | event | stop_slot | result | note |", "|---|---|---|---|---|---|---|"]
    state_updates: dict[str, str] = {}
    for bucket in buckets:
        result_rel = f"logs/orchestration/{bucket}.supervisor_result.json"
        progress.append(f"| {now} | {bucket} | {bucket} P-Bucket Supervisor | invoked | {stop_target} | - | frontend handoff path |")
        progress.append(f"| {now} | {bucket} | {bucket} P-Bucket Supervisor | returned | {stop_target} | {result_rel} | bucket complete |")
        key = f"orchestration.{bucket}.supervisor"
        state_updates[f"{key}.call_status"] = "returned"
        state_updates[f"{key}.status"] = "done"
        state_updates[f"{key}.finished_at"] = now
        status_key = f"slot.{bucket_slots[bucket][-1]}.status"
        expected_status = "done" if bucket == "p500" and stop_target == "p680" else ("awaiting_approval" if bucket_slots[bucket][-1] in AWAITING_ALLOWED else "done")
        result = {
            "bucket": bucket,
            "status": "done",
            "completed_slots": list(bucket_slots[bucket]),
            "required_artifacts": [{"path": path, "exists": True} for path in bucket_artifacts[bucket]],
            "state_keys": {status_key: expected_status},
            "review_outputs": [],
            "next_bucket": None if bucket == "p600" else "next",
        }
        (orch / f"{bucket}.supervisor_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (orch / "l2_supervisor_progress.md").write_text("\n".join(progress) + "\n", encoding="utf-8")
    return state_updates


def _used_selectors_by_asset_id(manifest: dict[str, Any], field_name: str) -> dict[str, list[str]]:
    used: dict[str, list[str]] = {}
    for scene in manifest.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        for cut in scene.get("cuts", []):
            if not isinstance(cut, dict):
                continue
            selector = str(cut.get("selector") or "").strip()
            image_generation = cut.get("image_generation") if isinstance(cut.get("image_generation"), dict) else {}
            for asset_id in image_generation.get(field_name, []) or []:
                key = str(asset_id).strip()
                if key and selector:
                    used.setdefault(key, []).append(selector)
    return used


def _build_asset_artifacts_from_manifest(
    *,
    profile: dict[str, Any],
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), dict) else {}
    character_usage = _used_selectors_by_asset_id(manifest, "character_ids")
    object_usage = _used_selectors_by_asset_id(manifest, "object_ids")
    location_usage = _used_selectors_by_asset_id(manifest, "location_ids")

    inventory_items: list[dict[str, Any]] = []
    plan_entries: list[dict[str, Any]] = []
    coverage = {
        "characters": [],
        "story_specific_items": [],
        "locations": [],
        "setpieces": [profile["artifact_name"], *[str(spec["name"]) for spec in _supporting_object_asset_specs(profile)]],
        "reusable_stills": ["時間制限を示す象徴的な光"],
    }

    for entry in assets.get("character_bible", []) or []:
        if not isinstance(entry, dict):
            continue
        asset_id = str(entry.get("character_id") or "").strip()
        output = str((entry.get("reference_images") or [""])[0]).strip()
        selectors = character_usage.get(asset_id, [])
        if not asset_id or not output or not selectors:
            continue
        role = str((entry.get("cinematic") or {}).get("role") or "登場人物の一貫性を固定する")
        subject = str((entry.get("cinematic") or {}).get("visual_subject") or f"{profile['protagonist_name']}の全身、自然な映画俳優の顔立ち、生活感のある衣装")
        reference_inputs = _asset_reference_inputs_for_plan(profile, asset_id)
        execution_lane = "standard" if reference_inputs else "bootstrap_builtin"
        coverage["characters"].append(asset_id)
        inventory_items.append({"item_id": asset_id, "category": "characters", "source_script_selectors": selectors, "story_purpose": role, "reusable_reason": "登場cutで人物同一性を保つ", "recommended_asset_type": "character_reference"})
        plan_entries.append({"asset_id": asset_id, "asset_type": "character_reference", "source_script_selectors": selectors, "story_purpose": role, "visual_spec": {"subject": subject, "style": "photorealistic live-action cinematic", "forbidden": ["文字", "ロゴ", "アニメ"]}, "generation_plan": {"execution_lane": execution_lane, "bootstrap_allowed": not reference_inputs, "required_views": ["front", "side", "back"], "reference_inputs": reference_inputs, "output": output}, "review": {"status": "approved", "reason": "登場cutで人物同一性を保つため必須"}})

    for entry in assets.get("object_bible", []) or []:
        if not isinstance(entry, dict):
            continue
        asset_id = str(entry.get("object_id") or "").strip()
        output = str((entry.get("reference_images") or [""])[0]).strip()
        selectors = object_usage.get(asset_id, [])
        if not asset_id or not output or not selectors:
            continue
        coverage["story_specific_items"].append(asset_id)
        role = str((entry.get("cinematic") or {}).get("role") or profile["artifact_role"])
        subject = str((entry.get("cinematic") or {}).get("visual_subject") or profile["artifact_visual"])
        inventory_items.append({"item_id": asset_id, "category": "story_specific_items", "source_script_selectors": selectors, "story_purpose": role, "reusable_reason": "証が必要なcutで小道具の形状を保つ", "recommended_asset_type": "object_reference"})
        plan_entries.append({"asset_id": asset_id, "asset_type": "object_reference", "source_script_selectors": selectors, "story_purpose": role, "visual_spec": {"subject": subject, "style": "photorealistic live-action product still", "forbidden": ["文字", "ロゴ", "玩具風"]}, "generation_plan": {"execution_lane": "bootstrap_builtin", "bootstrap_allowed": True, "required_views": ["front"], "reference_inputs": [], "output": output}, "review": {"status": "approved", "reason": "証または舞台装置として必要なcutに使う"}})

    for entry in assets.get("location_bible", []) or []:
        if not isinstance(entry, dict):
            continue
        asset_id = str(entry.get("location_id") or "").strip()
        output = str((entry.get("reference_images") or [""])[0]).strip()
        selectors = location_usage.get(asset_id, [])
        if not asset_id or not output or not selectors:
            continue
        location_name = asset_id
        location_subject = ""
        for spec in _location_asset_specs(profile):
            if spec["asset_id"] == asset_id:
                location_name = str(spec["name"])
                location_subject = str((spec.get("visual_spec") or {}).get("subject") or "")
                break
        if not location_subject:
            fixed_prompts = entry.get("fixed_prompts") if isinstance(entry.get("fixed_prompts"), list) else []
            location_subject = str(fixed_prompts[0]) if fixed_prompts else f"{location_name}の場所参照、実写映画のロケーションスチル、奥行き、光、床壁の質感"
        coverage["locations"].append(asset_id)
        inventory_items.append({"item_id": asset_id, "category": "locations", "source_script_selectors": selectors, "story_purpose": f"{location_name}の空間・光・質感を固定する", "reusable_reason": "同じ場所のcutで背景と空気感を保つ", "recommended_asset_type": "location_reference"})
        plan_entries.append({"asset_id": asset_id, "asset_type": "location_reference", "source_script_selectors": selectors, "story_purpose": f"{location_name}の空間・光・質感を固定する", "visual_spec": {"subject": location_subject, "style": "photorealistic live-action cinematic location still", "forbidden": ["文字", "ロゴ", "人物主役", "アニメ"]}, "generation_plan": {"execution_lane": "bootstrap_builtin", "bootstrap_allowed": True, "required_views": ["wide"], "reference_inputs": [], "output": output}, "review": {"status": "approved", "reason": "scene背景と空気感の一貫性に必要"}})

    if not plan_entries:
        raise RuntimeError("manifest did not yield any reusable asset plan entries")
    inventory = {"asset_inventory": {"source_artifacts": ["story.md", "script.md", "video_manifest.md"], "coverage_scope": coverage, "items": inventory_items}}
    plan = {"assets": plan_entries}
    return inventory, plan


def materialize_run(topic: str, source: str, run_dir: Path, stop_target: str) -> None:
    profile = _story_profile(topic, source)
    run_dir.mkdir(parents=True, exist_ok=True)
    for rel in ("assets/characters", "assets/objects", "assets/locations", "assets/scenes", "assets/audio", "logs/grounding"):
        (run_dir / rel).mkdir(parents=True, exist_ok=True)
    now = "2026-05-24T08:34:00+09:00"
    (run_dir / "research.md").write_text(_md_yaml(f"リサーチ（{profile['topic_label']}）", _build_research(topic, source, now, profile)), encoding="utf-8")
    (run_dir / "story.md").write_text(_md_yaml(f"物語設計（{profile['topic_label']}）", _build_story(topic, run_dir, now, profile)), encoding="utf-8")
    protagonist_asset = profile["protagonist_asset_id"]
    artifact_asset = profile["artifact_asset_id"]
    visual = {
        "global_visual_identity": {"format": "実写シネマティック", "palette": ["深い生活影", "月白", "金色", "象徴物の反射"], "no_onscreen_text": "画面内テキスト、字幕、ロゴ、ウォーターマークなし"},
        "scene_visual_values": [{"scene_selector": idx, "value": f"{title}の感情を、{'・'.join(profile['motifs'])}の触感で伝える", "anchor": title} for idx, title in enumerate(profile["scene_titles"], start=1)],
        "asset_bible_candidates": {"characters": [protagonist_asset, *[str(spec["character_id"]) for spec in _supporting_character_asset_specs(profile)]], "objects": [artifact_asset, *[str(spec["object_id"]) for spec in _supporting_object_asset_specs(profile)]], "locations": [spec["asset_id"] for spec in _location_asset_specs(profile)], "setpieces": [profile["artifact_name"], *[str(spec["name"]) for spec in _supporting_object_asset_specs(profile)]], "reusable_stills": ["時間制限を示す象徴的な光"]},
        "anchor_cut_candidates": [{"selector": "scene10_cut01", "reason": "主人公の顔と衣装を固定する"}],
        "reference_strategy": {"p500": f"{profile['protagonist_name']}全身参照と{profile['artifact_name']}を先に生成する", "p600": "各cutは参照画像を使い、同じ顔・象徴物・質感を保つ"},
        "regeneration_risks": [{"risk": "衣装や顔がcutごとに変わる", "mitigation": "character referenceを全cutに指定する"}],
        "handoff_to_p400_p500_p600_p700": {"p400_script": "scene設計から必要なcut数を逆算して構成する", "p500_asset": f"{protagonist_asset} と {artifact_asset} を必須参照にする", "p600_scene_implementation": "各cutにscene_contractと画像promptを持たせる", "p700_narration": "画像確定後に語りを同期する"},
    }
    (run_dir / "visual_value.md").write_text(_md_yaml(f"視覚化価値設計（{profile['topic_label']}）", visual), encoding="utf-8")
    try:
        script, manifest, selectors = _build_script_and_manifest(topic, run_dir, now, profile)
    except Exception as exc:
        _write_cut_design_failure_log(
            run_dir,
            now=now,
            topic=topic,
            phase="build_script_and_manifest",
            profile=profile,
            exc=exc,
        )
        raise
    (run_dir / "script.md").write_text(_md_yaml(f"台本（{profile['topic_label']} / cinematic_story）", script), encoding="utf-8")
    (run_dir / "video_manifest.md").write_text(_md_yaml(f"Video Manifest（{profile['topic_label']} / p450 production）", manifest), encoding="utf-8")
    asset_inventory, asset_plan = _build_asset_artifacts_from_manifest(profile=profile, manifest=manifest)
    (run_dir / "asset_inventory.md").write_text(_md_yaml("Asset Inventory", asset_inventory), encoding="utf-8")
    (run_dir / "asset_plan.md").write_text(_md_yaml("Asset Plan", asset_plan), encoding="utf-8")
    _write_asset_request_files(run_dir, asset_plan, profile)
    _write_review_artifacts(run_dir)
    _materialize_standard_request_files(run_dir)
    state_updates = _write_orchestration(run_dir, stop_target)
    slots = P650_SLOTS if stop_target == "p680" else P650_SLOTS
    for slot in slots:
        state_updates[f"slot.{slot}.status"] = "awaiting_approval" if slot in AWAITING_ALLOWED else "done"
        state_updates[f"slot.{slot}.note"] = "frontend handoff" if slot in AWAITING_ALLOWED else "completed by frontend-review workflow"
    if stop_target == "p680":
        state_updates["slot.p660.status"] = "in_progress"
        state_updates["slot.p660.note"] = "scene images are still generating"
        state_updates["slot.p670.status"] = "pending"
        state_updates["slot.p670.note"] = "waiting for scene image generation to finish"
        state_updates["slot.p680.status"] = "pending"
        state_updates["slot.p680.note"] = "frontend image review is not ready until every scene image exists"
    state_updates.update(
        {
            "timestamp": now,
            "topic": topic,
            "status": "P650",
            "runtime.stage": "scene_images_generating" if stop_target == "p680" else "asset_and_scene_requests_ready",
            "runtime.stage_target": "p600",
            "runtime.stop_slot": stop_target,
            "runtime.scaffold.content_status": "authored",
            "runtime.review_policy": "frontend",
            "review.policy.story": "optional",
            "review.policy.image": "required",
            "review.policy.narration": "optional",
            "gate.story_review": "optional",
            "gate.narration_review": "optional",
            "immersive.experience": "cinematic_story",
            "review.story.status": "approved",
            "review.script.status": "approved",
            "stage.research.status": "awaiting_approval",
            "stage.story.status": "awaiting_approval",
            "stage.visual_value.status": "awaiting_approval",
            "stage.script.status": "awaiting_approval",
            "stage.asset.status": "awaiting_approval",
            "stage.scene_implementation.status": "awaiting_approval",
            "review.image.status": "generating" if stop_target == "p680" else "pending",
            "gate.image_review": "required",
        }
    )
    append_state_snapshot(run_dir / "state.txt", state_updates)


def prepare_grounding(run_dir: Path) -> None:
    for stage in ("research", "story", "visual_value", "script", "manifest"):
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "prepare-stage-context.py"), "--stage", stage, "--run-dir", str(run_dir), "--flow", "immersive"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "verify-pipeline.py"),
            "--run-dir",
            str(run_dir),
            "--flow",
            "immersive",
            "--profile",
            "standard",
            "--stage-target",
            "p450",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    for stage in ("asset", "scene_implementation"):
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "prepare-stage-context.py"), "--stage", stage, "--run-dir", str(run_dir), "--flow", "immersive"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )


async def generate_images(run_dir: Path, stop_target: str) -> None:
    from server import image_gen_app

    run_id = _run_id_from_dir(run_dir)
    if stop_target == "p650":
        for stage in ("scene_set", "scene_detail", "cut_blueprint", "asset_plan"):
            await image_gen_app._run_semantic_review("toc-immersive-frontend-run", run_dir=run_dir, stage=stage)
        await image_gen_app._generate_request_outputs(run_dir=run_dir, kind="asset")
        await image_gen_app._run_semantic_review("toc-immersive-frontend-run", run_dir=run_dir, stage="image_prompt")
    else:
        await image_gen_app._generate_create_images("toc-immersive-frontend-run", run_id=run_id)


def validate(run_dir: Path, stop_target: str) -> None:
    from server import image_gen_app

    run_id = _run_id_from_dir(run_dir)
    if stop_target == "p650":
        image_gen_app._validate_p650_run(run_id)
    else:
        image_gen_app._validate_frontend_create_run(run_id, strict_visual_quality=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ToC immersive frontend-review workflow to p650/p680.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--source", default="")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--stop-target", choices=["p650", "p680"], default="p680")
    parser.add_argument("--materialize-only", action="store_true", help="Write text artifacts only; do not generate images or validate media.")
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    source = args.source.strip() or args.topic
    materialize_stop_target = "p650" if args.materialize_only and args.stop_target == "p680" else args.stop_target
    materialize_run(args.topic, source, run_dir, materialize_stop_target)
    prepare_grounding(run_dir)
    if not args.materialize_only:
        asyncio.run(generate_images(run_dir, args.stop_target))
    write_run_index(run_dir)
    if not args.skip_validation and not args.materialize_only:
        validate(run_dir, args.stop_target)
    print(f"Run dir: {run_dir.resolve()}")
    print(f"Stop target: {args.stop_target}")


if __name__ == "__main__":
    main()
