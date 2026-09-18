"""Legacy synthetic narratives for isolated compiler tests ONLY.

Production must never import this fixture or use it as research evidence.
New source-first integration tests use an injected researcher instead.
"""
import hashlib
from typing import Any
from toc.story_duration import build_duration_plan
DEFAULT_SCENE_TIMES_OF_DAY = ["朝", "昼", "夕方", "夜", "夜", "夜", "夜", "翌朝"]

RUN_VARIANTS = [
    {
        "label": "quiet_defiance",
        "focus": "静かな抵抗と手元の決意",
        "scene_titles": ["息を潜める日常", "願いが折られる場所", "小さな助力の兆し", "境界へ歩き出す夜", "視線が集まる入口", "名乗らない中心", "失われる前の選択", "証が戻る朝"],
        "motifs": ["煤けた手触り", "細い光", "沈黙", "鍵", "朝の埃"],
        "places": ["狭い生活空間", "閉ざされた入口", "助力が差す場所", "境界の道", "公的な入口", "人々の輪", "時間が迫る場所", "証明の部屋"],
        "artifact": "小さな鍵",
    },
    {
        "label": "public_recognition",
        "focus": "群衆の視線と公的な認識",
        "scene_titles": ["見過ごされる場所", "場のルールが迫る部屋", "助力が形を取る瞬間", "外へ出る境目", "公の光の下", "視線の中心", "時間が場を割る", "名前が戻る場所"],
        "motifs": ["視線", "布の陰影", "灯り", "扉", "反射"],
        "places": ["見過ごされる家", "拒まれる部屋", "準備の余白", "門の前", "公的な階段", "集会の広間", "期限の場所", "承認の空間"],
        "artifact": "光を返す留め具",
    },
    {
        "label": "memory_and_proof",
        "focus": "記憶が物証へ変わる過程",
        "scene_titles": ["記憶が残る場所", "願いが試される壁", "導きが触れる夜", "古い生活を離れる道", "知らない場所のしるし", "記憶が照らされる場", "証だけが残る瞬間", "物証が語る部屋"],
        "motifs": ["記憶", "擦れた素材", "月の白さ", "影", "手の跡"],
        "places": ["記憶のある部屋", "立ちはだかる壁際", "植栽のある庭", "古い道", "見知らぬ入口", "明るい集いの場", "静かな階段", "物証を確かめる部屋"],
        "artifact": "古い飾り紐",
    },
    {
        "label": "threshold_escape",
        "focus": "越境と逃走の身体感覚",
        "scene_titles": ["出口のない日常", "踏み出せない境界", "助力が出口を開く", "夜の道へ出る", "高い入口を越える", "中心で息を止める", "追いつく時間", "戻ってきた証"],
        "motifs": ["出口", "足音", "風", "暗い青", "手元の光"],
        "places": ["出口のない家", "狭い境界", "風が通る場所", "境界へ続く道", "高い入口", "中心の広間", "追われる通路", "証が置かれる部屋"],
        "artifact": "道を示す小片",
    },
]


def _stable_slug(text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"story_{digest}"


def _run_variant(topic: str, source: str, variant_seed: str) -> dict[str, Any]:
    key = f"{topic}\0{source}\0{variant_seed}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    variant = dict(RUN_VARIANTS[int(digest[:8], 16) % len(RUN_VARIANTS)])
    variant["seed"] = digest[:16]
    variant["index"] = int(digest[:8], 16) % len(RUN_VARIANTS)
    variant["source"] = "topic_source_run_dir"
    return variant


def _story_profile(topic: str, source: str, variant_seed: str = "") -> dict[str, Any]:
    """Build topic-aware names used by authored artifacts and image requests."""

    variant = _run_variant(topic, source, variant_seed)
    slug = _stable_slug(f"{topic}\n{source}\n{variant['label']}\n{variant['seed']}")
    topic_label = topic.strip() or "物語"
    artifact_name = f"{topic_label}の{variant['artifact']}"
    return {
        "slug": slug,
        "topic_label": topic_label,
        "story_time": "",
        "run_variant": {
            "seed": variant["seed"],
            "index": variant["index"],
            "label": variant["label"],
            "focus": variant["focus"],
            "source": variant["source"],
        },
        "protagonist_name": f"{topic_label}の主人公",
        "protagonist_asset_id": f"{slug}_protagonist_fullbody",
        "artifact_name": artifact_name,
        "artifact_asset_id": f"{slug}_signature_artifact",
        "artifact_output_dir": "objects",
        "artifact_role": f"{variant['focus']}を可視化する主役級アイテム",
        "artifact_visual": f"{artifact_name}。{variant['focus']}を感じさせる手に持てる象徴物、実物の質感、強い形状記憶",
        "artifact_fixed_prompt": f"{artifact_name}、{variant['focus']}、実物の質量、触れられる素材、読める文字なし",
        "places": variant["places"][:4],
        "scene_locations": variant["places"],
        "motifs": variant["motifs"],
        "scene_titles": variant["scene_titles"],
        "scene_times_of_day": list(DEFAULT_SCENE_TIMES_OF_DAY),
        "artifact_scene_indices": [4, 6, 8],
        "summary": f"{source or topic_label}を、{variant['focus']}を中心に、主人公が不均衡な日常から呼び出され、助力と試練を経て、最後に自分の価値を証明する実写シネマティックな物語として再構成する。",
        "aliases": [topic_label],
        "events": [
            f"{topic_label}の主人公が、いつもの場所で欠落や抑圧を抱え、{variant['focus']}が画面上の軸になる。",
            "外部からの知らせや事件が入り、主人公の願いと越えるべき境界がはっきりする。",
            "周囲の力が主人公の前進を拒み、選択の代償が見える。",
            "物語を動かす助力の道具が現れ、越境の条件が整う。",
            "主人公は境界を越え、未知の場所で自分の力を試される。",
            f"{artifact_name}が、主人公の内面と外部世界を結び始める。",
            "時間、追跡、喪失、誤解の圧力で、主人公は一度すべてを失いかける。",
            "残された証が手がかりとなり、真実を探す流れが生まれる。",
            "主人公は隠された状態から表へ出され、自分の名や価値を問われる。",
            "証が主人公と結びつき、主人公は自分の場所へ帰還する。",
        ],
    }


def _build_research(topic: str, source: str, now: str, profile: dict[str, Any]) -> dict[str, Any]:
    duration_plan = dict(profile.get("duration_plan") or build_duration_plan().to_dict())
    events = [str(event) for event in profile.get("events", []) if str(event).strip()]
    if not events:
        topic_label = str(profile.get("topic_label") or topic or "物語")
        events = [
            f"{topic_label}の主人公が、いつもの場所で不均衡を抱える。",
            "外部からの知らせや事件が入り、願いと境界が見える。",
            "周囲の力が主人公の前進を拒み、選択の代償が見える。",
            "助力者、道具、記憶、偶然のいずれかが現れ、越境の条件が整う。",
            "主人公は境界を越え、未知の場所で自分の力を試される。",
            "主人公の行為が、内面と外部世界を結ぶ証拠になる。",
            "時間、追跡、喪失、誤解の圧力で、主人公は一度すべてを失いかける。",
            "残された証が手がかりとなり、真実を探す流れが生まれる。",
            "主人公は隠された状態から表へ出され、自分の名や価値を問われる。",
            "証が主人公と結びつき、物語は解放または帰還へ向かう。",
        ]
    motif_sequence = "、".join(str(motif) for motif in profile["motifs"][:4])
    deadline_trigger = "時間制限の合図"
    helper_claim = "助力者、記憶、偶然、環境の変化のいずれかとして描く"
    helper_theory = "ユーザー指定のsourceから、助力の形を映像化に合わせて選ぶ。"
    characters = [
        {"character_id": "protagonist", "name": profile["protagonist_name"], "role": "主人公", "motivations": ["尊厳と願いを失わずに進む"], "relationships": [{"target": "opposition", "relation": "前進を妨げられる"}]},
        {"character_id": "opposition", "name": "主人公を妨げる力", "role": "抑圧者または障害", "motivations": ["現状維持"], "relationships": [{"target": "protagonist", "relation": "選択を狭める"}]},
        {"character_id": "witness", "name": "真実を見届ける者", "role": "証人", "motivations": ["主人公の本質を探す"], "relationships": [{"target": "protagonist", "relation": "証を通じて探す"}]},
    ]
    symbols_and_themes = [
        {"item_id": "SYM1", "item": profile["motifs"][0], "meaning": "抑圧と不可視化", "evidence_refs": ["P1"]},
        {"item_id": "SYM2", "kind": "object", "item": profile["artifact_name"], "meaning": "脆さと証明が同居する身元の鍵", "evidence_refs": ["P2"]},
    ]
    conflicts = [{"conflict_id": "C1", "topic": "助力者の表現", "accounts": [{"account_id": "A", "claim": helper_claim, "sources": ["S1"], "confidence": 0.8}], "impact_on_story": "映像では光、風、物の配置、人物の反応で示せる。", "selection_notes": {"recommended_choice": "A", "rationale": "映像上の因果を作りやすい。"}, "hybrid_proposal": {"proposed": False, "mix_elements": [], "risks": [], "mitigations": []}}]
    open_questions = [{"question_id": "Q1", "question": "助力を人物として出すか、現象・記憶・道具として出すか。", "known_theories": [helper_theory], "investigation_status": "verified", "sources": ["S1"]}]
    handoff_to_story: dict[str, Any] = {
        "recommended_focus": [f"{profile['motifs'][0]}から光へ", f"証としての{profile['artifact_name']}"],
        "must_preserve": ["抑圧", "越境", "時間制限", "証明"],
        "avoid_overstating": ["史実性"],
        "selection_questions_for_p200": ["主人公の能動性をどの場面で強めるか"],
    }
    event_character_ids: dict[int, list[str]] = {}
    return {
        "topic": topic,
        "aliases": profile["aliases"],
        "story_materials": {
            "canonical_story_dump": f"{source}。{profile['summary']}",
            "chronological_events": [
                {
                    "event_id": f"E{i:02d}",
                    "event": event,
                    **({"involved_characters": event_character_ids[i]} if i in event_character_ids else {}),
                    "sources": ["S1", "S2"],
                    "confidence": 0.88,
                }
                for i, event in enumerate(events, start=1)
            ],
            "characters": characters,
            "setting": {
                "places": profile["places"],
                "time_or_era": str(profile.get("story_time") or "").strip(),
                "world_rules": [f"{profile['artifact_name']}は証として残る", "助力は主人公の選択を代行しない"],
            },
            "symbols_and_themes": symbols_and_themes,
            "emotional_material": [{"emotion": "切迫", "trigger": deadline_trigger, "story_value": "逃走と証明を一気に動かす"}],
            "adaptation_options": [{"option_id": "A1", "proposal": f"実写映画のように{motif_sequence}の質感で感情を語る", "source_basis": ["S1"], "risks": ["説明台詞に寄せすぎない"]}],
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
        "conflicts": conflicts,
        "facts": {"items": [{"fact_id": "F1", "claim": f"{profile['artifact_name']}が主人公の価値や身元を証明する。", "kind": "plot", "confidence": 0.86, "verification": "partially_verified", "sources": ["S1"], "notes": "物語筋として扱う。"}]},
        "engagement": {"hooks": [{"hook_id": "H1", "type": "emotional", "content": f"{profile['protagonist_name']}が、隠された状態から光の中で自分の名を取り戻す。", "curiosity_score": 0.92, "supporting_facts": ["F1"]}]},
        "open_questions": open_questions,
        "handoff_to_story": handoff_to_story,
        "metadata": {
            "collected_at": now,
            "sources_used": ["S1", "S2", "S3"],
            "confidence_score": 0.86,
            "target_duration_seconds": int(duration_plan["target_seconds"]),
            "duration_plan": duration_plan,
        },
        "evaluation_contract": {"target_questions": ["主要筋を映像化できるか"], "must_cover": ["canonical_story_dump", "chronological_events", "source_passages", "conflicts"], "must_resolve_conflicts": ["C1"], "done_when": ["p200 が追加調査なしで scene/beat 候補を作れる"]},
    }

