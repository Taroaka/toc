from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import asyncio
import pytest
import yaml
from toc import narration_authoring as author


def documents():
    spoken={'tool':'elevenlabs','text':'短い下書きです。','tts_text':'短い下書きです。','authoring_status':'draft'}
    silent={'tool':'silent','text':'','tts_text':'','authoring_status':'silent','silence_contract':{'intentional':True}}
    data={'scenes':[{'scene_id':1,'cuts':[{'cut_id':1,'audio':{'narration':spoken},'image_generation':{'output':'assets/a.png'}}, {'cut_id':2,'audio':{'narration':silent},'narration_authoring':{'status':'silent'},'image_generation':{'output':'assets/b.png'}}]}]}
    return deepcopy(data),deepcopy(data)


def plan():
    return {'schema_version':'audio_story_plan_v1','authoring_provenance':'audio_story_director','authoring_status':'authored',
      'audience_promise':'約束の行方を追う','narrator_bible':{'relationship_to_story':'第三者','knowledge_boundary':['原作'],'emotional_permission':['温かく'],'forbidden_attitudes':['先取り']},
      'continuous_full_draft':'彼は、約束を思い出します。そして帰る道を選びます。','scene_arcs':[{'scene_id':1,'attention_state':'理解','audience_state_before':'理由を知らない','audience_state_after':'理由が分かる','semantic_load':'一つずつ'}], 'open_loops':[], 'silence_budget':{'intentional_silence_cut_ids':['scene1_cut2']},'duration_assessment':{'rationale':'原作と既存映像の間を守る','planned_narration_seconds':10}}


def allocation():
    txt=plan()['continuous_full_draft']
    return {'scenes':[{'scene_id':1,'cuts':[{'cut_id':1,'narration_text':txt,'tts_text':'[Warm, calm narration, slow measured delivery] '+txt}, {'cut_id':2,'narration_text':'','tts_text':''}]}],
       'narration_spans':[{'span_id':'ns1','source_cut_ids':['scene1_cut1'],'story_job':'aftertaste','text':txt,'tts_text':'[Warm, calm narration, slow measured delivery] '+txt,'tts_generation_group_id':'flow1','audio_visual_relation':'complement','opened_loop_ids':[],'closed_loop_ids':[]}]}


def test_allocation_preserves_images_silence_and_whole_draft():
    script,manifest=documents();before=deepcopy(manifest)
    projected,by_scene=author.validate_allocation(script,manifest,plan(),allocation())
    assert projected['scenes'][0]['cuts'][0]['image_generation']==before['scenes'][0]['cuts'][0]['image_generation']
    assert projected['scenes'][0]['cuts'][1]['audio']['narration']['text']==''
    assert projected['audio_story_plan']['continuous_full_draft']==plan()['continuous_full_draft']
    assert manifest==before


@pytest.mark.parametrize('failure',['changed_text','missing_cut','voiced_silence','changed_lock'])
def test_allocation_rejects_content_or_inventory_changes(failure):
    script,manifest=documents();a=allocation()
    if failure=='changed_text':a['scenes'][0]['cuts'][0]['narration_text']='別の話です。'
    if failure=='missing_cut':a['scenes'][0]['cuts'].pop()
    if failure=='voiced_silence':a['scenes'][0]['cuts'][1]['narration_text']='無音に追加'
    if failure=='changed_lock':script['scenes'][0]['cuts'][0]['narration_authoring']={'status':'human_locked'}
    with pytest.raises(ValueError):author.validate_allocation(script,manifest,plan(),a)


def test_two_stage_author_runs_before_publication(tmp_path,monkeypatch):
    script,manifest=documents()
    for name,data in [('script.md',script),('video_manifest.md',manifest)]:
        (tmp_path/name).write_text('```yaml\n'+yaml.safe_dump(data,allow_unicode=True)+'```\n')
    for name in ['research.md','story.md','visual_value.md']:(tmp_path/name).write_text('根拠となる物語。')
    calls=[]
    async def runner(**kwargs):
        calls.append(kwargs['prompt'])
        payload={'audio_story_plan':plan()} if len(calls)==1 else allocation()
        return SimpleNamespace(payload={'result_json':json.dumps(payload,ensure_ascii=False)},provenance=SimpleNamespace(as_dict=lambda:{'model':'test'}),transcript=())
    published=[]
    monkeypatch.setattr(author,'publish_narration',lambda *args,**kwargs:published.append(kwargs))
    result=asyncio.run(author.author_full_run_narration(run_dir=tmp_path,client_factory=lambda:None,turn_runner=runner))
    assert len(calls)==2
    assert 'continuous_full_draft' in calls[0]
    assert plan()['continuous_full_draft'] in calls[1]
    assert len(published)==1
    assert result['status']=='authored'


def test_real_publication_changes_only_narration_and_reuses_on_retry(tmp_path):
    script,manifest=documents()
    for name,data in [('script.md',script),('video_manifest.md',manifest)]:
        (tmp_path/name).write_text('```yaml\n'+yaml.safe_dump(data,allow_unicode=True)+'```\n')
    for name in ['research.md','story.md','visual_value.md']:(tmp_path/name).write_text('根拠となる物語。')
    calls=[]
    async def runner(**kwargs):
        calls.append(kwargs['prompt'])
        payload={'audio_story_plan':plan()} if len(calls)==1 else allocation()
        return SimpleNamespace(payload={'result_json':json.dumps(payload,ensure_ascii=False)},provenance=SimpleNamespace(as_dict=lambda:{'model':'test'}),transcript=())
    first=asyncio.run(author.author_full_run_narration(run_dir=tmp_path,client_factory=lambda:None,turn_runner=runner))
    second=asyncio.run(author.author_full_run_narration(run_dir=tmp_path,client_factory=lambda:None,turn_runner=runner))
    assert first['status']=='authored' and second['status']=='reused'
    assert len(calls)==2
    _,published=author.load_structured_document(tmp_path/'video_manifest.md')
    for before,after in zip(manifest['scenes'][0]['cuts'],published['scenes'][0]['cuts']):
        assert before['image_generation']==after['image_generation']
    assert author.full_run_narration_current(author.load_structured_document(tmp_path/'script.md')[1],published)


def test_manifest_only_human_lock_cannot_be_overwritten():
    script,manifest=documents()
    manifest['scenes'][0]['cuts'][0]['audio']['narration'].update(
        authoring_status='human_locked',text='人が確定した別の原稿です。',tts_text='人が確定した別の原稿です。')
    with pytest.raises(ValueError,match='protected'):
        author.validate_allocation(script,manifest,plan(),allocation())


def test_source_drift_never_publishes(tmp_path,monkeypatch):
    script,manifest=documents()
    for name,data in [('script.md',script),('video_manifest.md',manifest)]:
        (tmp_path/name).write_text('```yaml\n'+yaml.safe_dump(data,allow_unicode=True)+'```\n')
    for name in ['research.md','story.md']:(tmp_path/name).write_text('根拠となる物語。')
    async def runner(**kwargs):
        (tmp_path/'story.md').write_text('別の物語に変更された。')
        return SimpleNamespace(payload={'result_json':json.dumps({'audio_story_plan':plan()},ensure_ascii=False)},provenance=SimpleNamespace(as_dict=lambda:{}),transcript=())
    published=[]
    monkeypatch.setattr(author,'publish_narration',lambda *a,**kw:published.append(kw))
    with pytest.raises(RuntimeError,match='source changed'):
        asyncio.run(author.author_full_run_narration(run_dir=tmp_path,client_factory=lambda:None,turn_runner=runner))
    assert not published


def test_first_draft_context_omits_old_cut_timing_and_draft_text():
    script,manifest=documents()
    cut=manifest['scenes'][0]['cuts'][0]
    cut['video_generation']={'duration_seconds':1}
    cut['cut_contract']={'narration_contract':{'rhythm_and_timing':{'maximum_seconds':1}}}
    context=json.dumps(author.draft_semantic_context(manifest),ensure_ascii=False)
    assert 'maximum_seconds' not in context
    assert '短い下書きです。' not in context
    assert 'scene1_cut2' in context


def test_explicit_rewrite_does_not_replay_prior_author_response(tmp_path,monkeypatch):
    script,manifest=documents()
    for name,data in [('script.md',script),('video_manifest.md',manifest)]:
        (tmp_path/name).write_text('```yaml\n'+yaml.safe_dump(data,allow_unicode=True)+'```\n')
    for name in ['research.md','story.md']:(tmp_path/name).write_text('根拠となる物語。')
    calls=[]
    async def runner(**kwargs):
        calls.append(kwargs['prompt'])
        payload={'audio_story_plan':plan()} if len(calls)%2 else allocation()
        return SimpleNamespace(payload={'result_json':json.dumps(payload,ensure_ascii=False)},provenance=SimpleNamespace(as_dict=lambda:{}),transcript=())
    monkeypatch.setattr(author,'publish_narration',lambda *args,**kwargs:None)
    first=asyncio.run(author.author_full_run_narration(run_dir=tmp_path,client_factory=lambda:None,turn_runner=runner,force=True))
    second=asyncio.run(author.author_full_run_narration(run_dir=tmp_path,client_factory=lambda:None,turn_runner=runner,force=True))
    assert len(calls)==4
    assert first['log_dir']!=second['log_dir']


def test_retry_reuses_completed_draft_checkpoint(tmp_path,monkeypatch):
    script,manifest=documents()
    for name,data in [('script.md',script),('video_manifest.md',manifest)]:
        (tmp_path/name).write_text('```yaml\n'+yaml.safe_dump(data,allow_unicode=True)+'```\n')
    for name in ['research.md','story.md']:(tmp_path/name).write_text('根拠となる物語。')
    calls=[]
    async def runner(**kwargs):
        calls.append(kwargs['prompt'])
        if len(calls)==2:raise RuntimeError('transport failure at allocation')
        payload={'audio_story_plan':plan()} if len(calls)==1 else allocation()
        return SimpleNamespace(payload={'result_json':json.dumps(payload,ensure_ascii=False)},provenance=SimpleNamespace(as_dict=lambda:{}),transcript=())
    monkeypatch.setattr(author,'publish_narration',lambda *args,**kwargs:None)
    with pytest.raises(RuntimeError,match='transport failure'):
        asyncio.run(author.author_full_run_narration(run_dir=tmp_path,client_factory=lambda:None,turn_runner=runner,force=True))
    result=asyncio.run(author.author_full_run_narration(run_dir=tmp_path,client_factory=lambda:None,turn_runner=runner))
    assert len(calls)==3 and result['status']=='authored'
    assert calls[1]==calls[2]


@pytest.mark.parametrize('field',['silence_budget','duration_assessment'])
def test_missing_full_plan_fields_block_publication(field):
    script,manifest=documents();p=plan();p.pop(field)
    with pytest.raises(ValueError,match=field):author.validate_allocation(script,manifest,p,allocation())


def test_api_author_entrypoint_prepares_readset_before_model(tmp_path,monkeypatch):
    from server import image_gen_app as app
    events=[]
    def prepare(*args,**kwargs):
        events.append('readset')
        assert '--stage' in args[0] and 'narration' in args[0]
        assert kwargs['check'] is True
    async def run(**kwargs):
        events.append('author')
        assert kwargs['force'] is True
        return {'status':'authored'}
    monkeypatch.setattr(app.subprocess,'run',prepare)
    monkeypatch.setattr(author,'author_full_run_narration',run)
    result=asyncio.run(app._author_automatic_narration(tmp_path,force=True))
    assert events==['readset','author']
    assert result['status']=='authored'


def test_single_cut_loop_declarations_bind_without_rewriting_spoken_text():
    script,manifest=documents();p=plan();p['narrator_bible']['emotional_permission']='温かく見守る'
    for document in (script,manifest):
        document['scenes'][0]['cuts'][1]['audio']['narration']={'tool':'elevenlabs','text':'旧稿の結末です。','tts_text':'旧稿の結末です。','authoring_status':'draft'}
        document['scenes'][0]['cuts'][1]['narration_authoring']={'status':'draft'}
    p['open_loops']=[{'loop_id':'q1','question':'帰るのでしょうか','payoff_type':'answer'}]
    a=allocation()
    parts=['彼は、約束を思い出します。','そして帰る道を選びます。']
    a['narration_spans']=[]
    for index,text in enumerate(parts):
        a['scenes'][0]['cuts'][index].update(narration_text=text,tts_text=text)
        a['narration_spans'].append({'span_id':f'ns{index+1}','source_cut_ids':[f'scene1_cut{index+1}'],
            'story_job':'aftertaste','text':text,'tts_text':text,'tts_generation_group_id':'flow1','audio_visual_relation':'complement',
            'opened_loop_ids':['q1'] if index==0 else [],'closed_loop_ids':['q1'] if index==1 else []})
    projected,_=author.validate_allocation(script,manifest,p,a)
    updated=projected['audio_story_plan']
    assert author._speech(updated['continuous_full_draft'])==author._speech(p['continuous_full_draft'])
    assert updated['narrator_bible']['emotional_permission']==['温かく見守る']
    assert updated['open_loops'][0]['opened_at']=='scene1_cut1'
    assert updated['open_loops'][0]['payoff_at']=='scene1_cut2'
    assert 'opened_at' not in p['open_loops'][0]


def test_cross_cut_loop_requires_explicit_anchor():
    p=plan();p['open_loops']=[{'loop_id':'q1','payoff_type':'answer'}]
    a={'narration_spans':[{'source_cut_ids':['scene1_cut1','scene1_cut2'],'opened_loop_ids':['q1'],'closed_loop_ids':['q1']}]}
    with pytest.raises(ValueError,match='exact opened_at'):
        author.bind_open_loop_anchors(p,a)


def test_frozen_draft_preserves_internal_spaces():
    assert author._speech('A B。') != author._speech('AB。')
    assert author._speech('A B。\n続き。') == author._speech('A B。続き。')


def test_plan_shape_errors_are_reported_before_allocation():
    _,manifest=documents();p=plan()
    p['narrator_bible'].pop('knowledge_boundary')
    p['silence_budget']='not a mapping'
    with pytest.raises(ValueError) as exc:author.validate_draft_plan(p,manifest)
    assert 'knowledge_boundary' in str(exc.value)
    assert 'silence_budget' in str(exc.value)
