from copy import deepcopy

import pytest

from toc.story_authoring import build_research_registry, build_story_architect_prompt, validate_story_document
from toc.story_author_pipeline import _validate_architect_plan
from toc.story_selection import selected_event_order, StorySelectionError
from test_story_author_pipeline import _research, _scene


def fixture():
    research = _research()
    events = research['story_materials']['chronological_events']
    for event in events: event['variant_ids'] = ['V1']
    extra = deepcopy(events[0]); extra.update(event_id='E03', variant_ids=['V2'])
    events.append(extra)
    research['variants'] = [
        {'variant_id': 'V1', 'event_ids': ['E01', 'E02'], 'name': 'widely known'},
        {'variant_id': 'V2', 'event_ids': ['E03'], 'name': 'alternate'},
    ]
    selection = {'event_selection_contract': 'story_event_selection_v1',
        'selected_variant_ids': ['V1'], 'selected_event_ids': ['E01', 'E02'],
        'selection_rationale': '依頼の対象視聴者に親しまれた筋を選ぶ。',
        'familiarity_basis': 'researchの普及情報を優先。数値比較は未確認。',
        'omitted_events': []}
    scenes = [_scene('scene_01','E01','s0','s1',None,'scene_02'), _scene('scene_02','E02','s1','s2','scene_01',None)]
    return research, {'selection': selection, 'script': {'scenes': scenes}}


def test_unselected_variant_does_not_need_scene_coverage():
    research, story = fixture()
    registry = build_research_registry(research)
    assert selected_event_order(story, registry) == ['E01','E02']
    assert validate_story_document(story, registry) == []


def test_architect_plan_uses_selected_events_only():
    research, story = fixture()
    story['scene_plan'] = [dict(scene_id=s['scene_id'], source_event_ids=s['source_basis']['event_ids'],
        incoming_state_id=s['start_state']['state_id'], outgoing_state_id=s['end_state']['state_id'],
        previous_scene_id=s['handoff_chain']['incoming']['producer_scene_id'],
        next_scene_id=s['handoff_chain']['outgoing']['consumer_scene_id']) for s in story['script']['scenes']]
    assert len(_validate_architect_plan(story, build_research_registry(research))) == 2


@pytest.mark.parametrize('mutation', ['two_versions','unknown_event','foreign_event','reverse','duplicate','missing_selection'])
def test_bad_selection_cannot_silently_change_the_story(mutation):
    research, story = fixture()
    selection = story['selection']
    if mutation == 'two_versions': selection['selected_variant_ids'] = ['V1','V2']
    if mutation == 'unknown_event': selection['selected_event_ids'] = ['BAD']
    if mutation == 'foreign_event': selection['selected_event_ids'] += ['E03']
    if mutation == 'reverse': selection['selected_event_ids'].reverse()
    if mutation == 'duplicate': selection['selected_event_ids'] *= 2
    if mutation == 'missing_selection': story.pop('selection')
    with pytest.raises(StorySelectionError): selected_event_order(story,build_research_registry(research))


def test_omission_within_selected_version_is_explicit():
    research, story = fixture()
    story['selection']['selected_event_ids'] = ['E02']
    with pytest.raises(StorySelectionError): selected_event_order(story,build_research_registry(research))
    story['selection']['omitted_events'] = [{'event_id':'E01','reason':'導入を説明へ圧縮し、原因と結末を保持する。'}]
    assert selected_event_order(story,build_research_registry(research)) == ['E02']


def test_chosen_event_still_requires_coverage():
    research, story = fixture()
    story['script']['scenes'].pop()
    assert 'story.scene_source_event_coverage' in validate_story_document(story,build_research_registry(research))


def test_prompt_selects_familiar_story_instead_of_covering_research():
    research,_ = fixture()
    prompt = build_story_architect_prompt(build_research_registry(research))
    assert 'widely familiar' in prompt
    assert 'selected_event_ids' in prompt
    assert 'Assign every canonical research event' not in prompt


def test_downstream_profile_retains_only_selected_coverage():
    from test_source_first_research import runner
    research, story = fixture(); m=runner()
    profile=m._profile_from_research(m._story_profile('topic','topic'),research)
    result=m._profile_from_story(profile,story)
    assert result['research_event_ids'] == ['E01','E02']
    assert result['research'] == research
    from toc.visual_planning_contract import VISUAL_PLANNING_CONTRACT
    result['visual_planning'] = {'visual_value_metadata': {'visual_planning_contract': VISUAL_PLANNING_CONTRACT}}
    assert [r['event_id'] for r in m._scene_acceptance_source_ledger(result)['events']] == ['E01','E02']


def test_pipeline_preserves_selection_in_scene_author_and_final_story():
    import asyncio
    from test_story_author_pipeline import FakeTurnRunner
    from toc.story_author_pipeline import author_story_from_research
    research, story = fixture()
    base = FakeTurnRunner()
    async def turn(**kwargs):
        result = await base(**kwargs)
        if kwargs['role'] == 'architect':
            result['selection'] = deepcopy(story['selection'])
        else:
            assert kwargs['registry']['story_selection']['selected_event_ids'] == ['E01', 'E02']
        return result
    result = asyncio.run(author_story_from_research(research, topic='別の物語', target_duration_seconds=300, turn_runner=turn))
    assert not result.validation_errors
    assert result.story['selection'] == story['selection']
    assert result.registry['raw_research'] == research


def test_selected_story_reaches_p450_without_reintroducing_other_version(tmp_path):
    from unittest.mock import patch
    import test_toc_immersive_frontend_run as fake_story
    from test_source_first_research import runner
    from test_p400_cinematic_author import write_test_cinematic_direction
    from story_profile_fixture import _story_profile, _build_research
    from toc.visual_planning_contract import bind_visual_value
    m = runner()
    selected = _build_research('original', 'original', '2026-09-27', _story_profile('original', 'original'))
    research = deepcopy(selected)
    events = research['story_materials']['chronological_events']
    ids = [e['event_id'] for e in events]
    for e in events: e['variant_ids'] = ['popular']
    other = deepcopy(events[-1]);other.update(event_id='UNSELECTED', variant_ids=['alternate'],event='採用しない別版の結末')
    events.append(other)
    research['variants'] = [{'variant_id':'popular','event_ids':ids}, {'variant_id':'alternate','event_ids':['UNSELECTED']}]
    def research_author(**kwargs):
        (tmp_path/'research.md').write_text(m._md_yaml('research',research))
    def story_author(**kwargs):
        with patch.object(fake_story,'load_structured_document', return_value=('',selected)):
            fake_story.write_test_llm_story(**kwargs)
        data=m.load_structured_document(tmp_path/'story.md')[1]
        data['selection']={'event_selection_contract':'story_event_selection_v1','selected_variant_ids':['popular'],
            'selected_event_ids':ids,'selection_rationale':'よく知られた筋を採用','familiarity_basis':'研究資料の普及情報','omitted_events':[]}
        (tmp_path/'story.md').write_text(m._md_yaml('story',data))
    def visual_author(*,run_dir):
        data=m.load_structured_document(run_dir/'story.md')[1]
        raw={key:(run_dir/f'{key}.md').read_bytes() for key in ('research','story')}
        visual=bind_visual_value({'scene_visual_values':[{'scene_selector':s['scene_id'],'notes':[]} for s in data['script']['scenes']]},raw)
        (run_dir/'visual_value.md').write_text(m._md_yaml('visual',visual))
    m.materialize_run('original','original',tmp_path,'p450',research_author_runner=research_author,
        story_author_runner=story_author,visual_value_author_runner=visual_author,cinematic_author_runner=write_test_cinematic_direction)
    assert (tmp_path/'video_manifest.md').is_file()
    data=m.load_structured_document(tmp_path/'script.md')[1]
    event_ids=[e['event_id'] for e in data['scene_set_authoring_contract']['canonical_events']]
    assert 'UNSELECTED' not in event_ids
    assert set(event_ids)==set(ids)
    assert m.load_structured_document(tmp_path/'research.md')[1]==research


def test_selected_variant_can_be_later_in_the_research_inventory():
    research, story = fixture()
    story['selection'].update(selected_variant_ids=['V2'],selected_event_ids=['E03'])
    assert selected_event_order(story,build_research_registry(research)) == ['E03']


def test_single_variant_compatibility_does_not_override_explicit_foreign_membership():
    research, story=fixture()
    research['variants']=research['variants'][:1]
    research['variants'][0]['event_ids']=[]
    for event in research['story_materials']['chronological_events']:
        event['variant_ids']=['other']
    with pytest.raises(StorySelectionError, match='outside_selected_variant'):
        selected_event_order(story,build_research_registry(research))


def test_unselected_symbol_does_not_become_default_scene_prop():
    from test_source_first_research import runner
    research, story=fixture()
    research['story_materials']['symbols_and_themes']=[
        {'item_id':'foreign_prop','kind':'object','item':'別版だけの道具'},
        {'item_id':'chosen_prop','kind':'object','item':'採用版の道具'},
    ]
    for scene in story['script']['scenes']:
        scene['source_basis']['symbol_ids']=['chosen_prop']
    m=runner();profile=m._profile_from_research(m._story_profile('topic','topic'),research)
    result=m._profile_from_story(profile,story)
    assert result['artifact_name']=='採用版の道具'
    assert '別版だけの道具' not in result['motifs']


def test_null_contract_does_not_restore_full_coverage():
    research, story=fixture()
    research['variants']=research['variants'][:1]
    story['selection']['event_selection_contract']=None
    with pytest.raises(StorySelectionError, match='contract_invalid'):
        selected_event_order(story,build_research_registry(research))


def test_omissions_cannot_reference_other_variants():
    research, story=fixture()
    story['selection']['omitted_events']=[{'event_id':'E03','reason':'other variant'}]
    with pytest.raises(StorySelectionError, match='outside_variant'):
        selected_event_order(story,build_research_registry(research))


def test_conflicting_membership_does_not_silently_choose_one_index():
    research, story=fixture()
    research['variants'][0]['event_ids']=['E02']
    with pytest.raises(StorySelectionError, match='membership_conflict'):
        selected_event_order(story,build_research_registry(research))


def test_variant_chronology_takes_precedence_over_cross_variant_inventory_order():
    research, story=fixture()
    research['story_materials']['chronological_events'].reverse()
    assert selected_event_order(story,build_research_registry(research))==['E01','E02']


def test_malformed_scene_basis_reenters_author_instead_of_crashing_projection():
    from test_source_first_research import runner
    from toc.production_diagnostics import AuthoringValidationError
    research, story=fixture();m=runner()
    story['script']['scenes'][0]['source_basis']='bad'
    profile=m._profile_from_research(m._story_profile('topic','topic'),research)
    with pytest.raises(AuthoringValidationError) as exc:
        m._profile_from_story(profile,story)
    assert exc.value.owner_stage=='p220'
