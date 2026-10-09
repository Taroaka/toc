from copy import deepcopy

import pytest

from test_source_first_scene_projection import setup_profile


@pytest.mark.parametrize('actions', [
    ['修理工が蓋を開く', '修理工が歯車を外す', '修理工が蓋を閉じる'],
    ['船員が帆をほどく', '船員が帆を張る', '船員が索を結ぶ'],
])
def test_cut_plan_keeps_each_authored_beat_and_research_id(tmp_path, actions):
    m, profile, story, _ = setup_profile(tmp_path)
    scene = profile['story_scenes'][0]
    original = deepcopy(scene['event_sequence'][0])
    original.pop('cut_transitions', None)
    scene['event_sequence'] = [dict(original, beat_id=f'b{i}', beat_function='action',
        what_happens=action, visible_action=action, source_event_ids=[f'E{i}'],
        first_frame_brief=f'{action}直前の手元', motion_brief=action,
        motion_end_state=f'{action}後の手元') for i, action in enumerate(actions)]
    event = m._scene_event_for_cut_design(title='作業', idx=1, scene_intent={},
        location_name='作業場', profile=profile, include_artifact=False)
    plan = m._scene_cut_coverage_plan(title='作業', idx=1, scene_intent={},
        scene_event=event, location_name='作業場', profile=profile, include_artifact=False)
    assert [c['primary_event_beat_id'] for c in plan['cuts']] == ['b0', 'b1', 'b2']
    assert [c['motion_brief'] for c in plan['cuts']] == actions
    assert [c['source_event_ids'] for c in plan['cuts']] == [['E0'], ['E1'], ['E2']]
    assert [c['first_frame_brief'] for c in plan['cuts']] == [f'{a}直前の手元' for a in actions]


def test_explicit_subdivisions_keep_transition_identity_and_optional_beats(tmp_path):
    m, profile, _, _ = setup_profile(tmp_path)
    scene = profile['story_scenes'][0]
    beat = scene['event_sequence'][0]
    beat['cut_transitions'] = [dict(transition_id=f't{i}',
        first_frame_brief=f'状態{i}', motion_brief=f'動作{i}', motion_end_state=f'状態{i+1}')
        for i in range(2)]
    scene['event_sequence'].append(dict(deepcopy(beat), beat_id='offscreen', must_be_seen=False))
    event = m._scene_event_for_cut_design(title='作業', idx=1, scene_intent={},
        location_name='作業場', profile=profile, include_artifact=False)
    plan = m._scene_cut_coverage_plan(title='作業', idx=1, scene_intent={},
        scene_event=event, location_name='作業場', profile=profile, include_artifact=False)
    assert [c['source_transition_id'] for c in plan['cuts']] == ['t0', 't1']
    assert plan['coverage_plan']['event_beat_inventory'][-1]['assigned_cut_ids'] == []
    assert plan['coverage_plan']['event_beat_inventory'][-1]['must_be_seen'] is False


def test_research_ids_survive_duplicate_event_text(tmp_path):
    m, profile, _, _ = setup_profile(tmp_path)
    research = {'story_materials': {'chronological_events': [
        {'event_id': 'first', 'event': '扉を閉める'},
        {'event_id': 'second', 'event': '扉を閉める'},
    ]}}
    projected = m._profile_from_research(profile, research)
    assert projected['research_event_ids'] == ['first', 'second']
    assert [e['event_id'] for e in m._scene_acceptance_source_ledger(projected)['events']] == ['first', 'second']


def test_final_contract_preserves_research_and_transition_ids(tmp_path):
    m, profile, story, _ = setup_profile(tmp_path)
    script, manifest, _ = m._build_script_and_manifest('作業', tmp_path, '2026-09-26', profile)
    for document in (script, manifest):
        for scene, authored in zip(document['scenes'], story['script']['scenes']):
            beat = authored['event_sequence'][0]
            for cut, transition in zip(scene['cuts'], beat['cut_transitions'], strict=True):
                contract = cut['cut_contract']['source_event_contract']
                assert contract['source_event_ids'] == beat['source_event_ids']
                assert contract['source_transition_id'] == transition['transition_id']
                assert contract['primary_event_beat_id'] == beat['beat_id']
                assert cut['cut_contract']['first_frame_contract']['first_frame_brief'] == transition['first_frame_brief']


def test_coverage_matrix_uses_explicit_beat_sources_even_when_text_is_identical(tmp_path):
    m, profile, _, _ = setup_profile(tmp_path)
    profile['events'] = ['扉を閉める', '扉を閉める']
    profile['research_event_ids'] = ['first', 'second']
    scenes = [dict(scene_id=10, scene_event={'event_sequence': [
        dict(beat_id='a', source_event_ids=['first']),
        dict(beat_id='b', source_event_ids=['second']),
    ]})]
    matrix = m._canonical_event_coverage_matrix(profile, scenes)
    assert [(r['source_event_id'], r['assigned_event_beat_ids'])
            for r in matrix['source_story_events']] == [('first', ['a']), ('second', ['b'])]
    scenes[0]['scene_event']['event_sequence'].pop()
    with pytest.raises(ValueError, match='no authored beat'):
        m._canonical_event_coverage_matrix(profile, scenes)


@pytest.mark.parametrize('transitions', [[], [None], [{'transition_id': 'x'}]])
def test_invalid_subdivisions_are_not_silently_filled(tmp_path, transitions):
    from toc.authored_cut_projection import authored_cut_plan
    with pytest.raises(ValueError, match='transition'):
        authored_cut_plan({'event_sequence': [dict(beat_id='a', source_event_ids=['E1'], cut_transitions=transitions)]},
                          scene_id=10, location_name='工房', protagonist='修理工')


@pytest.mark.parametrize('source_ids', [None, [], 'E1', ['E1', 'E1'], ['']])
def test_cut_cannot_lose_research_identity(source_ids):
    from toc.authored_cut_projection import authored_cut_plan
    with pytest.raises(ValueError, match='source_event_ids'):
        authored_cut_plan({'event_sequence': [dict(beat_id='a', source_event_ids=source_ids)]},
                          scene_id=10, location_name='工房', protagonist='修理工')


def test_custom_beat_functions_keep_future_boundaries(tmp_path):
    m, profile, _, _ = setup_profile(tmp_path)
    scene = profile['story_scenes'][0]
    original = deepcopy(scene['event_sequence'][0])
    original.pop('cut_transitions', None)
    scene['event_sequence'] = [dict(original, beat_id=f'b{i}', beat_function='observe',
        first_frame_brief=f'状態{i}', motion_brief=f'動作{i}', motion_end_state=f'状態{i+1}')
        for i in range(3)]
    event = m._scene_event_for_cut_design(title='観察', idx=1, scene_intent={},
        location_name='工房', profile=profile, include_artifact=False)
    plan = m._scene_cut_coverage_plan(title='観察', idx=1, scene_intent={},
        scene_event=event, location_name='工房', profile=profile, include_artifact=False)
    progression = m._scene_state_progression_plan_for_scaffold(scene_id=10,
        title='観察', scene_intent={}, scene_event=event, cut_plans=plan['cuts'], location_name='工房')
    assert progression['progression_mode'] == 'sequential_state_progression'
    assert progression['cut_progression_map'][0]['forbidden_future_event_beat_ids'] == ['b1', 'b2']
