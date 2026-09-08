#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Materialize a frontend ToC immersive run through p650/p680.

This is the Codex-native helper for app-server create flows.  It intentionally
does not call Claude slash commands.  It writes real p100-p650 run artifacts and,
unless requested otherwise, uses the existing Codex app-server image lane for
p560/p660 media generation.
"""

from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import (
    append_state_snapshot as _append_state_snapshot,
    load_structured_document,
    parse_state_file as _parse_canonical_state,
)
from toc.adaptation_value_contract import (
    ADAPTATION_VALUE_MARKER,
    source_value_ids as adaptation_source_value_ids,
    visual_value_adaptation_issues,
)
from toc.asset_prompt_compiler import compile_asset_prompt
from toc.cut_context_packet import materialize_cut_context_packet
from toc.image_prompt_compiler import compile_image_api_prompt_v2
from toc.cut_design_logging import (
    SCENE_GENERATION_PROMPTS_FILENAME,
    profile_failure_summary,
    read_scene_design_json as _raw_read_scene_design_json,
    scene_design_log_relpath,
    write_cut_design_context as _raw_write_cut_design_context,
    write_cut_design_failure_log as _raw_write_cut_design_failure_log,
    write_scene_design_json as _raw_write_scene_design_json,
)
from toc.scene_acceptance_contract import (
    CRITERION_REGISTRY_VERSION,
    SCENE_ACCEPTANCE_CONTRACT_VERSION,
    SCENE_DRAFT_VERSION,
    build_scene_slice,
    canonical_json_bytes,
    criterion_registry_digest,
    criterion_registry_payload,
    digest_contract as digest_scene_acceptance_contract,
    digest_scene_draft,
    digest_scene_slice,
    domain_separated_digest,
    validate_scene_draft,
    validate_scene_set_authoring_contract,
    validate_scene_set_preflight,
)
from toc.run_index import write_run_index as _write_run_index
from toc.run_root_binding import (
    bind_run_root,
    current_run_root_binding,
    read_run_file_bytes_serialized,
)
from toc.stage_evaluator import check_manifest_single
from toc.story_duration import build_duration_plan, normalize_target_duration
from toc.story_authoring import build_research_registry, validate_story_document
from scripts.world_walk_source import (
    PathIdentity,
    copy_regular_file_atomic_nofollow,
    directory_identity_nofollow,
    ensure_directory_relative_nofollow,
    open_directory_nofollow,
    read_regular_file_nofollow,
    sha256_regular_file_nofollow,
    unlink_regular_file_verified_nofollow,
    validate_world_walk_source_contract_path,
    validate_world_walk_source_path,
    write_regular_file_exclusive_nofollow,
    write_regular_file_nofollow,
)


P650_SLOTS = (
    "p110",
    "p120",
    "p210",
    "p220",
    "p310",
    "p330",
    "p410",
    "p420",
    "p440",
    "p450",
    "p510",
    "p520",
    "p530",
    "p550",
    "p560",
    "p570",
    "p610",
    "p620",
    "p650",
)
P680_SLOTS = (*P650_SLOTS, "p660", "p670", "p680")
AWAITING_ALLOWED = {"p330", "p570", "p680"}
CREATE_INPUT_SCHEMA_VERSION = "toc.create_input.v1"
CREATE_INPUT_REL_PATH = Path("logs/orchestration/create_input.json")
MIN_MATERIALIZATION_FREE_BYTES = 512 * 1024 * 1024
_ACTIVE_MATERIALIZATION_ROOT: ContextVar[
    tuple[str, PathIdentity, int, bool] | None
] = ContextVar(
    "toc_frontend_active_materialization_root",
    default=None,
)


def _exact_materialization_source(
    *,
    source: str,
    experience: str,
    source_run: Path | None,
    source_root_identity: PathIdentity | None = None,
    expected_source_sha256: str | None = None,
) -> str:
    """Return the exact bytes used to reconstruct the story profile."""

    if experience != "world_walk":
        return source
    if source_run is None:
        raise ValueError("world_walk materialization requires source_run")
    expected_identity = (
        source_root_identity
        if source_root_identity is not None
        else directory_identity_nofollow(source_run)
    )
    source_bytes = read_regular_file_nofollow(
        source_run,
        "story.md",
        expected_root_identity=expected_identity,
    )
    if (
        expected_source_sha256 is not None
        and hashlib.sha256(source_bytes).hexdigest()
        != expected_source_sha256
    ):
        raise ValueError("world-walk source story sha256 changed")
    return source_bytes.decode("utf-8")


def _write_create_input_contract(
    *,
    run_dir: Path,
    topic: str,
    source: str,
    experience: str,
    source_run: Path | None,
    target_duration_seconds: int,
    review_mode: str | None = None,
    expected_run_identity: PathIdentity | None = None,
) -> Path:
    """Persist the exact, non-derived input needed for deterministic resume."""

    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("create input topic must be nonempty")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("create input source must be nonempty")
    if experience not in {"cinematic_story", "world_walk"}:
        raise ValueError(f"unsupported create input experience: {experience}")
    if experience == "world_walk" and source_run is None:
        raise ValueError("world_walk create input requires source_run")
    if experience != "world_walk" and source_run is not None:
        raise ValueError(
            "source_run is only valid for world_walk create input"
        )
    normalized_duration = normalize_target_duration(target_duration_seconds)
    # ``review_mode`` remains an accepted input for old server clients.  The
    # production create lane has one behavior now, so the compatibility value
    # must not become state or a reason to materialize synthetic reports.
    del review_mode
    source_run_rel = (
        source_run.relative_to(REPO_ROOT).as_posix()
        if source_run is not None
        else None
    )
    path = run_dir / CREATE_INPUT_REL_PATH
    if not run_dir.exists():
        if expected_run_identity is not None:
            raise ValueError(
                f"create input run directory disappeared: {run_dir}"
            )
        run_dir.mkdir(parents=True, exist_ok=False)
    payload = (
        json.dumps(
            {
                "schema_version": CREATE_INPUT_SCHEMA_VERSION,
                "topic": topic,
                "source": source,
                "source_sha256": hashlib.sha256(
                    source.encode("utf-8")
                ).hexdigest(),
                "experience": experience,
                "source_run": source_run_rel,
                "target_duration_seconds": normalized_duration,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    root_identity = (
        expected_run_identity
        if expected_run_identity is not None
        else directory_identity_nofollow(run_dir)
    )
    write_regular_file_exclusive_nofollow(
        destination_root=run_dir,
        destination_relative=CREATE_INPUT_REL_PATH,
        data=payload,
        expected_destination_root_identity=root_identity,
    )
    return path


def _fresh_materialized_media_slot_updates(stop_target: str) -> dict[str, str]:
    """Describe only p500/p600 work that materialize_run has actually done."""

    if stop_target not in {"p650", "p680"}:
        raise ValueError(f"unsupported stop target: {stop_target}")
    updates = {
        "slot.p510.status": "pending",
        "slot.p510.note": "asset grounding has not completed",
        "slot.p520.status": "done",
        "slot.p520.note": "asset inventory materialized from the production manifest",
        "slot.p530.status": "done",
        "slot.p530.note": "asset plan materialized from the production manifest",
        "slot.p550.status": "pending",
        "slot.p550.note": "candidate asset requests exist but provider submission has not completed",
        "slot.p560.status": "pending",
        "slot.p560.note": "asset generation has not completed",
        "slot.p570.status": "pending",
        "slot.p570.note": "asset output validation has not completed",
        "slot.p610.status": "pending",
        "slot.p610.note": "scene implementation grounding has not completed",
        "slot.p620.status": "done",
        "slot.p620.note": "production manifest materialized into candidate scene requests",
        "slot.p650.status": "pending",
        "slot.p650.note": "concrete scene requests are materialized; provider freeze is pending",
    }
    if stop_target == "p680":
        updates.update(
            {
                "slot.p660.status": "pending",
                "slot.p660.note": "waiting for provider-ready scene request freeze",
                "slot.p670.status": "pending",
                "slot.p670.note": "waiting for scene image generation to finish",
                "slot.p680.status": "pending",
                "slot.p680.note": "scene image handoff is not ready until every scene image exists",
            }
        )
    return updates


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
DEFAULT_SCENE_TIMES_OF_DAY = ["朝", "昼", "夕方", "夜", "夜", "夜", "夜", "翌朝"]
SCENE_TIME_OF_DAY_CONTRACT = "required_v1"
SCENE_TIME_OF_DAY_VISUAL_BASIS_CONTRACT = "required_v1"
PHASES = ["opening", "development", "development", "ordeal", "ordeal", "transformation", "transformation", "ending"]
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


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _run_variant(topic: str, source: str, variant_seed: str) -> dict[str, Any]:
    key = f"{topic}\0{source}\0{variant_seed}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    variant = dict(RUN_VARIANTS[int(digest[:8], 16) % len(RUN_VARIANTS)])
    variant["seed"] = digest[:16]
    variant["index"] = int(digest[:8], 16) % len(RUN_VARIANTS)
    variant["source"] = "topic_source_run_dir"
    return variant






def _safe_asset_id(prefix: str, text: str, index: int) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    if not normalized:
        normalized = f"{prefix}_{index:02d}"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]
    return f"{prefix}_{index:02d}_{normalized[:24]}_{digest}"


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


def _duration_aware_profile(profile: dict[str, Any], *, target_duration_seconds: int) -> dict[str, Any]:
    """Expand canonical story beats into ordered runtime scenes for the target length."""

    plan = build_duration_plan(target_duration_seconds)
    authored_scene_ids = [
        str(value).strip()
        for value in profile.get("scene_ids") or []
        if str(value).strip()
    ]
    authored_titles = [
        str(value).strip()
        for value in profile.get("scene_titles") or []
        if str(value).strip()
    ]
    if authored_scene_ids and len(authored_scene_ids) == len(authored_titles):
        # A story_scene_contract_v1 scene is a semantic boundary authored from
        # research. Target duration may change timing density, but must never
        # clone or split those scenes into generic runtime padding.
        scene_base, scene_remainder = divmod(
            plan.target_seconds, len(authored_scene_ids)
        )
        expanded = dict(profile)
        expanded.update(
            {
                "scene_target_durations": [
                    scene_base + (1 if index < scene_remainder else 0)
                    for index in range(len(authored_scene_ids))
                ],
                "canonical_scene_indices": list(
                    range(1, len(authored_scene_ids) + 1)
                ),
                "canonical_scene_count": len(authored_scene_ids),
                "scene_segment_positions": [1] * len(authored_scene_ids),
                "scene_segment_counts": [1] * len(authored_scene_ids),
                "scene_segment_roles": ["semantic_scene"]
                * len(authored_scene_ids),
                "duration_plan": plan.to_dict(),
            }
        )
        return expanded
    canonical_titles = [str(value) for value in profile.get("scene_titles") or DEFAULT_SCENE_TITLES]
    canonical_locations = [str(value) for value in profile.get("scene_locations") or profile.get("places") or canonical_titles]
    raw_location_sequences = profile.get("scene_location_sequences")
    raw_location_segments = profile.get("scene_location_segments")
    canonical_location_sequences: list[list[str]] = []
    canonical_location_segments: list[list[dict[str, Any]]] = []
    for index, location in enumerate(canonical_locations):
        raw_sequence = (
            raw_location_sequences[min(index, len(raw_location_sequences) - 1)]
            if isinstance(raw_location_sequences, list) and raw_location_sequences
            else None
        )
        if isinstance(raw_sequence, list):
            sequence = [str(value).strip() for value in raw_sequence if str(value).strip()]
        elif isinstance(raw_sequence, str) and raw_sequence.strip():
            sequence = [raw_sequence.strip()]
        else:
            sequence = []
        canonical_sequence = sequence or [location]
        canonical_location_sequences.append(canonical_sequence)
        raw_segments = (
            raw_location_segments[min(index, len(raw_location_segments) - 1)]
            if isinstance(raw_location_segments, list) and raw_location_segments
            else []
        )
        normalized_segments = [
            segment
            for value in (raw_segments if isinstance(raw_segments, list) else [])
            if (segment := _normalize_location_segment(value))
            and segment["location"] in canonical_sequence
        ]
        canonical_location_segments.append(normalized_segments)
    canonical_times_of_day = [
        str(value).strip()
        for value in profile.get("scene_times_of_day") or DEFAULT_SCENE_TIMES_OF_DAY
    ]
    if not canonical_titles:
        raise ValueError("story profile must define at least one canonical scene")

    runtime_count = max(len(canonical_titles), plan.minimum_scene_count)
    canonical_count = len(canonical_titles)
    canonical_scene_indices = [
        min(canonical_count, ((runtime_index - 1) * canonical_count) // runtime_count + 1)
        for runtime_index in range(1, runtime_count + 1)
    ]
    group_counts = {
        canonical_index: canonical_scene_indices.count(canonical_index)
        for canonical_index in range(1, canonical_count + 1)
    }
    group_positions: dict[int, int] = {}
    runtime_titles: list[str] = []
    runtime_locations: list[str] = []
    runtime_location_sequences: list[list[str]] = []
    runtime_location_segments: list[list[dict[str, Any]]] = []
    runtime_times_of_day: list[str] = []
    runtime_segment_positions: list[int] = []
    runtime_segment_counts: list[int] = []
    runtime_segment_roles: list[str] = []
    for canonical_index in canonical_scene_indices:
        group_positions[canonical_index] = group_positions.get(canonical_index, 0) + 1
        position = group_positions[canonical_index]
        count = group_counts[canonical_index]
        base_title = canonical_titles[canonical_index - 1]
        if count == 1:
            runtime_titles.append(base_title)
        else:
            if position == 1:
                segment_role = "導入"
            elif position == count:
                segment_role = "余韻"
            elif position * 2 <= count:
                segment_role = "圧力"
            else:
                segment_role = "転換"
            runtime_titles.append(f"{base_title}（{position}/{count}・{segment_role}）")
        if count == 1:
            segment_role = "全体"
        runtime_segment_positions.append(position)
        runtime_segment_counts.append(count)
        runtime_segment_roles.append(segment_role)
        location_index = min(canonical_index - 1, len(canonical_locations) - 1)
        canonical_location_sequence = canonical_location_sequences[location_index]
        canonical_segments = canonical_location_segments[location_index]
        beat_function_order = ("setup", "pressure", "turn", "payoff")
        function_start = (position - 1) * len(beat_function_order) // count
        function_end = position * len(beat_function_order) // count
        allowed_segment_functions = set(
            beat_function_order[function_start:function_end]
            or [beat_function_order[min(function_start, len(beat_function_order) - 1)]]
        )
        runtime_location_sequence = list(canonical_location_sequence)
        runtime_location = runtime_location_sequence[0]
        runtime_segments: list[dict[str, Any]] = []
        for segment_index, canonical_segment in enumerate(canonical_segments):
            if canonical_segment["location"] not in runtime_location_sequence:
                continue
            runtime_segment = deepcopy(canonical_segment)
            segment_overrides = runtime_segment.get("beat_overrides")
            if isinstance(segment_overrides, dict) and count > 1:
                runtime_segment["beat_overrides"] = {
                    function: deepcopy(override)
                    for function, override in segment_overrides.items()
                    if function in allowed_segment_functions
                }
            if count > 1:
                segment_count = len(canonical_segments)
                if segment_count <= 1 or segment_index == segment_count - 1:
                    root_owner_functions = {"payoff"}
                elif segment_index == 0:
                    root_owner_functions = {"setup"}
                else:
                    middle_functions = ("pressure", "turn")
                    middle_index = min(
                        segment_index - 1,
                        len(middle_functions) - 1,
                    )
                    root_owner_functions = {middle_functions[middle_index]}
                runtime_segment["root_active_beat_functions"] = [
                    function
                    for function in beat_function_order
                    if function in root_owner_functions
                    and function in allowed_segment_functions
                ]
            runtime_segments.append(runtime_segment)
        runtime_locations.append(runtime_location)
        runtime_location_sequences.append(runtime_location_sequence)
        runtime_location_segments.append(runtime_segments)
        time_index = min(canonical_index - 1, len(canonical_times_of_day) - 1)
        runtime_times_of_day.append(canonical_times_of_day[time_index])

    base_scene_seconds, remainder = divmod(plan.target_seconds, runtime_count)
    scene_target_durations = [
        base_scene_seconds + (1 if index < remainder else 0)
        for index in range(runtime_count)
    ]

    expanded = dict(profile)
    expanded.update(
        {
            "scene_titles": runtime_titles,
            "scene_locations": runtime_locations,
            "scene_location_sequences": runtime_location_sequences,
            "scene_location_segments": runtime_location_segments,
            "scene_times_of_day": runtime_times_of_day,
            "canonical_scene_titles": canonical_titles,
            "canonical_scene_location_sequences": canonical_location_sequences,
            "canonical_scene_times_of_day": canonical_times_of_day,
            "canonical_scene_indices": canonical_scene_indices,
            "canonical_scene_count": canonical_count,
            "scene_target_durations": scene_target_durations,
            "scene_segment_positions": runtime_segment_positions,
            "scene_segment_counts": runtime_segment_counts,
            "scene_segment_roles": runtime_segment_roles,
            "duration_plan": plan.to_dict(),
        }
    )
    return expanded


def _allocate_scene_cut_durations(
    *,
    scene_target_seconds: int,
    cut_count: int,
) -> list[int]:
    """Partition a scene target exactly across its authored semantic cuts."""

    if (
        isinstance(scene_target_seconds, bool)
        or not isinstance(scene_target_seconds, int)
        or scene_target_seconds <= 0
    ):
        raise RuntimeError("scene target duration must be a positive integer")
    if isinstance(cut_count, bool) or not isinstance(cut_count, int) or cut_count <= 0:
        raise RuntimeError("scene cut count must be a positive integer")
    base_seconds, remainder = divmod(scene_target_seconds, cut_count)
    durations = [
        base_seconds + (1 if index < remainder else 0)
        for index in range(cut_count)
    ]
    if any(seconds < 1 or seconds > 60 for seconds in durations):
        raise RuntimeError(
            "scene target cannot be partitioned within Kling duration range "
            f"1-60 seconds: target={scene_target_seconds}, cuts={cut_count}"
        )
    return durations


def _duration_exception_for_cut(cut_duration_seconds: int) -> dict[str, Any]:
    """Declare when an authored semantic cut intentionally exceeds 12 seconds."""

    enabled = cut_duration_seconds > 12
    return {
        "allowed": enabled,
        "reason": (
            "scene target durationをsemantic cut数へ厳密配分し、"
            "durationだけを理由に未承認cutを増やさないため"
            if enabled
            else ""
        ),
    }


def _md_yaml(title: str, data: dict[str, Any]) -> str:
    return f"# {title}\n\n```yaml\n{yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=120)}```\n"


def _write_run_text_nofollow(
    run_dir: Path,
    path: Path,
    text: str,
) -> None:
    try:
        relative = path.relative_to(run_dir)
    except ValueError as exc:
        raise ValueError(
            f"run artifact path escapes run directory: {path}"
        ) from exc
    active_root = _active_materialization_root(run_dir)
    lexical_root = os.path.abspath(os.fspath(run_dir))
    identity = (
        active_root[1]
        if active_root is not None and active_root[0] == lexical_root
        else directory_identity_nofollow(run_dir)
    )
    write_regular_file_nofollow(
        destination_root=run_dir,
        destination_relative=relative,
        data=text.encode("utf-8"),
        expected_destination_root_identity=identity,
    )


def _recover_interrupted_scene_pair_publish(
    run_dir: Path,
    *,
    root_identity: PathIdentity,
) -> None:
    """Restore the prior script/manifest generation after a crashed publish."""

    staging_root = run_dir / "logs" / "authoring" / "staging"
    if not staging_root.exists():
        return
    if staging_root.is_symlink() or not staging_root.is_dir():
        raise RuntimeError("scene authoring staging root is unsafe")
    for entry in os.scandir(staging_root):
        if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
            continue
        generation_id = entry.name
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+\-]*", generation_id) is None:
            raise RuntimeError("scene authoring staging generation id is unsafe")
        journal_relative = (
            Path("logs")
            / "authoring"
            / "staging"
            / generation_id
            / "publish.journal.json"
        )
        try:
            journal_raw = read_regular_file_nofollow(
                run_dir,
                journal_relative,
                expected_root_identity=root_identity,
            )
        except FileNotFoundError:
            continue
        try:
            journal = json.loads(journal_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("scene authoring publish journal is invalid") from exc
        if not isinstance(journal, dict) or journal.get("status") != "publishing":
            continue
        target_digests = journal.get("canonical_target_sha256")
        previous = journal.get("previous_canonical")
        expected_targets = {"script.md", "video_manifest.md"}
        if (
            not isinstance(target_digests, dict)
            or set(target_digests) != expected_targets
            or not isinstance(previous, dict)
            or set(previous) != expected_targets
        ):
            raise RuntimeError("scene authoring publish journal cannot be recovered")
        for relative in expected_targets:
            target_digest = str(target_digests.get(relative) or "")
            previous_record = previous.get(relative)
            if (
                re.fullmatch(r"sha256:[0-9a-f]{64}", target_digest) is None
                or not isinstance(previous_record, dict)
            ):
                raise RuntimeError("scene authoring publish binding is malformed")
            try:
                current = read_regular_file_nofollow(
                    run_dir,
                    relative,
                    expected_root_identity=root_identity,
                )
            except FileNotFoundError:
                current = None
            current_digest = (
                "sha256:" + hashlib.sha256(current).hexdigest()
                if current is not None
                else None
            )
            previous_exists = previous_record.get("exists") is True
            previous_digest = previous_record.get("sha256")
            if previous_exists:
                if (
                    not isinstance(previous_digest, str)
                    or re.fullmatch(r"sha256:[0-9a-f]{64}", previous_digest)
                    is None
                ):
                    raise RuntimeError("scene authoring backup digest is malformed")
                if current_digest == previous_digest:
                    continue
                if current_digest != target_digest:
                    raise RuntimeError(
                        f"scene authoring active bytes changed during recovery: {relative}"
                    )
                backup_path = str(previous_record.get("backup_path") or "")
                expected_backup = (
                    Path("logs")
                    / "authoring"
                    / "staging"
                    / generation_id
                    / "publish_backup"
                    / relative
                ).as_posix()
                if backup_path != expected_backup:
                    raise RuntimeError("scene authoring backup path is invalid")
                backup = read_regular_file_nofollow(
                    run_dir,
                    backup_path,
                    expected_root_identity=root_identity,
                )
                if "sha256:" + hashlib.sha256(backup).hexdigest() != previous_digest:
                    raise RuntimeError("scene authoring backup bytes changed")
                write_regular_file_nofollow(
                    destination_root=run_dir,
                    destination_relative=relative,
                    data=backup,
                    expected_destination_root_identity=root_identity,
                )
            else:
                if current is None:
                    continue
                if current_digest != target_digest:
                    raise RuntimeError(
                        f"scene authoring active bytes changed during recovery: {relative}"
                    )
                if not unlink_regular_file_verified_nofollow(
                    root=run_dir,
                    relative_path=relative,
                    expected_root_identity=root_identity,
                    expected_sha256=target_digest.removeprefix("sha256:"),
                ):
                    raise RuntimeError(
                        f"scene authoring recovery could not remove: {relative}"
                    )
        journal["status"] = "rolled_back"
        journal["error"] = "recovered interrupted canonical publish"
        write_regular_file_nofollow(
            destination_root=run_dir,
            destination_relative=journal_relative,
            data=(
                json.dumps(journal, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n"
            ).encode("utf-8"),
            expected_destination_root_identity=root_identity,
        )


def _active_materialization_root(
    run_dir: Path,
) -> tuple[str, PathIdentity, int, bool] | None:
    active_root = _ACTIVE_MATERIALIZATION_ROOT.get()
    lexical_root = os.path.abspath(os.fspath(run_dir))
    if active_root is not None and active_root[0] == lexical_root:
        return active_root
    shared_binding = current_run_root_binding()
    if (
        shared_binding is not None
        and shared_binding.lexical_root == lexical_root
    ):
        return (
            shared_binding.lexical_root,
            shared_binding.identity,
            shared_binding.descriptor,
            False,
        )
    return None


def _verify_active_materialization_root(
    run_dir: Path,
    active_root: tuple[str, PathIdentity, int, bool],
) -> None:
    descriptor = open_directory_nofollow(
        run_dir,
        expected_identity=active_root[1],
    )
    os.close(descriptor)


def _read_active_root_file(
    *,
    run_dir: Path,
    relative_path: str | Path,
    active_root: tuple[str, PathIdentity, int, bool],
    missing_ok: bool = False,
) -> bytes:
    try:
        relative = Path(relative_path)
        if relative == Path("state.txt"):
            return read_run_file_bytes_serialized(run_dir, relative)
        return read_regular_file_nofollow(
            run_dir,
            relative,
            expected_root_identity=active_root[1],
        )
    except FileNotFoundError:
        if missing_ok:
            return b""
        raise


def write_run_index(
    run_dir: Path,
    *,
    state: dict[str, str] | None = None,
) -> Path:
    return _write_run_index(run_dir, state=state)


def append_state_snapshot(
    state_path: Path,
    updates: dict[str, str],
) -> dict[str, str]:
    run_dir = state_path.parent
    active_root = _active_materialization_root(run_dir)
    if active_root is None:
        return _append_state_snapshot(state_path, updates)
    if state_path.name != "state.txt":
        raise ValueError(
            f"state snapshot must target state.txt: {state_path}"
        )
    _verify_active_materialization_root(run_dir, active_root)
    # The shared store performs read-current -> merge -> delta append ->
    # current-view publication under the same state append lock.  The active
    # frontend binding keeps every artifact write pinned to this run inode.
    return _append_state_snapshot(state_path, updates)


def _write_scene_design_json(
    run_dir: Path,
    filename: str,
    payload: dict[str, Any],
) -> None:
    active_root = _active_materialization_root(run_dir)
    if active_root is None:
        _raw_write_scene_design_json(run_dir, filename, payload)
        return
    if Path(filename).name != filename:
        raise ValueError(
            f"scene design filename must be a basename: {filename}"
        )
    _write_run_text_nofollow(
        run_dir,
        run_dir / "logs" / "scene_design" / filename,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def _read_scene_design_json(
    run_dir: Path,
    filename: str,
) -> dict[str, Any]:
    active_root = _active_materialization_root(run_dir)
    if active_root is None:
        return _raw_read_scene_design_json(run_dir, filename)
    if Path(filename).name != filename:
        raise ValueError(
            f"scene design filename must be a basename: {filename}"
        )
    try:
        payload = json.loads(
            _read_active_root_file(
                run_dir=run_dir,
                relative_path=(
                    Path("logs") / "scene_design" / filename
                ),
                active_root=active_root,
            ).decode("utf-8")
        )
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, UnicodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_cut_design_context(
    run_dir: Path,
    *,
    now: str,
    topic: str,
    phase: str,
    profile: dict[str, Any] | None = None,
    scene_context: dict[str, Any] | None = None,
    cut_context: dict[str, Any] | None = None,
    partial_counts: dict[str, Any] | None = None,
    flow: str | None = None,
    status: str | None = None,
    reason: str | None = None,
) -> None:
    if _active_materialization_root(run_dir) is None:
        _raw_write_cut_design_context(
            run_dir,
            now=now,
            topic=topic,
            phase=phase,
            profile=profile,
            scene_context=scene_context,
            cut_context=cut_context,
            partial_counts=partial_counts,
            flow=flow,
            status=status,
            reason=reason,
        )
        return
    payload: dict[str, Any] = {
        "schema_version": "cut_design_generation_context_v1",
        "updated_at": now,
        "topic": topic,
        "phase": phase,
        "profile_summary": profile_failure_summary(profile or {}),
        "scene_context": scene_context or {},
        "cut_context": cut_context or {},
        "partial_counts": partial_counts or {},
    }
    if flow:
        payload["flow"] = flow
    if status:
        payload["status"] = status
    if reason:
        payload["reason"] = reason
    _write_scene_design_json(
        run_dir,
        "latest_generation_context.json",
        payload,
    )


def _write_cut_design_failure_log(
    run_dir: Path,
    *,
    now: str,
    topic: str,
    phase: str,
    profile: dict[str, Any] | None,
    exc: BaseException,
) -> None:
    if _active_materialization_root(run_dir) is None:
        _raw_write_cut_design_failure_log(
            run_dir,
            now=now,
            topic=topic,
            phase=phase,
            profile=profile,
            exc=exc,
        )
        return
    latest_context = _read_scene_design_json(
        run_dir,
        "latest_generation_context.json",
    )
    scene_event_input = _read_scene_design_json(
        run_dir,
        "scene_event_input.json",
    )
    scene_event_output = _read_scene_design_json(
        run_dir,
        "scene_event_output.json",
    )
    scene_generation_prompts = _read_scene_design_json(
        run_dir,
        SCENE_GENERATION_PROMPTS_FILENAME,
    )
    payload = {
        "schema_version": "cut_design_failure_v1",
        "created_at": now,
        "topic": topic,
        "phase": phase,
        "profile_summary": profile_failure_summary(profile or {}),
        "latest_generation_context": latest_context,
        "partial_artifacts": {
            "scene_event_input": {
                "path": scene_design_log_relpath(
                    "scene_event_input.json"
                ),
                "scene_count": scene_event_input.get("scene_count"),
            },
            "scene_event_output": {
                "path": scene_design_log_relpath(
                    "scene_event_output.json"
                ),
                "scene_count": scene_event_output.get("scene_count"),
            },
            "scene_generation_prompts": {
                "path": scene_design_log_relpath(
                    SCENE_GENERATION_PROMPTS_FILENAME
                ),
                "scene_count": scene_generation_prompts.get("scene_count"),
            },
        },
        "error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exception(
                type(exc),
                exc,
                exc.__traceback__,
            ),
        },
    }
    _write_scene_design_json(
        run_dir,
        "cut_contract_failure.json",
        payload,
    )
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "runtime.stage": "cut_design_failed",
            "runtime.cut_design.status": "failed",
            "runtime.cut_design.phase": phase,
            "runtime.cut_design.error_type": type(exc).__name__,
            "runtime.cut_design.error": str(exc)[:2000],
            "runtime.cut_design.latest_context": scene_design_log_relpath(
                "latest_generation_context.json"
            ),
            "runtime.cut_design.failure_log": scene_design_log_relpath(
                "cut_contract_failure.json"
            ),
            "slot.p420.status": "failed",
            "slot.p420.note": (
                "cut design failed before frontend handoff"
            ),
            "cut_design.status": "failed",
        },
    )


def _rewrite_subprocess_run_paths(
    command: list[str | os.PathLike[str]],
    *,
    lexical_root: str,
) -> list[str]:
    rewritten: list[str] = []
    for raw_argument in command:
        argument = os.fspath(raw_argument)
        absolute_argument = os.path.abspath(argument)
        try:
            contained = os.path.commonpath(
                (lexical_root, absolute_argument)
            ) == lexical_root
        except ValueError:
            contained = False
        if contained:
            relative = os.path.relpath(absolute_argument, lexical_root)
            rewritten.append("." if relative == "." else relative)
        else:
            rewritten.append(argument)
    return rewritten


def _run_materialization_subprocess(
    run_dir: Path,
    command: list[str | os.PathLike[str]],
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    active_root = _active_materialization_root(run_dir)
    if active_root is None:
        return subprocess.run(command, **kwargs)
    _verify_active_materialization_root(run_dir, active_root)
    subprocess_command = [os.fspath(argument) for argument in command]
    if not active_root[3]:
        subprocess_command = _rewrite_subprocess_run_paths(
            command,
            lexical_root=active_root[0],
        )
        inherited_descriptors = set(kwargs.pop("pass_fds", ()))
        inherited_descriptors.add(active_root[2])
        kwargs["pass_fds"] = tuple(sorted(inherited_descriptors))
        if "preexec_fn" in kwargs:
            raise ValueError(
                "frontend materialization subprocess cannot override "
                "its pinned-root preexec"
            )
        root_descriptor = active_root[2]

        def enter_pinned_root() -> None:
            os.fchdir(root_descriptor)
            os.close(root_descriptor)

        kwargs["preexec_fn"] = enter_pinned_root
    try:
        return subprocess.run(subprocess_command, **kwargs)
    finally:
        _verify_active_materialization_root(run_dir, active_root)


def _run_id_from_dir(run_dir: Path) -> str:
    resolved = run_dir.resolve()
    try:
        return resolved.relative_to(REPO_ROOT / "output").as_posix()
    except ValueError as exc:
        raise SystemExit(f"--run-dir must be under output/: {run_dir}") from exc


def _validated_fresh_cli_run_dir(
    raw_run_dir: str,
    *,
    expected_identity: PathIdentity | None = None,
) -> Path:
    run_dir = Path(raw_run_dir)
    _run_id_from_dir(run_dir)
    if run_dir.is_symlink():
        raise SystemExit(f"--run-dir must not be a symlink: {run_dir}")
    if expected_identity is not None and not run_dir.exists():
        raise SystemExit(
            f"--run-dir disappeared after server reservation: {run_dir}"
        )
    if run_dir.exists() and not run_dir.is_dir():
        raise SystemExit(f"--run-dir must be a directory: {run_dir}")
    stale_entries: list[str] = []
    if run_dir.is_dir():
        for entry in run_dir.iterdir():
            if entry.name == ".locks" and entry.is_dir():
                descendants = tuple(entry.rglob("*"))
                safe = all(
                    not path.is_symlink()
                    and (
                        path.is_dir()
                        or (
                            path.is_file()
                            and path.suffix == ".lock"
                        )
                    )
                    for path in descendants
                )
            elif entry.name == "logs" and entry.is_dir():
                descendants = tuple(entry.rglob("*"))
                safe = all(
                    not path.is_symlink()
                    and (
                        path.is_dir()
                        or path.is_file()
                    )
                    and (
                        path == entry / "app_server"
                        or (entry / "app_server") in path.parents
                    )
                    for path in descendants
                )
            elif entry.name == ".toc_frontend_create.lock":
                safe = entry.is_file() and not entry.is_symlink()
            else:
                safe = False
            if entry.is_symlink() or not safe:
                stale_entries.append(entry.name)
        stale_entries.sort()
    if stale_entries:
        raise SystemExit(
            "--run-dir must be empty for a fresh run: "
            + ", ".join(stale_entries)
        )
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


@contextmanager
def _run_materialization_lock(
    run_dir: Path,
    *,
    expected_identity: PathIdentity | None = None,
    protect_pathname: bool = False,
    inherited_descriptor: int | None = None,
):
    # Kept for caller compatibility. Root safety is provided by an
    # owner-death-safe inode lock plus fd-relative writes; persistent
    # filesystem flags would survive SIGKILL and strand the run.
    _ = protect_pathname
    inherited_lock = inherited_descriptor is not None
    if inherited_descriptor is None:
        root_descriptor = open_directory_nofollow(
            run_dir,
            expected_identity=expected_identity,
        )
    else:
        root_descriptor = inherited_descriptor
        os.set_inheritable(root_descriptor, False)
        opened = os.fstat(root_descriptor)
        actual_identity = opened.st_dev, opened.st_ino
        if (
            not stat.S_ISDIR(opened.st_mode)
            or expected_identity is None
            or actual_identity != expected_identity
        ):
            os.close(root_descriptor)
            raise RuntimeError(
                "inherited frontend-create run descriptor identity changed: "
                f"{run_dir}"
            )
    opened_root = os.fstat(root_descriptor)
    root_identity = opened_root.st_dev, opened_root.st_ino
    active_root_token = None
    try:
        fcntl.flock(
            root_descriptor,
            fcntl.LOCK_EX | fcntl.LOCK_NB,
        )
    except BlockingIOError as exc:
        os.close(root_descriptor)
        raise RuntimeError(
            f"another frontend-create process owns this run: {run_dir}"
        ) from exc
    except Exception:
        os.close(root_descriptor)
        raise
    try:
        with bind_run_root(
            run_dir,
            expected_identity=root_identity,
            descriptor=root_descriptor,
        ):
            active_root_token = _ACTIVE_MATERIALIZATION_ROOT.set(
                (
                    os.path.abspath(os.fspath(run_dir)),
                    root_identity,
                    root_descriptor,
                    False,
                )
            )
            yield
            verified = open_directory_nofollow(
                run_dir,
                expected_identity=root_identity,
            )
            os.close(verified)
    finally:
        if active_root_token is not None:
            _ACTIVE_MATERIALIZATION_ROOT.reset(active_root_token)
        if not inherited_lock:
            fcntl.flock(root_descriptor, fcntl.LOCK_UN)
        os.close(root_descriptor)


def _profile_from_research(profile: dict[str, Any], research: dict[str, Any]) -> dict[str, Any]:
    """Project researched source material into story and cut builders."""

    projected = dict(profile)
    materials = research.get("story_materials") if isinstance(research.get("story_materials"), dict) else {}
    setting = materials.get("setting") if isinstance(materials.get("setting"), dict) else {}
    projected["story_time"] = str(setting.get("time_or_era") or profile.get("story_time") or "").strip()
    raw_events = materials.get("chronological_events") if isinstance(materials.get("chronological_events"), list) else []
    event_records = [item for item in raw_events if isinstance(item, dict) and str(item.get("event") or "").strip()]
    if event_records:
        projected["events"] = [str(item["event"]).strip() for item in event_records]
        projected["research_event_ids_by_text"] = {
            str(item["event"]).strip(): str(item.get("event_id") or f"E{index:02d}").strip()
            for index, item in enumerate(event_records, start=1)
        }
        projected["research_event_ids"] = list(projected["research_event_ids_by_text"].values())
    canonical_dump = str(materials.get("canonical_story_dump") or "").strip()
    if canonical_dump:
        projected["summary"] = canonical_dump
    characters = materials.get("characters") if isinstance(materials.get("characters"), list) else []
    protagonist = next(
        (
            item
            for item in characters
            if isinstance(item, dict)
            and (
                str(item.get("character_id") or "").strip() == "protagonist"
                or "主人公" in str(item.get("role") or "")
            )
        ),
        None,
    )
    if isinstance(protagonist, dict) and str(protagonist.get("name") or "").strip():
        projected["protagonist_name"] = str(protagonist["name"]).strip()
    passages = research.get("source_passages") if isinstance(research.get("source_passages"), list) else []
    passage_records = [
        item
        for item in passages
        if isinstance(item, dict)
        and str(item.get("passage_id") or "").strip()
        and str(item.get("passage") or "").strip()
    ]
    projected["research_passage_ids"] = [str(item["passage_id"]).strip() for item in passage_records]
    projected["research_passage_ids_by_text"] = {
        str(item["passage"]).strip(): str(item["passage_id"]).strip()
        for item in passage_records
    }
    projected["research"] = research
    return projected


def _profile_from_story(profile: dict[str, Any], story: dict[str, Any]) -> dict[str, Any]:
    """Project authored scene intent into cut construction without inventing a second story."""

    projected = dict(profile)
    metadata = story.get("story_metadata") if isinstance(story.get("story_metadata"), dict) else {}
    # The authored story is canonical.  An explicit empty string is meaningful
    # for user-created worlds and must not resurrect a topic-derived era.
    projected["story_time"] = str(metadata.get("time") or "").strip()
    script = story.get("script") if isinstance(story.get("script"), dict) else {}
    scenes = [item for item in script.get("scenes", []) if isinstance(item, dict)]
    projected["story"] = story
    projected["story_scenes"] = scenes
    source_contract = story.get("adaptation_source_contract")
    if isinstance(source_contract, dict) and source_contract:
        projected["adaptation_source_contract"] = deepcopy(source_contract)
    if not scenes:
        return projected

    existing_titles = [str(item) for item in profile.get("scene_titles") or []]
    projected["scene_titles"] = [
        str(scene.get("title") or (existing_titles[index] if index < len(existing_titles) else f"scene {index + 1}")).strip()
        for index, scene in enumerate(scenes)
    ]
    projected["scene_ids"] = [
        str(scene.get("scene_id") or f"scene_{index + 1:02d}").strip()
        for index, scene in enumerate(scenes)
    ]
    projected["scene_semantic_responsibility_ids"] = [
        str(
            scene.get("semantic_scene_responsibility_id")
            or scene.get("scene_id")
            or f"scene_{index + 1:02d}"
        ).strip()
        for index, scene in enumerate(scenes)
    ]

    def resized(values: Any, fallback: Any) -> list[Any]:
        source_values = list(values) if isinstance(values, list) else []
        return [source_values[min(index, len(source_values) - 1)] if source_values else fallback for index in range(len(scenes))]

    existing_locations = resized(
        profile.get("scene_locations"),
        str((profile.get("places") or ["物語の場所"])[0]),
    )
    existing_location_sequences = resized(profile.get("scene_location_sequences"), [])
    existing_location_segments = resized(profile.get("scene_location_segments"), [])
    projected_locations: list[str] = []
    projected_location_ids: list[str] = []
    projected_location_sequences: list[list[str]] = []
    projected_location_segments: list[list[dict[str, Any]]] = []
    for scene, fallback_name, fallback_sequence, fallback_segments in zip(
        scenes,
        existing_locations,
        existing_location_sequences,
        existing_location_segments,
        strict=True,
    ):
        location = scene.get("location") if isinstance(scene.get("location"), dict) else {}
        location_name = str(location.get("name") or fallback_name).strip()
        projected_location_ids.append(
            str(location.get("location_id") or location.get("place_id") or "").strip()
        )
        raw_sequence = location.get("sequence")
        if isinstance(raw_sequence, list):
            sequence = [str(value).strip() for value in raw_sequence if str(value).strip()]
        elif isinstance(fallback_sequence, list):
            sequence = [str(value).strip() for value in fallback_sequence if str(value).strip()]
        else:
            sequence = []
        normalized_sequence = sequence or [location_name]
        raw_segments = location.get("segments")
        if not isinstance(raw_segments, list):
            raw_segments = fallback_segments if isinstance(fallback_segments, list) else []
        segments = [
            segment
            for value in raw_segments
            if (segment := _normalize_location_segment(value))
            and segment["location"] in normalized_sequence
        ]
        projected_locations.append(location_name)
        projected_location_sequences.append(normalized_sequence)
        projected_location_segments.append(segments)
    projected["scene_locations"] = projected_locations
    projected["scene_location_ids"] = projected_location_ids
    projected["scene_location_sequences"] = projected_location_sequences
    projected["scene_location_segments"] = projected_location_segments
    existing_times_of_day = resized(profile.get("scene_times_of_day"), "")
    projected["scene_times_of_day"] = [
        str(scene.get("time_of_day") if "time_of_day" in scene else value).strip()
        for scene, value in zip(scenes, existing_times_of_day)
    ]
    projected["scene_time_of_day_visual_bases"] = [
        str(
            scene.get("time_of_day_visual_basis")
            or _time_of_day_visual_basis(time_of_day)
        ).strip()
        for scene, time_of_day in zip(
            scenes,
            projected["scene_times_of_day"],
            strict=True,
        )
    ]
    projected["canonical_scene_indices"] = [
        int(scene.get("canonical_scene_index") or value)
        for scene, value in zip(scenes, resized(profile.get("canonical_scene_indices"), 1))
    ]
    projected["scene_target_durations"] = [
        int(scene.get("target_duration_seconds") or value)
        for scene, value in zip(scenes, resized(profile.get("scene_target_durations"), 40))
    ]
    projected["scene_segment_positions"] = [
        int((scene.get("segment") or {}).get("position") or value)
        for scene, value in zip(scenes, resized(profile.get("scene_segment_positions"), 1))
    ]
    projected["scene_segment_counts"] = [
        int((scene.get("segment") or {}).get("count") or value)
        for scene, value in zip(scenes, resized(profile.get("scene_segment_counts"), 1))
    ]
    projected["scene_segment_roles"] = [
        str((scene.get("segment") or {}).get("role") or value)
        for scene, value in zip(scenes, resized(profile.get("scene_segment_roles"), "全体"))
    ]
    return projected


def _positive_story_duration_seconds(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seconds) or seconds <= 0:
        return None
    return seconds


def _research_duration_contract_errors(
    research: dict[str, Any],
    *,
    target_duration_seconds: int,
) -> list[str]:
    """Ensure researched source material preserves the requested duration plan."""

    plan = build_duration_plan(target_duration_seconds)
    metadata = research.get("metadata") if isinstance(research.get("metadata"), dict) else {}
    errors: list[str] = []
    raw_target = metadata.get("target_duration_seconds")
    if raw_target is None:
        normalized_target = None
    else:
        try:
            normalized_target = normalize_target_duration(raw_target)
        except ValueError:
            normalized_target = None
    if normalized_target != plan.target_seconds:
        errors.append(
            "metadata.target_duration_seconds must preserve the requested target "
            f"({normalized_target!r}!={plan.target_seconds})"
        )

    duration_plan = metadata.get("duration_plan") if isinstance(metadata.get("duration_plan"), dict) else {}
    expected_plan = plan.to_dict()
    for key, expected in expected_plan.items():
        raw_value = duration_plan.get(key)
        if raw_value is None or isinstance(raw_value, bool):
            actual: float | None = None
        else:
            try:
                actual = float(raw_value)
            except (TypeError, ValueError):
                actual = None
        if actual is None or not math.isfinite(actual) or actual != float(expected):
            errors.append(f"metadata.duration_plan.{key} must equal {expected} (got {raw_value!r})")
    return errors


def _validate_research_duration_contract(
    research: dict[str, Any],
    *,
    target_duration_seconds: int,
) -> None:
    errors = _research_duration_contract_errors(
        research,
        target_duration_seconds=target_duration_seconds,
    )
    if errors:
        raise RuntimeError(
            "research duration contract failed before story authoring: " + "; ".join(errors)
        )


def _story_duration_contract_errors(
    story: dict[str, Any],
    *,
    target_duration_seconds: int,
) -> list[str]:
    """Return deterministic duration-floor defects before any cut is authored."""

    plan = build_duration_plan(target_duration_seconds)
    errors: list[str] = []
    metadata = story.get("story_metadata") if isinstance(story.get("story_metadata"), dict) else {}
    raw_target = metadata.get("target_duration_seconds")
    if raw_target is None:
        normalized_target = None
    else:
        try:
            normalized_target = normalize_target_duration(raw_target)
        except ValueError:
            normalized_target = None
    if normalized_target != plan.target_seconds:
        errors.append(
            "story_metadata.target_duration_seconds must preserve the requested target "
            f"({normalized_target!r}!={plan.target_seconds})"
        )

    script = story.get("script") if isinstance(story.get("script"), dict) else {}
    raw_scenes = script.get("scenes")
    scenes = [scene for scene in raw_scenes if isinstance(scene, dict)] if isinstance(raw_scenes, list) else []
    semantic_scene_contract = (
        str(metadata.get("scene_authoring_contract") or "").strip()
        == "story_scene_contract_v1"
    )
    if not semantic_scene_contract and len(scenes) < plan.minimum_scene_count:
        errors.append(f"scene count below duration floor ({len(scenes)}<{plan.minimum_scene_count})")
    if not isinstance(raw_scenes, list) or len(scenes) != len(raw_scenes):
        errors.append("script.scenes must contain only scene objects")

    scene_target_seconds: list[float] = []
    narration_target_seconds: list[float] = []
    for index, scene in enumerate(scenes, start=1):
        scene_seconds = _positive_story_duration_seconds(scene.get("target_duration_seconds"))
        if scene_seconds is None:
            errors.append(
                f"scene[{index}].target_duration_seconds must be a positive integer"
            )
        elif not scene_seconds.is_integer():
            errors.append(
                f"scene[{index}].target_duration_seconds must be a positive integer"
            )
        else:
            scene_target_seconds.append(scene_seconds)
        narration_seconds = _positive_story_duration_seconds(scene.get("narration_target_seconds"))
        if narration_seconds is None:
            errors.append(f"scene[{index}].narration_target_seconds must be positive")
        else:
            narration_target_seconds.append(narration_seconds)

    if (
        len(scene_target_seconds) == len(scenes)
        and sum(scene_target_seconds) != plan.target_seconds
    ):
        errors.append(
            "scene target duration sum must equal requested target "
            f"({sum(scene_target_seconds):g}!={plan.target_seconds})"
        )
    if len(narration_target_seconds) == len(scenes) and sum(narration_target_seconds) < plan.minimum_narration_seconds:
        errors.append(
            "narration target duration sum below duration floor "
            f"({sum(narration_target_seconds):g}<{plan.minimum_narration_seconds})"
        )
    return errors


def _validate_story_duration_contract(
    story: dict[str, Any],
    *,
    target_duration_seconds: int,
) -> None:
    errors = _story_duration_contract_errors(
        story,
        target_duration_seconds=target_duration_seconds,
    )
    if errors:
        raise RuntimeError(
            "story duration contract failed before cut materialization: " + "; ".join(errors)
        )


def _story_time_of_day_contract_errors(story: dict[str, Any]) -> list[str]:
    metadata = story.get("story_metadata") if isinstance(story.get("story_metadata"), dict) else {}
    semantic_scene_contract = (
        str(metadata.get("scene_authoring_contract") or "").strip()
        == "story_scene_contract_v1"
    )
    errors: list[str] = []
    if metadata.get("scene_time_of_day_contract") != SCENE_TIME_OF_DAY_CONTRACT:
        errors.append(
            "story_metadata.scene_time_of_day_contract must equal "
            f"{SCENE_TIME_OF_DAY_CONTRACT}"
        )
    if (
        metadata.get("scene_time_of_day_visual_basis_contract")
        != SCENE_TIME_OF_DAY_VISUAL_BASIS_CONTRACT
    ):
        errors.append(
            "story_metadata.scene_time_of_day_visual_basis_contract must equal "
            f"{SCENE_TIME_OF_DAY_VISUAL_BASIS_CONTRACT}"
        )
    script = story.get("script") if isinstance(story.get("script"), dict) else {}
    scenes = script.get("scenes") if isinstance(script.get("scenes"), list) else []
    for index, scene in enumerate(scenes, start=1):
        value = scene.get("time_of_day") if isinstance(scene, dict) else None
        if not isinstance(value, str) or not value.strip():
            errors.append(f"scene[{index}].time_of_day must be a non-empty string")
        visual_basis = (
            scene.get("time_of_day_visual_basis")
            if isinstance(scene, dict)
            else None
        )
        if not isinstance(visual_basis, str) or not visual_basis.strip():
            errors.append(
                f"scene[{index}].time_of_day_visual_basis must be a non-empty string"
            )
        else:
            missing_dimensions = [
                dimension
                for dimension in ("光源", "明るさ", "影", "色温度")
                if dimension not in visual_basis
            ]
            if missing_dimensions:
                errors.append(
                    f"scene[{index}].time_of_day_visual_basis must cover "
                    + ", ".join(missing_dimensions)
                )
        location = scene.get("location") if isinstance(scene, dict) and isinstance(scene.get("location"), dict) else {}
        raw_sequence = location.get("sequence")
        sequence = [
            str(item).strip()
            for item in (raw_sequence if isinstance(raw_sequence, list) else [])
            if str(item).strip()
        ]
        if (
            not semantic_scene_contract
            and (str(location.get("mode") or "") == "sequence" or len(sequence) > 1)
        ):
            raw_segments = location.get("segments")
            segments = [
                segment
                for item in (raw_segments if isinstance(raw_segments, list) else [])
                if (segment := _normalize_location_segment(item))
            ]
            segment_locations = [segment["location"] for segment in segments]
            missing_locations = [name for name in sequence if name not in segment_locations]
            unexpected_locations = [name for name in segment_locations if name not in sequence]
            duplicate_locations = sorted(
                {name for name in segment_locations if segment_locations.count(name) > 1}
            )
            if missing_locations:
                errors.append(
                    f"scene[{index}].location.segments must cover every sequence location: "
                    + ", ".join(missing_locations)
                )
            if unexpected_locations:
                errors.append(
                    f"scene[{index}].location.segments contains locations outside sequence: "
                    + ", ".join(unexpected_locations)
                )
            if duplicate_locations:
                errors.append(
                    f"scene[{index}].location.segments must contain each location once: "
                    + ", ".join(duplicate_locations)
                )
            for segment_index, segment in enumerate(segments, start=1):
                for required_key in (
                    "responsibility",
                    "primary_subject",
                    "visible_action",
                    "required_visual_evidence",
                    "motion_brief",
                    "motion_end_state",
                ):
                    if not segment.get(required_key):
                        errors.append(
                            f"scene[{index}].location.segments[{segment_index}].{required_key} must be non-empty"
                        )
    return errors


def _validate_story_time_of_day_contract(story: dict[str, Any]) -> None:
    errors = _story_time_of_day_contract_errors(story)
    if errors:
        raise RuntimeError(
            "story scene time-of-day contract failed before cut materialization: "
            + "; ".join(errors)
        )


def _location_asset_specs(profile: dict[str, Any]) -> list[dict[str, Any]]:
    places = [str(value) for value in profile.get("scene_locations") or profile["places"]]
    for raw_sequence in profile.get("scene_location_sequences") or []:
        if isinstance(raw_sequence, list):
            places.extend(str(value) for value in raw_sequence if str(value).strip())
    specs: list[dict[str, Any]] = []
    unique_places = list(dict.fromkeys(str(place) for place in places))
    for index, place in enumerate(unique_places, start=1):
        subject = f"{place}の場所参照。人物なし"
        specs.append(
            {
                "asset_id": _safe_asset_id("location", place, index),
                "asset_type": "location_reference",
                "name": place,
                "output": f"assets/locations/{_safe_asset_id('location', place, index)}.png",
                "story_purpose": f"{place}の空間・光・質感を固定する",
                "reusable_reason": "同じ場所のcutで背景と空気感を保つ",
                "visual_spec": {"subject": subject},
                "reuse_contract": {"mode": "neutral_anchor"},
            }
        )
    return specs


def _location_spec_for_scene(profile: dict[str, Any], scene_index: int) -> dict[str, Any]:
    specs = _location_asset_specs(profile)
    scene_locations = [str(value) for value in profile.get("scene_locations") or []]
    desired_name = scene_locations[min(scene_index - 1, len(scene_locations) - 1)] if scene_locations else ""
    return next((spec for spec in specs if str(spec.get("name") or "") == desired_name), specs[-1])


def _canonical_scene_index(profile: dict[str, Any], scene_index: int) -> int:
    indices = profile.get("canonical_scene_indices")
    if isinstance(indices, list) and 0 <= scene_index - 1 < len(indices):
        return int(indices[scene_index - 1])
    return scene_index


def _phase_for_scene(profile: dict[str, Any], scene_index: int) -> str:
    canonical_index = _canonical_scene_index(profile, scene_index)
    return PHASES[min(max(canonical_index, 1), len(PHASES)) - 1]


def _scene_time_of_day(profile: dict[str, Any], scene_index: int) -> str:
    values = profile.get("scene_times_of_day")
    if isinstance(values, list) and 0 <= scene_index - 1 < len(values):
        return str(values[scene_index - 1] or "").strip()
    return ""


def _time_of_day_visual_basis(time_of_day: str) -> str:
    """Turn an open daypart string into explicit lighting evidence."""

    value = str(time_of_day or "").strip()
    if not value:
        return ""
    if "真夜中" in value or "深夜" in value:
        return (
            "光源は月光や時代に整合する弱い実用灯に限定する。空や窓外の明るさは深く暗い。"
            "影は長く高コントラストにし、色温度は冷たい月光と暖かな実用灯を分離する。"
        )
    if "夕" in value or "黄昏" in value:
        return (
            "光源は低い夕日の自然光を主にする。空や窓外の明るさは日没へ向けて落ちる。"
            "影は長く伸ばし、色温度は暖色寄りの夕光に整合させる。"
        )
    if "夜" in value:
        return (
            "光源は月光と時代に整合する実用灯に限定する。空や窓外の明るさは夜として暗い。"
            "影は光源ごとに明確に落とし、色温度は冷たい外光と暖かな室内灯を分離する。"
        )
    if "朝" in value:
        return (
            "光源は低い朝の自然光を主にする。空や窓外の明るさは夜明け後として穏やかに上がる。"
            "影は長く柔らかくし、色温度はわずかに暖かな朝光に整合させる。"
        )
    if "昼" in value or "正午" in value:
        return (
            "光源は高い位置からの昼の自然光を主にする。空や窓外の明るさは十分に高い。"
            "影は短く輪郭を保ち、色温度は中立的な昼光に整合させる。"
        )
    return (
        f"光源は「{value}」として物語内で定義された光に限定する。空や窓外の明るさ、"
        "影の長さと硬さ、色温度を同じ時間帯の条件として一貫させる。"
    )


def _scene_time_of_day_visual_basis(profile: dict[str, Any], scene_index: int) -> str:
    values = profile.get("scene_time_of_day_visual_bases")
    if isinstance(values, list) and 0 <= scene_index - 1 < len(values):
        explicit = str(values[scene_index - 1] or "").strip()
        if explicit:
            return explicit
    return _time_of_day_visual_basis(_scene_time_of_day(profile, scene_index))


def _scene_location_sequence(profile: dict[str, Any], scene_index: int) -> list[str]:
    values = profile.get("scene_location_sequences")
    if isinstance(values, list) and 0 <= scene_index - 1 < len(values):
        raw = values[scene_index - 1]
        if isinstance(raw, list):
            sequence = [str(value).strip() for value in raw if str(value).strip()]
            if sequence:
                return sequence
    locations = profile.get("scene_locations")
    if isinstance(locations, list) and 0 <= scene_index - 1 < len(locations):
        value = str(locations[scene_index - 1] or "").strip()
        if value:
            return [value]
    return []


def _normalize_location_segment(value: Any) -> dict[str, Any]:
    """Normalize one authored location segment without inventing content."""

    if not isinstance(value, dict):
        return {}
    location = str(value.get("location") or "").strip()
    if not location:
        return {}
    normalized: dict[str, Any] = {
        "location": location,
        "responsibility": str(value.get("responsibility") or "").strip(),
        "primary_subject": str(value.get("primary_subject") or "").strip(),
        "primary_subject_by_function": {
            str(key).strip(): str(item).strip()
            for key, item in (
                value.get("primary_subject_by_function")
                if isinstance(value.get("primary_subject_by_function"), dict)
                else {}
            ).items()
            if str(key).strip() and str(item).strip()
        },
        "beat_overrides": deepcopy(
            value.get("beat_overrides")
            if isinstance(value.get("beat_overrides"), dict)
            else {}
        ),
        "visible_action": str(value.get("visible_action") or "").strip(),
        "visible_reaction": str(value.get("visible_reaction") or "").strip(),
        "required_visual_evidence": list(
            dict.fromkeys(
                str(item).strip()
                for item in value.get("required_visual_evidence") or []
                if str(item).strip()
            )
        ),
        "required_roles": list(
            dict.fromkeys(
                str(item).strip()
                for item in value.get("required_roles") or []
                if str(item).strip()
            )
        ),
        "motion_brief": str(value.get("motion_brief") or "").strip(),
        "motion_end_state": str(value.get("motion_end_state") or "").strip(),
        "visible_character_state": {
            str(key): str(item).strip()
            for key, item in (
                value.get("visible_character_state")
                if isinstance(value.get("visible_character_state"), dict)
                else {}
            ).items()
            if str(item).strip()
        },
    }
    if "root_active_beat_functions" in value:
        raw_root_functions = value.get("root_active_beat_functions")
        normalized["root_active_beat_functions"] = list(
            dict.fromkeys(
                str(item).strip()
                for item in (
                    raw_root_functions
                    if isinstance(raw_root_functions, list)
                    else []
                )
                if str(item).strip()
            )
        )
    for policy_key in (
        "first_frame_character_asset_overrides",
        "first_frame_excluded_object_ids",
    ):
        if policy_key in value:
            normalized[policy_key] = deepcopy(value[policy_key])
    return normalized


def _scene_location_segments(
    profile: dict[str, Any],
    scene_index: int,
) -> list[dict[str, Any]]:
    """Return per-location authoring segments aligned to the scene route."""

    values = profile.get("scene_location_segments")
    if not isinstance(values, list) or not 0 <= scene_index - 1 < len(values):
        return []
    raw_segments = values[scene_index - 1]
    if not isinstance(raw_segments, list):
        return []
    allowed_locations = set(_scene_location_sequence(profile, scene_index))
    return [
        segment
        for value in raw_segments
        if (segment := _normalize_location_segment(value))
        and (not allowed_locations or segment["location"] in allowed_locations)
    ]


def _location_segment_root_is_active(
    segment: dict[str, Any], beat_function: str | None = None
) -> bool:
    """Treat absent scope as canonical; explicit empty scope as route-only."""

    if "root_active_beat_functions" not in segment:
        return True
    functions = {
        str(item).strip()
        for item in segment.get("root_active_beat_functions") or []
        if str(item).strip()
    }
    return beat_function in functions if beat_function is not None else bool(functions)


def _location_specs_for_scene_sequence(
    profile: dict[str, Any],
    scene_index: int,
) -> list[dict[str, Any]]:
    specs = _location_asset_specs(profile)
    by_name = {str(spec.get("name") or ""): spec for spec in specs}
    sequence = _scene_location_sequence(profile, scene_index)
    selected = [by_name[name] for name in sequence if name in by_name]
    return selected or [_location_spec_for_scene(profile, scene_index)]


def _scene_segment(profile: dict[str, Any], scene_index: int) -> tuple[int, int, str]:
    position_values = profile.get("scene_segment_positions")
    count_values = profile.get("scene_segment_counts")
    role_values = profile.get("scene_segment_roles")
    offset = scene_index - 1
    if isinstance(position_values, list) and isinstance(count_values, list) and isinstance(role_values, list):
        if 0 <= offset < min(len(position_values), len(count_values), len(role_values)):
            return int(position_values[offset]), int(count_values[offset]), str(role_values[offset])
    return 1, 1, "全体"


def _scene_artifact_state(profile: dict[str, Any], scene_index: int) -> str:
    canonical_index = _canonical_scene_index(profile, scene_index)
    segment_position, segment_count, _segment_role = _scene_segment(
        profile, scene_index
    )
    artifact_scene_indices = {
        int(value) for value in profile.get("artifact_scene_indices", [])
    }
    if canonical_index in artifact_scene_indices:
        return "focal"
    return "not_yet_revealed"


def _scene_uses_artifact(profile: dict[str, Any], scene_index: int) -> bool:
    return _scene_artifact_state(profile, scene_index) == "focal"


def _artifact_first_scene_index(profile: dict[str, Any]) -> int:
    if not profile.get("artifact_scene_indices"):
        return len(profile["scene_titles"])
    return next(
        (
            index
            for index in range(1, len(profile["scene_titles"]) + 1)
            if _scene_uses_artifact(profile, index)
        ),
        len(profile["scene_titles"]),
    )


def _supporting_character_asset_specs(profile: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []

    research = profile.get("research")
    materials = research.get("story_materials") if isinstance(research, dict) else {}
    raw_characters = materials.get("characters") if isinstance(materials, dict) else []
    character_records = [item for item in raw_characters or [] if isinstance(item, dict)]

    authored_story = profile.get("story")
    story_script = authored_story.get("script") if isinstance(authored_story, dict) else {}
    story_scenes = story_script.get("scenes") if isinstance(story_script, dict) else []
    slug = str(profile.get("slug") or "story")
    for index, record in enumerate(character_records, start=1):
        source_character_id = str(record.get("character_id") or "").strip()
        if not source_character_id or source_character_id == "protagonist":
            continue
        scene_indices = [
            int(scene.get("canonical_scene_index") or scene.get("scene_id") or scene_index)
            for scene_index, scene in enumerate(story_scenes or [], start=1)
            if isinstance(scene, dict)
            and source_character_id
            in {str(value).strip() for value in scene.get("character_ids") or [] if str(value).strip()}
        ]
        if not scene_indices:
            continue
        normalized_source_id = re.sub(r"[^a-zA-Z0-9]+", "_", source_character_id).strip("_").lower()
        if normalized_source_id:
            asset_id = f"{slug}_{normalized_source_id}_fullbody"
        else:
            asset_id = _safe_asset_id("character", f"{slug}_{source_character_id}", index)
        name = str(record.get("name") or source_character_id).strip()
        role = str(record.get("role") or "物語上の主要人物").strip()
        appearance_continuity = (
            dict(record.get("appearance_continuity"))
            if isinstance(record.get("appearance_continuity"), dict)
            else {}
        )
        raw_members = record.get("members") if isinstance(record.get("members"), list) else record.get("member_ids")
        member_ids = [str(value).strip() for value in raw_members or [] if str(value).strip()]
        plural_probe = f"{source_character_id} {record.get('name') or ''}".lower()
        is_ensemble = bool(member_ids) or any(token in plural_probe for token in ("たち", "姉妹", "兄弟", "sisters", "brothers", "group"))
        if is_ensemble and not member_ids:
            member_ids = [f"{source_character_id}_1", f"{source_character_id}_2"]
        subject_contract = {
            "identity_scope": "ensemble" if is_ensemble else "individual",
            "subject_count": len(member_ids) if is_ensemble else 1,
            "member_ids": member_ids,
        }
        role_probe = f"{source_character_id} {name} {role}".lower()
        role_tags: list[str] = []
        for terms, tag in (
            (("opposition", "抑圧", "妨げ", "支配"), "opponent"),
            (("競争", "偽", "候補"), "contrast_or_false_claimant"),
            (("helper", "助力", "援助", "導く"), "helper"),
            (("公的", "権威"), "authority_or_community"),
            (("witness", "見届け", "認識"), "witness"),
        ):
            if any(term in role_probe for term in terms):
                role_tags.append(tag)
        story_time = str(profile.get("story_time") or "").strip()
        period_clause = f"{story_time}の衣装・髪型・素材・身分表現" if story_time else "物語世界に整合する衣装・髪型・素材"
        specs.append(
            {
                "character_id": asset_id,
                "source_character_id": source_character_id,
                "name": name,
                "role_tags": role_tags,
                "reference_images": [f"assets/characters/{asset_id}.png"],
                "scene_indices": list(dict.fromkeys(scene_indices)),
                "story_purpose": role,
                "visual_subject": f"{name}の全身参照。{role}。実写映画の同一人物として固定し、{period_clause}を守る",
                "subject_contract": subject_contract,
                "appearance_contract": {
                    "social_position": str(record.get("social_position") or role).strip(),
                    "occupation_or_role": role,
                    "occasion_or_state": str(appearance_continuity.get("costume_state") or record.get("costume_state") or "物語内の通常状態").strip(),
                    "silhouette": str(record.get("silhouette") or "役割と身分を他人物から判別できる輪郭").strip(),
                    "materials": str(record.get("materials") or f"{period_clause}に整合する素材").strip(),
                    "condition": str(record.get("condition") or "役割と生活状況が手入れの状態から読める").strip(),
                    "palette": str(record.get("palette") or "他の主要人物と混同しない固有配色").strip(),
                    "must_avoid": [str(value).strip() for value in record.get("must_avoid") or ["現代服", "役割と矛盾する身分表現"] if str(value).strip()],
                },
                "reuse_contract": {"mode": "neutral_anchor"},
                **(
                    {
                        "identity_name": name,
                        "appearance_continuity": appearance_continuity,
                    }
                    if str(appearance_continuity.get("costume_state") or "").strip()
                    else {}
                ),
            }
        )
    return specs


def _protagonist_appearance_contract(profile: dict[str, Any]) -> dict[str, Any]:
    """Project authored role and appearance facts without inventing a costume."""

    research = profile.get("research")
    materials = research.get("story_materials") if isinstance(research, dict) else {}
    records = materials.get("characters") if isinstance(materials, dict) else []
    protagonist_record = next(
        (
            item
            for item in records or []
            if isinstance(item, dict)
            and str(item.get("character_id") or "").strip() == "protagonist"
        ),
        {},
    )
    role = str(protagonist_record.get("role") or "物語上の主人公").strip()
    continuity = (
        protagonist_record.get("appearance_continuity")
        if isinstance(protagonist_record.get("appearance_continuity"), dict)
        else {}
    )
    story_time = str(profile.get("story_time") or "").strip()
    period_materials = f"{story_time}に整合する素材" if story_time else "物語世界に整合する素材"
    return {
        "social_position": str(protagonist_record.get("social_position") or role).strip(),
        "occupation_or_role": role,
        "occasion_or_state": str(continuity.get("costume_state") or protagonist_record.get("costume_state") or "物語冒頭の通常状態").strip(),
        "silhouette": str(protagonist_record.get("silhouette") or "他の主要人物と混同しない主人公固有の輪郭").strip(),
        "materials": str(protagonist_record.get("materials") or period_materials).strip(),
        "condition": str(protagonist_record.get("condition") or "生活状況が衣装の手入れと摩耗から読める").strip(),
        "palette": str(protagonist_record.get("palette") or "後続の状態variantと区別できる固有配色").strip(),
        "must_avoid": [
            str(value).strip()
            for value in protagonist_record.get("must_avoid") or ["現代服", "後続場面でのみ現れる衣装"]
            if str(value).strip()
        ],
    }


def _protagonist_asset_for_cut(profile: dict[str, Any], scene_index: int, obligation_id: str) -> str:
    return str(profile["protagonist_asset_id"])


def _protagonist_reference_for_asset(profile: dict[str, Any], asset_id: str) -> str:
    return f"assets/characters/{profile['protagonist_asset_id']}.png"


def _supporting_object_asset_specs(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return []


def _supporting_character_ids_for_scene(profile: dict[str, Any], scene_index: int) -> list[str]:
    canonical_index = _canonical_scene_index(profile, scene_index)
    return [
        str(spec["character_id"])
        for spec in _supporting_character_asset_specs(profile)
        if canonical_index in {int(value) for value in spec.get("scene_indices", [])}
    ]


def _supporting_character_ids_for_cut(
    profile: dict[str, Any],
    scene_index: int,
    cut_plan: dict[str, Any],
    _scene_event: dict[str, Any],
    drawable_evidence: list[dict[str, str]] | None = None,
) -> list[str]:
    """Select only supporting cast that is drawable in this cut's assigned beat."""

    scene_candidates = [
        spec
        for spec in _supporting_character_asset_specs(profile)
        if _canonical_scene_index(profile, scene_index)
        in {int(value) for value in spec.get("scene_indices", [])}
        and str(spec.get("source_character_id") or "").strip()
    ]
    explicit_source_ids = {
        str(value).strip()
        for key in ("visible_character_ids", "character_ids")
        for value in cut_plan.get(key) or []
        if str(value).strip()
    }
    explicit_matches = [
        spec
        for spec in scene_candidates
        if str(spec.get("source_character_id") or "").strip() in explicit_source_ids
        or str(spec.get("character_id") or "").strip() in explicit_source_ids
    ]
    evidence_items = drawable_evidence if isinstance(drawable_evidence, list) else []
    evidence_text = json.dumps(evidence_items, ensure_ascii=False, sort_keys=True).lower()
    named_matches = [
        spec
        for spec in scene_candidates
        if any(
            token and token.lower() in evidence_text
            for token in (str(spec.get("source_character_id") or "").strip(), str(spec.get("name") or "").strip())
        )
    ]
    source_event_beat_ids = {
        str(value).strip()
        for value in [
            cut_plan.get("primary_event_beat_id"),
            *(cut_plan.get("source_event_beat_ids") or []),
        ]
        if str(value).strip()
    }
    source_role_ids: set[str] = set()
    source_event_text_parts: list[str] = []
    for beat in _scene_event.get("event_sequence") or []:
        if not isinstance(beat, dict) or str(beat.get("beat_id") or "").strip() not in source_event_beat_ids:
            continue
        concrete_event = beat.get("concrete_event") if isinstance(beat.get("concrete_event"), dict) else {}
        raw_who = concrete_event.get("who")
        who = raw_who if isinstance(raw_who, list) else [raw_who]
        source_role_ids.update(str(value).strip() for value in who if str(value or "").strip())
        source_event_text_parts.extend(
            str(value or "").strip()
            for value in (beat.get("what_happens"), concrete_event.get("what_happens"))
            if str(value or "").strip()
        )
    source_role_ids.update(
        str(value).strip()
        for value in cut_plan.get("required_roles") or []
        if str(value).strip()
    )
    visible_role_obligations = {
        "helper": {
            "visible_value_shift",
            "transformation_reveal",
            "story_event_proof",
        },
        "opponent": {"scene_pressure", "audience_context", "story_event_proof"},
        "contrast_or_false_claimant": {"scene_pressure", "audience_context", "story_event_proof"},
        "witness": {"causal_handoff", "symbolic_proof", "reaction_after_change", "story_event_proof"},
        "authority_or_community": {"audience_context", "terminal_resolution", "story_event_proof"},
    }
    obligation_id = str(cut_plan.get("obligation_id") or "").strip()
    source_event_text = " / ".join(source_event_text_parts).lower()
    role_matches = [
        spec
        for spec in scene_candidates
        if any(
            token and token.lower() in source_event_text
            for token in (str(spec.get("source_character_id") or "").strip(), str(spec.get("name") or "").strip())
        )
        and (
            (
                any(
                    candidate in source_role_ids
                    for candidate in (
                        str(spec.get("source_character_id") or "").strip(),
                        str(spec.get("character_id") or "").strip(),
                        str(spec.get("name") or "").strip(),
                    )
                )
                and not (spec.get("role_tags") or [])
            )
            or any(
                role in source_role_ids
                and obligation_id in visible_role_obligations.get(role, set())
                for role in spec.get("role_tags") or []
            )
        )
    ]
    selected_specs = list(dict.fromkeys(id(spec) for spec in [*explicit_matches, *named_matches, *role_matches]))
    selected_by_identity = {
        id(spec): spec for spec in [*explicit_matches, *named_matches, *role_matches]
    }
    selected = [selected_by_identity[identity] for identity in selected_specs]
    for spec in selected:
        name = str(spec.get("name") or "").strip()
        if name and name.lower() not in evidence_text:
            evidence_items.append(
                {
                    "source_field": "resolved_visible_character_role",
                    "must_be_drawn_as": name,
                }
            )
    return list(
        dict.fromkeys(
            str(spec["character_id"])
            for spec in selected
        )
    )


def _supporting_object_ids_for_cut(
    profile: dict[str, Any],
    drawable_evidence: list[dict[str, str]] | None = None,
    *,
    cut_plan: dict[str, Any] | None = None,
    scene_event: dict[str, Any] | None = None,
) -> list[str]:
    """Bind reusable objects grounded in this cut's drawable event."""

    evidence_items = drawable_evidence if isinstance(drawable_evidence, list) else []
    evidence_text = json.dumps(evidence_items, ensure_ascii=False, sort_keys=True).lower()
    plan = cut_plan if isinstance(cut_plan, dict) else {}
    event = scene_event if isinstance(scene_event, dict) else {}
    source_event_beat_ids = {
        str(value).strip()
        for value in [
            plan.get("primary_event_beat_id"),
            *(plan.get("source_event_beat_ids") or []),
        ]
        if str(value).strip()
    }
    source_event_text = " / ".join(
        str(value).strip()
        for beat in event.get("event_sequence") or []
        if isinstance(beat, dict)
        and str(beat.get("beat_id") or "").strip() in source_event_beat_ids
        for value in (
            beat.get("what_happens"),
            (
                beat.get("concrete_event", {}).get("what_happens")
                if isinstance(beat.get("concrete_event"), dict)
                else ""
            ),
        )
        if str(value or "").strip()
    ).lower()
    source_object_is_drawable = str(plan.get("obligation_id") or "").strip() in {
        "transformation_reveal",
        "causal_handoff",
        "spatial_transition",
        "symbolic_proof",
        "story_event_proof",
    }
    selected: list[dict[str, Any]] = []
    for spec in _supporting_object_asset_specs(profile):
        tokens = (
            str(spec.get("object_id") or "").strip(),
            str(spec.get("name") or "").strip(),
        )
        named_in_evidence = any(token and token.lower() in evidence_text for token in tokens)
        named_in_source_event = source_object_is_drawable and any(
            token and token.lower() in source_event_text for token in tokens
        )
        if not (named_in_evidence or named_in_source_event):
            continue
        selected.append(spec)
        name = str(spec.get("name") or "").strip()
        if named_in_source_event and name and name.lower() not in evidence_text:
            evidence_items.append(
                {
                    "source_field": "resolved_visible_object_role",
                    "must_be_drawn_as": name,
                }
            )
    return list(dict.fromkeys(str(spec["object_id"]) for spec in selected))


def _scene_has_supporting_object(profile: dict[str, Any], scene_index: int) -> bool:
    canonical_index = _canonical_scene_index(profile, scene_index)
    return any(
        canonical_index in {int(value) for value in spec.get("scene_indices", [])}
        for spec in _supporting_object_asset_specs(profile)
    )


def _supporting_character_reference(profile: dict[str, Any], character_id: str) -> str:
    for spec in _supporting_character_asset_specs(profile):
        if spec["character_id"] == character_id:
            return str((spec.get("reference_images") or [""])[0])
    return ""


def _character_name_for_asset(profile: dict[str, Any], character_id: str) -> str:
    if character_id == str(profile.get("protagonist_asset_id") or ""):
        return str(profile["protagonist_name"])
    for spec in _supporting_character_asset_specs(profile):
        if str(spec.get("character_id") or "") == character_id:
            return str(spec.get("name") or character_id)
    return character_id


def _character_state_bindings_for_scaffold(
    profile: dict[str, Any], character_ids: list[str]
) -> list[dict[str, Any]]:
    """Bind optional appearance variants to every visible character by identity."""

    specs_by_id = {
        str(spec.get("character_id") or "").strip(): spec
        for spec in _supporting_character_asset_specs(profile)
        if str(spec.get("character_id") or "").strip()
    }
    bindings: list[dict[str, Any]] = []
    for character_id in character_ids:
        spec = specs_by_id.get(str(character_id).strip())
        appearance = (
            spec.get("appearance_continuity")
            if isinstance(spec, dict)
            and isinstance(spec.get("appearance_continuity"), dict)
            else {}
        )
        if not str(appearance.get("costume_state") or "").strip():
            continue
        bindings.append(
            {
                "character_id": str(character_id).strip(),
                "character_name": str(
                    spec.get("identity_name")
                    or spec.get("name")
                    or _character_name_for_asset(profile, character_id)
                ).strip(),
                "appearance_continuity": deepcopy(appearance),
            }
        )
    return bindings


def _character_asset_for_subject(
    profile: dict[str, Any],
    *,
    scene_index: int,
    obligation_id: str,
    subject: str,
    first_frame_asset_overrides: dict[str, str] | None = None,
) -> str:
    """Resolve a cut's focal subject to the matching character anchor."""

    normalized_subject = str(subject or "").strip()
    protagonist_names = {
        str(profile.get("protagonist_name") or "").strip(),
        "protagonist",
    }
    overrides = {
        str(key).strip(): str(value).strip()
        for key, value in (
            first_frame_asset_overrides
            if isinstance(first_frame_asset_overrides, dict)
            else {}
        ).items()
        if str(key).strip() and str(value).strip()
    }
    direct_override = overrides.get(normalized_subject)
    if direct_override:
        return direct_override
    if normalized_subject in protagonist_names:
        protagonist_override = (
            overrides.get(str(profile.get("protagonist_name") or "").strip())
            or overrides.get("protagonist")
        )
        if protagonist_override:
            return protagonist_override
    if not normalized_subject or normalized_subject in protagonist_names:
        return _protagonist_asset_for_cut(profile, scene_index, obligation_id)
    for spec in _supporting_character_asset_specs(profile):
        candidates = {
            str(spec.get("character_id") or "").strip(),
            str(spec.get("source_character_id") or "").strip(),
            str(spec.get("name") or "").strip(),
        }
        if normalized_subject in candidates:
            return str(spec.get("character_id") or "").strip()
    return ""


def _character_reference_for_asset(profile: dict[str, Any], character_id: str) -> str:
    protagonist_ids = {
        str(profile.get("protagonist_asset_id") or ""),
    }
    if character_id in protagonist_ids:
        return _protagonist_reference_for_asset(profile, character_id)
    return _supporting_character_reference(profile, character_id)


def _asset_reference_inputs_for_plan(profile: dict[str, Any], asset_id: str) -> list[str]:
    return []


def _supporting_object_reference(profile: dict[str, Any], object_id: str) -> str:
    for spec in _supporting_object_asset_specs(profile):
        if spec["object_id"] == object_id:
            return str((spec.get("reference_images") or [""])[0])
    return ""


def _object_name_for_asset(profile: dict[str, Any], object_id: str) -> str:
    if object_id == str(profile.get("artifact_asset_id") or ""):
        return str(profile["artifact_name"])
    for spec in _supporting_object_asset_specs(profile):
        if str(spec.get("object_id") or "") == object_id:
            return str(spec.get("name") or object_id)
    return object_id


_MISSING_POLICY_VALUE = object()


def _character_identity_catalog(
    profile: dict[str, Any],
) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Return asset→identity and alias→identities without merging ambiguity."""

    identity_by_asset: dict[str, str] = {}
    identities_by_alias: dict[str, set[str]] = {}

    def register(identity: str, asset_id: str, aliases: set[str]) -> None:
        if not identity or not asset_id:
            return
        identity_by_asset[asset_id] = identity
        for alias in {asset_id, *aliases}:
            normalized_alias = str(alias or "").strip()
            if normalized_alias:
                identities_by_alias.setdefault(normalized_alias, set()).add(identity)

    protagonist_name = str(profile.get("protagonist_name") or "").strip()
    protagonist_ids = {
        str(profile.get("protagonist_asset_id") or "").strip(),
    }
    protagonist_ids.discard("")
    protagonist_identity = (
        f"protagonist:{str(profile.get('protagonist_asset_id') or protagonist_name)}"
    )
    protagonist_aliases = {
        protagonist_name,
        "protagonist",
    }
    for asset_id in protagonist_ids:
        register(protagonist_identity, asset_id, protagonist_aliases)

    for spec in _supporting_character_asset_specs(profile):
        asset_id = str(spec.get("character_id") or "").strip()
        if not asset_id:
            continue
        identity_name = str(spec.get("identity_name") or "").strip()
        if asset_id in protagonist_ids:
            identity = protagonist_identity
        else:
            identity = "supporting:" + str(
                spec.get("source_character_id")
                or identity_name
                or spec.get("name")
                or asset_id
            ).strip()
        register(
            identity,
            asset_id,
            {
                str(spec.get("source_character_id") or "").strip(),
                str(spec.get("name") or "").strip(),
                identity_name,
            },
        )
    return identity_by_asset, identities_by_alias


def _character_identities_in_text(
    profile: dict[str, Any], value: Any
) -> set[str]:
    text = str(value or "").strip()
    if not text:
        return set()
    _identity_by_asset, identities_by_alias = _character_identity_catalog(profile)
    return {
        identity
        for alias, identities in identities_by_alias.items()
        if alias and alias in text
        for identity in identities
    }


def _is_character_body_part_evidence(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return bool(
        re.search(r"(?:手元|手|指先|指|腕|足元|足先|足|踵)", text)
        and not re.search(r"(?:全身|身体|姿|立つ|座る|歩く|走る|を乗せた|と[^、。]+)", text)
    )


def _validate_first_frame_excluded_object_ids(
    profile: dict[str, Any],
    value: Any = _MISSING_POLICY_VALUE,
    *,
    context: str,
) -> list[str]:
    """Validate first-frame object exclusions without accepting unknown assets."""

    if value is _MISSING_POLICY_VALUE:
        return []
    if not isinstance(value, list):
        raise RuntimeError(
            f"{context}: first_frame_excluded_object_ids must be a list"
        )
    known_ids = {
        str(profile.get("artifact_asset_id") or "").strip(),
        *(
            str(spec.get("object_id") or "").strip()
            for spec in _supporting_object_asset_specs(profile)
        ),
    }
    known_ids.discard("")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(
                f"{context}: first_frame_excluded_object_ids must contain "
                "non-blank strings"
            )
        object_id = item.strip()
        if object_id not in known_ids:
            raise RuntimeError(
                f"{context}: unknown object asset id in "
                f"first_frame_excluded_object_ids: {object_id}"
            )
        if object_id not in normalized:
            normalized.append(object_id)
    return normalized


def _validate_first_frame_character_asset_overrides(
    profile: dict[str, Any],
    value: Any = _MISSING_POLICY_VALUE,
    *,
    context: str,
) -> dict[str, str]:
    """Allow overrides only between known variants of the same character."""

    if value is _MISSING_POLICY_VALUE:
        return {}
    if not isinstance(value, dict):
        raise RuntimeError(
            f"{context}: first_frame_character_asset_overrides must be an object"
        )

    identity_by_asset, identities_by_alias = _character_identity_catalog(profile)
    known_ids = set(identity_by_asset)

    normalized: dict[str, str] = {}
    for raw_subject, raw_asset_id in value.items():
        if (
            not isinstance(raw_subject, str)
            or not raw_subject.strip()
            or not isinstance(raw_asset_id, str)
            or not raw_asset_id.strip()
        ):
            raise RuntimeError(
                f"{context}: first_frame_character_asset_overrides must map "
                "non-blank strings to non-blank strings"
            )
        subject = raw_subject.strip()
        asset_id = raw_asset_id.strip()
        if asset_id not in known_ids:
            raise RuntimeError(
                f"{context}: first-frame override must reference a known "
                f"character asset: {asset_id}"
            )
        subject_identities = identities_by_alias.get(subject)
        if not subject_identities:
            raise RuntimeError(
                f"{context}: first-frame override subject is not a known "
                f"character identity: {subject}"
            )
        if len(subject_identities) != 1:
            raise RuntimeError(
                f"{context}: first-frame override subject alias is ambiguous: "
                f"{subject}"
            )
        if identity_by_asset[asset_id] != next(iter(subject_identities)):
            raise RuntimeError(
                f"{context}: first-frame override must stay within the same "
                f"identity: {subject} -> {asset_id}"
            )
        normalized[subject] = asset_id
    return normalized


def _bind_character_reference_pairs(
    *,
    character_ids: list[str],
    references: list[str],
    context: str,
) -> list[tuple[str, str]]:
    """Bind each character reference to its asset id, never by list position."""

    reference_by_character_id: dict[str, str] = {}
    for raw_reference in references:
        reference = str(raw_reference)
        if "/characters/" not in reference:
            continue
        character_id = Path(reference).stem
        if character_id in reference_by_character_id:
            raise RuntimeError(
                f"{context}: duplicate character reference binding for "
                f"{character_id}"
            )
        reference_by_character_id[character_id] = reference

    requested_ids = list(dict.fromkeys(str(item).strip() for item in character_ids))
    if len(requested_ids) != len(character_ids) or any(not item for item in requested_ids):
        raise RuntimeError(f"{context}: character ids must be unique non-blank asset ids")
    if set(reference_by_character_id) != set(requested_ids):
        missing = sorted(set(requested_ids) - set(reference_by_character_id))
        unexpected = sorted(set(reference_by_character_id) - set(requested_ids))
        raise RuntimeError(
            f"{context}: character reference binding id mismatch: "
            f"missing={missing}, unexpected={unexpected}"
        )
    return [
        (character_id, reference_by_character_id[character_id])
        for character_id in requested_ids
    ]


def _first_frame_exclusion_tokens(
    profile: dict[str, Any], excluded_object_ids: list[str]
) -> set[str]:
    return {
        token
        for object_id in excluded_object_ids
        for token in (object_id, _object_name_for_asset(profile, object_id))
        if token
    }


def _sanitize_first_frame_prose(value: Any, *, excluded_tokens: set[str]) -> Any:
    """Remove positive still-image clauses that name an excluded object."""

    if isinstance(value, dict):
        return {
            key: _sanitize_first_frame_prose(item, excluded_tokens=excluded_tokens)
            for key, item in value.items()
        }
    if isinstance(value, list):
        sanitized = [
            _sanitize_first_frame_prose(item, excluded_tokens=excluded_tokens)
            for item in value
        ]
        return [item for item in sanitized if item not in ("", None, [], {})]
    if not isinstance(value, str) or not excluded_tokens:
        return value
    if not any(token in value for token in excluded_tokens):
        return value
    clauses = re.split(r"(?<=[。！？\n])", value)
    kept = [
        clause
        for clause in clauses
        if clause.strip()
        and not any(token in clause for token in excluded_tokens)
    ]
    return "".join(kept).strip()


def _abstract_non_primary_route_locations(
    value: Any,
    *,
    primary_location: str,
    route_locations: list[str],
) -> Any:
    """Keep route provenance exact while removing other location IDs from provider prose."""

    if isinstance(value, dict):
        return {
            key: _abstract_non_primary_route_locations(
                item,
                primary_location=primary_location,
                route_locations=route_locations,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _abstract_non_primary_route_locations(
                item,
                primary_location=primary_location,
                route_locations=route_locations,
            )
            for item in value
        ]
    if not isinstance(value, str):
        return value
    projected = value
    try:
        primary_index = route_locations.index(primary_location)
    except ValueError:
        primary_index = -1
    for location in sorted(route_locations, key=len, reverse=True):
        if (
            not location
            or location == primary_location
        ):
            continue
        try:
            location_index = route_locations.index(location)
        except ValueError:
            location_index = primary_index
        replacement = (
            "次の場所へ続く導線"
            if primary_index >= 0 and location_index > primary_index
            else "前の場所へ続く導線"
            if primary_index >= 0 and location_index < primary_index
            else "画面内で別方向へ続く導線"
        )
        projected = projected.replace(location, replacement)
    return projected


def _validate_exact_obligation_string_list(
    value: Any = _MISSING_POLICY_VALUE,
    *,
    field_name: str,
    context: str,
) -> list[str]:
    if value is _MISSING_POLICY_VALUE:
        return []
    if not isinstance(value, list):
        raise RuntimeError(f"{context}: {field_name} must be a list")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(
                f"{context}: {field_name} must contain non-blank strings"
            )
        if item.strip() not in normalized:
            normalized.append(item.strip())
    return normalized


def _drawable_forbidden_reveal_names_for_scaffold(
    profile: dict[str, Any], raw_values: Any
) -> list[str]:
    """Resolve reveal keys to known drawable asset display names only.

    Reveal contracts may contain opaque IDs or abstract information such as a
    deadline's consequence.  Provider-facing still prompts must only name a
    concrete character/object when that value resolves exactly to an asset
    known by this story profile.  Resolution never activates the asset as a
    drawable dependency or reference; it only supplies an inline prohibition.
    """

    aliases_to_names: dict[str, str] = {}

    def register(display_name: Any, *aliases: Any) -> None:
        display = str(display_name or "").strip()
        if not display:
            return
        for raw_alias in (display, *aliases):
            if isinstance(raw_alias, (list, tuple, set)):
                for nested_alias in raw_alias:
                    register(display, nested_alias)
                continue
            alias = str(raw_alias or "").strip()
            if alias:
                aliases_to_names.setdefault(alias.casefold(), display)

    protagonist_name = str(profile.get("protagonist_name") or "").strip()
    register(
        protagonist_name,
        profile.get("protagonist_asset_id"),
        profile.get("protagonist_aliases") or [],
    )
    register(
        profile.get("artifact_name"),
        profile.get("artifact_asset_id"),
        profile.get("artifact_aliases") or [],
    )
    for spec in _supporting_character_asset_specs(profile):
        register(
            spec.get("name"),
            spec.get("character_id"),
            spec.get("source_character_id"),
            spec.get("aliases") or [],
            spec.get("review_aliases") or [],
        )
    for spec in _supporting_object_asset_specs(profile):
        register(
            spec.get("name"),
            spec.get("object_id"),
            spec.get("source_object_id"),
            spec.get("aliases") or [],
            spec.get("review_aliases") or [],
        )

    values = raw_values if isinstance(raw_values, (list, tuple, set)) else [raw_values]
    resolved: list[str] = []
    for value in values:
        name = aliases_to_names.get(str(value or "").strip().casefold(), "")
        if name and name not in resolved:
            resolved.append(name)
    return resolved


def _artifact_scene_role(profile: dict[str, Any], scene_index: int) -> str:
    return profile["artifact_role"]


def _cut_uses_artifact(profile: dict[str, Any], scene_index: int, obligation_id: str, *, include_artifact: bool) -> bool:
    return include_artifact


def _prompt_for_asset(entry: dict[str, Any], profile: dict[str, Any]) -> str:
    return compile_asset_prompt(
        entry,
        topic_label=str(profile.get("topic_label") or profile.get("topic") or "物語"),
        story_time=str(profile.get("story_time") or ""),
    )






def _visible_behavior_from_cut(
    *,
    profile: dict[str, Any],
    cut_plan: dict[str, Any],
    cut_blueprint: dict[str, Any],
    location_name: str,
    object_ids: list[str],
    focal_character_name: str = "",
) -> dict[str, str]:
    evidence = str(cut_blueprint.get("visual_beat") or cut_blueprint.get("first_frame_brief") or "").strip()
    cut_function = str(cut_blueprint.get("cut_function") or "").strip()
    action_completion_state = str(
        cut_blueprint.get("action_completion_state") or ""
    ).strip()
    is_payoff = cut_function == "payoff" or cut_function.startswith("payoff_")
    is_handoff = cut_function == "handoff" or (
        action_completion_state == "handoff_state" and not is_payoff
    )
    focal_name = str(focal_character_name or profile["protagonist_name"]).strip()
    if profile.get("artifact_asset_id") in object_ids:
        object_focus = profile["artifact_name"]
    elif object_ids:
        object_focus = _object_name_for_asset(profile, object_ids[0])
    elif is_handoff:
        object_focus = _drawable_phrase_for_scaffold(
            cut_plan.get("foreground")
        ) or "画面奥の出入口へ続く具体的な導線"
    elif is_payoff:
        object_focus = _drawable_phrase_for_scaffold(
            cut_plan.get("foreground")
        ) or "前景に残る具体的な証拠"
    elif cut_function == "pressure":
        object_focus = str(cut_plan.get("foreground") or "出入口を狭める具体物")
    else:
        object_focus = "手元に差す光と画面内の出入口"
    face = "声に出さず、圧力を受け止めている表情"
    gaze = f"{object_focus}へ向く視線"
    hands = f"{focal_name}の手元が行為直前の位置にあり、緊張が読める"
    feet = "足先と重心が画面内の出入口へ向き、動き出す直前で止まっている"
    if is_handoff:
        face = "口元を閉じ、画面奥の出入口へ視線を定めた表情"
        gaze = "前景に残る痕跡から画面奥の出入口へ向く視線"
        hands = (
            f"{focal_name}の手は前景に残る痕跡のそばで止まり、"
            "指を伸ばし切らず、直前の動きが終わった位置にある"
        )
        feet = "足先と重心は画面奥の出入口側へ移り、両足は行動後の位置で止まっている"
    elif is_payoff:
        face = "肩と眉の緊張がほどけ、口元を閉じたまま安堵が読める表情"
        gaze = f"{object_focus}へ静かに下ろした視線"
        hands = (
            f"{focal_name}の手は{object_focus}のそばで止まり、"
            "指を伸ばし切らず、直前の動きが終わった位置にある"
        )
        feet = "両足は前景に残る痕跡のそばで止まり、重心は安定している"
    projected_state = (
        cut_plan.get("visible_character_state")
        if isinstance(cut_plan.get("visible_character_state"), dict)
        else {}
    )
    carried_posture = _drawable_phrase_for_scaffold(projected_state.get("posture"))
    if (
        cut_plan.get("first_frame_carried_from_previous_end")
        and not projected_state.get("feet")
        and any(term in carried_posture for term in ("足", "踵", "重心", "段"))
    ):
        feet = carried_posture
    return {
        "face": str(projected_state.get("expression") or face),
        "gaze": str(projected_state.get("gaze") or gaze),
        "posture": str(
            projected_state.get("posture")
            or cut_blueprint.get("first_frame_brief")
            or "行為が始まる直前の姿勢"
        ),
        "hands": str(projected_state.get("hands") or hands),
        "feet": str(projected_state.get("feet") or feet),
        "distance": f"{location_name}の中で、人物と{object_focus}の距離が読める",
        "visible_proof": evidence,
        "screen_direction": str(cut_plan.get("screen_direction") or "次へ進む方向"),
    }


def _scene_character_state_timeline_for_scaffold(
    *,
    scene_id: int,
    scene_event: dict[str, Any],
    scene_intent: dict[str, Any],
    profile: dict[str, Any],
    location_name: str,
    major_character_ids: list[str],
) -> dict[str, Any]:
    sequence = [beat for beat in scene_event.get("event_sequence", []) if isinstance(beat, dict)]
    protagonist_identity_id = str(profile["protagonist_asset_id"])
    supporting_specs_by_id = {
        str(spec.get("character_id") or ""): spec
        for spec in _supporting_character_asset_specs(profile)
        if str(spec.get("source_character_id") or "")
    }

    def character_role_id(character_id: str) -> str:
        if character_id == protagonist_identity_id:
            return "protagonist"
        return str(
            supporting_specs_by_id.get(character_id, {}).get(
                "source_character_id", ""
            )
        )

    def participates(character_id: str, beat: dict[str, Any]) -> bool:
        role_id = character_role_id(character_id)
        required_roles = {
            str(role)
            for role in beat.get("required_roles", [])
            if str(role).strip()
        }
        if role_id and role_id in required_roles:
            return True
        character_name = _character_name_for_asset(profile, character_id)
        primary_subject = str(
            beat.get("primary_subject")
            or (
                beat.get("concrete_event", {}).get("primary_subject")
                if isinstance(beat.get("concrete_event"), dict)
                else ""
            )
            or ""
        )
        return primary_subject in {
            character_id,
            character_name,
            role_id,
        }

    def event_body_state(
        beat: dict[str, Any],
        *,
        character_name: str,
        is_primary: bool,
    ) -> str:
        visible_action = str(beat.get("visible_action") or "").strip()
        visible_reaction = str(beat.get("visible_reaction") or "").strip()
        what_happens = str(beat.get("what_happens") or "").strip()
        beat_primary_subject = str(
            beat.get("primary_subject")
            or (
                beat.get("concrete_event", {}).get("primary_subject")
                if isinstance(beat.get("concrete_event"), dict)
                else ""
            )
            or ""
        )
        is_beat_primary = beat_primary_subject in {
            character_name,
            "protagonist" if is_primary else "",
        }

        def named_clause(value: str) -> str:
            clauses = [
                clause.strip(" 、。")
                for clause in re.split(r"[。；]|、(?=[^、。]{0,28}(?:は|が))", value)
                if clause.strip(" 、。")
            ]
            return next(
                (clause for clause in clauses if character_name in clause),
                "",
            )

        if is_beat_primary:
            own_action = (
                named_clause(visible_action)
                or named_clause(visible_reaction)
            )
            return (
                f"{character_name}自身の行動: {own_action}"
                if own_action
                else f"{character_name}自身が{what_happens}を実行する"
            )
        own_reaction = (
            named_clause(visible_reaction)
            or named_clause(visible_action)
        )
        if own_reaction:
            return f"{character_name}自身の反応: {own_reaction}"
        return (
            f"{character_name}自身の反応: {what_happens}を受け、"
            f"{beat_primary_subject or '出来事の主体'}との距離、視線、手元を"
            "出来事直後の位置へ変える"
        )

    def event_gaze_target(
        beat: dict[str, Any],
        *,
        character_name: str,
        is_primary: bool,
    ) -> str:
        visible_reaction = str(beat.get("visible_reaction") or "").strip()
        if is_primary:
            return visible_reaction or "圧力源または導線"
        return (
            f"{character_name}自身の視線が、"
            f"{str(beat.get('primary_subject') or '出来事の主体')}の行動結果へ向く"
        )

    def visible_proof(
        beat: dict[str, Any],
        *,
        phase: str,
        character_name: str,
        is_primary: bool,
    ) -> dict[str, str]:
        evidence = " / ".join(str(item) for item in beat.get("required_visual_evidence", []) if str(item).strip()) if isinstance(beat.get("required_visual_evidence"), list) else ""
        return {
            "face": f"{character_name}の{phase}の反応が声に出さず顔に残る表情",
            "gaze": event_gaze_target(
                beat,
                character_name=character_name,
                is_primary=is_primary,
            ),
            "posture": event_body_state(
                beat,
                character_name=character_name,
                is_primary=is_primary,
            ),
            "hands": f"{character_name}自身の手元に出来事直後の緊張または選択が見える",
            "feet": f"{character_name}自身の足先と重心が出来事直後の位置にある",
            "distance": f"{location_name}内で人物と圧力源の距離が読める",
            "visible_proof": evidence or str(beat.get("what_happens") or scene_intent.get("dramatic_question") or ""),
        }

    raw_character_ids = [
        character_id
        for character_id in major_character_ids
        if str(character_id).strip()
    ]
    character_ids = list(dict.fromkeys(raw_character_ids))
    if not character_ids:
        character_ids = [str(profile["protagonist_asset_id"])]

    characters = []
    for character_id in character_ids:
        character_name = _character_name_for_asset(profile, character_id)
        is_primary = character_id == character_ids[0]
        character_sequence = sequence
        start_beat = character_sequence[0] if character_sequence else {}
        midpoint_beat = next(
            (
                beat
                for beat in character_sequence
                if str(beat.get("beat_function") or "") == "turn"
            ),
            character_sequence[len(character_sequence) // 2]
            if character_sequence
            else {},
        )
        end_beat = next(
            (
                beat
                for beat in character_sequence
                if str(beat.get("beat_function") or "") == "payoff"
            ),
            character_sequence[-1] if character_sequence else {},
        )
        start_beat_id = str(start_beat.get("beat_id") or "")
        midpoint_beat_id = str(midpoint_beat.get("beat_id") or "")
        end_beat_id = str(end_beat.get("beat_id") or "")
        scene_role = "protagonist" if is_primary else "supporting_major_character"
        characters.append(
            {
                "character_id": character_id,
                "character_name": character_name,
                "scene_role": scene_role,
                "objective_in_scene": str(scene_intent.get("dramatic_question") or "sceneの問いに身体で答える") if is_primary else "主人公の変化を受け取り、関係性の圧力や反応を画面に出す",
                "emotional_arc_summary": f"{scene_intent.get('value_shift', {}).get('from', '圧力を受ける状態')}から{scene_intent.get('value_shift', {}).get('to', '次へ進む状態')}へ移る" if is_primary else "主人公の行為や証拠を受け、距離、視線、身体の向きが変わる",
                "start_state": {
                    "trigger_event_beat_id": start_beat_id,
                    "emotion": str(start_beat.get("emotional_pressure") or "圧力を受けている"),
                    "desire": "前へ進みたいが、まだ確信しきっていない" if is_primary else "状況を見極めようとしている",
                    "fear_or_pressure": str(start_beat.get("what_happens") or scene_event.get("start_situation") or ""),
                    "belief": str(scene_intent.get("value_shift", {}).get("from") or "まだ状況に縛られている"),
                    "relationship_to_others": "周囲の圧力や証人との距離が画面に残る",
                    "body_state": event_body_state(start_beat, character_name=character_name, is_primary=is_primary),
                    "gaze_target": event_gaze_target(start_beat, character_name=character_name, is_primary=is_primary),
                    "visible_proof": visible_proof(start_beat, phase="start", character_name=character_name, is_primary=is_primary),
                },
                "midpoint_state": {
                    "trigger_event_beat_id": midpoint_beat_id,
                    "emotion": str(midpoint_beat.get("emotional_pressure") or "選択が身体に出始める"),
                    "desire_shift": "迷いよりも行為が前に出る" if is_primary else "相手の変化を受け取り、視線や距離が変わる",
                    "fear_or_pressure_shift": str(midpoint_beat.get("immediate_consequence") or "後戻りできない圧力が増す"),
                    "belief_shift": str(scene_intent.get("causal_turn") or "状況を受けるだけでなく動かす側へ移る"),
                    "relationship_shift": "他者または場所との力関係が画面配置で変わる",
                    "body_state": event_body_state(midpoint_beat, character_name=character_name, is_primary=is_primary),
                    "gaze_target": event_gaze_target(midpoint_beat, character_name=character_name, is_primary=is_primary),
                    "visible_proof": visible_proof(midpoint_beat, phase="midpoint", character_name=character_name, is_primary=is_primary),
                },
                "end_state": {
                    "trigger_event_beat_id": end_beat_id,
                    "emotion": str(end_beat.get("emotional_pressure") or "次へ渡る感情が残る"),
                    "new_desire": "次のsceneへ進む理由を持つ" if is_primary else "新しい関係性の距離を受け入れる、または拒む",
                    "unresolved_pressure": str(scene_event.get("end_situation", {}).get("new_pressure") or "次の圧力が残る") if isinstance(scene_event.get("end_situation"), dict) else "次の圧力が残る",
                    "belief_after_scene": str(scene_intent.get("value_shift", {}).get("to") or "一段変化した状態"),
                    "relationship_after_scene": str(scene_event.get("end_situation", {}).get("relationship_state") or "関係性が次へ渡る") if isinstance(scene_event.get("end_situation"), dict) else "関係性が次へ渡る",
                    "body_state": event_body_state(end_beat, character_name=character_name, is_primary=is_primary),
                    "gaze_target": event_gaze_target(end_beat, character_name=character_name, is_primary=is_primary),
                    "visible_proof": visible_proof(end_beat, phase="end", character_name=character_name, is_primary=is_primary),
                },
                "emotional_no_return_point": {
                    "event_beat_id": midpoint_beat_id,
                    "description": str(scene_intent.get("causal_turn") or "このsceneの感情が戻れない方向へ動く"),
                    "visible_behavior": event_body_state(midpoint_beat, character_name=character_name, is_primary=is_primary),
                },
            }
        )

    return {
        "policy_version": "character_emotion_continuity_v1",
        "source_schema_version": "scene_event_v1",
        "scene_id": scene_id,
        "linked_scene_event_beat_ids": [str(beat.get("beat_id") or "") for beat in sequence if str(beat.get("beat_id") or "").strip()],
        "characters": characters,
    }


def _scene_film_coverage_plan_for_scaffold(
    *,
    scene_id: int,
    scene_event: dict[str, Any],
    cut_plans: list[dict[str, Any]],
    scene_character_state_timeline: dict[str, Any],
    has_important_object: bool,
) -> dict[str, Any]:
    selectors = [f"scene{scene_id}_cut{index:02d}" for index, _ in enumerate(cut_plans, start=1)]
    function_to_selectors: dict[str, list[str]] = {}
    for selector, cut_plan in zip(selectors, cut_plans):
        function_to_selectors.setdefault(str(cut_plan.get("cut_function") or "custom"), []).append(selector)
    action_reaction_pairs = []
    for index, beat in enumerate([beat for beat in scene_event.get("event_sequence", []) if isinstance(beat, dict)], start=1):
        function = str(beat.get("beat_function") or "")
        if function not in {"turn", "payoff"}:
            continue
        action_selector = selectors[min(index - 1, len(selectors) - 1)] if selectors else ""
        reaction_selector = selectors[min(index, len(selectors) - 1)] if selectors else action_selector
        action_reaction_pairs.append(
            {
                "source_event_beat_id": str(beat.get("beat_id") or ""),
                "action_cut_selector": action_selector,
                "reaction_cut_selector": reaction_selector,
                "meaning_created_by_pair": str(beat.get("visible_reaction") or beat.get("immediate_consequence") or ""),
            }
        )
    required_when_rules = {
        "reaction": "turn / reveal / payoff の event beat が scene_event にある場合、出来事を受け取る人物または場の反応を cut_film_grammar_contract.conditional_modules.character_reaction_contract に持つ",
        "insert": "重要小道具、証拠、身体部位、期限の合図が scene_event.required_visual_evidence にある場合、insert または object_proof の coverage を要求する",
        "eyeline": "人物が何かを認識、拒否、探す、受け取る場合、attention_state と eyeline_continuity で視線の渡し先を明示する",
        "silence": "感情転換、reveal、no_return_point は narration で説明しすぎず、silence_and_pause_contract に読ませる感情を持つ",
    }
    insert_selectors = (
        function_to_selectors.get("symbolic_proof", [])
        + function_to_selectors.get("object_proof", [])
        + function_to_selectors.get("proof", [])
    )
    if has_important_object and not insert_selectors and selectors:
        insert_selectors = selectors[min(1, len(selectors) - 1) : min(2, len(selectors))]
    coverage_modules = {
        "establishing": function_to_selectors.get("setup", selectors[:1]),
        "action": [
            selector
            for function, values in function_to_selectors.items()
            for selector in values
            if function not in {"reaction", "handoff"}
        ],
        "insert": insert_selectors,
        "reaction": function_to_selectors.get("reaction", []) + function_to_selectors.get("reaction_after_change", []),
        "handoff": function_to_selectors.get("handoff", selectors[-1:]),
    }
    return {
        "policy_version": "scene_film_coverage_v1",
        "source": ["scene_event", "scene_character_state_timeline", "scene_cut_coverage_plan"],
        "scene_id": scene_id,
        "shot_mix": {
            "required_coverage": coverage_modules,
            "actual_shots": [],
            "missing_coverage": [],
        },
        "action_reaction_pair": action_reaction_pairs,
        "missing_coverage": [],
        "required_when_rules": required_when_rules,
        "audience_emotion_target": {
            "separate_from_character_emotion": True,
            "intended_audience_feeling": "人物の内面ラベルではなく、反応、距離、視線、沈黙から意味を受け取る",
            "achieved_by": ["character_reaction", "shot_scale", "silence", "object_reveal", "lighting"],
        },
        "character_timeline_ref": "scene_character_state_timeline",
        "character_count": len(scene_character_state_timeline.get("characters", [])) if isinstance(scene_character_state_timeline.get("characters"), list) else 0,
    }


def _scene_state_progression_plan_for_scaffold(
    *,
    scene_id: int,
    title: str,
    scene_intent: dict[str, Any],
    scene_event: dict[str, Any],
    cut_plans: list[dict[str, Any]],
    location_name: str,
) -> dict[str, Any]:
    selectors = [f"scene{scene_id}_cut{index:02d}" for index, _ in enumerate(cut_plans, start=1)]
    joined = " / ".join(
        [
            title,
            location_name,
            str(scene_intent.get("causal_turn") or ""),
            str(scene_intent.get("handoff_to_next_scene") or ""),
            str(scene_intent.get("terminal_resolution") or ""),
            " / ".join(str(item) for item in scene_intent.get("audience_information", []) if str(item).strip()),
            " / ".join(str(item) for item in (scene_intent.get("value_shift", {}) or {}).get("visible_evidence", []) if str(item).strip()) if isinstance(scene_intent.get("value_shift"), dict) else "",
            " / ".join(
                " / ".join(str(plan.get(key) or "") for key in ("obligation_id", "cut_function", "target_beat", "visual_proof", "first_frame_brief", "motion_end_state"))
                for plan in cut_plans
            ),
        ]
    )
    sequential_keywords = (
        "移動",
        "出発",
        "向かう",
        "越",
        "入口",
        "出口",
        "道",
        "乗",
        "逃",
        "走",
        "追",
        "階段",
        "進む",
        "運ぶ",
        "渡る",
        "変身",
        "現れる",
        "探",
        "巡",
    )
    progression_mode = "sequential_state_progression" if any(keyword in joined for keyword in sequential_keywords) else "suspended_moment"
    mode_reason = (
        "scene内で場所、身体、小道具の状態が前cutの結果を受けて前進するため、各cutのfirst frameは開始前に戻さない"
        if progression_mode == "sequential_state_progression"
        else "sceneの品質は未完了の1フレームで圧力や余白を保つ方が高いため、各cutは行為直前または途中の緊張を保持する"
    )

    event_sequence = [beat for beat in scene_event.get("event_sequence", []) if isinstance(beat, dict)]
    event_index_by_id = {
        str(beat.get("beat_id") or "").strip(): index
        for index, beat in enumerate(event_sequence)
        if str(beat.get("beat_id") or "").strip()
    }

    def future_event_beat_ids(source_event_beat_ids: list[str]) -> list[str]:
        if not source_event_beat_ids:
            return []
        source_indexes = [event_index_by_id[beat_id] for beat_id in source_event_beat_ids if beat_id in event_index_by_id]
        if not source_indexes:
            return []
        max_index = max(source_indexes)
        return [
            str(beat.get("beat_id") or "")
            for index, beat in enumerate(event_sequence)
            if index > max_index and str(beat.get("beat_function") or "") in {"turn", "payoff"}
        ]

    cut_progression_map: list[dict[str, Any]] = []
    scene_start_state = str(cut_plans[0].get("first_frame_brief") or title) if cut_plans else title
    for index, (selector, cut_plan) in enumerate(zip(selectors, cut_plans), start=1):
        previous_plan = cut_plans[index - 2] if index > 1 else {}
        next_plan = cut_plans[index] if index < len(cut_plans) else {}
        state_after_previous_cut = (
            str(previous_plan.get("motion_end_state") or previous_plan.get("visual_proof") or "")
            if index > 1
            else "scene開始時点"
        )
        state_visible = str(cut_plan.get("first_frame_brief") or cut_plan.get("visual_proof") or cut_plan.get("target_beat") or "")
        visible_delta = (
            f"前cutの「{state_after_previous_cut}」から、このcutでは「{state_visible}」へ進む"
            if index > 1
            else "scene開始の状態を提示する"
        )
        action_completion_state = "pre_action"
        if progression_mode == "sequential_state_progression":
            if index == 1:
                action_completion_state = "scene_start_state"
            elif index == len(cut_plans):
                action_completion_state = "handoff_state"
            else:
                action_completion_state = "progressed_state"
        elif index > 1:
            action_completion_state = "early_action"
        source_event_beat_ids = [str(item) for item in cut_plan.get("source_event_beat_ids", []) if str(item).strip()]
        cut_progression_map.append(
            {
                "cut_selector": selector,
                "source_event_beat_ids": source_event_beat_ids,
                "progression_position": str(cut_plan.get("cut_function") or "custom"),
                "progression_mode": progression_mode,
                "first_frame_temporal_role": "progressed_state_after_previous_cut" if progression_mode == "sequential_state_progression" and index > 1 else "suspended_before_or_during_cut_event",
                "state_after_previous_cut": state_after_previous_cut,
                "state_visible_in_this_cut": state_visible,
                "visible_state_delta_from_previous_cut": visible_delta,
                "action_completion_state": action_completion_state,
                "must_not_revert_to": scene_start_state if progression_mode == "sequential_state_progression" and index > 1 else "",
                "must_not_advance_beyond": str(next_plan.get("first_frame_brief") or scene_intent.get("handoff_to_next_scene") or scene_intent.get("terminal_resolution") or "次sceneの結果"),
                "forbidden_future_event_beat_ids": future_event_beat_ids(source_event_beat_ids),
                "done_when": [
                    "前cutから進んだ状態が静止画で読める" if progression_mode == "sequential_state_progression" and index > 1 else "未完了の1フレームとして圧力と動き出しの余地が読める"
                ],
            }
        )
    return {
        "policy_version": "scene_state_progression_v1",
        "source": ["scene_event", "scene_cut_coverage_plan"],
        "scene_id": scene_id,
        "progression_mode": progression_mode,
        "mode_reason": mode_reason,
        "scene_progression_goal": str(scene_intent.get("causal_turn") or scene_intent.get("dramatic_question") or title),
        "starts_at": scene_start_state,
        "ends_at": str(scene_event.get("end_situation", {}).get("outcome") or scene_intent.get("value_shift", {}).get("to") or "") if isinstance(scene_event.get("end_situation"), dict) else "",
        "cut_progression_map": cut_progression_map,
        "gate_requirements": [
            "scene_state_progression_plan_exists",
            "sequential_scene_cuts_do_not_revert_to_scene_start",
            "suspended_moment_scenes_keep_unfinished_first_frame",
            "cut_state_progression_exists",
        ],
    }


def _cut_character_emotion_transition_for_scaffold(
    *,
    profile: dict[str, Any],
    cut_blueprint: dict[str, Any],
    primary_event_beat: dict[str, Any],
    primary_event_beat_id: str,
    visible_behavior: dict[str, str],
    focal_character_id: str,
    supporting_character_ids: list[str],
    cut_number: int,
    cut_count: int,
) -> dict[str, Any]:
    function = str(primary_event_beat.get("beat_function") or cut_blueprint.get("cut_function") or "")
    transition_mode = {
        "setup": "hold_pressure",
        "pressure": "pressure_to_visible_choice",
        "turn": "triggered_shift",
        "payoff": "consequence_to_handoff",
    }.get(function, "visible_micro_shift")
    return {
        "policy_version": "cut_character_emotion_transition_v1",
        "focal_character_id": focal_character_id,
        "supporting_character_ids": supporting_character_ids,
        "transition_mode": transition_mode,
        "emotion_from": {
            "label": "未完了の圧力",
            "visible_behavior": visible_behavior,
        },
        "emotion_to": {
            "label": "次の行為へ寄る状態" if cut_number < cut_count else "次sceneへ渡る余韻",
            "visible_behavior": visible_behavior,
        },
        "transition_trigger": {
            "source_event_beat_id": primary_event_beat_id,
            "what_causes_shift": str(primary_event_beat.get("what_happens") or cut_blueprint.get("target_beat") or ""),
            "visible_cause": str(primary_event_beat.get("visible_action") or cut_blueprint.get("visual_beat") or ""),
        },
        "transition_visible_in_cut": {
            "face_change": visible_behavior["face"],
            "gaze_change": visible_behavior["gaze"],
            "posture_change": visible_behavior["posture"],
            "hand_change": visible_behavior["hands"],
            "foot_change": visible_behavior["feet"],
            "distance_change": visible_behavior["distance"],
            "silence_or_pause": "説明ではなく、息を止めた間で感情を読ませる",
        },
        "emotional_delta_visible_in_first_frame": "感情は完了しきらず、視線、姿勢、手足の緊張として始まる",
        "emotional_delta_completed_by_motion": "動画内で視線または身体が一段だけ変化する",
        "must_not_jump_to_final_emotion": True,
    }


def _cut_film_grammar_contract_for_scaffold(
    *,
    selector: str,
    profile: dict[str, Any],
    location_name: str,
    cut_number: int,
    cut_count: int,
    cut_plan: dict[str, Any],
    cut_blueprint: dict[str, Any],
    primary_event_beat: dict[str, Any],
    primary_event_beat_id: str,
    source_event_beat_ids: list[str],
    object_ids: list[str],
    visible_behavior: dict[str, str],
    focal_character_id: str,
    supporting_character_ids: list[str],
) -> dict[str, Any]:
    next_selector = re.sub(r"cut\d+$", f"cut{cut_number + 1:02d}", selector) if cut_number < cut_count else ""
    previous_selector = re.sub(r"cut\d+$", f"cut{cut_number - 1:02d}", selector) if cut_number > 1 else ""
    function = str(primary_event_beat.get("beat_function") or cut_blueprint.get("cut_function") or "")
    reaction_required = function in {"turn", "payoff"} or bool(primary_event_beat.get("story_information_revealed_ids"))
    object_name = _object_name_for_asset(profile, object_ids[0]) if object_ids else ""
    object_contact_state = "reaching_toward" if object_ids else "not_visible"
    object_story_meaning = object_name or "場所と身体が証拠になる"
    return {
        "policy_version": "cut_film_grammar_v1",
        "required_modules": {
            "character_objective_and_tactic": {
                "character_id": focal_character_id,
                "objective": str(cut_blueprint.get("screen_question") or "sceneの問いに身体で答える"),
                "tactic": str(primary_event_beat.get("visible_action") or cut_blueprint.get("visual_beat") or ""),
                "obstacle": str(primary_event_beat.get("emotional_pressure") or "sceneの圧力"),
                "tactic_shift_after_event": str(primary_event_beat.get("immediate_consequence") or "次の行為へ寄る"),
                "visible_action": str(primary_event_beat.get("visible_action") or cut_blueprint.get("visual_beat") or ""),
            },
            "attention_state": {
                "character_id": focal_character_id,
                "gaze_target": visible_behavior["gaze"],
                "attention_type": "recognizing" if reaction_required else "searching",
                "viewer_attention_target": object_name or visible_behavior["visible_proof"],
                "eyeline_match_to_next_cut": next_selector,
            },
            "eyeline_continuity": {
                "cut_selector": selector,
                "character_id": focal_character_id,
                "gaze_target": visible_behavior["gaze"],
                "next_cut_should_show_target": bool(next_selector),
                "previous_cut_gaze_source": previous_selector,
                "eyeline_match_valid": True,
            },
            "screen_direction_continuity": {
                "movement_direction": str(cut_plan.get("screen_direction") or "static"),
                "previous_direction": "scene_incoming" if cut_number == 1 else "前cutの導線を受ける",
                "direction_change_motivated": True,
                "motivation": str(cut_blueprint.get("dramatic_job") or "観客の注意を次の証拠へ移す"),
            },
            "edit_motivation": {
                "cut_selector": selector,
                "cut_reason": "reaction" if reaction_required else "new_information",
                "why_previous_cut_is_complete": "前cutの視覚証拠が読め、次の視線または行為へ渡せる",
                "why_current_cut_is_needed": str(cut_blueprint.get("dramatic_job") or cut_blueprint.get("visual_beat") or ""),
                "viewer_attention_shift": visible_behavior["gaze"],
            },
            "audience_emotion_target": {
                "cut_selector": selector,
                "separate_from_character_emotion": True,
                "intended_audience_feeling": "人物の内面名ではなく、視線、距離、手足、小道具接触から圧力を感じる",
                "achieved_by": ["character_reaction", "shot_scale", "silence", "object_reveal" if object_ids else "lighting"],
            },
        },
        "conditional_modules": {
            "character_reaction_contract": {
                "required": reaction_required,
                "required_when": "turn / reveal / payoff の event beat を担当するcut",
                "reacts_to_event_beat_id": primary_event_beat_id,
                "reacting_character_id": focal_character_id,
                "reaction_type": "resolve" if function == "payoff" else "recognition" if function == "turn" else "held",
                "visible_reaction": {
                    "eyes": visible_behavior["gaze"],
                    "mouth": "声に出さない緊張が残る",
                    "head": "証拠または導線へわずかに向く",
                    "shoulders": "圧力を受けた硬さが残る",
                    "hands": visible_behavior["hands"],
                    "body_distance": visible_behavior["distance"],
                },
                "reaction_duration_intent": "held",
                "should_be_silent": reaction_required,
                "narration_should_not_explain": True,
            },
            "relationship_state_delta": {
                "required": bool(cut_blueprint.get("required_roles")),
                "relationship_id": f"{selector}_primary_relationship",
                "characters": [focal_character_id, *supporting_character_ids, *[str(role) for role in cut_blueprint.get("required_roles", [])]],
                "from_state": "圧力または距離が残る",
                "to_state": "視線、距離、配置が一段変わる",
                "trigger_event_beat_id": primary_event_beat_id,
                "visible_evidence": {
                    "distance": visible_behavior["distance"],
                    "gaze": visible_behavior["gaze"],
                    "body_orientation": visible_behavior["posture"],
                    "touch_or_non_touch": "接触状態が読める" if object_ids else "非接触の状態",
                    "hierarchy_in_frame": "人物、小道具、場所の優先順位が読める",
                },
                "must_not_resolve_yet": [],
            },
            "prop_state_progression": {
                "required": bool(object_ids),
                "object_id": object_ids[0] if object_ids else "",
                "source_event_beat_ids": source_event_beat_ids,
                "state_by_cut": [
                    {
                        "cut_selector": selector,
                        "visibility": "foreground" if object_ids else "not_visible",
                        "contact_state": object_contact_state,
                        "screen_position": "foreground",
                        "story_meaning": object_story_meaning,
                        "next_state_requirement": "同じ形状と位置関係を保って次cutへ渡す",
                    }
                ],
            },
            "costume_and_body_continuity": {
                "required": True,
                "character_id": focal_character_id,
                "costume_state": "参照人物の衣装状態を維持する",
                "hair_state": "参照人物の髪型を維持する",
                "dirt_or_damage_state": "scene内の汚れや質感を急に変えない",
                "posture_state": visible_behavior["posture"],
                "allowed_changes_in_this_cut": ["視線", "手元", "足先", "距離"],
                "forbidden_changes_in_this_cut": ["別衣装への急変", "別人物化", "後続revealの先取り"],
            },
            "silence_and_pause_contract": {
                "required": reaction_required,
                "cut_selector": selector,
                "silence_required": reaction_required,
                "pause_reason": "感情転換やrevealを説明せず、反応で読ませる",
                "emotion_to_read_in_silence": "視線、手、足、距離の変化",
                "narration_must_not_explain": True,
            },
        },
        "required_when_rules": {
            "reaction": "turn / reveal / payoff の event beat では required",
            "insert": "小道具または身体部位が scene_event.required_visual_evidence の中心なら required",
            "eyeline": "認識、拒否、探索、handoff を担う cut では required",
            "silence": "感情転換、reveal、no_return_point を担う cut では required",
        },
    }


def _image_api_prompt_payload_for_scaffold(
    *,
    first_frame_visual_plan: dict[str, Any],
    character_ids: list[str],
    object_ids: list[str],
    location_ids: list[str],
    references: list[str],
    story_time: str = "",
    scene_time_of_day: str = "",
) -> dict[str, Any]:
    """Compile only drawable first-frame information into the provider payload."""

    return compile_image_api_prompt_v2(
        first_frame_visual_plan=first_frame_visual_plan,
        character_ids=character_ids,
        object_ids=object_ids,
        location_ids=location_ids,
        reference_images=references,
        story_time=story_time,
        scene_time_of_day=scene_time_of_day,
    )


def _scaffold_shot_design(
    *,
    cut_number: int,
    cut_blueprint: dict[str, Any],
    cut_uses_artifact: bool,
    object_ids: list[str],
) -> dict[str, Any]:
    cut_function = str(cut_blueprint.get("cut_function") or "")
    if cut_uses_artifact:
        if len(object_ids) > 1 or cut_function in {"handoff", "payoff"}:
            # Multi-prop proof, handoff, and payoff shots need enough depth to
            # keep the object, acting character, and witnesses or destination
            # legible together.  An extreme insert makes that composition
            # impossible even when the proof object is the primary subject.
            shot_role, shot_scale = "object_proof", "medium_wide"
        elif cut_number % 3 == 0:
            shot_role, shot_scale = "insert", "extreme_closeup"
        elif cut_number % 2 == 0:
            shot_role, shot_scale = "object_proof", "medium_closeup"
        else:
            shot_role, shot_scale = "object_proof", "closeup"
    elif cut_number == 1:
        shot_role, shot_scale = "establishing", "medium_wide"
    elif cut_function in {"reaction", "payoff"}:
        shot_role, shot_scale = "reaction", "medium_closeup"
    elif cut_number % 4 == 0:
        shot_role, shot_scale = "handoff", "medium_wide"
    elif cut_number % 3 == 0:
        shot_role, shot_scale = "insert", "closeup"
    else:
        shot_role, shot_scale = "character_action", "medium"
    face_action_required = bool(
        re.search(
            r"顔|視線|目を|振り返|表情",
            " / ".join(
                str(cut_blueprint.get(key) or "")
                for key in (
                    "motion_brief",
                    "motion_end_state",
                    "visual_beat",
                    "causal_proof",
                )
            ),
        )
    )
    return {
        "shot_role": shot_role,
        "shot_scale": shot_scale,
        "a_roll_or_b_roll": "b_roll" if shot_role == "object_proof" else "a_roll",
        "should_show_face": shot_role != "object_proof" or face_action_required,
        "should_show_hands": bool(object_ids) or shot_role not in {"establishing", "handoff"},
        "should_show_object_detail": bool(object_ids),
    }


def _scaffold_location_light(location_spec: dict[str, Any], location_name: str) -> str:
    visual_spec = location_spec.get("visual_spec")
    subject = str(visual_spec.get("subject") or "") if isinstance(visual_spec, dict) else ""
    for phrase in (
        "シャンデリア光",
        "濃い青の月明かり",
        "月明かり",
        "月光",
        "集いの場の光",
        "遮られた光",
        "低い自然光",
        "落ち着いた光",
    ):
        if phrase in subject:
            return f"{location_name}を照らす{phrase}"
    return f"{location_name}の奥から前景へ差す、場所の形が読める光"


def _drawable_phrase_for_scaffold(value: Any) -> str:
    """Translate sequencing shorthand into an absolute, drawable current state."""

    text = re.sub(r"\s+", " ", str(value or "")).strip()
    current_quoted = re.search(
        r"このcutでは「(?P<state>.*)」へ進む",
        text,
    ) or re.search(r'このcutでは"(?P<state>.*)"へ進む', text)
    if current_quoted:
        text = current_quoted.group("state")
    text = re.sub(
        r"(?:前|次|後続)(?:の)?(?:cut|scene)[^、。]*[、。]?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = text.replace("このcut", "現在の画面").replace("この cut", "現在の画面")
    for production_phrase, visible_phrase in {
        "観客がsceneを誤読しないための情報を画面に置く": "場所、人物同士の距離、出入口の位置関係を見せる",
        "scene理解に必要な手がかり": "状況を示す前景の障害物",
        "観客がsceneの前提情報を一枚で読める": "場所、人物、出入口の位置関係が一枚で見える",
        "sceneの結果を次へ渡す": "前景の痕跡、主人公の姿勢、出口へ伸びる光を見せる",
        "場面の結果を次へ渡す": "前景の痕跡、主人公の姿勢、出口へ伸びる光を見せる",
    }.items():
        text = text.replace(production_phrase, visible_phrase)
    text = re.sub(
        r"\b(?:setup|pressure|turn|payoff)\s+beat(?:の)?",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = text.replace("scene固有", "場面固有").replace("scene内", "場面内").replace("sceneの", "場面の")
    text = re.sub(r"物語イベントの証拠\s*[:：]\s*", "", text)
    for internal_term, drawable_term in {
        "場面の核": "主被写体",
        "観客理解": "画面で見える情報",
        "因果の証明": "画面内の物理的な証拠",
        "価値変化": "表情と姿勢の変化",
        "場所の圧力": "狭さと障害物",
        "場のルール": "人物同士の距離と出入口への位置関係",
        "主人公の制限": "動きを止める身体配置",
    }.items():
        text = text.replace(internal_term, drawable_term)
    text = text.replace("物証として始まる", "光に照らされて見える")
    text = re.sub(
        r"(?P<subject>[^、。]{1,30})の足音",
        r"\g<subject>の足元と床へ伸びる影",
        text,
    )
    text = re.sub(
        r"(?P<subject>[^、。]{1,30})の排除",
        r"\g<subject>が主被写体から距離を取り、画面端へ退く身体配置",
        text,
    )
    text = text.replace("が動けない理由を示す", "に緊張が残り、身体が出口へ向けずにいる")
    text = text.replace("状態差が", "手元と周囲の明暗差が")
    text = text.replace("を固定する", "が明確に見える")
    text = text.replace(
        "姿勢が次の方向を示している",
        "姿勢と身体軸が画面奥の出口へ向いている",
    )
    text = text.replace("次へ進む導線", "画面奥の出口方向")
    text = text.replace("次へ続く導線", "画面奥へ続く通路")
    text = text.replace(
        "足先と重心が次の動きに向き",
        "足先と重心が画面内の出口方向へ向き",
    )
    text = text.replace("次の導線", "画面奥の導線").replace("次の方向", "身体が向く方向")
    text = text.replace("次の動き", "身体が向く画面内の方向")
    text = text.replace("次の場面", "画面外の後続場面")
    text = text.replace("画面奥または横方向に画面奥の導線", "画面奥または横方向の導線")
    if re.search(r"(?:scene|場面)開始(?:の)?状態(?:を)?提示", text, flags=re.IGNORECASE):
        return ""
    text = re.sub(r"\bscene\d+[_-](?:cut|event)[A-Za-z0-9_.-]*\b", "", text, flags=re.IGNORECASE)
    if "を受け、" in text:
        text = text.split("を受け、", 1)[1]
    if re.search(r"(?:scene|場面)?理解に必要な手がかり", text, flags=re.IGNORECASE):
        return ""
    return re.sub(r"\s+", " ", text).strip(" 、。:：/")


def _cut_specific_drawable_evidence_for_scaffold(
    viewer_contract: dict[str, Any],
) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    seen: set[str] = set()
    for field_name in ("must_show", "visual_evidence"):
        raw_values = viewer_contract.get(field_name)
        values = raw_values if isinstance(raw_values, list) else [raw_values]
        for raw_value in values:
            if isinstance(raw_value, dict):
                raw_value = (
                    raw_value.get("must_be_drawn_as")
                    or raw_value.get("visible_substitute")
                    or raw_value.get("name")
                    or ""
                )
            phrase = _drawable_phrase_for_scaffold(raw_value)
            if (
                not phrase
                or phrase in seen
                or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", phrase)
                or re.search(
                    r"first_frame_visual_plan|cut_contract|scene_event|source_event_contract|motion_brief",
                    phrase,
                    flags=re.IGNORECASE,
                )
            ):
                continue
            seen.add(phrase)
            evidence.append(
                {
                    "source_field": f"viewer_contract.{field_name}",
                    "must_be_drawn_as": phrase,
                }
            )
    return evidence


def _first_frame_visual_plan_for_scaffold(
    *,
    selector: str,
    profile: dict[str, Any],
    location_spec: dict[str, Any],
    location_name: str,
    cut_number: int,
    cut_plan: dict[str, Any],
    cut_blueprint: dict[str, Any],
    cut_contract: dict[str, Any],
    character_ids: list[str],
    object_ids: list[str],
    references: list[str],
    cut_uses_artifact: bool,
    scene_time_of_day: str = "",
    drawable_evidence: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Derive the immutable provider-facing first-frame plan from the cut contract."""

    source_event = (
        cut_contract.get("source_event_contract")
        if isinstance(cut_contract.get("source_event_contract"), dict)
        else {}
    )
    first_frame = (
        cut_contract.get("first_frame_contract")
        if isinstance(cut_contract.get("first_frame_contract"), dict)
        else {}
    )
    viewer = (
        cut_contract.get("viewer_contract")
        if isinstance(cut_contract.get("viewer_contract"), dict)
        else {}
    )
    cinematic = (
        cut_contract.get("cinematic_contract")
        if isinstance(cut_contract.get("cinematic_contract"), dict)
        else {}
    )
    geography = (
        cinematic.get("screen_geography")
        if isinstance(cinematic.get("screen_geography"), dict)
        else {}
    )
    progression = (
        cut_contract.get("cut_state_progression")
        if isinstance(cut_contract.get("cut_state_progression"), dict)
        else {}
    )
    visible_moment = _drawable_phrase_for_scaffold(
        first_frame.get("event_fact_visible_in_still")
        or cut_blueprint.get("visual_beat")
        or progression.get("state_visible_in_first_frame")
        or cut_blueprint.get("first_frame_brief")
        or ""
    )
    if not visible_moment:
        visible_moment = _drawable_phrase_for_scaffold(
            cut_blueprint.get("first_frame_brief") or viewer.get("visual_proof") or ""
        )

    emotion_transition = (
        cut_contract.get("cut_character_emotion_transition")
        if isinstance(cut_contract.get("cut_character_emotion_transition"), dict)
        else {}
    )
    emotion_from = (
        emotion_transition.get("emotion_from")
        if isinstance(emotion_transition.get("emotion_from"), dict)
        else {}
    )
    visible_behavior = (
        emotion_from.get("visible_behavior")
        if isinstance(emotion_from.get("visible_behavior"), dict)
        else {}
    )
    if not visible_behavior and character_ids:
        visible_behavior = _visible_behavior_from_cut(
            profile=profile,
            cut_plan=cut_plan,
            cut_blueprint=cut_blueprint,
            location_name=location_name,
            object_ids=object_ids,
            focal_character_name=str(
                cut_plan.get("primary_subject_name") or profile["protagonist_name"]
            ),
        )

    character_state_bindings = _character_state_bindings_for_scaffold(
        profile, character_ids
    )
    identity_by_asset, identities_by_alias = _character_identity_catalog(profile)
    preferred_name_by_identity: dict[str, str] = {}
    for character_id in character_ids:
        identity = identity_by_asset.get(str(character_id).strip())
        if identity and identity not in preferred_name_by_identity:
            preferred_name_by_identity[identity] = _character_name_for_asset(
                profile, character_id
            )

    def canonicalize_visible_character_name(value: Any) -> str:
        text = str(value or "").strip()
        identities = _character_identities_in_text(profile, text)
        if len(identities) != 1:
            return text
        identity = next(iter(identities))
        preferred = preferred_name_by_identity.get(identity, "")
        if not preferred or preferred in text:
            return text
        matching_aliases = sorted(
            (
                alias
                for alias, alias_identities in identities_by_alias.items()
                if alias
                and alias in text
                and alias_identities == {identity}
                and alias not in identity_by_asset
            ),
            key=len,
            reverse=True,
        )
        if not matching_aliases:
            return text
        return text.replace(matching_aliases[0], preferred, 1)

    object_entries: list[dict[str, Any]] = []
    for object_index, object_id in enumerate(object_ids):
        object_name = _object_name_for_asset(profile, object_id)
        screen_position = "foreground" if object_index == 0 else "midground"
        object_entries.append(
            {
                "object_id": object_id,
                "object_name": object_name,
                "visibility_in_this_cut": "clearly_visible",
                "object_state": f"形、素材、現在位置が{'前景' if screen_position == 'foreground' else '中景'}で明確に見える",
                "story_meaning_in_this_cut": "",
                "required_screen_position": screen_position,
            }
        )

    shot_design = _scaffold_shot_design(
        cut_number=cut_number,
        cut_blueprint=cut_blueprint,
        cut_uses_artifact=cut_uses_artifact,
        object_ids=object_ids,
    )
    subject_priority = (
        cinematic.get("subject_priority")
        if isinstance(cinematic.get("subject_priority"), dict)
        else {}
    )
    primary_subject_name = str(
        subject_priority.get("primary")
        or cut_plan.get("primary_subject_name")
        or profile["protagonist_name"]
    ).strip()
    if object_entries and shot_design["shot_role"] in {"insert", "object_proof"}:
        primary_subject_name = str(object_entries[0]["object_name"])
    else:
        primary_subject_name = canonicalize_visible_character_name(
            primary_subject_name
        )

    primary_subject_identities = _character_identities_in_text(
        profile, primary_subject_name
    )
    secondary_subject_names: list[str] = []
    seen_subject_identities = set(primary_subject_identities)
    seen_subject_names = {primary_subject_name}
    for character_id in character_ids:
        character_name = _character_name_for_asset(profile, character_id)
        identity = identity_by_asset.get(str(character_id).strip())
        if identity and identity in seen_subject_identities:
            continue
        if character_name and character_name not in seen_subject_names:
            secondary_subject_names.append(character_name)
            seen_subject_names.add(character_name)
        if identity:
            seen_subject_identities.add(identity)
    for entry in object_entries:
        object_name = str(entry.get("object_name") or "").strip()
        if object_name and object_name not in seen_subject_names:
            secondary_subject_names.append(object_name)
            seen_subject_names.add(object_name)

    spatial_background = _drawable_phrase_for_scaffold(
        cut_plan.get("background") or location_name
    )
    spatial_midground = canonicalize_visible_character_name(
        _drawable_phrase_for_scaffold(
            cut_plan.get("midground") or geography.get("midground") or ""
        )
    )
    midground_identities = _character_identities_in_text(
        profile, spatial_midground
    )
    spatial_evidence = (
        drawable_evidence
        if drawable_evidence is not None
        else _cut_specific_drawable_evidence_for_scaffold(viewer)
    )
    raw_foreground_candidates = [
        cut_plan.get("foreground") or geography.get("foreground") or "",
        *(entry.get("object_name") or "" for entry in object_entries),
        *(
            item.get("must_be_drawn_as") or ""
            for item in spatial_evidence
            if isinstance(item, dict)
        ),
    ]
    spatial_foreground = ""
    for raw_candidate in raw_foreground_candidates:
        candidate = canonicalize_visible_character_name(
            _drawable_phrase_for_scaffold(raw_candidate)
        )
        if (
            not candidate
            or candidate == spatial_background
            or candidate == spatial_midground
        ):
            continue
        candidate_identities = _character_identities_in_text(profile, candidate)
        if (
            candidate_identities.intersection(midground_identities)
            and not _is_character_body_part_evidence(candidate)
        ):
            continue
        spatial_foreground = candidate
        break

    subject_priority_order: list[str] = []
    seen_priority_identities: set[str] = set()
    seen_priority_names: set[str] = set()
    for value in [
        primary_subject_name,
        *secondary_subject_names,
        location_name,
    ]:
        name = str(value or "").strip()
        identities = _character_identities_in_text(profile, name)
        if (
            not name
            or name in seen_priority_names
            or identities.intersection(seen_priority_identities)
        ):
            continue
        subject_priority_order.append(name)
        seen_priority_names.add(name)
        seen_priority_identities.update(identities)

    character_state_gate: dict[str, Any] = {}
    if character_ids:
        character_state_gate["pose"] = _drawable_phrase_for_scaffold(
            visible_behavior.get("posture") or visible_moment
        )
        if character_state_bindings:
            character_state_gate["character_states"] = character_state_bindings
        cut_function = str(cut_blueprint.get("cut_function") or "")
        if shot_design["should_show_face"] and (
            cut_function in {"reaction", "payoff", "threshold"}
            or re.search(r"視線|目|顔|見(?:る|上げ|つめ|渡)", visible_moment)
        ):
            character_state_gate["gaze"] = _drawable_phrase_for_scaffold(
                visible_behavior.get("gaze")
            )
        if shot_design["should_show_face"] and (
            cut_function in {"reaction", "payoff", "pressure"}
            or re.search(r"表情|顔|反応|圧力|拒|願い|ためら", visible_moment)
        ):
            character_state_gate["expression"] = _drawable_phrase_for_scaffold(
                visible_behavior.get("face")
            )
        if shot_design["should_show_hands"] and (
            object_ids or re.search(r"手|握|触|持|腕|指", visible_moment)
        ):
            character_state_gate["hand_position"] = _drawable_phrase_for_scaffold(
                visible_behavior.get("hands")
            )
        if re.search(r"足|歩|走|踏|重心", visible_moment):
            character_state_gate["foot_position"] = _drawable_phrase_for_scaffold(
                visible_behavior.get("feet")
            )
        if re.search(r"距離|迫|囲|押|立ち|座|倒", visible_moment):
            character_state_gate["physical_state"] = _drawable_phrase_for_scaffold(
                visible_behavior.get("distance")
            )
        character_state_gate = {
            key: value for key, value in character_state_gate.items() if value
        }

    reveal_constraints = (
        viewer.get("reveal_constraints")
        if isinstance(viewer.get("reveal_constraints"), dict)
        else {}
    )
    explicit_forbidden_future_outcomes = [
        _drawable_phrase_for_scaffold(item)
        for item in reveal_constraints.get("forbidden_until_later_cut", [])
        if _drawable_phrase_for_scaffold(item)
    ]
    resolved_forbidden_reveal_names = _drawable_forbidden_reveal_names_for_scaffold(
        profile,
        [
            *(source_event.get("forbidden_reveal_info_ids") or []),
            *(reveal_constraints.get("forbidden_until_later_scene") or []),
        ],
    )
    motion_contract = (
        cut_contract.get("motion_contract")
        if isinstance(cut_contract.get("motion_contract"), dict)
        else {}
    )
    motion_reveal_outcomes = [
        _drawable_phrase_for_scaffold(item)
        for item in motion_contract.get("allowed_new_reveal_elements") or []
        if _drawable_phrase_for_scaffold(item)
    ]
    first_frame_asset_policy = (
        cut_blueprint.get("first_frame_asset_policy")
        if isinstance(cut_blueprint.get("first_frame_asset_policy"), dict)
        else {}
    )
    excluded_object_names = [
        _object_name_for_asset(profile, str(object_id).strip())
        for object_id in first_frame_asset_policy.get("excluded_object_ids") or []
        if str(object_id).strip()
    ]
    excluded_object_tokens = {
        str(value).strip()
        for value in [
            *(first_frame_asset_policy.get("excluded_object_ids") or []),
            *excluded_object_names,
        ]
        if str(value).strip()
    }
    forbidden_future_outcomes = list(
        dict.fromkeys(
            [
                *explicit_forbidden_future_outcomes,
                *resolved_forbidden_reveal_names,
                *motion_reveal_outcomes,
                *excluded_object_names,
            ]
        )
    )
    # `must_not_advance_beyond` is a progression boundary.  In the
    # scaffold it is commonly the next cut's *positive* first-frame brief, so
    # projecting it into provider-facing `not_yet` prose reverses its polarity.
    # Only explicit
    # reveal/future-outcome constraints belong in the drawable negative list;
    # the progression boundary remains available in cut_state_progression for
    # downstream consumer.

    visual_spec = location_spec.get("visual_spec")
    location_texture = (
        str(visual_spec.get("subject") or "").strip()
        if isinstance(visual_spec, dict)
        else ""
    )
    location_texture = "、".join(
        part.strip()
        for part in location_texture.split("、")
        if part.strip()
        and not re.search(r"(?:人物|物語アイテム)なし$", part.strip())
    )
    location_texture = str(
        _sanitize_first_frame_prose(
            location_texture,
            excluded_tokens=excluded_object_tokens,
        )
        or ""
    ).strip()
    location_light = str(
        _sanitize_first_frame_prose(
            _scaffold_location_light(location_spec, location_name),
            excluded_tokens=excluded_object_tokens,
        )
        or f"{location_name}の空間構造が読める光"
    ).strip()
    state_delta = _drawable_phrase_for_scaffold(
        progression.get("visible_state_delta_from_previous_cut")
    )

    protagonist_reference_ids = {
        str(profile.get("protagonist_asset_id") or "").strip(),
    }
    protagonist_subject_names = {
        str(profile.get("protagonist_name") or "").strip(),
    }
    character_identity_names = {
        str(binding.get("character_id") or "").strip(): str(
            binding.get("character_name") or ""
        ).strip()
        for binding in character_state_bindings
        if str(binding.get("character_id") or "").strip()
        and str(binding.get("character_name") or "").strip()
    }

    def character_role_in_frame(character_id: str) -> str:
        target_name = _character_name_for_asset(profile, character_id)
        is_protagonist_variant = (
            character_id in protagonist_reference_ids
            and primary_subject_name in protagonist_subject_names
        )
        return (
            "primary_subject"
            if target_name == primary_subject_name or is_protagonist_variant
            else "secondary_subject"
        )

    return {
        "schema_version": "first_frame_visual_plan_v1",
        "derived_from": [
            "scene_event.event_sequence[]",
            "cut_contract.source_event_contract",
            "cut_contract.first_frame_contract",
            "cut_contract.motion_contract",
            "cut_contract.event_context_for_cut",
        ],
        "editable": False,
        "source_grounding": {
            "scene_id": str(selector).split("_cut", 1)[0],
            "cut_id": selector,
            "source_event_beat_id": str(source_event.get("primary_event_beat_id") or ""),
            "source_event_beat_ids": list(source_event.get("source_event_beat_ids") or []),
            "event_beat_function": str(source_event.get("event_beat_function") or ""),
            "cut_function": str(cut_contract.get("cut_function") or ""),
            "what_happens": str(source_event.get("source_event_summary") or ""),
            "visible_action": str(source_event.get("source_visible_action") or ""),
            "visible_reaction": str(source_event.get("source_visible_reaction") or ""),
            "event_facts_to_preserve": list(source_event.get("event_facts_to_preserve") or []),
            "event_facts_not_to_invent": list(source_event.get("event_facts_not_to_invent") or []),
            "allowed_reveal_info_ids": list(source_event.get("allowed_reveal_info_ids") or []),
            "forbidden_reveal_info_ids": list(source_event.get("forbidden_reveal_info_ids") or []),
        },
        "temporal_boundary": {
            "event_time_position": str(first_frame.get("event_time_position") or ""),
            "first_visible_moment": visible_moment,
            "action_completion_state": str(first_frame.get("action_completion_state") or ""),
            "event_fact_visible_in_still": visible_moment,
            "not_yet_happened_in_still": forbidden_future_outcomes,
            "forbidden_future_event_beat_ids": list(first_frame.get("not_yet_happened_in_still") or []),
            "forbidden_future_outcomes": forbidden_future_outcomes,
            "still_must_not_show_completion": True,
            "one_visible_moment_rule": True,
        },
        "visual_translation": {
            "concrete_visible_evidence": deepcopy(
                drawable_evidence
                if drawable_evidence is not None
                else _cut_specific_drawable_evidence_for_scaffold(viewer)
            ),
            "nonvisual_terms_to_exclude_from_prompt": [
                "audience_knowledge_delta",
                "dramatic_job",
                "source_event_contract",
                "motion_brief",
            ],
            "imageable_causal_proof": str(viewer.get("causal_proof") or viewer.get("visual_proof") or ""),
        },
        "subject_binding": {
            "primary_subject": {"name": primary_subject_name},
            "secondary_subjects": [
                {"name": value} for value in secondary_subject_names
            ],
            "background_subjects": [{"name": location_name}],
        },
        "reference_binding": {
            "character_references": [
                {
                    "path": reference,
                    "target_character_id": character_id,
                    "target_character_name": _character_name_for_asset(
                        profile, character_id
                    ),
                    **(
                        {
                            "target_identity_name": character_identity_names[
                                character_id
                            ]
                        }
                        if character_id in character_identity_names
                        else {}
                    ),
                    "role_in_frame": character_role_in_frame(character_id),
                }
                for character_id, reference in _bind_character_reference_pairs(
                    character_ids=character_ids,
                    references=references,
                    context=selector,
                )
            ],
            "object_references": [
                ref for ref in references if "/objects/" in ref or f"/{profile['artifact_output_dir']}/" in ref
            ],
            "location_references": [ref for ref in references if "/locations/" in ref],
        },
        "character_state_gate": character_state_gate,
        "object_visibility_gate": {"objects": object_entries},
        "spatial_composition": {
            "foreground": spatial_foreground,
            "midground": spatial_midground,
            "background": spatial_background,
            "subject_priority_order": subject_priority_order,
            "frame_edge_handoff": str(geography.get("screen_direction") or cut_plan.get("screen_direction") or ""),
            "shot_size": shot_design["shot_scale"],
            "camera_angle": str(geography.get("screen_direction") or cut_plan.get("screen_direction") or ""),
        },
        "scene_material_pack": {
            "time_of_day": str(scene_time_of_day or "").strip(),
            "light_source": location_light,
            "light_direction": f"{location_name}の奥から主被写体へ向く",
            "dominant_materials": [location_texture] if location_texture else [f"{location_name}の床、壁、衣服の実物質感"],
            "story_specific_texture": location_texture,
        },
        "scene_state_progression": {
            "progression_mode": str(progression.get("progression_mode") or "suspended_moment"),
            "state_visible_in_first_frame": "",
            "visible_state_delta_from_previous_cut": state_delta,
        },
        "motion_affordance": {
            "movable_subjects": [],
            "must_not_resolve_in_image": forbidden_future_outcomes,
            "motion_ceiling": {
                "must_stop_before_event_beat_ids": list(first_frame.get("not_yet_happened_in_still") or []),
                "must_not_complete_outcomes": forbidden_future_outcomes,
            },
        },
        "prompt_rendering_policy": {
            "render_only_drawable_information": True,
            "do_not_render_design_meta": True,
            "do_not_render_future_motion_as_action": True,
        },
    }


def _scene_source_events(profile: dict[str, Any], idx: int) -> list[str]:
    authored_events = _story_source_events(profile, idx)
    if authored_events:
        return authored_events
    events = [str(event) for event in profile.get("events", []) if str(event).strip()]
    if not events:
        return []
    scene_count = max(1, len(profile.get("scene_titles") or []))
    start = min(len(events) - 1, int((idx - 1) * len(events) / scene_count))
    window = max(1, int((len(events) + scene_count - 1) / scene_count))
    return events[start : min(len(events), start + window)]


def _runtime_scene_id(idx: int) -> int:
    return idx * 10


def _scene_research_refs(
    idx: int,
    source_events: list[str],
    profile: dict[str, Any] | None = None,
) -> list[str]:
    if not source_events:
        event_ids = profile.get("research_event_ids") if isinstance(profile, dict) else None
        if isinstance(event_ids, list) and event_ids:
            event_id = str(event_ids[min(idx - 1, len(event_ids) - 1)])
            return [f"research.story_materials.chronological_events[{event_id}]"]
        return [f"research.story_materials.chronological_events[E{idx:02d}]"]
    refs: list[str] = []
    event_ids_by_text = profile.get("research_event_ids_by_text") if isinstance(profile, dict) else None
    for event in source_events:
        event_id = event_ids_by_text.get(event) if isinstance(event_ids_by_text, dict) else None
        refs.append(f"research.story_materials.chronological_events[{event_id or _stable_slug(event)}]")
    passage_ids_by_text = profile.get("research_passage_ids_by_text") if isinstance(profile, dict) else None
    passage_ids = profile.get("research_passage_ids") if isinstance(profile, dict) else None
    if isinstance(passage_ids_by_text, dict):
        for event in source_events:
            passage_id = str(passage_ids_by_text.get(event) or "").strip()
            if passage_id:
                refs.append(f"research.source_passages[{passage_id}]")
    elif isinstance(passage_ids, list) and passage_ids:
        passage_id = str(passage_ids[min(idx - 1, len(passage_ids) - 1)])
        refs.append(f"research.source_passages[{passage_id}]")
    elif profile is None:
        refs.append(f"research.source_passages[P{idx}]")

    return list(dict.fromkeys(refs))


def _story_research_refs(profile: dict[str, Any], idx: int) -> list[str]:
    scenes = profile.get("story_scenes")
    if not isinstance(scenes, list) or not 0 <= idx - 1 < len(scenes):
        return []
    scene = scenes[idx - 1]
    if not isinstance(scene, dict) or not isinstance(scene.get("research_refs"), list):
        return []
    return list(
        dict.fromkeys(
            str(value).strip()
            for value in scene["research_refs"]
            if str(value).strip()
        )
    )


def _research_ref_entry_id(ref: str, section: str) -> str:
    prefix = f"research.{section}["
    return ref[len(prefix) : -1].strip() if ref.startswith(prefix) and ref.endswith("]") else ""


def _story_source_events(profile: dict[str, Any], idx: int) -> list[str]:
    """Resolve authored scene allocation against the researched source artifact."""

    refs = _story_research_refs(profile, idx)
    research = profile.get("research")
    if not refs or not isinstance(research, dict):
        return []
    materials = research.get("story_materials") if isinstance(research.get("story_materials"), dict) else {}
    raw_events = materials.get("chronological_events") if isinstance(materials.get("chronological_events"), list) else []
    events_by_id = {
        str(item.get("event_id") or "").strip(): str(item.get("event") or "").strip()
        for item in raw_events
        if isinstance(item, dict) and str(item.get("event_id") or "").strip() and str(item.get("event") or "").strip()
    }
    raw_passages = research.get("source_passages") if isinstance(research.get("source_passages"), list) else []
    passages_by_id = {
        str(item.get("passage_id") or "").strip(): str(item.get("passage") or "").strip()
        for item in raw_passages
        if isinstance(item, dict) and str(item.get("passage_id") or "").strip() and str(item.get("passage") or "").strip()
    }
    raw_conflicts = research.get("conflicts") if isinstance(research.get("conflicts"), list) else []

    def conflict_source_text(item: dict[str, Any]) -> str:
        selection = item.get("selection_notes") if isinstance(item.get("selection_notes"), dict) else {}
        recommended_choice = str(selection.get("recommended_choice") or "").strip()
        accounts = item.get("accounts") if isinstance(item.get("accounts"), list) else []
        selected_claim = next(
            (
                str(account.get("claim") or "").strip()
                for account in accounts
                if isinstance(account, dict)
                and str(account.get("account_id") or "").strip() == recommended_choice
                and str(account.get("claim") or "").strip()
            ),
            "",
        )
        if not selected_claim:
            selected_claim = next(
                (
                    str(account.get("claim") or "").strip()
                    for account in accounts
                    if isinstance(account, dict) and str(account.get("claim") or "").strip()
                ),
                "",
            )
        return " / ".join(
            text
            for text in (
                str(item.get("topic") or "").strip(),
                selected_claim,
                str(item.get("impact_on_story") or "").strip(),
            )
            if text
        )

    conflicts_by_id: dict[str, str] = {}
    for item in raw_conflicts:
        if not isinstance(item, dict):
            continue
        conflict_id = str(item.get("conflict_id") or "").strip()
        source_text = conflict_source_text(item)
        if conflict_id and source_text:
            conflicts_by_id[conflict_id] = source_text
    event_values = [
        events_by_id[entry_id]
        for ref in refs
        if (entry_id := _research_ref_entry_id(ref, "story_materials.chronological_events")) in events_by_id
    ]
    if event_values:
        return list(dict.fromkeys(event_values))
    passage_values = [
        passages_by_id[entry_id]
        for ref in refs
        if (entry_id := _research_ref_entry_id(ref, "source_passages")) in passages_by_id
    ]
    if passage_values:
        return list(dict.fromkeys(passage_values))
    conflict_values = [
        conflicts_by_id[entry_id]
        for ref in refs
        if (entry_id := _research_ref_entry_id(ref, "conflicts")) in conflicts_by_id
    ]
    return list(dict.fromkeys(conflict_values))


def _downstream_scene_research_refs(
    idx: int,
    source_events: list[str],
    profile: dict[str, Any],
) -> list[str]:
    authored_refs = _story_research_refs(profile, idx)
    return authored_refs or _scene_research_refs(idx, source_events, profile)


def _next_scene_title(profile: dict[str, Any], idx: int) -> str:
    titles = [str(title) for title in profile.get("scene_titles") or []]
    if idx < len(titles):
        return titles[idx]
    return "物語の終端"


def _previous_scene_title(profile: dict[str, Any], idx: int) -> str:
    titles = [str(title) for title in profile.get("scene_titles") or []]
    if idx > 1 and idx - 2 < len(titles):
        return titles[idx - 2]
    return "開始前の状況"


def _story_scene(profile: dict[str, Any], idx: int) -> dict[str, Any]:
    scenes = profile.get("story_scenes")
    if isinstance(scenes, list) and 0 <= idx - 1 < len(scenes) and isinstance(scenes[idx - 1], dict):
        return scenes[idx - 1]
    return {}


def _apply_story_scene_to_blueprint(
    blueprint: dict[str, Any],
    *,
    profile: dict[str, Any],
    idx: int,
) -> dict[str, Any]:
    """Overlay only authored story meaning onto downstream cut inputs."""

    authored_scene = _story_scene(profile, idx)
    if not authored_scene:
        return blueprint
    merged = dict(blueprint)
    purpose = str(authored_scene.get("purpose") or "").strip()
    conflict = str(authored_scene.get("conflict") or "").strip()
    turn = str(authored_scene.get("turn") or "").strip()
    visual_action = str(authored_scene.get("visualizable_action") or "").strip()
    if purpose:
        merged["story_purpose"] = purpose
    if conflict:
        merged["obstacle"] = conflict
        merged["scene_spine"] = f"{merged.get('desire', '')} / {conflict} / {turn or merged.get('causal_turn', '')}"
    if turn:
        merged["causal_turn"] = turn
        merged["no_return_point"] = turn
        merged["payoff"] = f"{turn}の結果が{merged.get('handoff_anchor', '次のscene')}へ残る"
    # ``visualizable_action`` is a story/scene overview, even when the scene
    # uses only one location.  It may describe A→B→C across several beats, so
    # it is scene overview context rather than cut-local drawable evidence. The cut
    # event projection below owns the concrete still state.
    if visual_action:
        merged["story_overview_visualizable_action"] = visual_action
    merged["story_scene_id"] = str(authored_scene.get("scene_id") or idx)
    merged["research_refs"] = list(authored_scene.get("research_refs") or merged.get("research_refs") or [])
    return merged




def _project_beat_overrides_to_segment_locations(
    beat_overrides: dict[str, Any],
    *,
    allowed_locations: set[str],
    allowed_functions: set[str],
) -> dict[str, Any]:
    """Project canonical multi-location overrides onto one duration segment."""

    def project_override(value: Any) -> Any | None:
        if not isinstance(value, dict):
            return deepcopy(value)
        explicit_location = str(value.get("location") or "").strip()
        projected = deepcopy(value)
        nested = projected.get("obligation_overrides")
        projected_nested: dict[str, Any] = {}
        if isinstance(nested, dict):
            for obligation_id, obligation_override in nested.items():
                projected_override = project_override(obligation_override)
                if projected_override is not None:
                    projected_nested[obligation_id] = projected_override
            projected["obligation_overrides"] = projected_nested
        if explicit_location and explicit_location not in allowed_locations:
            if projected_nested:
                return {"obligation_overrides": projected_nested}
            return None
        return projected

    projected: dict[str, Any] = {}
    for function, override in beat_overrides.items():
        if function not in allowed_functions:
            continue
        projected_override = project_override(override)
        if projected_override is not None:
            projected[function] = projected_override
    return projected


def _scene_blueprint(
    *,
    profile: dict[str, Any],
    idx: int,
    title: str,
    location_name: str,
    include_artifact: bool,
) -> dict[str, Any]:
    protagonist = str(profile.get("protagonist_name") or profile.get("topic_label") or "主要人物")
    artifact = str(profile.get("artifact_name") or "物語上の証拠")
    source_events = _scene_source_events(profile, idx)
    source_summary = " / ".join(source_events) if source_events else str(profile.get("summary") or title)
    previous_title = _previous_scene_title(profile, idx)
    next_title = _next_scene_title(profile, idx)
    is_terminal = idx == len(profile.get("scene_titles") or [])
    evidence_terms = _event_visual_evidence_terms(source_summary, profile, include_artifact=include_artifact)
    primary_evidence = evidence_terms[0] if evidence_terms else location_name
    second_evidence = evidence_terms[1] if len(evidence_terms) > 1 else protagonist
    artifact_term = artifact if include_artifact else f"{artifact}をまだ隠す条件"
    return {
        "source_events": source_events,
        "research_refs": _downstream_scene_research_refs(idx, source_events, profile),
        "semantic_scene_responsibility_id": f"scene_{idx:02d}",
        "segment_beat_ids": [f"scene_{idx:02d}_whole"],
        "segment_responsibility": f"{title}で{source_summary}を人物・場所・証拠の因果として成立させる",
        "dramatic_question": f"{title}で{protagonist}は、{primary_evidence}を根拠に選択を変えられるか",
        "story_purpose": f"{title}で、source event「{source_summary}」を人物・場所・証拠の因果として成立させる",
        "scene_spine": f"{source_summary} / {location_name}の制約 / {artifact_term}",
        "desire": f"{protagonist}は{source_summary}を受けて、現在の制約から抜け出したい",
        "obstacle": f"{location_name}、関係性、または{second_evidence}が選択を狭める",
        "stakes": f"失敗すると、{source_summary}の意味が周囲に認識されないまま終わる",
        "escalation": f"{primary_evidence}が画面に増え、{protagonist}の選択肢が一つへ絞られる",
        "no_return_point": f"{source_summary}が、{location_name}内の物理的な痕跡として残る",
        "visible_pressure": list(dict.fromkeys([primary_evidence, second_evidence, location_name, *([artifact] if include_artifact else [])]))[:5],
        "pressure_source": second_evidence,
        "pressure_source_visible_from": "setup",
        "turn_motion_target": primary_evidence,
        "payoff_focus": primary_evidence,
        "beat_overrides": {},
        "causal_turn": f"{title}で{source_summary}が物的証拠に変わり、後続場面の原因になる",
        "payoff": f"{primary_evidence}と{location_name}の変化が、{next_title}の開始条件になる",
        "handoff_anchor": f"{primary_evidence}と{location_name}に残る痕跡",
        "incoming_trigger": f"{previous_title}から渡る原因: {source_events[0] if source_events else source_summary}",
        "outgoing_pressure": "終端" if is_terminal else f"{primary_evidence}が{next_title}で回収される",
        "value_from": "周囲の制約に意味を奪われている状態",
        "value_to": "選択の根拠が画面内の物証として残る状態" if not is_terminal else "証拠と人物が結びつき物語が閉じる状態",
        "visible_evidence": list(dict.fromkeys([location_name, protagonist, *evidence_terms, *([artifact] if include_artifact else [])]))[:6],
        "character_start": f"{protagonist}は{location_name}で{second_evidence}に制限されている",
        "character_end": f"{protagonist}は{primary_evidence}を残し、後続場面を始める原因を持つ",
        "story_terms": list(dict.fromkeys([protagonist, artifact, location_name, *evidence_terms]))[:8],
    }

def _canonical_event_coverage_matrix(
    profile: dict[str, Any],
    script_scenes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    events = [str(event).strip() for event in profile.get("events", []) if str(event).strip()]
    scene_count = max(1, len(profile.get("scene_titles") or []))
    scene_by_id = {
        str(scene.get("scene_id") or _runtime_scene_id(scene_index)): scene
        for scene_index, scene in enumerate(script_scenes or [], start=1)
        if isinstance(scene, dict)
    }
    rows: list[dict[str, Any]] = []
    for event_index, event in enumerate(events, start=1):
        assigned_scene_indexes = [
            scene_index
            for scene_index in range(1, scene_count + 1)
            if event in _scene_source_events(profile, scene_index)
        ]
        if not assigned_scene_indexes:
            estimated_scene = min(scene_count, max(1, int((event_index - 1) * scene_count / max(1, len(events))) + 1))
            assigned_scene_indexes = [estimated_scene]
        assigned_scene_ids = [_runtime_scene_id(scene_index) for scene_index in assigned_scene_indexes]
        importance = "critical" if event_index in {1, len(events)} else "high" if event_index in {2, 3, 4, len(events) - 1} else "medium"
        preferred_beat_function = "turn" if importance in {"critical", "high"} else "pressure"
        assigned_event_beat_ids: list[str] = []
        for scene_index, scene_id in zip(
            assigned_scene_indexes,
            assigned_scene_ids,
            strict=True,
        ):
            legacy_beat_id = f"scene{scene_index:02d}_event_{preferred_beat_function}"
            scene = scene_by_id.get(str(scene_id))
            scene_event = (
                scene.get("scene_event")
                if isinstance(scene, dict) and isinstance(scene.get("scene_event"), dict)
                else {}
            )
            event_sequence = [
                beat
                for beat in scene_event.get("event_sequence", [])
                if isinstance(beat, dict) and str(beat.get("beat_id") or "").strip()
            ]
            preferred_beat = next(
                (
                    beat
                    for beat in event_sequence
                    if str(beat.get("beat_function") or "").strip()
                    == preferred_beat_function
                ),
                None,
            )
            actual_beat_ids = {
                str(beat["beat_id"]).strip()
                for beat in event_sequence
            }
            turning_event = (
                scene_event.get("turning_event")
                if isinstance(scene_event.get("turning_event"), dict)
                else {}
            )
            turning_beat_id = str(
                turning_event.get("source_event_beat_id") or ""
            ).strip()
            assigned_event_beat_ids.append(
                str(preferred_beat["beat_id"]).strip()
                if preferred_beat is not None
                else turning_beat_id
                if turning_beat_id in actual_beat_ids
                else str(event_sequence[-1]["beat_id"]).strip()
                if event_sequence
                else legacy_beat_id
            )
        rows.append(
            {
                "source_event_id": f"source_event_{event_index:02d}",
                "source_event_summary": event,
                "importance": importance,
                "required": importance in {"critical", "high"},
                "must_appear_as": "scene",
                "canonical_order_index": event_index,
                "assigned_scene_ids": assigned_scene_ids,
                "assigned_event_beat_ids": assigned_event_beat_ids,
                "omission_reason": "",
                "adaptation_change_reason": "scene数とcut密度に合わせ、source event を最も近い scene_event beat へ割り当てる",
                "human_approval_required": False,
            }
        )
    return {
        "policy_version": "canonical_event_coverage_matrix_v1",
        "source": ["profile.events", "source_story_beat_ids", "scene_event.event_sequence"],
        "source_story_events": rows,
    }


SCENE_GENERATION_REQUIRED_OUTPUTS: tuple[str, ...] = (
    "scene_intent",
    "scene_event",
    "scene_character_state_timeline",
    "scene_film_coverage_plan",
    "scene_cut_coverage_plan",
    "forbidden_event_changes",
)


def _scene_generation_policy(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "scene_generation_policy_v1",
        "purpose": "scene 正本を作るための authoring prompt を、設計文脈・実行 payload・debug source・出力 contract に分離する",
        "canonical_payload_path": "scenes[].scene_generation.scene_prompt_payload.prompt",
        "deprecated_fields": ["scene_generation.prompt"],
        "required_blocks": [
            "scene_authoring_context",
            "scene_prompt_payload",
            "scene_debug_prompt_source",
            "scene_generation_contract",
        ],
        "required_outputs": list(SCENE_GENERATION_REQUIRED_OUTPUTS),
        "downstream_boundary": "cut/image/narration/video は scene_prompt_payload を読まず、scene_event と scene_cut_coverage_plan から逆算する",
        "scene_count_policy": "scene prompt は cut 数を固定しない。scene_cut_coverage_plan が scene obligation から必要 cut 数を逆算する",
        "topic": profile.get("topic_label"),
    }


def _scene_generation_contract() -> dict[str, Any]:
    return {
        "schema_version": "scene_generation_contract_v1",
        "required_outputs": list(SCENE_GENERATION_REQUIRED_OUTPUTS),
        "scene_event_schema_version": "scene_event_v1",
        "must_preserve_order": ["scene_intent", "scene_event", "scene_character_state_timeline", "scene_film_coverage_plan", "scene_cut_coverage_plan"],
        "scene_event_rules": [
            "scene_event は出来事の正本であり、演出語を入れない",
            "event_sequence は authored required event beats を列挙し、各 beat を可視出来事へ接地する",
            "scene_event.forbidden_event_changes を scene から downstream へ渡す",
        ],
        "payload_boundary": "scene_prompt_payload は scene 正本生成だけに使う。後段の画像、音声、動画の実行情報は含めない",
    }


def _scene_generation_for_scene(
    *,
    topic: str,
    scene_id: int,
    idx: int,
    title: str,
    location_spec: dict[str, Any],
    include_artifact: bool,
    profile: dict[str, Any],
) -> dict[str, Any]:
    source_events = _scene_source_events(profile, idx)
    blueprint = _apply_story_scene_to_blueprint(
        _scene_blueprint(
            profile=profile,
            idx=idx,
            title=title,
            location_name=str(location_spec.get("name") or ""),
            include_artifact=include_artifact,
        ),
        profile=profile,
        idx=idx,
    )
    source_events = [
        str(event)
        for event in blueprint.get("source_events", [])
        if str(event).strip()
    ] or source_events
    source_beat_ids = [f"source_scene{idx:02d}_beat{event_index:02d}" for event_index, _ in enumerate(source_events, start=1)]
    protagonist = str(profile.get("protagonist_name") or topic)
    artifact = str(profile.get("artifact_name") or "")
    location_name = str(location_spec.get("name") or "")
    time_of_day = _scene_time_of_day(profile, idx)
    time_of_day_visual_basis = _scene_time_of_day_visual_basis(profile, idx)
    location_sequence = _scene_location_sequence(profile, idx) or [location_name]
    location_segments = _scene_location_segments(profile, idx)
    production_location_segments = [
        segment
        for segment in location_segments
        if _location_segment_root_is_active(segment)
    ]
    location_mode = "sequence" if len(location_sequence) > 1 else "single"
    required_outputs = list(SCENE_GENERATION_REQUIRED_OUTPUTS)
    scene_authoring_context = {
        "schema_version": "scene_authoring_context_v1",
        "topic": topic,
        "scene_id": scene_id,
        "scene_index": idx,
        "scene_title": title,
        "time_of_day": time_of_day,
        "time_of_day_visual_basis": time_of_day_visual_basis,
        "story_scope": {
            "protagonist": protagonist,
            "artifact": artifact,
            "theme": "尊厳、越境、時間制限、証明を scene 単位で成立させる",
            "run_variant": profile.get("run_variant", {}),
            "scene_titles": profile.get("scene_titles", []),
        },
        "source_beats": [
            {
                "source_story_beat_id": source_beat_ids[event_index],
                "summary": event,
                "source_origin": _source_origin_for_profile(profile),
            }
            for event_index, event in enumerate(source_events)
        ],
        "canonical_event_policy": {
            "source_story_events": "top-level canonical_event_coverage_matrix を参照",
            "scene_specificity": "この scene に割り当てられた source beat を scene_event の具体出来事へ接地する",
        },
        "scene_count_policy": {
            "maximize_meaningful_scene_count": True,
            "do_not_fix_cut_count_in_prompt": True,
            "cut_count_is_derived_by": "scene_cut_coverage_plan",
        },
        "location": {
            "location_id": location_spec.get("asset_id"),
            "name": location_name,
            "mode": location_mode,
            "sequence": location_sequence,
            "segments": location_segments,
            "story_purpose": location_spec.get("story_purpose"),
        },
        "artifact_usage": {
            "include_artifact": include_artifact,
            "artifact_name": artifact,
            "story_role": _artifact_scene_role(profile, idx) if include_artifact else "このsceneでは証拠アイテムを先取りしない",
        },
        "scene_specific_blueprint": {
            "dramatic_question": blueprint["dramatic_question"],
            "desire": blueprint["desire"],
            "obstacle": blueprint["obstacle"],
            "stakes": blueprint["stakes"],
            "causal_turn": blueprint["causal_turn"],
            "visible_pressure": blueprint["visible_pressure"],
            "handoff_anchor": blueprint["handoff_anchor"],
            "story_terms": blueprint["story_terms"],
        },
    }
    prompt = "\n".join(
        [
            f"物語「{topic}」の scene{scene_id}「{title}」を設計する。",
            "目的は、絵を直接描くことではなく、この scene が物語内で何を成立させるかを正本化すること。",
            f"場所: {location_name}",
            f"場所モード: {location_mode}",
            f"場所遷移: {' → '.join(location_sequence)}",
            *(
                [
                    "場所別の責任: "
                    + " / ".join(
                        f"{segment['location']}={segment['responsibility']}"
                        for segment in production_location_segments
                    )
                ]
                if production_location_segments
                else []
            ),
            f"時間帯: {time_of_day}",
            f"時間帯の視覚根拠: {time_of_day_visual_basis}",
            f"主人公: {protagonist}",
            f"必須 source beat: {' / '.join(source_events) if source_events else title}",
            f"この scene の固有問い: {blueprint['dramatic_question']}",
            f"この scene で起きる物理的 turn: {blueprint['causal_turn']}",
            f"画面で残す証拠: {', '.join(blueprint['visible_evidence'])}",
            f"次へ渡す handoff: {blueprint['handoff_anchor']}",
            f"必須出力: {', '.join(required_outputs)}",
            "scene_event は出来事だけを書く。演出や後段実行の情報は入れない。",
            "抽象的な役割を残しつつ、各 event beat を source に基づく具体出来事へ接地する。",
            "scene 内の具体要素は story function を持つものだけに絞る。",
            "cut 側で必要数を逆算できるよう、scene obligation と event beat の対応を明確にする。",
        ]
    )
    return {
        "schema_version": "scene_generation_v1",
        "scene_authoring_context": scene_authoring_context,
        "scene_prompt_payload": {
            "schema_version": "scene_prompt_payload_v1",
            "prompt": prompt,
            "input_refs": [
                "story.md",
                "research.md",
                "visual_value.md",
                "canonical_event_coverage_matrix",
                "asset_bible",
            ],
            "required_outputs": required_outputs,
            "constraints": [
                "scene 正本生成だけに使う",
                "後段の画像・音声・動画実行情報を含めない",
                "scene_event は物語事実に限定する",
                "具体要素は story function を持つものだけにする",
                "scene 内で必要な cut は coverage plan が逆算する",
            ],
        },
        "scene_debug_prompt_source": {
            "schema_version": "scene_debug_prompt_source_v1",
            "not_sent_to_agent": True,
            "source_story_beat_ids": source_beat_ids,
            "source_beats": source_events,
            "source_origin": _source_origin_for_profile(profile),
            "adaptation_choices": [
                "authored required event beats を列挙し、各 beat を可視出来事へ接地する",
                "asset は名前の登場ではなく scene 内の story function で採用する",
            ],
            "excluded_from_payload": [
                "後段の画像生成詳細",
                "後段の動画生成詳細",
                "後段の音声生成詳細",
                "内部診断",
            ],
            "forbidden_event_changes_source": "scene_event.forbidden_event_changes",
        },
        "scene_generation_contract": _scene_generation_contract(),
    }


def _event_visual_evidence_terms(event_text: str, profile: dict[str, Any], *, include_artifact: bool) -> list[str]:
    terms = ["人物の手元", "床や道具に残る痕跡"]
    rules = [
        (("知らせ", "招待", "呼び出", "命令", "告げ"), ["届いた知らせ", "周囲の反応"]),
        (("拒", "妨げ", "閉", "支配", "押しつけ", "仕事"), ["閉ざされた入口", "主人公の止まった身体"]),
        (("助力", "魔法", "変身", "偶然", "記憶"), ["助力の発生源", "変化前後の差"]),
        (("境界", "越え", "出発", "向かう", "旅", "移動"), ["越えるべき境界", "進む先が分かる導線"]),
        (("視線", "踊", "認識", "中心", "知らない姿"), ["見届ける人物の視線", "主人公が場の中心に置かれた構図"]),
        (("時間", "鐘", "追跡", "逃", "失"), ["期限を示す時計", "急ぐ身体と失われる証拠"]),
        (("探", "巡", "手がかり", "証"), ["持ち込まれた証", "証拠を見る視線"]),
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
        (("王", "宮殿", "公", "裁き", "村", "家々"), "authority_or_community"),
        (("偽", "失敗", "競争", "候補"), "contrast_or_false_claimant"),
    ]
    for keywords, role in role_rules:
        if any(keyword in event_text for keyword in keywords) and role not in roles:
            roles.append(role)
    return roles


def _visible_character_role_ids(
    *,
    profile: dict[str, Any],
    primary_subject: str,
    visible_text: str,
) -> list[str]:
    """Resolve only characters that the projected frame actually names."""

    roles: list[str] = []
    protagonist_names = {
        str(profile.get("protagonist_name") or "").strip(),
    }
    if primary_subject in protagonist_names or any(
        name and name in visible_text for name in protagonist_names
    ):
        roles.append("protagonist")
    for spec in _supporting_character_asset_specs(profile):
        name = str(spec.get("name") or "").strip()
        source_character_id = str(spec.get("source_character_id") or "").strip()
        if (
            name
            and source_character_id
            and (name == primary_subject or name in visible_text)
        ):
            roles.append(source_character_id)
    return list(dict.fromkeys(role for role in roles if role))


def _mixed_affect_design_for_cut(
    *,
    cut_function: str,
    cut_number: int,
    cut_count: int,
    is_terminal_scene: bool,
    visual_beat: str,
    narration: str,
) -> dict[str, Any]:
    base = {
        "mode": "none",
        "optional": True,
        "apply_when": [],
        "positive_valence_thread": "",
        "negative_valence_thread": "",
        "arousal_strategy": "hold",
        "audience_rollercoaster_job": "none",
        "design_intent": "",
        "visible_support": [],
        "narration_support": [],
        "sound_or_rhythm_support": [],
        "handoff_effect": "",
        "avoid_if": [
            "primary intent が増えて 1 cut = 1意図 を壊す",
            "scene_event にない新事実を足す必要がある",
            "視覚・語り・音/リズム・handoff の支えがない",
        ],
    }
    function = str(cut_function or "")
    terminal_cut = is_terminal_scene and cut_number == cut_count
    if function not in {"pressure", "turn", "payoff", "reaction"} and not terminal_cut:
        return base

    visible_support = [str(visual_beat or "人物の視線、姿勢、距離、残された証拠で感情の二重性を見せる")]
    narration_support = [str(narration or "映像を説明せず、希望と代償のどちらか一方だけを短く足す")]
    if function == "pressure":
        return {
            **base,
            "mode": "tension_release",
            "apply_when": ["希望や突破口が見えるほど、失敗や代償の不安も強まる cut"],
            "positive_valence_thread": "まだ突破できる可能性",
            "negative_valence_thread": "失敗した場合の損失や戻れなさ",
            "arousal_strategy": "rise",
            "audience_rollercoaster_job": "strain",
            "design_intent": "希望を見せて安心させず、次の turn への緊張を高める",
            "visible_support": visible_support,
            "narration_support": narration_support,
            "sound_or_rhythm_support": ["間を詰め、解放をまだ置かない"],
            "handoff_effect": "未解決の問いを次 cut に渡す",
        }
    if function == "turn":
        return {
            **base,
            "mode": "mixed",
            "apply_when": ["発見、決断、勝利の兆しと同時に代償が見える cut"],
            "positive_valence_thread": "状況が動いた、または真実に近づいた手応え",
            "negative_valence_thread": "その行為で失われるもの、戻れない境界",
            "arousal_strategy": "spike",
            "audience_rollercoaster_job": "reframe",
            "design_intent": "気持ちよい転換を単純な成功にせず、意味の重さを同時に出す",
            "visible_support": visible_support,
            "narration_support": narration_support,
            "sound_or_rhythm_support": ["ピーク直後に短い間を置き、理解を遅らせる"],
            "handoff_effect": "成功と不安の両方を payoff / reaction へ渡す",
        }
    if function == "payoff" or terminal_cut:
        return {
            **base,
            "mode": "bittersweet" if terminal_cut else "tension_release",
            "apply_when": ["安堵、証明、解決の中に代償や余韻を残す cut"],
            "positive_valence_thread": "救済、証明、到達、解放",
            "negative_valence_thread": "失われた時間、戻れなさ、残された孤独や責任",
            "arousal_strategy": "release",
            "audience_rollercoaster_job": "aftertaste" if terminal_cut else "release",
            "design_intent": "解放を与えつつ、映画的な余韻として一段だけ苦味を残す",
            "visible_support": visible_support,
            "narration_support": narration_support,
            "sound_or_rhythm_support": ["ピーク後に音量や密度を落とし、静かな残響を作る"],
            "handoff_effect": "終端なら aftertaste、続くなら次 scene の問いを静かに残す",
        }
    if function == "reaction":
        return {
            **base,
            "mode": "aftertaste",
            "apply_when": ["出来事の直後に、安心と理解の遅れを同時に読ませる cut"],
            "positive_valence_thread": "危機が一段解けた感覚",
            "negative_valence_thread": "理解したからこそ残る痛みや恐れ",
            "arousal_strategy": "drop",
            "audience_rollercoaster_job": "aftertaste",
            "design_intent": "反応で意味を沈め、次の情報を急がない",
            "visible_support": visible_support,
            "narration_support": narration_support,
            "sound_or_rhythm_support": ["短い沈黙または低密度の音で感情を落とす"],
            "handoff_effect": "余韻を次 cut の理解条件として渡す",
        }
    return base


STORY_FUNCTION_BY_ELEMENT_TYPE = {
    "character": "status_marker",
    "object": "proof",
    "location": "threshold",
    "gesture": "pressure",
    "trace": "proof",
    "rule": "deadline",
    "relationship": "obstacle",
    "event": "handoff",
    "visual_evidence": "proof",
}


def _source_origin_for_profile(profile: dict[str, Any]) -> str:
    return "user_input"


def _story_specificity_layers(
    *,
    profile: dict[str, Any],
    location_name: str,
    source_events: list[str],
    include_artifact: bool,
) -> dict[str, Any]:
    protagonist = str(profile["protagonist_name"])
    artifact = str(profile["artifact_name"])
    source_summary = " / ".join(source_events) if source_events else str(profile.get("summary") or "")
    return {
        "canonical_specificity": {
            "description": "原典・既知筋・ユーザー入力に由来する、この物語で欠かせない出来事や設定",
            "required_elements": [source_summary] if source_summary else [],
        },
        "character_specificity": {
            "description": "この物語の人物名、役割、欲望、弱点、関係性に固有の要素",
            "required_elements": [protagonist],
        },
        "relationship_specificity": {
            "description": "人物同士の支配、敵対、助力、誤解、約束、秘密などの関係性",
            "required_elements": ["主人公を妨げる力", "主人公を見届ける視線"],
        },
        "object_specificity": {
            "description": "物語上の小道具、証拠、呪い、鍵、手紙などの機能",
            "required_elements": [artifact] if include_artifact else [f"{artifact}は後続revealとして伏せる"],
        },
        "location_specificity": {
            "description": "その場所が物語上どんな制約・圧力・誘惑・境界として働くか",
            "required_elements": [location_name],
        },
        "rule_specificity": {
            "description": "魔法の制約、時間制限、社会制度、約束、禁忌など、その物語固有のルール",
            "required_elements": ["後続sceneの証明やrevealを先に見せない"],
        },
        "visual_specificity": {
            "description": "その物語でしか成立しない画面上の証拠、身体状態、痕跡、配置",
            "required_elements": _event_visual_evidence_terms(source_summary, profile, include_artifact=include_artifact),
        },
    }


def _non_replaceable_elements_for_beat(
    *,
    profile: dict[str, Any],
    location_name: str,
    source_event_text: str,
    include_artifact: bool,
) -> list[dict[str, str]]:
    protagonist = str(profile["protagonist_name"])
    artifact = str(profile["artifact_name"])
    elements = [
        {
            "element_id": "protagonist",
            "type": "character",
            "value": protagonist,
            "why_non_replaceable": "この人物の欲望と制約がsceneの中心因果を作るため",
        },
        {
            "element_id": "scene_location",
            "type": "location",
            "value": location_name,
            "why_non_replaceable": "この場所の制約や境界がsceneの圧力を作るため",
        },
    ]
    if source_event_text:
        elements.append(
            {
                "element_id": "source_event",
                "type": "event",
                "value": source_event_text,
                "why_non_replaceable": "source story / user input からこのsceneへ割り当てた出来事であり、別の出来事に置換するとsceneの意味が変わるため",
            }
        )
    if include_artifact:
        elements.append(
            {
                "element_id": "signature_artifact",
                "type": "object",
                "value": artifact,
                "why_non_replaceable": "この物語の証明やhandoffを担う主役級小道具であるため",
            }
        )
    return elements[:4]


def _concrete_story_elements_for_beat(
    *,
    beat_id: str,
    profile: dict[str, Any],
    location_name: str,
    source_event_text: str,
    visual_evidence: list[str],
    include_artifact: bool,
) -> list[dict[str, Any]]:
    protagonist = str(profile["protagonist_name"])
    artifact = str(profile["artifact_name"])
    elements: list[dict[str, Any]] = [
        {
            "element_id": "protagonist_state",
            "element_type": "character",
            "concrete_description": protagonist,
            "story_function": "status_marker",
            "appears_in_event_beat_ids": [beat_id],
            "visible_form": f"{protagonist}の姿勢、視線、手足の位置",
            "must_not_be_generic": True,
        },
        {
            "element_id": "scene_location_pressure",
            "element_type": "location",
            "concrete_description": location_name,
            "story_function": "threshold",
            "appears_in_event_beat_ids": [beat_id],
            "visible_form": f"{location_name}の入口、奥行き、遮断、導線",
            "must_not_be_generic": True,
        },
    ]
    if source_event_text:
        elements.append(
            {
                "element_id": "source_event_proof",
                "element_type": "event",
                "concrete_description": source_event_text,
                "story_function": "proof",
                "appears_in_event_beat_ids": [beat_id],
                "visible_form": "source story に由来する出来事が人物・場所・痕跡の関係で見える",
                "must_not_be_generic": True,
            }
        )
    if include_artifact:
        elements.append(
            {
                "element_id": "signature_artifact",
                "element_type": "object",
                "concrete_description": artifact,
                "story_function": "proof",
                "appears_in_event_beat_ids": [beat_id],
                "visible_form": f"{artifact}の形、反射、位置、人物との距離",
                "must_not_be_generic": True,
            }
        )
    for index, evidence in enumerate(visual_evidence[:2], start=1):
        evidence_text = str(evidence).strip()
        if not evidence_text:
            continue
        elements.append(
            {
                "element_id": f"visual_evidence_{index}",
                "element_type": "visual_evidence",
                "concrete_description": evidence_text,
                "story_function": "proof",
                "appears_in_event_beat_ids": [beat_id],
                "visible_form": evidence_text,
                "must_not_be_generic": True,
            }
        )
    return elements[:6]


def _asset_story_function_usage_for_beat(
    *,
    beat_id: str,
    profile: dict[str, Any],
    location_id: str,
    include_artifact: bool,
) -> list[dict[str, Any]]:
    usage = [
        {
            "asset_id": str(profile.get("protagonist_asset_id") or "protagonist"),
            "asset_type": "character",
            "used_in_scene": True,
            "used_in_event_beat_ids": [beat_id],
            "story_function_in_scene": "status_marker",
            "visible_or_hidden": "visible",
            "reason_if_unused": "",
        }
    ]
    if location_id:
        usage.append(
            {
                "asset_id": location_id,
                "asset_type": "location",
                "used_in_scene": True,
                "used_in_event_beat_ids": [beat_id],
                "story_function_in_scene": "threshold",
                "visible_or_hidden": "visible",
                "reason_if_unused": "",
            }
        )
    if include_artifact:
        usage.append(
            {
                "asset_id": str(profile.get("artifact_asset_id") or "signature_artifact"),
                "asset_type": "object",
                "used_in_scene": True,
                "used_in_event_beat_ids": [beat_id],
                "story_function_in_scene": "proof",
                "visible_or_hidden": "visible",
                "reason_if_unused": "",
            }
        )
    return usage


def _specificity_budget() -> dict[str, Any]:
    return {
        "max_primary_story_elements": 3,
        "max_secondary_story_elements": 3,
        "required_element_types": ["character", "location", "conflict_or_constraint", "visual_evidence"],
        "optional_element_types": ["object", "sound", "weather"],
        "reject_if": [
            "decorative_detail_without_story_function",
            "too_many_unrelated_objects",
            "concrete_but_not_source_grounded",
        ],
        "reject_decorative_detail_without_story_function": True,
    }


def _cut_required_roles_for_obligation(obligation: dict[str, Any]) -> list[str]:
    joined = " / ".join(
        str(obligation.get(key) or "")
        for key in ("screen_question", "dramatic_job", "visual_proof", "first_frame_brief", "foreground", "midground", "background")
    )
    roles = ["protagonist"]
    if any(word in joined for word in ("妨げ", "拒", "閉ざ", "支配", "敵")):
        roles.append("opponent")
    if any(word in joined for word in ("助力", "導く", "魔法", "光が届", "月光")):
        roles.append("helper")
    if any(word in joined for word in ("視線", "見届け", "受容", "認識", "群衆")):
        roles.append("witness")
    if any(word in joined for word in ("宮殿", "公的", "社会", "部屋の人物")):
        roles.append("authority_or_community")
    if any(word in joined for word in ("偽", "候補", "失敗")):
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
    blueprint = _apply_story_scene_to_blueprint(
        _scene_blueprint(
            profile=profile,
            idx=idx,
            title=title,
            location_name=location_name,
            include_artifact=include_artifact,
        ),
        profile=profile,
        idx=idx,
    )
    event_text = " / ".join(source_events)
    visual_evidence = list(blueprint["visible_evidence"])
    required_roles = _event_required_roles(event_text)
    return [
        {
            "event_id": f"scene{idx:02d}_story_event",
            "source_events": source_events,
            "audience_knowledge_delta": f"観客は「{blueprint['causal_turn']}」が「{event_text}」から生じた不可逆な出来事だと理解する",
            "causal_proof": f"{blueprint['handoff_anchor']}が、{title}の原因と結果を説明なしに結びつける",
            "visual_evidence": visual_evidence,
            "required_roles": required_roles,
            "static_first_frame_rule": "動作中の説明ではなく、原因・結果・証人・物的証拠が一枚で読める静止状態にする",
            "anti_redundancy_key": "story_event_irreversible_fact",
        }
    ]


def _adaptation_source_contract_for_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Build the adaptation value root used by downstream contracts."""

    protagonist = str(profile.get("protagonist_name") or "主人公").strip()
    artifact = str(profile.get("artifact_name") or "物語の証拠").strip()
    raw_event_ids = profile.get("research_event_ids")
    event_ids = [str(value).strip() for value in raw_event_ids or [] if str(value).strip()]
    event_refs = event_ids or ["research.story_materials.chronological_events"]
    return {
        "schema_version": "adaptation_source_contract_v1",
        "mode": "existing_story",
        "authoring_provenance": "story_authoring_projection",
        "source_story_promise": f"{protagonist}が圧力の中でも失わなかった価値を、選択と{artifact}の証明によって取り戻す。",
        "core_values": [
            {
                "value_id": "value_dignity_recognized",
                "statement": f"見過ごされていた{protagonist}の尊厳が、外見だけでなく存在と行為によって認識される。",
                "audience_effect": "耐えてきた時間が報われ、自分の価値を見つけ直す安堵と高揚。",
                "source_event_refs": event_refs,
            },
            {
                "value_id": "value_choice_under_pressure",
                "statement": f"{protagonist}が制約や時間圧力の中でも、自分で次の一歩を選ぶ。",
                "audience_effect": "受動的に救われるのではなく、選択が運命を動かす緊張と希望。",
                "source_event_refs": event_refs,
            },
            {
                "value_id": "value_proof_and_release",
                "statement": f"{artifact}が所有物ではなく、隠されていた真実と関係を公にする証拠になる。",
                "audience_effect": "積み重ねた因果が一つの物証へ収束する納得と解放。",
                "source_event_refs": event_refs,
            },
        ],
        "non_negotiable_events": [
            "主人公を拘束する初期状態が具体的な出来事として示される",
            "主人公自身の選択が転換を発生させる",
            f"{artifact}が終盤の照合または真実の証明に働く",
        ],
        "non_negotiable_meanings": [
            "救済を外見や地位の獲得だけに縮小しない",
            "主人公を他者が受け取る賞品としてだけ描かない",
            "結末の解放を、それ以前の選択と因果から切り離さない",
        ],
        "iconic_moments": [
            "日常の拘束から可能性が開く瞬間",
            f"時間または社会的圧力の中で{protagonist}が選択する瞬間",
            f"{artifact}によって真実が認識される瞬間",
        ],
        "forbidden_value_distortions": [
            "豪華な衣装・場所・魔法だけで感動を代替する",
            "主人公の選択を削り、偶然や権力者だけで解決する",
            "原作の主要因果をgeneric montageへ置き換える",
        ],
    }


def _adaptation_contract_from_profile(profile: dict[str, Any]) -> dict[str, Any]:
    existing = profile.get("adaptation_source_contract")
    if isinstance(existing, dict) and existing:
        return deepcopy(existing)
    return _adaptation_source_contract_for_profile(profile)


def _adaptation_value_ids_for_profile(profile: dict[str, Any]) -> list[str]:
    return [
        str(value.get("value_id") or "").strip()
        for value in _adaptation_contract_from_profile(profile).get("core_values", [])
        if isinstance(value, dict) and str(value.get("value_id") or "").strip()
    ]


def _scene_value_amplification_for_profile(
    *,
    profile: dict[str, Any],
    idx: int,
    title: str,
) -> dict[str, Any]:
    authored_amplifications = profile.get("scene_value_amplifications")
    if isinstance(authored_amplifications, dict):
        runtime_scene_id = _runtime_scene_id(idx)
        for selector in (
            str(runtime_scene_id),
            f"scene{runtime_scene_id}",
            str(idx),
            f"scene{idx}",
            f"scene{idx:02d}",
        ):
            authored = authored_amplifications.get(selector)
            if isinstance(authored, dict) and authored:
                return deepcopy(authored)
        raise RuntimeError(
            "authored visual_value.md is missing scene_value_amplification "
            f"for scene{idx}; deterministic fallback is forbidden"
        )
    value_ids = _adaptation_value_ids_for_profile(profile)
    if not value_ids:
        value_ids = ["value_dignity_recognized"]
    scene_count = max(1, len(profile.get("scene_titles") or []))
    if idx >= scene_count:
        source_value_ref = value_ids[min(2, len(value_ids) - 1)]
    elif idx <= max(1, scene_count // 3):
        source_value_ref = value_ids[min(1, len(value_ids) - 1)]
    else:
        source_value_ref = value_ids[0]
    protagonist = str(profile.get("protagonist_name") or "主人公").strip()
    artifact = str(profile.get("artifact_name") or "物語の証拠").strip()
    motifs = [str(value).strip() for value in profile.get("motifs") or [] if str(value).strip()]
    motif_text = "・".join(motifs[:3]) or "光・距離・呼吸"
    return {
        "schema_version": "scene_value_amplification_v1",
        "source_value_refs": [source_value_ref],
        "why_this_scene_matters": f"「{title}」で{protagonist}の選択・認識・証拠のいずれかを不可逆に進め、原作の価値を次sceneへ渡す。",
        "audience_state_before": f"観客は{protagonist}がまだ「{title}」の圧力を越えられるか確信していない。",
        "audience_state_after": f"観客は「{title}」で生じた選択または証拠が、後続の解放を必然にしたと理解する。",
        "emotional_contradiction": "希望が開くほど、失敗したときに失うものと時間圧力も強くなる。",
        "cinematic_gain": {
            "performance": f"{protagonist}の感情を名称で説明せず、呼吸、視線、手の停止、重心の変化で抑制から選択へ移す。",
            "blocking_and_space": f"「{title}」の遮蔽・距離・出口を使い、孤立した配置から自分で進路を取る配置へ変える。",
            "camera_and_composition": f"{motif_text}を装飾ではなく認識の手掛かりにし、出来事より先に結果を見せない。",
            "edit_and_rhythm": "原因を読ませるhold、選択の瞬間、他者または空間のreaction、余韻の順を守る。",
            "sound": "環境音の密度を圧力として使い、転換直前の沈黙と出来事後に残る具体音で因果を強める。",
        },
        "iconic_moment_target": f"{protagonist}と{artifact}または周囲の視線の関係が、一瞬で別の意味へ変わる瞬間。",
        "must_preserve_story_facts": [
            f"「{title}」を成立させるsource eventの順序と因果を変えない",
            "後続sceneで成立する証明や解決を早出ししない",
        ],
        "must_not_reduce_to": [
            f"{title}の場所や衣装を紹介するだけの説明映像",
            "感情語を光や表情で一対一に図解するgeneric montage",
        ],
        "success_evidence": [
            "ナレーションなしでも、scene前後で主人公の選択可能性または社会的な位置が変わったと読める",
            "次sceneを発生させる物理的・視覚的・聴覚的な因果が画面に残る",
        ],
    }


def _adaptation_intent_for_profile(profile: dict[str, Any]) -> dict[str, Any]:
    protagonist = str(profile.get("protagonist_name") or "主人公").strip()
    return {
        "schema_version": "adaptation_intent_v1",
        "source_value_ids": _adaptation_value_ids_for_profile(profile),
        "effect_fidelity_goal": "原作で評価された尊厳、選択、証明の感情曲線を、観客が身体的な距離と時間として再体験できるようにする。",
        "adaptation_angle": f"{protagonist}を救済される対象としてだけ見せず、圧力の中で選び、見返し、因果を次へ渡す主体として再発見させる。",
        "visual_principles": ["人物間の距離、遮蔽、進路、物証の位置関係で価値変化を見せる"],
        "performance_principles": ["感情名ではなく呼吸、視線、手、重心の抑制と解放で演じる"],
        "sound_principles": ["環境音の圧力、転換前の沈黙、出来事後の残響で因果を感じさせる"],
        "editorial_principles": ["出来事の前に結果を見せず、認識とreactionを読む時間を確保する"],
        "forbidden_generic_treatments": ["豪華さだけのspectacle", "説明的montage", "全cut同じ距離とテンポ"],
    }


def _cut_expressive_contract_for_scaffold(
    *,
    scene_id: int | str,
    scene_amplification: dict[str, Any],
    cut_function: str,
    focal_character_name: str,
    visual_beat: str,
    motion_brief: str,
    motion_end_state: str,
) -> dict[str, Any]:
    function_map = {
        "setup": "withhold",
        "context": "withhold",
        "reveal_hold": "withhold",
        "pressure": "pressure",
        "threshold": "contrast",
        "turn": "reframe",
        "payoff": "recognition",
        "proof": "recognition",
        "event_proof": "recognition",
        "reaction": "reaction",
        "handoff": "transition",
        "custom": "reframe",
    }
    normalized_cut_function = str(cut_function).strip()
    if normalized_cut_function.endswith("_detail"):
        normalized_cut_function = normalized_cut_function.removesuffix("_detail")
    if normalized_cut_function not in function_map:
        raise ValueError(f"unsupported cut_function for expressive contract: {normalized_cut_function or '(empty)'}")
    expressive_function = function_map[normalized_cut_function]
    return {
        "schema_version": "cut_expressive_contract_v1",
        "source_value_refs": list(scene_amplification.get("source_value_refs") or []),
        "scene_amplification_ref": f"scene{scene_id}.scene_intent.scene_value_amplification",
        "audience_experience_delta": f"{visual_beat}を情報として知る前の予測から、その因果を画面上の事実として受け取る状態へ移る。",
        "expressive_function": expressive_function,
        "performance_beat": f"{focal_character_name}が、{motion_brief}の前後で呼吸・視線・重心のいずれかを一度だけ変える。",
        "visual_pressure": f"{visual_beat}を妨げる距離・遮蔽・画面内運動を残し、解決前に圧力を読ませる。",
        "attention_shift": f"周囲の状況から、{focal_character_name}の選択とその結果へ注意を移す。",
        "edit_trigger": f"{motion_end_state}が画面で成立し、観客が因果を読めた瞬間に次へ切る。",
        "sound_function": "環境音を圧力として保ち、選択の直前だけ密度を下げ、結果を示す具体音を残す。",
        "emotional_afterimage": f"{focal_character_name}の一つの行為が次の出来事を避けられなくした感覚。",
        "must_not_reduce_to": ["人物や場所の紹介だけのショット", "感情語を表情だけで図解するショット"],
    }


def _scene_intent_for_cut_design(
    *,
    title: str,
    idx: int,
    location_spec: dict[str, Any],
    profile: dict[str, Any],
    include_artifact: bool,
) -> dict[str, Any]:
    is_terminal = idx == len(profile["scene_titles"])
    canonical_index = _canonical_scene_index(profile, idx)
    artifact_has_been_revealed = idx >= _artifact_first_scene_index(profile)
    story_event_obligations = _story_event_obligations_for_scene(
        title=title,
        idx=idx,
        location_name=str(location_spec["name"]),
        profile=profile,
        include_artifact=include_artifact,
    )
    blueprint = _apply_story_scene_to_blueprint(
        _scene_blueprint(
            profile=profile,
            idx=idx,
            title=title,
            location_name=str(location_spec["name"]),
            include_artifact=include_artifact,
        ),
        profile=profile,
        idx=idx,
    )
    visible_evidence = list(blueprint["visible_evidence"])
    audience_information = [f"{title}の場所と主人公の現在位置", "主人公が何に妨げられているか"]
    if canonical_index in {2, 5, 6}:
        audience_information.append("周囲の視線や場のルール")
    if canonical_index in {4, 7}:
        audience_information.append("移動や時間制限によって状況が変わること")
    withheld_information = [] if artifact_has_been_revealed else [profile["artifact_name"]]
    if canonical_index == 7:
        withheld_information.append("時間制限の結果")
    reveal_constraints = [] if artifact_has_been_revealed else [f"{profile['artifact_name']}はこのsceneでは見せない"]
    if is_terminal:
        reveal_constraints = ["終端後の新しい解決や別の証拠を足さない"]
    value_to = str(blueprint["value_to"])
    causal_turn = str(blueprint["causal_turn"])
    if is_terminal:
        causal_turn = str(blueprint["causal_turn"])
    authored_turn = str(_story_scene(profile, idx).get("turn") or "").strip()
    if authored_turn:
        causal_turn = authored_turn
    done_when = (
        f"{title}の問い、終結、物証の一致が、人物・場所・光・{profile['artifact_name']}の関係で説明なしに読める"
        if is_terminal
        else f"{title}の問い、状態差、因果の受け渡しが、人物・場所・光・必要な証拠の関係で説明なしに読める"
    )
    screen_geography = (
        f"{location_spec['name']}の前景/中景/背景が、出口ではなく主人公と{profile['artifact_name']}へ収束する"
        if is_terminal
        else f"{location_spec['name']}の前景/中景/背景と出口方向を固定する"
    )
    intent = {
        "story_purpose": blueprint["story_purpose"],
        "scene_value_amplification": _scene_value_amplification_for_profile(
            profile=profile,
            idx=idx,
            title=title,
        ),
        "story_overview_visualizable_action": str(
            blueprint.get("story_overview_visualizable_action") or ""
        ),
        "dramatic_question": blueprint["dramatic_question"],
        "scene_spine": blueprint["scene_spine"],
        "value_shift": {
            "from": blueprint["value_from"],
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
            "still_unknown_after_scene": withheld_information or ["このsceneで新たに伏せる情報はなく、既存の証拠だけを回収する"],
            "forbidden_early_reveals": reveal_constraints or ["後続sceneの物証を先に確定しない"],
        },
        "withheld_information": withheld_information,
        "reveal_constraints": reveal_constraints,
        "affect_transition": f"{blueprint['visible_pressure'][0]}による緊張から、{blueprint['handoff_anchor']}を見た理解へ移る",
        "character_state": {
            "start": blueprint["character_start"],
            "end": blueprint["character_end"],
            "visible_behavior": [
                f"{profile['protagonist_name']}の手元",
                "顔の向き",
                "足元の重心",
                blueprint["visible_pressure"][0],
            ],
        },
        "story_specificity": {
            "non_compressible_beat": blueprint["causal_turn"],
            "scene_promotion_reason": f"{title}は「{blueprint['causal_turn']}」を独立して成立させるため、別sceneとして必要",
            "unique_scene_responsibility": f"{blueprint['handoff_anchor']}を後続sceneの物理的原因として残す",
            "actor_forces": {
                "protagonist": profile["protagonist_name"],
                "opposing_or_limiting_force": blueprint["obstacle"],
                "pressure_method": blueprint["visible_pressure"],
                "witness_or_authority": [role for role in _event_required_roles(' / '.join(blueprint["source_events"])) if role != "protagonist"] or ["場所または周囲の反応"],
            },
            "meaning_ladder": {
                "object_or_trace": blueprint["handoff_anchor"],
                "scene_function": blueprint["payoff"],
                "story_function": blueprint["causal_turn"],
            },
            "concrete_handoff": {
                "incoming_trigger": blueprint["incoming_trigger"],
                "outgoing_anchor": blueprint["handoff_anchor"],
                "outgoing_pressure": blueprint["outgoing_pressure"],
            },
            "anti_template_language": {
                "banned_generic_phrases_absent": True,
                "story_specific_terms": blueprint["story_terms"],
                "specificity_note": "物語名だけでなく、人物・場所・物証・行為の組み合わせでsceneを固定する",
            },
        },
        "visual_value_source": {
            "source": "scene_blueprint",
            "visual_terms": visible_evidence,
            "source_events": blueprint["source_events"],
        },
        "production_risks": [
            "物証を早出ししない",
            "人物の内面説明だけでsceneを閉じない",
            "同じ証拠の反復ならcutを増やさずpromptを厚くする",
        ],
        "handoff_notes": {
            "incoming": blueprint["incoming_trigger"],
            "outgoing": blueprint["handoff_anchor"],
            "next_scene": "" if is_terminal else _next_scene_title(profile, idx),
        },
        "scene_conflict_engine": {
            "desire": blueprint["desire"],
            "obstacle": blueprint["obstacle"],
            "stakes": blueprint["stakes"],
            "escalation": blueprint["escalation"],
            "no_return_point": blueprint["no_return_point"],
            "visible_pressure": blueprint["visible_pressure"],
        },
        "handoff_chain": {
            "incoming": {
                "anchor_type": "source_event" if idx == 1 else "physical_or_audible_trace",
                "visible_or_audible_form": blueprint["incoming_trigger"],
            },
            "outgoing": {
                "anchor_id": f"scene{idx:02d}_handoff",
                "anchor_type": "terminal" if is_terminal else "physical_or_audible_trace",
                "visible_or_audible_form": blueprint["handoff_anchor"],
                "next_scene_selector": "" if is_terminal else f"scene{_runtime_scene_id(idx + 1)}",
                "required_next_scene_start_pressure": blueprint["outgoing_pressure"],
            },
        },
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
        "handoff_to_next_scene": f"{title}の出口側に残る光と人物の視線が、まだ画面内の導線を指す" if not is_terminal else "",
        "terminal_resolution": f"{profile['artifact_name']}が主人公の価値を証明する" if is_terminal else "",
    }
    authored_scene = _story_scene(profile, idx)
    for key in ("start_state", "end_state", "handoff_chain", "preservation", "reveal_contract"):
        if isinstance(authored_scene.get(key), dict):
            intent[key] = deepcopy(authored_scene[key])
    intent["authored_scene_id"] = str(authored_scene.get("scene_id") or "").strip()
    return intent






def _legacy_scene_event_for_cut_design(
    *,
    title: str,
    idx: int,
    scene_intent: dict[str, Any],
    location_name: str,
    location_id: str = "",
    profile: dict[str, Any],
    include_artifact: bool,
) -> dict[str, Any]:
    protagonist = str(profile["protagonist_name"])
    artifact = str(profile["artifact_name"])
    source_story_beat_id = f"story_scene{idx:02d}_primary"
    source_events = _scene_source_events(profile, idx)
    research_refs = _downstream_scene_research_refs(idx, source_events, profile)
    blueprint = _apply_story_scene_to_blueprint(
        _scene_blueprint(
            profile=profile,
            idx=idx,
            title=title,
            location_name=location_name,
            include_artifact=include_artifact,
        ),
        profile=profile,
        idx=idx,
    )
    source_summary = " / ".join(source_events) if source_events else str(profile.get("summary") or title)
    visible_evidence = scene_intent.get("value_shift", {}).get("visible_evidence", []) if isinstance(scene_intent.get("value_shift"), dict) else []
    evidence_terms = [str(item) for item in visible_evidence if str(item).strip()][:4] or [location_name, protagonist]
    artifact_clause = f"と{artifact}" if include_artifact else ""
    source_fact_setup = source_events[0] if source_events else f"{title}で{protagonist}が{location_name}の制約に置かれる"
    source_fact_pressure = source_events[1] if len(source_events) > 1 else source_fact_setup
    source_fact_turn = str(scene_intent.get("causal_turn") or blueprint["causal_turn"])
    source_fact_payoff = str(blueprint["payoff"])
    visible_pressure = [
        str(item).strip()
        for item in blueprint.get("visible_pressure") or []
        if str(item).strip()
    ]
    pressure_anchor = visible_pressure[0] if visible_pressure else f"{location_name}の床"
    pressure_source = str(
        blueprint.get("pressure_source")
        or (visible_pressure[1] if len(visible_pressure) > 1 else blueprint["obstacle"])
    ).strip()
    pressure_source_visible_from = str(
        blueprint.get("pressure_source_visible_from") or "setup"
    ).strip()
    turn_motion_target = str(
        blueprint.get("turn_motion_target") or pressure_anchor
    ).strip()
    payoff_focus = str(
        blueprint.get("payoff_focus") or turn_motion_target
    ).strip()
    setup_pressure_source = (
        pressure_source
        if pressure_source_visible_from == "setup"
        else pressure_anchor
    )
    pressure_evidence = (
        f"{pressure_source}、{pressure_anchor}"
        if pressure_source_visible_from != "setup"
        else ("、".join(visible_pressure[:3]) or pressure_anchor)
    )
    setup_visible_action = (
        f"{protagonist}は{location_name}で{pressure_anchor}のそばに留まり、"
        f"片手の動きを止め、顔を{setup_pressure_source}へ向けている"
    )
    setup_visible_reaction = (
        f"{pressure_anchor}が{protagonist}の手元と出入口の間にあり、"
        "足先と重心はその場で止まっている"
    )
    pressure_visible_action = (
        f"{protagonist}は{pressure_anchor}のそばで手を止め、肩をすぼめ、"
        f"顔を{pressure_source}へ向け、足先を出入口から外している"
    )
    pressure_visible_reaction = (
        f"{pressure_evidence}が同じ画面にあり、"
        f"{protagonist}から出入口までの導線を狭めている"
    )
    if turn_motion_target == pressure_anchor:
        default_turn_motion = (
            f"{protagonist}が{turn_motion_target}へ片手を一度だけ伸ばす"
        )
        default_turn_end_state = (
            f"{protagonist}の指先が{turn_motion_target}の手前で止まっている"
        )
    else:
        default_turn_motion = (
            f"{protagonist}が{pressure_anchor}から{turn_motion_target}へ"
            "顔を一度だけゆっくり向ける"
        )
        default_turn_end_state = (
            f"{protagonist}の顔が{turn_motion_target}へ向き、"
            f"片手は{pressure_anchor}のそばで止まっている"
        )
    default_motion_by_function = {
        "setup": (
            f"{protagonist}が{setup_pressure_source}から出入口へ顔をゆっくり向け、"
            f"片手は{pressure_anchor}のそばに残す"
        ),
        "pressure": (
            f"{protagonist}が片足を{pressure_anchor}側へ短く一度だけ引く"
        ),
        "turn": default_turn_motion,
        "payoff": (
            f"{protagonist}が{payoff_focus}へ顔をゆっくり向け、"
            "肩を一度だけ下げる"
        ),
    }
    default_motion_end_by_function = {
        "setup": (
            f"{protagonist}の顔が出入口を向き、"
            f"片手が{pressure_anchor}のそばで止まっている"
        ),
        "pressure": (
            f"{protagonist}の足先と重心が{pressure_anchor}側へ戻り、"
            "出入口との間に距離が残っている"
        ),
        "turn": default_turn_end_state,
        "payoff": (
            f"{protagonist}の肩が下がり、"
            f"視線が{payoff_focus}に残っている"
        ),
    }
    location_specs = _location_specs_for_scene_sequence(profile, idx)
    location_spec_by_name = {
        str(spec.get("name") or ""): spec for spec in location_specs
    }
    location_sequence = [str(spec.get("name") or "") for spec in location_specs]
    location_segments = _scene_location_segments(profile, idx)
    location_segment_by_name = {
        str(segment.get("location") or ""): segment
        for segment in location_segments
        if str(segment.get("location") or "")
    }
    turn_visible_action = (
        f"{protagonist}の衣装と足元、{pressure_anchor}の周囲に、"
        f"{'、'.join(visible_pressure[1:])}が実物として整っている"
        if pressure_source_visible_from != "setup" and len(visible_pressure) > 1
        else f"{protagonist}は{pressure_anchor}のそばで手を止め、顔を{pressure_anchor}へ向けている"
    )
    turn_visible_reaction = (
        f"{pressure_anchor}と{turn_motion_target}が同じ画面にあり、"
        f"{protagonist}の片手は{pressure_anchor}のそばで止まっている"
    )
    payoff_visible_action = (
        f"{payoff_focus}が前景に残り、{protagonist}はその近くで身体を止めている"
    )
    payoff_visible_reaction = (
        f"{protagonist}の視線が{payoff_focus}へ向き、肩と手元は動きを止めている"
    )
    beat_specs = [
        (
            "setup",
            source_fact_setup,
            setup_visible_action,
            setup_visible_reaction,
            "sceneの問いと開始状況が観客に確定する",
            "まだ動けない圧力が見える",
        ),
        (
            "pressure",
            source_fact_pressure,
            pressure_visible_action,
            pressure_visible_reaction,
            "迷いが具体的な行為の直前まで進む",
            "不安や期待が上がる",
        ),
        (
            "turn",
            source_fact_turn,
            turn_visible_action,
            turn_visible_reaction,
            "scene内の状態差が物語上の事実になる",
            "不可逆な決断が画面に固定される",
        ),
        (
            "payoff",
            source_fact_payoff,
            payoff_visible_action,
            payoff_visible_reaction,
            (
                "終結の証明が成立する"
                if scene_intent.get("terminal_resolution")
                else "次のsceneの開始理由が成立する"
            ),
            "変化後の余韻が残る",
        ),
    ]
    raw_beat_overrides = (
        blueprint.get("beat_overrides")
        if isinstance(blueprint.get("beat_overrides"), dict)
        else {}
    )
    artifact_was_revealed = any(
        _scene_artifact_state(profile, prior_scene_index)
        in {"focal", "carried"}
        for prior_scene_index in range(1, idx)
    )
    event_sequence = []
    for beat_index, (
        function,
        what_happens,
        visible_action,
        visible_reaction,
        consequence,
        pressure,
    ) in enumerate(beat_specs):
        raw_function_override = (
            raw_beat_overrides.get(function)
            if isinstance(raw_beat_overrides.get(function), dict)
            else {}
        )
        beat_location_name = str(
            raw_function_override.get("location")
            or location_sequence[min(beat_index, len(location_sequence) - 1)]
        ).strip()
        if beat_location_name not in location_spec_by_name:
            raise RuntimeError(
                f"scene{idx:02d} {function}: beat location is not declared in "
                f"scene_location_sequence: {beat_location_name}"
            )
        beat_location_spec = location_spec_by_name[beat_location_name]
        location_segment = location_segment_by_name.get(beat_location_name, {})
        location_beat_overrides = (
            location_segment.get("beat_overrides")
            if isinstance(location_segment.get("beat_overrides"), dict)
            else {}
        )
        beat_override = {
            **raw_function_override,
            **(
                location_beat_overrides.get(function)
                if isinstance(location_beat_overrides.get(function), dict)
                else {}
            ),
        }
        root_scope = location_segment.get("root_active_beat_functions")
        root_is_active = (
            "root_active_beat_functions" not in location_segment
            or (
                isinstance(root_scope, list)
                and function in {str(item) for item in root_scope}
            )
        )
        semantic_segment = location_segment if root_is_active else {}
        if semantic_segment or beat_override:
            what_happens = str(
                beat_override.get("what_happens")
                or semantic_segment.get("responsibility")
                or what_happens
            )
            visible_action = str(
                beat_override.get("visible_action")
                or semantic_segment.get("visible_action")
                or visible_action
            )
            visible_reaction = str(
                beat_override.get("visible_reaction")
                or semantic_segment.get("visible_reaction")
                or visible_reaction
            )
        artifact_visible_in_beat = bool(
            include_artifact
            and (
                semantic_segment
                or beat_override
                or function in {"turn", "payoff"}
            )
        )
        artifact_continuity_state = (
            "focal"
            if artifact_visible_in_beat
            else "carried"
            if artifact_was_revealed
            else "not_yet_revealed"
        )
        if artifact_visible_in_beat:
            artifact_was_revealed = True
        beat_id = f"scene{idx:02d}_event_{function}"
        if semantic_segment or beat_override:
            primary_subject_by_function = (
                semantic_segment.get("primary_subject_by_function")
                if isinstance(
                    semantic_segment.get("primary_subject_by_function"), dict
                )
                else {}
            )
            primary_subject = str(
                beat_override.get("primary_subject")
                or primary_subject_by_function.get(function)
                or semantic_segment.get("primary_subject")
                or protagonist
            )
            required_roles = [
                str(item).strip()
                for item in (
                    beat_override.get("required_roles")
                    or semantic_segment.get("required_roles")
                    or []
                )
                if str(item).strip()
            ]
            segment_evidence = [
                str(item).strip()
                for item in (
                    beat_override.get("required_visual_evidence")
                    or semantic_segment.get("required_visual_evidence")
                    or []
                )
                if str(item).strip()
            ]
            visual_evidence_for_beat = list(
                dict.fromkeys([beat_location_name, *segment_evidence])
            )[:6]
        else:
            primary_subject = protagonist
            scoped_evidence_terms = [
                term
                for term in evidence_terms
                if not any(
                    other_location in term
                    for other_location in location_sequence
                    if other_location != beat_location_name
                )
                and (artifact_visible_in_beat or artifact not in term)
                and not (
                    pressure_source_visible_from != "setup"
                    and function in {"setup", "pressure"}
                    and term != pressure_anchor
                )
            ]
            visual_evidence_for_beat = list(
                dict.fromkeys(
                    [
                        beat_location_name,
                        protagonist,
                        *scoped_evidence_terms,
                        *([artifact] if artifact_visible_in_beat else []),
                    ]
                )
            )[:6]
            required_roles = _visible_character_role_ids(
                profile=profile,
                primary_subject=primary_subject,
                visible_text=" / ".join(
                    [visible_action, visible_reaction, *visual_evidence_for_beat]
                ),
            )
        if not required_roles:
            required_roles = _visible_character_role_ids(
                profile=profile,
                primary_subject=primary_subject,
                visible_text=" / ".join(
                    [visible_action, visible_reaction, *visual_evidence_for_beat]
                ),
            )
        if isinstance(beat_override.get("visible_character_state"), dict) and beat_override.get("visible_character_state"):
            visible_character_state = dict(beat_override["visible_character_state"])
        elif isinstance(semantic_segment.get("visible_character_state"), dict) and semantic_segment.get("visible_character_state"):
            visible_character_state = dict(semantic_segment["visible_character_state"])
        elif semantic_segment:
            visible_character_state = {
                "posture": visible_action,
                "gaze": visible_reaction,
            }
        elif function == "setup":
            visible_character_state = {
                "posture": (
                    f"{pressure_anchor}のそばで片手の動きを止め、"
                    f"顔を{setup_pressure_source}へ向けた姿勢"
                ),
                "gaze": f"{setup_pressure_source}へ向く視線",
                "expression": "口元を閉じ、相手の圧力を受け止めている表情",
                "hands": f"{primary_subject}の片手が{pressure_anchor}のそばで止まっている",
                "feet": "足先と重心がその場で止まっている",
            }
        elif function == "pressure":
            visible_character_state = {
                "posture": (
                    f"{pressure_anchor}のそばで手を止め、肩をすぼめ、"
                    f"顔を{pressure_source}へ向けた姿勢"
                ),
                "gaze": f"{pressure_source}へ向く視線",
                "expression": "肩と眉に緊張が残り、口元を閉じている表情",
                "hands": f"{primary_subject}の手が{pressure_anchor}のそばで止まっている",
                "feet": f"足先が出入口から外れ、重心が{pressure_anchor}側に残っている",
            }
        else:
            visible_character_state = {
                "posture": visible_action,
                "gaze": (
                    f"{payoff_focus}へ向く視線"
                    if function == "payoff"
                    else f"{turn_motion_target}へ向く視線"
                ),
                "expression": (
                    "肩と眉の緊張がほどけ、口元を閉じた表情"
                    if function == "payoff"
                    else "直前の出来事への集中が残る表情"
                ),
                "hands": f"{primary_subject}の手元が直前の行為を終えた位置で止まっている",
                "feet": "両足と重心が行為後の位置で止まっている",
            }
        if semantic_segment or beat_override:
            motion_attention_target = str(
                beat_override.get("motion_attention_target")
                or next(
                    (
                        item
                        for item in visual_evidence_for_beat
                        if item not in {beat_location_name, primary_subject}
                    ),
                    beat_location_name,
                )
            )
        elif function == "setup":
            motion_attention_target = "画面内の出入口"
        elif function == "pressure":
            motion_attention_target = pressure_source
        else:
            motion_attention_target = (
                payoff_focus if function == "payoff" else turn_motion_target
            )
        source_event_text = str(what_happens or source_summary)
        motion_brief = str(
            beat_override.get("motion_brief")
            or semantic_segment.get("motion_brief")
            or default_motion_by_function[function]
        ).strip()
        motion_end_state = str(
            beat_override.get("motion_end_state")
            or semantic_segment.get("motion_end_state")
            or default_motion_end_by_function[function]
        ).strip()
        # First-frame asset, reveal, and next-frame binding policies are all
        # exact-obligation data. Function/segment roots stay inert so one
        # authored policy cannot affect sibling semantic obligations.
        first_frame_character_asset_overrides: dict[str, str] = {}
        first_frame_excluded_object_ids: list[str] = []
        allowed_new_reveal_elements: list[str] = []
        allowed_reveal_info_ids: list[str] = []
        use_next_cut_first_frame_as_last_frame = False
        obligation_overrides = deepcopy(
            beat_override.get("obligation_overrides")
            if isinstance(beat_override.get("obligation_overrides"), dict)
            else {}
        )
        visible_character_state_source = (
            "beat_override"
            if isinstance(beat_override.get("visible_character_state"), dict)
            and beat_override.get("visible_character_state")
            else (
                "location_segment"
                if isinstance(semantic_segment.get("visible_character_state"), dict)
                and semantic_segment.get("visible_character_state")
                else "inferred"
            )
        )
        concrete_story_elements = _concrete_story_elements_for_beat(
            beat_id=beat_id,
            profile=profile,
            location_name=beat_location_name,
            source_event_text=source_event_text,
            visual_evidence=visual_evidence_for_beat,
            include_artifact=artifact_visible_in_beat,
        )
        event_sequence.append(
            {
                "beat_id": beat_id,
                "beat_function": function,
                "source_story_beat_ids": [source_story_beat_id],
                "abstract_function": {
                    "dramatic_job": f"{title}の{function}として見る側の理解を一段進める",
                    "value_shift_role": str(
                        scene_intent.get("value_shift", {}).get("to")
                        if isinstance(scene_intent.get("value_shift"), dict)
                        else "状態差を物証で進める"
                    ),
                    "emotional_pressure_role": pressure,
                    "causal_role": consequence,
                },
                "concrete_event": {
                    "who": required_roles,
                    "primary_subject": primary_subject,
                    "where": beat_location_name,
                    "what_happens": source_event_text,
                    "conflict_or_constraint": blueprint["obstacle"],
                    "object_or_trace": (
                        [artifact]
                        if artifact_continuity_state == "focal"
                        else [
                            f"{artifact}は既にreveal済みで人物に携行されるが、この beat の焦点ではない"
                        ]
                        if artifact_continuity_state == "carried"
                        else [f"{artifact}はまだ出さない"]
                    ),
                    "artifact_continuity_state": artifact_continuity_state,
                    "visible_action": visible_action,
                    "visible_reaction": visible_reaction,
                    "immediate_consequence": consequence,
                    "required_visual_evidence": visual_evidence_for_beat,
                    "motion_brief": motion_brief,
                    "motion_end_state": motion_end_state,
                    "first_frame_character_asset_overrides": first_frame_character_asset_overrides,
                    "first_frame_excluded_object_ids": first_frame_excluded_object_ids,
                    "allowed_new_reveal_elements": allowed_new_reveal_elements,
                    "allowed_reveal_info_ids": allowed_reveal_info_ids,
                    "use_next_cut_first_frame_as_last_frame": use_next_cut_first_frame_as_last_frame,
                    "visible_character_state": visible_character_state,
                    "visible_character_state_source": visible_character_state_source,
                    "motion_attention_target": motion_attention_target,
                    "obligation_overrides": obligation_overrides,
                },
                "story_grounding": {
                    "source_story_beat_ids": [source_story_beat_id],
                    "research_refs": research_refs,
                    "source_origin": _source_origin_for_profile(profile),
                    "source_confidence": "high" if source_events else "medium",
                    "source_text_or_summary": source_event_text,
                    "adaptation_reason": "source story の出来事を、静止画とcut設計で読める物理的証拠へ変換するため",
                    "human_approval_required": False,
                    "non_replaceable_elements": _non_replaceable_elements_for_beat(
                        profile=profile,
                        location_name=beat_location_name,
                        source_event_text=source_event_text,
                        include_artifact=artifact_visible_in_beat,
                    ),
                    "replaceability_check": {
                        "would_survive_character_swap": False,
                        "would_survive_object_swap": False if include_artifact else True,
                        "would_survive_location_swap": False,
                        "note": "人物・場所・source出来事のいずれかを置換すると、このscene beatの意味が変わる",
                    },
                    "concrete_story_elements": concrete_story_elements,
                    "asset_story_function_usage": _asset_story_function_usage_for_beat(
                        beat_id=beat_id,
                        profile=profile,
                        location_id=str(beat_location_spec.get("asset_id") or location_id),
                        include_artifact=artifact_visible_in_beat,
                    ),
                    "confidence": "high" if source_events else "medium",
                },
                "specificity_budget": _specificity_budget(),
                "what_happens": source_event_text,
                "visible_action": visible_action,
                "visible_reaction": visible_reaction,
                "immediate_consequence": consequence,
                "emotional_pressure": pressure,
                "required_visual_evidence": visual_evidence_for_beat,
                "primary_subject": primary_subject,
                "required_roles": required_roles,
                "motion_brief": motion_brief,
                "motion_end_state": motion_end_state,
                "first_frame_character_asset_overrides": first_frame_character_asset_overrides,
                "first_frame_excluded_object_ids": first_frame_excluded_object_ids,
                "allowed_new_reveal_elements": allowed_new_reveal_elements,
                "allowed_reveal_info_ids": allowed_reveal_info_ids,
                "use_next_cut_first_frame_as_last_frame": use_next_cut_first_frame_as_last_frame,
                "visible_character_state": visible_character_state,
                "visible_character_state_source": visible_character_state_source,
                "motion_attention_target": motion_attention_target,
                "obligation_overrides": obligation_overrides,
                "story_information_revealed_ids": [f"scene{idx:02d}_{function}"],
            }
        )
    return {
        "schema_version": "scene_event_v1",
        "event_logline": f"{title}で「{blueprint['causal_turn']}」が起き、{blueprint['handoff_anchor']}が残る",
        "start_situation": blueprint["character_start"],
        "source_story_beat_ids": [source_story_beat_id],
        "research_refs": research_refs,
        "story_specificity": _story_specificity_layers(
            profile=profile,
            location_name=location_name,
            source_events=source_events,
            include_artifact=include_artifact,
        ),
        "event_sequence": event_sequence,
        "turning_event": {
            "source_event_beat_id": str(
                next(
                    (
                        beat.get("beat_id")
                        for beat in event_sequence
                        if beat.get("beat_function") == "turn"
                    ),
                    event_sequence[-1].get("beat_id") if event_sequence else "",
                )
            ),
            "causal_turn_ref": "scene_intent.causal_turn",
            "irreversible_change": str(scene_intent.get("causal_turn") or f"{title}の不可逆な変化"),
        },
        "end_situation": {
            "value_shift_to_ref": "scene_intent.value_shift.to",
            "outcome": str(scene_intent.get("value_shift", {}).get("to") if isinstance(scene_intent.get("value_shift"), dict) else blueprint["value_to"]),
            "character_position": blueprint["character_end"],
            "object_state": f"{artifact}は証拠として扱われる" if include_artifact else "必要な証拠が場所に残る",
            "relationship_state": "周囲との関係が、制限から認識または次の圧力へ変化する",
            "new_pressure": str(scene_intent.get("terminal_resolution") or scene_intent.get("handoff_to_next_scene") or "次sceneへ渡る圧力が残る"),
            "visible_evidence_refs": [
                str(
                    next(
                        (
                            beat.get("beat_id")
                            for beat in event_sequence
                            if beat.get("beat_function") == "payoff"
                        ),
                        event_sequence[-1].get("beat_id")
                        if event_sequence
                        else "",
                    )
                )
            ],
        },
        "offscreen_context": [str(item) for item in scene_intent.get("withheld_information", []) if str(item).strip()] or ["このscene外の出来事は画面で完了させない"],
        "forbidden_event_changes": [str(item) for item in scene_intent.get("reveal_constraints", []) if str(item).strip()] or ["scene_eventにない結末や新事実を追加しない"],
        "specificity_budget": _specificity_budget(),
    }


def _scene_event_for_cut_design(
    *,
    title: str,
    idx: int,
    scene_intent: dict[str, Any],
    location_name: str,
    location_id: str = "",
    profile: dict[str, Any],
    include_artifact: bool,
) -> dict[str, Any]:
    """Project authored lifecycle beats without replacing their semantics.

    The legacy compiler still supplies downstream production-only fields such
    as drawable evidence and motion boundaries. For story_scene_contract_v1,
    however, beat identity, order, function, event text, state, turn, and
    handoff remain owned by story.md and are overlaid after enrichment.
    """

    projected = _legacy_scene_event_for_cut_design(
        title=title,
        idx=idx,
        scene_intent=scene_intent,
        location_name=location_name,
        location_id=location_id,
        profile=profile,
        include_artifact=include_artifact,
    )
    authored_scene = _story_scene(profile, idx)
    authored_beats = authored_scene.get("event_sequence")
    if not isinstance(authored_beats, list) or not authored_beats:
        return projected

    templates = [
        beat
        for beat in projected.get("event_sequence", [])
        if isinstance(beat, dict)
    ]
    if not templates:
        raise RuntimeError(f"scene{idx}: legacy enrichment produced no beat template")
    enriched_beats: list[dict[str, Any]] = []
    research_refs = list(authored_scene.get("research_refs") or projected.get("research_refs") or [])
    for beat_index, authored in enumerate(authored_beats):
        if not isinstance(authored, dict):
            raise RuntimeError(f"scene{idx}: authored event_sequence contains a non-object beat")
        template = deepcopy(templates[min(beat_index, len(templates) - 1)])
        beat_id = str(authored.get("beat_id") or "").strip()
        beat_function = str(authored.get("beat_function") or "").strip()
        what_happens = str(authored.get("what_happens") or "").strip()
        visible_action = str(authored.get("visible_action") or what_happens).strip()
        visible_reaction = str(
            authored.get("visible_reaction")
            or template.get("visible_reaction")
            or "場所と人物の状態が行為後の配置に変わる"
        ).strip()
        consequence = str(authored.get("immediate_consequence") or "").strip()
        motion_brief = str(
            authored.get("motion_brief")
            or f"{visible_action}を発生させる一つの行為を行う（{beat_id}）"
        ).strip()
        motion_end_state = str(
            authored.get("motion_end_state")
            or f"{consequence}が画面上の結果として残る（{beat_id}）"
        ).strip()
        evidence = [
            str(value).strip()
            for value in authored.get("required_visual_evidence") or []
            if str(value).strip()
        ] or list(template.get("required_visual_evidence") or [])
        required_roles = [
            str(value).strip()
            for value in (
                authored.get("participants")
                or authored.get("character_ids")
                or template.get("required_roles")
                or []
            )
            if str(value).strip()
        ]
        template.update(deepcopy(authored))
        template.update(
            {
                "beat_id": beat_id,
                "beat_function": beat_function,
                "what_happens": what_happens,
                "visible_action": visible_action,
                "visible_reaction": visible_reaction,
                "immediate_consequence": consequence,
                "required_visual_evidence": evidence,
                "required_roles": required_roles,
                "motion_brief": motion_brief,
                "motion_end_state": motion_end_state,
            }
        )
        concrete_event = deepcopy(template.get("concrete_event") or {})
        concrete_event.update(
            {
                "what_happens": what_happens,
                "visible_action": visible_action,
                "visible_reaction": visible_reaction,
                "immediate_consequence": consequence,
                "required_visual_evidence": evidence,
                "motion_brief": motion_brief,
                "motion_end_state": motion_end_state,
            }
        )
        if required_roles:
            concrete_event["who"] = required_roles
        template["concrete_event"] = concrete_event
        grounding = deepcopy(template.get("story_grounding") or {})
        grounding["research_refs"] = research_refs
        grounding["source_text_or_summary"] = what_happens
        template["story_grounding"] = grounding
        enriched_beats.append(template)

    authored_turn = (
        authored_scene.get("turning_event")
        if isinstance(authored_scene.get("turning_event"), dict)
        else {}
    )
    projected["event_sequence"] = enriched_beats
    projected["turning_event"] = {
        **deepcopy(projected.get("turning_event") or {}),
        **deepcopy(authored_turn),
        "source_event_beat_id": str(
            authored_turn.get("beat_id")
            or authored_turn.get("source_event_beat_id")
            or ""
        ).strip(),
        "irreversible_change": str(
            authored_turn.get("irreversible_change")
            or authored_turn.get("change")
            or scene_intent.get("causal_turn")
            or ""
        ).strip(),
    }
    for key in ("start_state", "end_state", "handoff_chain", "preservation", "reveal_contract"):
        if isinstance(authored_scene.get(key), dict):
            projected[key] = deepcopy(authored_scene[key])
    projected["authored_scene_id"] = str(authored_scene.get("scene_id") or "").strip()
    return projected


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
                "audience_knowledge_delta": (
                    str(beat.get("audience_knowledge_delta") or "").strip()
                    or str(beat.get("immediate_consequence") or "").strip()
                ),
                "causal_proof": str(beat.get("visible_action") or "").strip(),
                "visual_evidence": [str(item) for item in beat.get("required_visual_evidence", []) if str(item).strip()] if isinstance(beat.get("required_visual_evidence"), list) else [],
                "required_roles": [
                    str(item).strip()
                    for item in (
                        beat.get("required_roles")
                        if isinstance(beat.get("required_roles"), list)
                        else (
                            beat.get("concrete_event", {}).get("who", [])
                            if isinstance(beat.get("concrete_event"), dict)
                            else []
                        )
                    )
                    if str(item).strip()
                ],
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
    cut_location: str,
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
    def project_cut_location(beat: dict[str, Any]) -> dict[str, Any]:
        projected = deepcopy(beat)
        if (
            cut_location
            and str(projected.get("beat_id") or "").strip() == primary_id
        ):
            concrete_event = (
                deepcopy(projected.get("concrete_event"))
                if isinstance(projected.get("concrete_event"), dict)
                else {}
            )
            concrete_event["where"] = cut_location
            projected["concrete_event"] = concrete_event
        return projected

    constraints = reveal_constraints if isinstance(reveal_constraints, list) else []
    return {
        "derived_from": ["scene_event.event_sequence[]", "cut_contract.source_event_contract"],
        "editable": False,
        "scene_event_logline": str(scene_event.get("event_logline") or ""),
        "primary_event_beat": project_cut_location(by_id.get(primary_id, {})),
        "source_event_beats": [
            project_cut_location(by_id[source_id])
            for source_id in source_ids
            if source_id in by_id
        ],
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
    source_event_sequence = [
        beat
        for beat in scene_event.get("event_sequence", [])
        if isinstance(beat, dict)
    ]

    def source_beat(function: str) -> dict[str, Any]:
        return next(
            (
                beat
                for beat in source_event_sequence
                if str(beat.get("beat_function") or "") == function
            ),
            {},
        )

    def drawable_beat_value(beat: dict[str, Any], key: str, fallback: str) -> str:
        concrete_event = (
            beat.get("concrete_event")
            if isinstance(beat.get("concrete_event"), dict)
            else {}
        )
        return _drawable_phrase_for_scaffold(
            beat.get(key) or concrete_event.get(key) or fallback
        )

    def drawable_beat_evidence(beat: dict[str, Any]) -> list[str]:
        concrete_event = (
            beat.get("concrete_event")
            if isinstance(beat.get("concrete_event"), dict)
            else {}
        )
        raw = beat.get("required_visual_evidence")
        if not isinstance(raw, list):
            raw = concrete_event.get("required_visual_evidence")
        return list(
            dict.fromkeys(
                phrase
                for value in (raw if isinstance(raw, list) else [])
                if (phrase := _drawable_phrase_for_scaffold(value))
                and phrase not in {location_name, protagonist}
            )
        )

    pressure_beat = source_beat("pressure")
    pressure_action = drawable_beat_value(
        pressure_beat,
        "visible_action",
        f"{protagonist}は片手の動きを止め、顔だけを圧力の原因へ向けている",
    )
    pressure_reaction = drawable_beat_value(
        pressure_beat,
        "visible_reaction",
        f"{location_name}の床と出入口に、前進を妨げる配置が見える",
    )
    pressure_evidence = drawable_beat_evidence(pressure_beat)
    pressure_foreground = pressure_evidence[0] if pressure_evidence else f"{location_name}の床にある進路を狭める実物"

    turn_beat = source_beat("turn")
    turn_action = drawable_beat_value(
        turn_beat,
        "visible_action",
        f"{protagonist}の手と顔に、直前の出来事を受けた緊張が残る",
    )
    turn_reaction = drawable_beat_value(
        turn_beat,
        "visible_reaction",
        f"{location_name}の前景に直前の出来事が残した実物と人物の反応が見える",
    )
    turn_evidence = drawable_beat_evidence(turn_beat)
    turn_foreground = turn_evidence[0] if turn_evidence else f"{protagonist}の手元"

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
            "target_beat": pressure_action,
            "screen_question": f"{title}で、{protagonist}は何に妨げられているのか",
            "dramatic_job": "sceneの問いを、空間の締めつけと人物の身体状態で立ち上げる",
            "visual_proof": f"{pressure_action}。{pressure_reaction}",
            "first_frame_brief": f"{location_name}の中広。前景の{pressure_foreground}、中景の{protagonist}、背景の出入口が同時に見え、{protagonist}の手は止まっている。",
            "must_show_extra": [location_name],
            "done_when": "sceneの問いと圧力が、人物と場所だけで読める",
            "foreground": pressure_foreground,
            "midground": protagonist,
            "background": location_name,
            "screen_direction": "pressure_holds_character",
            "motion_brief": f"{protagonist}が片手の動きを止め、顔だけを圧力の原因へ向ける",
            "motion_end_state": f"{protagonist}の手が{pressure_foreground}のそばで止まり、視線が圧力の原因に残る",
            "narration": f"{title}。まだ動けない場所で、進む理由だけが奥に残っている。",
        },
        {
            "obligation_id": "visible_value_shift",
            "cut_function": "threshold",
            "source": "value_shift.visible_evidence",
            "target_beat": turn_action,
            "screen_question": f"{title}で、何が変わり始めたのか",
            "dramatic_job": "scene内の状態差を、手元、表情、光、必要な物証で可視化する",
            "visual_proof": f"{turn_action}。{turn_reaction}",
            "first_frame_brief": f"{protagonist}の手と顔が同時に読める中距離。前景に{turn_foreground}があり、手と姿勢には直前の出来事を受けた状態が残る。",
            "must_show_extra": [artifact] if include_artifact else (turn_evidence[:3] or ["光"]),
            "done_when": "scene内の状態差が、人物の手元、顔の向き、光の変化で読める",
            "foreground": turn_foreground,
            "midground": protagonist,
            "background": location_name,
            "screen_direction": "toward_change",
            "motion_brief": f"{protagonist}が{turn_foreground}から出入口へ視線を移し、片手の動きを止める",
            "motion_end_state": f"{protagonist}の手が{turn_foreground}のそばで止まり、視線が出入口に残る",
            "narration": f"{title}。消えかけた願いが、手の届く距離まで近づく。",
        },
        {
            "cut_function": "handoff",
            "obligation_id": "causal_handoff",
            "source": "causal_turn/handoff_to_next_scene",
            "target_beat": f"前景に残る痕跡、{protagonist}の姿勢、出口へ伸びる光が同時に見える",
            "screen_question": f"{title}の終わりに、次へ進む理由は何として残るのか",
            "dramatic_job": "前景に残る物理的な痕跡と、人物の重心、出入口へ伸びる光を一枚に固定する",
            "visual_proof": f"{location_name}の前景に残された痕跡、出口側へ重心を移した{protagonist}、画面奥の出入口へ伸びる光が同時に見える",
            "first_frame_brief": f"{protagonist}は行動後に重心を出口側へ移している。前景に残された痕跡、画面奥の出入口、そこへ伸びる光が同時に見える。",
            "must_show_extra": [artifact] if include_artifact else ["導線"],
            "done_when": "前景の痕跡、主人公の重心、出口へ伸びる光が一枚で見える",
            "foreground": f"{protagonist}の足元と前景に残る痕跡",
            "midground": protagonist,
            "background": f"{location_name}の出口と画面奥へ続く通路",
            "screen_direction": "toward_next_scene",
            "motion_brief": f"{protagonist}が前景の痕跡から出口へ視線を移し、重心を出口側へ一度だけ移す",
            "motion_end_state": f"{protagonist}の足先と視線が{location_name}の出口へ向き、前景の痕跡が残る",
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
                        "target_beat": f"{title}: {artifact}、{protagonist}の現在位置、周囲の視線を同時に見せる",
                        "screen_question": f"{title}の終わりに、何が主人公の価値を証明するのか",
                        "dramatic_job": "前景の証拠、主人公の現在位置、見守る人物の視線、部屋の光を一枚に固定する",
                        "visual_proof": f"前景の{artifact}、それと関係する{protagonist}、見守る人物の視線、{location_name}の光が同時に見える",
                        "first_frame_brief": f"{protagonist}は肩の緊張をほどき、{artifact}との関係が読める位置にいる。前景の証拠から主人公の顔へ光が集まり、周囲の人物は主人公へ視線を向けている。",
                        "must_show_extra": [artifact],
                        "done_when": "前景の証拠、主人公の現在位置、見守る人物の視線、部屋の光が一枚で見える",
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
                visual_proof=f"{event_summary}。{event_obligation.get('causal_proof')}。同じ画面に{'、'.join(must_show_event_terms)}が見える",
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
        drawable_information = [
            phrase
            for item in audience_information[:3]
            if (phrase := _drawable_phrase_for_scaffold(item))
        ]
        key_information = "、".join(drawable_information) or f"{location_name}、{protagonist}、出入口"
        append_unique(
            extra_obligation(
                obligation_id="audience_context",
                cut_function="context",
                source="audience_information",
                target_beat=f"{title}: 場所、人物同士の距離、出入口の位置関係を同時に見せる",
                screen_question=f"観客は{title}の状況を何から理解するのか",
                dramatic_job="場所、人物同士の距離、出入口を、説明台詞に頼らず構図で示す",
                visual_proof=f"{location_name}で、{key_information}、人物同士の距離、出入口の位置関係が光の向きとともに見える",
                first_frame_brief=f"{location_name}の前景・中景・背景に人物と出入口を分け、{protagonist}の現在位置と他者までの距離が見える。",
                must_show_extra=[location_name, "人物同士の距離", "出入口"],
                done_when="場所、人物、出入口の位置関係が一枚で見える",
                foreground="出入口をふさぐ扉または障害物",
                midground=protagonist,
                background=location_name,
                screen_direction="context_established",
                motion_brief="視線誘導が場所、人物、ルールの順に静かに移る",
                motion_end_state="sceneの前提が次の変化cutを受け止められる状態で残る",
                narration=f"{title}。場所の決まりが、彼女の進める幅を静かに狭めている。",
            )
        )

    if (withheld_information or reveal_constraints) and not include_artifact:
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
                dramatic_job="象徴物を装飾ではなく、身元や状態差の証拠として配置する",
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

    # Duration alone must never invent filler actions.  If the authored
    # obligations do not cover all canonical event functions, add only the
    # missing event-beat coverage; pacing and clip duration are handled later.
    duration_cut_floor = 0
    function_order = ("setup", "pressure", "turn", "payoff")
    function_counts = {
        function: sum(
            1
            for obligation_index, obligation in enumerate(obligations, start=1)
            if target_event_function(obligation, obligation_index) == function
        )
        for function in function_order
    }
    facet_labels = {
        "setup": ("空間と開始状態", "人物の初期姿勢"),
        "pressure": ("外部圧力", "圧力への身体反応"),
        "turn": ("不可逆な行為", "行為が残す物証"),
        "payoff": ("直後の結果", "次へ残る反応と痕跡"),
    }
    function_labels = {
        "setup": "開始状態",
        "pressure": "外部圧力",
        "turn": "不可逆な転換",
        "payoff": "直後の結果",
    }
    required_obligation_count = len(event_sequence)
    while len(obligations) < required_obligation_count:
        function = min(function_order, key=lambda item: (function_counts[item], function_order.index(item)))
        beat = beat_for_function(function)
        beat_id = str(beat.get("beat_id") or f"scene{idx:02d}_event_{function}").strip()
        occurrence = function_counts[function] + 1
        facet_options = facet_labels[function]
        facet = facet_options[(occurrence - 1) % len(facet_options)]
        concrete_event = beat.get("concrete_event") if isinstance(beat.get("concrete_event"), dict) else {}
        visual_evidence_for_beat = [
            str(item)
            for item in beat.get("required_visual_evidence", [])
            if str(item).strip()
        ] if isinstance(beat.get("required_visual_evidence"), list) else []
        if not visual_evidence_for_beat:
            visual_evidence_for_beat = [
                str(item)
                for item in concrete_event.get("required_visual_evidence", [])
                if str(item).strip()
            ] if isinstance(concrete_event.get("required_visual_evidence"), list) else []
        if not visual_evidence_for_beat:
            visual_evidence_for_beat = [location_name, protagonist]
        what_happens = str(beat.get("what_happens") or concrete_event.get("what_happens") or title)
        visible_action = str(beat.get("visible_action") or concrete_event.get("visible_action") or what_happens)
        visible_reaction = str(beat.get("visible_reaction") or concrete_event.get("visible_reaction") or "周囲の反応が変わる")
        immediate_consequence = str(
            beat.get("immediate_consequence")
            or concrete_event.get("immediate_consequence")
            or scene_intent.get("handoff_to_next_scene")
            or scene_intent.get("terminal_resolution")
            or "次の状態へ因果が残る"
        )
        must_show = list(dict.fromkeys(visual_evidence_for_beat[:3]))
        required_roles = [
            str(item)
            for item in concrete_event.get("who", [])
            if str(item).strip()
        ] if isinstance(concrete_event.get("who"), list) else []
        append_unique(
            extra_obligation(
                obligation_id=f"coverage_{function}_{occurrence:02d}",
                cut_function=f"{function}_detail",
                source=f"scene_event.event_sequence[{beat_id}]",
                target_beat=f"{title}: {function_labels[function]}の{facet}を独立して見せる — {what_happens}",
                screen_question=f"{function}の{facet}から、観客は何が変わったと理解するのか",
                dramatic_job=f"{beat_id}の{facet}を、他cutと異なる原因・反応・結果として可視化する",
                visual_proof=f"{visible_action}。{visible_reaction}。同じ画面に{'、'.join(must_show)}が見える",
                first_frame_brief=f"{', '.join(must_show)}が読め、{visible_action}の直前または直後を示す静止状態。",
                must_show_extra=must_show,
                done_when=f"{beat_id}の{facet}と{immediate_consequence}が、このcut固有の画面情報として読める",
                foreground=must_show[0],
                midground=protagonist,
                background=location_name,
                screen_direction=f"coverage_{function}_{occurrence:02d}",
                motion_brief=f"{visible_action}から{visible_reaction}へ小さく進み、{facet}を強める",
                motion_end_state=immediate_consequence,
                narration=f"{title}。{what_happens}",
                audience_knowledge_delta=f"観客は{what_happens}の{facet}を具体的な事実として理解する",
                causal_proof=immediate_consequence,
                visual_evidence=must_show,
                required_roles=required_roles,
                static_first_frame_rule="動作の説明ではなく、原因・反応・結果のいずれかが一枚で読める静止状態にする",
                anti_redundancy_key=f"{beat_id}:{facet}:{occurrence}",
            )
        )
        function_counts[function] += 1

    _normalize_cut_obligations_for_scene(obligations)

    def event_time_position_for_function(function: str) -> str:
        if function == "setup":
            return "before_trigger"
        if function == "pressure":
            return "early_action"
        if function == "turn":
            return "trigger_moment"
        return "consequence"

    location_sequence = _scene_location_sequence(profile, idx) or [location_name]

    def project_obligation_to_event_beat(
        obligation: dict[str, Any],
        beat: dict[str, Any],
    ) -> None:
        """Project one canonical event beat into one drawable/motion cut state."""

        # Audience interpretation is authored separately from physical consequence.
        # Keep it bound to the selected beat instead of a scaffold's generic claim.
        audience_delta = str(beat.get("audience_knowledge_delta") or "").strip()
        if audience_delta:
            obligation["audience_knowledge_delta"] = audience_delta
        obligation_id = str(obligation.get("obligation_id") or "").strip()
        concrete = beat.get("concrete_event") if isinstance(beat.get("concrete_event"), dict) else {}
        raw_obligation_overrides = beat.get("obligation_overrides")
        if not isinstance(raw_obligation_overrides, dict):
            raw_obligation_overrides = concrete.get("obligation_overrides")
        if not isinstance(raw_obligation_overrides, dict):
            raw_obligation_overrides = {}
        shared_obligation_override = (
            raw_obligation_overrides.get("*")
            if isinstance(raw_obligation_overrides.get("*"), dict)
            else {}
        )
        exact_obligation_override = (
            raw_obligation_overrides.get(obligation_id)
            if isinstance(raw_obligation_overrides.get(obligation_id), dict)
            else {}
        )
        obligation_override = {
            **shared_obligation_override,
            **exact_obligation_override,
        }
        beat_location = str(
            obligation_override.get("location")
            or concrete.get("where")
            or location_name
        ).strip()
        if beat_location not in location_sequence:
            raise RuntimeError(
                f"scene{idx:02d} {obligation_id}: cut location is not declared in "
                f"scene_location_sequence: {beat_location}"
            )
        primary_subject = str(
            obligation_override.get("primary_subject")
            or beat.get("primary_subject")
            or concrete.get("primary_subject")
            or protagonist
        ).strip()
        concrete_location = str(concrete.get("where") or location_name).strip()
        exact_cross_location_projection = beat_location != concrete_location
        what_happens = str(
            obligation_override.get("what_happens")
            or beat.get("what_happens")
            or concrete.get("what_happens")
            or title
        ).strip()
        other_route_locations = {
            location for location in location_sequence if location != beat_location
        }
        what_happens = str(
            _sanitize_first_frame_prose(
                what_happens,
                excluded_tokens=other_route_locations,
            )
            or _sanitize_first_frame_prose(
                obligation.get("target_beat") or "",
                excluded_tokens=other_route_locations,
            )
            or f"{primary_subject}が{beat_location}でこのcutの出来事を進める"
        ).strip()
        visible_action = _drawable_phrase_for_scaffold(
            obligation_override.get("visible_action")
            or (
                f"{primary_subject}が{beat_location}の経路上で身体を止めている"
                if exact_cross_location_projection
                else ""
            )
            or beat.get("visible_action")
            or concrete.get("visible_action")
            or what_happens
        )
        visible_reaction = _drawable_phrase_for_scaffold(
            obligation_override.get("visible_reaction")
            or (
                f"{beat_location}の入口と出口が同じ画面内で読める"
                if exact_cross_location_projection
                else ""
            )
            or beat.get("visible_reaction")
            or concrete.get("visible_reaction")
            or concrete.get("immediate_consequence")
            or beat.get("immediate_consequence")
        )
        visible_action = _drawable_phrase_for_scaffold(
            _sanitize_first_frame_prose(
                visible_action,
                excluded_tokens=other_route_locations,
            )
            or f"{primary_subject}が{beat_location}で身体を止めている"
        )
        visible_reaction = _drawable_phrase_for_scaffold(
            _sanitize_first_frame_prose(
                visible_reaction,
                excluded_tokens=other_route_locations,
            )
            or f"{beat_location}の入口と人物の位置関係が読める"
        )
        raw_evidence = obligation_override.get("required_visual_evidence")
        if not isinstance(raw_evidence, list):
            raw_evidence = beat.get("required_visual_evidence")
        if not isinstance(raw_evidence, list):
            raw_evidence = concrete.get("required_visual_evidence")
        evidence = list(
            dict.fromkeys(
                phrase
                for item in (raw_evidence if isinstance(raw_evidence, list) else [])
                if (phrase := _drawable_phrase_for_scaffold(item))
                and not any(
                    other_location in phrase
                    for other_location in location_sequence
                    if other_location != beat_location
                )
            )
        )
        if beat_location and beat_location not in evidence:
            evidence.insert(0, beat_location)
        if primary_subject and primary_subject not in evidence:
            evidence.insert(1 if evidence else 0, primary_subject)
        if (
            _cut_uses_artifact(
                profile,
                idx,
                obligation_id,
                include_artifact=include_artifact,
            )
            and not any(artifact in item for item in evidence)
        ):
            evidence.append(artifact)
        detail_evidence = [
            item for item in evidence if item not in {beat_location, primary_subject}
        ]
        foreground = _drawable_phrase_for_scaffold(
            obligation_override.get("foreground")
        ) or (detail_evidence[0] if detail_evidence else f"{primary_subject}の手元")
        required_roles = obligation_override.get("required_roles")
        if not isinstance(required_roles, list):
            required_roles = beat.get("required_roles")
        if not isinstance(required_roles, list):
            required_roles = concrete.get("who")
        role_ids = list(
            dict.fromkeys(
                str(item).strip()
                for item in (required_roles if isinstance(required_roles, list) else [])
                if str(item).strip()
            )
        )
        motion_brief = _drawable_phrase_for_scaffold(
            obligation_override.get("motion_brief")
            or obligation.get("motion_brief")
            or beat.get("motion_brief")
            or concrete.get("motion_brief")
            or visible_action
        )
        motion_end_state = _drawable_phrase_for_scaffold(
            obligation_override.get("motion_end_state")
            or obligation.get("motion_end_state")
            or beat.get("motion_end_state")
            or concrete.get("motion_end_state")
            or visible_reaction
            or beat.get("immediate_consequence")
        )
        raw_visible_character_state = obligation_override.get("visible_character_state")
        visible_character_state_source = (
            "duration_segment_contract"
            if str(beat.get("visible_character_state_source") or "")
            == "duration_segment_contract"
            else "obligation_override"
            if isinstance(raw_visible_character_state, dict)
            and raw_visible_character_state
            else str(
                beat.get("visible_character_state_source")
                or concrete.get("visible_character_state_source")
                or "inferred"
            )
        )
        if not isinstance(raw_visible_character_state, dict):
            raw_visible_character_state = beat.get("visible_character_state")
        if not isinstance(raw_visible_character_state, dict):
            raw_visible_character_state = concrete.get("visible_character_state")
        visible_character_state = {
            str(key): _drawable_phrase_for_scaffold(value)
            for key, value in (
                raw_visible_character_state
                if isinstance(raw_visible_character_state, dict)
                else {}
            ).items()
            if _drawable_phrase_for_scaffold(value)
        }
        motion_attention_target = _drawable_phrase_for_scaffold(
            beat.get("motion_attention_target")
            or concrete.get("motion_attention_target")
            or foreground
        )
        if (
            visible_character_state_source == "duration_segment_contract"
            and obligation_id == "scene_pressure"
        ):
            motion_brief = (
                f"{primary_subject}が{foreground}のそばで両手を一度止め、"
                "出来事の相手へ顔を向ける"
            )
            motion_end_state = (
                f"{primary_subject}の両手が{foreground}のそばで止まり、"
                "顔と身体が出来事の相手を向いている"
            )
            motion_attention_target = foreground
        elif (
            visible_character_state_source == "duration_segment_contract"
            and obligation_id == "visible_value_shift"
        ):
            motion_brief = (
                f"{primary_subject}が{foreground}から自分の手元へ"
                "視線を一度だけ戻す"
            )
            motion_end_state = (
                f"{primary_subject}の視線が自分の手元に残り、"
                f"身体は{beat_location}の結果位置で止まっている"
            )
            motion_attention_target = f"{primary_subject}の手元"
        elif obligation_id == "audience_context":
            motion_brief = (
                f"{primary_subject}が{foreground}から画面奥の出入口へ"
                "顔を一度だけゆっくり向ける"
            )
            motion_end_state = (
                f"{primary_subject}の顔が画面奥の出入口を向き、"
                f"身体は{beat_location}の中景で止まっている"
            )
            motion_attention_target = "画面奥の出入口"
        elif obligation_id == "symbolic_proof":
            motion_brief = f"{primary_subject}が{foreground}へ片手を一度だけ伸ばす"
            motion_end_state = (
                f"{primary_subject}の指先が{foreground}の手前で止まり、"
                "視線も同じ位置に残っている"
            )
            motion_attention_target = foreground
        elif obligation_id == "spatial_transition":
            motion_brief = (
                f"{primary_subject}が{foreground}から画面奥の通路側へ"
                "重心を一度だけ移す"
            )
            motion_end_state = (
                f"{primary_subject}の足先と身体軸が画面奥の通路へ向き、"
                f"{foreground}は前景に残っている"
            )
            motion_attention_target = "画面奥の通路"
        elif obligation_id == "time_or_deadline_pressure":
            motion_brief = f"{primary_subject}が足先を出入口へ一度だけ向け直す"
            motion_end_state = (
                f"{primary_subject}の足先が出入口を向き、"
                f"{foreground}との距離が開いている"
            )
            motion_attention_target = "出入口"
        elif obligation_id == "reaction_after_change":
            motion_brief = (
                f"{primary_subject}が{foreground}を見たまま、"
                "一度だけゆっくり息を吐いて肩を下げる"
            )
            motion_end_state = (
                f"{primary_subject}の肩が下がり、"
                f"視線が{foreground}に残っている"
            )
            motion_attention_target = foreground
        elif obligation_id == "terminal_resolution":
            motion_brief = (
                f"{primary_subject}が{foreground}から画面内の証人へ"
                "顔を一度だけゆっくり上げる"
            )
            motion_end_state = (
                f"{primary_subject}の顔が画面内の証人を向き、"
                f"{foreground}は前景の同じ位置に残っている"
            )
            motion_attention_target = "画面内の証人"
        elif obligation_id.startswith("duration_"):
            motion_brief = (
                f"{primary_subject}が{foreground}のそばで片手を一度だけ引き、"
                "身体の近くで止める"
            )
            motion_end_state = (
                f"{primary_subject}の片手が身体の近くで止まり、"
                f"{foreground}との間に距離が残っている"
            )
            motion_attention_target = foreground
        motion_brief = _drawable_phrase_for_scaffold(
            obligation_override.get("motion_brief")
        ) or motion_brief
        motion_end_state = _drawable_phrase_for_scaffold(
            obligation_override.get("motion_end_state")
        ) or motion_end_state
        motion_attention_target = _drawable_phrase_for_scaffold(
            obligation_override.get("motion_attention_target")
        ) or motion_attention_target
        environment_motion = _drawable_phrase_for_scaffold(
            obligation_override.get("environment_motion")
        )
        emotional_change = _drawable_phrase_for_scaffold(
            obligation_override.get("emotional_change")
        )
        raw_first_frame_character_asset_overrides = (
            exact_obligation_override["first_frame_character_asset_overrides"]
            if "first_frame_character_asset_overrides"
            in exact_obligation_override
            else _MISSING_POLICY_VALUE
        )
        first_frame_character_asset_overrides = (
            _validate_first_frame_character_asset_overrides(
                profile,
                raw_first_frame_character_asset_overrides,
                context=f"scene{idx:02d}.{obligation_id}",
            )
        )
        raw_first_frame_excluded_object_ids = (
            exact_obligation_override["first_frame_excluded_object_ids"]
            if "first_frame_excluded_object_ids" in exact_obligation_override
            else _MISSING_POLICY_VALUE
        )
        first_frame_excluded_object_ids = (
            _validate_first_frame_excluded_object_ids(
                profile,
                raw_first_frame_excluded_object_ids,
                context=f"scene{idx:02d}.{obligation_id}",
            )
        )
        raw_allowed_new_reveal_elements = (
            exact_obligation_override["allowed_new_reveal_elements"]
            if "allowed_new_reveal_elements" in exact_obligation_override
            else _MISSING_POLICY_VALUE
        )
        allowed_new_reveal_elements = _validate_exact_obligation_string_list(
            raw_allowed_new_reveal_elements,
            field_name="allowed_new_reveal_elements",
            context=f"scene{idx:02d}.{obligation_id}",
        )
        raw_allowed_reveal_info_ids = (
            exact_obligation_override["allowed_reveal_info_ids"]
            if "allowed_reveal_info_ids" in exact_obligation_override
            else _MISSING_POLICY_VALUE
        )
        allowed_reveal_info_ids = _validate_exact_obligation_string_list(
            raw_allowed_reveal_info_ids,
            field_name="allowed_reveal_info_ids",
            context=f"scene{idx:02d}.{obligation_id}",
        )
        if "use_next_cut_first_frame_as_last_frame" in exact_obligation_override:
            raw_last_frame_binding = exact_obligation_override[
                "use_next_cut_first_frame_as_last_frame"
            ]
            if not isinstance(raw_last_frame_binding, bool):
                raise RuntimeError(
                    f"scene{idx:02d}.{obligation_id}: "
                    "use_next_cut_first_frame_as_last_frame must be a boolean"
                )
            use_next_cut_first_frame_as_last_frame = raw_last_frame_binding
        else:
            use_next_cut_first_frame_as_last_frame = False
        proof_parts = [visible_action, visible_reaction]
        if detail_evidence:
            proof_parts.append("同じ画面に" + "、".join(detail_evidence[:4]) + "が見える")
        static_first_frame_rule = _drawable_phrase_for_scaffold(
            _sanitize_first_frame_prose(
                obligation_override.get("static_first_frame_rule") or "",
                excluded_tokens=other_route_locations,
            )
        ) or (
            f"動作説明ではなく、{beat_location}で{primary_subject}と"
            "この event beat の証拠だけが一枚で読める静止状態にする"
        )
        obligation.update(
            {
                "target_beat": f"{beat_location}。{what_happens}",
                "visible_action": visible_action,
                "visible_reaction": visible_reaction,
                "visual_proof": "。".join(part.strip("。") for part in proof_parts if part),
                "first_frame_brief": (
                    _drawable_phrase_for_scaffold(
                        obligation_override.get("first_frame_brief")
                    )
                    or (
                        f"{beat_location}。前景に{foreground}、中景に{primary_subject}を置き、"
                        f"{visible_action.rstrip('。')}。"
                    )
                ),
                "static_first_frame_rule": static_first_frame_rule,
                "must_show_extra": evidence,
                "foreground": foreground,
                "midground": primary_subject,
                "background": beat_location,
                "motion_brief": motion_brief,
                "motion_end_state": motion_end_state,
                "visible_character_state": visible_character_state,
                "visible_character_state_source": visible_character_state_source,
                "motion_attention_target": motion_attention_target,
                "environment_motion": environment_motion,
                "emotional_change": emotional_change,
                "first_frame_character_asset_overrides": first_frame_character_asset_overrides,
                "first_frame_excluded_object_ids": first_frame_excluded_object_ids,
                "allowed_new_reveal_elements": allowed_new_reveal_elements,
                "allowed_reveal_info_ids": allowed_reveal_info_ids,
                "use_next_cut_first_frame_as_last_frame": use_next_cut_first_frame_as_last_frame,
                "retain_carried_character_subjects": bool(
                    obligation_override.get("retain_carried_character_subjects", True)
                ),
                "visual_evidence": evidence,
                "required_roles": role_ids,
                "primary_subject_name": primary_subject,
                "visible_character_ids": role_ids,
                "causal_proof": visible_reaction,
            }
        )

    scene_id = _runtime_scene_id(idx)
    assignment_records: list[dict[str, Any]] = []
    assigned_by_source: dict[str, list[str]] = {}
    assigned_by_obligation: dict[str, list[str]] = {}
    previous_projected_obligation: dict[str, Any] | None = None
    for index, obligation in enumerate(obligations, start=1):
        selector = f"scene{scene_id}_cut{index:02d}"
        obligation_id = str(obligation.get("obligation_id") or f"obligation_{index:02d}")
        source = str(obligation.get("source") or "scene")
        function = target_event_function(obligation, index)
        exact_override_beat = next(
            (
                beat
                for beat in event_sequence
                if obligation_id
                in (
                    beat.get("obligation_overrides")
                    if isinstance(beat.get("obligation_overrides"), dict)
                    else {}
                )
            ),
            None,
        )
        primary_beat = (
            exact_override_beat
            or event_sequence[min(index - 1, len(event_sequence) - 1)]
            if event_sequence
            else beat_for_function(function)
        )
        project_obligation_to_event_beat(obligation, primary_beat)
        primary_beat_id = str(primary_beat.get("beat_id") or "").strip()
        if (
            previous_projected_obligation is not None
            and (
                str(previous_projected_obligation.get("background") or "").strip()
                == str(obligation.get("background") or "").strip()
                or bool(
                    previous_projected_obligation.get(
                        "use_next_cut_first_frame_as_last_frame"
                    )
                )
            )
        ):
            previous_end_state = _drawable_phrase_for_scaffold(
                previous_projected_obligation.get("motion_end_state")
            )
            if previous_end_state:
                persistent_evidence = [
                    str(item).strip()
                    for item in obligation.get("visual_evidence") or []
                    if str(item).strip()
                    and str(item).strip()
                    not in {
                        str(obligation.get("background") or "").strip(),
                        str(obligation.get("primary_subject_name") or "").strip(),
                    }
                ]
                evidence_clause = (
                    "。同じ画面に"
                    + "、".join(persistent_evidence[:3])
                    + "が見える"
                    if persistent_evidence
                    else ""
                )
                same_primary_subject = str(
                    previous_projected_obligation.get("primary_subject_name") or ""
                ).strip() == str(
                    obligation.get("primary_subject_name") or ""
                ).strip()
                current_visual_proof = _drawable_phrase_for_scaffold(
                    obligation.get("visual_proof")
                )
                retain_carried_character_subjects = bool(
                    obligation.get("retain_carried_character_subjects", True)
                )
                carried_character_subject_names = [
                    str(item).strip()
                    for item in [
                        *(
                            obligation.get("carried_character_subject_names")
                            or []
                        ),
                        *(
                            previous_projected_obligation.get(
                                "carried_character_subject_names"
                            )
                            or []
                            if retain_carried_character_subjects
                            else []
                        ),
                        *(
                            []
                            if same_primary_subject
                            or not retain_carried_character_subjects
                            else [
                                previous_projected_obligation.get(
                                    "primary_subject_name"
                                )
                            ]
                        ),
                    ]
                    if str(item or "").strip()
                ]
                if carried_character_subject_names:
                    obligation["carried_character_subject_names"] = list(
                        dict.fromkeys(carried_character_subject_names)
                    )
                obligation["visual_proof"] = (
                    previous_end_state + evidence_clause
                    if same_primary_subject
                    else "。".join(
                        part
                        for part in (previous_end_state, current_visual_proof)
                        if part
                    )
                )
                obligation["first_frame_brief"] = (
                    f"{obligation.get('background')}。{previous_end_state}。"
                    f"前景の{obligation.get('foreground')}と中景の"
                    f"{obligation.get('primary_subject_name')}が同時に見える。"
                )
                obligation["first_frame_carried_from_previous_end"] = True
                if same_primary_subject:
                    authored_state = str(
                        obligation.get("visible_character_state_source") or ""
                    ) in {"beat_override", "location_segment", "obligation_override"}
                    authored_visible_state = (
                        dict(obligation.get("visible_character_state") or {})
                        if authored_state
                        and isinstance(
                            obligation.get("visible_character_state"), dict
                        )
                        else {}
                    )
                    authored_posture = _drawable_phrase_for_scaffold(
                        authored_visible_state.get("posture")
                    )
                    carried_posture = "。".join(
                        dict.fromkeys(
                            item
                            for item in (previous_end_state, authored_posture)
                            if item
                        )
                    )
                    obligation["visible_character_state"] = {
                        **authored_visible_state,
                        "posture": carried_posture,
                    }
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
        previous_projected_obligation = obligation
    required_functions = ("setup", "pressure", "turn", "payoff")

    def assigned_beat_ids(record: dict[str, Any]) -> list[str]:
        source_contract = (
            record.get("event_assignment", {}).get("source_event_contract", {})
            if isinstance(record.get("event_assignment"), dict)
            else {}
        )
        return [str(item).strip() for item in source_contract.get("source_event_beat_ids", []) if str(item).strip()] if isinstance(source_contract.get("source_event_beat_ids"), list) else []

    primary_covered_ids = {
        str(record.get("event_assignment", {}).get("source_event_contract", {}).get("primary_event_beat_id") or "").strip()
        for record in assignment_records
        if isinstance(record.get("event_assignment"), dict)
    }
    missing_primary_ids = [
        str(beat.get("beat_id") or "").strip()
        for beat in event_sequence
        if str(beat.get("beat_id") or "").strip() not in primary_covered_ids
    ]
    if missing_primary_ids:
        raise RuntimeError(
            "scene cut coverage must assign every event beat as a primary cut: "
            + ", ".join(missing_primary_ids)
        )

    def assigned_for(*sources: str) -> list[str]:
        selectors: list[str] = []
        for source in sources:
            selectors.extend(assigned_by_source.get(source, []))
        return list(dict.fromkeys(selectors))

    minimum_by_distinct_semantic_obligations = len(
        {
            str(record.get("obligation_id") or "").strip()
            for record in assignment_records
            if str(record.get("obligation_id") or "").strip()
        }
    )
    minimum_by_event_beats = len(event_sequence)
    selected_minimum = max(
        minimum_by_distinct_semantic_obligations,
        minimum_by_event_beats,
    )
    coverage = {
        "coverage_strategy": "reverse_from_scene_event",
        "source_schema_version": "scene_event_v1",
        "strategy": "scene設計から必要な視覚要件を列挙し、1 cut = 1主要意図になるよう割り当てる",
        "min_cut_count": {
            "by_distinct_semantic_obligations": minimum_by_distinct_semantic_obligations,
            "by_event_beats": minimum_by_event_beats,
            "selected": selected_minimum,
            "by_importance": 0,
            "by_duration": 0,
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
            {
                "obligation_id": str(record["obligation_id"]),
                "source": str(record.get("source") or "scene"),
                "evidence": str(record.get("visual_proof") or record.get("target_beat") or ""),
                "assigned_cut_ids": [str(record["cut_selector"])],
            }
            for record in assignment_records
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
        {"item_id": "SYM2", "item": profile["artifact_name"], "meaning": "脆さと証明が同居する身元の鍵", "evidence_refs": ["P2"]},
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

def _story_scene_character_ids(
    profile: dict[str, Any],
    idx: int,
    source_events: list[str],
) -> list[str]:
    """Carry research character responsibility into each authored story scene."""

    research = profile.get("research")
    materials = research.get("story_materials") if isinstance(research, dict) else None
    raw_events = materials.get("chronological_events") if isinstance(materials, dict) else None
    character_ids: list[str] = []
    for event in raw_events or []:
        if not isinstance(event, dict) or str(event.get("event") or "").strip() not in source_events:
            continue
        character_ids.extend(
            str(value).strip()
            for value in event.get("involved_characters") or []
            if str(value).strip()
        )
    return list(dict.fromkeys(character_ids)) or ["protagonist"]


def _authored_location_segments_for_story(
    *,
    profile: dict[str, Any],
    scene_index: int,
    blueprint: dict[str, Any],
) -> list[dict[str, Any]]:
    """Materialize one complete, exact route from authored scene semantics."""

    route = _scene_location_sequence(profile, scene_index)
    existing = {
        str(segment.get("location") or "").strip(): deepcopy(segment)
        for segment in _scene_location_segments(profile, scene_index)
        if str(segment.get("location") or "").strip() in route
    }
    if len(route) <= 1:
        return [existing[name] for name in route if name in existing]

    candidates_by_location: dict[str, list[dict[str, Any]]] = {
        name: [] for name in route
    }
    beat_overrides = (
        blueprint.get("beat_overrides")
        if isinstance(blueprint.get("beat_overrides"), dict)
        else {}
    )
    for function, raw_override in beat_overrides.items():
        if not isinstance(raw_override, dict):
            continue
        root_location = str(raw_override.get("location") or "").strip()
        if root_location in candidates_by_location:
            candidates_by_location[root_location].append(
                {**deepcopy(raw_override), "beat_function": str(function)}
            )
        nested = raw_override.get("obligation_overrides")
        if not isinstance(nested, dict):
            continue
        for obligation_id, raw_exact in nested.items():
            if not isinstance(raw_exact, dict):
                continue
            exact_location = str(
                raw_exact.get("location") or root_location
            ).strip()
            if exact_location in candidates_by_location:
                candidates_by_location[exact_location].append(
                    {
                        **deepcopy(raw_override),
                        **deepcopy(raw_exact),
                        "beat_function": str(function),
                        "obligation_id": str(obligation_id),
                    }
                )

    protagonist = str(profile.get("protagonist_name") or "主人公").strip()
    _runtime_position, runtime_segment_count, _runtime_role = _scene_segment(
        profile, scene_index
    )

    materialized: list[dict[str, Any]] = []
    for route_position, location in enumerate(route, start=1):
        if location in existing:
            materialized.append(existing[location])
            continue
        candidates = candidates_by_location.get(location, [])
        if not candidates:
            raise RuntimeError(
                f"scene{scene_index} location segment has no authored beat or obligation: {location}"
            )
        candidate = max(
            candidates,
            key=lambda item: sum(
                bool(item.get(key))
                for key in (
                    "visible_action",
                    "required_visual_evidence",
                    "motion_brief",
                    "motion_end_state",
                    "primary_subject",
                )
            ),
            default={},
        )
        missing_concrete_fields = [
            key
            for key in (
                "required_visual_evidence",
                "motion_brief",
                "motion_end_state",
            )
            if not candidate.get(key)
        ]
        if missing_concrete_fields:
            raise RuntimeError(
                f"scene{scene_index} location segment is not concretely authored: "
                f"{location} ({', '.join(missing_concrete_fields)})"
            )
        primary_subject = str(
            candidate.get("primary_subject") or protagonist
        ).strip()
        responsibility = str(
            candidate.get("what_happens")
            or candidate.get("visible_action")
            or candidate.get("motion_brief")
            or ""
        ).strip()
        evidence = list(
            dict.fromkeys(
                [
                    str(item).strip()
                    for item in candidate.get("required_visual_evidence") or []
                    if str(item).strip()
                ]
                + [location, primary_subject]
            )
        )
        visible_action = str(candidate.get("visible_action") or "").strip()
        if not visible_action:
            visible_action = (
                f"{evidence[0]}が{location}にあり、"
                f"{primary_subject}との位置関係が見える"
            )
        visible_reaction = str(candidate.get("visible_reaction") or "").strip()
        if not visible_reaction:
            visible_reaction = (
                f"{evidence[1] if len(evidence) > 1 else location}と"
                f"{location}の入口・出口の関係が同じ画面で読める"
            )
        motion_brief = str(candidate["motion_brief"]).strip()
        motion_end_state = str(candidate["motion_end_state"]).strip()
        primary_subject_by_function = {
            str(item.get("beat_function") or "").strip(): str(
                item.get("primary_subject") or protagonist
            ).strip()
            for item in candidates
            if str(item.get("beat_function") or "").strip()
        }
        required_roles = list(
            dict.fromkeys(
                str(role).strip()
                for role in candidate.get("required_roles") or []
                if str(role).strip()
            )
        ) or ["protagonist"]
        materialized_segment = {
                "location": location,
                "responsibility": responsibility,
                "primary_subject": primary_subject,
                "primary_subject_by_function": primary_subject_by_function,
                "beat_overrides": {},
                "visible_action": visible_action,
                "visible_reaction": visible_reaction,
                "required_visual_evidence": evidence,
                "required_roles": required_roles,
                "motion_brief": motion_brief,
                "motion_end_state": motion_end_state,
                "visible_character_state": {
                    "posture": visible_action,
                    "gaze": visible_reaction,
                    "route_position": f"{route_position}/{len(route)}",
                },
            }
        if runtime_segment_count > 1:
            owner_function = str(candidate.get("beat_function") or "").strip()
            materialized_segment["root_active_beat_functions"] = (
                [owner_function] if owner_function else []
            )
        materialized.append(materialized_segment)
    return materialized



def _validate_next_cut_last_frame_boundary(
    *,
    selector: str,
    current_cut_plan: dict[str, Any],
    next_cut_plan: dict[str, Any] | None,
    route_locations: list[str],
) -> dict[str, str]:
    """Validate an authored last-frame/next-first-frame spatial boundary."""

    if not isinstance(next_cut_plan, dict):
        raise RuntimeError(
            f"{selector}: next-cut last-frame binding requires a next cut"
        )
    departure = str(current_cut_plan.get("background") or "").strip()
    destination = str(next_cut_plan.get("background") or "").strip()
    route = [str(value).strip() for value in route_locations if str(value).strip()]
    if not destination or destination not in route:
        raise RuntimeError(
            f"{selector}: next-cut destination is not declared in scene route: "
            f"{destination or '<empty>'}"
        )
    actual_end_state = str(
        current_cut_plan.get("motion_end_state") or ""
    ).strip()
    if not actual_end_state:
        raise RuntimeError(
            f"{selector}: next-cut boundary requires a concrete motion end state"
        )
    next_first_frame_text = " / ".join(
        str(next_cut_plan.get(key) or "").strip()
        for key in (
            "first_frame_brief",
            "visual_proof",
            "visible_action",
            "visible_reaction",
        )
        if str(next_cut_plan.get(key) or "").strip()
    )
    if destination != departure:
        allowed_destinations = {
            str(item).strip()
            for item in current_cut_plan.get("allowed_new_reveal_elements") or []
            if str(item).strip()
        }
        if destination not in allowed_destinations:
            raise RuntimeError(
                f"{selector}: cross-location boundary lacks exact obligation "
                f"authorization for destination: {destination}"
            )
        if destination not in actual_end_state:
            raise RuntimeError(
                f"{selector}: motion end state does not reach destination: "
                f"{destination}"
            )
        if destination not in next_first_frame_text:
            raise RuntimeError(
                f"{selector}: next first frame does not agree with destination: "
                f"{destination}"
            )
    if actual_end_state not in next_first_frame_text:
        raise RuntimeError(
            f"{selector}: next first frame does not agree with actual motion "
            "end state"
        )
    return {
        "departure_location": departure,
        "destination_location": destination,
        "actual_end_state": actual_end_state,
    }


def _validate_adjacent_cut_motion_is_distinct(
    *, scene_id: int, cut_plans: list[dict[str, Any]]
) -> None:
    """Fail closed when adjacent semantic cuts would replay the same action."""

    for index, (previous, current) in enumerate(
        zip(cut_plans, cut_plans[1:]), start=1
    ):
        previous_motion = str(previous.get("motion_brief") or "").strip()
        previous_end = str(previous.get("motion_end_state") or "").strip()
        current_motion = str(current.get("motion_brief") or "").strip()
        current_end = str(current.get("motion_end_state") or "").strip()
        if previous_motion == current_motion and previous_end == current_end:
            raise RuntimeError(
                f"scene{scene_id} adjacent cuts replay identical motion: "
                f"cut{index:02d} -> cut{index + 1:02d}; "
                "author distinct exact obligation start/motion/end states or "
                "merge the semantic responsibilities"
            )


def _author_story_with_codex(
    *,
    run_dir: Path,
    topic: str,
    target_duration_seconds: int,
) -> None:
    """Invoke the canonical LLM Story Architect / Scene Author pipeline."""

    _run_materialization_subprocess(
        run_dir,
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "author-story-with-codex.py"),
            "--research",
            str(run_dir / "research.md"),
            "--output",
            str(run_dir / "story.md"),
            "--topic",
            topic,
            "--target-duration-seconds",
            str(target_duration_seconds),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _bind_experience_metadata(
    manifest: dict[str, Any],
    *,
    experience: str,
    source_run: Path | None,
) -> None:
    metadata = manifest["video_metadata"]
    metadata["experience"] = experience
    if source_run is None:
        return
    source_run_rel = source_run.relative_to(REPO_ROOT).as_posix()
    metadata["source_run"] = source_run_rel
    metadata["source_story"] = f"{source_run_rel}/story.md"
    metadata["source_assets"] = f"{source_run_rel}/assets"


WORLD_WALK_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
WorldWalkSourceReferenceLease = tuple[tuple[str, str], ...]
WORLD_WALK_PROMPT_CONTRACT = (
    "観察者POV。カメラは物語へ介入せず、自然な歩行速度と安定した水平線を保つ。"
    "人物は中景から遠景に置き、顔の大写し、自撮り、肩越し密着、急接近を避ける。"
    "序盤は物語を進めず参照世界の場所と生活痕跡を観察し、中盤以降に物語の出来事を遠目に見かける。"
)


def _world_walk_source_reference_inventory(
    source_run: Path,
    *,
    source_root_identity: PathIdentity,
) -> WorldWalkSourceReferenceLease:
    root_descriptor = open_directory_nofollow(
        source_run,
        expected_identity=source_root_identity,
    )
    assets_descriptor: int | None = None
    try:
        try:
            assets_descriptor = os.open(
                "assets",
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=root_descriptor,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "world_walk source run has no reusable asset images"
            ) from exc
        inventory_paths: list[Path] = []

        def scan_directory(
            directory_descriptor: int,
            relative_parent: Path,
        ) -> None:
            for name in sorted(os.listdir(directory_descriptor)):
                if name in {"", ".", ".."} or "/" in name:
                    raise ValueError(
                        f"unsafe world-walk source asset entry: {name!r}"
                    )
                entry = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                relative = relative_parent / name
                if stat.S_ISDIR(entry.st_mode):
                    child_descriptor = os.open(
                        name,
                        os.O_RDONLY
                        | getattr(os, "O_CLOEXEC", 0)
                        | getattr(os, "O_DIRECTORY", 0)
                        | getattr(os, "O_NOFOLLOW", 0),
                        dir_fd=directory_descriptor,
                    )
                    try:
                        opened = os.fstat(child_descriptor)
                        if (
                            opened.st_dev,
                            opened.st_ino,
                        ) != (
                            entry.st_dev,
                            entry.st_ino,
                        ):
                            raise ValueError(
                                "world-walk source asset directory "
                                f"identity changed: {relative.as_posix()}"
                            )
                        scan_directory(child_descriptor, relative)
                    finally:
                        os.close(child_descriptor)
                    continue
                if stat.S_ISLNK(entry.st_mode):
                    raise ValueError(
                        "world-walk source assets must not contain symlinks: "
                        f"{relative.as_posix()}"
                    )
                if not stat.S_ISREG(entry.st_mode):
                    raise ValueError(
                        "world-walk source assets must contain only regular "
                        f"files and directories: {relative.as_posix()}"
                    )
                if relative.suffix.lower() in WORLD_WALK_IMAGE_SUFFIXES:
                    inventory_paths.append(relative)

        scan_directory(assets_descriptor, Path())
    finally:
        if assets_descriptor is not None:
            os.close(assets_descriptor)
        os.close(root_descriptor)
    inventory = tuple(
        (
            (Path("assets") / relative).as_posix(),
            sha256_regular_file_nofollow(
                source_run,
                Path("assets") / relative,
                expected_root_identity=source_root_identity,
            ),
        )
        for relative in sorted(inventory_paths)
    )
    return inventory


def _freeze_world_walk_source_reference_inventory(
    source_run: Path,
    *,
    source_root_identity: PathIdentity | None = None,
) -> WorldWalkSourceReferenceLease:
    expected_identity = (
        source_root_identity
        if source_root_identity is not None
        else directory_identity_nofollow(source_run)
    )
    first = _world_walk_source_reference_inventory(
        source_run,
        source_root_identity=expected_identity,
    )
    second = _world_walk_source_reference_inventory(
        source_run,
        source_root_identity=expected_identity,
    )
    if first != second:
        raise RuntimeError(
            "world_walk source reference inventory changed while freezing"
        )
    if not first:
        raise RuntimeError(
            "world_walk source run has no reusable asset images"
        )
    return first


def _verify_world_walk_source_reference_inventory(
    source_run: Path,
    *,
    source_root_identity: PathIdentity,
    source_reference_lease: WorldWalkSourceReferenceLease,
) -> None:
    current = _world_walk_source_reference_inventory(
        source_run,
        source_root_identity=source_root_identity,
    )
    if current != source_reference_lease:
        raise RuntimeError(
            "world_walk source reference inventory changed"
        )


def _verify_world_walk_source_story(
    source_run: Path,
    *,
    source_root_identity: PathIdentity,
    source_story_sha256: str,
) -> None:
    story_bytes = read_regular_file_nofollow(
        source_run,
        "story.md",
        expected_root_identity=source_root_identity,
    )
    if hashlib.sha256(story_bytes).hexdigest() != source_story_sha256:
        raise RuntimeError("world_walk source story sha256 changed")


def _materialize_world_walk_source_references(
    source_run: Path,
    run_dir: Path,
    *,
    source_root_identity: PathIdentity | None = None,
    destination_root_identity: PathIdentity | None = None,
    source_reference_lease: WorldWalkSourceReferenceLease | None = None,
    source_story_sha256: str | None = None,
) -> list[str]:
    expected_source_identity = (
        source_root_identity
        if source_root_identity is not None
        else directory_identity_nofollow(source_run)
    )
    expected_destination_identity = (
        destination_root_identity
        if destination_root_identity is not None
        else directory_identity_nofollow(run_dir)
    )
    lease = (
        source_reference_lease
        if source_reference_lease is not None
        else _freeze_world_walk_source_reference_inventory(
            source_run,
            source_root_identity=expected_source_identity,
        )
    )
    _verify_world_walk_source_reference_inventory(
        source_run,
        source_root_identity=expected_source_identity,
        source_reference_lease=lease,
    )
    if source_story_sha256 is not None:
        _verify_world_walk_source_story(
            source_run,
            source_root_identity=expected_source_identity,
            source_story_sha256=source_story_sha256,
        )
    references: list[str] = []
    copied: list[tuple[Path, str]] = []
    try:
        for source_relative_text, expected_sha256 in lease[:12]:
            source_relative = Path(source_relative_text)
            relative = source_relative.relative_to("assets")
            output_relative = (
                Path("assets") / "source_references" / relative
            )
            copied_sha256 = copy_regular_file_atomic_nofollow(
                source_root=source_run,
                source_relative=source_relative,
                destination_root=run_dir,
                destination_relative=output_relative,
                expected_source_root_identity=expected_source_identity,
                expected_destination_root_identity=expected_destination_identity,
                expected_sha256=expected_sha256,
            )
            copied.append((output_relative, copied_sha256))
            references.append(output_relative.as_posix())
        _verify_world_walk_source_reference_inventory(
            source_run,
            source_root_identity=expected_source_identity,
            source_reference_lease=lease,
        )
        if source_story_sha256 is not None:
            _verify_world_walk_source_story(
                source_run,
                source_root_identity=expected_source_identity,
                source_story_sha256=source_story_sha256,
            )
    except Exception:
        for output_relative, copied_sha256 in reversed(copied):
            unlink_regular_file_verified_nofollow(
                root=run_dir,
                relative_path=output_relative,
                expected_root_identity=expected_destination_identity,
                expected_sha256=copied_sha256,
            )
        raise
    return references


def _apply_world_walk_asset_generation_contract(
    *,
    asset_plan: dict[str, Any],
    source_references: list[str],
) -> None:
    if not source_references:
        raise RuntimeError("world_walk requires concrete source asset references")
    selected_references = list(source_references[:4])
    for entry in asset_plan.get("assets") or []:
        if not isinstance(entry, dict):
            continue
        generation_plan = entry.get("generation_plan")
        if not isinstance(generation_plan, dict):
            continue
        generation_plan["reference_inputs"] = list(selected_references)
        generation_plan["execution_lane"] = "standard"
        generation_plan["bootstrap_allowed"] = False
        fixed_prompts = entry.setdefault("fixed_prompts", [])
        if (
            isinstance(fixed_prompts, list)
            and WORLD_WALK_PROMPT_CONTRACT not in fixed_prompts
        ):
            fixed_prompts.append(WORLD_WALK_PROMPT_CONTRACT)


def _apply_world_walk_generation_contract(
    *,
    script: dict[str, Any],
    manifest: dict[str, Any],
    source_references: list[str],
) -> None:
    if not source_references:
        raise RuntimeError("world_walk requires concrete source asset references")
    world_walk_contract = {
        "viewpoint": "observer_pov",
        "camera_distance": "medium_to_long",
        "intervention": "forbidden",
        "opening": "asset_walk_without_story_progression",
        "story_encounter": "characters_and_events_are_seen_from_a_distance",
        "prompt_requirement": WORLD_WALK_PROMPT_CONTRACT,
        "source_references": source_references,
    }
    script["world_walk_contract"] = deepcopy(world_walk_contract)
    manifest["world_walk_contract"] = deepcopy(world_walk_contract)
    assets = manifest.get("assets")
    if isinstance(assets, dict):
        style_guide = assets.get("style_guide")
        if isinstance(style_guide, dict):
            style_guide["reference_images"] = list(source_references)
            style_guide["world_walk_prompt_contract"] = WORLD_WALK_PROMPT_CONTRACT

    for document in (script, manifest):
        for scene_index, scene in enumerate(document.get("scenes") or [], start=1):
            if not isinstance(scene, dict):
                continue
            phase = (
                "asset_walk_without_story_progression"
                if scene_index <= max(1, len(document.get("scenes") or []) // 3)
                else "distant_story_encounter"
            )
            scene["world_walk_contract"] = {
                **deepcopy(world_walk_contract),
                "phase": phase,
            }
            for cut in scene.get("cuts") or []:
                if not isinstance(cut, dict):
                    continue
                cut_contract = cut.get("cut_contract")
                if isinstance(cut_contract, dict):
                    cut_contract["world_walk_contract"] = deepcopy(scene["world_walk_contract"])
                    cinematic = cut_contract.get("cinematic_contract")
                    if isinstance(cinematic, dict):
                        cinematic["world_walk_camera_rule"] = WORLD_WALK_PROMPT_CONTRACT
                scene_contract = cut.get("scene_contract")
                if isinstance(scene_contract, dict):
                    must_avoid = scene_contract.setdefault("must_avoid", [])
                    for value in ("顔の大写し", "自撮り", "肩越し密着", "観察者の物語介入"):
                        if value not in must_avoid:
                            must_avoid.append(value)

                image_generation = cut.get("image_generation")
                if not isinstance(image_generation, dict):
                    continue
                selected_references = source_references[:4]
                visual_plan = image_generation.get("first_frame_visual_plan")
                if isinstance(visual_plan, dict):
                    composition = visual_plan.setdefault("spatial_composition", {})
                    if isinstance(composition, dict):
                        composition["shot_size"] = "wide"
                        composition["camera_angle"] = WORLD_WALK_PROMPT_CONTRACT
                        composition["foreground"] = (
                            "観察者が歩ける自然な導線。観察者本人は画面に映さない"
                        )
                        if phase == "asset_walk_without_story_progression":
                            composition["midground"] = "参照世界の日常の生活痕跡と静かな空間"
                            composition["background"] = "物語の事件がまだ始まっていない遠景"
                    if phase == "asset_walk_without_story_progression":
                        temporal = visual_plan.setdefault("temporal_boundary", {})
                        if isinstance(temporal, dict):
                            temporal["event_fact_visible_in_still"] = (
                                "物語を進めず、参照世界の場所と生活痕跡だけを観察している瞬間"
                            )
                    visual_plan["world_walk_prompt_contract"] = WORLD_WALK_PROMPT_CONTRACT
                    image_generation["api_prompt_payload"] = _image_api_prompt_payload_for_scaffold(
                        first_frame_visual_plan=visual_plan,
                        character_ids=image_generation.get("character_ids") or [],
                        object_ids=image_generation.get("object_ids") or [],
                        location_ids=image_generation.get("location_ids") or [],
                        references=selected_references,
                        story_time=str(manifest.get("video_metadata", {}).get("time") or ""),
                        scene_time_of_day=str(scene.get("time_of_day") or ""),
                    )
                image_generation["references"] = selected_references
                image_generation["reference_count"] = len(selected_references)
                video_generation = cut.get("video_generation")
                if isinstance(video_generation, dict):
                    original_motion = str(video_generation.get("motion_prompt") or "").strip()
                    video_generation["motion_prompt"] = (
                        f"{WORLD_WALK_PROMPT_CONTRACT} {original_motion}".strip()
                    )


def _scene_acceptance_role_character_id(
    profile: dict[str, Any],
    *,
    scene_index: int,
    role_id: str,
) -> str:
    """Resolve an authored role once while the whole-set contract is planned."""

    normalized = str(role_id).strip()
    if normalized == "protagonist":
        return str(
            _protagonist_asset_for_cut(profile, scene_index, "")
            or profile["protagonist_asset_id"]
        )
    supporting_specs = _supporting_character_asset_specs(profile)
    direct = next(
        (
            spec
            for spec in supporting_specs
            if str(spec.get("source_character_id") or "").strip() == normalized
        ),
        None,
    )
    if direct is None:
        direct = next(
            (
                spec
                for spec in supporting_specs
                if normalized
                in {
                    str(value).strip()
                    for value in spec.get("role_tags", [])
                    if str(value).strip()
                }
            ),
            None,
        )
    if direct is not None:
        return str(direct["character_id"])
    # Unknown roles are still represented by a stable participant ID so the
    # contract cannot silently claim coverage without a visible participant.
    safe_role = re.sub(r"[^A-Za-z0-9_-]+", "-", normalized).strip("-") or "unknown"
    return f"character-role-{safe_role}"


def _scene_acceptance_source_ledger(profile: dict[str, Any]) -> dict[str, Any]:
    """Freeze the authored profile facts addressed by contract JSON Pointers."""

    return {
        "schema_version": "scene_acceptance_source_ledger_v1",
        "events": [
            {
                "event_id": f"source_event_{event_index:02d}",
                "summary": str(event).strip(),
            }
            for event_index, event in enumerate(profile.get("events", []), start=1)
            if str(event).strip()
        ],
        "adaptation_source_contract": deepcopy(
            profile.get("adaptation_source_contract") or {}
        ),
        "scene_value_amplifications": deepcopy(
            profile.get("scene_value_amplifications") or {}
        ),
    }


def _scene_acceptance_source_artifacts(
    profile: dict[str, Any],
) -> dict[str, Any]:
    ledger = _scene_acceptance_source_ledger(profile)
    return {
        "authoring_source_ledger": (
            json.dumps(
                ledger,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    }


def _scene_acceptance_source_binding_digest(value: Any) -> str:
    raw = value if isinstance(value, bytes) else canonical_json_bytes(value)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _build_scene_set_authoring_contract(
    *,
    profile: dict[str, Any],
    scene_records: list[dict[str, Any]],
    now: str,
    run_dir: Path,
) -> dict[str, Any]:
    """Build the frozen whole-scene ledger before any cut is planned."""

    source_events = [
        str(value).strip()
        for value in profile.get("events", [])
        if str(value).strip()
    ]
    source_artifacts = _scene_acceptance_source_artifacts(profile)
    source_ledger = _scene_acceptance_source_ledger(profile)
    source_digest = _scene_acceptance_source_binding_digest(
        source_artifacts["authoring_source_ledger"]
    )
    generation_seed = domain_separated_digest(
        "toc.scene_acceptance.generation.v1",
        {
            "created_at": now,
            "source_digest": source_digest,
            "scene_ids": [record["scene_id"] for record in scene_records],
        },
    ).split(":", 1)[-1][:20]
    generation_id = f"scene-authoring-{generation_seed}"
    source_bindings: dict[str, dict[str, str]] = {
        "authoring_source_ledger": {
            "path": (
                Path("logs")
                / "authoring"
                / "staging"
                / generation_id
                / "source_ledger.json"
            ).as_posix(),
            "sha256": source_digest,
        }
    }
    for artifact_name in ("story.md", "visual_value.md"):
        try:
            artifact_bytes = read_run_file_bytes_serialized(
                run_dir,
                artifact_name,
            )
        except FileNotFoundError:
            continue
        source_bindings[artifact_name.removesuffix(".md")] = {
            "path": artifact_name,
            "sha256": _scene_acceptance_source_binding_digest(
                artifact_bytes
            ),
        }
    source_refs = [
        {
            "source_ref_id": f"source-event-{event_index:02d}",
            "artifact": "authoring_source_ledger",
            "artifact_sha256": source_digest,
            "pointer": f"/events/{event_index - 1}",
            "expected_id": f"source_event_{event_index:02d}",
        }
        for event_index, _event in enumerate(source_events, start=1)
    ]
    event_id_by_text = {
        event: f"source_event_{event_index:02d}"
        for event_index, event in enumerate(source_events, start=1)
    }
    source_ref_by_event_id = {
        f"source_event_{event_index:02d}": f"source-event-{event_index:02d}"
        for event_index, _event in enumerate(source_events, start=1)
    }

    scene_source_event_ids: dict[int, list[str]] = {}
    candidate_scene_ids_by_event_id: dict[str, list[int]] = {}
    for record in scene_records:
        scene_id = int(record["scene_id"])
        event_ids = [
            event_id_by_text[event]
            for event in _scene_source_events(profile, int(record["scene_index"]))
            if event in event_id_by_text
        ]
        scene_source_event_ids[scene_id] = list(dict.fromkeys(event_ids))
        for event_id in event_ids:
            candidate_scene_ids_by_event_id.setdefault(event_id, []).append(scene_id)
    owner_scene_by_event_id: dict[str, int] = {}
    previous_owner_scene_id = int(scene_records[0]["scene_id"])
    for event_index, _event in enumerate(source_events, start=1):
        event_id = f"source_event_{event_index:02d}"
        candidate_scene_ids = candidate_scene_ids_by_event_id.get(event_id, [])
        if candidate_scene_ids:
            proposed_scene_id = min(candidate_scene_ids)
        else:
            estimated_index = min(
                len(scene_records),
                max(
                    1,
                    int(
                        (event_index - 1)
                        * len(scene_records)
                        / max(1, len(source_events))
                    )
                    + 1,
                ),
            )
            proposed_scene_id = int(scene_records[estimated_index - 1]["scene_id"])
        # Keep source-event ownership monotonic across runtime scenes so a
        # later fact is not assigned to an earlier runtime scene.
        owner_scene_id = max(previous_owner_scene_id, proposed_scene_id)
        owner_scene_by_event_id[event_id] = owner_scene_id
        previous_owner_scene_id = owner_scene_id

    evidence_catalog: list[dict[str, Any]] = []
    contract_scenes: list[dict[str, Any]] = []
    authored_end_state_by_scene: dict[int, str] = {}
    authored_handoff_by_scene: dict[int, dict[str, Any]] = {}
    beat_ids_by_scene: dict[int, list[str]] = {}
    evidence_ids_by_scene: dict[int, list[str]] = {}
    event_beat_owner: dict[str, str] = {}
    previous_time_of_day = ""
    previous_location_sequence: list[str] = []
    transition_cues: list[dict[str, Any]] = []
    first_artifact_scene_id = next(
        (
            int(record["scene_id"])
            for record in scene_records
            if bool(record.get("include_artifact"))
        ),
        None,
    )
    reveal_transition_id = (
        f"reveal-artifact-{first_artifact_scene_id}"
        if first_artifact_scene_id is not None
        else ""
    )

    for record_index, record in enumerate(scene_records):
        scene_id = int(record["scene_id"])
        scene_index = int(record["scene_index"])
        event_sequence = [
            beat
            for beat in record["scene_event"].get("event_sequence", [])
            if isinstance(beat, dict) and str(beat.get("beat_id") or "").strip()
        ]
        if not event_sequence:
            raise RuntimeError(f"scene {scene_id} has no authored event beat")
        beat_ids = [str(beat["beat_id"]).strip() for beat in event_sequence]
        beat_ids_by_scene[scene_id] = beat_ids
        owned_event_ids = [
            event_id
            for event_id, owner_scene_id in owner_scene_by_event_id.items()
            if owner_scene_id == scene_id
        ]
        owned_event_ids.sort(
            key=lambda value: int(value.rsplit("_", 1)[-1])
        )
        assigned_event_ids_by_beat = {beat_id: [] for beat_id in beat_ids}
        for owned_index, event_id in enumerate(owned_event_ids):
            preferred_index = min(len(beat_ids) - 1, 2 + owned_index)
            selected_beat_id = beat_ids[preferred_index]
            assigned_event_ids_by_beat[selected_beat_id].append(event_id)
            event_beat_owner[event_id] = selected_beat_id

        scene_evidence_ids: list[str] = []
        required_beat_specs: list[dict[str, Any]] = []
        role_binding_beats: dict[str, list[str]] = {}
        role_binding_characters: dict[str, list[str]] = {}
        non_replaceable_elements: list[dict[str, Any]] = []
        fallback_source_event_ids = scene_source_event_ids.get(scene_id) or owned_event_ids
        if not fallback_source_event_ids and source_events:
            fallback_source_event_ids = ["source_event_01"]
        fallback_source_ref_ids = [
            source_ref_by_event_id[event_id]
            for event_id in fallback_source_event_ids
            if event_id in source_ref_by_event_id
        ]
        for beat_index, beat in enumerate(event_sequence, start=1):
            beat_id = str(beat["beat_id"]).strip()
            evidence_id = f"evidence-scene{scene_id}-beat-{beat_index:02d}"
            element_id = f"element-scene{scene_id}-beat-{beat_index:02d}"
            required_evidence = [
                str(value).strip()
                for value in beat.get("required_visual_evidence", [])
                if str(value).strip()
            ]
            visible_form = (
                required_evidence[0]
                if required_evidence
                else str(beat.get("what_happens") or "").strip()
            )
            if not visible_form:
                raise RuntimeError(
                    f"scene {scene_id} beat {beat_id} has no source-specific evidence"
                )
            evidence_catalog.append(
                {
                    "evidence_id": evidence_id,
                    "owner_scene_id": scene_id,
                    "element_id": element_id,
                    "source_ref_ids": fallback_source_ref_ids,
                    "visible_form": visible_form,
                }
            )
            scene_evidence_ids.append(evidence_id)
            role_ids = [
                str(value).strip()
                for value in beat.get("required_roles", [])
                if str(value).strip()
            ]
            character_ids: list[str] = []
            for role_id in role_ids:
                character_id = _scene_acceptance_role_character_id(
                    profile,
                    scene_index=scene_index,
                    role_id=role_id,
                )
                character_ids.append(character_id)
                role_binding_beats.setdefault(role_id, []).append(beat_id)
                role_binding_characters.setdefault(role_id, []).append(character_id)
            required_beat_specs.append(
                {
                    "beat_id": beat_id,
                    "source_event_ids": assigned_event_ids_by_beat[beat_id],
                    "beat_function": str(beat.get("beat_function") or "event"),
                    "required_role_ids": list(dict.fromkeys(role_ids)),
                    "required_character_ids": list(dict.fromkeys(character_ids)),
                    "required_evidence_ids": [evidence_id],
                    "required_non_replaceable_element_ids": [element_id],
                }
            )
            non_replaceable_elements.append(
                {
                    "element_id": element_id,
                    "source_ref_ids": fallback_source_ref_ids,
                    "required_evidence_ids": [evidence_id],
                }
            )
        evidence_ids_by_scene[scene_id] = scene_evidence_ids

        time_of_day = str(record["time_of_day"])
        location_sequence = [
            str(spec.get("asset_id") or spec.get("name") or "").strip()
            for spec in record["scene_location_specs"]
            if str(spec.get("asset_id") or spec.get("name") or "").strip()
        ]
        time_changed = bool(
            record_index > 0 and time_of_day != previous_time_of_day
        )
        location_changed = bool(
            record_index > 0
            and location_sequence != previous_location_sequence
        )
        transition_required = time_changed or location_changed
        transition_cue_ids: list[str] = []
        if transition_required:
            cue_id = f"cue-{scene_records[record_index - 1]['scene_id']}-{scene_id}"
            transition_cue_ids.append(cue_id)
            transition_cues.append(
                {
                    "transition_cue_id": cue_id,
                    "owner_scene_id": scene_id,
                    "from_time_of_day": previous_time_of_day,
                    "to_time_of_day": time_of_day,
                    "from_location_ids": list(previous_location_sequence),
                    "to_location_ids": list(location_sequence),
                    "owner_beat_id": beat_ids[0],
                    "evidence_ids": [scene_evidence_ids[0]],
                }
            )
        previous_time_of_day = time_of_day
        previous_location_sequence = list(location_sequence)
        reveal_state_before = (
            "withheld"
            if first_artifact_scene_id is None or scene_id <= first_artifact_scene_id
            else "revealed"
        )
        reveal_state_after = (
            "revealed"
            if first_artifact_scene_id is not None and scene_id >= first_artifact_scene_id
            else "withheld"
        )
        allowed_reveal_transition_ids = (
            [reveal_transition_id]
            if scene_id == first_artifact_scene_id and reveal_transition_id
            else []
        )
        authored_end_state = (
            record["scene_event"].get("end_state")
            if isinstance(record["scene_event"].get("end_state"), dict)
            else {}
        )
        authored_handoff = (
            record["scene_event"].get("handoff_chain")
            if isinstance(record["scene_event"].get("handoff_chain"), dict)
            else {}
        )
        authored_incoming = (
            authored_handoff.get("incoming")
            if isinstance(authored_handoff.get("incoming"), dict)
            else {}
        )
        authored_outgoing = (
            authored_handoff.get("outgoing")
            if isinstance(authored_handoff.get("outgoing"), dict)
            else {}
        )
        authored_end_state_id = str(
            authored_end_state.get("state_id") or f"state-after-scene-{scene_id}"
        ).strip()
        authored_end_state_by_scene[scene_id] = authored_end_state_id
        authored_handoff_by_scene[scene_id] = deepcopy(authored_handoff)
        incoming_anchor = str(authored_incoming.get("anchor_id") or "").strip() or (
            "story-opening"
            if record_index == 0
            else f"handoff-{scene_records[record_index - 1]['scene_id']}-{scene_id}"
        )
        outgoing_anchor = str(authored_outgoing.get("anchor_id") or "").strip() or (
            "story-ending"
            if record_index + 1 == len(scene_records)
            else f"handoff-{scene_id}-{scene_records[record_index + 1]['scene_id']}"
        )
        contract_scenes.append(
            {
                "scene_id": scene_id,
                "owned_event_ids": owned_event_ids,
                "required_beat_specs": required_beat_specs,
                "role_bindings": [
                    {
                        "role_id": role_id,
                        "character_ids": list(
                            dict.fromkeys(role_binding_characters[role_id])
                        ),
                        "required_for_beat_ids": list(
                            dict.fromkeys(role_binding_beats[role_id])
                        ),
                    }
                    for role_id in role_binding_beats
                ],
                "reveal_state_before": {
                    "artifact-primary": reveal_state_before
                },
                "allowed_reveal_transition_ids": allowed_reveal_transition_ids,
                "reveal_state_after": {"artifact-primary": reveal_state_after},
                "time_location_transition": {
                    "time_of_day": time_of_day,
                    "continuity_from_previous": (
                        "opening"
                        if record_index == 0
                        else "elapsed_time"
                        if time_changed
                        else "location_transition"
                        if location_changed
                        else "continuous"
                    ),
                    "transition_cue_required": transition_required,
                    "transition_cue_ids": transition_cue_ids,
                    "location_sequence": location_sequence,
                },
                "incoming_handoff_anchor_id": incoming_anchor,
                "outgoing_handoff_anchor_id": outgoing_anchor,
                "causal_proof_contract": {
                    "cause_beat_id": beat_ids[0],
                    "action_beat_id": beat_ids[-1],
                    "result_state_id": authored_end_state_id,
                    "required_evidence_ids": [scene_evidence_ids[-1]],
                },
                "non_replaceable_elements": non_replaceable_elements,
            }
        )

    canonical_events = [
        {
            "event_id": event_id,
            "canonical_order_index": event_index,
            "owner_scene_id": owner_scene_by_event_id[event_id],
            "required_beat_ids": [event_beat_owner[event_id]],
            "source_ref_ids": [source_ref_by_event_id[event_id]],
        }
        for event_index, _event in enumerate(source_events, start=1)
        for event_id in [f"source_event_{event_index:02d}"]
    ]
    handoff_chain = [
        {
            "anchor_id": str(
                (
                    authored_handoff_by_scene.get(int(current["scene_id"]), {}).get("outgoing")
                    or {}
                ).get("anchor_id")
                or f"handoff-{current['scene_id']}-{following['scene_id']}"
            ),
            "owner_scene_id": current["scene_id"],
            "consumer_scene_id": following["scene_id"],
            "state_id": authored_end_state_by_scene.get(
                int(current["scene_id"]),
                f"state-after-scene-{current['scene_id']}",
            ),
            "producer_beat_id": str(
                (
                    authored_handoff_by_scene.get(int(current["scene_id"]), {}).get("outgoing")
                    or {}
                ).get("producer_beat_id")
                or beat_ids_by_scene[int(current["scene_id"])][-1]
            ),
            "consumer_beat_id": str(
                (
                    authored_handoff_by_scene.get(int(following["scene_id"]), {}).get("incoming")
                    or {}
                ).get("consumer_beat_id")
                or beat_ids_by_scene[int(following["scene_id"])][0]
            ),
            "evidence_ids": [evidence_ids_by_scene[int(current["scene_id"])][-1]],
        }
        for current, following in zip(
            contract_scenes,
            contract_scenes[1:],
        )
    ]
    reveal_ledger: list[dict[str, Any]] = []
    if first_artifact_scene_id is not None:
        owner_beat_id = beat_ids_by_scene[first_artifact_scene_id][0]
        reveal_ledger.append(
            {
                "information_id": "artifact-primary",
                "initial_state": "withheld",
                "allowed_states": ["withheld", "revealed", "carried", "known"],
                "transitions": [
                    {
                        "reveal_transition_id": reveal_transition_id,
                        "from_state": "withheld",
                        "to_state": "revealed",
                        "owner_scene_id": first_artifact_scene_id,
                        "owner_beat_id": owner_beat_id,
                        "evidence_ids": [
                            evidence_ids_by_scene[first_artifact_scene_id][0]
                        ],
                    }
                ],
            }
        )
    contract = {
        "schema_version": SCENE_ACCEPTANCE_CONTRACT_VERSION,
        "generation_id": generation_id,
        "criterion_registry_version": CRITERION_REGISTRY_VERSION,
        "criterion_registry_sha256": criterion_registry_digest(),
        "source_bindings": source_bindings,
        "source_refs": source_refs,
        "canonical_events": canonical_events,
        "evidence_catalog": evidence_catalog,
        "reveal_ledger": reveal_ledger,
        "handoff_chain": handoff_chain,
        "transition_cues": transition_cues,
        "scenes": contract_scenes,
    }
    validation = validate_scene_set_authoring_contract(
        contract,
        source_artifacts=source_artifacts,
    )
    if not validation.valid:
        raise RuntimeError(
            "scene-set authoring contract is invalid: "
            + ", ".join(validation.reason_keys)
        )
    contract["contract_digest"] = digest_scene_acceptance_contract(contract)
    return contract


def _build_scene_acceptance_drafts(
    *,
    contract: dict[str, Any],
    scene_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    handoff_by_owner = {
        int(item["owner_scene_id"]): item
        for item in contract.get("handoff_chain", [])
    }
    handoff_by_consumer = {
        int(item["consumer_scene_id"]): item
        for item in contract.get("handoff_chain", [])
    }
    reveal_by_scene: dict[int, list[dict[str, Any]]] = {}
    for ledger in contract.get("reveal_ledger", []):
        for transition in ledger.get("transitions", []):
            reveal_by_scene.setdefault(int(transition["owner_scene_id"]), []).append(
                transition
            )
    cue_by_scene: dict[int, list[dict[str, Any]]] = {}
    for cue in contract.get("transition_cues", []):
        cue_by_scene.setdefault(int(cue["owner_scene_id"]), []).append(cue)
    record_by_scene_id = {
        int(record["scene_id"]): record for record in scene_records
    }
    drafts: list[dict[str, Any]] = []
    for scene_contract in contract["scenes"]:
        scene_id = int(scene_contract["scene_id"])
        record = record_by_scene_id[scene_id]
        incoming_handoff = handoff_by_consumer.get(scene_id)
        outgoing_handoff = handoff_by_owner.get(scene_id)
        scene_reveals = reveal_by_scene.get(scene_id, [])
        scene_cues = cue_by_scene.get(scene_id, [])
        beat_entries: list[dict[str, Any]] = []
        beat_specs = scene_contract["required_beat_specs"]
        for beat_index, beat_spec in enumerate(beat_specs):
            beat_id = str(beat_spec["beat_id"])
            beat_entries.append(
                {
                    "beat_id": beat_id,
                    "source_event_ids": list(beat_spec["source_event_ids"]),
                    "role_ids": list(beat_spec["required_role_ids"]),
                    "participant_character_ids": list(
                        beat_spec["required_character_ids"]
                    ),
                    "evidence_ids": list(beat_spec["required_evidence_ids"]),
                    "required_non_replaceable_element_ids": list(
                        beat_spec["required_non_replaceable_element_ids"]
                    ),
                    "reveal_transition_ids": [
                        str(item["reveal_transition_id"])
                        for item in scene_reveals
                        if str(item["owner_beat_id"]) == beat_id
                    ],
                    "transition_cue_ids": [
                        str(item["transition_cue_id"])
                        for item in scene_cues
                        if str(item["owner_beat_id"]) == beat_id
                    ],
                    "incoming_handoff_anchor_ids": (
                        [str(incoming_handoff["anchor_id"])]
                        if beat_index == 0 and incoming_handoff is not None
                        else []
                    ),
                    "outgoing_handoff_anchor_ids": (
                        [str(outgoing_handoff["anchor_id"])]
                        if beat_index + 1 == len(beat_specs)
                        and outgoing_handoff is not None
                        else []
                    ),
                    "result_state_id": str(
                        scene_contract["causal_proof_contract"]["result_state_id"]
                    ),
                }
            )
        participants = [
            {
                "character_id": character_id,
                "role_ids": [str(binding["role_id"])],
                "visibility": "visible",
                "required_for_beat_ids": list(binding["required_for_beat_ids"]),
                "evidence_ids": list(
                    dict.fromkeys(
                        evidence_id
                        for beat_spec in beat_specs
                        if str(binding["role_id"])
                        in beat_spec["required_role_ids"]
                        for evidence_id in beat_spec["required_evidence_ids"]
                    )
                ),
            }
            for binding in scene_contract["role_bindings"]
            for character_id in binding["character_ids"]
        ]
        draft = {
            "schema_version": SCENE_DRAFT_VERSION,
            "generation_id": contract["generation_id"],
            "scene_id": scene_id,
            "contract_digest": contract["contract_digest"],
            "scene_slice_digest": digest_scene_slice(contract, scene_id),
            "scene_intent": record["scene_intent"],
            "scene_event": {"event_sequence": beat_entries},
            "participants": participants,
            "handoff_refs": {
                "incoming": (
                    [
                        {
                            "anchor_id": incoming_handoff["anchor_id"],
                            "state_id": incoming_handoff["state_id"],
                            "evidence_ids": incoming_handoff["evidence_ids"],
                        }
                    ]
                    if incoming_handoff is not None
                    else []
                ),
                "outgoing": (
                    [
                        {
                            "anchor_id": outgoing_handoff["anchor_id"],
                            "state_id": outgoing_handoff["state_id"],
                            "evidence_ids": outgoing_handoff["evidence_ids"],
                        }
                    ]
                    if outgoing_handoff is not None
                    else []
                ),
            },
        }
        validation = validate_scene_draft(draft, contract)
        if not validation.valid:
            raise RuntimeError(
                f"scene {scene_id} authoring preflight failed: "
                + ", ".join(validation.reason_keys)
            )
        drafts.append(draft)
    return drafts


def _run_scene_acceptance_preflight(
    contract: dict[str, Any],
    drafts: list[dict[str, Any]],
    *,
    source_artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation = validate_scene_set_preflight(
        contract,
        drafts,
        source_artifacts=source_artifacts,
    )
    checks = validation.to_dict()
    report = {
        "status": "passed" if validation.valid else "failed",
        "generation_id": contract["generation_id"],
        "contract_digest": contract["contract_digest"],
        "criterion_registry_digest": contract["criterion_registry_sha256"],
        "source_digest": domain_separated_digest(
            "toc.scene_acceptance.sources.v1",
            contract["source_bindings"],
        ),
        "checks": checks.get("findings", []),
        "blocking_reason_keys": list(validation.reason_keys),
        "scene_draft_digests": [
            digest_scene_draft(draft)
            for draft in drafts
        ],
    }
    report["preflight_digest"] = str(
        validation.metadata.get("preflight_digest") or ""
    )
    if not report["preflight_digest"]:
        raise RuntimeError("scene-set preflight did not produce a digest")
    if not validation.valid:
        raise RuntimeError(
            "scene-set authoring preflight failed: "
            + ", ".join(validation.reason_keys)
        )
    return report


def _require_current_scene_acceptance_before_publish(
    script: dict[str, Any],
    manifest: dict[str, Any],
    *,
    profile: dict[str, Any],
    run_dir: Path,
) -> None:
    """Fail closed before canonical script/manifest or requests are written."""

    source_artifacts = _scene_acceptance_source_artifacts(profile)
    validation = validate_scene_set_authoring_contract(
        script,
        source_artifacts=source_artifacts,
    )
    if not validation.valid:
        raise RuntimeError(
            "scene acceptance contract is not publishable: "
            + ", ".join(validation.reason_keys)
        )
    contract = script.get("scene_set_authoring_contract")
    if not isinstance(contract, dict):
        raise RuntimeError("scene_set_authoring_contract is missing before publish")
    drafts = [
        scene.get("scene_acceptance_draft")
        for scene in script.get("scenes", [])
        if isinstance(scene, dict)
    ]
    if not drafts or any(not isinstance(draft, dict) for draft in drafts):
        raise RuntimeError("scene acceptance draft set is incomplete before publish")
    for binding_name, binding in contract.get("source_bindings", {}).items():
        if not isinstance(binding, dict):
            raise RuntimeError(
                f"scene acceptance source binding is invalid: {binding_name}"
            )
        if binding_name == "authoring_source_ledger":
            current_value: Any = source_artifacts[binding_name]
        else:
            relative_path = str(binding.get("path") or "").strip()
            if not relative_path:
                raise RuntimeError(
                    f"scene acceptance source binding is missing: {binding_name}"
                )
            try:
                current_value = read_run_file_bytes_serialized(
                    run_dir,
                    relative_path,
                )
            except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
                raise RuntimeError(
                    f"scene acceptance source binding is missing: {binding_name}"
                ) from exc
        if _scene_acceptance_source_binding_digest(current_value) != binding.get(
            "sha256"
        ):
            raise RuntimeError(
                f"scene acceptance source binding is stale: {binding_name}"
            )
    current_report = _run_scene_acceptance_preflight(
        contract,
        drafts,
        source_artifacts=source_artifacts,
    )
    stored_report = script.get("authoring_preflight")
    projection = manifest.get("scene_acceptance_contract")
    if not isinstance(stored_report, dict) or not isinstance(projection, dict):
        raise RuntimeError("scene acceptance preflight projection is missing")
    expected = {
        "contract_digest": contract.get("contract_digest"),
        "preflight_digest": current_report.get("preflight_digest"),
        "generation_id": contract.get("generation_id"),
    }
    for field, value in expected.items():
        if stored_report.get(field) != value or projection.get(field) != value:
            raise RuntimeError(
                f"scene acceptance {field} is stale before publish"
            )


def _canonical_event_coverage_matrix_from_contract(
    contract: dict[str, Any],
    profile: dict[str, Any],
) -> dict[str, Any]:
    source_events = [
        str(value).strip()
        for value in profile.get("events", [])
        if str(value).strip()
    ]
    rows: list[dict[str, Any]] = []
    canonical_events = sorted(
        contract.get("canonical_events", []),
        key=lambda item: int(item["canonical_order_index"]),
    )
    for event in canonical_events:
        order_index = int(event["canonical_order_index"])
        importance = (
            "critical"
            if order_index in {1, len(canonical_events)}
            else "high"
            if order_index in {2, 3, 4, len(canonical_events) - 1}
            else "medium"
        )
        rows.append(
            {
                "source_event_id": event["event_id"],
                "source_event_summary": (
                    source_events[order_index - 1]
                    if order_index - 1 < len(source_events)
                    else ""
                ),
                "importance": importance,
                "required": importance in {"critical", "high"},
                "must_appear_as": "scene",
                "canonical_order_index": order_index,
                "assigned_scene_ids": [event["owner_scene_id"]],
                "assigned_event_beat_ids": list(event["required_beat_ids"]),
                "omission_reason": "",
                "adaptation_change_reason": "",
                "human_approval_required": False,
            }
        )
    return {
        "policy_version": "canonical_event_coverage_matrix_v1",
        "source": ["scene_set_authoring_contract.canonical_events"],
        "contract_digest": contract["contract_digest"],
        "source_story_events": rows,
    }


def _build_script_and_manifest(
    topic: str,
    run_dir: Path,
    now: str,
    profile: dict[str, Any],
    *,
    experience: str = "cinematic_story",
    source_run: Path | None = None,
    source_references: list[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    script_scenes: list[dict[str, Any]] = []
    manifest_scenes: list[dict[str, Any]] = []
    selectors: list[str] = []
    scene_event_inputs: list[dict[str, Any]] = []
    scene_event_outputs: list[dict[str, Any]] = []
    scene_generation_prompts: list[dict[str, Any]] = []
    duration_plan = dict(profile.get("duration_plan") or build_duration_plan().to_dict())
    scene_targets = [int(value) for value in profile.get("scene_target_durations") or []]
    _write_cut_design_context(
        run_dir,
        now=now,
        topic=topic,
        phase="cut_design_init",
        profile=profile,
        partial_counts={"scene_event_inputs": 0, "scene_event_outputs": 0, "scene_generation_prompts": 0, "selectors": 0},
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
    _write_scene_design_json(
        run_dir,
        SCENE_GENERATION_PROMPTS_FILENAME,
        {
            "schema_version": "scene_generation_prompt_log_v1",
            "created_at": now,
            "topic": topic,
            "source": str(run_dir / "story.md"),
            "scene_count": 0,
            "scenes": scene_generation_prompts,
        },
    )
    protagonist_asset = profile["protagonist_asset_id"]
    artifact_asset = profile["artifact_asset_id"]
    run_variant = profile.get("run_variant", {})
    protagonist_ref = f"assets/characters/{protagonist_asset}.png"
    artifact_ref = f"assets/{profile['artifact_output_dir']}/{artifact_asset}.png"
    # Pass 1 deliberately stops at scene intent/event.  No cut, camera, image,
    # motion, request, or manifest work is allowed until the entire scene set
    # has passed the deterministic acceptance contract.
    scene_authoring_records: list[dict[str, Any]] = []
    for idx, title in enumerate(profile["scene_titles"], start=1):
        time_of_day = _scene_time_of_day(profile, idx)
        time_of_day_visual_basis = _scene_time_of_day_visual_basis(profile, idx)
        include_artifact = _scene_uses_artifact(profile, idx)
        location_spec = _location_spec_for_scene(profile, idx)
        scene_location_specs = _location_specs_for_scene_sequence(profile, idx)
        location_sequence = [str(spec["name"]) for spec in scene_location_specs]
        location_segments = _scene_location_segments(profile, idx)
        scene_id = _runtime_scene_id(idx)
        scene_generation = _scene_generation_for_scene(
            topic=topic,
            scene_id=scene_id,
            idx=idx,
            title=title,
            location_spec=location_spec,
            include_artifact=include_artifact,
            profile=profile,
        )
        scene_intent = _scene_intent_for_cut_design(
            title=title,
            idx=idx,
            location_spec=location_spec,
            profile=profile,
            include_artifact=include_artifact,
        )
        scene_event = _scene_event_for_cut_design(
            title=title,
            idx=idx,
            scene_intent=scene_intent,
            location_name=str(location_spec["name"]),
            location_id=str(location_spec.get("asset_id") or ""),
            profile=profile,
            include_artifact=include_artifact,
        )
        scene_intent["story_event_obligations"] = (
            _story_event_obligations_from_scene_event(scene_event)
        )
        scene_authoring_records.append(
            {
                "scene_id": scene_id,
                "scene_index": idx,
                "title": title,
                "time_of_day": time_of_day,
                "time_of_day_visual_basis": time_of_day_visual_basis,
                "include_artifact": include_artifact,
                "location_spec": location_spec,
                "scene_location_specs": scene_location_specs,
                "location_sequence": location_sequence,
                "location_segments": location_segments,
                "scene_generation": scene_generation,
                "scene_intent": scene_intent,
                "scene_event": scene_event,
            }
        )
    scene_set_authoring_contract = _build_scene_set_authoring_contract(
        profile=profile,
        scene_records=scene_authoring_records,
        now=now,
        run_dir=run_dir,
    )
    authoring_instructions = [
        {
            "criterion_id": criterion["criterion_id"],
            "owner": criterion["owner"],
            "instruction": criterion["authoring_instruction"],
            "required_inputs": criterion["required_inputs"],
            }
            for criterion in criterion_registry_payload()
        ]
    for authored_record in scene_authoring_records:
        authored_record["scene_generation"]["scene_acceptance_prompt_packet"] = {
            "schema_version": "scene_authoring_prompt_packet_v1",
            "generation_id": scene_set_authoring_contract["generation_id"],
            "contract_digest": scene_set_authoring_contract["contract_digest"],
            "scene_contract_slice": build_scene_slice(
                scene_set_authoring_contract,
                int(authored_record["scene_id"]),
            ),
            "criterion_registry_version": CRITERION_REGISTRY_VERSION,
            "criterion_registry_sha256": scene_set_authoring_contract[
                "criterion_registry_sha256"
            ],
            "authoring_instructions": authoring_instructions,
            "output_contract": SCENE_DRAFT_VERSION,
        }
    scene_acceptance_drafts = _build_scene_acceptance_drafts(
        contract=scene_set_authoring_contract,
        scene_records=scene_authoring_records,
    )
    authoring_preflight = _run_scene_acceptance_preflight(
        scene_set_authoring_contract,
        scene_acceptance_drafts,
        source_artifacts=_scene_acceptance_source_artifacts(profile),
    )
    authoring_record_by_scene_id = {
        int(record["scene_id"]): record for record in scene_authoring_records
    }
    acceptance_draft_by_scene_id = {
        int(draft["scene_id"]): draft for draft in scene_acceptance_drafts
    }
    total_duration_seconds = 0
    for idx, title in enumerate(profile["scene_titles"], start=1):
        time_of_day = _scene_time_of_day(profile, idx)
        time_of_day_visual_basis = _scene_time_of_day_visual_basis(profile, idx)
        include_artifact = _scene_uses_artifact(profile, idx)
        location_spec = _location_spec_for_scene(profile, idx)
        scene_location_specs = _location_specs_for_scene_sequence(profile, idx)
        location_sequence = [str(spec["name"]) for spec in scene_location_specs]
        location_segments = _scene_location_segments(profile, idx)
        location_ref = str(location_spec["output"])
        location_name = str(location_spec["name"])
        scene_id = _runtime_scene_id(idx)
        scene_context = {
            "scene_id": scene_id,
            "scene_index": idx,
            "title": title,
            "time_of_day": time_of_day,
            "time_of_day_visual_basis": time_of_day_visual_basis,
            "location_id": location_spec.get("asset_id"),
            "location_name": location_name,
            "location_mode": "sequence" if len(location_sequence) > 1 else "single",
            "location_sequence": location_sequence,
            "location_segments": location_segments,
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
                "scene_generation_prompts": len(scene_generation_prompts),
                "selectors": len(selectors),
            },
        )
        authored_record = authoring_record_by_scene_id[scene_id]
        scene_generation = deepcopy(authored_record["scene_generation"])
        scene_intent = deepcopy(authored_record["scene_intent"])
        scene_event_inputs.append(
            {
                "scene_id": scene_id,
                "scene_index": idx,
                "title": title,
                "topic": topic,
                "time_of_day": time_of_day,
                "time_of_day_visual_basis": time_of_day_visual_basis,
                "location": location_spec,
                "location_sequence": location_sequence,
                "location_segments": location_segments,
                "include_artifact": include_artifact,
                "scene_generation": scene_generation,
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
        scene_generation_prompts.append(
            {
                "scene_id": scene_id,
                "scene_index": idx,
                "title": title,
                "time_of_day": time_of_day,
                "time_of_day_visual_basis": time_of_day_visual_basis,
                "location_sequence": location_sequence,
                "scene_generation": scene_generation,
            }
        )
        _write_scene_design_json(
            run_dir,
            SCENE_GENERATION_PROMPTS_FILENAME,
            {
                "schema_version": "scene_generation_prompt_log_v1",
                "created_at": now,
                "topic": topic,
                "source": str(run_dir / "story.md"),
                "scene_count": len(scene_generation_prompts),
                "scenes": scene_generation_prompts,
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
                "scene_generation_prompts": len(scene_generation_prompts),
                "selectors": len(selectors),
            },
        )
        scene_event = deepcopy(authored_record["scene_event"])
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
                "scene_generation_prompts": len(scene_generation_prompts),
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
        _validate_adjacent_cut_motion_is_distinct(
            scene_id=scene_id,
            cut_plans=cut_plans,
        )
        scene_major_character_ids = list(
            dict.fromkeys(
                [
                    _protagonist_asset_for_cut(profile, idx, str(cut_plan.get("obligation_id") or ""))
                    for cut_plan in cut_plans
                ]
                + _supporting_character_ids_for_scene(profile, idx)
                + [
                    _scene_acceptance_role_character_id(
                        profile,
                        scene_index=idx,
                        role_id=str(role_id),
                    )
                    for beat in event_sequence
                    if isinstance(beat, dict)
                    for role_id in beat.get("required_roles", []) or []
                    if str(role_id).strip()
                ]
            )
        )
        scene_character_state_timeline = _scene_character_state_timeline_for_scaffold(
            scene_id=scene_id,
            scene_event=scene_event,
            scene_intent=scene_intent,
            profile=profile,
            location_name=location_name,
            major_character_ids=scene_major_character_ids,
        )
        scene_film_coverage_plan = _scene_film_coverage_plan_for_scaffold(
            scene_id=scene_id,
            scene_event=scene_event,
            cut_plans=cut_plans,
            scene_character_state_timeline=scene_character_state_timeline,
            has_important_object=include_artifact or _scene_has_supporting_object(profile, idx),
        )
        scene_state_progression_plan = _scene_state_progression_plan_for_scaffold(
            scene_id=scene_id,
            title=title,
            scene_intent=scene_intent,
            scene_event=scene_event,
            cut_plans=cut_plans,
            location_name=location_name,
        )
        cut_state_progression_by_selector = {
            str(item.get("cut_selector") or ""): item
            for item in scene_state_progression_plan.get("cut_progression_map", [])
            if isinstance(item, dict) and str(item.get("cut_selector") or "").strip()
        }
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
                "scene_generation_prompts": len(scene_generation_prompts),
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
        scene_target_seconds = (
            scene_targets[idx - 1]
            if idx - 1 < len(scene_targets)
            else len(cut_plans) * 8
        )
        cut_duration_seconds = _allocate_scene_cut_durations(
            scene_target_seconds=scene_target_seconds,
            cut_count=len(cut_plans),
        )
        scene_duration_seconds = sum(cut_duration_seconds)
        total_duration_seconds += scene_duration_seconds
        cuts: list[dict[str, Any]] = []
        manifest_cuts: list[dict[str, Any]] = []
        scene_shot_records: list[dict[str, Any]] = []
        for cut_number, cut_plan in enumerate(cut_plans, start=1):
            cut_target_seconds = cut_duration_seconds[cut_number - 1]
            cut_duration_exception = _duration_exception_for_cut(
                cut_target_seconds
            )
            primary_event_beat_id_for_location = str(
                cut_plan.get("primary_event_beat_id") or ""
            ).strip()
            primary_event_beat_for_location = next(
                (
                    beat
                    for beat in scene_event.get("event_sequence", [])
                    if isinstance(beat, dict)
                    and str(beat.get("beat_id") or "").strip()
                    == primary_event_beat_id_for_location
                ),
                {},
            )
            concrete_event_for_location = (
                primary_event_beat_for_location.get("concrete_event")
                if isinstance(primary_event_beat_for_location.get("concrete_event"), dict)
                else {}
            )
            event_location_name = str(
                cut_plan.get("background")
                or concrete_event_for_location.get("where")
                or ""
            ).strip()
            matching_location_spec = next(
                (
                    spec
                    for spec in scene_location_specs
                    if str(spec.get("name") or "") == event_location_name
                ),
                None,
            )
            if matching_location_spec is None:
                raise RuntimeError(
                    f"cut primary event location is not bound to this scene route: {event_location_name or '<empty>'}"
                )
            allowed_reveal_locations = {
                str(item).strip()
                for item in cut_plan.get("allowed_new_reveal_elements") or []
                if str(item).strip() in location_sequence
            }
            provider_cut_plan = deepcopy(cut_plan)
            for field_name in (
                "target_beat",
                "visual_proof",
                "first_frame_brief",
                "static_first_frame_rule",
                "foreground",
                "midground",
                "background",
                "visible_action",
                "visible_reaction",
                "causal_proof",
                "motion_brief",
                "motion_end_state",
                "visual_evidence",
                "must_show_extra",
                "visible_character_state",
            ):
                route_locations_to_abstract = (
                    [
                        location
                        for location in location_sequence
                        if location not in allowed_reveal_locations
                    ]
                    if field_name in {"motion_brief", "motion_end_state"}
                    else location_sequence
                )
                provider_cut_plan[field_name] = _abstract_non_primary_route_locations(
                    cut_plan.get(field_name),
                    primary_location=event_location_name,
                    route_locations=route_locations_to_abstract,
                )
            provider_location_text = " / ".join(
                str(provider_cut_plan.get(key) or "")
                for key in (
                    "target_beat",
                    "visual_proof",
                    "first_frame_brief",
                    "foreground",
                    "midground",
                    "background",
                )
            )
            cross_locations = [
                other_location
                for other_location in location_sequence
                if other_location != event_location_name
                and other_location in provider_location_text
                and other_location not in allowed_reveal_locations
            ]
            if cross_locations:
                cross_location_fields = [
                    key
                    for key in (
                        "target_beat",
                        "visual_proof",
                        "first_frame_brief",
                        "foreground",
                        "midground",
                        "background",
                    )
                    if any(
                        location in str(provider_cut_plan.get(key) or "")
                        for location in cross_locations
                    )
                ]
                raise RuntimeError(
                    f"scene{scene_id} cut{cut_number:02d} provider fields mix locations "
                    f"outside primary event location {event_location_name}: "
                    + ", ".join(cross_locations)
                    + f" (fields: {', '.join(cross_location_fields)})"
                )
            location_spec = matching_location_spec
            location_ref = str(location_spec["output"])
            location_name = str(location_spec["name"])
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
                    "scene_generation_prompts": len(scene_generation_prompts),
                    "selectors": len(selectors),
                    "manifest_cuts_in_current_scene": len(manifest_cuts),
                },
            )
            obligation_id = str(cut_plan.get("obligation_id"))
            focal_character_name = str(
                cut_plan.get("primary_subject_name") or profile["protagonist_name"]
            ).strip()
            first_frame_character_asset_overrides = (
                _validate_first_frame_character_asset_overrides(
                    profile,
                    cut_plan["first_frame_character_asset_overrides"]
                    if "first_frame_character_asset_overrides" in cut_plan
                    else _MISSING_POLICY_VALUE,
                    context=selector,
                )
            )
            first_frame_excluded_object_ids = (
                _validate_first_frame_excluded_object_ids(
                    profile,
                    cut_plan["first_frame_excluded_object_ids"]
                    if "first_frame_excluded_object_ids" in cut_plan
                    else _MISSING_POLICY_VALUE,
                    context=selector,
                )
            )
            first_frame_excluded_tokens = _first_frame_exclusion_tokens(
                profile, first_frame_excluded_object_ids
            )
            first_frame_location_name = str(
                _sanitize_first_frame_prose(
                    location_name,
                    excluded_tokens=first_frame_excluded_tokens,
                )
                or "承認済みの場所"
            ).strip()

            def is_first_frame_excluded_object_evidence(value: Any) -> bool:
                text = str(value or "").strip()
                return any(
                    token in text
                    for token in first_frame_excluded_tokens
                )

            cut_uses_artifact = (
                _cut_uses_artifact(
                    profile,
                    idx,
                    obligation_id,
                    include_artifact=include_artifact,
                )
                and str(profile.get("artifact_asset_id") or "").strip()
                not in first_frame_excluded_object_ids
            )
            must_show = list(
                dict.fromkeys(
                    phrase
                    for phrase in (
                        _drawable_phrase_for_scaffold(item)
                        for item in [focal_character_name, *cut_plan["must_show_extra"]]
                    )
                    if phrase and not is_first_frame_excluded_object_evidence(phrase)
                )
            )
            if not cut_uses_artifact:
                must_show = [item for item in must_show if item != profile["artifact_name"]]
            if cut_uses_artifact and profile["artifact_name"] not in must_show:
                must_show.append(profile["artifact_name"])
            if "光" not in must_show:
                must_show.append("光")
            drawable_evidence = _cut_specific_drawable_evidence_for_scaffold(
                {
                    "must_show": must_show,
                    "visual_evidence": [
                        *(
                            item
                            for item in cut_plan.get("visual_evidence", []) or []
                            if not is_first_frame_excluded_object_evidence(item)
                        ),
                        *(
                            [cut_plan.get("visual_proof")]
                            if not is_first_frame_excluded_object_evidence(
                                cut_plan.get("visual_proof")
                            )
                            else []
                        ),
                    ],
                }
            )
            drawable_evidence_text = json.dumps(
                drawable_evidence,
                ensure_ascii=False,
                sort_keys=True,
            ).lower()
            artifact_named_by_drawable_evidence = any(
                token and token.lower() in drawable_evidence_text
                for token in (str(profile.get("artifact_asset_id") or "").strip(), str(profile.get("artifact_name") or "").strip())
            )
            if (
                artifact_named_by_drawable_evidence
                and not cut_uses_artifact
            ):
                cut_uses_artifact = True
                if profile["artifact_name"] not in must_show:
                    must_show.append(profile["artifact_name"])
                drawable_evidence = _cut_specific_drawable_evidence_for_scaffold(
                    {
                        "must_show": must_show,
                        "visual_evidence": [
                            *(cut_plan.get("visual_evidence", []) or []),
                            cut_plan.get("visual_proof"),
                        ],
                    }
                )
            supporting_character_ids = _supporting_character_ids_for_cut(
                profile,
                idx,
                cut_plan,
                scene_event,
                drawable_evidence,
            )
            supporting_object_ids = _supporting_object_ids_for_cut(
                profile,
                drawable_evidence,
                cut_plan=cut_plan,
                scene_event=scene_event,
            )
            drawable_evidence = [
                item
                for item in drawable_evidence
                if not is_first_frame_excluded_object_evidence(
                    item.get("must_be_drawn_as") if isinstance(item, dict) else item
                )
            ]
            supporting_object_ids = [
                object_id
                for object_id in supporting_object_ids
                if object_id not in first_frame_excluded_object_ids
            ]
            object_ids = [*supporting_object_ids, *([artifact_asset] if cut_uses_artifact else [])]
            primary_character_asset = _character_asset_for_subject(
                profile,
                scene_index=idx,
                obligation_id=obligation_id,
                subject=focal_character_name,
                first_frame_asset_overrides=first_frame_character_asset_overrides,
            )
            if not primary_character_asset:
                raise RuntimeError(
                    f"cut primary subject has no character reference binding: {focal_character_name}"
                )
            carried_character_ids = [
                asset_id
                for subject_name in [
                    *(cut_plan.get("carried_character_subject_names") or []),
                    *(cut_plan.get("visible_character_ids") or []),
                ]
                if (
                    asset_id := _character_asset_for_subject(
                        profile,
                        scene_index=idx,
                        obligation_id=obligation_id,
                        subject=str(subject_name),
                        first_frame_asset_overrides=first_frame_character_asset_overrides,
                    )
                )
            ]
            protagonist_variant_ids = {
                str(profile.get("protagonist_asset_id") or "").strip(),
            }
            protagonist_override = (
                first_frame_character_asset_overrides.get(
                    str(profile.get("protagonist_name") or "").strip()
                )
                or first_frame_character_asset_overrides.get("protagonist")
            )
            if protagonist_override and any(
                character_id in protagonist_variant_ids
                for character_id in [
                    *carried_character_ids,
                    *supporting_character_ids,
                ]
            ):
                supporting_character_ids = [
                    character_id
                    for character_id in supporting_character_ids
                    if character_id not in protagonist_variant_ids
                ]
                carried_character_ids = [
                    character_id
                    for character_id in carried_character_ids
                    if character_id not in protagonist_variant_ids
                ]
                if protagonist_override != primary_character_asset:
                    carried_character_ids.append(protagonist_override)
            supporting_character_ids = list(
                dict.fromkeys(
                    asset_id
                    for asset_id in [
                        *carried_character_ids,
                        *supporting_character_ids,
                    ]
                    if asset_id != primary_character_asset
                )
            )
            primary_character_ref = _character_reference_for_asset(
                profile, primary_character_asset
            )
            if not primary_character_ref:
                raise RuntimeError(
                    f"cut primary subject reference path is missing: {focal_character_name}"
                )
            character_ids = [primary_character_asset, *supporting_character_ids]
            supporting_character_refs = [
                ref
                for ref in (
                    _character_reference_for_asset(profile, asset_id)
                    for asset_id in supporting_character_ids
                )
                if ref
            ]
            supporting_object_refs = [
                ref for ref in (_supporting_object_reference(profile, asset_id) for asset_id in supporting_object_ids) if ref
            ]
            references = [primary_character_ref, *supporting_character_refs, location_ref, *supporting_object_refs, *([artifact_ref] if cut_uses_artifact else [])]
            clean_first_frame_fallback = (
                f"{first_frame_location_name}。{focal_character_name}が次の行為の直前で"
                "身体を止めている"
            )
            safe_cut_plan = deepcopy(provider_cut_plan)
            for field_name in (
                "target_beat",
                "visual_proof",
                "first_frame_brief",
                "static_first_frame_rule",
                "visible_action",
                "visible_reaction",
                "causal_proof",
                "foreground",
                "midground",
                "background",
            ):
                safe_cut_plan[field_name] = _sanitize_first_frame_prose(
                    provider_cut_plan.get(field_name, ""),
                    excluded_tokens=first_frame_excluded_tokens,
                )
            for field_name in (
                "visual_evidence",
                "must_show_extra",
                "carried_character_subject_names",
                "visible_character_ids",
            ):
                safe_cut_plan[field_name] = _sanitize_first_frame_prose(
                    provider_cut_plan.get(field_name, []),
                    excluded_tokens=first_frame_excluded_tokens,
                )
            safe_cut_plan["visible_character_state"] = _sanitize_first_frame_prose(
                provider_cut_plan.get("visible_character_state", {}),
                excluded_tokens=first_frame_excluded_tokens,
            )
            safe_cut_plan["target_beat"] = (
                str(safe_cut_plan.get("target_beat") or "").strip()
                or clean_first_frame_fallback
            )
            safe_cut_plan["visual_proof"] = (
                str(safe_cut_plan.get("visual_proof") or "").strip()
                or clean_first_frame_fallback
            )
            safe_cut_plan["first_frame_brief"] = (
                str(safe_cut_plan.get("first_frame_brief") or "").strip()
                or clean_first_frame_fallback
            )
            safe_cut_plan["static_first_frame_rule"] = (
                str(safe_cut_plan.get("static_first_frame_rule") or "").strip()
                or "次の行為の直前に止まった一つの静止状態だけを描く"
            )
            safe_cut_plan["foreground"] = (
                str(safe_cut_plan.get("foreground") or "").strip()
                or focal_character_name
            )
            safe_cut_plan["midground"] = (
                str(safe_cut_plan.get("midground") or "").strip()
                or focal_character_name
            )
            safe_cut_plan["background"] = (
                str(safe_cut_plan.get("background") or "").strip()
                or first_frame_location_name
            )
            beat = str(safe_cut_plan["target_beat"])
            visual_beat = str(safe_cut_plan["visual_proof"])
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
            cut_state_progression = _sanitize_first_frame_prose(
                dict(cut_state_progression_by_selector.get(selector, {})),
                excluded_tokens=first_frame_excluded_tokens,
            )
            is_terminal_scene = bool(scene_intent.get("terminal_resolution"))
            cut_blueprint = {
                "cut_role": "状況を前へ進める映画的断片",
                "cut_function": cut_plan["cut_function"],
                "duration_intent": f"{cut_target_seconds}秒で感情と情報を同時に渡す",
                "target_beat": beat,
                "scene_focus": scene_intent["dramatic_question"],
                "coverage_obligation_id": cut_plan["obligation_id"],
                "coverage_source": cut_plan["source"],
                "screen_question": cut_plan["screen_question"],
                "dramatic_job": cut_plan["dramatic_job"],
                "audience_knowledge_delta": cut_plan.get("audience_knowledge_delta", ""),
                "causal_proof": safe_cut_plan.get("causal_proof", ""),
                "visual_evidence": safe_cut_plan.get("visual_evidence", []),
                "required_roles": cut_plan.get("required_roles", []),
                "anti_redundancy_key": cut_plan.get("anti_redundancy_key", ""),
                "must_show": must_show,
                "must_avoid": ["画面内テキスト", "字幕", "ロゴ"],
                "done_when": [cut_plan["done_when"]],
                "visual_beat": visual_beat,
                "first_frame_brief": safe_cut_plan["first_frame_brief"],
                "static_first_frame_rule": safe_cut_plan.get("static_first_frame_rule", ""),
                "action_completion_state": str(cut_state_progression.get("action_completion_state") or ("pre_action" if cut_number == 1 else "early_action")),
                "motion_brief": safe_cut_plan["motion_brief"],
                "motion_end_state": safe_cut_plan["motion_end_state"],
                "first_frame_asset_policy": {
                    "character_asset_overrides": first_frame_character_asset_overrides,
                    "excluded_object_ids": sorted(first_frame_excluded_object_ids),
                },
                "allowed_new_reveal_elements": list(
                    cut_plan.get("allowed_new_reveal_elements") or []
                ),
                "narration_role": "絵を説明せず内面の方向だけを示す",
                "asset_dependency_hint": {"characters": character_ids, "objects": object_ids, "locations": [location_spec["asset_id"]]},
            }
            script_cut_base = {"cut_id": f"{cut_number:02d}", "selector": selector, "target_duration_seconds": cut_target_seconds, "estimated_duration_seconds": cut_target_seconds, "cut_blueprint": cut_blueprint}
            narration = str(cut_plan["narration"])
            actual_motion_end_state = str(cut_blueprint["motion_end_state"]).strip()
            continuity_destination_location = location_name
            motion_must_not_add = (
                ["新しい人物", "外部への導線", "次sceneのreveal", "画面内テキスト"]
                if is_terminal_scene
                else ["新しい人物", "次sceneのreveal", "画面内テキスト"]
            )
            use_next_cut_first_frame_as_last_frame = bool(
                cut_plan.get("use_next_cut_first_frame_as_last_frame")
            )
            next_cut_plan = (
                cut_plans[cut_number]
                if cut_number < len(cut_plans)
                else None
            )
            if use_next_cut_first_frame_as_last_frame:
                boundary = _validate_next_cut_last_frame_boundary(
                    selector=selector,
                    current_cut_plan=cut_plan,
                    next_cut_plan=next_cut_plan,
                    route_locations=location_sequence,
                )
                continuity_destination_location = boundary[
                    "destination_location"
                ]
                actual_motion_end_state = boundary["actual_end_state"]
            bound_last_frame = (
                f"assets/scenes/scene{scene_id}_cut{cut_number + 1:02d}.png"
                if use_next_cut_first_frame_as_last_frame
                else ""
            )
            cut_allowed_reveal_info_ids = list(
                dict.fromkeys(
                    str(item).strip()
                    for item in cut_plan.get("allowed_reveal_info_ids") or []
                    if str(item).strip()
                )
            )
            cut_forbidden_reveal_info_ids = [
                str(item).strip()
                for item in scene_intent.get("withheld_information", [])
                if str(item).strip()
                and str(item).strip() not in cut_allowed_reveal_info_ids
            ]
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
                "character_state": str(cut_state_progression.get("state_visible_in_this_cut") or ("まだ行為を完了していない" if scene_state_progression_plan["progression_mode"] != "sequential_state_progression" else cut_blueprint["first_frame_brief"])),
                "prop_state": "前cutから進んだ小道具・場所の状態が見える" if scene_state_progression_plan["progression_mode"] == "sequential_state_progression" else "必要な小道具や証拠は見えるが、結果を説明しすぎない",
                "spatial_state": first_frame_location_name,
                "emotional_state": "sceneの圧力を受けている",
                "gaze_or_attention": f"{safe_cut_plan['foreground']}へ向く",
                "pose": str(cut_state_progression.get("state_visible_in_this_cut") or cut_blueprint["first_frame_brief"]),
                "hand_position": "前cutから進んだ状態に合う手元" if scene_state_progression_plan["progression_mode"] == "sequential_state_progression" else "行為を始める位置で止まった手元",
                "foot_position": "前cutから進んだ位置関係が読める足元" if scene_state_progression_plan["progression_mode"] == "sequential_state_progression" else "次に動き出せる足元",
            }
            camera_motion = {
                "setup": "locked_off",
                "pressure": "slow_push",
                "turn": "slow_dolly_in",
                "payoff": "slow_pull_back",
            }.get(event_beat_function, "static_camera")
            environment_motion = str(
                cut_plan.get("environment_motion")
                or (
                    f"{location_name}の背景に見える空気中の微粒子と、"
                    "画面内の衣服の端だけがごくわずかに動く"
                )
            )
            motion_attention_target = str(
                cut_plan.get("motion_attention_target")
                or cut_plan["foreground"]
            ).strip()
            emotional_change = str(
                cut_plan.get("emotional_change")
                or (
                    f"{focal_character_name}の肩の緊張がわずかに変わり、"
                    f"視線が{motion_attention_target}へ定まる"
                )
            )
            motion_start_affordance = {
                "movable_subject": focal_character_name,
                "movement_vector": cut_plan["screen_direction"],
                "camera_start_reason": "静止画内の視線、光、導線から自然に動き出せる",
            }
            visible_behavior = _visible_behavior_from_cut(
                profile=profile,
                cut_plan=safe_cut_plan,
                cut_blueprint=cut_blueprint,
                location_name=location_name,
                object_ids=object_ids,
                focal_character_name=focal_character_name,
            )
            cut_character_emotion_transition = _cut_character_emotion_transition_for_scaffold(
                profile=profile,
                cut_blueprint=cut_blueprint,
                primary_event_beat=primary_event_beat,
                primary_event_beat_id=primary_event_beat_id,
                visible_behavior=visible_behavior,
                focal_character_id=primary_character_asset,
                supporting_character_ids=supporting_character_ids,
                cut_number=cut_number,
                cut_count=len(cut_plans),
            )
            cut_film_grammar_contract = _cut_film_grammar_contract_for_scaffold(
                selector=selector,
                profile=profile,
                location_name=location_name,
                cut_number=cut_number,
                cut_count=len(cut_plans),
                cut_plan=safe_cut_plan,
                cut_blueprint=cut_blueprint,
                primary_event_beat=primary_event_beat,
                primary_event_beat_id=primary_event_beat_id,
                source_event_beat_ids=source_event_beat_ids,
                object_ids=object_ids,
                visible_behavior=visible_behavior,
                focal_character_id=primary_character_asset,
                supporting_character_ids=supporting_character_ids,
            )
            mixed_affect_design = _mixed_affect_design_for_cut(
                cut_function=str(cut_blueprint["cut_function"]),
                cut_number=cut_number,
                cut_count=len(cut_plans),
                is_terminal_scene=is_terminal_scene,
                visual_beat=visual_beat,
                narration=narration,
            )
            source_non_replaceable_elements = [
                element
                for beat in event_beats_for_cut
                if isinstance(beat.get("story_grounding"), dict)
                for element in beat["story_grounding"].get("non_replaceable_elements", [])
                if isinstance(element, dict)
            ]
            cut_contract = {
                "schema_version": "3.0",
                "expressive_contract": _cut_expressive_contract_for_scaffold(
                    scene_id=scene_id,
                    scene_amplification=scene_intent["scene_value_amplification"],
                    cut_function=str(cut_blueprint["cut_function"]),
                    focal_character_name=focal_character_name,
                    visual_beat=visual_beat,
                    motion_brief=str(cut_blueprint["motion_brief"]),
                    motion_end_state=str(cut_blueprint["motion_end_state"]),
                ),
                "cut_state_progression": {
                    "policy_version": "cut_state_progression_v1",
                    "source_scene_progression_plan": "scene_state_progression_plan",
                    "progression_mode": scene_state_progression_plan["progression_mode"],
                    "cut_selector": selector,
                    "progression_position": str(cut_state_progression.get("progression_position") or cut_blueprint["cut_function"]),
                    "first_frame_temporal_role": str(cut_state_progression.get("first_frame_temporal_role") or "suspended_before_or_during_cut_event"),
                    "state_after_previous_cut": str(cut_state_progression.get("state_after_previous_cut") or ""),
                    "state_visible_in_first_frame": str(cut_state_progression.get("state_visible_in_this_cut") or cut_blueprint["first_frame_brief"]),
                    "visible_state_delta_from_previous_cut": str(cut_state_progression.get("visible_state_delta_from_previous_cut") or ""),
                    "action_completion_state": cut_blueprint["action_completion_state"],
                    "must_not_revert_to": str(cut_state_progression.get("must_not_revert_to") or ""),
                    "must_not_advance_beyond": str(cut_state_progression.get("must_not_advance_beyond") or ""),
                    "done_when": list(cut_state_progression.get("done_when") or []),
                },
                "source_event_contract": {
                    "primary_event_beat_id": primary_event_beat_id,
                    "source_event_beat_ids": source_event_beat_ids,
                    "event_beat_function": event_beat_function,
                    "event_time_position": event_time_position,
                    "source_event_summary": str(
                        primary_event_beat.get("what_happens")
                        or beat
                        or clean_first_frame_fallback
                    ),
                    "source_concrete_events": [
                        {
                            **event_beat["concrete_event"],
                            "primary_subject": cut_plan.get(
                                "primary_subject_name"
                            ),
                            "where": cut_plan.get("background") or location_name,
                            "what_happens": (
                                event_beat["concrete_event"].get(
                                    "what_happens", ""
                                )
                                or beat
                            ),
                            "object_or_trace": _sanitize_first_frame_prose(
                                event_beat["concrete_event"].get("object_or_trace", []),
                                excluded_tokens=first_frame_excluded_tokens,
                            ),
                            "visible_action": safe_cut_plan.get("visible_action"),
                            "visible_reaction": safe_cut_plan.get("visible_reaction"),
                            "required_visual_evidence": list(
                                safe_cut_plan.get("visual_evidence") or []
                            ),
                            "motion_brief": cut_plan.get("motion_brief"),
                            "motion_end_state": cut_plan.get(
                                "motion_end_state"
                            ),
                            "visible_character_state": dict(
                                safe_cut_plan.get("visible_character_state") or {}
                            ),
                            "allowed_new_reveal_elements": list(
                                cut_plan.get("allowed_new_reveal_elements") or []
                            ),
                            "allowed_reveal_info_ids": list(
                                cut_plan.get("allowed_reveal_info_ids") or []
                            ),
                            "use_next_cut_first_frame_as_last_frame": bool(
                                cut_plan.get(
                                    "use_next_cut_first_frame_as_last_frame"
                                )
                            ),
                        }
                        for event_beat in event_beats_for_cut
                        if isinstance(event_beat.get("concrete_event"), dict)
                    ],
                    "source_story_grounding": [
                        beat.get("story_grounding")
                        for beat in event_beats_for_cut
                        if isinstance(beat.get("story_grounding"), dict)
                    ],
                    "source_non_replaceable_elements": source_non_replaceable_elements,
                    "source_visible_action": str(
                        _sanitize_first_frame_prose(
                            primary_event_beat.get("visible_action")
                            or safe_cut_plan.get("visual_proof")
                            or "",
                            excluded_tokens=first_frame_excluded_tokens,
                        )
                        or visual_beat
                    ),
                    "canonical_source_visible_action": str(
                        primary_event_beat.get("visible_action")
                        or safe_cut_plan.get("visual_proof")
                        or visual_beat
                    ),
                    "source_visible_reaction": str(
                        _sanitize_first_frame_prose(
                            primary_event_beat.get("visible_reaction")
                            or safe_cut_plan.get("audience_knowledge_delta")
                            or "画面内の人物の視線が出来事へ向く",
                            excluded_tokens=first_frame_excluded_tokens,
                        )
                        or "画面内の人物の視線が出来事へ向く"
                    ),
                    "source_required_visual_evidence": (
                        _sanitize_first_frame_prose(
                            [
                                str(item)
                                for event_beat in event_beats_for_cut
                                for item in (
                                    event_beat.get("required_visual_evidence", [])
                                    if isinstance(
                                        event_beat.get("required_visual_evidence"), list
                                    )
                                    else []
                                )
                                if str(item).strip()
                            ],
                            excluded_tokens=first_frame_excluded_tokens,
                        )
                        or cut_blueprint["visual_evidence"]
                        or must_show
                    ),
                    "canonical_source_required_visual_evidence": [
                        str(item)
                        for event_beat in event_beats_for_cut
                        for item in (
                            event_beat.get("required_visual_evidence", [])
                            if isinstance(event_beat.get("required_visual_evidence"), list)
                            else []
                        )
                        if str(item).strip()
                    ],
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
                    "event_facts_to_preserve": _sanitize_first_frame_prose(
                        [
                            str(event_beat.get("what_happens") or "")
                            for event_beat in event_beats_for_cut
                            if str(event_beat.get("what_happens") or "").strip()
                        ],
                        excluded_tokens=first_frame_excluded_tokens,
                    ),
                    "canonical_event_facts_to_preserve": [
                        str(event_beat.get("what_happens") or "")
                        for event_beat in event_beats_for_cut
                        if str(event_beat.get("what_happens") or "").strip()
                    ],
                    "event_facts_not_to_invent": scene_event.get("forbidden_event_changes", []),
                    "allowed_reveal_info_ids": list(
                        dict.fromkeys(
                            [
                                *cut_blueprint["visual_evidence"],
                                *cut_allowed_reveal_info_ids,
                            ]
                        )
                    ),
                    "forbidden_reveal_info_ids": cut_forbidden_reveal_info_ids,
                    "must_not_change": scene_event.get("forbidden_event_changes", []),
                },
                "cut_character_emotion_transition": cut_character_emotion_transition,
                "cut_film_grammar_contract": cut_film_grammar_contract,
                "cut_role": "main",
                "cut_function": cut_blueprint["cut_function"],
                "coverage_obligation_id": cut_plan["obligation_id"],
                "coverage_source": cut_plan["source"],
                "duration_intent": "standard",
                "target_duration_seconds": cut_target_seconds,
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
                    "emotional_micro_shift": {
                        "from": str(primary_event_beat.get("emotional_pressure") or "sceneの圧力"),
                        "to": str(cut_plan.get("audience_knowledge_delta") or cut_blueprint["dramatic_job"]),
                    },
                    "mixed_affect_design": mixed_affect_design,
                    "reveal_constraints": {
                        "inherited_from_scene": scene_intent.get("reveal_constraints", []),
                        "allowed_reveals_in_this_cut": list(
                            dict.fromkeys(
                                [
                                    *cut_blueprint["visual_evidence"],
                                    *cut_allowed_reveal_info_ids,
                                ]
                            )
                        ),
                        "forbidden_until_later_cut": [],
                        "forbidden_until_later_scene": cut_forbidden_reveal_info_ids,
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
                    "subject_priority": {"primary": focal_character_name, "secondary": profile["artifact_name"] if cut_uses_artifact else first_frame_location_name, "background": first_frame_location_name},
                    "screen_geography": {"foreground": safe_cut_plan["foreground"], "midground": safe_cut_plan["midground"], "background": safe_cut_plan["background"], "screen_direction": cut_plan["screen_direction"]},
                },
                "continuity_contract": {
                    "location_ids": [location_spec["asset_id"]],
                    "character_ids": character_ids,
                    "object_ids": object_ids,
                    "start_state": {"character_state": visible_start_state["character_state"], "prop_state": visible_start_state["prop_state"], "spatial_state": first_frame_location_name, "time_state": "scene内の現在時点"},
                    "end_state": {"character_state": actual_motion_end_state, "prop_state": "次へ渡す証拠が画面に残る", "spatial_state": continuity_destination_location, "time_state": "cutの理解が完了した時点"},
                    "carry_forward_to_next_cut": list(
                        dict.fromkeys(
                            [
                                focal_character_name,
                                continuity_destination_location,
                                actual_motion_end_state,
                                *object_ids,
                            ]
                        )
                    ),
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
                        "binds_video_last_frame_to_next_first_frame": use_next_cut_first_frame_as_last_frame,
                    },
                },
                "first_frame_contract": {
                    "imageable": True,
                    "image_role": "video_first_frame_candidate",
                    "source_event_beat_id": primary_event_beat_id,
                    "event_time_position": event_time_position,
                    "event_fact_visible_in_still": cut_blueprint["visual_beat"],
                    "not_yet_happened_in_still": [
                        str(item)
                        for item in (
                            cut_state_progression.get("forbidden_future_event_beat_ids", [])
                            if scene_state_progression_plan["progression_mode"] == "sequential_state_progression"
                            else [
                                str(beat.get("beat_id") or "")
                                for beat in scene_event.get("event_sequence", [])
                                if isinstance(beat, dict) and str(beat.get("beat_id") or "") not in source_event_beat_ids
                            ]
                        )
                        if str(item).strip()
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
                        str(item)
                        for item in (
                            cut_state_progression.get("forbidden_future_event_beat_ids", [])
                            if scene_state_progression_plan["progression_mode"] == "sequential_state_progression"
                            else [
                                str(beat.get("beat_id") or "")
                                for beat in scene_event.get("event_sequence", [])
                                if isinstance(beat, dict) and str(beat.get("beat_id") or "") not in source_event_beat_ids and str(beat.get("beat_function") or "") in {"turn", "payoff"}
                            ]
                        )
                        if str(item).strip()
                    ],
                    "must_not_resolve_scene_turn_unless_primary_event_is_turn": event_beat_function != "turn",
                    "motion_brief": cut_blueprint["motion_brief"],
                    "start_from_visible_state": "first_frame_contract.visible_start_state",
                    "camera_motion": camera_motion,
                    "subject_motion": cut_blueprint["motion_brief"],
                    "environment_motion": environment_motion,
                    "emotional_change": emotional_change,
                    "end_state": cut_blueprint["motion_end_state"],
                    "end_frame_brief": cut_blueprint["motion_end_state"],
                    "allowed_new_reveal_elements": cut_blueprint[
                        "allowed_new_reveal_elements"
                    ],
                    "must_not_add": motion_must_not_add,
                },
                "narration_contract": {
                    "speakable_or_silent": True,
                    "source_event_beat_ids": source_event_beat_ids,
                    "allowed_info_ids": list(
                        dict.fromkeys(
                            [
                                *cut_blueprint["visual_evidence"],
                                *cut_allowed_reveal_info_ids,
                            ]
                        )
                    ),
                    "forbidden_info_ids": cut_forbidden_reveal_info_ids,
                    "must_not_advance_to_event_beat_ids": [
                        str(item)
                        for item in (
                            cut_state_progression.get("forbidden_future_event_beat_ids", [])
                            if scene_state_progression_plan["progression_mode"] == "sequential_state_progression"
                            else [
                                str(beat.get("beat_id") or "")
                                for beat in scene_event.get("event_sequence", [])
                                if isinstance(beat, dict) and str(beat.get("beat_id") or "") not in source_event_beat_ids
                            ]
                        )
                        if str(item).strip()
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
                    "expected_duration_seconds": cut_target_seconds,
                    "pacing": "standard",
                    "comprehension_moment": "visual_proof が画面で読める瞬間",
                    "cut_out_reason": "次cutへ渡す anchor が画面に残った瞬間",
                    "audio_visual_sync_point": "ナレーションは visual_proof の後を追い、画面説明にならない",
                    "duration_exception": {
                        **cut_duration_exception,
                    },
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
                    "p700_narration": {
                        "event_context_for_cut": "<cut_contract.event_context_for_cut>",
                        "narration_requirements": [
                            "説明ではなく感情の方向",
                            *(
                                mixed_affect_design.get("narration_support", [])
                                if mixed_affect_design.get("mode") != "none"
                                and isinstance(mixed_affect_design.get("narration_support"), list)
                                else []
                            ),
                        ],
                        "role": "emotion",
                        "must_not_caption_visible_content": True,
                    },
                    "p800_video": {"event_context_for_cut": "<cut_contract.event_context_for_cut>", "motion_requirements": [cut_blueprint["motion_brief"]], "start_state": "first_frame_contract.visible_start_state", "last_frame_or_end_state": cut_blueprint["motion_end_state"], "must_not_add": motion_must_not_add},
                    "carries_to_next_cut": list(
                        dict.fromkeys(
                            [
                                focal_character_name,
                                continuity_destination_location,
                                actual_motion_end_state,
                            ]
                        )
                    ),
                    "carries_to_next_scene": carries_to_next_scene,
                },
            }
            cut_contract["event_context_for_cut"] = _event_context_for_cut_contract(
                scene_event=scene_event,
                source_event_contract=cut_contract["source_event_contract"],
                reveal_constraints=scene_intent.get("reveal_constraints", []),
                cut_location=str(
                    safe_cut_plan.get("background") or first_frame_location_name
                ).strip(),
            )
            first_frame_visual_plan = _first_frame_visual_plan_for_scaffold(
                selector=selector,
                profile=profile,
                location_spec=location_spec,
                location_name=first_frame_location_name,
                cut_number=cut_number,
                cut_plan=safe_cut_plan,
                cut_blueprint=cut_blueprint,
                cut_contract=cut_contract,
                character_ids=character_ids,
                object_ids=object_ids,
                references=references,
                cut_uses_artifact=cut_uses_artifact,
                scene_time_of_day=time_of_day,
                drawable_evidence=drawable_evidence,
            )
            api_prompt_payload = _image_api_prompt_payload_for_scaffold(
                first_frame_visual_plan=first_frame_visual_plan,
                character_ids=character_ids,
                object_ids=object_ids,
                location_ids=[location_spec["asset_id"]],
                references=references,
                story_time=str(profile.get("story_time") or "").strip(),
                scene_time_of_day=time_of_day,
            )
            debug_prompt_source = {
                "first_frame_contract": cut_contract["first_frame_contract"],
                "first_frame_visual_plan": first_frame_visual_plan,
                "first_frame_visual_plan_source": [
                    "cut_contract.source_event_contract",
                    "cut_contract.first_frame_contract",
                    "cut_contract.cinematic_contract",
                ],
                "api_prompt_payload": {
                    "policy_version": api_prompt_payload["policy_version"],
                    "sha256": api_prompt_payload["sha256"],
                },
                "send_to_api": False,
            }
            shot_contract = api_prompt_payload.get("shot_design_contract") if isinstance(api_prompt_payload.get("shot_design_contract"), dict) else {}
            scene_shot_records.append(
                {
                    "selector": selector,
                    "shot_role": shot_contract.get("shot_role", ""),
                    "shot_scale": shot_contract.get("shot_scale", ""),
                    "a_roll_or_b_roll": shot_contract.get("a_roll_or_b_roll", ""),
                }
            )
            cuts.append({**script_cut_base, "cut_contract": cut_contract, "scene_contract": {"legacy_note": "旧reader向け alias。cut_contract が正本。", "target_beat": beat, "must_show": must_show, "must_avoid": ["英字看板", "署名クレジット", "企業ロゴ"], "done_when": [cut_plan["done_when"]]}})
            manifest_cuts.append(
                {
                    "cut_id": f"{cut_number:02d}",
                    "selector": selector,
                    "duration_seconds": cut_target_seconds,
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
                    "still_image_plan": {
                        "mode": "generate_still",
                        "generation_status": "missing",
                        "prompt_source": "image_generation.api_prompt_payload.prompt",
                    },
                    "image_generation": {"tool": "codex_builtin_image", "character_ids": character_ids, "object_ids": object_ids, "location_ids": [location_spec["asset_id"]], "asset_id": "", "asset_type": "scene_still", "execution_lane": "standard", "reference_count": len(references), "references": references, "first_frame_visual_plan": first_frame_visual_plan, "api_prompt_payload": api_prompt_payload, "debug_prompt_source": debug_prompt_source, "output": f"assets/scenes/{selector}.png", "aspect_ratio": "16:9", "image_size": "1K"},
                    "video_generation": {
                        "tool": "kling_3_0_omni",
                        "duration_seconds": cut_target_seconds,
                        "duration_exception": deepcopy(cut_duration_exception),
                        "first_frame": f"assets/scenes/{selector}.png",
                        **(
                            {"last_frame": bound_last_frame}
                            if bound_last_frame
                            else {}
                        ),
                        "motion_prompt": cut_plan["motion_brief"],
                        "output": f"assets/scenes/{selector}.mp4",
                    },
                    "audio": {"narration": {"contract_ref": "cut_contract.narration_contract", "text": narration, "tts_text": narration, "tool": "elevenlabs", "output": f"assets/audio/{selector}.mp3", "applied_request_ids": []}},
                    "implementation_trace": {"status": "verified", "source_request_ids": []},
                }
            )
        scene_shot_mix_plan = {
            "policy_version": "scene_shot_mix_v1",
            "source": "image_generation.api_prompt_payload.shot_design_contract",
            "shots": scene_shot_records,
            "gate_requirements": [
                "scene_shot_mix_plan_exists",
                "scene_shot_mix_not_all_medium_wide",
                "no_two_adjacent_cuts_same_shot_role_and_scale",
            ],
        }
        object_cut_selectors = [
            str(cut.get("selector") or "").strip()
            for cut in manifest_cuts
            if isinstance(cut, dict)
            and any(
                str(value).strip()
                for value in (
                    ((cut.get("cut_contract") or {}).get("asset_dependency") or {}).get(
                        "object_ids_required"
                    )
                    or []
                )
            )
            and str(cut.get("selector") or "").strip()
        ]
        required_coverage = scene_film_coverage_plan["shot_mix"]["required_coverage"]
        if object_cut_selectors and not required_coverage.get("insert"):
            shot_role_by_selector = {
                str(record.get("selector") or "").strip(): str(record.get("shot_role") or "").strip()
                for record in scene_shot_records
                if isinstance(record, dict)
            }
            preferred = next(
                (
                    selector
                    for selector in object_cut_selectors
                    if shot_role_by_selector.get(selector) in {"object_proof", "insert"}
                ),
                object_cut_selectors[0],
            )
            required_coverage["insert"] = [preferred]
        scene_film_coverage_plan["shot_mix"]["actual_shots"] = scene_shot_records
        scene_for_cut_packets = {
            "scene_id": scene_id,
            "scene_intent": scene_intent,
            "scene_event": scene_event,
            "scene_character_state_timeline": scene_character_state_timeline,
            "scene_film_coverage_plan": scene_film_coverage_plan,
            "scene_state_progression_plan": scene_state_progression_plan,
            "scene_cut_coverage_plan": scene_cut_coverage_plan,
            "scene_shot_mix_plan": scene_shot_mix_plan,
            "cuts": cuts,
        }
        for cut_index, cut in enumerate(cuts):
            materialize_cut_context_packet(
                scene_for_cut_packets,
                cut,
                previous_cut=cuts[cut_index - 1] if cut_index > 0 else None,
                next_cut=cuts[cut_index + 1] if cut_index + 1 < len(cuts) else None,
            )
        manifest_scene_for_cut_packets = {**scene_for_cut_packets, "cuts": manifest_cuts}
        for cut_index, cut in enumerate(manifest_cuts):
            materialize_cut_context_packet(
                manifest_scene_for_cut_packets,
                cut,
                previous_cut=manifest_cuts[cut_index - 1] if cut_index > 0 else None,
                next_cut=manifest_cuts[cut_index + 1] if cut_index + 1 < len(manifest_cuts) else None,
            )
        script_scenes.append({"scene_id": scene_id, "canonical_scene_index": _canonical_scene_index(profile, idx), "phase": _phase_for_scene(profile, idx), "time_of_day": time_of_day, "time_of_day_visual_basis": time_of_day_visual_basis, "location_mode": "sequence" if len(location_sequence) > 1 else "single", "location_sequence": location_sequence, "location_segments": location_segments, "importance": "medium", "target_duration_seconds": scene_target_seconds, "estimated_duration_seconds": scene_duration_seconds, "research_refs": _downstream_scene_research_refs(idx, _scene_source_events(profile, idx), profile), "handoff_to_next_scene": scene_intent["handoff_to_next_scene"], "terminal_resolution": scene_intent["terminal_resolution"], "scene_generation": scene_generation, "scene_intent": scene_intent, "scene_event": scene_event, "scene_acceptance_draft": deepcopy(acceptance_draft_by_scene_id[scene_id]), "scene_character_state_timeline": scene_character_state_timeline, "scene_film_coverage_plan": scene_film_coverage_plan, "scene_state_progression_plan": scene_state_progression_plan, "semantic_contract": scene_semantic_contract, "scene_cut_coverage_plan": scene_cut_coverage_plan, "scene_shot_mix_plan": scene_shot_mix_plan, "cuts": cuts})
        manifest_scene_generation = deepcopy(scene_generation)
        prompt_packet = manifest_scene_generation.pop(
            "scene_acceptance_prompt_packet",
            None,
        )
        if isinstance(prompt_packet, dict):
            manifest_scene_generation["scene_acceptance_prompt_binding"] = {
                "schema_version": prompt_packet.get("schema_version"),
                "generation_id": prompt_packet.get("generation_id"),
                "contract_digest": prompt_packet.get("contract_digest"),
                "criterion_registry_version": prompt_packet.get(
                    "criterion_registry_version"
                ),
                "criterion_registry_sha256": prompt_packet.get(
                    "criterion_registry_sha256"
                ),
                "scene_slice_digest": acceptance_draft_by_scene_id[scene_id].get(
                    "scene_slice_digest"
                ),
            }
        manifest_scenes.append({"scene_id": scene_id, "canonical_scene_index": _canonical_scene_index(profile, idx), "time_of_day": time_of_day, "time_of_day_visual_basis": time_of_day_visual_basis, "location_mode": "sequence" if len(location_sequence) > 1 else "single", "location_sequence": location_sequence, "location_segments": location_segments, "importance": "medium", "target_duration_seconds": scene_target_seconds, "estimated_duration_seconds": scene_duration_seconds, "research_refs": _downstream_scene_research_refs(idx, _scene_source_events(profile, idx), profile), "scene_generation": manifest_scene_generation, "scene_intent": scene_intent, "scene_event": scene_event, "scene_acceptance_binding": {"generation_id": scene_set_authoring_contract["generation_id"], "contract_digest": scene_set_authoring_contract["contract_digest"], "scene_slice_digest": acceptance_draft_by_scene_id[scene_id]["scene_slice_digest"], "preflight_digest": authoring_preflight["preflight_digest"]}, "scene_character_state_timeline": scene_character_state_timeline, "scene_film_coverage_plan": scene_film_coverage_plan, "scene_state_progression_plan": scene_state_progression_plan, "semantic_contract": scene_semantic_contract, "scene_cut_coverage_plan": scene_cut_coverage_plan, "scene_shot_mix_plan": scene_shot_mix_plan, "handoff_to_next_scene": scene_intent["handoff_to_next_scene"], "terminal_resolution": scene_intent["terminal_resolution"], "cuts": manifest_cuts})
        scene_event_outputs.append(
            {
                "scene_id": scene_id,
                "scene_index": idx,
                "title": title,
                "time_of_day": time_of_day,
                "time_of_day_visual_basis": time_of_day_visual_basis,
                "location_sequence": location_sequence,
                "location_segments": location_segments,
                "scene_generation": scene_generation,
                "scene_event": scene_event,
                "scene_character_state_timeline": scene_character_state_timeline,
                "scene_film_coverage_plan": scene_film_coverage_plan,
                "story_event_obligations": scene_intent.get("story_event_obligations", []),
                "scene_cut_coverage_plan": scene_cut_coverage_plan,
                "cut_contracts": [
                    {
                        "selector": cut.get("selector"),
                        "cut_id": cut.get("cut_id"),
                        "source_event_contract": (cut.get("cut_contract") or {}).get("source_event_contract"),
                        "cut_character_emotion_transition": (cut.get("cut_contract") or {}).get("cut_character_emotion_transition"),
                        "cut_film_grammar_contract": (cut.get("cut_contract") or {}).get("cut_film_grammar_contract"),
                        "event_context_for_cut": (cut.get("cut_contract") or {}).get("event_context_for_cut"),
                        "cut_context_packet": (cut.get("cut_contract") or {}).get("cut_context_packet"),
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
    canonical_event_coverage_matrix = _canonical_event_coverage_matrix_from_contract(
        scene_set_authoring_contract,
        profile,
    )
    scene_generation_policy = _scene_generation_policy(profile)
    script = {
        "schema_version": "scene_event_v1",
        "script_metadata": {
            "topic": topic,
            "target_duration": int(duration_plan["target_seconds"]),
            "target_duration_seconds": int(duration_plan["target_seconds"]),
            "minimum_narration_seconds": int(duration_plan["minimum_narration_seconds"]),
            "duration_plan": duration_plan,
            "created_at": now,
            "run_variant": run_variant,
            "scene_acceptance_contract": "required_v1",
        },
        "scene_generation": scene_generation_policy,
        "scene_set_authoring_contract": scene_set_authoring_contract,
        "authoring_preflight": authoring_preflight,
        "canonical_event_coverage_matrix": canonical_event_coverage_matrix,
        "evaluation_contract": {
            "target_arc": "opening,development,ordeal,transformation,ending",
            "must_cover": [
                profile["protagonist_name"],
                profile["artifact_name"],
                "時間制限",
                profile["motifs"][0],
            ],
            "must_avoid": [
                "未承認の結末改変",
                "原典筋にない身元証明の差し替え",
            ],
            "reveal_constraints": [],
        },
        "human_change_requests": [],
        "scenes": script_scenes,
    }
    script["script_metadata"]["adaptation_value_contract"] = ADAPTATION_VALUE_MARKER
    script["script_metadata"]["time"] = str(profile.get("story_time") or "").strip()
    script["script_metadata"]["scene_time_of_day_contract"] = SCENE_TIME_OF_DAY_CONTRACT
    script["script_metadata"]["scene_time_of_day_visual_basis_contract"] = SCENE_TIME_OF_DAY_VISUAL_BASIS_CONTRACT
    character_bible = [
        {
            "character_id": protagonist_asset,
            "reference_images": [protagonist_ref],
            "review_aliases": [profile["protagonist_name"], profile["topic_label"]],
            "fixed_prompts": [f"{profile['protagonist_name']}、自然な実写肌、同じ顔と髪型を維持"],
            "cinematic": {
                "role": f"{profile['protagonist_name']}本人の基準状態の一貫性",
                "visual_subject": profile.get("protagonist_asset_subject") or f"{profile['protagonist_name']}の基準状態の全身参照。自然な映画俳優の顔立ち。衣装は下記の役割、身分、状態に従う",
            },
            "subject_contract": {"identity_scope": "individual", "subject_count": 1, "member_ids": []},
            "appearance_contract": _protagonist_appearance_contract(profile),
            "reuse_contract": {"mode": "neutral_anchor"},
        }
    ]
    for spec in _supporting_character_asset_specs(profile):
        appearance_continuity = (
            deepcopy(spec.get("appearance_continuity"))
            if isinstance(spec.get("appearance_continuity"), dict)
            else {}
        )
        identity_name = str(
            spec.get("identity_name") or spec.get("name") or ""
        ).strip()
        appearance_prompt = ""
        costume_state = str(
            appearance_continuity.get("costume_state") or ""
        ).strip()
        forbidden_costume_states = [
            str(value).strip()
            for value in appearance_continuity.get(
                "forbidden_costume_states", []
            )
            if str(value).strip()
        ]
        if costume_state:
            appearance_prompt = (
                f"{identity_name}の衣装は{costume_state}で固定する。"
                + (
                    "、".join(forbidden_costume_states) + "には変えない。"
                    if forbidden_costume_states
                    else ""
                )
            )
        character_bible.append(
            {
                "character_id": spec["character_id"],
                "reference_images": spec["reference_images"],
                "review_aliases": list(
                    dict.fromkeys(
                        value
                        for value in (identity_name, str(spec["name"]).strip())
                        if value
                    )
                ),
                "fixed_prompts": [
                    value
                    for value in (spec["visual_subject"], appearance_prompt)
                    if value
                ],
                "cinematic": {"role": spec["story_purpose"], "visual_subject": spec["visual_subject"]},
                "subject_contract": deepcopy(spec.get("subject_contract") or {}),
                "appearance_contract": deepcopy(spec.get("appearance_contract") or {}),
                "reuse_contract": deepcopy(spec.get("reuse_contract") or {"mode": "neutral_anchor"}),
                **(
                    {
                        "appearance_continuity": appearance_continuity
                    }
                    if appearance_continuity
                    else {}
                ),
            }
        )
    object_bible = [
        {
            "object_id": artifact_asset,
            "kind": "artifact",
            "reference_images": [artifact_ref],
            "review_aliases": [profile["artifact_name"]],
            "fixed_prompts": [profile["artifact_fixed_prompt"]],
            "cinematic": {"role": profile["artifact_role"], "visual_takeaways": ["脆さと証拠性"], "spectacle_details": ["光を反射して手がかりになる"]},
            "reuse_contract": {"mode": "neutral_anchor"},
        }
    ]
    for spec in _supporting_object_asset_specs(profile):
        object_bible.append(
            {
                "object_id": spec["object_id"],
                "kind": "setpiece",
                "reference_images": spec["reference_images"],
                "review_aliases": [spec["name"]],
                "fixed_prompts": [spec["visual_subject"]],
                "cinematic": {"role": spec["story_purpose"], "visual_takeaways": [spec["name"]], "visual_subject": spec["visual_subject"]},
                "reuse_contract": deepcopy(spec.get("reuse_contract") or {"mode": "neutral_anchor"}),
            }
        )
    derived_semantic_minimum_cut_count = sum(
        int(scene["scene_cut_coverage_plan"]["min_cut_count"]["selected"])
        for scene in manifest_scenes
    )
    manifest = {"schema_version": "scene_event_v1", "manifest_phase": "production", "video_metadata": {"topic": topic, "source_story": str(run_dir / "story.md"), "created_at": now, "run_variant": run_variant, "experience": "cinematic_story", "aspect_ratio": "16:9", "resolution": "1280x720", "frame_rate": 24, "target_duration_seconds": int(duration_plan["target_seconds"]), "minimum_duration_seconds": int(duration_plan["minimum_effective_seconds"]), "minimum_scene_count": int(duration_plan["minimum_scene_count"]), "minimum_cut_count": derived_semantic_minimum_cut_count, "minimum_narration_seconds": int(duration_plan["minimum_narration_seconds"]), "duration_plan": duration_plan, "duration_seconds": total_duration_seconds}, "scene_generation": scene_generation_policy, "canonical_event_coverage_matrix": canonical_event_coverage_matrix, "assets": {"character_bible": character_bible, "object_bible": object_bible, "location_bible": [{"location_id": spec["asset_id"], "reference_images": [spec["output"]], "review_aliases": [spec["name"]], "fixed_prompts": [str((spec.get("visual_spec") or {}).get("subject") or f"{spec['name']}、実写映画の場所参照、空間構造と固定素材を維持")], "cinematic": {"role": spec["story_purpose"], "visual_subject": str((spec.get("visual_spec") or {}).get("subject") or "")}, "reuse_contract": deepcopy(spec.get("reuse_contract") or {"mode": "neutral_anchor"})} for spec in _location_asset_specs(profile)], "style_guide": {"visual_style": "実写、シネマティック、プラクティカルエフェクト。画面内テキストなし。", "forbidden": ["アニメ調", "漫画調", "イラスト調", "画面内テキスト", "字幕", "ウォーターマーク", "ロゴ"], "reference_images": []}}, "human_change_requests": [], "scenes": manifest_scenes}
    manifest["scene_acceptance_contract"] = {
        "schema_version": SCENE_ACCEPTANCE_CONTRACT_VERSION,
        "canonical_script_path": "script.md",
        "generation_id": scene_set_authoring_contract["generation_id"],
        "contract_digest": scene_set_authoring_contract["contract_digest"],
        "criterion_registry_sha256": scene_set_authoring_contract[
            "criterion_registry_sha256"
        ],
        "preflight_status": authoring_preflight["status"],
        "preflight_digest": authoring_preflight["preflight_digest"],
        "scene_slice_digests": {
            str(draft["scene_id"]): draft["scene_slice_digest"]
            for draft in scene_acceptance_drafts
        },
    }
    manifest["video_metadata"]["adaptation_value_contract"] = ADAPTATION_VALUE_MARKER
    manifest["video_metadata"]["time"] = str(profile.get("story_time") or "").strip()
    _bind_experience_metadata(
        manifest,
        experience=experience,
        source_run=source_run,
    )
    if experience == "world_walk":
        _apply_world_walk_generation_contract(
            script=script,
            manifest=manifest,
            source_references=list(source_references or []),
        )
    manifest["video_metadata"]["scene_time_of_day_contract"] = SCENE_TIME_OF_DAY_CONTRACT
    manifest["video_metadata"]["scene_time_of_day_visual_basis_contract"] = SCENE_TIME_OF_DAY_VISUAL_BASIS_CONTRACT
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
    _write_scene_design_json(
        run_dir,
        SCENE_GENERATION_PROMPTS_FILENAME,
        {
            "schema_version": "scene_generation_prompt_log_v1",
            "created_at": now,
            "topic": topic,
            "source": str(run_dir / "story.md"),
            "scene_count": len(scene_generation_prompts),
            "scenes": scene_generation_prompts,
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
            "scene_generation_prompts": len(scene_generation_prompts),
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
        reference_inputs = list(generation_plan.get("reference_inputs") or [])
        execution_lane = str(
            generation_plan.get("execution_lane")
            or ("standard" if reference_inputs else "bootstrap_builtin")
        ).strip()
        bootstrap_allowed_raw = generation_plan.get("bootstrap_allowed")
        bootstrap_allowed = (
            bootstrap_allowed_raw
            if isinstance(bootstrap_allowed_raw, bool)
            else not reference_inputs
        )
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
                            "reference_inputs": reference_inputs,
                        },
                        "image_generation": {
                            "tool": "codex_builtin_image",
                            "execution_lane": execution_lane,
                            "bootstrap_allowed": bootstrap_allowed,
                            "bootstrap_reason": (
                                "frontend_create_asset_stage"
                                if bootstrap_allowed
                                else ""
                            ),
                            "prompt": _prompt_for_asset(entry, profile),
                            "output": output,
                            "references": reference_inputs,
                        },
                    }
                ],
            }
        )
        manifest_items.append({"asset_id": asset_id, "selector": asset_id, "output": output, "asset_type": entry["asset_type"], "status": "requested"})
    asset_stage_manifest = {
        "video_metadata": {
            "topic": profile["topic_label"],
            "time": str(profile.get("story_time") or "").strip(),
            "experience": "asset_stage",
        },
        "scenes": asset_stage_scenes,
    }
    _write_run_text_nofollow(
        run_dir,
        run_dir / "asset_stage_manifest.md",
        _md_yaml("Asset Stage Manifest", asset_stage_manifest),
    )
    _write_run_text_nofollow(
        run_dir,
        run_dir / "asset_generation_manifest.md",
        _md_yaml(
            "Asset Generation Manifest",
            {"asset_generation_manifest": {"items": manifest_items}},
        ),
    )
    _run_materialization_subprocess(
        run_dir,
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate-assets-from-manifest.py"),
            "--manifest",
            str(run_dir / "asset_stage_manifest.md"),
            "--materialize-request-files-only",
            "--skip-videos",
            "--skip-audio",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _materialize_standard_request_files(run_dir: Path) -> None:
    _run_materialization_subprocess(
        run_dir,
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate-assets-from-manifest.py"),
            "--manifest",
            str(run_dir / "video_manifest.md"),
            "--materialize-request-files-only",
            "--enable-last-frame",
            "--skip-audio",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _require_fresh_p400_readiness(run_dir: Path) -> None:
    stage_result, updates = check_manifest_single(run_dir, "standard", "immersive")
    if updates:
        append_state_snapshot(run_dir / "state.txt", updates)
    checks = [
        check
        for check in stage_result.get("checks", [])
        if isinstance(check, dict)
    ]
    failed = [
        str(check.get("id") or check.get("message") or "failed check")
        for check in checks
        if check.get("passed") is False
    ]
    if not bool(stage_result.get("passed")) or failed:
        detail = ", ".join(failed[:8]) or "manifest structural validation failed"
        raise RuntimeError(f"p400 manifest structure is invalid: {detail}")


def _write_orchestration(
    run_dir: Path,
    stop_target: str,
    now: str,
) -> dict[str, str]:
    buckets = ("p100", "p200", "p300", "p400", "p500", "p600")
    bucket_slots = {
        "p100": ("p110", "p120"),
        "p200": ("p210", "p220"),
        "p300": ("p310", "p330"),
        "p400": ("p410", "p420", "p440", "p450"),
        "p500": ("p510", "p520", "p530", "p550", "p560", "p570"),
        "p600": ("p610", "p620", "p650", "p660", "p670", "p680") if stop_target == "p680" else ("p610", "p620", "p650"),
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
    progress = ["| timestamp | bucket | supervisor | event | stop_slot | result | note |", "|---|---|---|---|---|---|---|"]
    state_updates: dict[str, str] = {}
    for bucket in buckets:
        bucket_pending = bucket in {"p500", "p600"}
        result_rel = f"logs/orchestration/{bucket}.supervisor_result.json"
        progress.append(f"| {now} | {bucket} | {bucket} P-Bucket Supervisor | invoked | {stop_target} | - | frontend handoff path |")
        progress.append(
            f"| {now} | {bucket} | {bucket} P-Bucket Supervisor | returned | {stop_target} | {result_rel} | "
            + ("media workflow pending |" if bucket_pending else "bucket complete |")
        )
        key = f"orchestration.{bucket}.supervisor"
        state_updates[f"{key}.call_status"] = "returned"
        state_updates[f"{key}.status"] = "pending" if bucket_pending else "done"
        state_updates[f"{key}.finished_at"] = now
        status_key = f"slot.{bucket_slots[bucket][-1]}.status"
        if bucket_pending:
            expected_status = "pending"
        else:
            expected_status = "awaiting_approval" if bucket_slots[bucket][-1] in AWAITING_ALLOWED else "done"
        if bucket == "p500":
            completed_slots = ["p520", "p530"]
        elif bucket == "p600":
            completed_slots = ["p620"]
        else:
            completed_slots = list(bucket_slots[bucket])
        result = {
            "bucket": bucket,
            "status": "pending" if bucket_pending else "done",
            "stop_slot": stop_target,
            "completed_slots": completed_slots,
            "required_artifacts": [{"path": path, "exists": True} for path in bucket_artifacts[bucket]],
            "state_keys": {status_key: expected_status},
            "next_bucket": None if bucket == "p600" else "next",
        }
        _write_run_text_nofollow(
            run_dir,
            orch / f"{bucket}.supervisor_result.json",
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        )
    _write_run_text_nofollow(
        run_dir,
        orch / "l2_supervisor_progress.md",
        "\n".join(progress) + "\n",
    )
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
        subject = str((entry.get("cinematic") or {}).get("visual_subject") or f"{profile['protagonist_name']}の全身、自然な映画俳優の顔立ち。衣装は下記の役割、身分、状態に従う")
        fixed_prompts = [str(item) for item in entry.get("fixed_prompts") or [] if str(item).strip()]
        reference_inputs = _asset_reference_inputs_for_plan(profile, asset_id)
        execution_lane = "standard" if reference_inputs else "bootstrap_builtin"
        coverage["characters"].append(asset_id)
        inventory_items.append({"item_id": asset_id, "category": "characters", "source_script_selectors": selectors, "story_purpose": role, "reusable_reason": "登場cutで人物同一性を保つ", "recommended_asset_type": "character_reference"})
        plan_entries.append({"asset_id": asset_id, "asset_type": "character_reference", "source_script_selectors": selectors, "story_purpose": role, "fixed_prompts": fixed_prompts, "generation_prompt": str(entry.get("generation_prompt") or "").strip(), "subject_contract": deepcopy(entry.get("subject_contract") or {"identity_scope": "individual", "subject_count": 1, "member_ids": []}), "appearance_contract": deepcopy(entry.get("appearance_contract") or {}), "reuse_contract": deepcopy(entry.get("reuse_contract") or {"mode": "neutral_anchor"}), "visual_spec": {"subject": subject, "style": "photorealistic live-action cinematic", "forbidden": ["文字", "ロゴ", "アニメ"]}, "generation_plan": {"execution_lane": execution_lane, "bootstrap_allowed": not reference_inputs, "required_views": ["front", "side", "back"], "reference_inputs": reference_inputs, "output": output}})

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
        fixed_prompts = [str(item) for item in entry.get("fixed_prompts") or [] if str(item).strip()]
        inventory_items.append({"item_id": asset_id, "category": "story_specific_items", "source_script_selectors": selectors, "story_purpose": role, "reusable_reason": "証が必要なcutで小道具の形状を保つ", "recommended_asset_type": "object_reference"})
        plan_entries.append({"asset_id": asset_id, "asset_type": "object_reference", "source_script_selectors": selectors, "story_purpose": role, "fixed_prompts": fixed_prompts, "generation_prompt": str(entry.get("generation_prompt") or "").strip(), "reuse_contract": deepcopy(entry.get("reuse_contract") or {"mode": "neutral_anchor"}), "visual_spec": {"subject": subject, "style": "photorealistic live-action product still", "forbidden": ["文字", "ロゴ", "玩具風"]}, "generation_plan": {"execution_lane": "bootstrap_builtin", "bootstrap_allowed": True, "required_views": ["front"], "reference_inputs": [], "output": output}})

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
        fixed_prompts = [str(item) for item in entry.get("fixed_prompts") or [] if str(item).strip()]
        coverage["locations"].append(asset_id)
        inventory_items.append({"item_id": asset_id, "category": "locations", "source_script_selectors": selectors, "story_purpose": f"{location_name}の空間・光・質感を固定する", "reusable_reason": "同じ場所のcutで背景と空気感を保つ", "recommended_asset_type": "location_reference"})
        plan_entries.append({"asset_id": asset_id, "asset_type": "location_reference", "source_script_selectors": selectors, "story_purpose": f"{location_name}の空間構造と固定素材を保つ", "fixed_prompts": fixed_prompts, "generation_prompt": str(entry.get("generation_prompt") or "").strip(), "reuse_contract": deepcopy(entry.get("reuse_contract") or {"mode": "neutral_anchor"}), "visual_spec": {"subject": location_subject, "style": "photorealistic live-action cinematic location still", "forbidden": ["文字", "ロゴ", "人物主役", "アニメ"]}, "generation_plan": {"execution_lane": "bootstrap_builtin", "bootstrap_allowed": True, "required_views": ["wide"], "reference_inputs": [], "output": output}})

    if not plan_entries:
        raise RuntimeError("manifest did not yield any reusable asset plan entries")
    inventory = {"asset_inventory": {"source_artifacts": ["story.md", "script.md", "video_manifest.md"], "coverage_scope": coverage, "items": inventory_items}}
    plan = {"assets": plan_entries}
    return inventory, plan


def materialize_run(
    topic: str,
    source: str,
    run_dir: Path,
    stop_target: str,
    target_duration_seconds: int = 300,
    review_mode: str | None = None,
    story_author_runner: Callable[..., None] | None = None,
    experience: str = "cinematic_story",
    source_run: Path | None = None,
    world_walk_source_identity: PathIdentity | None = None,
    world_walk_destination_identity: PathIdentity | None = None,
    world_walk_source_reference_lease: (
        WorldWalkSourceReferenceLease | None
    ) = None,
    world_walk_source_story_sha256: str | None = None,
) -> None:
    # Keep accepting the legacy switch while the server/client migration
    # completes.  Creation is deliberately single-path and never records or
    # branches on this value.
    del review_mode
    target_duration_seconds = normalize_target_duration(
        target_duration_seconds
    )
    source = _exact_materialization_source(
        source=source,
        experience=experience,
        source_run=source_run,
        source_root_identity=world_walk_source_identity,
        expected_source_sha256=world_walk_source_story_sha256,
    )
    if experience == "world_walk" and source_run is not None:
        if world_walk_source_identity is None:
            world_walk_source_identity = directory_identity_nofollow(
                source_run
            )
        if world_walk_source_story_sha256 is None:
            world_walk_source_story_sha256 = hashlib.sha256(
                source.encode("utf-8")
            ).hexdigest()
        if world_walk_source_reference_lease is None:
            world_walk_source_reference_lease = (
                _freeze_world_walk_source_reference_inventory(
                    source_run,
                    source_root_identity=world_walk_source_identity,
                )
            )
    run_dir.mkdir(parents=True, exist_ok=True)
    materialization_root_identity = (
        world_walk_destination_identity
        if world_walk_destination_identity is not None
        else directory_identity_nofollow(run_dir)
    )
    _recover_interrupted_scene_pair_publish(
        run_dir,
        root_identity=materialization_root_identity,
    )
    for reserved_path, initial_bytes in (
        ("state.txt", b""),
        ("run_status.json", b"{}\n"),
        ("p000_index.md", b""),
    ):
        write_regular_file_exclusive_nofollow(
            destination_root=run_dir,
            destination_relative=reserved_path,
            data=initial_bytes,
            expected_destination_root_identity=(
                materialization_root_identity
            ),
        )
    source_references = (
        _materialize_world_walk_source_references(
            source_run,
            run_dir,
            source_root_identity=world_walk_source_identity,
            destination_root_identity=materialization_root_identity,
            source_reference_lease=world_walk_source_reference_lease,
            source_story_sha256=world_walk_source_story_sha256,
        )
        if experience == "world_walk" and source_run is not None
        else []
    )
    _write_create_input_contract(
        run_dir=run_dir,
        topic=topic,
        source=source,
        experience=experience,
        source_run=source_run,
        target_duration_seconds=target_duration_seconds,
        expected_run_identity=materialization_root_identity,
    )
    if (
        experience == "world_walk"
        and source_run is not None
        and world_walk_source_reference_lease is not None
        and world_walk_source_story_sha256 is not None
    ):
        lease_payload = {
            "schema_version": "world_walk_source_reference_lease_v1",
            "source_run": str(source_run),
            "source_root_identity": {
                "device": world_walk_source_identity[0],
                "inode": world_walk_source_identity[1],
            },
            "source_story_sha256": world_walk_source_story_sha256,
            "reference_inventory": [
                {
                    "path": relative_path,
                    "sha256": sha256,
                }
                for relative_path, sha256
                in world_walk_source_reference_lease
            ],
        }
        lease_payload["lease_sha256"] = hashlib.sha256(
            json.dumps(
                lease_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        _write_run_text_nofollow(
            run_dir,
            (
                run_dir
                / "logs"
                / "orchestration"
                / "world_walk_source_reference_lease.json"
            ),
            json.dumps(
                lease_payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    profile = _duration_aware_profile(
        _story_profile(topic, source, variant_seed=run_dir.name),
        target_duration_seconds=target_duration_seconds,
    )
    duration_plan = dict(profile["duration_plan"])
    for rel in ("assets/characters", "assets/objects", "assets/locations", "assets/scenes", "assets/audio", "logs/grounding"):
        ensure_directory_relative_nofollow(
            run_dir,
            rel,
            expected_root_identity=materialization_root_identity,
        )
    now = _now_iso()
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "timestamp": now,
            "topic": topic,
            "status": "AUTHORING",
            "runtime.stage": "research_authoring",
            "runtime.target_video_seconds": str(duration_plan["target_seconds"]),
            "runtime.duration_gate.minimum_seconds": str(int(duration_plan["minimum_effective_seconds"])),
            "runtime.duration_plan.minimum_scene_count": str(duration_plan["minimum_scene_count"]),
            "runtime.duration_plan.minimum_narration_seconds": str(duration_plan["minimum_narration_seconds"]),
            "immersive.experience": experience,
            **(
                {"immersive.source_run": source_run.relative_to(REPO_ROOT).as_posix()}
                if source_run is not None
                else {}
            ),
            "slot.p420.status": "pending",
            "slot.p650.status": "pending",
            **(
                {
                    "slot.p660.status": "pending",
                    "slot.p670.status": "pending",
                    "slot.p680.status": "pending",
                }
                if stop_target == "p680"
                else {}
            ),
        },
    )
    _write_run_text_nofollow(
        run_dir,
        run_dir / "research.md",
        _md_yaml(
            f"リサーチ（{profile['topic_label']}）",
            _build_research(topic, source, now, profile),
        ),
    )
    _research_text, researched_source = load_structured_document(run_dir / "research.md")
    if not researched_source:
        raise RuntimeError("research.md is not a structured document")
    try:
        _validate_research_duration_contract(
            researched_source,
            target_duration_seconds=target_duration_seconds,
        )
    except RuntimeError as exc:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "timestamp": _now_iso(),
                "runtime.stage": "research_duration_contract_failed",
                "research.duration_contract.status": "failed",
                "last_error": str(exc)[:2000],
            },
        )
        raise
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "timestamp": _now_iso(),
            "research.duration_contract.status": "passed",
        },
    )
    profile = _profile_from_research(profile, researched_source)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "timestamp": _now_iso(),
            "runtime.stage": "story_authoring",
            "slot.p200.status": "in_progress",
            "slot.p200.note": "Story Architect / Scene Author is grounding story.md in researched source material",
        },
    )
    (story_author_runner or _author_story_with_codex)(
        run_dir=run_dir,
        topic=topic,
        target_duration_seconds=target_duration_seconds,
    )
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "timestamp": _now_iso(),
            "runtime.stage": "story_authored",
            "slot.p200.status": "authored",
            "slot.p200.note": "LLM-authored story.md passed deterministic research and handoff validation",
        },
    )
    _story_text, authored_story = load_structured_document(run_dir / "story.md")
    if not authored_story:
        raise RuntimeError("story.md is not a structured document")
    story_contract_errors = validate_story_document(
        authored_story,
        build_research_registry(researched_source),
    )
    if story_contract_errors:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "timestamp": _now_iso(),
                "runtime.stage": "story_contract_failed",
                "story.contract.status": "failed",
                "last_error": ", ".join(story_contract_errors)[:2000],
            },
        )
        raise RuntimeError(
            "story contract failed before cut materialization: "
            + ", ".join(story_contract_errors)
        )
    try:
        _validate_story_duration_contract(
            authored_story,
            target_duration_seconds=target_duration_seconds,
        )
    except RuntimeError as exc:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "timestamp": _now_iso(),
                "runtime.stage": "story_duration_contract_failed",
                "story.duration_contract.status": "failed",
                "last_error": str(exc)[:2000],
            },
        )
        raise
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "timestamp": _now_iso(),
            "story.duration_contract.status": "passed",
        },
    )
    try:
        _validate_story_time_of_day_contract(authored_story)
    except RuntimeError as exc:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "timestamp": _now_iso(),
                "runtime.stage": "story_time_of_day_contract_failed",
                "story.time_of_day_contract.status": "failed",
                "last_error": str(exc)[:2000],
            },
        )
        raise
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "timestamp": _now_iso(),
            "story.time_of_day_contract.status": "passed",
        },
    )
    authored_adaptation_contract = authored_story.get("adaptation_source_contract")
    if isinstance(authored_adaptation_contract, dict) and authored_adaptation_contract:
        profile["adaptation_source_contract"] = deepcopy(authored_adaptation_contract)
    profile = _profile_from_story(profile, authored_story)
    protagonist_asset = profile["protagonist_asset_id"]
    artifact_asset = profile["artifact_asset_id"]
    visual = {
        "visual_value_metadata": {
            "topic": topic,
            "source_story": str(run_dir / "story.md"),
            "created_at": now,
            "adaptation_value_contract": ADAPTATION_VALUE_MARKER,
        },
        "duration_plan": duration_plan,
        "adaptation_intent": _adaptation_intent_for_profile(profile),
        "global_visual_identity": {"format": "実写シネマティック", "palette": ["深い生活影", "月白", "金色", "象徴物の反射"], "no_onscreen_text": "画面内テキスト、字幕、ロゴ、ウォーターマークなし"},
        "scene_visual_values": [
            {
                "scene_selector": _runtime_scene_id(idx),
                "value": f"{title}の感情を、{'・'.join(profile['motifs'])}の触感で伝える",
                "anchor": title,
                "scene_value_amplification": _scene_value_amplification_for_profile(
                    profile=profile,
                    idx=idx,
                    title=title,
                ),
            }
            for idx, title in enumerate(profile["scene_titles"], start=1)
        ],
        "asset_bible_candidates": {"characters": [protagonist_asset, *[str(spec["character_id"]) for spec in _supporting_character_asset_specs(profile)]], "objects": [artifact_asset, *[str(spec["object_id"]) for spec in _supporting_object_asset_specs(profile)]], "locations": [spec["asset_id"] for spec in _location_asset_specs(profile)], "setpieces": [profile["artifact_name"], *[str(spec["name"]) for spec in _supporting_object_asset_specs(profile)]], "reusable_stills": ["時間制限を示す象徴的な光"]},
        "anchor_cut_candidates": [{"selector": "scene10_cut01", "reason": "主人公の顔と衣装を固定する"}],
        "reference_strategy": {"p500": f"{profile['protagonist_name']}全身参照と{profile['artifact_name']}を先に生成する", "p600": "各cutは参照画像を使い、同じ顔・象徴物・質感を保つ"},
        "regeneration_risks": [{"risk": "衣装や顔がcutごとに変わる", "mitigation": "character referenceを全cutに指定する"}],
        "handoff_to_p400_p500_p600_p700": {"p400_script": "scene設計から必要なcut数を逆算して構成する", "p500_asset": f"{protagonist_asset} と {artifact_asset} を必須参照にする", "p600_scene_implementation": "各cutにscene_contractと画像promptを持たせる", "p700_narration": "画像確定後に語りを同期する"},
    }
    _write_run_text_nofollow(
        run_dir,
        run_dir / "visual_value.md",
        _md_yaml(
            f"視覚化価値設計（{profile['topic_label']}）",
            visual,
        ),
    )
    _visual_text, authored_visual_value = load_structured_document(
        run_dir / "visual_value.md"
    )
    if not authored_visual_value:
        raise RuntimeError("visual_value.md is not a structured document")
    visual_adaptation_issues = visual_value_adaptation_issues(
        authored_visual_value,
        source_value_ids=adaptation_source_value_ids(authored_story),
    )
    if visual_adaptation_issues:
        raise RuntimeError(
            "visual_value adaptation contract is invalid: "
            + ", ".join(visual_adaptation_issues[:12])
        )
    authored_intent = authored_visual_value.get("adaptation_intent")
    if isinstance(authored_intent, dict) and authored_intent:
        profile["adaptation_intent"] = deepcopy(authored_intent)
    profile["scene_value_amplifications"] = {
        str(scene_value.get("scene_selector") or scene_value.get("scene_id")): deepcopy(
            scene_value["scene_value_amplification"]
        )
        for scene_value in authored_visual_value.get("scene_visual_values", [])
        if isinstance(scene_value, dict)
        and isinstance(scene_value.get("scene_value_amplification"), dict)
        and scene_value.get("scene_selector") is not None
    }
    try:
        script, manifest, selectors = _build_script_and_manifest(
            topic,
            run_dir,
            now,
            profile,
            experience=experience,
            source_run=source_run,
            source_references=source_references,
        )
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
    _require_current_scene_acceptance_before_publish(
        script,
        manifest,
        profile=profile,
        run_dir=run_dir,
    )
    generation_id = str(
        script["scene_set_authoring_contract"]["generation_id"]
    )
    staging_rel = Path("logs") / "authoring" / "staging" / generation_id
    for relative_directory in (
        Path("logs") / "authoring",
        Path("logs") / "authoring" / "staging",
        staging_rel,
        staging_rel / "scene_drafts",
    ):
        ensure_directory_relative_nofollow(
            run_dir,
            relative_directory,
            expected_root_identity=materialization_root_identity,
        )
    _write_run_text_nofollow(
        run_dir,
        run_dir / staging_rel / "contract.json",
        json.dumps(
            script["scene_set_authoring_contract"],
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    _write_run_text_nofollow(
        run_dir,
        run_dir / staging_rel / "preflight.json",
        json.dumps(
            script["authoring_preflight"],
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    _write_run_text_nofollow(
        run_dir,
        run_dir / staging_rel / "source_ledger.json",
        json.dumps(
            _scene_acceptance_source_ledger(profile),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    _write_run_text_nofollow(
        run_dir,
        run_dir / staging_rel / "criterion_registry.json",
        json.dumps(
            {
                "schema_version": CRITERION_REGISTRY_VERSION,
                "criterion_registry_sha256": criterion_registry_digest(),
                "criteria": criterion_registry_payload(),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    for scene in script["scenes"]:
        draft = scene["scene_acceptance_draft"]
        _write_run_text_nofollow(
            run_dir,
            run_dir
            / staging_rel
            / "scene_drafts"
            / f"{int(draft['scene_id'])}.json",
            json.dumps(
                draft,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
    _write_run_text_nofollow(
        run_dir,
        run_dir / staging_rel / "script.candidate.md",
        script_candidate_text := _md_yaml(
            f"台本候補（{profile['topic_label']} / cinematic_story）",
            script,
        ),
    )
    _write_run_text_nofollow(
        run_dir,
        run_dir / staging_rel / "video_manifest.candidate.md",
        manifest_candidate_text := _md_yaml(
            f"Video Manifest候補（{profile['topic_label']} / p450 production）",
            manifest,
        ),
    )
    publish_journal_path = run_dir / staging_rel / "publish.journal.json"
    canonical_publish_targets = {
        "script.md": script_candidate_text.replace("台本候補（", "台本（", 1),
        "video_manifest.md": manifest_candidate_text.replace(
            "Video Manifest候補（", "Video Manifest（", 1
        ),
    }
    canonical_target_digests = {
        relative: "sha256:"
        + hashlib.sha256(text.encode("utf-8")).hexdigest()
        for relative, text in canonical_publish_targets.items()
    }
    previous_canonical_bytes: dict[str, bytes | None] = {}
    for relative in canonical_publish_targets:
        try:
            previous_canonical_bytes[relative] = read_regular_file_nofollow(
                run_dir,
                relative,
                expected_root_identity=materialization_root_identity,
            )
        except FileNotFoundError:
            previous_canonical_bytes[relative] = None
    backup_rel = staging_rel / "publish_backup"
    ensure_directory_relative_nofollow(
        run_dir,
        backup_rel,
        expected_root_identity=materialization_root_identity,
    )
    for relative, previous in previous_canonical_bytes.items():
        if previous is None:
            continue
        write_regular_file_nofollow(
            destination_root=run_dir,
            destination_relative=backup_rel / relative,
            data=previous,
            expected_destination_root_identity=materialization_root_identity,
        )

    def write_publish_journal(status: str, *, error: str = "") -> None:
        _write_run_text_nofollow(
            run_dir,
            publish_journal_path,
            json.dumps(
                {
                    "schema_version": "scene_authoring_publish_journal_v1",
                    "generation_id": generation_id,
                    "status": status,
                    "contract_digest": script["scene_set_authoring_contract"][
                        "contract_digest"
                    ],
                    "preflight_digest": script["authoring_preflight"][
                        "preflight_digest"
                    ],
                    "canonical_targets": ["script.md", "video_manifest.md"],
                    "canonical_target_sha256": canonical_target_digests,
                    "previous_canonical": {
                        relative: {
                            "exists": previous is not None,
                            "sha256": (
                                "sha256:" + hashlib.sha256(previous).hexdigest()
                                if previous is not None
                                else None
                            ),
                            "backup_path": (
                                (backup_rel / relative).as_posix()
                                if previous is not None
                                else None
                            ),
                        }
                        for relative, previous in previous_canonical_bytes.items()
                    },
                    "error": error,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

    write_publish_journal("validated")
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "timestamp": _now_iso(),
            "authoring.scene_set.contract.status": "validated",
            "authoring.scene_set.contract.path": (
                staging_rel / "contract.json"
            ).as_posix(),
            "authoring.scene_set.contract.digest": script[
                "scene_set_authoring_contract"
            ]["contract_digest"],
            "authoring.scene_set.generation_id": generation_id,
            "authoring.scene_set.preflight.status": "passed",
            "authoring.scene_set.preflight.digest": script[
                "authoring_preflight"
            ]["preflight_digest"],
            "authoring.scene_set.preflight.source_digest": script[
                "authoring_preflight"
            ]["source_digest"],
            "authoring.scene_set.preflight.criterion_registry_digest": script[
                "authoring_preflight"
            ]["criterion_registry_digest"],
            "authoring.scene_set.preflight.error_count": "0",
            "authoring.scene_set.preflight.failed_scene_ids": "",
        },
    )
    write_publish_journal("publishing")
    try:
        for relative, text in canonical_publish_targets.items():
            _write_run_text_nofollow(run_dir, run_dir / relative, text)
    except Exception as publish_error:
        try:
            for relative, previous in reversed(previous_canonical_bytes.items()):
                if previous is not None:
                    write_regular_file_nofollow(
                        destination_root=run_dir,
                        destination_relative=relative,
                        data=previous,
                        expected_destination_root_identity=materialization_root_identity,
                    )
                    continue
                try:
                    current = read_regular_file_nofollow(
                        run_dir,
                        relative,
                        expected_root_identity=materialization_root_identity,
                    )
                except FileNotFoundError:
                    continue
                if (
                    "sha256:" + hashlib.sha256(current).hexdigest()
                    != canonical_target_digests[relative]
                ):
                    raise RuntimeError(
                        f"canonical publish rollback found changed bytes: {relative}"
                    )
                if not unlink_regular_file_verified_nofollow(
                    root=run_dir,
                    relative_path=relative,
                    expected_root_identity=materialization_root_identity,
                    expected_sha256=canonical_target_digests[relative].removeprefix(
                        "sha256:"
                    ),
                ):
                    raise RuntimeError(
                        f"canonical publish rollback could not remove: {relative}"
                    )
            write_publish_journal(
                "rolled_back",
                error=str(publish_error)[:2000],
            )
        except Exception as rollback_error:
            raise RuntimeError(
                "canonical scene publish failed and rollback failed: "
                f"{rollback_error}"
            ) from publish_error
        raise
    write_publish_journal("published")
    asset_inventory, asset_plan = _build_asset_artifacts_from_manifest(profile=profile, manifest=manifest)
    if experience == "world_walk":
        _apply_world_walk_asset_generation_contract(
            asset_plan=asset_plan,
            source_references=source_references,
        )
    _write_run_text_nofollow(
        run_dir,
        run_dir / "asset_inventory.md",
        _md_yaml("Asset Inventory", asset_inventory),
    )
    _write_run_text_nofollow(
        run_dir,
        run_dir / "asset_plan.md",
        _md_yaml("Asset Plan", asset_plan),
    )
    _prepare_authoring_grounding(run_dir)
    _require_fresh_p400_readiness(run_dir)
    _write_asset_request_files(run_dir, asset_plan, profile)
    _materialize_standard_request_files(run_dir)
    # Request projection persists compiled provider payloads back into the
    # production manifest. Re-ground and recheck the final structural revision
    # before handing concrete requests to the provider.
    _prepare_authoring_grounding(run_dir)
    _require_fresh_p400_readiness(run_dir)
    state_updates = _write_orchestration(run_dir, stop_target, now)
    media_slot_updates = _fresh_materialized_media_slot_updates(stop_target)
    slots = P680_SLOTS if stop_target == "p680" else P650_SLOTS
    for slot in slots:
        if f"slot.{slot}.status" in media_slot_updates:
            continue
        state_updates[f"slot.{slot}.status"] = "awaiting_approval" if slot in AWAITING_ALLOWED else "done"
        state_updates[f"slot.{slot}.note"] = "frontend handoff" if slot in AWAITING_ALLOWED else "completed by frontend create workflow"
    state_updates.update(media_slot_updates)
    state_updates.update(
        {
            "timestamp": now,
            "topic": topic,
            "runtime.run_variant.seed": str((profile.get("run_variant") or {}).get("seed") or ""),
            "runtime.run_variant.label": str((profile.get("run_variant") or {}).get("label") or ""),
            "runtime.target_video_seconds": str(duration_plan["target_seconds"]),
            "runtime.duration_gate.minimum_seconds": str(int(duration_plan["minimum_effective_seconds"])),
            "runtime.duration_plan.minimum_scene_count": str(duration_plan["minimum_scene_count"]),
            "runtime.duration_plan.minimum_narration_seconds": str(duration_plan["minimum_narration_seconds"]),
            "status": "P650",
            "runtime.stage": "provider_requests_ready",
            "runtime.stage_target": "p600",
            "runtime.stop_slot": stop_target,
            "runtime.scaffold.content_status": "authored",
            "immersive.experience": experience,
            "stage.research.status": "authored",
            "stage.story.status": "authored",
            "stage.visual_value.status": "authored",
            "stage.script.status": "authored",
            "stage.asset.status": "planned",
            "stage.scene_implementation.status": "planned",
            "generation.image_prompt.request_freeze.status": "draft",
            "generation.image_prompt.request_freeze.request": "image_generation_requests.md",
            "generation.image_prompt.request_freeze.snapshot": "image_generation_request_snapshot.json",
        }
    )
    append_state_snapshot(run_dir / "state.txt", state_updates)


def _prepare_authoring_grounding(run_dir: Path) -> None:
    for stage in ("research", "story", "visual_value", "script", "manifest"):
        _run_materialization_subprocess(
            run_dir,
            [sys.executable, str(REPO_ROOT / "scripts" / "prepare-stage-context.py"), "--stage", stage, "--run-dir", str(run_dir), "--flow", "immersive"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )


def prepare_grounding(
    run_dir: Path,
    *,
    verify_p450: bool = False,
) -> None:
    # Keep this compatibility keyword for callers that used to request a
    # p450 gate. Grounding prepares source/readset artifacts only; the state
    # worker records their progress.
    del verify_p450
    grounding_slots = {
        "asset": ("p510", "asset grounding completed"),
        "scene_implementation": ("p610", "scene implementation grounding completed"),
    }
    for stage, (slot, note) in grounding_slots.items():
        _run_materialization_subprocess(
            run_dir,
            [sys.executable, str(REPO_ROOT / "scripts" / "prepare-stage-context.py"), "--stage", stage, "--run-dir", str(run_dir), "--flow", "immersive"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        append_state_snapshot(
            run_dir / "state.txt",
            {
                "timestamp": _now_iso(),
                f"slot.{slot}.status": "done",
                f"slot.{slot}.note": note,
            },
        )


async def generate_images(run_dir: Path, stop_target: str) -> None:
    from server import image_gen_app

    run_id = _run_id_from_dir(run_dir)
    if stop_target == "p650":
        image_gen_app._validate_pre_asset_provider_gate(run_dir)
        await image_gen_app._generate_request_outputs(run_dir=run_dir, kind="asset")
        try:
            image_gen_app._validate_generated_outputs(run_dir, "asset")
        except Exception as exc:
            failed_check_ids = getattr(
                exc,
                "failed_check_ids",
                ("p570.asset_output_validation",),
            )
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    "timestamp": _now_iso(),
                    "runtime.stage": "asset_output_validation_failed",
                    "generation.asset_validation.status": "failed",
                    "generation.asset_validation.last_error": str(exc)[:2000],
                    "generation.asset_validation.failed_check_ids": ", ".join(
                        str(check_id)
                        for check_id in failed_check_ids
                        if str(check_id).strip()
                    ),
                    "slot.p550.status": "done",
                    "slot.p550.note": "asset requests were submitted to the image provider",
                    "slot.p560.status": "done",
                    "slot.p560.note": "reusable asset image generation completed before output validation failed",
                    "slot.p570.status": "failed",
                    "slot.p570.note": "asset output validation failed",
                    "stage.asset.status": "failed",
                },
            )
            raise
        image_gen_app._mark_asset_generation_handoff(
            run_dir,
            asset_quality_passed=True,
        )
        async with image_gen_app._serialized_run_write(
            run_dir,
            "scene_request_revision",
        ):
            image_gen_app._mark_image_prompt_request_freeze_done(run_dir)
    else:
        generation_completed = await image_gen_app._generate_create_images(
            "toc-immersive-frontend-run",
            run_id=run_id,
        )
        if generation_completed is False:
            raise RuntimeError(
                "asset output validation did not complete; "
                "p680 scene generation is blocked"
            )


def validate(run_dir: Path, stop_target: str) -> None:
    from server import image_gen_app

    run_id = _run_id_from_dir(run_dir)
    if stop_target == "p650":
        image_gen_app._validate_p650_run(run_id)
    else:
        image_gen_app._validate_frontend_create_run(run_id, strict_visual_quality=True)


def _require_materialization_free_space(run_dir: Path) -> None:
    available_bytes = shutil.disk_usage(run_dir.parent).free
    if available_bytes >= MIN_MATERIALIZATION_FREE_BYTES:
        return
    mib = 1024 * 1024
    raise RuntimeError(
        "storage preflight failed before materialization: "
        f"required {MIN_MATERIALIZATION_FREE_BYTES // mib} MiB free, "
        f"available {available_bytes // mib} MiB. "
        "Reclaim space by deleting unused output runs or moving them to another volume, then retry."
    )


# Compatibility names used by the resume helper and older structural fixtures.
# They only project authored source data; no review step is restored.
_profile_from_reviewed_research = _profile_from_research
_profile_from_reviewed_story = _profile_from_story
_reviewed_research_duration_contract_errors = _research_duration_contract_errors
_validate_reviewed_research_duration_contract = _validate_research_duration_contract
_reviewed_story_duration_contract_errors = _story_duration_contract_errors
_validate_reviewed_story_duration_contract = _validate_story_duration_contract
_reviewed_story_time_of_day_contract_errors = _story_time_of_day_contract_errors
_validate_reviewed_story_time_of_day_contract = _validate_story_time_of_day_contract
_reviewed_story_scene = _story_scene
_apply_reviewed_story_scene_to_blueprint = _apply_story_scene_to_blueprint


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ToC immersive frontend create workflow to p650/p680.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--source", default="")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument(
        "--expected-run-device",
        type=int,
        default=None,
        help="Optional server-probed destination st_dev binding.",
    )
    parser.add_argument(
        "--expected-run-inode",
        type=int,
        default=None,
        help="Optional server-probed destination st_ino binding.",
    )
    parser.add_argument(
        "--inherited-run-fd",
        type=int,
        default=None,
        help="Server-owned run descriptor carrying the active directory lease.",
    )
    parser.add_argument("--stop-target", choices=["p650", "p680"], default="p680")
    parser.add_argument(
        "--experience",
        choices=["cinematic_story", "world_walk"],
        default="cinematic_story",
    )
    parser.add_argument("--source-run", default=None)
    parser.add_argument(
        "--target-duration-seconds",
        type=int,
        default=300,
        help="Target video duration in seconds (300-1200).",
    )
    parser.add_argument(
        "--review-mode",
        default=None,
        help="Deprecated compatibility option; accepted and ignored.",
    )
    parser.add_argument("--materialize-only", action="store_true", help="Write text artifacts only; do not generate images or validate media.")
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    if (args.expected_run_device is None) != (
        args.expected_run_inode is None
    ):
        parser.error(
            "--expected-run-device and --expected-run-inode must be "
            "provided together"
        )
    if (
        args.expected_run_device is not None
        and (
            args.expected_run_device < 0
            or args.expected_run_inode < 0
        )
    ):
        parser.error("expected run identity values must be non-negative")

    try:
        target_duration_seconds = normalize_target_duration(args.target_duration_seconds)
    except ValueError as exc:
        parser.error(str(exc))

    source_run: Path | None = None
    world_walk_source_identity: PathIdentity | None = None
    world_walk_source_reference_lease: (
        WorldWalkSourceReferenceLease | None
    ) = None
    world_walk_source_story_sha256: str | None = None
    if args.experience == "world_walk":
        if not args.source_run:
            parser.error("--source-run is required for --experience world_walk")
        try:
            source_candidate, _source_run_rel = (
                validate_world_walk_source_contract_path(
                    REPO_ROOT,
                    args.source_run,
                    allow_missing=False,
                )
            )
            world_walk_source_identity = (
                directory_identity_nofollow(source_candidate)
            )
            source_run, _source_run_rel = validate_world_walk_source_path(
                REPO_ROOT,
                source_candidate,
            )
            if (
                directory_identity_nofollow(source_run)
                != world_walk_source_identity
            ):
                raise ValueError("world-walk source identity changed")
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        try:
            source_bytes = read_regular_file_nofollow(
                source_run,
                "story.md",
                expected_root_identity=world_walk_source_identity,
            )
            source = source_bytes.decode("utf-8")
            world_walk_source_story_sha256 = hashlib.sha256(
                source_bytes
            ).hexdigest()
            world_walk_source_reference_lease = (
                _freeze_world_walk_source_reference_inventory(
                    source_run,
                    source_root_identity=world_walk_source_identity,
                )
            )
        except (OSError, RuntimeError, UnicodeError, ValueError) as exc:
            parser.error(f"world-walk source story could not be read safely: {exc}")
    else:
        if args.source_run:
            parser.error("--source-run is only valid for --experience world_walk")
        source = args.source.strip() or args.topic
    expected_run_identity = (
        (args.expected_run_device, args.expected_run_inode)
        if args.expected_run_device is not None
        else None
    )
    run_dir = _validated_fresh_cli_run_dir(
        args.run_dir,
        expected_identity=expected_run_identity,
    )
    try:
        run_dir_identity = directory_identity_nofollow(run_dir)
    except (OSError, ValueError) as exc:
        parser.error(f"destination run could not be opened safely: {exc}")
    if (
        expected_run_identity is not None
        and run_dir_identity != expected_run_identity
    ):
        parser.error(
            "destination run identity changed after server reservation"
        )
    _require_materialization_free_space(run_dir)
    materialize_stop_target = "p650" if args.materialize_only and args.stop_target == "p680" else args.stop_target
    with _run_materialization_lock(
        run_dir,
        expected_identity=run_dir_identity,
        protect_pathname=True,
        inherited_descriptor=args.inherited_run_fd,
    ):
        materialize_run(
            args.topic,
            source,
            run_dir,
            materialize_stop_target,
            target_duration_seconds=target_duration_seconds,
            review_mode=args.review_mode,
            experience=args.experience,
            source_run=source_run,
            world_walk_source_identity=world_walk_source_identity,
            world_walk_destination_identity=run_dir_identity,
            world_walk_source_reference_lease=(
                world_walk_source_reference_lease
            ),
            world_walk_source_story_sha256=(
                world_walk_source_story_sha256
            ),
        )
        prepare_grounding(run_dir)
        if not args.materialize_only:
            asyncio.run(generate_images(run_dir, args.stop_target))
        write_run_index(run_dir)
        if not args.skip_validation:
            if args.materialize_only:
                from server import image_gen_app

                image_gen_app._validate_materialized_p650_run(_run_id_from_dir(run_dir))
            else:
                validate(run_dir, args.stop_target)
    print(f"Run dir: {run_dir.resolve()}")
    print(f"Stop target: {args.stop_target}")


if __name__ == "__main__":
    main()
