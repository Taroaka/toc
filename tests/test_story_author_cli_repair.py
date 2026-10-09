import asyncio
import hashlib
import importlib.util
import json
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


def cli():
    path=Path(__file__).resolve().parents[1]/'scripts/author-story-with-codex.py'
    spec=importlib.util.spec_from_file_location('story_cli_repair_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def setup(tmp_path, monkeypatch, role, payloads, schema, observed=None):
    m=cli();research=tmp_path/'research.md';research.write_text('```yaml\ntopic: sample\n```')
    args=m._parser().parse_args(['--research',str(research),'--output',str(tmp_path/'story.md'),'--topic','sample'])
    calls=observed if observed is not None else [];captured=[]
    async def transport(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(payload=payloads[len(calls)-1],provenance=SimpleNamespace(as_dict=lambda:{
            'prompt_sha256':hashlib.sha256(kwargs['prompt'].encode()).hexdigest(),'model':kwargs['model']}))
    async def author(*a,**kwargs):
        captured.append(await kwargs['turn_runner'](role=role,prompt='ORIGINAL_AUTHOR_TASK',output_schema=schema,scene_id='SC1'))
        return SimpleNamespace(validation_errors=(),source_digest='source')
    monkeypatch.setattr(m,'run_structured_story_turn',transport)
    monkeypatch.setattr(m,'author_story_from_research',author)
    asyncio.run(m._run(args))
    return calls,captured


def test_field_patch_schema_is_sent_directly_to_provider(tmp_path,monkeypatch):
    schema={'type':'object','additionalProperties':False,'required':['scene_id'], 'properties':{'scene_id':{'type':'string'}}}
    calls,result=setup(tmp_path,monkeypatch,'field_repair',[{'scene_id':'SC1'}],schema)
    assert calls[0]['output_schema']==schema
    assert 'TRANSPORT CONTRACT' not in calls[0]['prompt']
    assert result==[{'scene_id':'SC1'}]


def test_extra_closer_uses_no_llm_retry(tmp_path,monkeypatch):
    calls,result=setup(tmp_path,monkeypatch,'repair',[{'result_json':'{"scene_id":"SC1"}}'}],{'type':'object'})
    assert len(calls)==1
    assert result==[{'scene_id':'SC1'}]
    assert not (tmp_path/'logs/repair/ledger.json').exists()


def test_remaining_syntax_error_does_not_replay_author_task(tmp_path,monkeypatch):
    raw='{"a":1 "b":2}'
    calls,result=setup(tmp_path,monkeypatch,'repair',[{'result_json':raw},
        {'edits':[{'start':6,'end':6,'replacement':','}]}],{'type':'object'})
    assert len(calls)==2
    assert 'ORIGINAL_AUTHOR_TASK' not in calls[1]['prompt']
    assert calls[1]['output_schema']['required']==['edits']
    assert result==[{'a':1,'b':2}]


def test_legacy_valid_scene_cache_is_reused_with_new_named_targets(tmp_path,monkeypatch):
    m=cli();research=tmp_path/'research.md';research.write_text('```yaml\ntopic: sample\n```')
    args=m._parser().parse_args(['--research',str(research),'--output',str(tmp_path/'story.md'),'--topic','sample'])
    schema={'type':'object'}
    prompt=m.build_story_transport_prompt('ORIGINAL_AUTHOR_TASK',schema)
    payload={'scenes': [{'scene_id':'SC1'}]}
    output=tmp_path/'logs/authoring/story/outputs';output.mkdir(parents=True)
    (output/'001_scene_author_item.json').write_text(m._canonical_json(payload))
    (output/'001_scene_author_item.provenance.json').write_text(json.dumps({
        'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),
        'output_schema_sha256':hashlib.sha256(json.dumps(m.STORY_AUTHOR_TRANSPORT_SCHEMA,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        'decoded_payload_sha256':hashlib.sha256(m._canonical_json(payload).encode()).hexdigest(),
        'model':args.scene_author_model,
    }))
    provider=AsyncMock(side_effect=AssertionError('valid cache should avoid provider'))
    monkeypatch.setattr(m,'run_structured_story_turn',provider)
    async def author(*a,**kwargs):
        result=await kwargs['turn_runner'](role='scene_author',prompt='ORIGINAL_AUTHOR_TASK',output_schema=schema,scene_plans=[{'scene_id':'SC1'}])
        assert result==payload
        return SimpleNamespace(validation_errors=(),source_digest='source')
    monkeypatch.setattr(m,'author_story_from_research',author)
    asyncio.run(m._run(args))
    provider.assert_not_awaited()


def test_bad_envelope_cannot_be_accepted_as_inner_syntax_repair(tmp_path,monkeypatch):
    from toc.story_author_runtime import StoryAuthorRuntimeError
    calls=[]
    with pytest.raises(StoryAuthorRuntimeError, match='transport must contain only'):
        setup(tmp_path,monkeypatch,'repair',[{'result_json':'{"a":1 "b":2}','unexpected':'extra'}],{'type':'object'},observed=calls)
    assert len(calls)==1


def test_cache_only_miss_neither_calls_provider_nor_advances_ordinal(tmp_path,monkeypatch):
    from toc.story_author_pipeline import StoryAuthorCacheMiss
    m=cli();research=tmp_path/'research.md';research.write_text('```yaml\ntopic: sample\n```')
    args=m._parser().parse_args(['--research',str(research),'--output',str(tmp_path/'story.md'),'--topic','sample'])
    provider=AsyncMock(return_value=SimpleNamespace(payload={'scene_id':'SC1'},provenance=SimpleNamespace(as_dict=lambda:{'model':args.repair_author_model})))
    monkeypatch.setattr(m,'run_structured_story_turn',provider)
    async def author(*a,**kwargs):
        turn=kwargs['turn_runner']
        assert turn.supports_cache_lookup
        call={'role':'field_repair','scene_id':'SC1','prompt':'patch','output_schema':{'type':'object'}}
        with pytest.raises(StoryAuthorCacheMiss): await turn(**call,cache_only=True)
        provider.assert_not_awaited()
        assert await turn(**call)=={'scene_id':'SC1'}
        return SimpleNamespace(validation_errors=(),source_digest='source')
    monkeypatch.setattr(m,'author_story_from_research',author)
    asyncio.run(m._run(args))
    assert (tmp_path/'logs/authoring/story/outputs/001_field_repair_SC1.json').is_file()
    assert not (tmp_path/'logs/authoring/story/outputs/002_field_repair_SC1.json').exists()


def test_rejected_cache_hit_does_not_advance_provider_ordinal(tmp_path,monkeypatch):
    schema={'type':'object'}
    setup(tmp_path,monkeypatch,'field_repair',[{'scene_id':'wrong'}],schema)
    m=cli();args=m._parser().parse_args(['--research',str(tmp_path/'research.md'),'--output',str(tmp_path/'story.md'),'--topic','sample'])
    provider=AsyncMock(return_value=SimpleNamespace(payload={'scene_id':'SC1'},provenance=SimpleNamespace(as_dict=lambda:{'model':args.repair_author_model})))
    monkeypatch.setattr(m,'run_structured_story_turn',provider)
    async def author(*a,**kwargs):
        turn=kwargs['turn_runner']
        call={'role':'field_repair','scene_id':'SC1','prompt':'ORIGINAL_AUTHOR_TASK','output_schema':schema}
        assert (await turn(**call,cache_only=True))['scene_id']=='wrong'
        # The owner rejects the stale patch: do not commit this probe.
        assert await turn(**call,bypass_cache=True)=={'scene_id':'SC1'}
        return SimpleNamespace(validation_errors=(),source_digest='source')
    monkeypatch.setattr(m,'author_story_from_research',author)
    result=asyncio.run(m._run(args))
    assert result['turn_count']==1
    assert not (tmp_path/'logs/authoring/story/outputs/002_field_repair_SC1.json').exists()
    assert json.loads((tmp_path/'logs/authoring/story/outputs/001_field_repair_SC1.json').read_text())=={'scene_id':'SC1'}
