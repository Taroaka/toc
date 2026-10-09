import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from toc.p400_authoring import (
    author_cinematic_direction, bind_direction, validate_direction, load_direction,
    build_direction_prompt,
)


def sample(tmp_path):
    story = {'script': {'scenes': [
        {'scene_id': 'quiet', 'target_duration_seconds': 15, 'location': {'name': '工房'},
         'start_state': {'state_id': 'start'}, 'end_state': {'state_id': 'quiet-end'},
         'event_sequence': [{'beat_id': 'open', 'what_happens': '箱を開ける', 'source_event_ids': ['E1']},
                            {'beat_id': 'wait', 'what_happens': '返事を待つ', 'source_event_ids': ['E2']}]},
        {'scene_id': 'leave', 'target_duration_seconds': 8, 'location': {'name': '工房'},
         'start_state': {'state_id': 'quiet-end'}, 'end_state': {'state_id': 'leave-end'},
         'event_sequence': [{'beat_id': 'exit', 'what_happens': '箱を残す', 'source_event_ids': ['E3']}]},
    ]}}
    sources = {'research': b'{}', 'story': json.dumps(story, ensure_ascii=False).encode(), 'visual_value': b'{}'}
    for name, raw in sources.items():
        (tmp_path / f'{name}.md').write_bytes(raw)
    resources = {'characters': {'keeper': {'name': '修理工', 'references': ['assets/characters/keeper.png']}},
                 'objects': {}, 'locations': {'shop': {'name': '工房', 'references': ['assets/locations/shop.png']}}}
    def cut(cid, beats, duration, before, after, previous=''):
        return dict(cut_id=cid, event_time_position='consequence' if previous else 'before_trigger',
            progression_mode='suspended_moment', start_state_id={'a': 'start', 'b': 'a-end', 'c': 'quiet-end'}[cid],
            end_state_id={'a': 'a-end', 'b': 'quiet-end', 'c': 'leave-end'}[cid], source_beat_ids=beats, primary_beat_id=beats[0],
            cut_role='main', cut_function='observation', purpose='返事のない時間を観客にも経験させる',
            duration_seconds=duration, duration_reason='返事を待つ間を保持する',
            location_id='shop', character_ids=['keeper'], object_ids=[], primary_subject='修理工',
            start_state_facts={'場面': before}, end_state_facts={'場面': after}, visible_state_keys=['場面'],
            first_frame_brief=before, motion_brief='修理工は箱の前で待ち続ける', motion_end_state=after,
            camera={'framing': '腰上の固定画', 'movement': 'static', 'composition': '人物を画面端へ寄せる',
                    'light': '既存の窓からの光', 'focus': '人物と箱'},
            narration='', narration_role='silent', silence_reason='返事のなさを説明で埋めない', audio_intent='工房の環境音を続ける',
            edit_reason='待つ時間を残してから切る', continuity={'previous_cut_id': previous, 'previous_end_state': before,
                'mode': 'continuous' if previous else 'scene_entry', 'connection': '同じ場所で時間が続く'}, allowed_reveal_info_ids=[],
            allowed_new_reveal_elements=[])
    first = {'asset_requests': [], 'scene_id': 'quiet', 'direction': '和解を断定せず観察する', 'visual_plan_application': 'p300の静けさを長い保持へ具体化',
             'entry_connection': '前場面の作業音を受ける', 'exit_connection': '箱を残す行為へつなぐ',
             'cuts': [cut('a', ['open'], 4, '閉じた箱の前にいる', '箱が開いている'),
                      cut('b', ['wait'], 11, '箱が開いている', '箱を開けたまま待つ', 'a')]}
    second = {'asset_requests': [], 'scene_id': 'leave', 'direction': '理由を確定せず終える', 'visual_plan_application': '既存の箱を残す',
              'entry_connection': '前sceneの終了状態から続ける', 'exit_connection': '返事のないまま終える',
              'cuts': [cut('c', ['exit'], 8, '箱を開けたまま待つ', '箱だけが残る')]}
    return story, sources, resources, [first, second]


def test_author_keeps_full_context_unequal_timing_and_adjacent_scene(tmp_path):
    story, sources, resources, scenes = sample(tmp_path)
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs['prompt'])
        return SimpleNamespace(payload={'result_json': json.dumps(scenes[len(calls)-1])}, transcript=(),
                               provenance=SimpleNamespace(as_dict=lambda: {'model': 'stub'}))
    result = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='rules',
        client_factory=lambda: None, turn_runner=turn))
    assert len(calls) == 2
    assert json.dumps(sources['story'].decode(), ensure_ascii=False) in calls[0]
    assert '箱を開けたまま待つ' in calls[1]
    assert [c['duration_seconds'] for c in result['scenes'][0]['cuts']] == [4, 11]
    assert load_direction(tmp_path)['scenes'] == scenes


@pytest.mark.parametrize('fault', ['missing_beat', 'unknown_asset', 'duplicate_cut', 'duration', 'continuity', 'reveal', 'unknown_version'])
def test_invalid_direction_has_actionable_errors(tmp_path, fault):
    story, sources, resources, scenes = sample(tmp_path)
    doc = bind_direction(scenes, sources, resources)
    row = doc['scenes'][0]
    if fault == 'missing_beat': row['cuts'][1]['source_beat_ids'] = ['open']
    if fault == 'unknown_asset': row['cuts'][0]['character_ids'] = ['invented']
    if fault == 'duplicate_cut': row['cuts'][1]['cut_id'] = 'a'
    if fault == 'duration': row['cuts'][0]['duration_seconds'] = 60
    if fault == 'continuity': row['cuts'][1]['continuity']['previous_end_state'] = '閉じている'
    if fault == 'reveal': row['cuts'][0]['allowed_reveal_info_ids'] = ['future-secret']
    if fault == 'unknown_version': doc['metadata']['contract'] = 'future'
    assert validate_direction(doc, story, resources)


def test_repair_is_author_owned_and_does_not_replace_previous_on_failure(tmp_path):
    story, sources, resources, scenes = sample(tmp_path)
    previous = tmp_path / 'cinematic_direction.json'
    previous.write_text('previous')
    calls = []
    async def bad(**kwargs):
        calls.append(kwargs['prompt'])
        result = deepcopy(scenes[0]); result['cuts'][0]['duration_seconds'] = 0
        return SimpleNamespace(payload={'result_json': json.dumps(result)}, transcript=(),
                               provenance=SimpleNamespace(as_dict=lambda: {}))
    with pytest.raises(RuntimeError, match='repair_exhausted'):
        asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='',
            client_factory=lambda: None, turn_runner=bad, max_repairs=1))
    assert len(calls) == 2
    assert 'duration' in calls[1]
    assert previous.read_text() == 'previous'


def test_source_change_prevents_publication(tmp_path):
    story, sources, resources, scenes = sample(tmp_path)
    async def change(**kwargs):
        (tmp_path / 'story.md').write_bytes(sources['story'] + b'\n')
        return SimpleNamespace(payload={'result_json': json.dumps(scenes[0])}, transcript=(),
                               provenance=SimpleNamespace(as_dict=lambda: {}))
    with pytest.raises(RuntimeError, match='stale'):
        asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='',
            client_factory=lambda: None, turn_runner=change))
    assert not (tmp_path / 'cinematic_direction.json').exists()


def test_projection_keeps_author_camera_silence_timing_and_cut_boundary(tmp_path):
    from toc.p400_projection import project_scene
    from toc.stage_evaluation.common import _cut_contract_structure_issues
    story, _, resources, scenes = sample(tmp_path)
    source = story['script']['scenes'][0]
    script, manifest = project_scene(scenes[0], source_scene=source, scene_id=10,
        resources=resources, scene_intent={}, scene_event=source, scene_generation={},
        acceptance_draft={}, acceptance_binding={}, next_selector='scene20_cut01')
    for a, s, m in zip(scenes[0]['cuts'], script['cuts'], manifest['cuts']):
        assert s['cut_contract'] == m['cut_contract']
        assert _cut_contract_structure_issues(s['cut_contract']) == []
        assert m['duration_seconds'] == a['duration_seconds']
        assert m['cut_contract']['first_frame_contract']['first_frame_brief'] == a['first_frame_brief']
        assert m['cut_contract']['cinematic_contract']['camera'] == a['camera']
        assert m['audio']['narration']['tool'] == 'silent'
        assert a['camera']['focus'] in m['image_generation']['api_prompt_payload']['prompt']
    assert manifest['cuts'][-1]['cut_contract']['cut_handoff']['delivers_to_next']['expected_next_cut_selector'] == 'scene20_cut01'


def test_new_frontend_author_failure_is_not_replaced_with_mechanical_cuts(tmp_path):
    from test_toc_immersive_frontend_run import load_frontend_run_module, write_test_llm_story
    from story_profile_fixture import _story_profile, _build_research
    from toc.visual_planning_contract import bind_visual_value
    module = load_frontend_run_module()
    profile = _story_profile('修理工', '修理工')
    research = _build_research('修理工', '修理工', '2026-09-26', profile)
    for record in research['source_inventory']:
        record['url'] = 'https://example.org/' + record['source_id']
    def research_author(**kwargs):
        (tmp_path / 'research.md').write_text(module._md_yaml('research', research))
    def visual_author(*, run_dir):
        story = module.load_structured_document(run_dir / 'story.md')[1]
        raw = {n: (run_dir / f'{n}.md').read_bytes() for n in ('research', 'story')}
        visual = bind_visual_value({'scene_visual_values': [{'scene_selector': s['scene_id'], 'notes': []}
            for s in story['script']['scenes']]}, raw)
        (run_dir / 'visual_value.md').write_text(module._md_yaml('visual', visual))
    def failed(**kwargs):
        raise RuntimeError('cinematic author unavailable')
    with pytest.raises(RuntimeError, match='cinematic author unavailable'):
        module.materialize_run('修理工', '修理工', tmp_path, 'p450',
            research_author_runner=research_author, story_author_runner=write_test_llm_story,
            visual_value_author_runner=visual_author, cinematic_author_runner=failed)
    assert not (tmp_path / 'script.md').exists()
    assert 'slot.p410.status=failed' in (tmp_path / 'state.txt').read_text()


def write_test_cinematic_direction(*, run_dir, resources=None, profile=None):
    """Explicit fake author for offline integration tests, never production fallback."""
    from test_toc_immersive_frontend_run import load_frontend_run_module
    from toc.visual_planning_contract import decode_document
    m = load_frontend_run_module()
    sources = {n: (run_dir / f'{n}.md').read_bytes() for n in ('research', 'story', 'visual_value')}
    story = decode_document(sources['story']); research = decode_document(sources['research'])
    topic = story.get('story_metadata', {}).get('topic', 'fixture')
    profile = profile or m._profile_from_story(m._profile_from_research(m._story_profile(topic, topic), research), story)
    resources = resources or m._cinematic_resources(profile)
    rows, previous_end = [], ''
    for index, scene in enumerate(story['script']['scenes'], 1):
        location = m._location_spec_for_scene(profile, index)['asset_id']
        beats = scene['event_sequence']
        # Deliberately not one-cut-per-beat: a long take covers the scene's beats,
        # followed by a separately timed observation of the last beat.
        target = scene['target_duration_seconds']
        count = max(2, (target + 59) // 60)
        lengths = [target // count] * count
        lengths[-1] += target - sum(lengths)
        if 1 < lengths[0] and lengths[-1] < 60:
            lengths[0] -= 1; lengths[-1] += 1
        cuts = []
        for j, duration in enumerate(lengths):
            first = previous_end or '人物が場所に立っている'
            end = f'{index}-{j}: {beats[-1]["what_happens"]}'
            cuts.append(dict(cut_id=f'hold-{j}', event_time_position='before_trigger' if j == 0 else 'consequence',
                progression_mode='sequential_state_progression',
                start_state_id=scene['start_state']['state_id'] if j == 0 else f'{index}-state-{j}',
                end_state_id=scene['end_state']['state_id'] if j + 1 == count else f'{index}-state-{j+1}',
                source_beat_ids=[b['beat_id'] for b in beats] if j == 0 else [beats[-1]['beat_id']],
                primary_beat_id=beats[0]['beat_id'] if j == 0 else beats[-1]['beat_id'],
                cut_role='main', cut_function='observation', purpose='行為を途切れず見せる',
                duration_seconds=duration, duration_reason='行為と間に合わせる', location_id=location,
                character_ids=[next(iter(resources['characters']))], object_ids=[], primary_subject=resources['characters'][next(iter(resources['characters']))]['name'],
                start_state_facts={'場面': first}, end_state_facts={'場面': end}, visible_state_keys=['場面'],
                first_frame_brief=first, motion_brief=beats[-1]['what_happens'], motion_end_state=end,
                camera={'framing': 'medium', 'movement': 'static', 'composition': '画面端に人物を置く',
                        'light': scene['time_of_day_visual_basis'], 'focus': '人物の手元'},
                narration='', narration_role='silent', silence_reason='原作の曖昧さを説明しない', audio_intent='環境音', edit_reason='行為が終わってから切る',
                continuity={'previous_cut_id': f'hold-{j-1}' if j else '', 'previous_end_state': first, 'mode': 'continuous' if j else 'scene_entry', 'connection': '前の結果を受ける'},
                allowed_reveal_info_ids=[], allowed_new_reveal_elements=[]))
            previous_end = end
        rows.append(dict(scene_id=scene['scene_id'], direction='説明せず観察する', visual_plan_application='p300の意図を構図と間へ',
            entry_connection='前場面を受ける', exit_connection='次の出来事へ接続', cuts=cuts))
    doc = bind_direction(rows, sources, resources)
    assert validate_direction(doc, story, resources) == []
    (run_dir / 'cinematic_direction.json').write_text(json.dumps(doc, ensure_ascii=False))


def test_builder_uses_saved_director_without_legacy_shot_or_equal_duration_planners(tmp_path, monkeypatch):
    from test_source_first_scene_projection import setup_profile
    m, profile, story, _ = setup_profile(tmp_path)
    write_test_cinematic_direction(run_dir=tmp_path, profile=profile)
    def forbidden(*args, **kwargs):
        raise AssertionError('legacy cinematic fallback reached')
    monkeypatch.setattr(m, '_scene_cut_coverage_plan', forbidden)
    monkeypatch.setattr(m, '_allocate_scene_cut_durations', forbidden)
    before = (tmp_path / 'cinematic_direction.json').read_bytes()
    script, manifest, _ = m._build_script_and_manifest('fixture', tmp_path, '2026-09-26', profile)
    plan = json.loads(before)
    assert script['script_metadata']['cinematic_direction_contract'] == 'cinematic_direction_v1'
    for directed, ss, ms in zip(plan['scenes'], script['scenes'], manifest['scenes']):
        assert [c['duration_seconds'] for c in ms['cuts']] == [c['duration_seconds'] for c in directed['cuts']]
        assert ss['cinematic_direction'] == directed
        assert ms['cinematic_direction'] == directed
        assert [c['cut_contract']['first_frame_contract']['first_frame_brief'] for c in ms['cuts']] == [c['first_frame_brief'] for c in directed['cuts']]
    assert (tmp_path / 'cinematic_direction.json').read_bytes() == before


def test_repair_success_and_full_projection_tampering(tmp_path):
    from toc.p400_authoring import direction_projection_file_issues
    from toc.p400_projection import project_scene
    from toc.visual_planning_contract import source_binding
    story, sources, resources, scenes = sample(tmp_path)
    count = 0
    async def turn(**kwargs):
        nonlocal count
        count += 1
        row = deepcopy(scenes[0 if count <= 2 else 1])
        if count == 1: row['cuts'][0]['duration_seconds'] = 0
        if count == 2:
            from toc.production_repair import digest
            bad = deepcopy(scenes[0]); bad['cuts'][0]['duration_seconds'] = 0
            return SimpleNamespace(payload={'unit_id': bad['scene_id'], 'base_digest': digest(bad), 'operations': [
                {'path': '/cuts/0/duration_seconds', 'value': 4}]}, transcript=(), provenance=SimpleNamespace(as_dict=lambda: {}))
        return SimpleNamespace(payload={'result_json': json.dumps(row)}, transcript=(), provenance=SimpleNamespace(as_dict=lambda: {}))
    doc = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='', client_factory=lambda: None, turn_runner=turn))
    assert count == 3
    from toc.source_scene_projection import source_scene_event
    rows = [project_scene(d, source_scene=s, scene_id=i*10, resources=resources, scene_intent={},
        scene_event=source_scene_event(s, runtime_scene_id=i*10, location_name=s['location']['name']),
        scene_generation={}, acceptance_draft={}, acceptance_binding={},
        previous_selector='scene10_cut02' if i == 2 else '', next_selector='scene20_cut01' if i == 1 else '')[0] for i, (d, s) in enumerate(zip(doc['scenes'], story['script']['scenes']), 1)]
    data = {'script_metadata': {'cinematic_direction_contract': 'cinematic_direction_v1',
        'source_cinematic_direction': source_binding('cinematic_direction.json', (tmp_path / 'cinematic_direction.json').read_bytes())}, 'scenes': rows}
    assert direction_projection_file_issues(tmp_path, data, 'script_metadata') == []
    data['scenes'][0]['cuts'][0]['cut_contract']['motion_contract']['motion_brief'] = 'new event'
    assert 'cinematic:authored_cut_projection_changed' in direction_projection_file_issues(tmp_path, data, 'script_metadata')


def test_sub_cannot_take_over_required_story_events_or_import_future_character(tmp_path):
    story, sources, resources, scenes = sample(tmp_path)
    resources['scene_assets'] = {'quiet': {'character_ids': ['keeper'], 'object_ids': []}}
    resources['characters']['future'] = {'name': '未登場人物', 'references': ['assets/characters/future.png']}
    doc = bind_direction(scenes, sources, resources)
    doc['scenes'][0]['cuts'][0]['character_ids'] = ['future']
    assert any('outside_source_scene' in e for e in validate_direction(doc, story, resources))
    doc = bind_direction(scenes, sources, resources)
    doc['scenes'][0]['cuts'][0].update(cut_role='sub', character_ids=[])
    assert any('missing_main_beat_coverage' in e for e in validate_direction(doc, story, resources))


def test_director_file_symlink_is_rejected(tmp_path):
    story, sources, resources, scenes = sample(tmp_path)
    doc = bind_direction(scenes, sources, resources)
    other = tmp_path / 'other.json'; other.write_text(json.dumps(doc))
    (tmp_path / 'cinematic_direction.json').symlink_to(other)
    with pytest.raises((OSError, ValueError, RuntimeError)):
        load_direction(tmp_path)


def test_directed_output_materializes_provider_requests_without_generation(tmp_path):
    import subprocess
    from test_source_first_scene_projection import setup_profile
    from toc.harness import load_structured_document
    m, profile, _, _ = setup_profile(tmp_path)
    write_test_cinematic_direction(run_dir=tmp_path, profile=profile)
    script, manifest, _ = m._build_script_and_manifest('fixture', tmp_path, '2026-09-26', profile)
    for name, data in (('script', script), ('video_manifest', manifest)):
        (tmp_path / f'{name}.md').write_text(m._md_yaml(name, data))
    try:
        m._materialize_standard_request_files(tmp_path)
    except subprocess.CalledProcessError as exc:
        pytest.fail(str(exc.stdout) + str(exc.stderr))
    after = load_structured_document(tmp_path / 'video_manifest.md')[1]
    assert [c['cut_contract']['cinematic_contract']['camera'] for c in after['scenes'][0]['cuts']] == [c['camera'] for c in script['scenes'][0]['cinematic_direction']['cuts']]
    assert not list(tmp_path.rglob('*.mp4'))


def test_later_beat_reveal_cannot_be_authorized_by_an_earlier_cut(tmp_path):
    story, sources, resources, scenes = sample(tmp_path)
    story['script']['scenes'][0]['event_sequence'][1]['allowed_reveal_info_ids'] = ['identity']
    doc = bind_direction(scenes, sources, resources)
    doc['scenes'][0]['cuts'][0]['allowed_reveal_info_ids'] = ['identity']
    assert any('reveal_not_authorized' in error for error in validate_direction(doc, story, resources))
    doc['scenes'][0]['cuts'][0]['allowed_reveal_info_ids'] = []
    doc['scenes'][0]['cuts'][1]['allowed_reveal_info_ids'] = ['identity']
    assert validate_direction(doc, story, resources) == []


def test_continuous_cut_cannot_reopen_a_closed_state(tmp_path):
    story, sources, resources, scenes = sample(tmp_path)
    doc = bind_direction(scenes, sources, resources)
    doc['scenes'][0]['cuts'][1]['start_state_facts'] = {'場面': '箱が閉じている'}
    assert any('continuous_start_state_mismatch' in e for e in validate_direction(doc, story, resources))
    doc = bind_direction(scenes, sources, resources)
    doc['scenes'][0]['cuts'][-1]['end_state_id'] = 'unrelated-ending'
    assert any('source_end_state_mismatch' in e for e in validate_direction(doc, story, resources))


def test_temporal_position_preservation_and_future_boundary_reach_provider_prompt(tmp_path):
    from toc.p400_projection import project_scene
    story, _, resources, scenes = sample(tmp_path)
    source = story['script']['scenes'][0]
    source['preservation'] = {'must_not_change': ['箱の赤い塗装'], 'must_not_show': ['隠された署名']}
    source['event_sequence'][1]['what_happens'] = '部屋の明かりが消える'
    resources['characters']['keeper']['appearance_continuity'] = {'costume_state': '煤けた作業着', 'forbidden_costume_states': ['礼服']}
    script, manifest = project_scene(scenes[0], source_scene=source, scene_id=10, resources=resources,
        scene_intent={}, scene_event=source, scene_generation={}, acceptance_draft={}, acceptance_binding={})
    first = manifest['cuts'][0]
    text = first['image_generation']['api_prompt_payload']['prompt']
    assert '部屋の明かりが消える' in text
    assert '箱の赤い塗装' in text
    assert '隠された署名' in text
    assert '煤けた作業着' in text
    last = manifest['cuts'][-1]['cut_contract']
    assert last['source_event_contract']['event_time_position'] == 'consequence'
    assert last['first_frame_contract']['event_time_position'] == 'consequence'
    assert last['cut_state_progression']['progression_mode'] == 'suspended_moment'


def test_p400_started_state_cannot_downgrade_after_direction_disappears(tmp_path):
    from test_source_first_scene_projection import setup_profile
    m, profile, _, _ = setup_profile(tmp_path)
    (tmp_path / 'state.txt').write_text('p400.cinematic_direction_contract=cinematic_direction_v1\n')
    with pytest.raises(RuntimeError, match='cinematic direction is required'):
        m._build_script_and_manifest('fixture', tmp_path, '2026-09-26', profile)


@pytest.mark.parametrize('block,key,value', [
    ('source_event_contract', 'event_facts_not_to_invent', ['changed source']),
    ('asset_dependency', 'character_ids_required', ['future-actor']),
    ('continuity_contract', 'previous_end_state', 'unrelated state'),
    ('first_frame_contract', 'event_time_position', 'handoff_after'),
])
def test_full_semantic_projection_cannot_drift_from_director(tmp_path, block, key, value):
    from test_source_first_scene_projection import setup_profile
    from toc.p400_authoring import direction_projection_file_issues
    m, profile, _, _ = setup_profile(tmp_path)
    write_test_cinematic_direction(run_dir=tmp_path, profile=profile)
    script, _, _ = m._build_script_and_manifest('fixture', tmp_path, '2026-09-26', profile)
    script['scenes'][0]['cuts'][0]['cut_contract'][block][key] = value
    assert direction_projection_file_issues(tmp_path, script, 'script_metadata')


def test_ellipsis_requires_explicit_reason_and_survives_projection(tmp_path):
    from toc.p400_projection import project_scene
    story, sources, resources, scenes = sample(tmp_path)
    cut = scenes[0]['cuts'][1]
    cut['continuity']['mode'] = 'ellipsis'
    assert any('ellipsis_reason' in e for e in validate_direction(bind_direction(scenes, sources, resources), story, resources))
    cut['continuity']['ellipsis_reason'] = '原作にある待ち時間の一部を省略する'
    assert validate_direction(bind_direction(scenes, sources, resources), story, resources) == []
    source = story['script']['scenes'][0]
    _, manifest = project_scene(scenes[0], source_scene=source, scene_id=10, resources=resources,
        scene_intent={}, scene_event=source, scene_generation={}, acceptance_draft={}, acceptance_binding={})
    projected = manifest['cuts'][1]['cut_contract']
    assert projected['continuity_contract']['mode'] == 'ellipsis'
    assert projected['cut_handoff']['receives_from_previous']['ellipsis_reason'] == cut['continuity']['ellipsis_reason']
    assert manifest['scene_state_progression_plan']['progression_mode'] == 'suspended_moment'


def test_continuous_state_allows_a_new_framing_without_showing_offscreen_facts(tmp_path):
    from toc.p400_projection import project_scene
    story, sources, resources, scenes = sample(tmp_path)
    first, second = scenes[0]['cuts']
    shared = {'箱': '開いたまま机にある', '修理工': '返事を待っている'}
    first['end_state_facts'] = shared
    second['start_state_facts'] = deepcopy(shared)
    second['visible_state_keys'] = ['修理工']
    second['first_frame_brief'] = '修理工の顔のクローズアップ。返事を待つ表情だけが見える。'
    second['camera']['framing'] = 'close_up'
    assert validate_direction(bind_direction(scenes, sources, resources), story, resources) == []
    source = story['script']['scenes'][0]
    _, manifest = project_scene(scenes[0], source_scene=source, scene_id=10, resources=resources,
        scene_intent={}, scene_event=source, scene_generation={}, acceptance_draft={}, acceptance_binding={})
    plan = manifest['cuts'][1]['image_generation']['first_frame_visual_plan']
    assert plan['authored_visible_state_facts'] == ['修理工: 返事を待っている']
    assert manifest['cuts'][1]['cut_contract']['continuity_contract']['start_state']['facts']['箱'] == '開いたまま机にある'


def test_resume_reuses_completed_scene_after_transport_failure(tmp_path):
    story, sources, resources, scenes = sample(tmp_path)
    calls = []
    def response(row):
        return SimpleNamespace(payload={'result_json': json.dumps(row)}, transcript=(),
            provenance=SimpleNamespace(as_dict=lambda: {}))
    async def interrupted(**kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            raise RuntimeError('offline')
        return response(scenes[0])
    with pytest.raises(RuntimeError, match='offline'):
        asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='',
            client_factory=lambda: None, turn_runner=interrupted))
    resumed_calls = []
    async def resumed(**kwargs):
        resumed_calls.append(kwargs)
        return response(scenes[1])
    doc = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='',
        client_factory=lambda: None, turn_runner=resumed))
    assert len(resumed_calls) == 1
    assert doc['scenes'][0]['scene_id'] == scenes[0]['scene_id']


def test_unscoped_final_validation_does_not_regenerate_healthy_scenes(tmp_path, monkeypatch):
    import toc.p400_authoring as module
    story, sources, resources, scenes = sample(tmp_path)
    original = module.validate_direction
    checks = []
    def validate(*args):
        checks.append(args)
        return ['final_scene_boundary_needs_repair'] if len(checks) == 1 else original(*args)
    monkeypatch.setattr(module, 'validate_direction', validate)
    prompts = []
    async def turn(**kwargs):
        prompts.append(kwargs['prompt'])
        return SimpleNamespace(payload={'result_json': json.dumps(scenes[(len(prompts)-1) % len(scenes)])},
            transcript=(), provenance=SimpleNamespace(as_dict=lambda: {}))
    with pytest.raises(RuntimeError, match='final_scene_boundary_needs_repair'):
        asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='',
            client_factory=lambda: None, turn_runner=turn))
    assert len(prompts) == len(scenes)
