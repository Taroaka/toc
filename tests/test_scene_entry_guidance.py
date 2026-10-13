import asyncio
import json
from types import SimpleNamespace

import pytest

from toc.p400_authoring import build_direction_prompt
from test_p400_cinematic_author import sample


@pytest.mark.parametrize('repair', [None, {'errors': ['source_state_mismatch']}])
def test_direction_author_receives_scene_entry_guidance_on_initial_and_repair(tmp_path, repair):
    from toc.scene_entry_guidance import SCENE_ENTRY_GUIDANCE

    story, sources, resources, rows = sample(tmp_path)
    prompt = build_direction_prompt(
        sources=sources, resources=resources, scene=story['script']['scenes'][1],
        previous=rows[0], grounding='', repair=repair,
    )
    assert SCENE_ENTRY_GUIDANCE in prompt


def test_story_guidance_carries_scene_entry_policy_into_existing_author_routes():
    from toc.scene_entry_guidance import SCENE_ENTRY_GUIDANCE
    from toc.story_authoring import AUDIENCE_MEANING_INSTRUCTION

    # Existing pipeline integration tests verify this shared instruction reaches
    # architecture, scene authors and field repair calls.
    assert SCENE_ENTRY_GUIDANCE in AUDIENCE_MEANING_INSTRUCTION


@pytest.mark.parametrize('old_policy', [None, 'direction_author_policy_v3_state_asset_result_frame'])
def test_stale_handoff_is_reauthored_under_current_policy(tmp_path, monkeypatch, old_policy):
    import toc.p400_authoring as authoring
    from toc.scene_entry_guidance import SCENE_ENTRY_GUIDANCE

    _, sources, resources, rows = sample(tmp_path)
    old = authoring.bind_direction(rows, sources, resources)
    old['metadata']['author_policy'] = old_policy
    handoff = {'previous_output': {authoring.ARTIFACT: json.dumps(old)},
               'errors': ['old handoff diagnostic']}
    monkeypatch.setattr(authoring, 'handoff_session', lambda *args: SimpleNamespace(pending=lambda unit: handoff))
    calls = []

    async def turn(**kwargs):
        row = rows[len(calls)]
        calls.append(kwargs['prompt'])
        return SimpleNamespace(payload={'result_json': json.dumps(row)}, transcript=(),
                               provenance=SimpleNamespace(as_dict=lambda: {}))

    result = asyncio.run(authoring.author_cinematic_direction(
        run_dir=tmp_path, resources=resources, grounding='', client_factory=lambda: None,
        turn_runner=turn,
    ))
    assert len(calls) == len(rows)
    assert all(SCENE_ENTRY_GUIDANCE in prompt for prompt in calls)
    assert result['metadata']['author_policy'] == authoring.DIRECTION_AUTHOR_POLICY
