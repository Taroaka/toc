import asyncio
import copy
import pytest
from toc import scene_direction_service as service
from test_scene_video_preparation import fixture, FakeHooks, opts


class RevisionHooks(FakeHooks):
    def __init__(self, root, data):
        super().__init__(root, data, {'status':'revised','cuts':{'scene1_cut1':{'version':1}}})
        self.contexts=[]
    async def author(self, context, images):
        self.contexts.append(copy.deepcopy(context))
        return await super().author(context,images)
    def project(self, data, selector, plan):
        c=copy.deepcopy(data['scenes'][0]['cuts'][0])
        c['image_generation']={'output':f"assets/repair{plan['version']}.png",'prompt':str(plan['version'])}
        return c
    async def review(self, scene, context):
        return {'status':'needs_input','reason':'pose differs'} if self.generated==1 else {'status':'ready'}


def test_rejected_review_revision_uses_candidates_and_preserves_history(tmp_path):
    root,data=fixture(tmp_path); h=RevisionHooks(root,data)
    first=asyncio.run(service.prepare_run(root,h,opts()))
    assert first['status']=='needs_input'
    old=list((root/service.BASE/'drafts').glob('*.json'))[0]
    old_bytes=old.read_bytes(); old_image=(root/'assets/repair1.png').read_bytes()
    h.proposal={'status':'revised','cuts':{'scene1_cut1':{'version':2}}}
    second=asyncio.run(service.prepare_run(root,h,opts(review_revision=1)))
    assert second['status']=='completed',second
    assert h.contexts[-1]['repair_feedback']['reason']=='pose differs'
    assert h.contexts[-1]['scene']['cuts'][0]['image_generation']['output']=='assets/repair1.png'
    assert old.read_bytes()==old_bytes and (root/'assets/repair1.png').read_bytes()==old_image
    assert h.generated==2
    asyncio.run(service.prepare_run(root,h,opts(review_revision=1)))
    assert h.generated==2 and h.calls==2


def test_revision_without_failed_parent_cannot_call_author(tmp_path):
    root,data=fixture(tmp_path); h=RevisionHooks(root,data)
    result=asyncio.run(service.prepare_run(root,h,opts(review_revision=1)))
    assert result['status']=='needs_input'
    assert h.calls==0


def test_revision_refuses_changed_rejected_image(tmp_path):
    root,data=fixture(tmp_path); h=RevisionHooks(root,data)
    asyncio.run(service.prepare_run(root,h,opts()))
    from PIL import Image
    Image.new('RGB',(16,9),'blue').save(root/'assets/repair1.png')
    result=asyncio.run(service.prepare_run(root,h,opts(review_revision=1)))
    assert result['status']=='needs_input'
    assert h.calls==1


def test_same_failed_image_request_cannot_be_rejudged_as_ready(tmp_path):
    root,data=fixture(tmp_path); h=RevisionHooks(root,data)
    asyncio.run(service.prepare_run(root,h,opts()))
    result=asyncio.run(service.prepare_run(root,h,opts(review_revision=1)))
    assert result['status']=='needs_input'
    assert '画像条件の変更がありません' in result['scenes'][0]['reason']
    assert h.generated==1


@pytest.mark.parametrize('revision', [-1,4,True])
def test_revision_budget_is_bounded(tmp_path,revision):
    root,data=fixture(tmp_path); h=RevisionHooks(root,data)
    with pytest.raises(ValueError,match='review_revision'):
        asyncio.run(service.prepare_run(root,h,opts(review_revision=revision)))


def test_revision_generates_new_start_before_hashing_dependent_end(tmp_path):
    class PairHooks(RevisionHooks):
        def project(self,data,selector,plan):
            cut=super().project(data,selector,plan)
            cut['shots']=[{'selector':selector+'_shot1','image_generation':copy.deepcopy(cut['image_generation']),
                'video_generation':{'result_frame':{'image_generation':{
                    'output':f"assets/end{plan['version']}.png",
                    'references':[cut['image_generation']['output']]}}}}]
            return cut
        async def review(self,scene,context):
            return {'status':'needs_input','reason':'pose differs'} if scene['cuts'][0]['image_generation']['prompt']=='1' else {'status':'ready'}
    root,data=fixture(tmp_path);h=PairHooks(root,data)
    assert asyncio.run(service.prepare_run(root,h,opts(max_image_generations=4)))['status']=='needs_input'
    assert h.generated==2
    h.proposal={'status':'revised','cuts':{'scene1_cut1':{'version':2}}}
    result=asyncio.run(service.prepare_run(root,h,opts(review_revision=1,max_image_generations=4)))
    assert result['status']=='completed',result
    assert h.generated==4


def test_old_revision_checkpoint_migrates_without_reauthoring(tmp_path):
    import json
    root,data=fixture(tmp_path);h=RevisionHooks(root,data)
    asyncio.run(service.prepare_run(root,h,opts(max_image_generations=1)))
    h.proposal={'status':'revised','cuts':{'scene1_cut1':{'version':2}}}
    result=asyncio.run(service.prepare_run(root,h,opts(review_revision=1,max_image_generations=1)))
    assert result['status']=='needs_input' and h.generated==1
    path=next(p for p in (root/service.BASE/'drafts').glob('*.json') if 'revision_parent' in json.loads(p.read_text()))
    saved=json.loads(path.read_text());saved['previous_image_request_keys']=['legacy-byte-key']
    del saved['previous_image_plan_keys'];saved.pop('image_plan_key_version',None);path.write_text(json.dumps(saved))
    result=asyncio.run(service.prepare_run(root,h,opts(review_revision=1)))
    assert result['status']=='completed',result
    assert h.calls==2 and h.generated==2
    assert json.loads(path.read_text())['previous_image_plan_keys']


def test_destination_only_revision_cannot_clear_failed_image_review(tmp_path):
    class RenameHooks(RevisionHooks):
        def project(self,data,selector,plan):
            cut=super().project(data,selector,plan)
            cut['image_generation']['first_frame_visual_plan']={'pose':'same failed pose'}
            return cut
    root,data=fixture(tmp_path);h=RenameHooks(root,data)
    asyncio.run(service.prepare_run(root,h,opts()))
    h.proposal={'status':'revised','cuts':{'scene1_cut1':{'version':2}}}
    result=asyncio.run(service.prepare_run(root,h,opts(review_revision=1)))
    assert result['status']=='needs_input'
    assert '画像条件の変更がありません' in result['scenes'][0]['reason']
    assert h.generated==1
