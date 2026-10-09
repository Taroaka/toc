from copy import deepcopy
import asyncio
import json
from types import SimpleNamespace

import pytest

from toc.cinematic_language import execution_from_cut
from toc.p400_authoring import build_direction_prompt
from toc.p400_projection import project_scene
from toc.video_prompt_compiler import compile_video_api_prompt_v1
from test_p400_cinematic_author import sample


def staging():
    return {
        'first_frame_requirements': ['取っ手と支える手の間に空間がある'],
        'action_sequence': ['修理工が取っ手へ手を伸ばす', '接触してから一度だけ引く'],
        'end_behavior': {'mode': 'continue', 'description': '引く動きが続いている途中で終える'},
        'continuity_rules': ['箱は一つのままで増殖しない'],
    }


@pytest.mark.parametrize('subject', ['修理工', '配達人'])
def test_staging_reaches_still_and_motion_at_the_correct_boundary(tmp_path, subject):
    story, _, resources, scenes = sample(tmp_path)
    resources['characters']['keeper']['name'] = subject
    block = staging()
    block['action_sequence'][0] = f'{subject}が取っ手へ手を伸ばす'
    scenes[0]['cuts'][0]['execution'] = {'staging': block}
    _, manifest = project_scene(scenes[0], source_scene=story['script']['scenes'][0], scene_id=10,
        resources=resources, scene_intent={}, scene_event=story['script']['scenes'][0],
        scene_generation={}, acceptance_draft={}, acceptance_binding={})
    cut = manifest['cuts'][0]
    still = cut['image_generation']['api_prompt_payload']['prompt']
    payload = compile_video_api_prompt_v1(cut_contract=cut['cut_contract'],
        tool='kling_3_0', first_frame='assets/scenes/start.png', duration_seconds=8)
    motion = payload['prompt']
    assert block['first_frame_requirements'][0] in still
    for step in block['action_sequence']:
        assert step in motion
        assert step not in still
    assert motion.index(block['action_sequence'][0]) < motion.index(block['action_sequence'][1])
    assert block['end_behavior']['description'] in motion
    assert block['end_behavior']['description'] not in still
    assert block['continuity_rules'][0] in motion
    changed = deepcopy(cut['cut_contract'])
    changed['cinematic_contract']['execution']['staging']['end_behavior']['description'] = '取っ手を引き続ける'
    changed_payload = compile_video_api_prompt_v1(cut_contract=changed,
        tool='kling_3_0', first_frame='assets/scenes/start.png', duration_seconds=8)
    assert changed_payload['source_digest'] != payload['source_digest']


@pytest.mark.parametrize('field,value', [
    ('action_sequence', 'not-a-list'), ('action_sequence', []),
    ('first_frame_requirements', ['']), ('continuity_rules', [42]),
    ('end_behavior', {'mode': 'loop', 'description': 'repeat'}),
    ('end_behavior', {'mode': 'hold', 'description': ''}),
])
def test_malformed_staging_is_rejected(field, value):
    block = staging(); block[field] = value
    with pytest.raises(ValueError, match='staging'):
        execution_from_cut({'execution': {'staging': block}})


def test_legacy_execution_is_unchanged():
    assert 'staging' not in execution_from_cut({'execution': {}})


def test_person_staging_cannot_enter_unpeopled_sub_cut():
    with pytest.raises(ValueError, match='unpeopled_staging'):
        execution_from_cut({'cut_role': 'sub', 'execution': {'staging': staging()}})


def test_story_authors_supply_source_bound_transformation_permissions():
    from toc.story_author_pipeline import build_scene_author_prompt, build_scene_batch_author_prompt
    plan = {'scene_id': 'workshop', 'source_event_ids': []}
    for prompt in [build_scene_author_prompt({}, plan), build_scene_batch_author_prompt({}, [plan])]:
        assert 'allowed_new_reveal_elements' in prompt
        assert 'Do not invent' in prompt


def test_initial_author_prompt_requests_staging_without_a_second_review_pass(tmp_path):
    story, sources, resources, _ = sample(tmp_path)
    prompt = build_direction_prompt(sources=sources, resources=resources,
        scene=story['script']['scenes'][0], previous=None, grounding='')
    for field in ['first_frame_requirements', 'action_sequence', 'end_behavior', 'continuity_rules']:
        assert field in prompt
    assert 'allowed_new_reveal_elements' in prompt


def test_author_policy_change_does_not_reuse_old_cached_direction(tmp_path, monkeypatch):
    import toc.p400_authoring as authoring
    _, _, resources, scenes = sample(tmp_path)
    calls = []

    async def turn(**kwargs):
        row = scenes[len(calls) % len(scenes)]
        calls.append(kwargs['prompt'])
        return SimpleNamespace(payload={'result_json': json.dumps(row)}, transcript=(),
            provenance=SimpleNamespace(as_dict=lambda: {}))

    def run():
        return asyncio.run(authoring.author_cinematic_direction(run_dir=tmp_path,
            resources=resources, grounding='', client_factory=lambda: None, turn_runner=turn))

    first = run()
    assert len(calls) == 2
    assert run() == first
    assert len(calls) == 2
    monkeypatch.setattr(authoring, 'DIRECTION_AUTHOR_POLICY', 'different-author-policy')
    refreshed = run()
    assert len(calls) == 4
    assert refreshed['metadata']['author_policy'] == 'different-author-policy'
