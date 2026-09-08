from __future__ import annotations

import re
import importlib.util
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_FILES = (
    "scripts/toc-immersive-frontend-run.py",
    "scripts/build-semantic-review-pack.py",
    "scripts/review-image-prompt-story-consistency.py",
    "toc/scene_acceptance_contract.py",
)
FORBIDDEN_STORY_TOKENS = re.compile(
    r"cinderella|cendrillon|シンデレラ|灰かぶり|ガラスの靴|"
    r"TOC_ENABLE_LEGACY_CINDERELLA_PROFILE|\bslipper\b|"
    r"protagonist_transformed_asset_id|protagonist_post_midnight_asset_id|"
    r"dance_partner|pumpkin|fairy|stepmother|stepsister|prince|royal_envoy|"
    r"舞踏会|馬車|継母|義姉|王子|使者",
    flags=re.IGNORECASE,
)


def _authored_story_from_research(
    module: Any,
    *,
    topic: str,
    research: dict[str, Any],
    profile: dict[str, Any],
    target_duration_seconds: int,
) -> dict[str, Any]:
    """Return a small, rich Story Author fixture for downstream contracts.

    This test double deliberately models the LLM boundary: every research
    event owns one semantic scene, and the scene carries lifecycle, source,
    and handoff fields.  It keeps this contract test independent of the
    removed deterministic prose builder while exercising the same profile and
    cut/manifest projection used by an authored ``story.md``.
    """

    materials = research.get("story_materials") or {}
    events = [
        event
        for event in materials.get("chronological_events", [])
        if isinstance(event, dict) and str(event.get("event") or "").strip()
    ]
    assert events, "research fixture must contain chronological events"
    setting = materials.get("setting") if isinstance(materials.get("setting"), dict) else {}
    raw_places = setting.get("places") if isinstance(setting.get("places"), list) else []
    places: list[str] = []
    for place in raw_places:
        value = (
            str(place.get("name") or place.get("place_id") or "").strip()
            if isinstance(place, dict)
            else str(place).strip()
        )
        if value:
            places.append(value)
    if not places:
        places = ["物語の場所"]
    scene_base, scene_remainder = divmod(target_duration_seconds, len(events))
    narration_total = int(target_duration_seconds * 0.7)
    narration_base, narration_remainder = divmod(narration_total, len(events))
    scenes: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        event_id = str(event.get("event_id") or f"E{index:02d}").strip()
        event_text = str(event["event"]).strip()
        scene_id = f"scene_{index:02d}"
        start_state = "state_story_start" if index == 1 else f"state_after_scene_{index - 1:02d}"
        end_state = f"state_after_scene_{index:02d}"
        location = places[min(index - 1, len(places) - 1)]
        scene_title = event_text
        beat_id = f"{scene_id}_beat_01"
        scenes.append(
            {
                "scene_id": scene_id,
                "semantic_scene_responsibility_id": scene_id,
                "canonical_scene_index": index,
                "title": scene_title,
                "phase": "opening" if index == 1 else "ending" if index == len(events) else "development",
                "purpose": event_text,
                "conflict": f"{location}の制約が、{event_text}の選択を遅らせる。",
                "turn": event_text,
                "affect": {"label_hint": "tension", "audience_job": "follow_causality"},
                "visualizable_action": event_text,
                "grounding_note": f"reviewed research event {event_id}",
                "source_basis": {"event_ids": [event_id]},
                "research_refs": [
                    f"research.story_materials.chronological_events[{event_id}]"
                ],
                "location": {
                    "name": location,
                    "sequence": [location],
                    "segments": [],
                },
                "time_of_day": "昼",
                "time_of_day_visual_basis": (
                    f"光源: {location}の自然光。明るさ: 中間調。"
                    "影: 人物の足元に柔らかく落ちる。色温度: 5200K。"
                ),
                "target_duration_seconds": scene_base + (1 if index <= scene_remainder else 0),
                "narration_target_seconds": narration_base + (1 if index <= narration_remainder else 0),
                "scene_intent": {
                    "story_purpose": event_text,
                    "dramatic_question": f"{event_text}は次の原因になり得るか",
                    "value_shift": {"from": start_state, "to": end_state},
                    "causal_turn": event_text,
                },
                "start_state": {"state_id": start_state},
                "event_sequence": [
                    {
                        "beat_id": beat_id,
                        "beat_function": "source_event",
                        "source_event_ids": [event_id],
                        "what_happens": event_text,
                        "immediate_consequence": end_state,
                        "required_visual_evidence": [event_text, location],
                    }
                ],
                "turning_event": {
                    "beat_id": beat_id,
                    "irreversible_change": event_text,
                },
                "end_state": {"state_id": end_state},
                "handoff_chain": {
                    "incoming": {
                        "producer_scene_id": f"scene_{index - 1:02d}" if index > 1 else "",
                        "state_id": start_state,
                    },
                    "outgoing": {
                        "consumer_scene_id": f"scene_{index + 1:02d}" if index < len(events) else "",
                        "state_id": end_state,
                    },
                },
                "preservation": {"must_preserve": [event_text], "must_not_show": []},
            }
        )
    return {
        "story_metadata": {
            "scene_authoring_contract": "story_scene_contract_v1",
            "topic": topic,
            "time": str(setting.get("time_or_era") or "").strip(),
            "target_duration_seconds": target_duration_seconds,
            "scene_time_of_day_contract": "required_v1",
            "scene_time_of_day_visual_basis_contract": "required_v1",
            "adaptation_value_contract": "required_v1",
        },
        "adaptation_source_contract": module._adaptation_source_contract_for_profile(profile),
        "selection": {"chosen_candidate_id": "test_grounded"},
        "script": {"scenes": scenes},
    }


def test_production_code_contains_no_cinderella_specific_reinforcement() -> None:
    findings: list[str] = []
    for relative_path in PRODUCTION_FILES:
        path = REPO_ROOT / relative_path
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if FORBIDDEN_STORY_TOKENS.search(line):
                findings.append(f"{relative_path}:{line_number}: {line.strip()}")
    assert not findings, "\n".join(findings[:100])


def test_distinct_story_inputs_use_the_same_generic_profile_contract() -> None:
    path = REPO_ROOT / "scripts/toc-immersive-frontend-run.py"
    spec = importlib.util.spec_from_file_location(
        "story_neutral_frontend_runner",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    first = module._story_profile(
        "海辺の旅人",
        "旅人が失われた灯台を探す物語",
        variant_seed="story-a",
    )
    second = module._story_profile(
        "山の守り手",
        "守り手が崩れた橋を渡る物語",
        variant_seed="story-b",
    )

    assert set(first) == set(second)
    assert first["slug"] != second["slug"]
    assert first["topic_label"] == "海辺の旅人"
    assert second["topic_label"] == "山の守り手"
    assert "story_key" not in first
    assert "story_key" not in second


def test_generic_location_anchors_do_not_embed_scene_time_variants() -> None:
    path = REPO_ROOT / "scripts/toc-immersive-frontend-run.py"
    spec = importlib.util.spec_from_file_location(
        "story_neutral_location_runner",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    time_tokens = re.compile(r"夜|朝|昼|夕|黄昏|月光|月明かり")
    for variant in module.RUN_VARIANTS:
        assert not any(
            time_tokens.search(str(place))
            for place in variant["places"]
        ), variant


def test_two_generic_stories_keep_scene_cut_and_first_frame_contracts() -> None:
    path = REPO_ROOT / "scripts/toc-immersive-frontend-run.py"
    spec = importlib.util.spec_from_file_location(
        "story_neutral_contract_runner",
        path,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    for title, source, seed in (
        ("海辺の旅人", "旅人が失われた灯台を探す物語", "contract-a"),
        ("山の守り手", "守り手が崩れた橋を渡る物語", "contract-b"),
    ):
        with tempfile.TemporaryDirectory(
            prefix="story_neutral_contract_",
        ) as tmp:
            run_dir = Path(tmp)
            now = "2099-01-01T00:00:00+09:00"
            profile = module._duration_aware_profile(
                module._story_profile(title, source, seed),
                target_duration_seconds=300,
            )
            research = module._build_research(
                title,
                run_dir,
                now,
                profile,
            )
            profile = module._profile_from_reviewed_research(
                profile,
                research,
            )
            story = _authored_story_from_research(
                module,
                topic=title,
                research=research,
                profile=profile,
                target_duration_seconds=300,
            )
            profile = module._profile_from_reviewed_story(profile, story)
            script, manifest, selectors = module._build_script_and_manifest(
                title,
                run_dir,
                now,
                profile,
            )
        assert selectors
        assert len(script["scenes"]) == len(manifest["scenes"])
        for script_scene, manifest_scene in zip(
            script["scenes"],
            manifest["scenes"],
            strict=True,
        ):
            assert script_scene["scene_event"]["event_sequence"]
            assert script_scene["scene_cut_coverage_plan"]["cut_assignments"]
            assert script_scene["cuts"]
            assert len(script_scene["cuts"]) == len(manifest_scene["cuts"])
            for cut in manifest_scene["cuts"]:
                contract = cut["cut_contract"]
                first_frame = contract["first_frame_contract"]
                assert first_frame["event_fact_visible_in_still"]
                assert first_frame["first_frame_brief"]
                assert contract["motion_contract"]["motion_brief"]
                assert contract["source_event_contract"]["primary_event_beat_id"]
                prompt = cut["image_generation"]["api_prompt_payload"]["prompt"]
                assert prompt
                assert str(cut["selector"]) not in prompt
