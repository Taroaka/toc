import json
from copy import deepcopy

import pytest

from test_p400_cinematic_author import sample
from toc.p420_assets import resolve_asset_requests, ASSET_RESOLUTION_CONTRACT


def fixture(tmp_path):
    story, sources, resources, rows = sample(tmp_path)
    story['script']['scenes'][0]['event_sequence'][0]['what_happens'] = '修理工が手紙を読む。'
    sources['story'] = json.dumps(story, ensure_ascii=False).encode()
    research = {'source_passages': [{'text': '修理工が一通の手紙を読む。'}]}
    sources['research'] = json.dumps(research, ensure_ascii=False).encode()
    rows[0]['asset_requests'] = [{
        'request_id': 'letter', 'kind': 'object', 'name': '手紙',
        'source_entity': {'source': 'research', 'pointer': '/source_passages/0/text'},
        'source_evidence': [{'source': 'story', 'pointer': '/script/scenes/0/event_sequence/0/what_happens', 'quote': '修理工が手紙を読む。'}],
        'used_in_cuts': ['a'], 'reference_description': '原作に登場する一通の手紙', 'existing_asset_id': '',
    }]
    rows[0]['cuts'][0]['object_ids'] = ['request:letter']
    return story, sources, resources, rows


def test_grounded_request_is_registered_and_bound_to_its_cut(tmp_path):
    story, sources, base, rows = fixture(tmp_path)
    resolved, registry, records = resolve_asset_requests(rows, story, json.loads(sources['research']), base)
    aid = resolved[0]['cuts'][0]['object_ids'][0]
    assert aid.startswith('source-object-')
    assert registry['objects'][aid]['name'] == '手紙'
    assert registry['objects'][aid]['references'] == [f'assets/objects/{aid}.png']
    assert records[0]['asset_id'] == aid
    assert aid in registry['scene_assets']['quiet']['object_ids']
    assert 'request:letter' in rows[0]['cuts'][0]['object_ids']  # no mutation of author output
    again = resolve_asset_requests(resolved, story, json.loads(sources['research']), base)
    assert again == (resolved, registry, records)


@pytest.mark.parametrize('fault', ['bad_pointer', 'wrong_quote', 'unused', 'wrong_cut', 'other_scene', 'duplicate_id', 'metaphor', 'unknown_existing'])
def test_invalid_missing_asset_is_rejected(tmp_path, fault):
    story, sources, base, rows = fixture(tmp_path)
    request = rows[0]['asset_requests'][0]
    if fault == 'bad_pointer': request['source_entity']['pointer'] = '/not-here'
    if fault == 'wrong_quote': request['source_evidence'][0]['quote'] = 'a fabricated passage'
    if fault == 'unused': rows[0]['cuts'][0]['object_ids'] = []
    if fault == 'wrong_cut': request['used_in_cuts'] = ['unknown']
    if fault == 'other_scene': request['source_evidence'][0] = {'source': 'story', 'pointer': '/script/scenes/1/event_sequence/0/what_happens', 'quote': '箱を残す'}
    if fault == 'duplicate_id': rows[0]['asset_requests'].append(deepcopy(request))
    if fault == 'metaphor': request['source_entity'] = {'source': 'visual_value', 'pointer': '/notes/0'}
    if fault == 'unknown_existing': request['existing_asset_id'] = 'unknown'
    with pytest.raises(ValueError, match='asset_request'):
        resolve_asset_requests(rows, story, json.loads(sources['research']), base)


def test_repeated_source_identity_reuses_one_asset_and_existing_id_can_be_bound(tmp_path):
    story, sources, base, rows = fixture(tmp_path)
    request = rows[0]['asset_requests'][0]
    request['used_in_cuts'] = ['a', 'b']
    rows[0]['cuts'][1]['object_ids'] = ['request:letter']
    resolved, registry, records = resolve_asset_requests(rows, story, json.loads(sources['research']), base)
    assert len(registry['objects']) == 1
    assert resolved[0]['cuts'][0]['object_ids'] == resolved[0]['cuts'][1]['object_ids']
    base['objects']['existing-letter'] = {'name': '手紙', 'references': ['assets/objects/old.png']}
    request['existing_asset_id'] = 'existing-letter'
    resolved, registry, _ = resolve_asset_requests(rows, story, json.loads(sources['research']), base)
    assert resolved[0]['cuts'][0]['object_ids'] == ['existing-letter']
    assert len(registry['objects']) == 1


def test_author_resolves_request_in_existing_scene_turn_and_saves_replayable_registry(tmp_path):
    import asyncio
    from types import SimpleNamespace
    from toc.p400_authoring import author_cinematic_direction, load_direction
    story, sources, base, rows = fixture(tmp_path)
    for name, raw in sources.items():
        (tmp_path / f'{name}.md').write_bytes(raw)
    calls = []
    async def turn(**kwargs):
        calls.append(kwargs['prompt'])
        return SimpleNamespace(payload={'result_json': json.dumps(rows[len(calls)-1])}, transcript=(),
            provenance=SimpleNamespace(as_dict=lambda: {'model': 'stub'}))
    doc = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=base, grounding='', client_factory=lambda: None, turn_runner=turn))
    assert len(calls) == len(rows)
    assert 'source-object-' in calls[1]
    assert doc['metadata']['asset_resolution_contract'] == ASSET_RESOLUTION_CONTRACT
    assert load_direction(tmp_path, base) == doc
    # Expansions are not trusted merely because they were saved.
    aid = doc['asset_resolutions'][0]['asset_id']
    doc['resources']['objects'][aid]['references'] = ['../outside.png']
    (tmp_path / 'cinematic_direction.json').write_text(json.dumps(doc))
    with pytest.raises(RuntimeError, match='asset_resolution_changed'):
        load_direction(tmp_path, base)


def test_same_name_with_distinct_source_identity_is_not_merged(tmp_path):
    story, sources, base, rows = fixture(tmp_path)
    story['script']['scenes'][0]['event_sequence'][1]['what_happens'] = '修理工が別の手紙を置く。'
    research = json.loads(sources['research'])
    research['source_passages'].append({'text': '別の手紙が届く。'})
    second = deepcopy(rows[0]['asset_requests'][0])
    second.update(request_id='other_letter', used_in_cuts=['b'])
    second['source_entity']['pointer'] = '/source_passages/1/text'
    second['source_evidence'] = [{'source': 'story', 'pointer': '/script/scenes/0/event_sequence/1/what_happens', 'quote': '修理工が別の手紙を置く。'}]
    rows[0]['asset_requests'].append(second)
    rows[0]['cuts'][1]['object_ids'] = ['request:other_letter']
    _, registry, records = resolve_asset_requests(rows, story, research, base)
    assert len(registry['objects']) == 2
    assert records[0]['asset_id'] != records[1]['asset_id']


@pytest.mark.parametrize('kind,name,field', [('object', '手紙', 'object_ids'), ('character', '店主', 'character_ids')])
def test_added_object_reaches_script_manifest_and_p500_requests(tmp_path, kind, name, field):
    from test_source_first_scene_projection import setup_profile
    from test_p400_cinematic_author import write_test_cinematic_direction
    from toc.visual_planning_contract import bind_visual_value
    from toc.p400_authoring import bind_direction
    m, profile, story, visual = setup_profile(tmp_path)
    source = story['script']['scenes'][0]
    usage = f'この場に{name}が存在する。'
    source['event_sequence'][0]['what_happens'] += usage
    (tmp_path / 'story.md').write_text(m._md_yaml('story', story))
    visual = bind_visual_value(visual, {n: (tmp_path / f'{n}.md').read_bytes() for n in ('research', 'story')})
    (tmp_path / 'visual_value.md').write_text(m._md_yaml('visual', visual))
    profile = m._profile_from_story(profile, story)
    write_test_cinematic_direction(run_dir=tmp_path, profile=profile)
    original = json.loads((tmp_path / 'cinematic_direction.json').read_bytes())
    row = original['scenes'][0]
    row['asset_requests'] = [{
        'request_id': 'missing', 'kind': kind, 'name': name,
        'source_entity': {'source': 'story', 'pointer': '/script/scenes/0/event_sequence/0/what_happens'},
        'source_evidence': [{'source': 'story', 'pointer': '/script/scenes/0/event_sequence/0/what_happens', 'quote': usage}],
        'used_in_cuts': [row['cuts'][0]['cut_id']], 'reference_description': f'原作に登場する{name}', 'existing_asset_id': '',
    }]
    row['cuts'][0][field] = ['request:missing']
    row['cuts'][0]['first_frame_brief'] = f'{name}が画面の中央に見える。'
    sources = {n: (tmp_path / f'{n}.md').read_bytes() for n in ('research', 'story', 'visual_value')}
    directed = bind_direction(original['scenes'], sources, m._cinematic_resources(profile))
    (tmp_path / 'cinematic_direction.json').write_text(json.dumps(directed, ensure_ascii=False))
    script, manifest, _ = m._build_script_and_manifest('fixture', tmp_path, '2026-09-26', profile)
    aid = directed['asset_resolutions'][0]['asset_id']
    assert script['scenes'][0]['cuts'][0]['cut_contract']['asset_dependency'][f'{field}_required'] == [aid]
    assert f'assets/{"objects" if kind == "object" else "characters"}/{aid}.png' in manifest['scenes'][0]['cuts'][0]['image_generation']['references']
    assert any(a[f'{kind}_id'] == aid for a in manifest['assets'][f'{kind}_bible'])
    inventory, plan = m._build_asset_artifacts_from_manifest(profile=profile, manifest=manifest)
    entry = next(a for a in plan['assets'] if a['asset_id'] == aid)
    assert entry['source_script_selectors'] == ['scene10_cut01']
    assert entry['source_evidence'][0]['quote'] == usage
    m._write_asset_request_files(tmp_path, plan, profile)
    assert (tmp_path / 'asset_stage_manifest.md').is_file()
    assert aid in (tmp_path / 'asset_stage_manifest.md').read_text()
    from toc.p400_authoring import projection_issues
    assert projection_issues(manifest, 'video_metadata', directed, story) == []
    manifest['assets'][f'{kind}_bible'] = [a for a in manifest['assets'][f'{kind}_bible'] if a[f'{kind}_id'] != aid]
    assert any('bible_projection_missing' in error for error in projection_issues(manifest, 'video_metadata', directed, story))



def test_existing_named_asset_requires_reuse_or_explicit_distinct_identity(tmp_path):
    story, sources, base, rows = fixture(tmp_path)
    base['objects']['old-letter'] = {'name': '手紙', 'references': ['assets/objects/old.png']}
    with pytest.raises(ValueError, match='existing_candidate'):
        resolve_asset_requests(rows, story, json.loads(sources['research']), base)
    request = rows[0]['asset_requests'][0]
    request['distinct_from_asset_ids'] = ['old-letter']
    request['distinct_identity_reason'] = '原作のこの箇所の手紙は別の対象である'
    _, resources, _ = resolve_asset_requests(rows, story, json.loads(sources['research']), base)
    assert len(resources['objects']) == 2


def test_freeform_reference_description_cannot_invent_p500_attributes(tmp_path):
    from toc.p420_assets import extend_asset_bibles
    story, sources, base, rows = fixture(tmp_path)
    rows[0]['asset_requests'][0]['reference_description'] = '金色の王冠が描かれた魔法の手紙'
    resolved, resources, records = resolve_asset_requests(rows, story, json.loads(sources['research']), base)
    direction = {'resources': resources}
    manifest = {'assets': {'character_bible': [{'character_id': 'keeper'}], 'object_bible': [], 'location_bible': [{'location_id': 'shop'}]}}
    extend_asset_bibles(manifest, direction)
    assert manifest['assets']['object_bible'][0]['fixed_prompts'] == ['手紙']


def test_reused_asset_evidence_reaches_existing_bible(tmp_path):
    from toc.p420_assets import extend_asset_bibles
    story, sources, base, rows = fixture(tmp_path)
    base['objects']['old-letter'] = {'name': '手紙', 'references': ['assets/objects/old.png']}
    rows[0]['asset_requests'][0]['existing_asset_id'] = 'old-letter'
    _, resources, _ = resolve_asset_requests(rows, story, json.loads(sources['research']), base)
    manifest = {'assets': {'character_bible': [{'character_id': 'keeper'}], 'object_bible': [{'object_id': 'old-letter', 'fixed_prompts': ['既存の外観']}], 'location_bible': [{'location_id': 'shop'}]}}
    extend_asset_bibles(manifest, {'resources': resources})
    entry = manifest['assets']['object_bible'][0]
    assert entry['source_evidence'][0]['quote'] == '修理工が手紙を読む。'
    assert entry['fixed_prompts'] == ['既存の外観']


def test_earlier_unrelated_quote_cannot_authorize_a_later_asset(tmp_path):
    story, sources, base, rows = fixture(tmp_path)
    story['script']['scenes'][0]['event_sequence'][0]['what_happens'] = '修理工が箱を開ける。'
    story['script']['scenes'][0]['event_sequence'][1]['what_happens'] = '修理工が手紙を読む。'
    rows[0]['asset_requests'][0]['source_evidence'] = [
        {'source': 'story', 'pointer': '/script/scenes/0/event_sequence/0/what_happens', 'quote': '修理工が箱を開ける。'},
        {'source': 'story', 'pointer': '/script/scenes/0/event_sequence/1/what_happens', 'quote': '修理工が手紙を読む。'},
    ]
    with pytest.raises(ValueError, match='future_beat'):
        resolve_asset_requests(rows, story, json.loads(sources['research']), base)


def test_base_registry_does_not_change_after_a_source_role_is_resolved(tmp_path):
    from test_source_first_scene_projection import setup_profile
    m, profile, _, _ = setup_profile(tmp_path)
    profile['story_scenes'][0]['event_sequence'][0]['participants'] = ['unmapped_alias']
    before = m._cinematic_resources(profile)
    expanded = deepcopy(before)
    expanded['characters'][profile['protagonist_asset_id']]['source_role_ids'] = ['unmapped_alias']
    profile['cinematic_direction'] = {'resources': expanded}
    assert m._cinematic_resources(profile) == before


def test_one_source_entity_is_reused_across_scenes_with_both_usage_citations(tmp_path):
    story, sources, base, rows = fixture(tmp_path)
    story['script']['scenes'][1]['event_sequence'][0]['what_happens'] = '修理工が手紙を置く。'
    later = deepcopy(rows[0]['asset_requests'][0])
    later['used_in_cuts'] = ['c']
    later['source_evidence'] = [{'source': 'story', 'pointer': '/script/scenes/1/event_sequence/0/what_happens', 'quote': '修理工が手紙を置く。'}]
    rows[1]['asset_requests'] = [later]
    rows[1]['cuts'][0]['object_ids'] = ['request:letter']
    resolved, registry, records = resolve_asset_requests(rows, story, json.loads(sources['research']), base)
    assert len(registry['objects']) == 1
    assert records[0]['asset_id'] == records[1]['asset_id']
    assert [r['created'] for r in records] == [True, False]
    assert len(registry['objects'][records[0]['asset_id']]['source_evidence']) == 2
    assert resolve_asset_requests(resolved, story, json.loads(sources['research']), base) == (resolved, registry, records)


def test_missing_source_location_can_be_registered(tmp_path):
    story, sources, base, rows = fixture(tmp_path)
    base['locations'] = {}
    rows[0]['asset_requests'] = [{
        'request_id': 'shop', 'kind': 'location', 'name': '工房',
        'source_entity': {'source': 'story', 'pointer': '/script/scenes/0/location/name'},
        'source_evidence': [{'source': 'story', 'pointer': '/script/scenes/0/location/name', 'quote': '工房'}],
        'used_in_cuts': ['a', 'b'], 'existing_asset_id': '',
    }]
    for cut in rows[0]['cuts']:
        cut['object_ids'] = []
        cut['location_id'] = 'request:shop'
    resolved, registry, records = resolve_asset_requests(rows[:1], story, json.loads(sources['research']), base)
    aid = records[0]['asset_id']
    assert registry['locations'][aid]['name'] == '工房'
    assert registry['locations'][aid]['references'] == [f'assets/locations/{aid}.png']
    assert [cut['location_id'] for cut in resolved[0]['cuts']] == [aid, aid]
