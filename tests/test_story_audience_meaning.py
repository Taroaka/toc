"""The optional authoring guidance must reach every direct Story author turn."""

from copy import deepcopy
import json

import pytest

from toc.story_authoring import (
    AUDIENCE_MEANING_INSTRUCTION,
    build_research_registry,
    build_story_architect_prompt,
)
from toc.story_author_pipeline import (
    _build_repair_prompt,
    build_scene_author_prompt,
    build_scene_batch_author_prompt,
)


@pytest.mark.parametrize(
    "event,interpretation",
    [
        ("話し合いは結論を出さずに終わる。", "対立する解釈が残る。"),
        ("共同作業を終え、それぞれの日常に戻る。", "変わらない関係への理解が深まる。"),
    ],
    ids=["unresolved", "unchanged"],
)
def test_guidance_reaches_all_turns_without_mutating_source_or_plan(
    event: str, interpretation: str
) -> None:
    research = {
        "story_materials": {
            "chronological_events": [{"event_id": "E1", "event": event}],
            "symbols_and_themes": [],
        },
        "source_passages": [{"passage_id": "P1", "passage": interpretation}],
    }
    registry = build_research_registry(research)
    plan = {
        "scene_id": "scene_01",
        "title": event,
        "source_event_ids": ["E1"],
        "previous_scene_id": None,
        "next_scene_id": None,
        "incoming_state_id": "state_01",
        "outgoing_state_id": "state_02",
        "causal_connection_from_previous": None,
    }
    story = {"script": {"scenes": [{"scene_id": "scene_01"}]}}
    original = deepcopy((research, registry, plan, story))
    prompts = [
        build_story_architect_prompt(registry),
        build_scene_author_prompt(registry, plan),
        build_scene_batch_author_prompt(registry, [plan]),
        _build_repair_prompt(
            validation_errors=["story.scene_time_of_day_visual_basis_invalid"],
            current_story=story,
            scene_id="scene_01",
            scene_plan=plan,
            registry=registry,
            source_digest="source-digest",
            topic="",
            target_duration_seconds=None,
        ),
    ]

    payloads = [json.loads(prompt) for prompt in prompts]
    for payload in payloads:
        assert payload["instructions"].count(AUDIENCE_MEANING_INSTRUCTION) == 1
        assert payload["research_registry"]["raw_research"] == research
    assert payloads[1]["scene_plan"] == plan
    assert payloads[2]["scene_plans"] == [plan]
    assert payloads[3]["failing_scene_plan"] == plan
    assert payloads[3]["current_story"] == story
    assert (research, registry, plan, story) == original
