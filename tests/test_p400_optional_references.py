import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import json

import pytest
from toc.downstream_repair import Diagnostics, UnscopedRepairError, direction_diagnostics, patch_schema, apply_patch, repair_candidate
from toc.production_repair import RepairSession, digest
from toc.p400_authoring import author_cinematic_direction
from test_p400_cinematic_author import sample


def response(base,path):
    return {'unit_id':base['scene_id'],'base_digest':digest(base),'operations':[{'path':path,'value':None}]}


@pytest.mark.parametrize('field',['allowed_new_reveal_elements','allowed_reveal_info_ids'])
def test_optional_reveal_without_candidates_can_remove_only_invalid_element(tmp_path,field):
    story,_,resources,scenes=sample(tmp_path)
    bad=deepcopy(scenes[0]);bad['cuts'][0][field]=['unauthorized']
    issues=direction_diagnostics(bad,story['script']['scenes'][0],resources)
    path='/cuts/0/'+field+'/0'
    patch_schema(issues,bad)
    fixed=apply_patch(bad,issues,response(bad,path))
    assert fixed==scenes[0]
    assert bad['cuts'][0][field]==['unauthorized']


def test_valid_reveal_entries_are_preserved(tmp_path):
    story,_,resources,scenes=sample(tmp_path)
    story['script']['scenes'][0]['event_sequence'][0]['allowed_new_reveal_elements']=['authorized']
    bad=deepcopy(scenes[0]);bad['cuts'][0]['allowed_new_reveal_elements']=['authorized','unlicensed']
    issues=direction_diagnostics(bad,story['script']['scenes'][0],resources)
    path='/cuts/0/allowed_new_reveal_elements/1'
    fixed=apply_patch(bad,issues,response(bad,path))
    assert fixed['cuts'][0]['allowed_new_reveal_elements']==['authorized']
    with pytest.raises(ValueError):apply_patch(bad,issues,response(bad,'/cuts/0/allowed_new_reveal_elements/0'))


def test_unsatisfiable_required_reference_does_not_consume_provider_budget(tmp_path):
    candidate={'reference':'unknown'}
    diagnostics=Diagnostics(candidate);diagnostics.refs('/reference',{})
    session=RepairSession(tmp_path,'p420');turn=AsyncMock()
    with pytest.raises(UnscopedRepairError,match='no registered reference candidate'):
        asyncio.run(repair_candidate(candidate=candidate,session=session,unit='scene',
            diagnose=lambda _:diagnostics.items,validate=lambda _:['invalid'],turn=turn,context={},log=lambda *args:None))
    turn.assert_not_awaited()
    assert session.used()==0


def test_author_repairs_empty_optional_reveal_without_reauthoring_scene(tmp_path):
    _,_,resources,scenes=sample(tmp_path)
    bad=deepcopy(scenes[0]);bad['cuts'][0]['allowed_new_reveal_elements']=['unlicensed']
    calls=[]
    async def turn(**kwargs):
        calls.append(kwargs)
        if len(calls)==1: value={'result_json':json.dumps(bad)}
        elif len(calls)==2:
            assert 'operations' in kwargs['output_schema']['properties']
            value=response(bad,'/cuts/0/allowed_new_reveal_elements/0')
        else:value={'result_json':json.dumps(scenes[1])}
        return SimpleNamespace(payload=value,transcript=(),provenance=SimpleNamespace(as_dict=lambda:{}))
    result=asyncio.run(author_cinematic_direction(run_dir=tmp_path,resources=resources,grounding='',client_factory=lambda:None,turn_runner=turn))
    assert result['scenes']==scenes
    assert len(calls)==3


def test_resolved_asset_id_stays_valid_when_reveal_diagnostics_are_mixed(tmp_path):
    from test_p420_asset_requests import fixture
    from toc.p420_assets import resolve_asset_requests
    story,sources,resources,rows=fixture(tmp_path)
    for name,raw in sources.items(): (tmp_path/f'{name}.md').write_bytes(raw)
    resolved,_,_=resolve_asset_requests(rows,story,json.loads(sources['research']),resources)
    bad=deepcopy(resolved[0]);bad['cuts'][0]['allowed_new_reveal_elements']=['unlicensed']
    asset_id=bad['cuts'][0]['object_ids'][0]
    calls=[]
    async def turn(**kwargs):
        calls.append(kwargs)
        if len(calls)==1: value={'result_json':json.dumps(bad)}
        elif len(calls)==2:
            diagnostics=json.loads(kwargs['prompt'])['diagnostics']
            assert [d['path'] for d in diagnostics]==['/cuts/0/allowed_new_reveal_elements/0']
            value=response(bad,'/cuts/0/allowed_new_reveal_elements/0')
        else:value={'result_json':json.dumps(rows[1])}
        return SimpleNamespace(payload=value,transcript=(),provenance=SimpleNamespace(as_dict=lambda:{}))
    result=asyncio.run(author_cinematic_direction(run_dir=tmp_path,resources=resources,grounding='',client_factory=lambda:None,turn_runner=turn))
    assert result['scenes'][0]['cuts'][0]['object_ids']==[asset_id]
    assert len(calls)==3


def test_schema_rejects_impossible_removal_from_required_id_list():
    document={'ids':['unknown']};d=Diagnostics(document);d.refs('/ids',{},many=True)
    d.items[0]['allow_remove']=True
    with pytest.raises(UnscopedRepairError): patch_schema(d.items,document)


def test_missing_drawable_frame_is_scoped_to_frame_text_not_whole_cut(tmp_path):
    from toc.downstream_repair import projection_diagnostics
    story,_,resources,scenes=sample(tmp_path)
    bad=deepcopy(scenes[0]);bad['cuts'][0]['first_frame_brief']='前sceneから続く修理工が工房に立っている。'
    issues=projection_diagnostics(bad,story['script']['scenes'][0],resources)
    assert [d['path'] for d in issues]==['/cuts/0/first_frame_brief']
    fixed=apply_patch(bad,issues,{'unit_id':bad['scene_id'],'base_digest':digest(bad),'operations':[
        {'path':'/cuts/0/first_frame_brief','value':scenes[0]['cuts'][0]['first_frame_brief']}]})
    assert fixed==scenes[0]
    assert projection_diagnostics(fixed,story['script']['scenes'][0],resources)==[]
