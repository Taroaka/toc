import asyncio
from copy import deepcopy

from test_story_author_pipeline import FakeTurnRunner, _research
from toc.story_author_pipeline import author_story_from_research


def test_unknown_id_uses_only_field_patch_and_preserves_other_scene_data():
    from toc.story_field_repair import scene_digest
    base=FakeTurnRunner();calls=[];before=[]
    async def turn(**kwargs):
        calls.append(kwargs)
        if kwargs['role']=='field_repair':
            before.append(deepcopy(kwargs['scene']))
            assert kwargs['output_schema']['additionalProperties'] is False
            return {'scene_id':kwargs['scene_id'],'base_digest':scene_digest(kwargs['scene']),
                'operations':[{'path':'/source_basis/character_ids/0','value':'C01'}]}
        result=await base(**kwargs)
        if kwargs['role']=='scene_author' and result['scenes'][0]['scene_id']=='scene_01':
            result['scenes'][0]['source_basis']['character_ids']=['BAD_ID']
        return result
    result=asyncio.run(author_story_from_research(_research(),topic='時計',target_duration_seconds=300,
        turn_runner=turn,max_repair_rounds=3))
    assert [c['role'] for c in calls].count('field_repair')==1
    assert all(c['role']!='repair' for c in calls)
    scene=result.story['script']['scenes'][0]
    assert scene['source_basis']['character_ids']==['C01']
    assert scene['event_sequence']==before[0]['event_sequence']
    assert scene['purpose']==before[0]['purpose']
    assert result.repair_rounds[0]['mode']=='field_patch'


def test_bad_patch_is_retried_as_patch_not_replacement_scene():
    from toc.story_field_repair import scene_digest
    base=FakeTurnRunner();patches=[]
    async def turn(**kwargs):
        if kwargs['role']=='field_repair':
            patches.append(kwargs)
            path='/purpose' if len(patches)==1 else '/source_basis/character_ids/0'
            return {'scene_id':kwargs['scene_id'],'base_digest':scene_digest(kwargs['scene']),
                'operations':[{'path':path,'value':'C01'}]}
        assert kwargs['role']!='repair'
        result=await base(**kwargs)
        if kwargs['role']=='scene_author' and result['scenes'][0]['scene_id']=='scene_01':
            result['scenes'][0]['source_basis']['character_ids']=['BAD_ID']
        return result
    result=asyncio.run(author_story_from_research(_research(),topic='時計',target_duration_seconds=300,
        turn_runner=turn,max_repair_rounds=3))
    assert len(patches)==2
    assert '/purpose' in patches[1]['prompt']
    assert not result.validation_errors


def test_narrative_reveal_conflict_still_uses_scene_author():
    from test_story_author_pipeline import _scene
    base=FakeTurnRunner();roles=[]
    async def turn(**kwargs):
        roles.append(kwargs['role'])
        if kwargs['role']=='repair':
            assert kwargs['scene_id']=='scene_01'
            return {'scene_id':'scene_01','replacement_scene':_scene('scene_01','E01','state_start','state_clock_found',None,'scene_02')}
        assert kwargs['role']!='field_repair'
        result=await base(**kwargs)
        if kwargs['role']=='scene_author' and result['scenes'][0]['scene_id']=='scene_01':
            result['scenes'][0]['reveal_contract']={'before':{'truth':'known'},'after':{'truth':'withheld'}}
        return result
    result=asyncio.run(author_story_from_research(_research(),topic='時計',target_duration_seconds=300,
        turn_runner=turn,max_repair_rounds=2))
    assert roles.count('repair')==1
    assert not result.validation_errors
    assert result.repair_rounds[0]['mode']=='scene_rewrite'


def test_repeated_bad_field_patch_stops_without_rewriting_prose():
    import pytest
    from toc.story_author_pipeline import StoryAuthoringError
    from toc.story_field_repair import scene_digest
    base=FakeTurnRunner();roles=[]
    async def turn(**kwargs):
        roles.append(kwargs['role'])
        if kwargs['role']=='field_repair':
            return {'scene_id':kwargs['scene_id'],'base_digest':scene_digest(kwargs['scene']),
                'operations':[{'path':'/purpose','value':'unauthorized rewrite'}]}
        assert kwargs['role']!='repair'
        result=await base(**kwargs)
        if kwargs['role']=='scene_author' and result['scenes'][0]['scene_id']=='scene_01':
            result['scenes'][0]['source_basis']['character_ids']=['BAD_ID']
        return result
    with pytest.raises(StoryAuthoringError, match='field patch made no progress'):
        asyncio.run(author_story_from_research(_research(),topic='時計',target_duration_seconds=300,
            turn_runner=turn,max_repair_rounds=8))
    assert 'repair' not in roles
