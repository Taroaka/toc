"""Ensure isolated author turns receive the causal design requirement."""
import json

from toc.story_authoring import build_research_registry, build_story_architect_prompt
from toc.story_author_pipeline import (
    build_scene_author_prompt, build_scene_batch_author_prompt, _build_repair_prompt,
)


def test_causal_reason_reaches_every_author_and_repair():
    registry = build_research_registry({})
    plan = {
        "scene_id": "scene_02", "previous_scene_id": "scene_01",
        "causal_connection_from_previous": "前の発見によって次の調査が必要になる",
    }
    prompts = [
        build_story_architect_prompt(registry),
        build_scene_author_prompt(registry, plan),
        build_scene_batch_author_prompt(registry, [plan]),
        _build_repair_prompt(validation_errors=[], current_story={}, scene_id="scene_02",
                             scene_plan=plan, registry=registry, source_digest="", topic="",
                             target_duration_seconds=None),
    ]
    for prompt in prompts:
        payload = json.loads(prompt)
        instructions = " ".join(payload["instructions"])
        assert "causal_connection_from_previous" in instructions
        assert "なぜなら" in instructions
        assert "そしてそれから" in instructions
        assert "first scene" in instructions
        assert "Do not invent" in instructions
    for prompt in prompts[1:]:
        assert plan["causal_connection_from_previous"] in prompt
