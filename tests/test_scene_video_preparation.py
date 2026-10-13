from __future__ import annotations
import asyncio
import copy
import json
from pathlib import Path
import pytest
from PIL import Image
from toc import scene_direction_service as service


def fixture(tmp_path):
    root = tmp_path / 'run'; root.mkdir()
    (root/'assets').mkdir()
    Image.new('RGB',(16,9),'red').save(root/'assets/start.png')
    (root/'assets/audio.wav').write_bytes(b'audio')
    (root/'story.md').write_text('source')
    scene={'scene_id':'1','cuts':[{'selector':'scene1_cut1','cut_id':'1',
        'duration_seconds':4,'audio':{'narration':{'output':'assets/audio.wav'}},
        'image_generation':{'output':'assets/start.png'},'video_generation':{'duration_seconds':4}}]}
    return root, {'scenes':[scene], 'resources':{}}


def test_snapshot_binds_actual_image_and_audio_bytes(tmp_path):
    root,data=fixture(tmp_path)
    before=service.scene_snapshot(root,data,'1')
    Image.new('RGB',(16,9),'blue').save(root/'assets/start.png')
    assert before['digest']!=service.scene_snapshot(root,data,'1')['digest']
    assert before['images']==['assets/start.png']
    (root/'assets/audio.wav').write_bytes(b'other')
    assert before['files']['assets/audio.wav']!=service.scene_snapshot(root,data,'1')['files']['assets/audio.wav']


def test_snapshot_rejects_external_reference(tmp_path):
    root,data=fixture(tmp_path)
    data['scenes'][0]['cuts'][0]['image_generation']['references']=['../escape.png']
    with pytest.raises(ValueError):service.scene_snapshot(root,data,'1')


def test_scope_ignores_unrelated_scene_but_binds_boundary(tmp_path):
    root,data=fixture(tmp_path)
    data['scenes'].extend([{'scene_id':'2','cuts':[]},{'scene_id':'3','cuts':[]}])
    before=service.scene_snapshot(root,data,'1')
    data['scenes'][2]['notes']='other edit'
    assert before['digest']==service.scene_snapshot(root,data,'1')['digest']
    data['scenes'][1]['scene_intent']='changed'
    assert before['digest']!=service.scene_snapshot(root,data,'1')['digest']


def test_budget_reserves_before_send_and_does_not_reset(tmp_path):
    root,_=fixture(tmp_path)
    b=service.CostLedger(root)
    b.reserve('one',image_count=1,cost_usd=0.5,max_images=1,max_cost_usd=1)
    b.reserve('one',image_count=1,cost_usd=0.5,max_images=1,max_cost_usd=1)
    assert b.summary()=={'imageCount':1,'reservedCostUsd':0.5}
    with pytest.raises(service.NeedsInput):
        service.CostLedger(root).reserve('two',image_count=1,cost_usd=0.5,max_images=1,max_cost_usd=1)


def test_budget_unknown_price_cannot_send(tmp_path):
    root,_=fixture(tmp_path)
    with pytest.raises(service.NeedsInput):
        service.CostLedger(root).reserve('one',image_count=1,cost_usd=None,max_images=5,max_cost_usd=10)


def test_locked_image_change_rejected_before_generation(tmp_path):
    root,data=fixture(tmp_path)
    old=data['scenes'][0]['cuts'][0]
    new=copy.deepcopy(old);new['image_generation']={'output':'assets/new.png'}
    with pytest.raises(service.NeedsInput):
        service.validate_fixed_images(old,new,['assets/start.png'])


def test_candidate_commit_never_changes_audio_or_source(tmp_path):
    root,data=fixture(tmp_path)
    old=data['scenes'][0]['cuts'][0]
    new=copy.deepcopy(old);new['audio']['narration']['text']='unapproved'
    with pytest.raises(ValueError):service.validate_visual_only(old,new)


def test_read_status_does_not_enable_or_call_author(tmp_path):
    root,_=fixture(tmp_path)
    assert service.read_status(root)['enabled'] is False
    assert not (root/'logs/video_preparation').exists()


class FakeHooks:
    def __init__(self,root,data,proposal):
        self.root=root;self.data=data;self.proposal=proposal;self.calls=0;self.generated=0
    def load(self):return copy.deepcopy(self.data)
    def check_audio(self,data,sid):pass
    def context(self,data,sid,snap):return {'scene':snap['scene']}
    async def author(self,context,images):
        self.calls+=1
        assert images and images[0].read_bytes()
        return copy.deepcopy(self.proposal)
    def project(self,data,selector,plan):
        c=copy.deepcopy(data['scenes'][0]['cuts'][0]);c['image_generation']['output']='assets/repaired.png';return c
    def validate(self,scene):pass
    def extra_video_cost(self,old,new):return 0
    def image_cost(self):return 0.25
    async def generate_image(self,item,kind,node,key):
        self.generated+=1
        Image.new('RGB',(16,9),'green').save(self.root/'assets/candidate.png')
        return 'assets/candidate.png'
    async def stage_image(self,source,destination):
        (self.root/destination).write_bytes((self.root/source).read_bytes())
    async def review(self,scene,context):return {'status':'ready'}
    async def publish(self,sid,snapshot,new_scene,*,expected_outputs):
        assert service.scene_snapshot(self.root,self.data,sid)['digest']==snapshot['digest']
        self.data['scenes'][0]=copy.deepcopy(new_scene)
        return service.scene_snapshot(self.root,self.data,sid)


def opts(**kwargs):return {'max_image_generations':2,'max_cost_usd':2,**kwargs}


def test_preparation_unchanged_resumes_without_another_author(tmp_path):
    root,data=fixture(tmp_path);h=FakeHooks(root,data,{'status':'unchanged','reason':'keep','cuts':{}})
    result=asyncio.run(service.prepare_run(root,h,opts()))
    assert result['status']=='completed' and h.calls==1
    asyncio.run(service.prepare_run(root,h,opts()))
    assert h.calls==1
    service.require_ready(root,h.load())
    (root/'assets/audio.wav').write_bytes(b'new voice')
    with pytest.raises(service.NeedsInput):service.require_ready(root,h.load())


def test_preparation_repairs_then_publishes_with_audio_unchanged(tmp_path):
    root,data=fixture(tmp_path);old=copy.deepcopy(data['scenes'][0]['cuts'][0]['audio'])
    h=FakeHooks(root,data,{'status':'revised','cuts':{'scene1_cut1':{}},'reason':'show contact'})
    result=asyncio.run(service.prepare_run(root,h,opts()))
    assert result['status']=='completed' and h.generated==1
    assert h.data['scenes'][0]['cuts'][0]['audio']==old
    assert (root/'assets/start.png').exists()
    service.require_ready(root,h.load())


def test_unknown_image_submission_never_reposts(tmp_path):
    root,data=fixture(tmp_path);h=FakeHooks(root,data,{'status':'revised','cuts':{'scene1_cut1':{}}})
    async def fail(*args):h.generated+=1;raise TimeoutError('unknown submission')
    h.generate_image=fail
    with pytest.raises(TimeoutError):asyncio.run(service.prepare_run(root,h,opts()))
    result=asyncio.run(service.prepare_run(root,h,opts()))
    assert result['status']=='needs_input' and h.generated==1 and h.calls==1


def test_budget_pause_reuses_author_proposal(tmp_path):
    root,data=fixture(tmp_path);h=FakeHooks(root,data,{'status':'revised','cuts':{'scene1_cut1':{}}})
    result=asyncio.run(service.prepare_run(root,h,opts(max_image_generations=0)))
    assert result['status']=='needs_input' and h.generated==0
    result=asyncio.run(service.prepare_run(root,h,opts()))
    assert result['status']=='completed' and h.calls==1


def test_preview_gate_never_calls_author(tmp_path):
    root,data=fixture(tmp_path)
    data['video_metadata']={'video_preparation_policy':service.POLICY}
    with pytest.raises(service.NeedsInput):service.require_ready(root,data)
    assert not (root/service.BASE).exists()


def test_derived_video_prompt_does_not_invalidate_ready_inputs(tmp_path):
    root,data=fixture(tmp_path)
    before=service.scene_snapshot(root,data,'1')['digest']
    data['scenes'][0]['cuts'][0]['video_generation']['compiled_api_prompt']='materialized'
    assert before==service.scene_snapshot(root,data,'1')['digest']
    data['scenes'][0]['cuts'][0]['video_generation']['duration_seconds']=8
    assert before!=service.scene_snapshot(root,data,'1')['digest']


def test_asset_bible_references_are_attached_and_bound(tmp_path):
    root,data=fixture(tmp_path)
    data.pop('resources')
    data['assets']={'character_bible':[{'character_id':'hero','reference_images':['assets/start.png']}]}
    cut=data['scenes'][0]['cuts'][0]
    Image.new('RGB',(16,9),'green').save(root/'assets/other.png')
    cut['image_generation']['output']='assets/other.png'
    cut['cut_contract']={'asset_dependency':{'character_ids_required':['hero']}}
    snapshot=service.scene_snapshot(root,data,'1')
    assert 'assets/start.png' in snapshot['images']
    assert 'assets/start.png' in snapshot['files']


def test_unprepared_other_scene_does_not_block_target(tmp_path):
    root,data=fixture(tmp_path)
    data['scenes'].append({'scene_id':'2','cuts':[]})
    h=FakeHooks(root,data,{'status':'unchanged','cuts':{}})
    asyncio.run(service.prepare_run(root,h,opts(scene_ids=['1'])))
    service.require_ready_for_items(root,h.load(),['scene1_cut1'])
    with pytest.raises(service.NeedsInput):service.require_ready(root,h.load())


def test_actual_video_reference_bytes_are_bound(tmp_path):
    root,data=fixture(tmp_path)
    Image.new('RGB',(16,9),'blue').save(root/'assets/video_ref.png')
    data['scenes'][0]['cuts'][0]['video_generation']['references']=['assets/video_ref.png']
    before=service.scene_snapshot(root,data,'1')
    Image.new('RGB',(16,9),'green').save(root/'assets/video_ref.png')
    assert service.scene_snapshot(root,data,'1')['digest']!=before['digest']
    data['scenes'][0]['cuts'][0]['video_generation']['input_mode']='reference_images'
    assert service.scene_snapshot(root,data,'1')['digest']!=before['digest']


def test_declared_image_repair_cannot_pass_as_unchanged(tmp_path):
    root,data=fixture(tmp_path)
    h=FakeHooks(root,data,{'status':'unchanged','cuts':{},'image_repairs':['scene1_cut1:first']})
    result=asyncio.run(service.prepare_run(root,h,opts()))
    assert result['status']=='needs_input'
    assert h.generated==0
    with pytest.raises(service.NeedsInput):service.require_ready(root,h.load())
