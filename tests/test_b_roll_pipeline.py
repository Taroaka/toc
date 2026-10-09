from copy import deepcopy
import pytest

from toc.b_roll import validate_boundary, materialize_b_roll
from toc.video_prompt_compiler import compile_video_api_prompt_v1
from toc.image_prompt_compiler import compile_image_api_prompt_v2


def proposal(location='工房'):
    return {'reason': '作業後の空間に余韻を置く', 'cuts': [{
        'technique': 'pillow', 'source_event_beat_id': 'done', 'location': location,
        'subject': '窓辺', 'first_frame': '窓辺の床に光が落ちている',
        'motion': '窓辺の光を固定カメラで保持する', 'end_state': '窓辺の光が残っている',
        'foreground': '床', 'background': location, 'light': '窓からの自然光',
    }]}


def test_invalid_or_missing_boundary_fails():
    with pytest.raises(ValueError):
        validate_boundary(None, beat_ids=['done'])
    bad = proposal(); bad['cuts'][0]['source_event_beat_id'] = 'invented'
    with pytest.raises(ValueError):
        validate_boundary(bad, beat_ids=['done'])
    validate_boundary({'reason': '直結して緊張を保つ', 'cuts': []}, beat_ids=['done'])
    bad = proposal(); bad['cuts'][0]['motion'] = '人物が窓辺から去る'
    with pytest.raises(ValueError, match='visible_person'):
        validate_boundary(bad, beat_ids=['done'])
    valid = proposal(); valid['cuts'][0]['first_frame'] = '人影のない窓辺'
    validate_boundary(valid, beat_ids=['done'])


@pytest.mark.parametrize('location', ['工房', '港の倉庫'])
def test_sub_compiles_without_characters_in_image_and_video(location):
    spec = proposal(location)['cuts'][0]
    script, cut = materialize_b_roll(spec, selector='scene1_cut09', cut_id='09',
        location={'asset_id': 'loc_1', 'name': location, 'reference_image': 'assets/loc.png'},
        duration=4, story_time='', time_of_day='day', previous_selector='scene1_cut08')
    assert cut['cut_contract']['cut_role'] == 'sub'
    assert cut['image_generation']['character_ids'] == []
    assert cut['audio']['narration']['tool'] == 'silent'
    image = cut['image_generation']['api_prompt_payload']['prompt']
    assert '人物' in image and '映り込み' in image
    assert '[登場人物]' not in image
    video = compile_video_api_prompt_v1(cut_contract=cut['cut_contract'],
        video_generation=cut['video_generation'], first_frame_visual_plan=cut['image_generation']['first_frame_visual_plan'])
    assert '人物' in video['prompt'] and '映り込み' in video['prompt']
    assert '顔、髪、衣装、体格' not in video['prompt']
    assert '入力画像に写る人物' not in video['prompt']
    assert script['cut_contract'] == cut['cut_contract']
    bad = deepcopy(cut['image_generation'])
    with pytest.raises(ValueError, match='b_roll'):
        compile_image_api_prompt_v2(first_frame_visual_plan=bad['first_frame_visual_plan'], character_ids=['person'])
    contract = deepcopy(cut['cut_contract']); contract['asset_dependency']['character_ids_required'] = ['person']
    with pytest.raises(ValueError, match='b_roll'):
        compile_video_api_prompt_v1(cut_contract=contract, video_generation=cut['video_generation'])


@pytest.mark.parametrize('b_roll_count', [1, 2])
def test_new_run_projects_authored_sub_through_frontend(tmp_path, b_roll_count):
    from test_source_first_scene_projection import setup_profile
    from toc.b_roll import POLICY
    m, profile, story, visual = setup_profile(tmp_path)
    visual['visual_value_metadata']['b_roll_policy'] = POLICY
    for row, scene in zip(visual['scene_visual_values'], story['script']['scenes']):
        row['boundary_b_roll'] = {'reason': '直接接続', 'cuts': []}
    scene = story['script']['scenes'][0]
    location = m._scene_location_sequence(profile, 1)[-1]
    boundary = proposal(location)
    boundary['cuts'][0]['source_event_beat_id'] = scene['event_sequence'][-1]['beat_id']
    if b_roll_count == 2:
        second = deepcopy(boundary['cuts'][0])
        second.update({'technique': 'insert', 'subject': '床の光', 'first_frame': '床の木目に光が落ちている'})
        boundary['cuts'].append(second)
    visual['scene_visual_values'][0]['boundary_b_roll'] = boundary
    (tmp_path / 'visual_value.md').write_text(m._md_yaml('visual', visual))
    script, manifest, selectors = m._build_script_and_manifest('海辺の修理工', tmp_path, '2026-09-19T00:00:00Z', profile)
    sub = manifest['scenes'][0]['cuts'][-1]
    assert sub['cut_contract']['cut_role'] == 'sub'
    assert sub['selector'] in selectors
    assert script['scenes'][0]['cuts'][-1]['cut_contract']['cut_role'] == 'sub'
    for a, b in zip(script['scenes'][0]['cuts'], manifest['scenes'][0]['cuts']):
        assert a['cut_contract'] == b['cut_contract']
        assert b['cut_contract']['cut_handoff']['delivers_to_next']['expected_next_cut_selector'] != b['selector']
    assert not sub['cut_contract']['cut_handoff']['delivers_to_next']['expected_next_cut_selector']
    assert sub['image_generation']['character_ids'] == []
    assert sum(c['duration_seconds'] for c in manifest['scenes'][0]['cuts']) == script['scenes'][0]['target_duration_seconds']
    from toc.stage_evaluation.common import _cut_contract_structure_issues
    assert _cut_contract_structure_issues(sub['cut_contract']) == []
    compile_video_api_prompt_v1(cut_contract=sub['cut_contract'], video_generation=sub['video_generation'])
    (tmp_path / 'script.md').write_text(m._md_yaml('script', script))
    (tmp_path / 'video_manifest.md').write_text(m._md_yaml('manifest', manifest))
    from toc.stage_evaluation.pipeline import check_script_single, check_manifest_single
    for check in (check_script_single, check_manifest_single):
        result, _ = check(tmp_path)
        assert result['passed'], result


def test_generation_request_path_keeps_sub_references_and_silence(tmp_path):
    import yaml
    from test_image_prompt_compiler import _load_generate_assets_module
    generator = _load_generate_assets_module()
    _, cut = materialize_b_roll(proposal()['cuts'][0], selector='scene1_cut09', cut_id='09',
        location={'asset_id': 'loc_1', 'name': '工房', 'output': 'assets/loc.png'},
        duration=4, story_time='', time_of_day='day', previous_selector='scene1_cut08')
    document = {'video_metadata': {}, 'assets': {'character_bible': [{'character_id': 'person', 'reference_images': ['cast.png']}],
        'style_guide': {'reference_images': ['portrait.png']},
        'location_bible': [{'location_id': 'loc_1', 'reference_images': ['assets/loc.png']}]},
        'scenes': [{'scene_id': 1, 'time_of_day': 'day', 'cuts': [cut]}]}
    _, guides, scenes = generator.parse_manifest_yaml_full(yaml.safe_dump(document, allow_unicode=True))
    scene = scenes[0]
    generator.merge_asset_references_into_scene(scene=scene, guides=guides, character_refs_mode='all')
    assert scene.image_references == ['assets/loc.png']
    generator._validate_frozen_v2_payload_matches_plan(scene, cut['image_generation']['api_prompt_payload'])
    generator.validate_scene_narration(scenes=scenes, require=True, scene_filter=None)
    payload = generator._video_api_prompt_payload_for_scene(scene, prefix='', suffix='')
    assert '映り込み' in payload['prompt']
    targets = generator._build_video_render_targets(manifest=document, scenes=scenes)
    assert len(targets) == 1
    payload = generator._video_api_prompt_payload_for_target(targets[0], prefix='', suffix='')
    assert '映り込み' in payload['prompt']
    scene.image_references.append('cast.png')
    with pytest.raises(ValueError, match='b_roll'):
        generator.merge_asset_references_into_scene(scene=scene, guides=guides, character_refs_mode='all')


def test_b_roll_cannot_be_merged_into_character_clip():
    from toc.video_prompt_compiler import compose_video_render_unit_contract
    with pytest.raises(ValueError, match='separate_video_render_unit'):
        compose_video_render_unit_contract([{'cut_role': 'main'}, {'cut_role': 'sub'}])
