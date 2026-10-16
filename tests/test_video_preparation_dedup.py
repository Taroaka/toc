import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from server import cut_direction_api, image_gen_app, video_preparation_api
from toc import scene_direction_service
from toc.video_preparation_context import (
    compact_script_scene_against_context,
    review_source_context,
    scene_authoring_view,
    script_authoring_view,
)


def _pointer_get(value, pointer):
    current = value
    for part in pointer.split('/')[1:]:
        part = part.replace('~1', '/').replace('~0', '~')
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def _pointer_set(value, pointer, replacement):
    parts = pointer.split('/')[1:]
    current = value
    for encoded in parts[:-1]:
        part = encoded.replace('~1', '/').replace('~0', '~')
        current = current[int(part)] if isinstance(current, list) else current[part]
    final = parts[-1].replace('~1', '/').replace('~0', '~')
    if isinstance(current, list):
        current[int(final)] = replacement
    else:
        current[final] = replacement


def _source_and_current_scene():
    shared_a = {
        'selector': 'manifest-cut-a',
        'cut_id': '01',
        'authored_cut_id': 'authored-a',
        'cut_contract': {'required_action': 'place the first hat'},
        'shot_plan': {'shots': [{'selector': 'shot-a', 'initial_view': 'hands hold hat'}]},
        'audio': {'narration': {'text': 'The first hat is placed.', 'tts_text': 'The first hat is placed.'}},
        'duration_seconds': 4,
    }
    shared_b = {
        'selector': 'manifest-cut-b',
        'cut_id': '02',
        'authored_cut_id': 'authored-b',
        'cut_contract': {'required_action': 'place the second hat'},
        'shot_plan': {'shots': [{'selector': 'shot-b', 'initial_view': 'second hat in hands'}]},
        'audio': {'narration': {'text': 'The second hat is placed.', 'tts_text': 'The second hat is placed.'}},
        'duration_seconds': 5,
    }
    current = {
        'scene_id': 'scene-30',
        'scene_intent': 'The couple quietly completes the gift.',
        'scene_event': {'source/action': 'place the hats', 'reveal_order': ['one', 'two']},
        'cinematic_direction': {'camera_rule': 'hold on the hands', 'light': 'winter dawn'},
        'resource_bindings': [{'resource_id': 'hat', 'path': 'assets/objects/hat.png'}],
        'cuts': [copy.deepcopy(shared_a), copy.deepcopy(shared_b)],
    }

    # Deliberately reorder the source cuts and use mixed identifiers: cut A
    # matches only by authored_cut_id, while cut B matches by selector.
    source_b = copy.deepcopy(shared_b)
    source_b['cut_blueprint'] = {'source_only': 'keep this cut description'}
    source_b['narration_authoring'] = {'delivery': 'softly'}
    source_a = copy.deepcopy(shared_a)
    source_a['selector'] = 'script-cut-a'
    source_a['cut_id'] = 'source-01'
    source_a['cut_contract'] = {'required_action': 'script version differs'}
    source_a['cut_blueprint'] = {'source_only': 'retain the first authored beat'}
    source_a['narration_contract'] = {'must_preserve': 'first-hat reveal'}
    source = {
        'scene_id': 'scene-30',
        'scene_intent': current['scene_intent'],
        'scene_event': copy.deepcopy(current['scene_event']),
        'cinematic_direction': copy.deepcopy(current['cinematic_direction']),
        'resource_bindings': copy.deepcopy(current['resource_bindings']),
        'cuts': [source_b, source_a],
    }
    source['scene_event']['script_only'] = 'retain this source-only note'
    return source, current


def _script_document(scene):
    return {
        'schema_version': 'scene_event_v1',
        'script_metadata': {'topic': 'fixture', 'direction': 'preserve the order'},
        'human_change_requests': [{'note': 'keep the two reveals distinct'}],
        'asset_resolutions': [{'asset_id': 'hat', 'path': 'assets/objects/hat.png'}],
        'audio_story_plan': {'continuous_full_draft': 'The full narration draft remains.'},
        'narration_spans': [{'text': 'All authored narration stays available.'}],
        'scenes': [scene],
    }


def test_script_compaction_is_lossless_and_matches_cuts_by_identity():
    source_scene, current_scene = _source_and_current_scene()
    document = _script_document(source_scene)
    raw = json.dumps(document, ensure_ascii=False).encode('utf-8')
    original_document = copy.deepcopy(document)
    original_current = copy.deepcopy(current_scene)

    full_view = script_authoring_view(raw, 'scene-30')
    current_view = scene_authoring_view(current_scene)
    compacted = compact_script_scene_against_context(full_view, current_view)

    assert document == original_document
    assert current_scene == original_current
    assert compacted['script_metadata'] == document['script_metadata']
    assert compacted['human_change_requests'] == document['human_change_requests']
    assert compacted['asset_resolutions'] == document['asset_resolutions']
    assert compacted['audio_story_plan'] == document['audio_story_plan']
    assert compacted['narration_spans'] == document['narration_spans']
    assert compacted['scenes'][0]['scene_id'] == 'scene-30'
    assert compacted['scenes'][0]['scene_event']['script_only'] == 'retain this source-only note'
    assert [cut['selector'] for cut in compacted['scenes'][0]['cuts']] == [
        'manifest-cut-b', 'script-cut-a',
    ]
    assert compacted['scenes'][0]['cuts'][0]['cut_blueprint'] == source_scene['cuts'][0]['cut_blueprint']
    assert compacted['scenes'][0]['cuts'][1]['narration_contract'] == source_scene['cuts'][1]['narration_contract']
    assert compacted['scenes'][0]['cuts'][1]['cut_contract'] == source_scene['cuts'][1]['cut_contract']

    equivalences = compacted['selected_scene_equivalence_map']
    assert {
        'source_json_pointer': '/scenes/0/scene_event/source~1action',
        'context_json_pointer': '/scene/scene_event/source~1action',
    } in equivalences
    # The source list is reordered. The first source cut resolves by selector
    # to current index 1; the second resolves by authored_cut_id to current 0.
    assert {
        'source_json_pointer': '/scenes/0/cuts/0/cut_contract',
        'context_json_pointer': '/scene/cuts/1/cut_contract',
    } in equivalences
    assert {
        'source_json_pointer': '/scenes/0/cuts/1/shot_plan',
        'context_json_pointer': '/scene/cuts/0/shot_plan',
    } in equivalences
    assert not any(item['source_json_pointer'] == '/scenes/0/cuts/1/cut_contract'
                   for item in equivalences)
    assert compacted['context_scope'].startswith('The selected source-script scene is losslessly compacted')

    # Rehydrate every omitted source value from its explicit current-scene ref.
    reconstructed = copy.deepcopy(compacted)
    for item in equivalences:
        replacement = copy.deepcopy(_pointer_get(
            {'scene': current_view}, item['context_json_pointer'],
        ))
        _pointer_set(reconstructed, item['source_json_pointer'], replacement)
    assert reconstructed['scenes'][0] == full_view['scenes'][0]


def test_runtime_context_keeps_full_sources_resources_and_internal_hashes(monkeypatch, tmp_path):
    source_scene, current_scene = _source_and_current_scene()
    for cut in current_scene['cuts']:
        cut['duration_seconds'] = 4
    document = _script_document(source_scene)
    script_bytes = json.dumps(document, ensure_ascii=False).encode('utf-8')
    story = 'Complete story text. ' * 100
    resources = {'objects': {'hat': {'name': 'woven hat', 'references': ['assets/objects/hat.png']}}}
    direction = {'film_language': {'lens': '50mm', 'camera': 'patient'} }
    hashes = {'story.md': 's' * 64, 'script.md': 'p' * 64}

    def read_run_file(_root, name):
        if name == 'story.md':
            return story.encode('utf-8')
        if name == 'script.md':
            return script_bytes
        raise FileNotFoundError(name)

    monkeypatch.setattr(cut_direction_api, '_read_direction', lambda *_: (resources, direction, None))
    monkeypatch.setattr(video_preparation_api, 'read_run_file_bytes', read_run_file)
    monkeypatch.setattr(image_gen_app, '_narration_min_duration_seconds', lambda *_: 2.0)
    snapshot = {'boundaries': {'previous': {'scene_id': '20'}, 'next': {'scene_id': '40'}},
                'images': [], 'files': hashes}

    input_data = {'scenes': [current_scene]}
    original_data = copy.deepcopy(input_data)
    context = video_preparation_api.RuntimeHooks(tmp_path).context(
        input_data, 'scene-30', snapshot,
    )

    assert context['source_documents']['story.md'] == story
    assert context['source_documents']['script.md']['narration_spans'] == document['narration_spans']
    assert context['resources'] == resources
    assert context['film_language'] == direction['film_language']
    assert context['neighboring_scenes'] == snapshot['boundaries']
    assert context['file_hashes'] == hashes
    assert 'file_hashes' not in context['source_documents']['script.md']
    assert context['source_documents']['script.md']['selected_scene_equivalence_map']
    assert input_data == original_data

    image_context = video_preparation_api.RuntimeHooks(tmp_path, phase='images').context(
        input_data, 'scene-30', snapshot,
    )
    image_script = image_context['source_documents']['script.md']
    from toc.image_consistency import visual_inputs
    full_image_script = visual_inputs(script_authoring_view(script_bytes, 'scene-30'))
    assert 'narration_spans' not in image_script
    for item in image_script['selected_scene_equivalence_map']:
        assert _pointer_get(
            {'scene': image_context['scene']}, item['context_json_pointer'],
        ) == _pointer_get(full_image_script, item['source_json_pointer'])


def _large_context():
    shared_scene = {
        'scene_id': 'scene-30',
        'scene_intent': 'I' * 15_000,
        'scene_event': {'sequence': 'E' * 30_000},
        'cinematic_direction': {'visual_rule': 'D' * 45_000},
        'cuts': [],
    }
    for index in range(12):
        cut = {
            'selector': f'scene30_cut{index + 1:02d}',
            'cut_id': f'{index + 1:02d}',
            'authored_cut_id': f'authored-{index + 1}',
            'cut_contract': {'source_requirement': f'C{index}' + 'K' * 28_000},
            'shot_plan': {'shots': [{
                'selector': f'scene30_cut{index + 1:02d}_shot01',
                'initial_view': f'P{index}' + 'V' * 800,
            }]},
            'audio': {'narration': {
                'text': f'N{index}' + 'T' * 700,
                'tts_text': f'Q{index}' + 'U' * 700,
            }},
            'duration_seconds': 4,
            'cut_blueprint': {'source_only': f'keep authored cut {index}' + 'B' * 1_500},
            'narration_authoring': {'delivery': 'gentle', 'source_only': 'A' * 500},
        }
        shared_scene['cuts'].append(cut)
    source_scene = copy.deepcopy(shared_scene)
    current_scene = copy.deepcopy(shared_scene)
    # Runtime-only current shot material remains separately available.
    for index, cut in enumerate(current_scene['cuts']):
        cut.pop('cut_blueprint')
        cut.pop('narration_authoring')
        cut['shots'] = [{
            'selector': f'scene30_cut{index + 1:02d}_shot01',
            'render_note': 'R' * 1_500,
        }]
    document = {
        'schema_version': 'scene_event_v1',
        'script_metadata': {'topic': 'Kasa Jizo', 'notes': 'M' * 5_000},
        'human_change_requests': [{'note': 'keep the story order'}],
        'asset_resolutions': [{'asset_id': 'jizo', 'notes': 'X' * 3_000}],
        'audio_story_plan': {'continuous_full_draft': 'A' * 12_000},
        'narration_spans': [{'selector': f'span-{i}', 'text': 'S' * 1_000} for i in range(12)],
        'scenes': [source_scene],
    }
    raw = json.dumps(document, ensure_ascii=False).encode('utf-8')
    full_script = script_authoring_view(raw, 'scene-30')
    compact_script = compact_script_scene_against_context(
        full_script, scene_authoring_view(current_scene),
    )
    context = {
        'phase': 'video',
        'source_documents': {
            'story.md': 'Full story source. ' * 2_500,
            'script.md': compact_script,
        },
        'scene': scene_authoring_view(current_scene),
        'film_language': {'camera': 'patient', 'description': 'F' * 2_000},
        'resources': {'characters': {'jizo': {'description': 'J' * 5_000}}},
        'requested_target_video_model': None,
        'neighboring_scenes': {'previous': 'B' * 32_000, 'next': 'H' * 32_000},
        'effective_durations': {cut['selector']: 4 for cut in current_scene['cuts']},
        'audio_measurements': {cut['selector']: 3.5 for cut in current_scene['cuts']},
        'attached_images': [],
        'file_hashes': {'script.md': 'f' * 64},
    }
    full_context = copy.deepcopy(context)
    full_context['source_documents']['script.md'] = full_script
    return full_context, context


def test_deduplicated_author_prompt_is_below_limit_without_provider_call(monkeypatch, tmp_path):
    full_context, compact_context = _large_context()
    hooks = video_preparation_api.RuntimeHooks(tmp_path)
    provider_prompts = []

    async def fake_story_turn(**kwargs):
        provider_prompts.append(kwargs['prompt'])
        return SimpleNamespace(payload={'result_json': '{"status":"unchanged"}'})

    from toc import story_author_runtime
    monkeypatch.setattr(story_author_runtime, 'run_structured_story_turn', fake_story_turn)

    with pytest.raises(scene_direction_service.NeedsInput, match='上限'):
        asyncio.run(hooks.author(full_context, []))
    assert provider_prompts == []

    result = asyncio.run(hooks.author(compact_context, []))
    assert result == {'status': 'unchanged'}
    assert len(provider_prompts) == 1
    assert len(provider_prompts[0]) < 1_000_000
    assert 'selected_scene_equivalence_map' in provider_prompts[0]
    assert 'cut_blueprint' in provider_prompts[0]
    assert 'Full story source.' in provider_prompts[0]
    assert 'f' * 64 not in provider_prompts[0]


def test_internal_hashes_stay_out_of_author_prompt_and_review_context():
    hooks = video_preparation_api.RuntimeHooks('.')
    hashes = {'story.md': 's' * 64}
    seen = []

    async def capture(payload, images, expected_hashes):
        seen.append((payload, images, expected_hashes))
        return {'status': 'unchanged'}

    hooks._author = capture
    context = {
        'phase': 'video', 'scene': {'scene_id': 'scene-30'},
        'source_documents': {}, 'file_hashes': hashes,
        'prepared_image_hashes': {'assets/a.png': 'p' * 64},
    }
    asyncio.run(hooks.author(context, []))

    payload, images, expected_hashes = seen[0]
    assert 'file_hashes' not in payload['context']
    assert 'prepared_image_hashes' not in payload['context']
    assert expected_hashes is hashes
    assert images == []
    reviewed = review_source_context(context)
    assert 'file_hashes' not in reviewed
    assert 'prepared_image_hashes' not in reviewed

    review_input = {
        'scene': {'scene_id': 'scene-30'},
        'file_hashes': hashes,
        'prepared_image_hashes': {'assets/a.png': 'p' * 64},
        'neighboring_scenes': {'next': {'scene_id': 'scene-40'}},
        'source_documents': {'script.md': {
            'scenes': [{'scene_id': 'scene-30'}],
            'selected_scene_equivalence_map': [{'source_json_pointer': '/scenes/0/scene_id'}],
            'narration_spans': [{'text': 'global narration remains'}],
        }},
    }
    reviewed = review_source_context(review_input)
    assert 'scene' not in reviewed
    assert 'file_hashes' not in reviewed and 'prepared_image_hashes' not in reviewed
    assert 'scenes' not in reviewed['source_documents']['script.md']
    assert 'selected_scene_equivalence_map' not in reviewed['source_documents']['script.md']
    assert reviewed['source_documents']['script.md']['narration_spans'] == [
        {'text': 'global narration remains'},
    ]
