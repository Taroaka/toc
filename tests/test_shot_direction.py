from copy import deepcopy

import pytest

from toc.shot_direction import normalize_shot_plan
from toc.shot_projection import project_cut_shots


def plan(duration=4):
    return {'schema_version': 'shot_direction_v1', 'intent': '反応から動きへ注意を移す', 'shots': [{
        'shot_id': 'a', 'start_seconds': 0, 'duration_seconds': duration,
        'intent': '足取りを見る',
        'initial_view': {'description': '作業者の靴と裾だけが見える', 'subjects': [
            {'entity_id': 'keeper', 'kind': 'character', 'member_id': None,
             'visible_parts': ['足', '裾'], 'view': '上半身は画角外'}],
            'framing': '足元の寄り', 'composition': '床から低く撮る', 'focus': '靴と床'},
        'motion': '作業者が歩き続ける', 'camera': {'movement': '固定', 'angle': None,
            'lens_mm': None, 'focus_change': None},
        'performance': [{'actor_id': 'keeper', 'member_id': None, 'target_id': None,
            'objective': '立ち去る', 'emotion': None, 'basis': 'source_action',
            'behavior': '足を止めず歩く', 'trigger': None}],
        'events': [], 'end_view': None, 'end_state': '足元が画角から抜ける'}]}


def resources():
    return {'characters': {'keeper': {'name': '作業者', 'references': ['assets/characters/a.png']},
                           'visitor': {'name': '訪問者', 'references': ['assets/characters/b.png']}},
            'objects': {}, 'locations': {'room': {'name': '部屋', 'references': ['assets/locations/r.png']}}}


def parent():
    return {'cut_id': '01', 'selector': 'scene10_cut01', 'duration_seconds': 4,
            'audio': {'narration': {'text': '採用原稿', 'output': 'assets/audio/original.mp3', 'sha256': 'unchanged'}},
            'image_generation': {'character_ids': ['keeper', 'visitor'], 'object_ids': [],
                'location_ids': ['room'], 'output': 'assets/scenes/original.png'},
            'video_generation': {'output': 'assets/scenes/original.mp4'},
            'cut_contract': {
                'cut_role': 'main', 'viewer_contract': {'dramatic_job': '観察する'},
                'source_event_contract': {'source_event_beat_ids': ['beat_a']},
                'first_frame_contract': {}, 'motion_contract': {},
                'continuity_contract': {'character_ids': ['keeper', 'visitor'], 'object_ids': [],
                    'location_ids': ['room'], 'must_preserve': ['靴と裾の状態']},
                'cinematic_contract': {'camera': {'light': '窓明かり'}},
                'narration_contract': {'text': '採用原稿'},
                'asset_dependency': {'character_ids_required': ['keeper', 'visitor'],
                                     'object_ids_required': [], 'location_ids_required': ['room']}}}


def norm(value):
    return normalize_shot_plan(value, character_ids=['keeper', 'visitor'], object_ids=[], duration_seconds=4)


def test_nullable_choices_and_original_input_unchanged():
    value = plan(); before = deepcopy(value)
    result = norm(value)
    assert value == before
    assert result['shots'][0]['camera']['lens_mm'] is None
    assert result['shots'][0]['performance'][0]['emotion'] is None
    assert result['shots'][0]['end_view'] is None


def test_relative_object_view_uses_authored_current_frame_without_erasing_character_pose(monkeypatch):
    import json
    import toc.shot_projection as projection
    from toc.image_prompt_compiler import compile_image_api_prompt_v2

    value = plan()
    value['shots'][0]['initial_view']['description'] = '作業者の靴と裾、その横の床に置かれた小包が見える'
    value['shots'][0]['initial_view']['subjects'].append({
        'entity_id': 'parcel', 'kind': 'object', 'member_id': None,
        'visible_parts': ['外形'], 'view': '前cutから同じ向きで保つ',
    })
    source = parent()
    source['cut_contract']['asset_dependency']['object_ids_required'] = ['parcel']
    registry = resources()
    registry['objects'] = {'parcel': {'name': '小包', 'references': ['assets/objects/parcel.png']}}
    captured = []

    def compile_and_capture(**kwargs):
        captured.append(deepcopy(kwargs['first_frame_visual_plan']))
        return compile_image_api_prompt_v2(**kwargs)

    monkeypatch.setattr(projection, 'compile_image_api_prompt_v2', compile_and_capture)
    result = project_cut_shots(source, value, registry)
    assert '上半身は画角外' in captured[-1]['character_state_gate']['pose']
    assert '前cut' not in captured[-1]['character_state_gate']['pose']
    assert captured[-1]['object_visibility_gate']['objects'][0]['object_state'] == value['shots'][0]['initial_view']['description']
    assert '前cut' not in result['shots'][0]['image_generation']['api_prompt_payload']['prompt']


def test_relative_description_uses_only_the_same_views_explicit_subject_states():
    value = plan()
    view = value['shots'][0]['initial_view']
    view['description'] = '前cutの終わりと同じ作業者の胸上。視線は低い。'
    view['subjects'][0].update(visible_parts=['顔', '肩'], view='顔を右へ向け、目を落としている。手元は画角外。')
    view.update(framing='胸上の近景', composition='人物を左に置く')
    end = deepcopy(view)
    end['description'] = '作業者は視線を上げている'
    end['subjects'][0]['view'] = '眼と顔を右上へ向ける'
    value['shots'][0]['end_view'] = end
    before = deepcopy(value)
    child = project_cut_shots(parent(), value, resources())['shots'][0]
    prompt = child['image_generation']['api_prompt_payload']['prompt']
    assert '目を落としている' in prompt
    assert '人物を左に置く' in prompt
    assert '胸上の近景' in prompt
    assert '前cut' not in prompt and '右上へ' not in prompt
    assert value == before
    assert '目を落としている' in child['cut_contract']['first_frame_contract']['first_frame_brief']


@pytest.mark.parametrize('missing', ['relative_subject', 'no_subjects'])
def test_relative_description_without_explicit_subject_state_still_fails(missing):
    value = plan()
    view = value['shots'][0]['initial_view']
    view['description'] = '前sceneと同じ状態を引き継ぐ'
    if missing == 'relative_subject': view['subjects'][0]['view'] = '前cutと同じ'
    else: view['subjects'] = []
    with pytest.raises(ValueError, match='drawable_prompt_current_moment_missing'):
        project_cut_shots(parent(), value, resources())


def test_mixed_scene_reference_preserves_complete_current_view_sentences():
    from toc.video_prompt_compiler import _first_frame_plan_start_values
    value = plan()
    view = value['shots'][0]['initial_view']
    view['description'] = 'scene_04と同じ画軸側。左の作業者は床に立ち、両手を下ろしている。'
    view['subjects'][0]['view'] = '両手は身体側。前sceneと同じ衣服。'
    before = deepcopy(value)
    child = project_cut_shots(parent(), value, resources())['shots'][0]
    image = child['image_generation']
    assert '左の作業者は床に立ち' in image['api_prompt_payload']['prompt']
    assert '両手は身体側' in image['api_prompt_payload']['prompt']
    assert 'scene_04' not in image['api_prompt_payload']['prompt']
    assert '前scene' not in image['api_prompt_payload']['prompt']
    assert _first_frame_plan_start_values(image['first_frame_visual_plan'])
    assert value == before


@pytest.mark.parametrize('reference', [
    '次scene', '次のscene', '後続のshot', '次のシーン', 'Next scene', 'Following cut',
    'Next scene_04', 'Following cut02', 'Next-shot-03', 'next_scene_04',
])
def test_forward_scene_context_is_not_salvaged_as_current_state(reference):
    value = plan()
    view = value['shots'][0]['initial_view']
    view['description'] = reference + 'の構図。作業者は入口に立つ。'
    view['subjects'][0]['view'] = '入口で立つ。'
    with pytest.raises(ValueError, match='drawable_prompt_current_moment_missing'):
        project_cut_shots(parent(), value, resources())


@pytest.mark.parametrize('fault', ['version', 'unknown_actor', 'unknown_subject', 'gap', 'duration', 'duplicate', 'nan', 'missing_view', 'unknown_key'])
def test_malformed_or_unresolved_plan_fails(fault):
    value = plan(); shot = value['shots'][0]
    if fault == 'version': value['schema_version'] = 'future'
    if fault == 'unknown_actor': shot['performance'][0]['actor_id'] = 'unknown'
    if fault == 'unknown_subject': shot['initial_view']['subjects'][0]['entity_id'] = 'unknown'
    if fault == 'gap': shot['start_seconds'] = 1
    if fault == 'duration': shot['duration_seconds'] = 5
    if fault == 'duplicate': value['shots'].append(deepcopy(shot))
    if fault == 'nan': shot['duration_seconds'] = float('nan')
    if fault == 'missing_view': shot['initial_view'] = None
    if fault == 'unknown_key': shot['camera']['typo'] = 'ignored'
    with pytest.raises(ValueError): norm(value)


def test_project_part_view_preserves_audio_and_excludes_other_participants_from_still():
    source = parent(); before = deepcopy(source)
    result = project_cut_shots(source, plan(), resources())
    assert source == before and result['audio'] == before['audio']
    shot = result['shots'][0]
    image = shot['image_generation']
    assert image['character_ids'] == ['keeper']
    assert 'assets/characters/b.png' not in image['references']
    assert '足元の寄り' in image['api_prompt_payload']['prompt']
    assert '上半身は画角外' in image['api_prompt_payload']['prompt']
    assert shot['cut_contract']['asset_dependency']['character_ids_required'] == ['keeper']
    assert result['duration_seconds'] == 4
    assert result['image_generation'] == image


def test_later_person_is_bound_to_end_image_not_first_image():
    value = plan(); shot = value['shots'][0]
    end = deepcopy(shot['initial_view'])
    end['subjects'].append({'entity_id': 'visitor', 'kind': 'character', 'member_id': None,
                           'visible_parts': ['全身'], 'view': 'そばに立つ'})
    end['description'] = '訪問者も見える'
    shot['end_view'] = end
    shot['events'] = [{'kind': 'camera_reveal', 'entity_ids': ['visitor'],
                       'description': 'カメラが訪問者を捉える', 'trigger': '作業者が気づく'}]
    result = project_cut_shots(parent(), value, resources())['shots'][0]
    assert 'assets/characters/b.png' not in result['image_generation']['references']
    end_image = result['video_generation']['result_frame']['image_generation']
    assert 'assets/characters/b.png' in end_image['references']
    assert result['video_generation']['last_frame'] == end_image['output']
    assert result['image_generation']['output'] in end_image['references']


def test_multiple_shots_keep_audio_interval_and_separate_provider_duration():
    value = plan(1.5); second = deepcopy(value['shots'][0])
    second.update(shot_id='b', start_seconds=1.5, duration_seconds=2.5)
    value['shots'].append(second)
    result = project_cut_shots(parent(), value, resources())
    assert [s['duration_seconds'] for s in result['shots']] == [1.5, 2.5]
    assert [s['video_generation']['duration_seconds'] for s in result['shots']] == [3, 3]
    assert result['audio'] == parent()['audio']
    assert len({s['image_generation']['output'] for s in result['shots']}) == 2


def test_empty_environment_view_and_nonvisible_physical_conditions():
    value = plan(); shot = value['shots'][0]
    shot['initial_view'].update(subjects=[], description='床だけが見える', focus=None)
    shot['performance'] = []; shot['motion'] = '影がゆっくり動く'
    result = project_cut_shots(parent(), value, resources())['shots'][0]
    assert result['image_generation']['character_ids'] == []
    assert '人物、顔、身体、手足' in result['image_generation']['api_prompt_payload']['prompt']


def test_offscreen_identity_not_encodable_fails_before_purchase():
    value = plan(); shot = value['shots'][0]
    shot['events'] = [{'kind': 'enter_frame', 'entity_ids': ['visitor'],
                       'description': '訪問者が入ってから出ていく', 'trigger': None}]
    with pytest.raises(ValueError, match='reference|参照'):
        project_cut_shots(parent(), value, resources())


def test_directed_camera_and_response_survive_common_video_compiler():
    from toc.video_prompt_compiler import compile_video_api_prompt_v1
    value = plan()
    value['shots'][0]['camera'].update(movement='カメラが右にパンし、上へチルトし、最後にドリーで寄る', angle='床の高さ', lens_mm=70)
    child = project_cut_shots(parent(), value, resources())['shots'][0]
    image_prompt = child['image_generation']['api_prompt_payload']['prompt']
    assert '70mm' in image_prompt and '床の高さ' in image_prompt
    payload = compile_video_api_prompt_v1(cut_contract=child['cut_contract'], tool='kling_3_0',
        first_frame=child['image_generation']['output'], duration_seconds=4)
    assert '最後にドリーで寄る' in payload['prompt']
    assert '足を止めず歩く' in payload['prompt']
    assert '主動作は一つに絞り' not in payload['prompt']


def test_result_state_reference_carries_to_later_shot_without_audio_change():
    source = parent()
    source['video_generation']['result_state_reference'] = {'required': True, 'state_variant_refs': [
        {'entity_type': 'character', 'asset_id': 'keeper', 'variant_id': 'after', 'transition_id': 't',
         'consumer_source_event_beat_ids': ['beat_a']}]}
    source['video_generation']['result_frame'] = {'image_generation': {
        'character_variant_ids': ['after'],
        'references': ['assets/characters/keeper__after.png'],
        'first_frame_visual_plan': {'reference_binding': {'character_references': [
            {'target_character_id': 'keeper', 'path': 'assets/characters/keeper__after.png'}]}}}}
    value = plan(2)
    first = value['shots'][0]
    first['events'] = [{'kind': 'transform', 'entity_ids': ['keeper'], 'description': '外見が変わる', 'trigger': None}]
    first['end_view'] = deepcopy(first['initial_view'])
    second = deepcopy(plan(2)['shots'][0]); second.update(shot_id='b', start_seconds=2)
    second['initial_view']['state_source'] = 'previous_end'
    value['shots'].append(second)
    projected = project_cut_shots(source, value, resources())
    assert 'assets/characters/keeper__after.png' not in projected['shots'][0]['image_generation']['references']
    image = projected['shots'][1]['image_generation']
    assert 'assets/characters/keeper__after.png' in image['references']
    assert image['character_variant_ids'] == ['after']
    assert projected['shots'][0]['video_generation']['last_frame'] in image['references']
    # Both a transformation's end frame and later shots must retain the new
    # state. Preserve the exact view so the author can repair only its selector.
    from toc.shot_projection import ShotImageProjectionError
    for shot_index, view_field in ((0, 'end_view'), (1, 'initial_view')):
        reset = deepcopy(value)
        reset['shots'][shot_index][view_field]['state_source'] = 'start'
        with pytest.raises(ShotImageProjectionError) as failure:
            project_cut_shots(source, reset, resources())
        assert failure.value.issue == {'shot_index': shot_index, 'view_field': view_field,
            'reason': 'shot_direction:start_state_reset_after_transition'}
    wrong = deepcopy(source)
    wrong['video_generation']['result_state_reference']['state_variant_refs'][0]['asset_id'] = 'visitor'
    with pytest.raises(ValueError, match='transformed_entity_result_reference_missing'):
        project_cut_shots(wrong, value, resources())


def test_future_result_cannot_be_used_before_its_transition():
    value = plan(); value['shots'][0]['initial_view']['state_source'] = 'result'
    with pytest.raises(ValueError, match='before_transition'):
        project_cut_shots(parent(), value, resources())


def test_ordinary_action_result_end_view_keeps_identity_without_a_transformation():
    source = parent()
    value = plan()
    shot = value['shots'][0]
    shot['end_view'] = deepcopy(shot['initial_view'])
    shot['end_view'].update(state_source='result', description='作業者は足を止め、床に立っている')
    shot['end_view']['subjects'][0]['view'] = '床に両足を置き、静止している'
    before = deepcopy(value)
    projected = project_cut_shots(source, value, resources())
    child = projected['shots'][0]
    end_image = child['video_generation']['result_frame']['image_generation']
    assert value == before
    assert projected['audio'] == source['audio']
    assert child['image_generation']['output'] in end_image['references']
    assert set(child['image_generation']['references']) <= set(end_image['references'])
    assert '作業者は足を止め' in end_image['api_prompt_payload']['prompt']
    assert end_image['character_variant_ids'] == []
    assert 'result_state_reference' not in child['video_generation']


@pytest.mark.parametrize('parent_result', ['image', 'reference'])
def test_end_view_result_cannot_skip_a_parent_state_transition(parent_result):
    source = parent()
    value = plan()
    value['shots'][0]['end_view'] = deepcopy(value['shots'][0]['initial_view'])
    value['shots'][0]['end_view']['state_source'] = 'result'
    if parent_result == 'image':
        source['video_generation']['result_frame'] = {'image_generation': {'references': ['assets/characters/keeper__after.png']}}
    else:
        source['video_generation']['result_state_reference'] = {'required': True}
    with pytest.raises(ValueError, match='result_state_used_before_transition'):
        project_cut_shots(source, value, resources())


def test_previous_end_inherits_authored_state_without_forcing_optional_end_image():
    value = plan(2)
    value['shots'][0]['end_state'] = '足が画面左で静止している'
    second = deepcopy(value['shots'][0])
    second.update(shot_id='b', start_seconds=2)
    second['initial_view'].update(state_source='previous_end', description='画面左で静止した作業者の足')
    value['shots'].append(second)
    before = deepcopy(value)
    result = project_cut_shots(parent(), value, resources())
    assert value == before
    assert len(result['shots']) == 2
    assert not result['shots'][0]['video_generation'].get('last_frame')
    assert result['shots'][1]['image_generation']['first_frame_visual_plan']['source_grounding']['previous_shot_end_state'] == value['shots'][0]['end_state']
    assert not result['shots'][1]['image_generation']['first_frame_visual_plan']['reference_binding'].get('scene_references')


def test_first_shot_cannot_reference_a_nonexistent_previous_shot():
    value = plan()
    value['shots'][0]['initial_view']['state_source'] = 'previous_end'
    with pytest.raises(ValueError, match='previous_end_reference_missing'):
        project_cut_shots(parent(), value, resources())


def test_ordered_actions_remain_and_future_event_prose_does_not_reach_api():
    from toc.video_prompt_compiler import compile_video_api_prompt_v1
    value = plan(); value['shots'][0]['motion'] = '手を差し出す。その後、相手の反応を待つ'
    source = parent()
    source['cut_contract']['source_event_contract']['future_event_boundaries'] = [{'what_happens': '未来の王冠をかぶる'}]
    source['cut_contract']['motion_contract']['must_not_add'] = ['字幕', '未来の王冠をかぶる']
    child = project_cut_shots(source, value, resources())['shots'][0]
    payload = compile_video_api_prompt_v1(cut_contract=child['cut_contract'], tool='kling_3_0',
        first_frame=child['image_generation']['output'], duration_seconds=4)
    assert '相手の反応を待つ' in payload['prompt']
    assert '未来の王冠' not in payload['prompt']


def test_huge_integer_and_casefold_ids_fail_cleanly():
    value = plan(); value['shots'][0]['camera']['lens_mm'] = 10 ** 400
    with pytest.raises(ValueError, match='number_required'):
        norm(value)
    value = plan(2); second = deepcopy(value['shots'][0]); second.update(shot_id='A', start_seconds=2)
    value['shots'].append(second)
    with pytest.raises(ValueError, match='duplicate'):
        norm(value)


def test_p400_new_plan_projects_children_and_keeps_source_contract(tmp_path):
    from test_p400_cinematic_author import sample
    from toc.p400_projection import project_scene
    from toc.p400_authoring import validate_scene_direction
    story, _, registry, scenes = sample(tmp_path)
    scenes[0]['cuts'][0]['shot_plan'] = plan()
    assert not validate_scene_direction(scenes[0], story['script']['scenes'][0], registry)
    script, manifest = project_scene(scenes[0], source_scene=story['script']['scenes'][0], scene_id=10,
        resources=registry, scene_intent={}, scene_event=story['script']['scenes'][0],
        scene_generation={}, acceptance_draft={}, acceptance_binding={})
    assert script['cuts'][0]['shot_plan'] == manifest['cuts'][0]['shot_plan']
    assert manifest['cuts'][0]['shots'][0]['selector'] == 'scene10_cut01_shota'
    assert manifest['cuts'][0]['audio']['narration']['tool'] == 'silent'


def test_visual_revision_uses_new_outputs_but_stable_selectors():
    before = project_cut_shots(parent(), plan(), resources())['shots'][0]
    change = plan(); change['shots'][0]['initial_view']['framing'] = '背後から足元へ寄る'
    after = project_cut_shots(parent(), change, resources())['shots'][0]
    assert before['selector'] == after['selector']
    assert before['image_generation']['output'] != after['image_generation']['output']
    assert before['video_generation']['output'] != after['video_generation']['output']


def test_adopted_narration_timeline_takes_precedence_over_old_planned_duration():
    source = parent(); source['render'] = {'video_duration_seconds': 8, 'narration_offset_seconds': 0.5}
    source['video_generation']['duration_seconds'] = 8
    actual = project_cut_shots(source, plan(8), resources())
    assert actual['duration_seconds'] == source['duration_seconds'] == 4
    assert actual['render'] == source['render']
    assert actual['audio'] == source['audio']
    assert actual['shots'][0]['duration_seconds'] == 8
    with pytest.raises(ValueError, match='timeline_total'):
        project_cut_shots(source, plan(4), resources())


def test_manifest_checks_provider_limits_on_executed_shots_not_audio_parent():
    from toc.stage_evaluation.pipeline import _manifest_checks
    source = parent(); source['duration_seconds'] = 32
    source['video_generation'].update(tool='higgsfield', duration_seconds=32)
    source['cut_contract']['cinematic_direction_contract'] = 'cinematic_direction_v1'
    value = plan(12)
    for sid, start, duration in [('b', 12, 10), ('c', 22, 10)]:
        shot = deepcopy(value['shots'][0]); shot.update(shot_id=sid, start_seconds=start, duration_seconds=duration)
        value['shots'].append(shot)
    result = project_cut_shots(source, value, resources())

    def check(cut):
        checks = []
        _manifest_checks(checks, '', {'scenes': [{'scene_id': 1, 'cuts': [cut]}]},
                         profile='standard', flow='immersive', path_label='manifest')
        return next(row for row in checks if row['id'] == 'manifest.node_types')

    assert check(result)['passed'], check(result)
    result['shots'][0]['video_generation']['model'] = 'unsupported'
    assert not check(result)['passed']
    result['shots'][0]['video_generation']['model'] = 'kling-video/v3.0/std/image-to-video'
    result['shots'][0]['video_generation']['duration_seconds'] = 16
    assert not check(result)['passed']


def test_projection_accepts_nonexecuting_image_trace_but_rejects_prompt_changes(tmp_path):
    from test_p400_cinematic_author import sample
    from toc.p400_authoring import bind_direction, projection_issues
    from toc.p400_projection import project_scene
    from toc.source_scene_projection import source_scene_event
    story, sources, registry, scenes = sample(tmp_path)
    scenes[0]['cuts'][0]['shot_plan'] = plan(4)
    direction = bind_direction(scenes, sources, registry)
    data = {'video_metadata': {'cinematic_direction_contract': 'cinematic_direction_v1'}, 'scenes': []}
    for i, row in enumerate(scenes):
        source = story['script']['scenes'][i]
        event = source_scene_event(source, runtime_scene_id=(i+1)*10, location_name=source['location']['name'])
        previous = f'scene{i*10}_cut{len(scenes[i-1]["cuts"]):02d}' if i else ''
        following = f'scene{(i+2)*10}_cut01' if i+1 < len(scenes) else ''
        projected = project_scene(row, source_scene=source, scene_id=(i+1)*10, resources=registry,
            scene_intent={}, scene_event=event, scene_generation={}, acceptance_draft={}, acceptance_binding={},
            previous_selector=previous, next_selector=following)[1]
        data['scenes'].append(projected)
    assert projection_issues(data, 'video_metadata', direction, story) == []
    image = data['scenes'][0]['cuts'][0]['shots'][0]['image_generation']
    image['debug_prompt_source'] = 'nonexecuting source trace'
    assert projection_issues(data, 'video_metadata', direction, story) == []
    image['api_prompt_payload']['prompt'] = 'changed executable provider prompt'
    assert 'cinematic:shot_projection_changed' in projection_issues(data, 'video_metadata', direction, story)
