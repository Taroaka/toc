"""Image-stage semantic review collection helpers.

These collectors are intentionally side-effect free so a generic semantic pack
builder can call them before deciding where to render collection/scope/prompt
artifacts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from toc.harness import load_structured_document

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - exercised only in minimal envs
    yaml = None


IMAGE_STAGES = {"image_prompt"}
DEFAULT_MODE_FILTER = "generate_still"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
EXPECTED_ROLE_BY_ID_GROUP = {
    "character_ids": "character",
    "object_ids": "object",
    "location_ids": "location",
}
IMAGE_PROMPT_BLOCK_LABELS = (
    "参照画像の使い方",
    "shot / 画角",
    "この1枚に写る瞬間",
    "前cutからの変化",
    "人物の状態と配置",
    "小道具 / 物体",
    "場所の使い方",
    "このcutの開始状態",
    "単一瞬間ルール",
    "画面に必ず見えるもの",
    "画面に入れてはいけないもの",
    "人物状態",
    "小道具 / 舞台装置",
    "構図",
    "光 / 質感",
    "動画化のための開始余地",
    "禁止",
)


def _image_api_prompt_payload(image_generation: dict[str, Any]) -> dict[str, Any]:
    return _dict(image_generation.get("api_prompt_payload"))


def _image_api_prompt(image_generation: dict[str, Any]) -> str:
    payload = _image_api_prompt_payload(image_generation)
    return _as_str(payload.get("prompt") or image_generation.get("prompt"))


def _prompt_block_labels(prompt: str) -> list[str]:
    labels: list[str] = []
    for raw in (prompt or "").splitlines():
        match = re.fullmatch(r"\[(?P<label>.+?)\]", raw.strip())
        if not match:
            continue
        label = match.group("label").strip()
        if label in IMAGE_PROMPT_BLOCK_LABELS:
                labels.append(label)
    return labels


def build_first_frame_visual_plan(scene: dict[str, Any], cut: dict[str, Any]) -> dict[str, Any]:
    """Build the review-side derived plan that turns event intent into a drawable still."""

    explicit = _dict(cut.get("first_frame_visual_plan"))
    if explicit:
        return explicit
    image_generation = _dict(cut.get("image_generation"))
    contract = _cut_semantic_contract(cut, image_generation=image_generation)
    source = _dict(contract.get("source_event_contract"))
    event_context = _event_context_for_cut(scene, cut)
    primary_beat = _dict(event_context.get("primary_event_beat"))
    first_frame = _dict(_dict(cut.get("cut_contract")).get("first_frame_contract"))
    motion = _dict(_dict(cut.get("cut_contract")).get("motion_contract"))
    cinematic = _dict(_dict(cut.get("cut_contract")).get("cinematic_contract"))
    geography = _dict(cinematic.get("screen_geography"))
    ids = {
        "character_ids": _as_str_list(image_generation.get("character_ids")),
        "object_ids": _as_str_list(image_generation.get("object_ids")),
        "location_ids": _as_str_list(image_generation.get("location_ids")),
    }
    primary_id = _as_str(source.get("primary_event_beat_id") or primary_beat.get("beat_id"))
    source_ids = _as_str_list(source.get("source_event_beat_ids"))
    if primary_id and primary_id not in source_ids:
        source_ids = [primary_id, *source_ids]
    event_time_position = _as_str(source.get("event_time_position") or first_frame.get("event_time_position") or "before_trigger")
    visible_fact = _as_str(
        first_frame.get("event_fact_visible_in_still")
        or first_frame.get("first_frame_brief")
        or primary_beat.get("visible_action")
        or contract.get("visual_beat")
        or image_generation.get("prompt")
    )
    not_yet = (
        _as_str_list(first_frame.get("not_yet_happened_in_still"))
        or _as_str_list(source.get("event_facts_not_to_invent"))
        or _as_str_list(event_context.get("forbidden_event_changes"))
    )
    if not not_yet:
        not_yet = ["このcutの後続結果、次sceneの解決、未承認のrevealをまだ見せない。"]
    primary_anchor = (
        _as_str(_dict(cinematic.get("subject_priority")).get("primary"))
        or (ids["object_ids"] + ids["character_ids"] + ids["location_ids"] + _as_str_list(contract.get("must_include")) or [""])[0]
        or visible_fact
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
            "scene_id": _as_str(scene.get("scene_id")),
            "cut_id": _as_str(cut.get("cut_id")),
            "source_event_beat_id": primary_id,
            "source_event_beat_ids": source_ids,
            "event_beat_function": _as_str(source.get("event_beat_function") or primary_beat.get("beat_function")),
            "cut_function": _as_str(contract.get("cut_function")),
            "what_happens": _as_str(primary_beat.get("what_happens") or contract.get("target_beat")),
            "visible_action": _as_str(primary_beat.get("visible_action")),
            "visible_reaction": _as_str(primary_beat.get("visible_reaction")),
            "event_facts_to_preserve": _as_str_list(source.get("event_facts_to_preserve")),
            "event_facts_not_to_invent": _as_str_list(source.get("event_facts_not_to_invent")),
            "allowed_reveal_info_ids": _as_str_list(source.get("allowed_reveal_info_ids")),
            "forbidden_reveal_info_ids": _as_str_list(source.get("forbidden_reveal_info_ids")),
        },
        "temporal_boundary": {
            "event_time_position": event_time_position,
            "first_visible_moment": visible_fact,
            "action_completion_state": _as_str(first_frame.get("action_completion_state") or "hold"),
            "event_fact_visible_in_still": visible_fact,
            "not_yet_happened_in_still": not_yet,
            "forbidden_future_event_beat_ids": _as_str_list(motion.get("must_not_advance_to_event_beat_ids")),
            "forbidden_future_outcomes": not_yet,
            "still_must_not_show_completion": True,
            "one_visible_moment_rule": True,
        },
        "visual_translation": {
            "concrete_visible_evidence": [{"visible_substitute": visible_fact, "must_be_drawn_as": visible_fact}],
            "nonvisual_terms_to_exclude_from_prompt": ["価値変化", "場所の圧力", "観客理解", "因果の証明"],
            "imageable_causal_proof": _as_str(contract.get("causal_proof") or contract.get("visual_beat") or visible_fact),
        },
        "subject_binding": {
            "primary_subject": {"id": primary_anchor, "name": primary_anchor, "role": "primary_visual_anchor", "screen_priority": 1},
            "secondary_subjects": [{"id": item, "name": item, "role": "secondary_visual_anchor", "screen_priority": index + 2} for index, item in enumerate((ids["character_ids"] + ids["object_ids"] + ids["location_ids"])[1:])],
            "background_subjects": [{"id": item, "name": item, "role": "location_anchor", "visibility": "clearly_visible"} for item in ids["location_ids"]],
        },
        "object_visibility_gate": {
            "objects": [
                {
                    "object_id": object_id,
                    "visibility_in_this_cut": "clearly_visible",
                    "relation_to_event": visible_fact,
                    "story_meaning_in_this_cut": _as_str(contract.get("visual_beat") or contract.get("causal_proof")),
                }
                for object_id in ids["object_ids"]
            ]
        },
        "spatial_composition": {
            "aspect_ratio": _as_str(image_generation.get("aspect_ratio") or "16:9"),
            "foreground": _as_str(geography.get("foreground")),
            "midground": _as_str(geography.get("midground")),
            "background": _as_str(geography.get("background")),
            "subject_priority_order": [primary_anchor, *ids["character_ids"], *ids["object_ids"], *ids["location_ids"]],
            "frame_edge_handoff": _as_str(geography.get("frame_edge_handoff")),
        },
        "scene_material_pack": {
            "location_id": ids["location_ids"][0] if ids["location_ids"] else "",
            "light_source": _as_str(first_frame.get("light_source") or "scene固有の光源"),
            "dominant_materials": _as_str_list(first_frame.get("dominant_materials")),
        },
        "motion_affordance": {
            "movable_subjects": [{"subject_id": primary_anchor, "movement_vector": _as_str(motion.get("subject_motion") or "静止画の姿勢から自然に動き出す方向")}],
            "must_not_resolve_in_image": not_yet,
            "motion_ceiling": {
                "must_stop_before_event_beat_ids": _as_str_list(motion.get("must_not_advance_to_event_beat_ids")),
                "must_not_complete_outcomes": not_yet,
            },
        },
        "prompt_rendering_policy": {
            "render_only_drawable_information": True,
            "do_not_render_design_meta": True,
            "do_not_render_future_motion_as_action": True,
        },
    }


def collect_entries(stage: str, run_dir: Path, manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Collect image semantic review entries for a generic dispatcher."""

    if stage not in IMAGE_STAGES:
        raise ValueError(f"unsupported image semantic stage: {stage}")
    resolved_run_dir = Path(run_dir).resolve()
    data = manifest if isinstance(manifest, dict) else load_manifest(resolved_run_dir / "video_manifest.md")
    asset_context = asset_context_by_id(resolved_run_dir)
    entries = collect_image_prompt_entries(data, asset_context=asset_context)
    return entries + collect_scene_composite_entries(data, stage=stage)


def load_manifest(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to collect image semantic review entries.")
    return yaml.safe_load(extract_yaml_block(path.read_text(encoding="utf-8"))) or {}


def extract_yaml_block(text: str) -> str:
    match = re.search(r"```yaml\s*\n(.*?)\n```", text, re.S)
    if not match:
        raise ValueError("YAML block not found in video_manifest.md")
    return match.group(1)


def collect_image_prompt_entries(
    manifest: dict[str, Any],
    *,
    mode_filter: str = DEFAULT_MODE_FILTER,
    asset_context: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    asset_context = asset_context or {}
    for scene, cut in iter_scene_cuts(manifest):
        image_generation = _dict(cut.get("image_generation"))
        if not image_generation:
            continue
        plan = _dict(cut.get("still_image_plan"))
        plan_mode = _as_str(plan.get("mode"))
        if plan_mode and plan_mode != mode_filter:
            continue
        review = _dict(image_generation.get("review"))
        contract = _cut_semantic_contract(cut, image_generation=image_generation, review=review)
        semantic_contract = semantic_contract_payload(contract)
        event_context = _event_context_for_cut(scene, cut)
        first_frame_visual_plan = build_first_frame_visual_plan(scene, cut)
        api_prompt_payload = _image_api_prompt_payload(image_generation)
        api_prompt = _image_api_prompt(image_generation)
        ids = {
            "character_ids": _as_str_list(image_generation.get("character_ids")),
            "object_ids": _as_str_list(image_generation.get("object_ids")),
            "location_ids": _as_str_list(image_generation.get("location_ids")),
        }
        entries.append(
            {
                "stage": "image_prompt",
                "review_scope": "all_entries",
                "selector": cut_selector(scene, cut),
                "scene_id": scene.get("scene_id"),
                "cut_id": cut.get("cut_id"),
                "output": _as_str(image_generation.get("output")),
                "prompt": api_prompt,
                "legacy_prompt": _as_str(image_generation.get("prompt")),
                "api_prompt_payload": api_prompt_payload,
                "api_prompt_policy_version": _as_str(api_prompt_payload.get("policy_version")),
                "debug_prompt_source": _dict(image_generation.get("debug_prompt_source")),
                "prompt_blocks": _prompt_block_labels(api_prompt),
                "image_prompt_gate_focus": [
                    "api_prompt_payload.prompt が API 送信用正本であり、legacy image_generation.prompt や debug_prompt_source を読んでいないか",
                    "API prompt が意味説明ではなく、shot / location zone / blocking / object contact / previous cut delta で描ける1枚になっているか",
                    "旧 [cut契約からの可視要件] や 場面の核/観客理解/因果の証明 などの設計メタが API prompt に残っていないか",
                    "source_event_contract と event_context_for_cut の ID や event_time_position / what_happens / visible_action が API prompt に漏れていないか",
                    "小道具の reveal boundary が must_include / must_not_include と矛盾していないか",
                    "参照画像の使い方、人物状態、小道具 visibility、構図、光/質感、動画化の開始余地が描画可能な具体語になっているか",
                    "motion_brief や後続の出来事が API prompt に混入していないか",
                    "first_frame_visual_plan が poster 的な雰囲気画像ではなく、cutの出来事が始まる1つの瞬間へ変換されているか",
                ],
                "references": _as_str_list(image_generation.get("references")),
                **ids,
                "asset_reference_context": reference_context(ids, asset_context),
                "reference_count": _as_int(image_generation.get("reference_count")),
                "narration": narration_text(cut),
                "rationale": _as_str(plan.get("rationale")),
                "event_context_for_cut": event_context,
                "first_frame_visual_plan": first_frame_visual_plan,
                "semantic_contract": semantic_contract,
                "semantic_contract_missing": semantic_contract_missing(semantic_contract),
                "contract_required_fields_missing": missing_contract_fields(semantic_contract),
                "review": {
                    "status": _as_str(review.get("status")),
                    "agent_review_ok": _as_bool(review.get("agent_review_ok"), True),
                    "human_review_ok": _as_bool(review.get("human_review_ok"), False),
                    "agent_review_reason_keys": _as_str_list(
                        review.get("agent_review_reason_keys") or review.get("agent_review_reason_codes")
                    ),
                    "agent_review_reason_messages": _as_str_list(review.get("agent_review_reason_messages")),
                    "overall_score": _as_float(review.get("overall_score")),
                },
            }
        )
    return entries


def collect_scene_image_entries(
    run_dir: Path,
    manifest: dict[str, Any],
    *,
    asset_context: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    provenance = image_generation_provenance_by_destination(run_dir)
    contact_sheet_refs = discover_contact_sheet_refs(run_dir)
    contact_sheet_missing = not contact_sheet_refs
    asset_context = asset_context or {}
    entries: list[dict[str, Any]] = []
    for scene, cut in iter_scene_cuts(manifest):
        image_generation = _dict(cut.get("image_generation"))
        output = _as_str(image_generation.get("output"))
        if not output:
            continue
        output_path = resolve_run_path(run_dir, output)
        selector = cut_selector(scene, cut)
        matched_provenance = provenance.get(output) or provenance.get(output_path.as_posix())
        final_output_provenance = normalize_final_output_provenance(
            output=output,
            output_path=output_path,
            provenance=matched_provenance,
        )
        ids = {
            "character_ids": _as_str_list(image_generation.get("character_ids")),
            "object_ids": _as_str_list(image_generation.get("object_ids")),
            "location_ids": _as_str_list(image_generation.get("location_ids")),
        }
        semantic_contract = semantic_contract_payload(_cut_semantic_contract(cut, image_generation=image_generation))
        api_prompt_payload = _image_api_prompt_payload(image_generation)
        api_prompt = _image_api_prompt(image_generation)
        entries.append(
            {
                "stage": "scene_image",
                "review_scope": "all_entries",
                "selector": selector,
                "scene_id": scene.get("scene_id"),
                "cut_id": cut.get("cut_id"),
                "output": output,
                "output_exists": output_path.exists() and output_path.is_file(),
                "output_path": output_path.as_posix(),
                "final_output_provenance": final_output_provenance,
                "generated_image_path": _as_str((matched_provenance or {}).get("savedPath")),
                "generation_source": _as_str((matched_provenance or {}).get("source")),
                "debug_log": _as_str((matched_provenance or {}).get("debug_log")),
                "prompt": api_prompt,
                "legacy_prompt": _as_str(image_generation.get("prompt")),
                "api_prompt_payload": api_prompt_payload,
                "api_prompt_policy_version": _as_str(api_prompt_payload.get("policy_version")),
                "references": _as_str_list(image_generation.get("references")),
                **ids,
                "asset_reference_context": reference_context(ids, asset_context),
                "reference_count": _as_int(image_generation.get("reference_count")),
                "semantic_contract": semantic_contract,
                "semantic_contract_missing": semantic_contract_missing(semantic_contract),
                "contract_required_fields_missing": missing_contract_fields(semantic_contract),
                "narration": narration_text(cut),
                "contact_sheet_required": True,
                "contact_sheet_missing": contact_sheet_missing,
                "contact_sheet_refs": contact_sheet_refs,
            }
        )
    return entries


def collect_scene_composite_entries(
    manifest: dict[str, Any],
    *,
    stage: str,
    run_dir: Path | None = None,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    scenes = manifest.get("scenes")
    if not isinstance(scenes, list):
        return entries
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        cuts = [cut for cut in _list(scene.get("cuts")) if isinstance(cut, dict)]
        if not cuts:
            continue
        cut_entries: list[dict[str, Any]] = []
        for cut in cuts:
            image_generation = _dict(cut.get("image_generation"))
            video_generation = _dict(cut.get("video_generation"))
            contract = _cut_semantic_contract(cut, image_generation=image_generation)
            semantic_contract = semantic_contract_payload(contract)
            first_frame_visual_plan = build_first_frame_visual_plan(scene, cut)
            api_prompt_payload = _image_api_prompt_payload(image_generation)
            api_prompt = _image_api_prompt(image_generation)
            output = _as_str(image_generation.get("output"))
            output_exists = None
            if run_dir is not None and output:
                output_exists = resolve_run_path(run_dir, output).exists()
            cut_entries.append(
                {
                    "selector": cut_selector(scene, cut),
                    "cut_function": _as_str(contract.get("cut_function")),
                    "source_event_contract": _dict(contract.get("source_event_contract")),
                    "target_focus": semantic_contract.get("target_focus", ""),
                    "screen_question": _as_str(contract.get("screen_question")),
                    "dramatic_job": _as_str(contract.get("dramatic_job")),
                    "audience_knowledge_delta": _as_str(contract.get("audience_knowledge_delta")),
                    "causal_proof": _as_str(contract.get("causal_proof")),
                    "visual_evidence": _as_str_list(contract.get("visual_evidence")),
                    "required_roles": _as_str_list(contract.get("required_roles")),
                    "anti_redundancy_key": _as_str(contract.get("anti_redundancy_key")),
                    "visual_proof": _as_str(contract.get("visual_beat") or contract.get("visual_proof")),
                    "first_frame_brief": _as_str(contract.get("first_frame_brief")),
                    "static_first_frame_rule": _as_str(contract.get("static_first_frame_rule")),
                    "prompt": api_prompt,
                    "legacy_prompt": _as_str(image_generation.get("prompt")),
                    "api_prompt_payload": api_prompt_payload,
                    "api_prompt_policy_version": _as_str(api_prompt_payload.get("policy_version")),
                    "image_output": output,
                    "image_output_exists": output_exists,
                    "video_motion_prompt": _as_str(video_generation.get("motion_prompt")),
                    "motion_brief": _as_str(contract.get("motion_brief")),
                    "narration": narration_text(cut),
                    "event_context_for_cut": _event_context_for_cut(scene, cut),
                    "first_frame_visual_plan": first_frame_visual_plan,
                    "semantic_contract": semantic_contract,
                }
            )
        scene_intent = _dict(scene.get("scene_intent"))
        scene_event = _dict(scene.get("scene_event"))
        scene_contract = {
            "scene_id": scene.get("scene_id"),
            "scene_intent": scene_intent,
            "role_coverage": _dict(scene_intent.get("role_coverage")) or _dict(scene.get("role_coverage")) or _dict(scene_event.get("role_coverage")),
            "audience_knowledge_plan": _audience_knowledge_items(scene_intent) or _as_str_list(scene.get("audience_knowledge_plan")) or _as_str_list(scene_event.get("audience_knowledge_plan")),
            "visual_proof_obligations": _list(scene_intent.get("visual_proof_obligations")) or _list(scene.get("visual_proof_obligations")) or _list(scene_event.get("visual_proof_obligations")),
            "anti_redundancy_policy": _dict(scene_intent.get("anti_redundancy_policy")) or _dict(scene.get("anti_redundancy_policy")) or _dict(scene_event.get("anti_redundancy_policy")),
            "static_first_frame_rules": _as_str_list(scene_intent.get("static_first_frame_rules")) or _as_str_list(scene.get("static_first_frame_rules")) or _as_str_list(scene_event.get("static_first_frame_rules")),
            "scene_cut_coverage_plan": _dict(scene.get("scene_cut_coverage_plan")),
            "handoff_to_next_scene": _as_str(scene.get("handoff_to_next_scene")),
            "terminal_resolution": _as_str(scene.get("terminal_resolution")),
            "target_duration_seconds": scene.get("target_duration_seconds"),
            "estimated_duration_seconds": scene.get("estimated_duration_seconds"),
            "cut_count": len(cut_entries),
        }
        scene_cut_coverage_plan = _dict(scene.get("scene_cut_coverage_plan"))
        entries.append(
            {
                "stage": stage,
                "review_scope": "scene_composite",
                "selector": f"scene{scene.get('scene_id')}",
                "scene_id": scene.get("scene_id"),
                "scene_contract": scene_contract,
                "scene_event": scene_event,
                "scene_cut_coverage_plan": scene_cut_coverage_plan,
                "story_event_obligations": _list(scene_intent.get("story_event_obligations")) or _list(scene.get("story_event_obligations")),
                "role_coverage": _dict(scene_intent.get("role_coverage")) or _dict(scene.get("role_coverage")) or _dict(scene_event.get("role_coverage")),
                "audience_knowledge_delta": _dict(scene_intent.get("audience_knowledge_delta")) or _dict(scene.get("audience_knowledge_delta")) or _dict(scene_event.get("audience_knowledge_delta")),
                "audience_knowledge_plan": _audience_knowledge_items(scene_intent) or _as_str_list(scene.get("audience_knowledge_plan")) or _as_str_list(scene_event.get("audience_knowledge_plan")),
                "visual_proof_obligations": _list(scene_intent.get("visual_proof_obligations")) or _list(scene.get("visual_proof_obligations")) or _list(scene_event.get("visual_proof_obligations")),
                "anti_redundancy_policy": _dict(scene_intent.get("anti_redundancy_policy")) or _dict(scene.get("anti_redundancy_policy")) or _dict(scene_event.get("anti_redundancy_policy")),
                "static_first_frame_rules": _as_str_list(scene_intent.get("static_first_frame_rules")) or _as_str_list(scene.get("static_first_frame_rules")) or _as_str_list(scene_event.get("static_first_frame_rules")),
                "cut_count": len(cut_entries),
                "cut_entries": cut_entries,
                "scene_composite_gate": {
                    "required": True,
                    "minimum_cut_count": _coverage_minimum_cut_count(scene_cut_coverage_plan),
                    "must_judge": [
                        "scene_cut_coverage_plan の scene_obligations が cut_entries に割り当てられているか",
                        "cut_contract.source_event_contract の primary_event_beat_id / source_event_beat_ids が scene_event.event_sequence の beat_id を参照し、setup/pressure/turn/payoff を網羅しているか",
                        "event_context_for_cut が source_event_contract から生成された downstream 用 projection として primary beat だけを渡しているか",
                        "first_frame_visual_plan が source_event_contract / event_context_for_cut / first_frame_contract / motion_contract から派生し、物語意味を描画可能な開始静止画へ変換しているか",
                        "role_coverage.required_roles にある妨害者・助力者・証人・共同体などが、必要なsceneで主人公単独に潰されていないか",
                        "cutごとの差異が番号差分や同義反復ではなく、sceneを再現するために必要な視覚要件の分担になっているか",
                        "各cutの first_frame_brief が motion ではなく静止画として読める causal proof を持つか",
                        "各cutの画像promptが、動画として接続した時にscene設計の問い、価値変化、因果転換、handoffを伝えられるか",
                        "不足時は scene_requires_more_cuts、絵の具体性不足は cut_prompt_requires_reinforcement、重複過多は scene_cut_prompt_too_similar として判定する",
                    ],
                    "failure_reason_keys": [
                        "scene_cut_coverage_insufficient",
                        "scene_cut_prompt_too_similar",
                        "scene_meaning_not_visualized_across_cuts",
                        "scene_video_handoff_weak",
                        "scene_requires_more_cuts",
                        "cut_prompt_requires_reinforcement",
                        "event_beat_reference_integrity",
                        "source_event_preservation",
                        "event_first_frame_alignment",
                        "event_motion_boundary",
                        "event_narration_boundary",
                        "event_context_for_cut_not_derived",
                        "first_frame_visual_plan_missing",
                        "first_frame_is_story_event_start_not_poster",
                        "first_frame_has_action_potential",
                        "first_frame_preserves_scene_event_boundary",
                        "first_frame_does_not_resolve_cut_too_early",
                        "first_frame_does_not_show_later_reveal",
                        "first_frame_contains_specific_story_evidence",
                        "first_frame_has_cinematic_subject_hierarchy",
                        "first_frame_is_not_generic_mood_image",
                        "first_frame_can_connect_to_motion_prompt",
                        "first_frame_can_connect_to_narration_without_captioning",
                        "audience_knowledge_delta_missing",
                        "causal_proof_weak",
                        "role_coverage_missing",
                        "static_first_frame_not_imageable",
                        "scene_cut_redundancy_excessive",
                    ],
                },
            }
        )
    return entries


def asset_context_by_id(run_dir: Path) -> dict[str, dict[str, Any]]:
    context: dict[str, dict[str, Any]] = {}
    for rel in ("asset_inventory.md", "asset_plan.md"):
        path = run_dir / rel
        if not path.exists():
            continue
        _, data = load_structured_document(path)
        if rel == "asset_inventory.md":
            root = data.get("asset_inventory") if isinstance(data.get("asset_inventory"), dict) else data
            for item in _list(root.get("items") if isinstance(root, dict) else []):
                if not isinstance(item, dict):
                    continue
                asset_id = _as_str(item.get("item_id") or item.get("asset_id"))
                if not asset_id:
                    continue
                context.setdefault(asset_id, {}).update(
                    {
                        "inventory_category": _as_str(item.get("category")),
                        "inventory_story_purpose": _as_str(item.get("story_purpose")),
                        "reusable_reason": _as_str(item.get("reusable_reason")),
                        "recommended_asset_type": _as_str(item.get("recommended_asset_type")),
                    }
                )
        else:
            for item in asset_plan_items(data):
                if not isinstance(item, dict):
                    continue
                asset_id = _as_str(item.get("asset_id") or item.get("item_id"))
                if not asset_id:
                    continue
                context.setdefault(asset_id, {}).update(
                    {
                        "asset_type": _as_str(item.get("asset_type")),
                        "story_purpose": _as_str(item.get("story_purpose")),
                        "source_script_selectors": _as_str_list(item.get("source_script_selectors")),
                        "visual_spec": item.get("visual_spec") if item.get("visual_spec") is not None else {},
                    }
                )
    return {asset_id: payload for asset_id, payload in context.items() if any(value not in ("", [], {}) for value in payload.values())}


def asset_plan_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    assets = data.get("assets")
    if isinstance(assets, list):
        return [item for item in assets if isinstance(item, dict)]
    if not isinstance(assets, dict):
        return []
    out: list[dict[str, Any]] = []
    for category in ("characters", "objects", "locations", "setpieces", "reusable_stills"):
        for item in _list(assets.get(category)):
            if isinstance(item, dict):
                copied = dict(item)
                copied.setdefault("_category", category)
                out.append(copied)
    return out


def reference_context(ids: dict[str, list[str]], asset_context: dict[str, dict[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for group, values in ids.items():
        expected_role = EXPECTED_ROLE_BY_ID_GROUP.get(group, "")
        matched = {
            asset_id: normalize_asset_reference_context(asset_context.get(asset_id, {}), expected_role=expected_role)
            for asset_id in values
            if asset_context.get(asset_id)
        }
        if matched:
            payload[group] = matched
    return payload


def normalize_asset_reference_context(context: dict[str, Any], *, expected_role: str) -> dict[str, Any]:
    category = _as_str(context.get("category") or context.get("inventory_category") or context.get("asset_type") or context.get("recommended_asset_type"))
    story_purpose = _as_str(context.get("story_purpose") or context.get("inventory_story_purpose") or context.get("reusable_reason"))
    visual_spec = context.get("visual_spec") if context.get("visual_spec") is not None else {}
    return {
        "category": category,
        "story_purpose": story_purpose,
        "visual_spec": visual_spec,
        "expected_reference_role": expected_role,
        "reference_role_mismatch_hints": reference_role_mismatch_hints(context, expected_role=expected_role),
    }


def reference_role_mismatch_hints(context: dict[str, Any], *, expected_role: str) -> list[str]:
    if not expected_role:
        return []
    actual_roles = infer_reference_roles(context)
    if not actual_roles or expected_role in actual_roles:
        return []
    sorted_actual_roles = sorted(actual_roles)
    return [
        "expected_reference_role="
        f"{expected_role} but asset metadata suggests {','.join(sorted_actual_roles)}"
    ]


def infer_reference_roles(context: dict[str, Any]) -> set[str]:
    values = [
        context.get("category"),
        context.get("inventory_category"),
        context.get("asset_type"),
        context.get("recommended_asset_type"),
    ]
    combined = " ".join(_as_str(value).lower() for value in values if _as_str(value))
    roles: set[str] = set()
    if any(token in combined for token in ("character", "person", "people", "人物", "キャラクター")):
        roles.add("character")
    if any(token in combined for token in ("object", "artifact", "prop", "item", "小道具", "物", "舞台装置")):
        roles.add("object")
    if any(token in combined for token in ("location", "place", "setting", "background", "場所", "舞台", "背景")):
        roles.add("location")
    return roles


def iter_scene_cuts(manifest: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    scenes = manifest.get("scenes")
    if not isinstance(scenes, list):
        return pairs
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        cuts = scene.get("cuts")
        if not isinstance(cuts, list):
            continue
        for cut in cuts:
            if isinstance(cut, dict):
                pairs.append((scene, cut))
    return pairs


def cut_selector(scene: dict[str, Any], cut: dict[str, Any]) -> str:
    explicit = _as_str(cut.get("selector"))
    if explicit:
        return explicit
    scene_digits = re.sub(r"\D+", "", str(scene.get("scene_id") or ""))
    cut_raw = str(cut.get("cut_id") or "")
    cut_digits = re.sub(r"\D+", "", cut_raw.split("-")[-1])
    if scene_digits and cut_digits:
        return f"scene{int(scene_digits):02d}_cut{int(cut_digits):02d}"
    return ""


def narration_text(cut: dict[str, Any]) -> str:
    audio = _dict(cut.get("audio"))
    narration = _dict(audio.get("narration"))
    return _as_str(narration.get("text") or narration.get("tts_text"))


def _cut_semantic_contract(
    cut: dict[str, Any],
    *,
    image_generation: dict[str, Any] | None = None,
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    image_generation = image_generation or _dict(cut.get("image_generation"))
    review = review or _dict(image_generation.get("review"))
    explicit = _dict(review.get("contract")) or _dict(image_generation.get("contract"))
    if explicit:
        return explicit
    cut_contract = _dict(cut.get("cut_contract"))
    if cut_contract:
        legacy_scene_contract = _dict(cut.get("scene_contract"))
        source_event = _dict(cut_contract.get("source_event_contract"))
        viewer = _dict(cut_contract.get("viewer_contract"))
        first_frame = _dict(cut_contract.get("first_frame_contract"))
        motion = _dict(cut_contract.get("motion_contract"))
        cinematic = _dict(cut_contract.get("cinematic_contract"))
        geography = _dict(cinematic.get("screen_geography"))
        continuity = _dict(cut_contract.get("continuity_contract"))
        location_ids = _as_str_list(continuity.get("location_ids"))
        start_state = _dict(continuity.get("start_state"))
        return {
            "cut_function": _as_str(cut_contract.get("cut_function")),
            "source_event_contract": {
                "primary_event_beat_id": _as_str(source_event.get("primary_event_beat_id")),
                "source_event_beat_ids": _as_str_list(source_event.get("source_event_beat_ids")),
                "event_beat_function": _as_str(source_event.get("event_beat_function")),
                "event_time_position": _as_str(source_event.get("event_time_position")),
                "event_facts_to_preserve": _as_str_list(source_event.get("event_facts_to_preserve")),
                "event_facts_not_to_invent": _as_str_list(source_event.get("event_facts_not_to_invent")),
                "allowed_reveal_info_ids": _as_str_list(source_event.get("allowed_reveal_info_ids")),
                "forbidden_reveal_info_ids": _as_str_list(source_event.get("forbidden_reveal_info_ids")),
            },
            "event_facts_to_preserve": _as_str_list(source_event.get("event_facts_to_preserve")),
            "event_facts_not_to_invent": _as_str_list(source_event.get("event_facts_not_to_invent")),
            "target_focus": _as_str(viewer.get("target_beat") or cut_contract.get("target_beat")),
            "target_beat": _as_str(viewer.get("target_beat") or cut_contract.get("target_beat")),
            "screen_question": _as_str(viewer.get("screen_question")),
            "dramatic_job": _as_str(viewer.get("dramatic_job")),
            "audience_knowledge_delta": _as_str(viewer.get("audience_knowledge_delta")),
            "causal_proof": _as_str(viewer.get("causal_proof")),
            "visual_evidence": _as_str_list(viewer.get("visual_evidence")),
            "required_roles": _as_str_list(viewer.get("required_roles")),
            "anti_redundancy_key": _as_str(viewer.get("anti_redundancy_key")),
            "visual_beat": _as_str(viewer.get("visual_proof") or cut_contract.get("visual_beat")),
            "must_include": _as_str_list(viewer.get("must_show") or first_frame.get("must_include")),
            "must_show": _as_str_list(viewer.get("must_show") or first_frame.get("must_include")),
            "must_avoid": _as_str_list(viewer.get("must_avoid") or first_frame.get("must_avoid")),
            "done_when": _as_str_list(viewer.get("done_when")),
            "not_yet_visible": _as_str_list(viewer.get("not_yet_visible") or legacy_scene_contract.get("not_yet_visible")),
            "only_after_scene": _as_str(viewer.get("only_after_scene") or legacy_scene_contract.get("only_after_scene")),
            "first_frame_brief": _as_str(first_frame.get("first_frame_brief")),
            "static_first_frame_rule": _as_str(first_frame.get("static_first_frame_rule")),
            "motion_brief": _as_str(motion.get("motion_brief")),
            "primary_location": _as_str(geography.get("background") or legacy_scene_contract.get("primary_location") or (location_ids[0] if location_ids else "")),
            "emotional_state": _as_str(first_frame.get("emotional_state") or legacy_scene_contract.get("emotional_state")),
            "continuity_from_previous": _as_str(legacy_scene_contract.get("continuity_from_previous") or start_state.get("spatial_state") or start_state.get("character_state")),
        }
    return _dict(cut.get("scene_contract"))


def semantic_contract_payload(contract: dict[str, Any]) -> dict[str, Any]:
    source_event_contract = _dict(contract.get("source_event_contract"))
    return {
        "source_event_contract": source_event_contract,
        "primary_event_beat_id": _as_str(source_event_contract.get("primary_event_beat_id")),
        "source_event_beat_ids": _as_str_list(source_event_contract.get("source_event_beat_ids")),
        "event_facts_to_preserve": _as_str_list(contract.get("event_facts_to_preserve")),
        "event_facts_not_to_invent": _as_str_list(contract.get("event_facts_not_to_invent")),
        "target_focus": _as_str(contract.get("target_focus") or contract.get("target_beat")),
        "must_include": _as_str_list(contract.get("must_include") or contract.get("must_show")),
        "must_avoid": _as_str_list(contract.get("must_avoid")),
        "done_when": _as_str_list(contract.get("done_when")),
        "not_yet_visible": _as_str_list(contract.get("not_yet_visible")),
        "only_after_scene": _as_str(contract.get("only_after_scene")),
        "primary_location": _as_str(contract.get("primary_location")),
        "emotional_state": _as_str(contract.get("emotional_state")),
        "continuity_from_previous": _as_str(contract.get("continuity_from_previous")),
        "audience_knowledge_delta": _as_str(contract.get("audience_knowledge_delta")),
        "causal_proof": _as_str(contract.get("causal_proof")),
        "visual_evidence": _as_str_list(contract.get("visual_evidence")),
        "required_roles": _as_str_list(contract.get("required_roles")),
        "static_first_frame_rule": _as_str(contract.get("static_first_frame_rule")),
        "anti_redundancy_key": _as_str(contract.get("anti_redundancy_key")),
    }


def _event_context_for_cut(scene: dict[str, Any], cut: dict[str, Any]) -> dict[str, Any]:
    scene_event = _dict(scene.get("scene_event"))
    sequence = [beat for beat in _list(scene_event.get("event_sequence")) if isinstance(beat, dict)]
    if not scene_event or not sequence:
        return {}
    by_id = {str(beat.get("beat_id") or "").strip(): beat for beat in sequence if str(beat.get("beat_id") or "").strip()}
    contract = _dict(cut.get("cut_contract"))
    source_contract = _dict(contract.get("source_event_contract"))
    primary_id = _as_str(source_contract.get("primary_event_beat_id"))
    source_ids = _as_str_list(source_contract.get("source_event_beat_ids"))
    if primary_id and primary_id not in source_ids:
        source_ids = [primary_id, *source_ids]
    primary_beat = by_id.get(primary_id) if primary_id else None
    neighbor_ids: set[str] = set()
    for source_id in source_ids:
        for index, beat in enumerate(sequence):
            if str(beat.get("beat_id") or "").strip() != source_id:
                continue
            for neighbor_index in (index - 1, index + 1):
                if 0 <= neighbor_index < len(sequence):
                    neighbor_id = str(sequence[neighbor_index].get("beat_id") or "").strip()
                    if neighbor_id and neighbor_id not in source_ids:
                        neighbor_ids.add(neighbor_id)
    reveal_constraints = _dict(contract.get("viewer_contract")).get("reveal_constraints")
    if not reveal_constraints:
        reveal_constraints = _dict(scene.get("scene_intent")).get("reveal_constraints")
    return {
        "derived_from": ["scene_event.event_sequence[]", "cut_contract.source_event_contract"],
        "editable": False,
        "primary_event_beat": primary_beat or {},
        "source_event_beats": [by_id[source_id] for source_id in source_ids if source_id in by_id],
        "neighboring_event_beats": [by_id[beat_id] for beat_id in sorted(neighbor_ids) if beat_id in by_id],
        "forbidden_event_changes": _as_str_list(scene_event.get("forbidden_event_changes")),
        "reveal_constraints_for_this_cut": reveal_constraints if isinstance(reveal_constraints, list) else _as_str_list(reveal_constraints),
    }


def semantic_contract_missing(contract: dict[str, Any]) -> bool:
    return bool(missing_contract_fields(contract))


def missing_contract_fields(contract: dict[str, Any]) -> list[str]:
    required = ("target_focus", "must_include", "done_when")
    return [key for key in required if contract.get(key) in ("", [], {})]


def normalize_final_output_provenance(
    *,
    output: str,
    output_path: Path,
    provenance: dict[str, Any] | None,
) -> dict[str, Any]:
    provenance = provenance or {}
    return {
        "declared_output": output,
        "resolved_output_path": output_path.as_posix(),
        "output_exists": output_path.exists() and output_path.is_file(),
        "saved_path": _as_str(provenance.get("savedPath")),
        "source": _as_str(provenance.get("source")),
        "status": _as_str(provenance.get("status")),
        "debug_log": _as_str(provenance.get("debug_log")),
    }


def discover_contact_sheet_refs(run_dir: Path) -> list[str]:
    candidates = [
        run_dir / "logs" / "review" / "semantic" / "scene_image.contact_sheet.md",
        run_dir / "logs" / "review" / "semantic" / "scene_image.contact_sheet.png",
        run_dir / "logs" / "review" / "semantic" / "scene_image.samples.json",
        run_dir / "logs" / "review" / "scene_image.contact_sheet.md",
        run_dir / "logs" / "review" / "scene_image.contact_sheet.png",
        run_dir / "logs" / "review" / "scene_image.samples.json",
    ]
    refs: list[str] = []
    for path in candidates:
        if path.exists():
            refs.append(_relpath(run_dir, path))
    return refs


def image_generation_provenance_by_destination(run_dir: Path) -> dict[str, dict[str, Any]]:
    by_destination: dict[str, dict[str, Any]] = {}
    for log_dir in (run_dir / "logs" / "app_server" / "image_gen", run_dir / "logs" / "app_server" / "request_item_generation"):
        if not log_dir.exists():
            continue
        for path in sorted(log_dir.glob("*.json")):
            record = load_json(path)
            if not isinstance(record, dict):
                continue
            destination = _as_str(record.get("destination"))
            response = _dict(record.get("response"))
            request = _dict(record.get("request"))
            if not destination:
                destination = _as_str(request.get("output"))
            if not destination:
                continue
            payload = {
                "debug_log": _relpath(run_dir, path),
                "savedPath": _as_str(record.get("savedPath") or response.get("savedPath")),
                "source": _as_str(record.get("source") or response.get("source")),
                "status": _as_str(record.get("status") or response.get("status")),
            }
            by_destination[destination] = payload
            by_destination[resolve_run_path(run_dir, destination).as_posix()] = payload
    return by_destination


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def resolve_run_path(run_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (run_dir / path).resolve()


def _relpath(run_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(run_dir.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    return default


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _coverage_minimum_cut_count(plan: dict[str, Any]) -> int:
    if not isinstance(plan, dict):
        return 2
    direct = _as_int(plan.get("minimum_cut_count"))
    if direct:
        return direct
    min_cut_count = _dict(plan.get("min_cut_count"))
    selected = _as_int(min_cut_count.get("selected"))
    if selected:
        return selected
    by_importance = _as_int(min_cut_count.get("by_importance"))
    by_duration = _as_int(min_cut_count.get("by_duration"))
    return max(by_importance, by_duration, 2)


def _audience_knowledge_items(scene_intent: dict[str, Any]) -> list[str]:
    delta = _dict(scene_intent.get("audience_knowledge_delta"))
    items: list[str] = []
    for key in ("before_scene", "learned_during_scene", "misdirected_or_reframed", "still_unknown_after_scene", "forbidden_early_reveals"):
        items.extend(_as_str_list(delta.get(key)))
    items.extend(_as_str_list(scene_intent.get("audience_knowledge_plan")))
    return list(dict.fromkeys(item for item in items if item))
