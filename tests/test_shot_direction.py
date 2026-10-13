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
    wrong = deepcopy(source)
    wrong['video_generation']['result_state_reference']['state_variant_refs'][0]['asset_id'] = 'visitor'
    with pytest.raises(ValueError, match='transformed_entity_result_reference_missing'):
        project_cut_shots(wrong, value, resources())


def test_future_result_cannot_be_used_before_its_transition():
    value = plan(); value['shots'][0]['initial_view']['state_source'] = 'result'
    with pytest.raises(ValueError, match='before_transition'):
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
