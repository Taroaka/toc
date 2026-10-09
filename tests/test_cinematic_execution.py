from copy import deepcopy

import pytest

from toc.cinematic_language import resolve_film_language, validate_film_language
from toc.p400_projection import project_scene
from toc.video_prompt_compiler import compile_video_api_prompt_v1
from test_p400_cinematic_author import sample
import asyncio
import json
from types import SimpleNamespace
from toc.p400_authoring import author_cinematic_direction


def film():
    return {'schema_version': 'film_language_v1', 'intent': '控えめな観察',
            'fields': {'palette': '低彩度の土色', 'lighting': '存在する光源だけを使う',
                       'texture': '使い込まれた素材の細かな凹凸', 'camera': '静かな手持ち'},
            'voices': {'keeper': '落ち着いた低い声'}}


def test_scoped_override_clear_and_provenance():
    result = resolve_film_language(film(), {'camera': '固定'}, {'palette': None})
    assert result['fields']['camera'] == '固定'
    assert 'palette' not in result['fields']
    assert result['origins']['camera'] == 'scene'
    assert result['origins']['palette'] == 'cut:clear'
    assert resolve_film_language(film(), {'palette': '  '})['fields']['palette'] == film()['fields']['palette']
    with pytest.raises(ValueError, match='unknown'):
        resolve_film_language(film(), {'unknown': 'ignored'})
    invalid = film(); invalid['schema_version'] = 'future'
    with pytest.raises(ValueError, match='version'):
        validate_film_language(invalid)


def test_projection_preserves_motion_light_focus_physics_and_native_audio(tmp_path):
    story, _, resources, scenes = sample(tmp_path)
    cut = scenes[0]['cuts'][0]
    cut['execution'] = {
        'light_continuity': '扉が開いても部屋全体を明るくしない',
        'focus': {'initial': '指先に焦点', 'change': '手が止まってから目へ焦点を移す'},
        'performance': {'action': '返事を待つ', 'observable_reaction': '息を止めて遅く一度瞬く', 'timing': '一拍待つ'},
        'physics': ['指が木に触れてから力が掛かる', '木が抵抗してから動く'],
        'native_audio': {'mode': 'natural_sound', 'sound_events': ['木が動く瞬間の軋み'], 'dialogue': []},
    }
    source = story['script']['scenes'][0]
    _, manifest = project_scene(scenes[0], source_scene=source, scene_id=10, resources=resources,
        scene_intent={}, scene_event=source, scene_generation={}, acceptance_draft={}, acceptance_binding={},
        film_language=film())
    projected = manifest['cuts'][0]
    image = projected['image_generation']['api_prompt_payload']['prompt']
    assert '低彩度の土色' in image and '指先に焦点' in image
    assert '手が止まってから目へ焦点を移す' not in image
    assert '木が抵抗してから動く' not in image
    assert projected['video_generation']['native_audio']['mode'] == 'natural_sound'
    payload = compile_video_api_prompt_v1(cut_contract=projected['cut_contract'],
        tool='higgsfield', duration_seconds=5, first_frame='assets/scenes/start.png',
        execution_options={'model': 'bytedance/seedance-2.5/image-to-video', 'generate_audio': True})
    prompt = payload['prompt']
    for expected in ['扉が開いても部屋全体を明るくしない', '手が止まってから目へ焦点を移す',
                     '息を止めて遅く一度瞬く', '木が抵抗してから動く', '木が動く瞬間の軋み']:
        assert expected in prompt
    assert 'keeper' not in prompt
    assert payload['execution_compiler_version'] == 'cinematic_execution_compiler_v1'
    assert payload['projection_contract']['execution_projection_version'] == 'cinematic_execution_projection_v1'
    from toc.video_prompt_projection_registry import rule_for_source_key
    assert rule_for_source_key('cut.cut_contract.cinematic_contract.execution.physics').target_group == 'primary_motion'
    changed = deepcopy(projected['cut_contract'])
    changed['cinematic_contract']['execution']['light_continuity'] = '灯りは消える'
    other = compile_video_api_prompt_v1(cut_contract=changed, tool='higgsfield', duration_seconds=5,
        first_frame='assets/scenes/start.png', execution_options={'generate_audio': True})
    assert payload['source_digest'] != other['source_digest']


def test_dialogue_requires_bound_speaker_and_beat(tmp_path):
    story, _, resources, scenes = sample(tmp_path)
    scenes[0]['cuts'][0]['execution'] = {'native_audio': {'mode': 'dialogue_and_sound',
        'sound_events': [], 'dialogue': [{'speaker_id': 'stranger', 'text': '待って',
        'source_beat_ids': ['open'], 'delivery': '低く一度だけ'}]}}
    with pytest.raises(ValueError, match='speaker'):
        project_scene(scenes[0], source_scene=story['script']['scenes'][0], scene_id=10, resources=resources,
            scene_intent={}, scene_event=story['script']['scenes'][0], scene_generation={},
            acceptance_draft={}, acceptance_binding={}, film_language=film())


def test_dialogue_requires_source_speech_and_camera_shape_is_repairable(tmp_path):
    from toc.cinematic_language import execution_from_cut
    from toc.p400_authoring import validate_scene_direction
    story, _, resources, scenes = sample(tmp_path)
    cut = scenes[0]['cuts'][0]
    cut['execution'] = {'native_audio': {'mode': 'dialogue_and_sound', 'sound_events': [],
        'dialogue': [{'speaker_id': 'keeper', 'text': '待って', 'source_quote': '待って', 'source_beat_ids': ['open']}]}}
    with pytest.raises(ValueError, match='source_quote'):
        execution_from_cut(cut, resources=resources, source_beats=story['script']['scenes'][0]['event_sequence'])
    beat = story['script']['scenes'][0]['event_sequence'][0]
    beat['what_happens'] = '待って'
    with pytest.raises(ValueError, match='source_quote'):
        execution_from_cut(cut, resources=resources, source_beats=[beat])
    beat['dialogue'] = [{'speaker': '修理工', 'text': '待って'}]
    assert execution_from_cut(cut, resources=resources, source_beats=[beat])['native_audio']['dialogue'][0]['text'] == '待って'
    beat['dialogue'][0]['speaker'] = '別の人物'
    with pytest.raises(ValueError, match='source_quote'):
        execution_from_cut(cut, resources=resources, source_beats=[beat])
    cut['execution'] = {}; cut['camera'] = []
    errors = validate_scene_direction(scenes[0], story['script']['scenes'][0], resources)
    assert any('camera_required' in error for error in errors)


def test_execution_diagnostic_repairs_only_execution_field(tmp_path):
    from toc.downstream_repair import semantic_direction_diagnostics
    _, _, _, scenes = sample(tmp_path)
    scenes[0]['cuts'][0]['execution'] = {'native_audio': {'mode': 'wrong'}}
    issues = semantic_direction_diagnostics(scenes[0], ['quiet:cut[0]:execution_invalid:cinematic:native_audio:mode_invalid'])
    assert [issue['path'] for issue in issues] == ['/cuts/0/execution']


def test_metric_geometry_reaches_still_and_video_without_internal_asset_ids(tmp_path):
    story, _, resources, scenes = sample(tmp_path)
    scenes[0]['cuts'][0]['execution'] = {'geometry': {'schema_version': 'shot_geometry_v1',
        'camera': {'position': [0,-5,1.4], 'target': [0,0,1], 'vertical_fov_degrees': 48, 'aspect_ratio': 16/9},
        'subjects': [{'asset_id': 'keeper', 'name': 'ignored', 'position': [0,0,.9], 'size': [.6,.4,1.8]}], 'lights': []}}
    _, manifest = project_scene(scenes[0], source_scene=story['script']['scenes'][0], scene_id=10, resources=resources,
        scene_intent={}, scene_event=story['script']['scenes'][0], scene_generation={},
        acceptance_draft={}, acceptance_binding={})
    cut = manifest['cuts'][0]
    still = cut['image_generation']['api_prompt_payload']['prompt']
    motion = compile_video_api_prompt_v1(cut_contract=cut['cut_contract'], tool='higgsfield',
        duration_seconds=8, first_frame='assets/scenes/start.png')['prompt']
    for prompt in (still, motion):
        assert '修理工' in prompt and '48' in prompt and '開始時の撮影配置' in prompt
        assert 'keeper' not in prompt and 'ignored' not in prompt


def test_film_language_authored_once_shared_and_resumed(tmp_path):
    _, _, resources, scenes = sample(tmp_path)
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs['prompt'])
        payload = film() if len(calls) == 1 else scenes[len(calls) - 2]
        return SimpleNamespace(payload={'result_json': json.dumps(payload)}, transcript=(),
            provenance=SimpleNamespace(as_dict=lambda: {}))
    async def run():
        return await author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='',
            client_factory=lambda: None, turn_runner=turn, enable_film_language=True)
    result = asyncio.run(run())
    assert result['film_language'] == film()
    assert len(calls) == 3
    assert all('低彩度の土色' in text for text in calls[1:])
    assert asyncio.run(run()) == result
    assert len(calls) == 3


def test_user_preferences_are_input_and_part_of_source_freshness(tmp_path):
    from toc.p400_authoring import load_direction
    _, _, resources, scenes = sample(tmp_path)
    (tmp_path / 'cinematic_preferences.md').write_text('明るい自然光で観察する')
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs['prompt'])
        return SimpleNamespace(payload={'result_json': json.dumps(film() if len(calls) == 1 else scenes[len(calls)-2])},
            transcript=(), provenance=SimpleNamespace(as_dict=lambda: {}))
    asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='',
        client_factory=lambda: None, turn_runner=turn, enable_film_language=True))
    assert '明るい自然光で観察する' in calls[0]
    load_direction(tmp_path)
    (tmp_path / 'cinematic_preferences.md').write_text('逆光を使う')
    with pytest.raises(RuntimeError, match='source_stale'):
        load_direction(tmp_path)


@pytest.mark.parametrize('initial', ['', '自然光'])
def test_preferences_change_invalidates_prepared_rebuild(tmp_path, initial):
    from test_p400_rebuild import P400RebuildTests
    from toc.p400_rebuild import prepare_p400_rebuild, apply_p400_rebuild, P400RebuildError
    fixtures = P400RebuildTests()
    run = fixtures._run_fixture(tmp_path)
    if initial:
        (run / 'cinematic_preferences.md').write_text(initial)
    plan = prepare_p400_rebuild(repo_root=tmp_path, run_dir=run, checkpoint_id='pref-check',
        generation_id='pref-candidate', candidate_builder=fixtures._candidate)
    (run / 'cinematic_preferences.md').write_text('新しい撮影方針')
    with pytest.raises(P400RebuildError):
        apply_p400_rebuild(plan, plan_token=plan.plan_token)
