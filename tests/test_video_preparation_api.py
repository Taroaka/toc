import asyncio
import copy
import json
from pathlib import Path
import pytest
from PIL import Image
from server import video_preparation_api as route
from server import image_gen_app as app
from toc import scene_direction_service as service
from test_cut_direction_api import _fixture,_plan,_install_test_materializer


def setup(tmp_path,monkeypatch):
    root,data,_,_=_fixture(tmp_path)
    (root/'assets/audio').mkdir(exist_ok=True)
    (root/'assets/audio/one.mp3').write_bytes(b'voice')
    data['scenes'][0]['cuts'][1]['audio']={'narration':{'tool':'silent'}}
    data['scenes'][0]['cuts'][0]['video_generation'].update(tool='higgsfield',model='kling-video/v3.0/std/image-to-video')
    path,text,_=app._read_manifest_data(root);app._write_manifest_data(path,text,data)
    monkeypatch.setattr(app,'safe_run_dir',lambda run_id,repo:root)
    monkeypatch.setattr(route.RuntimeHooks,'check_audio',lambda *args:None)
    monkeypatch.setattr(app,'_narration_min_duration_seconds',lambda *args:3.5)
    _install_test_materializer(monkeypatch,root)
    return root,data


def test_scene_actual_images_pass_to_author_and_atomic_commit(tmp_path,monkeypatch):
    root,data=setup(tmp_path,monkeypatch)
    seen=[]
    async def author(self,context,images):
        seen.extend(images)
        return {'status':'revised','reason':'readable walk','cuts':{'scene10_cut01':_plan()}}
    async def image(self,item,kind,node,key):
        Image.new('RGB',(16,9),'green').save(root/'assets/scenes/candidate.png')
        return 'assets/scenes/candidate.png'
    async def review(*args):return {'status':'ready'}
    monkeypatch.setattr(route.RuntimeHooks,'author',author)
    monkeypatch.setattr(route.RuntimeHooks,'generate_image',image)
    monkeypatch.setattr(route.RuntimeHooks,'review',review)
    monkeypatch.setenv('TOC_PREPARATION_IMAGE_COST_UPPER_USD','0.25')
    monkeypatch.setenv('TOC_PREPARATION_VIDEO_SECOND_COST_UPPER_USD','0.1')
    original_audio=copy.deepcopy(data['scenes'][0]['cuts'][0]['audio'])
    result=asyncio.run(route.execute_preparation(route.PreparationRequest(run_id=root.name,max_image_generations=2,max_cost_usd=2)))
    assert result['status']=='completed',result
    published=app._read_manifest_data(root)[2]
    assert published['scenes'][0]['cuts'][0]['audio']==original_audio
    assert published['scenes'][0]['cuts'][0]['shot_plan']==_plan()
    assert root/'assets/scenes/scene10_cut01.png' in seen
    service.require_ready(root,published)


def test_author_conflict_cannot_overwrite_changed_audio(tmp_path,monkeypatch):
    root,data=setup(tmp_path,monkeypatch)
    async def author(self,context,images):
        p,t,current=app._read_manifest_data(root)
        current['scenes'][0]['cuts'][0]['audio']['narration']['text']='concurrent change'
        app._write_manifest_data(p,t,current)
        return {'status':'unchanged','cuts':{}}
    monkeypatch.setattr(route.RuntimeHooks,'author',author)
    result=asyncio.run(route.execute_preparation(route.PreparationRequest(run_id=root.name)))
    assert result['status']=='needs_input'
    assert app._read_manifest_data(root)[2]['scenes'][0]['cuts'][0]['audio']['narration']['text']=='concurrent change'


def test_get_is_read_only_and_no_generation(tmp_path,monkeypatch):
    root,_=setup(tmp_path,monkeypatch)
    result=asyncio.run(route.get_preparation(root.name))
    assert result['enabled'] is False
    assert not (root/service.BASE).exists()


def test_prompt_creation_requires_preparation_without_invoking_author(tmp_path,monkeypatch):
    root,data=setup(tmp_path,monkeypatch)
    data['video_metadata']['video_preparation_policy']=service.POLICY
    p,t,_=app._read_manifest_data(root);app._write_manifest_data(p,t,data)
    # This is the same guard used by p830 and p840; it is read-only.
    with pytest.raises(service.NeedsInput):service.require_ready(root,data)
    assert not (root/service.BASE).exists()


def test_scene_commit_uses_real_request_materializer(tmp_path,monkeypatch):
    from server import cut_direction_api as cut_api
    from test_cut_direction_api import test_publish_calls_real_manifest_materializer_and_publishes_shot_snapshot
    from toc.script_narration import resolve_manifest_narration
    async def publish_via_scene(**kwargs):
        root=kwargs['root'];hooks=route.RuntimeHooks(root);data=hooks.load()
        target=app._target_by_item_id(data,kwargs['item_id']);sid=str(target['scene']['scene_id'])
        target['cut']['video_generation'].update(tool='higgsfield',model='kling-video/v3.0/std/image-to-video')
        p,t,_=app._read_manifest_data(root);app._write_manifest_data(p,t,data)
        for cut in data['scenes'][0]['cuts']:
            for _,_,node in service.image_nodes(cut):
                dest=root/node['output'];dest.parent.mkdir(parents=True,exist_ok=True)
                Image.new('RGB',(16,9),'red').save(dest)
            audio=resolve_manifest_narration(cut) or {}
            if audio.get('output'):
                dest=root/audio['output'];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b'voice')
        snapshot=service.scene_snapshot(root,data,sid)
        new_scene=copy.deepcopy(target['scene'])
        new_scene['cuts'][target['cut_index']]=hooks.project(data,kwargs['item_id'],kwargs['plan_input'])
        outputs={}
        for cut in new_scene['cuts']:
            for _,_,node in service.image_nodes(cut):
                dest=root/node['output'];dest.parent.mkdir(parents=True,exist_ok=True)
                if not dest.exists():Image.new('RGB',(16,9),'green').save(dest)
                import hashlib
                outputs[node['output']]=hashlib.sha256(dest.read_bytes()).hexdigest()
        await hooks.publish(sid,snapshot,new_scene,expected_outputs=outputs)
        return cut_api.read_dto(root)
    monkeypatch.setattr(cut_api,'_publish_plan',publish_via_scene)
    test_publish_calls_real_manifest_materializer_and_publishes_shot_snapshot(tmp_path,monkeypatch)


def test_same_duration_replacement_reserves_full_new_video_request(tmp_path,monkeypatch):
    root,data=setup(tmp_path,monkeypatch)
    hooks=route.RuntimeHooks(root);before=data['scenes'][0];after=copy.deepcopy(before)
    after['cuts'][0]['video_generation']['motion_prompt']='changed acting'
    monkeypatch.setenv('TOC_PREPARATION_VIDEO_SECOND_COST_UPPER_USD','0.1')
    assert hooks.extra_video_cost(before,after)==pytest.approx(1.2)


def test_author_attachments_are_private_snapshots(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import hashlib
    from toc import story_author_runtime
    root,data=setup(tmp_path,monkeypatch);path=root/'assets/scenes/scene10_cut01.png'
    original=path.read_bytes()
    async def author(**kwargs):
        attachment=kwargs['local_images'][0]
        assert attachment!=path and not attachment.is_symlink()
        path.write_bytes(b'changed after attach')
        assert attachment.read_bytes()==original
        return SimpleNamespace(payload={'result_json':'{"status":"unchanged"}'})
    monkeypatch.setattr(story_author_runtime,'run_structured_story_turn',author)
    result=asyncio.run(route.RuntimeHooks(root)._author({},[path],{path.relative_to(root).as_posix():hashlib.sha256(original).hexdigest()}))
    assert result['status']=='unchanged'


def test_higgsfield_frame_mode_is_passed_to_manifest_capability_check():
    from toc.stage_evaluation.pipeline import _manifest_checks
    rows=[]
    data={'scenes':[{'scene_id':'1','cuts':[{'cut_id':'1','cut_contract':{'cinematic_direction_contract':'cinematic_direction_v1'},
        'image_generation':{'output':'assets/start.png'},'video_generation':{'tool':'higgsfield',
        'model':'kling-video/v3.0/std/image-to-video','first_frame':'assets/start.png','duration_seconds':8}}]}]}
    _manifest_checks(rows,'',data,profile='standard',flow='immersive',path_label='manifest')
    check=next(r for r in rows if r.get('id')=='manifest.node_types')
    assert check['passed'],check


def test_ready_survives_normal_video_prompt_materialization(tmp_path,monkeypatch):
    root,data=setup(tmp_path,monkeypatch)
    h=route.RuntimeHooks(root)
    cut=data['scenes'][0]['cuts'][0]
    plan=_plan()
    projected=h.project(data,cut['selector'],plan)
    data['scenes'][0]['cuts'][0]=projected
    for _,_,node in service.image_nodes(projected):
        dest=root/node['output'];dest.parent.mkdir(parents=True,exist_ok=True);Image.new('RGB',(16,9)).save(dest)
    p,t,_=app._read_manifest_data(root);app._write_manifest_data(p,t,data)
    snap=service.scene_snapshot(root,data,'10')
    service.save_json(root,service.BASE+'/current.json',{'enabled':True})
    service.save_json(root,service.BASE+'/ready/'+service.digest('10')+'.json',{'snapshot':snap['digest'],'policy':service.POLICY})
    shot=projected['shots'][0]
    item=app.FrontendReviewItem(item_id=shot['selector'],kind='scene',output=shot['image_generation']['output'],
        video_tool='higgsfield',video_duration_seconds=4,video_first_reference=shot['image_generation']['output'],video_aspect_ratio='16:9')
    app._update_manifest_video_generation(root,[item])
    assert service.scene_binding(data['scenes'][0])==service.scene_binding(h.load()['scenes'][0])
    service.require_ready(root,h.load(),{'10'})


def test_p840_reserves_actual_candidate_count_once_per_operation(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from toc.media_resume import ACTIVE_MEDIA_JOURNAL
    root,data=setup(tmp_path,monkeypatch)
    service.save_json(root,service.BASE+'/current.json',{'enabled':True,'limits':{'max_image_generations':0,'max_cost_usd':2}})
    monkeypatch.setenv('TOC_PREPARATION_VIDEO_SECOND_COST_UPPER_USD','0.1')
    item=app.VideoGenerateItem(item_id='scene10_cut01',prompt='walk',duration_seconds=4,candidate_count=3)
    token=ACTIVE_MEDIA_JOURNAL.set(SimpleNamespace(id='a'*32))
    try:
        route.reserve_video_execution(root,data,[item])
        route.reserve_video_execution(root,data,[item])
        assert service.CostLedger(root).summary()['reservedCostUsd']==pytest.approx(1.2)
        item.candidate_count=8
        with pytest.raises(service.NeedsInput):route.reserve_video_execution(root,data,[item])
    finally:ACTIVE_MEDIA_JOURNAL.reset(token)


def test_preparation_does_not_silently_switch_omni_to_standard(tmp_path,monkeypatch):
    root,data=setup(tmp_path,monkeypatch)
    data['scenes'][0]['cuts'][0]['video_generation']={'tool':'kling_3_0_omni','duration_seconds':4}
    with pytest.raises(service.NeedsInput):route.RuntimeHooks(root).project(data,'scene10_cut01',_plan())


def test_review_attaches_identity_references_with_hashes(tmp_path,monkeypatch):
    import hashlib
    root,data=setup(tmp_path,monkeypatch)
    node=data['scenes'][0]['cuts'][0]['image_generation'];node['references']=['assets/characters/keeper.png']
    paths={p for c in data['scenes'][0]['cuts'] for _,_,n in service.image_nodes(c) for p in [n['output'],*(n.get('references') or [])]}
    hashes={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
    async def read(payload,images,expected):
        assert root/'assets/characters/keeper.png' in images
        assert expected==hashes
        return {'status':'ready'}
    hook=route.RuntimeHooks(root);monkeypatch.setattr(hook,'_author',read)
    asyncio.run(hook.review(data['scenes'][0],{'prepared_image_hashes':hashes}))


def test_explicit_standard_selection_can_convert_legacy_omni(tmp_path,monkeypatch):
    root,data=setup(tmp_path,monkeypatch)
    data['scenes'][0]['cuts'][0]['video_generation']={'tool':'kling_3_0_omni','duration_seconds':4}
    projected=route.RuntimeHooks(root,'higgsfield_kling_standard').project(data,'scene10_cut01',_plan())
    assert projected['video_generation']==data['scenes'][0]['cuts'][0]['video_generation']
    assert projected['shots'][0]['video_generation']['model']=='kling-video/v3.0/std/image-to-video'


def test_cancel_keeps_durable_status_and_releases_task(tmp_path,monkeypatch):
    root,_=setup(tmp_path,monkeypatch)
    async def scenario():
        entered=asyncio.Event()
        async def author(*args):
            entered.set()
            await asyncio.Future()
        monkeypatch.setattr(route.RuntimeHooks,'author',author)
        await route.start_preparation(route.PreparationRequest(run_id=root.name))
        await asyncio.wait_for(entered.wait(),2)
        result=await route.cancel_preparation(route.CancelRequest(run_id=root.name))
        assert result['status']=='failed'
        assert root.name not in route._TASKS
        assert '再開' in result['error']
    asyncio.run(scenario())


def test_cli_uses_same_preparation_service(tmp_path,monkeypatch,capsys):
    import importlib.util
    import sys
    spec=importlib.util.spec_from_file_location('prepare_scene_cli',Path(__file__).resolve().parents[1]/'scripts/prepare-scene-video.py')
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    assert cli.execute_preparation is route.execute_preparation
    seen=[]
    async def execute(req):
        seen.append(req.model_dump())
        return {'status':'completed'}
    monkeypatch.setattr(cli,'execute_preparation',execute)
    monkeypatch.setattr(sys,'argv',['prepare-scene-video.py','--run-id','fixture','--execute',
        '--max-images','2','--max-cost-usd','5','--target-video-model','higgsfield_kling_standard'])
    assert cli.main()==0
    assert seen[0]['max_image_generations']==2 and seen[0]['target_video_model']=='higgsfield_kling_standard'
