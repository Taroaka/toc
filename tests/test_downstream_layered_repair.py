import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from toc.downstream_repair import apply_patch, patch_schema, visual_diagnostics, direction_diagnostics
from toc.downstream_repair import semantic_direction_diagnostics
from toc.downstream_repair import projection_diagnostics
from toc.production_repair import digest
from toc.visual_value_authoring import author_visual_value
from toc.p400_authoring import author_cinematic_direction
from test_p400_cinematic_author import sample
from test_p400_cinematic_author import source_entry_variant_sample
from test_visual_value_source_first import inputs


def response(payload):
    return SimpleNamespace(payload=payload, transcript=(), provenance=SimpleNamespace(as_dict=lambda: {}))


def patch(base, diagnostics, values):
    return {'unit_id': base.get('scene_id', 'visual_value'), 'base_digest': digest(base), 'operations': [
        {'path': path, 'value': json.dumps(value) if isinstance(value, dict) or (isinstance(value, list) and any(not isinstance(v, str) for v in value)) else value} for path, value in values.items()]}


def test_visual_bad_item_diagnostic_and_exact_patch(tmp_path):
    story, research, _, draft = inputs(tmp_path)
    for row in draft['scene_visual_values']:
        row['boundary_b_roll'] = {'reason': 'direct', 'cuts': []}
    draft['scene_visual_values'][0]['notes'] = ['kept', 7]
    diagnostics = visual_diagnostics(draft, story, research)
    path = '/scene_visual_values/0/notes/1'
    assert [d['path'] for d in diagnostics] == [path]
    assert diagnostics[0]['current_value'] == 7
    fixed = apply_patch(draft, diagnostics, patch(draft, diagnostics, {path: 'corrected'}))
    assert fixed['scene_visual_values'][0]['notes'] == ['kept', 'corrected']
    assert draft['scene_visual_values'][0]['notes'][1] == 7
    with pytest.raises(ValueError):
        apply_patch(draft, diagnostics, patch(draft, diagnostics, {'/scene_visual_values/1/notes': []}))
    with pytest.raises(ValueError):
        apply_patch(draft, diagnostics, patch(draft, diagnostics, {path: False}))
    schema = patch_schema(diagnostics, draft)
    assert schema['additionalProperties'] is False


def test_variant_entry_repair_is_scoped_to_the_cut_reference_list(tmp_path):
    from toc.p400_authoring import validate_scene_direction
    story, _, resources, scenes = source_entry_variant_sample(tmp_path)
    good = scenes[0]
    bad = deepcopy(good)
    del bad['cuts'][1]['state_variant_refs'][0]['source_entry']
    errors = validate_scene_direction(bad, story['script']['scenes'][0], resources)
    diagnostics = semantic_direction_diagnostics(bad, errors, story['script']['scenes'][0])
    path = '/cuts/1/state_variant_refs'
    assert [issue['path'] for issue in diagnostics] == [path]
    fixed = apply_patch(bad, diagnostics, patch(bad, diagnostics, {path: good['cuts'][1]['state_variant_refs']}))
    assert fixed == good
    assert validate_scene_direction(fixed, story['script']['scenes'][0], resources) == []
    with pytest.raises(ValueError, match='outside diagnostic scope'):
        apply_patch(bad, diagnostics, patch(bad, diagnostics, {'/cuts/0': good['cuts'][0]}))
    from toc.downstream_repair import UnscopedRepairError
    with pytest.raises(UnscopedRepairError):
        semantic_direction_diagnostics(bad, ['quiet:cut[1]:state_variant_refs[0]:unknown_failure'])


def test_variant_entry_is_repaired_by_normal_authoring_without_rewriting_scenes(tmp_path):
    _, _, resources, scenes = source_entry_variant_sample(tmp_path)
    bad = deepcopy(scenes[0])
    del bad['cuts'][1]['state_variant_refs'][0]['source_entry']
    calls = []

    async def turn(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1: return response({'result_json': json.dumps(bad)})
        if len(calls) == 2:
            request = json.loads(kwargs['prompt'])
            path = '/cuts/1/state_variant_refs'
            assert [d['path'] for d in request['diagnostics']] == [path]
            return response(patch(bad, [], {path: scenes[0]['cuts'][1]['state_variant_refs']}))
        return response({'result_json': json.dumps(scenes[1])})

    result = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources,
        grounding='', client_factory=lambda: None, turn_runner=turn))
    assert result['scenes'] == scenes
    assert len(calls) == 3


def test_p330_syntax_repair_without_new_llm_call(tmp_path):
    _, _, raw, draft = inputs(tmp_path)
    for row in draft['scene_visual_values']:
        row['boundary_b_roll'] = {'reason': 'direct', 'cuts': []}
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs)
        return response({'result_json': json.dumps(draft) + '}'})
    asyncio.run(author_visual_value(run_dir=tmp_path, grounding='', client_factory=lambda: None, turn_runner=turn))
    assert len(calls) == 1
    assert (tmp_path / 'story.md').read_bytes() == raw['story']
    assert any('one_redundant_closing_brace' in p.read_text() for p in (tmp_path / 'logs/authoring/visual_value').glob('*.json'))


def test_p330_uses_direct_patch_schema_and_preserves_media(tmp_path):
    story, research, _, draft = inputs(tmp_path)
    for row in draft['scene_visual_values']:
        row['boundary_b_roll'] = {'reason': 'direct', 'cuts': []}
    draft['scene_visual_values'][0]['notes'] = 7
    media = tmp_path / 'kept.png'; media.write_bytes(b'original image')
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return response({'result_json': json.dumps(draft)})
        assert 'operations' in kwargs['output_schema']['properties']
        assert '映像設計担当' not in kwargs['prompt']
        assert kwargs['model'] == 'gpt-6-luna'
        return response(patch(draft, [], {'/scene_visual_values/0/notes': ['fixed']}))
    result = asyncio.run(author_visual_value(run_dir=tmp_path, grounding='', client_factory=lambda: None, turn_runner=turn))
    assert len(calls) == 2
    assert result['scene_visual_values'][1] == draft['scene_visual_values'][1]
    assert media.read_bytes() == b'original image'


def test_p420_id_patch_preserves_other_fields(tmp_path):
    story, _, resources, scenes = sample(tmp_path)
    bad = deepcopy(scenes[0]); bad['cuts'][0]['character_ids'] = ['wrong']
    diagnostics = direction_diagnostics(bad, story['script']['scenes'][0], resources)
    d = next(d for d in diagnostics if d['path'] == '/cuts/0/character_ids/0')
    assert d['reference_candidates'][0]['id'] == 'keeper'
    assert d['reference_candidates'][0]['name'] == '修理工'
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1: return response({'result_json': json.dumps(bad)})
        if len(calls) == 2:
            assert 'operations' in kwargs['output_schema']['properties']
            return response(patch(bad, [], {'/cuts/0/character_ids/0': 'keeper'}))
        return response({'result_json': json.dumps(scenes[1])})
    result = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='', client_factory=lambda: None, turn_runner=turn))
    assert result['scenes'] == scenes
    assert len(calls) == 3


def test_cut_id_repair_also_diagnoses_shot_actor_subject_target_and_events(tmp_path):
    from test_shot_direction import plan
    from toc.shot_direction import normalize_shot_plan
    story, _, resources, scenes = sample(tmp_path)
    bad = deepcopy(scenes[0]); cut = bad['cuts'][0]
    cut['character_ids'] = ['stale']
    cut['shot_plan'] = plan(4)
    shot = cut['shot_plan']['shots'][0]
    shot['initial_view']['subjects'][0]['entity_id'] = 'stale'
    shot['performance'][0]['actor_id'] = 'stale'
    shot['performance'][0]['target_id'] = 'stale'
    shot['events'] = [{'kind': 'leave_frame', 'entity_ids': ['stale'], 'description': '立ち去る', 'trigger': None}]
    diagnostics = direction_diagnostics(bad, story['script']['scenes'][0], resources)
    paths = {d['path'] for d in diagnostics}
    expected = {'/cuts/0/character_ids/0',
        '/cuts/0/shot_plan/shots/0/initial_view/subjects/0/entity_id',
        '/cuts/0/shot_plan/shots/0/performance/0/actor_id',
        '/cuts/0/shot_plan/shots/0/performance/0/target_id',
        '/cuts/0/shot_plan/shots/0/events/0/entity_ids/0'}
    assert expected <= paths
    values = {path: 'keeper' for path in expected}
    fixed = apply_patch(bad, diagnostics, patch(bad, diagnostics, values))
    normalize_shot_plan(fixed['cuts'][0]['shot_plan'], character_ids=['keeper'], object_ids=[], duration_seconds=4)
    assert fixed['cuts'][1] == bad['cuts'][1]
    assert fixed['cuts'][0]['narration'] == bad['cuts'][0]['narration']


def test_shot_ids_are_restricted_to_current_cut_and_structural_errors_are_scoped(tmp_path):
    from test_shot_direction import plan
    story, _, resources, scenes = sample(tmp_path)
    resources['characters']['other'] = {'name': '別人', 'references': []}
    row = deepcopy(scenes[0]); row['cuts'][0]['shot_plan'] = plan(4)
    row['cuts'][0]['shot_plan']['shots'][0]['performance'][0]['actor_id'] = 'other'
    diagnostics = direction_diagnostics(row, story['script']['scenes'][0], resources)
    issue = next(d for d in diagnostics if d['path'].endswith('/actor_id'))
    assert issue['expected']['enum'] == ['keeper']
    assert semantic_direction_diagnostics(row, ['quiet:cut[0]:shot_direction:timeline_total_mismatch'])[0]['path'] == '/cuts/0/shot_plan'

    row['cuts'][0]['shot_plan']['shots'][0]['performance'][0]['actor_id'] = 'keeper'
    row['cuts'][0]['shot_plan']['shots'][0]['performance'][0]['target_id'] = 'other'
    diagnostics = direction_diagnostics(row, story['script']['scenes'][0], resources)
    path = '/cuts/0/shot_plan/shots/0/performance/0/target_id'
    repaired = apply_patch(row, diagnostics, patch(row, diagnostics, {path: None}))
    assert repaired['cuts'][0]['shot_plan']['shots'][0]['performance'][0]['target_id'] is None
    assert len(repaired['cuts'][0]['shot_plan']['shots'][0]['performance']) == 1


def test_unknown_shot_target_is_repaired_in_normal_authoring_loop(tmp_path):
    from test_shot_direction import plan
    _, _, resources, scenes = sample(tmp_path)
    scenes[0]['cuts'][0]['shot_plan'] = plan(4)
    bad = deepcopy(scenes[0])
    bad['cuts'][0]['shot_plan']['shots'][0]['performance'][0]['target_id'] = 'stale'
    calls = []

    async def turn(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return response({'result_json': json.dumps(bad)})
        if len(calls) == 2:
            request = json.loads(kwargs['prompt'])
            path = '/cuts/0/shot_plan/shots/0/performance/0/target_id'
            assert [d['path'] for d in request['diagnostics']] == [path]
            return response(patch(bad, [], {path: None}))
        return response({'result_json': json.dumps(scenes[1])})

    result = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources,
        grounding='', client_factory=lambda: None, turn_runner=turn))
    assert result['scenes'] == scenes
    assert len(calls) == 3


def test_child_image_failure_repairs_only_actual_frame_description(tmp_path):
    from test_shot_direction import plan
    story, _, registry, scenes = sample(tmp_path)
    registry['objects']['parcel'] = {'name': '小包', 'references': ['assets/objects/parcel.png']}
    row = deepcopy(scenes[0]); cut = row['cuts'][0]
    cut['object_ids'] = ['parcel']
    cut['shot_plan'] = plan()
    cut['shot_plan']['shots'][0]['initial_view']['subjects'].append({
        'entity_id': 'parcel', 'kind': 'object', 'member_id': None,
        'visible_parts': ['外形'], 'view': '前cutから同じ向きで保つ',
    })
    cut['first_frame_brief'] = '前sceneから同じ状態を引き継ぐ'
    cut['shot_plan']['shots'][0]['initial_view']['description'] = '前sceneから同じ状態を引き継ぐ'
    issues = projection_diagnostics(row, story['script']['scenes'][0], registry)
    path = '/cuts/0/shot_plan/shots/0/initial_view/description'
    assert [issue['path'] for issue in issues] == [path]
    fixed = apply_patch(row, issues, patch(row, issues, {path: '作業者の足と、その横の床に置かれた小包。上面と角が見える。'}))
    assert fixed['cuts'][1] == row['cuts'][1]
    assert not projection_diagnostics(fixed, story['script']['scenes'][0], registry)


@pytest.mark.parametrize('shot_index,view_field,state_source', [
    (0, 'initial_view', 'result'), (0, 'end_view', 'result'), (0, 'initial_view', 'previous_end'),
    (1, 'initial_view', 'result'), (1, 'end_view', 'result'),
])
def test_shot_state_projection_diagnostic_is_limited_to_state_source(tmp_path, shot_index, view_field, state_source):
    from test_shot_direction import plan
    story, _, registry, scenes = sample(tmp_path)
    row = deepcopy(scenes[0])
    row['cuts'][0]['shot_plan'] = plan(2 if shot_index else 4)
    shots = row['cuts'][0]['shot_plan']['shots']
    if shot_index:
        second = deepcopy(shots[0])
        second.update(shot_id='b', start_seconds=2)
        shots.append(second)
    shot = shots[shot_index]
    if view_field == 'end_view':
        shot['end_view'] = deepcopy(shot['initial_view'])
    shot[view_field]['state_source'] = state_source
    before = deepcopy(row)
    issues = projection_diagnostics(row, story['script']['scenes'][0], registry)
    if view_field == 'end_view':
        # An ordinary end view has no parent state variant to select early.
        assert issues == []
        assert row == before
        return
    path = f'/cuts/0/shot_plan/shots/{shot_index}/{view_field}/state_source'
    assert [issue['path'] for issue in issues] == [path]
    assert issues[0]['expected']['enum'] == [None, 'start'] + (
        ['previous_end'] if shot_index and view_field == 'initial_view' else [])
    fixed = apply_patch(row, issues, patch(row, issues, {path: None}))
    assert not projection_diagnostics(fixed, story['script']['scenes'][0], registry)
    expected = deepcopy(before)
    expected['cuts'][0]['shot_plan']['shots'][shot_index][view_field]['state_source'] = None
    assert fixed == expected
    assert row == before
    with pytest.raises(ValueError):
        apply_patch(row, issues, patch(row, issues, {'/cuts/1/narration': 'unrelated'}))


def test_shot_state_projection_error_returns_to_normal_authoring_repair(tmp_path):
    from test_shot_direction import plan
    _, _, registry, scenes = sample(tmp_path)
    scenes[0]['cuts'][0]['shot_plan'] = plan(4)
    scenes[0]['cuts'][0]['shot_plan']['shots'][0]['initial_view']['state_source'] = None
    bad = deepcopy(scenes[0])
    bad['cuts'][0]['shot_plan']['shots'][0]['initial_view']['state_source'] = 'result'
    calls = []

    async def turn(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return response({'result_json': json.dumps(bad)})
        if len(calls) == 2:
            request = json.loads(kwargs['prompt'])
            path = '/cuts/0/shot_plan/shots/0/initial_view/state_source'
            assert [d['path'] for d in request['diagnostics']] == [path]
            return response(patch(bad, [], {path: None}))
        return response({'result_json': json.dumps(scenes[1])})

    result = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=registry,
        grounding='', client_factory=lambda: None, turn_runner=turn))
    assert result['scenes'] == scenes
    assert len(calls) == 3
    ledger = json.loads((tmp_path / 'logs/repair/ledger.json').read_text())
    assert len(ledger['events']) == 1
    assert not ledger['pending']


@pytest.mark.parametrize('payload', [{'result_json': '{"broken":'}, None])
def test_syntax_and_transport_never_resend_author_prompt(tmp_path, payload):
    inputs(tmp_path)
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs)
        if payload is None: raise RuntimeError('authentication failed')
        return response(payload)
    with pytest.raises(RuntimeError):
        asyncio.run(author_visual_value(run_dir=tmp_path, grounding='', client_factory=lambda: None, turn_runner=turn))
    assert len(calls) == 1


def test_semantic_cut_rewrite_keeps_healthy_cut_and_uses_original_validator(tmp_path):
    _, _, resources, scenes = sample(tmp_path)
    bad = deepcopy(scenes[0]); bad['cuts'][0]['camera']['light'] = '朝日または昼光'
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1: return response({'result_json': json.dumps(bad)})
        if len(calls) == 2:
            request = json.loads(kwargs['prompt'])
            assert [d['path'] for d in request['diagnostics']] == ['/cuts/0']
            assert request['diagnostics'][0]['kind'] == 'semantic'
            assert kwargs['model'] == 'gpt-6-astra'
            return response(patch(bad, [], {'/cuts/0': scenes[0]['cuts'][0]}))
        return response({'result_json': json.dumps(scenes[1])})
    doc = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='', client_factory=lambda: None, turn_runner=turn))
    assert doc['scenes'] == scenes
    assert len(calls) == 3


def test_bad_patch_stays_patch_and_does_not_promote_all_scenes(tmp_path):
    _, _, resources, scenes = sample(tmp_path)
    bad = deepcopy(scenes[1]); bad['cuts'][0]['duration_seconds'] = 0
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1: return response({'result_json': json.dumps(scenes[0])})
        if len(calls) == 2: return response({'result_json': json.dumps(bad)})
        assert 'operations' in kwargs['output_schema']['properties']
        if len(calls) == 3:
            return response(patch(bad, [], {'/direction': 'unauthorized'}))
        assert 'outside diagnostic scope' in kwargs['prompt']
        return response(patch(bad, [], {'/cuts/0/duration_seconds': 8}))
    doc = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='', client_factory=lambda: None, turn_runner=turn))
    assert doc['scenes'] == scenes
    assert len(calls) == 4


def test_repeated_syntax_failure_uses_saved_candidate_without_regeneration(tmp_path):
    inputs(tmp_path)
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs)
        return response({'result_json': '{"incomplete":'})
    for _ in range(2):
        with pytest.raises(RuntimeError):
            asyncio.run(author_visual_value(run_dir=tmp_path, grounding='', client_factory=lambda: None, turn_runner=turn))
    assert len(calls) == 1
    assert json.loads((tmp_path/'logs/authoring/visual_value/validation.json').read_text())['kind'] == 'syntax'


def test_resume_repair_keeps_accepted_scene_and_durable_budget(tmp_path):
    _, _, resources, scenes = sample(tmp_path)
    bad = deepcopy(scenes[1]); bad['cuts'][0]['duration_seconds'] = 0
    calls = []
    async def fail(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1: return response({'result_json': json.dumps(scenes[0])})
        if len(calls) == 2: return response({'result_json': json.dumps(bad)})
        raise RuntimeError('network disconnected')
    with pytest.raises(RuntimeError, match='network'):
        asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='', client_factory=lambda: None, turn_runner=fail))
    before = json.loads((tmp_path/'logs/repair/ledger.json').read_text())
    async def finish(**kwargs):
        calls.append(kwargs)
        assert 'operations' in kwargs['output_schema']['properties']
        return response(patch(bad, [], {'/cuts/0/duration_seconds': 8}))
    doc = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='', client_factory=lambda: None, turn_runner=finish))
    after = json.loads((tmp_path/'logs/repair/ledger.json').read_text())
    assert len(after['events']) > len(before['events'])
    assert doc['scenes'] == scenes
    assert len(calls) == 4


def test_projection_only_reentry_does_not_regenerate_cinematic_scenes(tmp_path):
    _, _, resources, scenes = sample(tmp_path)
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs)
        return response({'result_json': json.dumps(scenes[len(calls)-1])})
    options = dict(run_dir=tmp_path, resources=resources, grounding='', client_factory=lambda: None, turn_runner=turn)
    asyncio.run(author_cinematic_direction(**options))
    # A repaired p330 boundary must not rerun every healthy p420 scene.
    (tmp_path/'visual_value.md').write_text('{"changed_boundary":true}')
    doc = asyncio.run(author_cinematic_direction(**options))
    assert len(calls) == 2
    assert doc['scenes'] == scenes


@pytest.mark.parametrize('fault', ['extra', 'root', 'overlap', 'duplicate', 'digest', 'noop', 'nan', 'duplicate_value_key'])
def test_patch_rejects_adversarial_operations_without_mutation(fault):
    from toc.downstream_repair import Diagnostics
    base = {'unit': {'value': 2}, 'healthy': 'kept'}
    d = Diagnostics(base); d.add('/unit/value', {'type': 'integer'})
    value = patch(base, d.items, {'/unit/value': 3})
    if fault == 'extra': value['document'] = base
    if fault == 'root': value['operations'][0]['path'] = ''
    if fault == 'overlap':
        d.add('/unit', {'type': 'object'}, kind='semantic')
        value['operations'].append({'path': '/unit', 'value': '{"value":4}'})
    if fault == 'duplicate': value['operations'] *= 2
    if fault == 'digest': value['base_digest'] = 'other'
    if fault == 'noop': value['operations'][0]['value'] = 2
    if fault == 'nan': value['operations'][0]['value'] = 'NaN'
    if fault == 'duplicate_value_key': value['operations'][0]['value'] = '3,"value":4'
    with pytest.raises(ValueError): apply_patch(base, d.items, value)
    assert base == {'unit': {'value': 2}, 'healthy': 'kept'}


def test_asset_pointer_repair_does_not_rewrite_cut_or_other_request(tmp_path):
    from test_p420_asset_requests import fixture
    story, sources, resources, scenes = fixture(tmp_path)
    for name, raw in sources.items(): (tmp_path/f'{name}.md').write_bytes(raw)
    bad = deepcopy(scenes[0]); bad['asset_requests'][0]['source_entity']['pointer'] = '/missing'
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1: return response({'result_json': json.dumps(bad)})
        if len(calls) == 2:
            data = json.loads(kwargs['prompt'])
            path = '/asset_requests/0/source_entity/pointer'
            assert [d['path'] for d in data['diagnostics']] == [path]
            return response(patch(bad, [], {path: '/source_passages/0/text'}))
        return response({'result_json': json.dumps(scenes[1])})
    doc = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='', client_factory=lambda: None, turn_runner=turn))
    assert doc['scenes'][0]['asset_requests'] == scenes[0]['asset_requests']
    assert doc['scenes'][0]['cuts'][1] == scenes[0]['cuts'][1]
    assert len(calls) == 3


def test_saved_asset_resolution_is_reused_without_reference_repair(tmp_path):
    from test_p420_asset_requests import fixture
    _, sources, resources, scenes = fixture(tmp_path)
    for name, raw in sources.items(): (tmp_path/f'{name}.md').write_bytes(raw)
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs)
        assert len(calls) <= 2, 'healthy resolved asset must not need LLM repair'
        return response({'result_json': json.dumps(scenes[len(calls)-1])})
    options = dict(run_dir=tmp_path, resources=resources, grounding='', client_factory=lambda: None, turn_runner=turn)
    first = asyncio.run(author_cinematic_direction(**options))
    second = asyncio.run(author_cinematic_direction(**options))
    assert first == second
    assert len(calls) == 2


def test_asset_semantic_repair_receives_actual_evidence(tmp_path):
    from test_p420_asset_requests import fixture
    _, sources, resources, scenes = fixture(tmp_path)
    for name, raw in sources.items(): (tmp_path/f'{name}.md').write_bytes(raw)
    bad = deepcopy(scenes[0]); bad['asset_requests'][0]['source_evidence'][0]['quote'] = 'fabricated quote'
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1: return response({'result_json': json.dumps(bad)})
        if len(calls) == 2:
            data = json.loads(kwargs['prompt'])
            path = '/asset_requests/0'
            assert [d['path'] for d in data['diagnostics']] == [path]
            assert any(r['value'] == '修理工が手紙を読む。' for r in data['context']['source_references'])
            return response(patch(bad, [], {path: scenes[0]['asset_requests'][0]}))
        return response({'result_json': json.dumps(scenes[1])})
    doc = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='', client_factory=lambda: None, turn_runner=turn))
    assert doc['scenes'][0]['asset_requests'] == scenes[0]['asset_requests']


def test_p330_comma_syntax_patch_never_resends_creative_prompt(tmp_path):
    _, _, _, draft = inputs(tmp_path)
    for row in draft['scene_visual_values']:
        row['boundary_b_roll'] = {'reason': 'direct', 'cuts': []}
    raw = json.dumps(draft)
    pos = raw.index(', "notes"')
    broken = raw[:pos] + raw[pos+1:]
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1: return response({'result_json': broken})
        assert json.loads(kwargs['prompt'])['task'] == 'JSON syntax repair only'
        assert 'edits' in kwargs['output_schema']['properties']
        assert kwargs['model'] == 'gpt-6-luna'
        return response({'edits': [{'start': pos, 'end': pos, 'replacement': ','}]})
    result = asyncio.run(author_visual_value(run_dir=tmp_path, grounding='', client_factory=lambda: None, turn_runner=turn))
    assert result['scene_visual_values'] == draft['scene_visual_values']
    assert len(calls) == 2


def test_only_invalid_optional_asset_reference_can_be_removed(tmp_path):
    story, _, resources, scenes = sample(tmp_path)
    base = deepcopy(scenes[0]); base['cuts'][0]['character_ids'] = ['bad1', 'keeper', 'bad2']
    issues = direction_diagnostics(base, story['script']['scenes'][0], resources)
    values = {'/cuts/0/character_ids/0': None, '/cuts/0/character_ids/2': None}
    repaired = apply_patch(base, issues, patch(base, issues, values))
    assert repaired['cuts'][0]['character_ids'] == ['keeper']
    assert repaired['cuts'][1] == base['cuts'][1]
    with pytest.raises(ValueError):
        apply_patch(base, issues, patch(base, issues, {'/cuts/0/character_ids/1': None}))


def test_typed_schema_pins_base_and_value_type(tmp_path):
    story, _, resources, scenes = sample(tmp_path)
    base = deepcopy(scenes[0]); base['cuts'][0]['duration_seconds'] = 'four'
    issues = direction_diagnostics(base, story['script']['scenes'][0], resources)
    schema = patch_schema(issues, base)
    assert schema['properties']['base_digest']['enum'] == [digest(base)]
    operation = schema['properties']['operations']['items']['anyOf'][0]
    assert operation['properties']['value']['type'] == 'integer'
    assert 'value_json' not in operation['properties']


def test_p420_syntax_rejects_story_edit_then_accepts_comma_only(tmp_path):
    _, _, resources, scenes = sample(tmp_path)
    raw = json.dumps(scenes[0]); pos = raw.index(', "scene_id"')
    broken = raw[:pos] + raw[pos+1:]
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1: return response({'result_json': broken})
        if len(calls) == 2:
            return response({'edits': [{'start': 0, 'end': len(broken), 'replacement': json.dumps(scenes[1])}]})
        if len(calls) == 3:
            data = json.loads(kwargs['prompt'])
            assert data['task'] == 'JSON syntax repair only'
            assert data['patch_error']
            return response({'edits': [{'start': pos, 'end': pos, 'replacement': ','}]})
        return response({'result_json': json.dumps(scenes[1])})
    doc = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources, grounding='', client_factory=lambda: None, turn_runner=turn))
    assert doc['scenes'] == scenes
    assert len(calls) == 4


def test_removal_never_empties_list_or_removes_registered_out_of_scope_id(tmp_path):
    story, _, resources, scenes = sample(tmp_path)
    base = deepcopy(scenes[0]); base['cuts'][0]['character_ids'] = ['unknown']
    issues = direction_diagnostics(base, story['script']['scenes'][0], resources)
    with pytest.raises(ValueError, match='empty'):
        apply_patch(base, issues, patch(base, issues, {'/cuts/0/character_ids/0': None}))
    base['cuts'][0]['character_ids'] = ['keeper']
    resources['scene_assets'] = {'quiet': {'character_ids': [], 'object_ids': []}}
    issues = direction_diagnostics(base, story['script']['scenes'][0], resources)
    assert not next(i for i in issues if i['path'] == '/cuts/0/character_ids/0').get('allow_remove')
    with pytest.raises(ValueError, match='not authorized'):
        apply_patch(base, issues, patch(base, issues, {'/cuts/0/character_ids/0': None}))


def test_structured_patch_duplicate_keys_and_wrong_unit_rejected():
    from toc.downstream_repair import Diagnostics
    base = {'scene_id': 'unit', 'camera': None}
    d = Diagnostics(base); d.add('/camera', {'type': 'object'})
    candidate = patch(base, d.items, {'/camera': {'light': 'day'}})
    candidate['operations'][0]['value'] = '{"light":"day","light":"night"}'
    with pytest.raises(ValueError): apply_patch(base, d.items, candidate)
    candidate = patch(base, d.items, {'/camera': {'light': 'day'}})
    candidate['unit_id'] = 'other'
    with pytest.raises(ValueError): apply_patch(base, d.items, candidate)


def test_saved_patch_can_finish_after_cap_without_another_provider_call():
    from toc.downstream_repair import Diagnostics, repair_candidate
    from toc.production_repair import RepairSession
    base = {'scene_id': 'unit', 'value': 'wrong'}
    session = RepairSession(None, 'p420', stage_limit=1)
    saved, calls = [], []

    def diagnose(candidate):
        d = Diagnostics(candidate)
        d.refs('/value', {'right': {'name': 'registered'}})
        return d.items

    async def turn(*args):
        calls.append(1)
        return response(patch(base, [], {'/value': 'right'}))

    def interrupted_log(name, payload):
        if name == 'repair-response':
            saved.append(payload)
            raise RuntimeError('interrupted after durable response')

    with pytest.raises(RuntimeError, match='interrupted'):
        asyncio.run(repair_candidate(candidate=base, session=session, unit='unit', diagnose=diagnose,
            validate=lambda c: [], turn=turn, context={}, log=interrupted_log))
    assert session.used() == 1
    fixed = asyncio.run(repair_candidate(candidate=base, session=session, unit='unit', diagnose=diagnose,
        validate=lambda c: [], turn=turn, context={}, log=lambda *a: None, replay=lambda c, d: saved[0]))
    assert fixed['value'] == 'right'
    assert len(calls) == 1
    assert session.used() == 1


def test_applied_candidate_checkpoint_keeps_budget_and_dispatched_reservation():
    from toc.production_repair import RepairSession
    session = RepairSession(None, 'p420', stage_limit=1)
    session.feedback('unit', {'value': 'before'}, ['invalid'])
    session.claim('unit')
    session.checkpoint_candidate('unit', {'value': 'after'})
    assert session.pending('unit')['previous_output'] == {'value': 'after'}
    assert session.pending('unit')['dispatched'] is True
    assert session.used() == 1


@pytest.mark.parametrize('cycle_size', [2, 3])
@pytest.mark.parametrize('stage_limit', [1, 2])
def test_saved_patch_replay_cycles_return_to_budgeted_correction(cycle_size, stage_limit):
    from toc.downstream_repair import Diagnostics, repair_candidate
    from toc.production_repair import RepairSession, RepairExhausted
    base = {'scene_id': 'unit', 'value': 'state_0'}
    session = RepairSession(None, 'p420', stage_limit=stage_limit)
    session.feedback('unit', base, ['invalid'])
    session.claim('unit')
    calls, replays, logs = [], [], []

    def diagnose(candidate):
        d = Diagnostics(candidate)
        if candidate['value'] != 'valid':
            d.add('/value', {'type': 'string'}, code='invalid', kind='semantic')
        return d.items

    def replay(candidate, diagnostics):
        replays.append(candidate['value'])
        assert len(replays) <= cycle_size, 'saved replay escaped convergence checks'
        next_value = 'state_' + str((int(candidate['value'].split('_')[1]) + 1) % cycle_size)
        return patch(candidate, diagnostics, {'/value': next_value})

    async def turn(prompt, schema):
        calls.append(prompt)
        request = json.loads(prompt)
        assert any('saved_patch_cycle' in error for error in request['patch_errors'])
        current = session.pending('unit')['previous_output']
        return response(patch(current, [], {'/value': 'valid'}))

    def run():
        return asyncio.run(repair_candidate(candidate=base, session=session, unit='unit',
            diagnose=diagnose, validate=lambda c: [], turn=turn, context={}, replay=replay,
            log=lambda name, payload: logs.append(name)))

    if stage_limit == 1:
        with pytest.raises(RepairExhausted): run()
        assert calls == []
        assert session.pending('unit')['previous_output']['value'] == f'state_{cycle_size - 1}'
    else:
        assert run()['value'] == 'valid'
        assert len(calls) == 1
    assert session.used() == stage_limit
    assert logs.count('repair-replayed') == cycle_size - 1
