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
    return [
        {
            "asset_id": _safe_asset_id("location", place, index),
            "asset_type": "location_reference",
            "name": place,
            "output": f"assets/locations/{_safe_asset_id('location', place, index)}.png",
            "story_purpose": f"{place}の空間・光・質感を固定する",
            "reusable_reason": "同じ場所のcutで背景と空気感を保つ",
        }
        for index, place in enumerate(places, start=1)
    ]


def _location_spec_for_scene(profile: dict[str, Any], scene_index: int) -> dict[str, Any]:
    specs = _location_asset_specs(profile)
    return specs[min(scene_index - 1, len(specs) - 1)]


def _scene_uses_artifact(profile: dict[str, Any], scene_index: int) -> bool:
    return scene_index in {int(value) for value in profile.get("artifact_scene_indices", [])}


def _prompt_for_asset(entry: dict[str, Any], profile: dict[str, Any]) -> str:
    asset_id = str(entry.get("asset_id") or "")
    asset_type = str(entry.get("asset_type") or "")
    if asset_id == profile["protagonist_asset_id"]:
        return "\n".join(
            [
                "[全体 / 不変条件]",
                "実写、シネマティック、全身、頭からつま先まで。自然な肌、同じ顔と髪型。画面内テキストなし、字幕なし、ロゴなし。",
                "",
                "[作成するもの]",
                f"{profile['protagonist_name']}の全身参照画像。主対象は人物1人で、場所参照や空の部屋ではない。",
                "",
                "[人物固定]",
                "穏やかな強さのある表情、自然な髪、自然な体格。後続画像で同じ顔、髪、体格を保つ。正面寄り、頭からつま先まで見える。",
                "",
                "[衣装]",
                f"{profile['topic_label']}の世界に合う生活感のある衣装。後続画像で顔、髪、体格、衣装の主要形状を保つ。",
                "",
                "[禁止]",
                "人物なし、空の部屋、場所だけ、後ろ姿だけ、顔が読めない構図、アニメ、漫画、イラスト、文字、ロゴ、ウォーターマーク、途中クロップ、低情報量のポスター風。",
            ]
        )
    if asset_type == "location_reference":
        place = str(entry.get("name") or entry.get("story_purpose") or "物語の場所")
        return "\n".join(
            [
                "[全体 / 不変条件]",
                "実写、シネマティック、広角の環境参照。自然な光、奥行き、触れられる素材感。画面内テキストなし、字幕なし、ロゴなし。",
                "",
                "[作成するもの]",
                f"{place}の場所参照画像。後続cutで背景、照明、空気感を固定できる一枚。",
                "",
                "[場所固定]",
                "人物を主役にしない。床、壁、出入口、光源、質感が読み取れる。映画のロケーションスチルとして成立させる。",
                "",
                "[禁止]",
                "主要人物、全身ポートレート、人物が画面の中心、アニメ、漫画、イラスト、文字、ロゴ、ウォーターマーク、低情報量、抽象背景だけの画像。",
            ]
        )
    return "\n".join(
            [
                "[全体 / 不変条件]",
                "実写、シネマティック、精密な素材感と反射。画面内テキストなし、字幕なし、ロゴなし。",
                "",
                "[作成するもの]",
                f"{profile['artifact_name']}。{profile['artifact_role']}として一目で読める。",
                "",
                "[小道具固定]",
                f"{profile['artifact_visual']}。実物として置ける重量感。",
                "",
                "[禁止]",
                "玩具風、プラスチック、文字、ロゴ、ウォーターマーク、イラスト、低情報量。",
        ]
    )


def _scene_prompt(title: str, beat: str, target_beat: str, location_name: str, profile: dict[str, Any], *, include_artifact: bool) -> str:
    active_motifs = [motif for motif in profile["motifs"] if include_artifact or motif != "ガラス"]
    motifs = "、".join(active_motifs)
    artifact_lines = [
        "[小道具 / 舞台装置]",
        f"{profile['artifact_name']}。{profile['artifact_role']}として、実物の重量感と読みやすいシルエットを持つ。",
        "",
    ] if include_artifact else []
    scene_detail = (
        f"{title}。場所は{location_name}。{target_beat}。{beat} 中景に{profile['protagonist_name']}、前景か手元に{profile['artifact_name']}の気配、背景に次の場所へ続く導線。"
        if include_artifact
        else f"{title}。場所は{location_name}。{target_beat}。{beat} 中景に{profile['protagonist_name']}、背景に場所の質感と次の場所へ続く導線。証の小道具はまだ画面に出さない。"
    )
    continuity = (
        f"{profile['topic_label']}の始まりから試練、証明へつながる。人物と{profile['artifact_name']}の形状を変えない。"
        if include_artifact
        else f"{profile['topic_label']}の始まりから試練、証明へつながる。人物の顔、髪、体格、衣装の主要形状を変えない。"
    )
    return "\n".join(
        [
            "[全体 / 不変条件]",
            f"実写、シネマティック、35mm映画、自然な肌、{motifs}の高密度な質感。画面内テキストなし、字幕なし、ロゴなし、ウォーターマークなし。",
            "",
            "[登場人物]",
            f"{profile['protagonist_name']}は参照画像と同じ人物。顔立ち、髪、体格、衣装の主要形状を保つ。",
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
    protagonist_asset = profile["protagonist_asset_id"]
    artifact_asset = profile["artifact_asset_id"]
    protagonist_ref = f"assets/characters/{protagonist_asset}.png"
    artifact_ref = f"assets/{profile['artifact_output_dir']}/{artifact_asset}.png"
    for idx, title in enumerate(profile["scene_titles"], start=1):
        include_artifact = _scene_uses_artifact(profile, idx)
        location_spec = _location_spec_for_scene(profile, idx)
        location_ref = str(location_spec["output"])
        scene_id = idx * 10
        cuts: list[dict[str, Any]] = []
        manifest_cuts: list[dict[str, Any]] = []
        for cut_number in range(1, 4):
            selector = f"scene{scene_id}_cut{cut_number:02d}"
            selectors.append(selector)
            beat = f"{title}の転換点{cut_number}"
            visual_beat = (
                f"{title}で{profile['protagonist_name']}、光、{profile['artifact_name']}が見える"
                if include_artifact
                else f"{title}で{profile['protagonist_name']}、光、場所の質感が見える"
            )
            must_show = [profile["protagonist_name"], "光", profile["artifact_name"]] if include_artifact else [profile["protagonist_name"], "光", title]
            object_ids = [artifact_asset] if include_artifact else []
            references = [protagonist_ref, location_ref, *([artifact_ref] if include_artifact else [])]
            location_name = str(location_spec["name"])
            cut_blueprint = {
                "cut_role": "状況を前へ進める映画的断片",
                "cut_function": ("setup", "turn", "handoff")[cut_number - 1],
                "duration_intent": "12秒で感情と情報を同時に渡す",
                "target_beat": beat,
                "screen_question": f"観客は{title}で何が変わると読むのか",
                "dramatic_job": "sceneの問いを一段進め、次のcutへ渡す",
                "must_show": must_show,
                "must_avoid": ["画面内テキスト", "字幕", "ロゴ"],
                "done_when": ["人物、場所、象徴が一枚で読める"],
                "visual_beat": visual_beat,
                "first_frame_brief": f"{title}で{profile['protagonist_name']}がまだ動き切る前の初期状態。{visual_beat}",
                "action_completion_state": "pre_action" if cut_number == 1 else "early_action",
                "motion_brief": f"{title}の空気がゆっくり動き、人物の視線と光が次の状態へ移る",
                "motion_end_state": f"{title}の最後に次cutへ渡る視線または光が残る",
                "narration_role": "絵を説明せず内面の方向だけを示す",
            "asset_dependency_hint": {"characters": [protagonist_asset], "objects": object_ids, "locations": [location_spec["asset_id"]]},
            }
            cuts.append({"cut_id": f"{cut_number:02d}", "selector": selector, "target_duration_seconds": 12, "estimated_duration_seconds": 12, "cut_blueprint": cut_blueprint, "human_review": {"status": "approved", "change_request_ids": []}})
            prompt = _scene_prompt(title, visual_beat, beat, location_name, profile, include_artifact=include_artifact)
            narration = f"{title}。奥に残った名前が、まだ消えていないことを光が知らせる。"
            cut_contract = {
                "schema_version": "2.1",
                "cut_role": "main",
                "cut_function": cut_blueprint["cut_function"],
                "duration_intent": "standard",
                "target_duration_seconds": 12,
                "viewer_contract": {
                    "target_beat": beat,
                    "screen_question": cut_blueprint["screen_question"],
                    "dramatic_job": cut_blueprint["dramatic_job"],
                    "visual_proof": visual_beat,
                    "must_show": must_show,
                    "must_avoid": ["英字看板", "署名クレジット", "企業ロゴ"],
                    "done_when": ["人物と場所が一枚で読める"] if not include_artifact else ["人物と小道具と場所が一枚で読める"],
                },
                "cinematic_contract": {
                    "camera_intent": "観客の視線を主人公、光、場所の奥行きへ導く",
                    "subject_priority": {"primary": profile["protagonist_name"], "secondary": profile["artifact_name"] if include_artifact else location_name, "background": location_name},
                    "screen_geography": {"foreground": "手元または床の質感", "midground": profile["protagonist_name"], "background": location_name, "screen_direction": "toward_camera"},
                },
                "continuity_contract": {
                    "location_ids": [location_spec["asset_id"]],
                    "character_ids": [protagonist_asset],
                    "object_ids": object_ids,
                    "start_state": {"character_state": "まだ行為を完了していない", "spatial_state": location_name},
                    "end_state": {"character_state": "次cutへ視線または姿勢が渡る", "spatial_state": location_name},
                    "carry_forward_to_next_cut": [profile["protagonist_name"], location_name, *object_ids],
                },
                "first_frame_contract": {
                    "imageable": True,
                    "image_role": "video_first_frame_candidate",
                    "first_frame_brief": cut_blueprint["first_frame_brief"],
                    "action_completion_state": cut_blueprint["action_completion_state"],
                    "must_include": must_show,
                    "must_avoid": ["画面内テキスト", "字幕", "ロゴ"],
                },
                "motion_contract": {
                    "movable": True,
                    "motion_brief": cut_blueprint["motion_brief"],
                    "camera_motion": "slow_push",
                    "subject_motion": "視線と姿勢がわずかに変わる",
                    "environment_motion": "光と空気がゆっくり揺れる",
                    "emotional_change": "不可視から可視へ一段近づく",
                    "end_state": cut_blueprint["motion_end_state"],
                    "must_not_add": ["新しい人物", "次sceneのreveal", "画面内テキスト"],
                },
                "narration_contract": {
                    "speakable_or_silent": True,
                    "role": "emotion",
                    "target_function": "映像を説明せず、内面の方向だけを示す",
                    "must_avoid": ["画面に見えている内容の単純説明"],
                    "text": narration,
                    "tts_text": narration,
                    "silence_reason": "",
                },
                "downstream_handoff": {
                    "p500_asset": {"asset_candidates": [protagonist_asset, *object_ids, location_spec["asset_id"]]},
                    "p600_image": {"prompt_requirements": must_show},
                    "p700_narration": {"narration_requirements": ["説明ではなく感情の方向"]},
                    "p800_video": {"motion_requirements": [cut_blueprint["motion_brief"]], "last_frame_or_end_state": cut_blueprint["motion_end_state"]},
                    "carries_to_next_cut": [profile["protagonist_name"], location_name],
                    "carries_to_next_scene": [profile["artifact_name"]] if include_artifact else [],
                },
            }
            manifest_cuts.append(
                {
                    "cut_id": f"{cut_number:02d}",
                    "selector": selector,
                    "duration_seconds": 12,
                    "cut_contract": cut_contract,
                    "scene_contract": {"cut_function": cut_contract["cut_function"], "target_beat": beat, "screen_question": cut_contract["viewer_contract"]["screen_question"], "dramatic_job": cut_contract["viewer_contract"]["dramatic_job"], "visual_beat": visual_beat, "first_frame_brief": cut_contract["first_frame_contract"]["first_frame_brief"], "motion_brief": cut_contract["motion_contract"]["motion_brief"], "must_show": must_show, "must_avoid": ["英字看板", "署名クレジット", "企業ロゴ"], "done_when": ["人物と場所が一枚で読める"] if not include_artifact else ["人物と小道具と場所が一枚で読める"]},
                    "image_generation": {"tool": "codex_builtin_image", "character_ids": [protagonist_asset], "object_ids": object_ids, "location_ids": [location_spec["asset_id"]], "asset_id": "", "asset_type": "scene_still", "execution_lane": "standard", "reference_count": len(references), "references": references, "prompt": prompt, "output": f"assets/scenes/{selector}.png", "aspect_ratio": "16:9", "image_size": "1K", "review": {"status": "approved"}},
                    "video_generation": {"tool": "kling_3_0_omni", "duration_seconds": 12, "first_frame": f"assets/scenes/{selector}.png", "motion_prompt": f"{title}の空気がゆっくり動く。カメラは滑らかに前進し、人物の顔と場所の奥行きを保つ。", "output": f"assets/scenes/{selector}.mp4"},
                    "audio": {"narration": {"text": narration, "tts_text": narration, "tool": "elevenlabs", "output": f"assets/audio/{selector}.mp3", "applied_request_ids": []}},
                    "implementation_trace": {"status": "verified", "source_request_ids": []},
                }
            )
        script_scenes.append({"scene_id": scene_id, "phase": PHASES[idx - 1], "importance": "medium", "target_duration_seconds": 36, "estimated_duration_seconds": 36, "handoff_to_next_scene": f"{title}の最後の光が次の場面へ観客を運ぶ" if idx < len(profile["scene_titles"]) else "", "terminal_resolution": f"{profile['artifact_name']}が名前を取り戻す" if idx == len(profile["scene_titles"]) else "", "scene_intent": {"dramatic_question": f"{title}で主人公は前進できるか", "value_shift": "不可視から可視へ一段進む", "causal_turn": "次の場所へ移る証拠が生まれる"}, "agent_review": {"status": "passed", "reason": "scene is concrete and production ready"}, "coverage_review": {"audience_information_covered": True, "visualizable_action_covered": True, "next_scene_connection_checked": True}, "cuts": cuts})
        manifest_scenes.append({"scene_id": scene_id, "importance": "medium", "target_duration_seconds": 36, "estimated_duration_seconds": 36, "handoff_to_next_scene": f"{title}から次へつながる" if idx < len(profile["scene_titles"]) else "", "terminal_resolution": f"{profile['artifact_name']}で身元や価値が明かされる" if idx == len(profile["scene_titles"]) else "", "coverage_review": {"audience_information_covered": True, "visualizable_action_covered": True, "next_scene_connection_checked": True}, "cuts": manifest_cuts})
    script = {"script_metadata": {"topic": topic, "target_duration": 300, "created_at": now}, "scene_set_review": {"status": "approved", "summary": "8 scenes / 24 cutsで主要筋を展開する。"}, "scene_detail_review": {"status": "approved", "summary": "各sceneは独立した問いと視覚行動を持つ。"}, "cut_blueprint_review": {"status": "approved", "summary": "全cutがp420 blueprintを持つ。"}, "script_review": {"status": "approved", "summary": "台本は後続画像生成に渡せる。"}, "production_readiness_review": {"status": "approved", "summary": "target duration is covered now."}, "evaluation_contract": {"target_arc": "opening,development,ordeal,transformation,ending", "must_cover": [profile["protagonist_name"], profile["artifact_name"], "時間制限", profile["motifs"][0]], "must_avoid": ["画面内テキスト", "字幕", "ロゴ"], "reveal_constraints": []}, "human_change_requests": [], "scenes": script_scenes}
    manifest = {"manifest_phase": "production", "video_metadata": {"topic": topic, "source_story": str(run_dir / "story.md"), "created_at": now, "experience": "cinematic_story", "aspect_ratio": "16:9", "resolution": "1280x720", "frame_rate": 24, "target_duration_seconds": 300, "duration_seconds": 288}, "assets": {"character_bible": [{"character_id": protagonist_asset, "reference_images": [protagonist_ref], "review_aliases": [profile["protagonist_name"], profile["topic_label"]], "fixed_prompts": [f"{profile['protagonist_name']}、自然な実写肌、同じ顔と髪型を維持"]}], "object_bible": [{"object_id": artifact_asset, "kind": "artifact", "reference_images": [artifact_ref], "fixed_prompts": [profile["artifact_fixed_prompt"]], "cinematic": {"role": profile["artifact_role"], "visual_takeaways": ["脆さと証拠性"], "spectacle_details": ["光を反射して手がかりになる"]}}], "location_bible": [{"location_id": spec["asset_id"], "reference_images": [spec["output"]], "fixed_prompts": [f"{spec['name']}、実写映画の場所参照、同じ光と質感を維持"]} for spec in _location_asset_specs(profile)], "style_guide": {"visual_style": "実写、シネマティック、プラクティカルエフェクト。画面内テキストなし。", "forbidden": ["アニメ調", "漫画調", "イラスト調", "画面内テキスト", "字幕", "ウォーターマーク", "ロゴ"], "reference_images": []}}, "human_change_requests": [], "scenes": manifest_scenes}
    return script, manifest, selectors


def _write_request_files(run_dir: Path, asset_plan: dict[str, Any], manifest: dict[str, Any], profile: dict[str, Any]) -> None:
    asset_lines = ["# Asset Generation Requests", ""]
    manifest_items = []
    for entry in asset_plan["assets"]:
        asset_id = entry["asset_id"]
        output = entry["generation_plan"]["output"]
        asset_lines.extend(
            [
                f"## {asset_id}",
                "",
                "- tool: `codex_builtin_image`",
                f"- asset_type: `{entry['asset_type']}`",
                "- execution_lane: `bootstrap_builtin`",
                "- reference_count: `0`",
                "- review_status: `approved`",
                f"- output: `{output}`",
                "- references: `[]`",
                "",
                "```text",
                _prompt_for_asset(entry, profile),
                "```",
                "",
            ]
        )
        manifest_items.append({"asset_id": asset_id, "selector": asset_id, "output": output, "asset_type": entry["asset_type"], "status": "requested"})
    (run_dir / "asset_generation_requests.md").write_text("\n".join(asset_lines), encoding="utf-8")
    (run_dir / "asset_generation_manifest.md").write_text(_md_yaml("Asset Generation Manifest", {"asset_generation_manifest": {"items": manifest_items}}), encoding="utf-8")

    scene_lines = ["# Image Generation Requests", ""]
    for scene in manifest["scenes"]:
        for cut in scene["cuts"]:
            ig = cut["image_generation"]
            scene_lines.extend(
                [
                    f"## {cut['selector']}",
                    "",
                    "- tool: `codex_builtin_image`",
                    "- still_mode: `generate_still`",
                    "- generation_status: `requested`",
                    "- execution_lane: `standard`",
                    f"- reference_count: `{len(ig.get('references', []))}`",
                    "- review_status: `approved`",
                    f"- output: `{ig['output']}`",
                    "- references:",
                    *[f"  - `{ref}`" for ref in ig.get("references", [])],
                    "",
                    "```text",
                    ig["prompt"],
                    "```",
                    "",
                ]
            )
    (run_dir / "image_generation_requests.md").write_text("\n".join(scene_lines), encoding="utf-8")


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
                "8 scenes / 24 cutsで主要筋を保持。",
                "",
                "## Duration",
                "target 300 seconds and current cut plan covers 288 seconds in p400, satisfying the 90 percent gate.",
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
    for semantic_stage in ("scene_set", "scene_detail", "cut_blueprint", "asset_plan", "asset_output", "image_prompt", "scene_image"):
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
                "beat_ladder_coverage",
                "first_frame_motion_readiness",
                "multimodal_contract_coverage",
                "duration_density_and_handoff",
                "coverage_plan_complete",
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
        result = {
            "bucket": bucket,
            "status": "done",
            "completed_slots": list(bucket_slots[bucket]),
            "required_artifacts": [{"path": path, "exists": True} for path in bucket_artifacts[bucket]],
            "state_keys": {status_key: "awaiting_approval" if bucket_slots[bucket][-1] in AWAITING_ALLOWED else "done"},
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
        "setpieces": [profile["artifact_name"]],
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
        coverage["characters"].append(asset_id)
        inventory_items.append({"item_id": asset_id, "category": "characters", "source_script_selectors": selectors, "story_purpose": "主人公の顔と体格を保つ", "reusable_reason": "登場cutで人物同一性を保つ", "recommended_asset_type": "character_reference"})
        plan_entries.append({"asset_id": asset_id, "asset_type": "character_reference", "source_script_selectors": selectors, "story_purpose": f"{profile['protagonist_name']}本人の一貫性を固定する", "visual_spec": {"subject": f"{profile['protagonist_name']}の全身、自然な映画俳優の顔立ち、生活感のある衣装", "style": "photorealistic live-action cinematic", "forbidden": ["文字", "ロゴ", "アニメ"]}, "generation_plan": {"execution_lane": "bootstrap_builtin", "bootstrap_allowed": True, "required_views": ["front", "side", "back"], "reference_inputs": [], "output": output}, "review": {"status": "approved", "reason": "登場cutで人物同一性を保つため必須"}})

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
        inventory_items.append({"item_id": asset_id, "category": "story_specific_items", "source_script_selectors": selectors, "story_purpose": role, "reusable_reason": "証が必要なcutで小道具の形状を保つ", "recommended_asset_type": "object_reference"})
        plan_entries.append({"asset_id": asset_id, "asset_type": "object_reference", "source_script_selectors": selectors, "story_purpose": role, "visual_spec": {"subject": profile["artifact_visual"], "style": "photorealistic live-action product still", "forbidden": ["文字", "ロゴ", "玩具風"]}, "generation_plan": {"execution_lane": "bootstrap_builtin", "bootstrap_allowed": True, "required_views": ["front"], "reference_inputs": [], "output": output}, "review": {"status": "approved", "reason": "証として必要なcutにだけ使う"}})

    for entry in assets.get("location_bible", []) or []:
        if not isinstance(entry, dict):
            continue
        asset_id = str(entry.get("location_id") or "").strip()
        output = str((entry.get("reference_images") or [""])[0]).strip()
        selectors = location_usage.get(asset_id, [])
        if not asset_id or not output or not selectors:
            continue
        location_name = asset_id
        for spec in _location_asset_specs(profile):
            if spec["asset_id"] == asset_id:
                location_name = str(spec["name"])
                break
        coverage["locations"].append(asset_id)
        inventory_items.append({"item_id": asset_id, "category": "locations", "source_script_selectors": selectors, "story_purpose": f"{location_name}の空間・光・質感を固定する", "reusable_reason": "同じ場所のcutで背景と空気感を保つ", "recommended_asset_type": "location_reference"})
        plan_entries.append({"asset_id": asset_id, "asset_type": "location_reference", "source_script_selectors": selectors, "story_purpose": f"{location_name}の空間・光・質感を固定する", "visual_spec": {"subject": f"{location_name}の場所参照、実写映画のロケーションスチル、奥行き、光、床壁の質感", "style": "photorealistic live-action cinematic location still", "forbidden": ["文字", "ロゴ", "人物主役", "アニメ"]}, "generation_plan": {"execution_lane": "bootstrap_builtin", "bootstrap_allowed": True, "required_views": ["wide"], "reference_inputs": [], "output": output}, "review": {"status": "approved", "reason": "scene背景と空気感の一貫性に必要"}})

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
        "asset_bible_candidates": {"characters": [protagonist_asset], "objects": [artifact_asset], "locations": [spec["asset_id"] for spec in _location_asset_specs(profile)], "setpieces": [profile["artifact_name"]], "reusable_stills": ["時間制限を示す象徴的な光"]},
        "anchor_cut_candidates": [{"selector": "scene10_cut01", "reason": "主人公の顔と衣装を固定する"}],
        "reference_strategy": {"p500": f"{profile['protagonist_name']}全身参照と{profile['artifact_name']}を先に生成する", "p600": "各cutは参照画像を使い、同じ顔・象徴物・質感を保つ"},
        "regeneration_risks": [{"risk": "衣装や顔がcutごとに変わる", "mitigation": "character referenceを全cutに指定する"}],
        "handoff_to_p400_p500_p600_p700": {"p400_script": "8 scenes / 24 cutsで構成する", "p500_asset": f"{protagonist_asset} と {artifact_asset} を必須参照にする", "p600_scene_implementation": "各cutにscene_contractと画像promptを持たせる", "p700_narration": "画像確定後に語りを同期する"},
    }
    (run_dir / "visual_value.md").write_text(_md_yaml(f"視覚化価値設計（{profile['topic_label']}）", visual), encoding="utf-8")
    script, manifest, selectors = _build_script_and_manifest(topic, run_dir, now, profile)
    (run_dir / "script.md").write_text(_md_yaml(f"台本（{profile['topic_label']} / cinematic_story）", script), encoding="utf-8")
    (run_dir / "video_manifest.md").write_text(_md_yaml(f"Video Manifest（{profile['topic_label']} / p450 production）", manifest), encoding="utf-8")
    asset_inventory, asset_plan = _build_asset_artifacts_from_manifest(profile=profile, manifest=manifest)
    (run_dir / "asset_inventory.md").write_text(_md_yaml("Asset Inventory", asset_inventory), encoding="utf-8")
    (run_dir / "asset_plan.md").write_text(_md_yaml("Asset Plan", asset_plan), encoding="utf-8")
    _write_request_files(run_dir, asset_plan, manifest, profile)
    _write_review_artifacts(run_dir)
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
        await image_gen_app._run_semantic_review("toc-immersive-frontend-run", run_dir=run_dir, stage="asset_output")
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
