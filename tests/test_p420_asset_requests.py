import json
from copy import deepcopy

import pytest

from test_p400_cinematic_author import sample
from toc.p420_assets import resolve_asset_requests, extend_asset_bibles, ASSET_RESOLUTION_CONTRACT


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


def test_existing_character_alias_reuses_exact_source_binding_and_rejects_other_person(tmp_path):
    story, sources, base, rows = fixture(tmp_path)
    research = {'story_materials': {'characters': [{'name': '修理工／職人'}, {'name': '修理工／訪問者'}]}}
    entity = {'source': 'research', 'pointer': '/story_materials/characters/0/name'}
    base['characters']['keeper']['name'] = '修理工／職人'
    base['characters']['keeper']['source_entity'] = entity
    base['characters']['keeper']['source_role_ids'] = ['C1']
    story['script']['scenes'][0]['event_sequence'][0]['participants'] = ['C1']
    rows[0]['asset_requests'] = [{
        'request_id': 'worker', 'kind': 'character', 'name': '修理工',
        'source_entity': entity, 'source_role_id': 'C1',
        'source_evidence': [{'source': 'story', 'pointer': '/script/scenes/0/event_sequence/0/what_happens', 'quote': '修理工が手紙を読む。'}],
        'used_in_cuts': ['a', 'b'], 'existing_asset_id': 'keeper',
    }]
    rows[0]['cuts'][0]['character_ids'] = ['request:worker']
    rows[0]['cuts'][0]['object_ids'] = []
    resolved, registry, _ = resolve_asset_requests(rows, story, research, base)
    assert resolved[0]['cuts'][0]['character_ids'] == ['keeper']
    assert len(registry['characters']) == 1
    rows[0]['asset_requests'][0]['source_entity'] = {'source': 'research', 'pointer': '/story_materials/characters/1/name'}
    with pytest.raises(ValueError, match='identity_mismatch'):
        resolve_asset_requests(rows, story, research, base)


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


def test_final_cast_includes_p420_character_and_reaches_both_asset_request_paths(tmp_path):
    import asyncio
    import hashlib
    import yaml
    from types import SimpleNamespace
    from test_toc_immersive_frontend_run import load_frontend_run_module
    from toc.cast_design import CAST_APPEARANCE_FIELDS, character_subject_contract
    from toc.p400_authoring import author_cinematic_direction
    from toc.visual_planning_contract import source_binding

    story, sources, base, rows = fixture(tmp_path)
    quote = '修理工が店主と話す。'
    story['script']['scenes'][0]['event_sequence'][0]['what_happens'] = quote
    sources['story'] = json.dumps(story, ensure_ascii=False).encode()
    sources['research'] = json.dumps({'source_passages': [{'text': quote}]}, ensure_ascii=False).encode()
    request = {
        'request_id': 'shopkeeper', 'kind': 'character', 'name': '店主',
        'source_entity': {'source': 'story', 'pointer': '/script/scenes/0/event_sequence/0/what_happens'},
        'source_evidence': [{'source': 'story', 'pointer': '/script/scenes/0/event_sequence/0/what_happens', 'quote': quote}],
        'used_in_cuts': ['a'], 'existing_asset_id': '',
    }
    rows[0]['asset_requests'] = [request]
    rows[0]['cuts'][0]['character_ids'] = ['keeper', 'request:shopkeeper']
    rows[0]['cuts'][0]['object_ids'] = []
    accepted_reference = tmp_path / base['characters']['keeper']['references'][0]
    accepted_reference.parent.mkdir(parents=True, exist_ok=True)
    accepted_reference.write_bytes(b'accepted character reference image bytes')
    for name, raw in sources.items():
        (tmp_path / f'{name}.md').write_bytes(raw)

    _resolved_rows, final_resources, _records = resolve_asset_requests(
        rows, story, json.loads(sources['research']), base)
    source_bindings = {name: source_binding(f'{name}.md', raw) for name, raw in sources.items()}

    def provenance(fact):
        return {'source_facts': [fact], 'interpretation': [], 'creative_choices': []}

    design_rows = {}
    for character_id, resource in final_resources['characters'].items():
        design_rows[character_id] = {
            'character_id': character_id,
            'name': resource['name'],
            'subject_contract': character_subject_contract(resource),
            'role': 'source-described story participant',
            'role_basis': f"the source identifies {resource['name']} as participating",
            'relationships': [],
            'personality_provenance': provenance(f"{resource['name']} participates in a source event"),
            'behavior_baseline': ["pauses before responding"],
            'contract_reconciliation': {
                'status': 'consistent',
                'source_basis': f"the source names {resource['name']}",
                'explanation': 'the individual contract agrees with the source',
            },
            'appearance': {field: f"distinctive {field} for {resource['name']}" for field in CAST_APPEARANCE_FIELDS},
            'appearance_provenance': provenance(f"the source names {resource['name']}"),
            'intentional_similarities': [],
            'distinguish_from': [],
            'members': [],
        }
    cast_design = {
        'schema_version': 'cast_design_v1',
        'source_bindings': source_bindings,
        'characters': design_rows,
    }
    calls = []

    async def turn(**kwargs):
        calls.append(kwargs['prompt'])
        if len(calls) <= len(rows):
            payload = rows[len(calls) - 1]
        else:
            payload = cast_design
        return SimpleNamespace(
            payload={'result_json': json.dumps(payload, ensure_ascii=False)},
            transcript=(), provenance=SimpleNamespace(as_dict=lambda: {'model': 'stub'}),
        )

    direction = asyncio.run(author_cinematic_direction(
        run_dir=tmp_path, resources=base, grounding='maintained cast design guidance',
        client_factory=lambda: None, turn_runner=turn, enable_cast_design=True,
    ))
    added_id = direction['asset_resolutions'][0]['asset_id']
    assert added_id in direction['cast_design']['characters']
    assert added_id in direction['resources']['characters']
    assert added_id in calls[-1]
    assert 'maintained cast design guidance' in calls[-1]
    prior_reference_sha = hashlib.sha256(accepted_reference.read_bytes()).hexdigest()
    assert direction['cast_design']['reference_identity_bindings']['keeper'][0]['sha256'] == prior_reference_sha

    accepted_reference.write_bytes(b'replaced bytes at the same accepted reference path')
    from toc.p400_authoring import load_direction
    import pytest
    with pytest.raises(RuntimeError, match='source_stale'):
        load_direction(tmp_path, base)

    reauthor_calls = []

    async def cast_only_turn(**kwargs):
        reauthor_calls.append(kwargs['prompt'])
        return SimpleNamespace(
            payload={'result_json': json.dumps(cast_design, ensure_ascii=False)},
            transcript=(), provenance=SimpleNamespace(as_dict=lambda: {'model': 'stub'}),
        )

    direction = asyncio.run(author_cinematic_direction(
        run_dir=tmp_path, resources=base, grounding='maintained cast design guidance',
        client_factory=lambda: None, turn_runner=cast_only_turn, enable_cast_design=True,
    ))
    new_reference_sha = hashlib.sha256(accepted_reference.read_bytes()).hexdigest()
    assert new_reference_sha != prior_reference_sha
    assert direction['cast_design']['reference_identity_bindings']['keeper'][0]['sha256'] == new_reference_sha
    assert len(reauthor_calls) == 1

    manifest = {
        'video_metadata': {'topic': 'fixture topic', 'time': ''},
        'assets': {
            'character_bible': [{
                'character_id': 'keeper',
                'reference_images': ['assets/characters/keeper.png'],
                'fixed_prompts': ['修理工'],
                'cinematic': {'role': '修理工の一貫性', 'visual_subject': '修理工の参照画像'},
            }],
            'object_bible': [],
            'location_bible': [{
                'location_id': 'shop', 'reference_images': ['assets/locations/shop.png'],
                'fixed_prompts': ['工房'], 'cinematic': {'role': '工房', 'visual_subject': '工房'},
            }],
            'style_guide': {'visual_style': '実写映画', 'forbidden': [], 'reference_images': []},
        },
        'scenes': [{
            'scene_id': 10,
            'cuts': [{
                'selector': 'scene10_cut01',
                'image_generation': {'character_ids': [added_id], 'object_ids': [], 'location_ids': ['shop']},
            }],
        }],
    }
    extend_asset_bibles(manifest, direction)
    added_bible = next(item for item in manifest['assets']['character_bible'] if item['character_id'] == added_id)
    assert added_bible['appearance_contract']['identifying_features'] == f'distinctive identifying_features for 店主'

    frontend = load_frontend_run_module()
    profile = {'topic_label': 'fixture topic', 'protagonist_name': '修理工', 'places': ['工房']}
    _inventory, frontend_plan = frontend._build_asset_artifacts_from_manifest(profile=profile, manifest=manifest)
    frontend_entry = next(item for item in frontend_plan['assets'] if item['asset_id'] == added_id)
    frontend_prompt = frontend._prompt_for_asset(frontend_entry, profile)
    assert 'distinctive face_shape for 店主' in frontend_prompt
    assert 'distinctive identifying_features for 店主' in frontend_prompt

    (tmp_path / 'video_manifest.md').write_text(
        '# Video Manifest\n\n```yaml\n' + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False) + '```\n',
        encoding='utf-8',
    )
    from server import image_gen_app
    codex_entries = image_gen_app._asset_entries_from_manifest(tmp_path)
    codex_entry = next(item for item in codex_entries if item['asset_id'] == added_id)
    assert 'distinctive face_shape for 店主' in codex_entry['prompt']
    assert 'distinctive identifying_features for 店主' in codex_entry['prompt']


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


@pytest.mark.parametrize('object_name', ['布', '小箱'])
def test_typed_physical_symbol_and_explicit_opening_object_prove_early_presence(tmp_path, object_name):
    story, sources, base, rows = fixture(tmp_path)
    research = {'story_materials': {'symbols_and_themes': [
        {'kind': 'object', 'item': object_name, 'meaning': '記憶を象徴する'},
    ]}}
    scene = story['script']['scenes'][0]
    scene['start_state']['objects'] = [f'旅人が身に着けた{object_name}']
    scene['event_sequence'][0]['what_happens'] = '旅人が歩く。'
    scene['event_sequence'][1]['what_happens'] = f'旅人が{object_name}を手渡す。'
    request = rows[0]['asset_requests'][0]
    request['name'] = object_name
    request['source_entity'] = {'source': 'research', 'pointer': '/story_materials/symbols_and_themes/0/item'}
    request['source_evidence'] = [{'source': 'story', 'pointer': '/script/scenes/0/event_sequence/1/what_happens',
                                  'quote': f'旅人が{object_name}を手渡す。'}]
    _, registry, records = resolve_asset_requests(rows, story, research, base)
    opening = next(ref for ref in records[0]['source_evidence'] if '/start_state/' in ref['pointer'])
    assert opening == {'source': 'story', 'pointer': '/script/scenes/0/start_state/objects/0',
                       'quote': f'旅人が身に着けた{object_name}'}
    assert len(records[0]['source_evidence']) == 2
    assert request['source_evidence'] == [request['source_evidence'][0]]
    assert len(registry['objects']) == 1

    scene['start_state']['objects'] = []
    with pytest.raises(ValueError, match='future_beat'):
        resolve_asset_requests(rows, story, research, base)


@pytest.mark.parametrize('bad_kind, pointer_field', [('theme', 'item'), ('motif', 'item'), ('object', 'meaning')])
def test_abstract_symbol_or_meaning_cannot_become_a_physical_asset(tmp_path, bad_kind, pointer_field):
    story, sources, base, rows = fixture(tmp_path)
    research = {'story_materials': {'symbols_and_themes': [{'kind': bad_kind, 'item': '手紙', 'meaning': '手紙'}]}}
    rows[0]['asset_requests'][0]['source_entity'] = {'source': 'research',
        'pointer': f'/story_materials/symbols_and_themes/0/{pointer_field}'}
    with pytest.raises(ValueError, match='physical_source_required'):
        resolve_asset_requests(rows, story, research, base)


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
