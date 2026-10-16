"""Shared scene preparation. Authoring decisions and paid calls are injected.

The manifest remains canonical. These journals describe pending work and bind
its inputs; they never turn stale generations into new provider provenance.
"""
from __future__ import annotations
import asyncio
import copy
import hashlib
import json
import math
import uuid
from pathlib import Path
from typing import Any
from toc.run_root_binding import read_run_file_bytes, write_run_file_text
from toc.runtime_locks import sync_file_lock, async_file_lock
from toc.shot_direction import parent_duration_seconds
from toc.script_narration import resolve_manifest_narration

POLICY = 'scene_video_preparation_v1'
BASE = 'logs/video_preparation'


def phase_base(phase):
    if phase == 'video':return BASE
    if phase == 'images':
        from toc.image_consistency import BASE as image_base
        return image_base
    raise ValueError('unknown preparation phase')


def phase_policy(phase):
    if phase == 'images':
        from toc.image_consistency import POLICY as image_policy
        return image_policy
    phase_base(phase)
    return POLICY


def preparation_snapshot(root,data,scene_id,phase='video'):
    if phase == 'images':
        from toc.image_consistency import image_snapshot
        return image_snapshot(root,data,scene_id)
    phase_base(phase)
    return scene_snapshot(root,data,scene_id)

class NeedsInput(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def read_json(root, path, default=None):
    try:return json.loads(read_run_file_bytes(root,path))
    except FileNotFoundError:return copy.deepcopy(default)


def save_json(root,path,data):
    write_run_file_text(root,path,json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def asset_bytes(root: Path,path: str) -> bytes:
    p=Path(path)
    if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0]!='assets':
        raise ValueError('media must be a run-relative assets path: '+str(path))
    return read_run_file_bytes(root,path)


def image_nodes(cut):
    for shot in cut.get('shots') or [cut]:
        selector=str(shot.get('selector') or cut.get('selector') or '')
        if shot.get('image_generation'):
            yield selector, 'first', shot['image_generation']
        result=(shot.get('video_generation') or {}).get('result_frame') or {}
        if result.get('image_generation'):
            yield selector, 'last', result['image_generation']


def _scene(data,scene_id):
    matches=[s for s in data.get('scenes',[]) if str(s.get('scene_id'))==str(scene_id)]
    if len(matches)!=1:raise ValueError('scene not uniquely found: '+str(scene_id))
    return matches[0]


def _boundary(scene,from_end):
    cuts=scene.get('cuts') or []
    cut=cuts[-1 if from_end else 0] if cuts else {}
    return {'scene_id':scene.get('scene_id'),'scene_intent':scene.get('scene_intent'),
        'handoff':scene.get('handoff_to_next_scene') if from_end else None,'edge_contract':cut.get('cut_contract'),
        'last_shot':(cut.get('shot_plan') or {}).get('shots',[])[-1:] if from_end else None}


def scene_binding(scene):
    """Exclude materialized prose/output bookkeeping; bind actual creative inputs."""
    value=copy.deepcopy(scene)
    def cut_binding(cut):
        video=cut.get('video_generation') or {}
        cut['video_generation']={k:video[k] for k in (
            'tool','model','duration_seconds','first_frame','last_frame','native_audio',
            'result_state_reference','result_frame','quality','aspect_ratio','resolution','references','input_mode') if k in video and video[k] is not None}
        cut['video_generation'].setdefault('references',[])
        cut['video_generation'].setdefault('input_mode','image_to_video')
        cut['video_generation'].setdefault('aspect_ratio',(cut.get('image_generation') or {}).get('aspect_ratio') or '16:9')
        render=cut.get('render') or {}
        cut['render']={k:render[k] for k in ('video_duration_seconds','narration_offset_seconds','narration_path') if k in render}
        cut['render'].setdefault('video_duration_seconds',video.get('duration_seconds') or cut.get('duration_seconds'))
        for shot in cut.get('shots') or []:cut_binding(shot)
    for cut in value.get('cuts',[]):cut_binding(cut)
    return value


def resource_registry(data):
    direct=data.get('resources') or {}
    if any(isinstance(direct.get(g),dict) for g in ('characters','objects','locations')):
        return copy.deepcopy(direct)
    assets=data.get('assets') or {};result={'characters':{},'objects':{},'locations':{}}
    for group,bible,id_key in (('characters','character_bible','character_id'),('objects','object_bible','object_id'),('locations','location_bible','location_id')):
        for row in assets.get(bible) or []:
            aid=row.get(id_key) or row.get('asset_id')
            if not aid:continue
            entry=copy.deepcopy(row)
            entry['name']=row.get('name') or row.get('display_name') or aid
            entry['references']=row.get('references') or row.get('reference_images') or (row.get('generation_plan') or {}).get('reference_inputs') or []
            result[group][aid]=entry
    return result


def scene_snapshot(root,data,scene_id):
    scene=_scene(data,scene_id); scenes=data['scenes'];index=scenes.index(scene)
    files={};images=[]
    for name in ('story.md','script.md','cinematic_direction.json','cinematic_preferences.md'):
        try:files[name]=hashlib.sha256(read_run_file_bytes(root,name)).hexdigest()
        except FileNotFoundError:files[name]=None
    def include(path,image=False):
        if not path:return
        raw=asset_bytes(root,str(path));files[str(path)]=hashlib.sha256(raw).hexdigest()
        if image and str(path) not in images:
            from io import BytesIO
            from PIL import Image
            with Image.open(BytesIO(raw)) as im:im.verify()
            images.append(str(path))
    resources=resource_registry(data)
    for cut in scene.get('cuts',[]):
        dependency=(cut.get('cut_contract') or {}).get('asset_dependency') or {}
        for group,kind in (('characters','character'),('objects','object'),('locations','location')):
            for aid in dependency.get(kind+'_ids_required') or []:
                row=(resources.get(group) or {}).get(aid) or {}
                for ref in row.get('references') or []:include(ref,True)
        for shot in cut.get('shots') or [cut]:
            video=shot.get('video_generation') or {}
            for path in [video.get('first_frame'),video.get('last_frame'),*(video.get('references') or [])]:include(path,True)
        for _,_,node in image_nodes(cut):
            include(node.get('output'),True)
            for ref in node.get('references') or []:include(ref,True)
        narration=resolve_manifest_narration(cut) or {}
        if narration.get('tool')!='silent':
            selected=((narration.get('generation') or {}).get('selected_candidate') or {})
            path=narration.get('output') or selected.get('output')
            if (narration.get('text') or narration.get('tts_text')) and not path:
                raise NeedsInput('採用音声がありません: '+str(cut.get('selector')))
            include(path)
    payload={'policy':POLICY,'scene':scene_binding(scene),'resources':data.get('resources',data.get('assets')),
        'film':{k:v for k,v in (data.get('video_metadata') or {}).items() if k not in ('duration_seconds','video_preparation')},
        'previous':_boundary(scenes[index-1],True) if index else None,
        'next':_boundary(scenes[index+1],False) if index+1<len(scenes) else None,'files':files}
    return {'digest':digest(payload),'files':files,'images':images,'scene':copy.deepcopy(scene),
        'boundaries':{'previous':payload['previous'],'next':payload['next']}}


def validate_visual_only(old,new):
    allowed={'shot_plan','shots','image_generation','shot_direction_override'}
    if {k:v for k,v in old.items() if k not in allowed}!={k:v for k,v in new.items() if k not in allowed}:
        raise ValueError('preparation changed protected narration, timing or source fields')


def validate_fixed_images(old,new,paths):
    before={n.get('output') for _,_,n in image_nodes(old)}
    after={n.get('output') for _,_,n in image_nodes(new)}
    if (set(paths)&before)-after and not all(any(can_reuse(n,nn) for _,_,nn in image_nodes(new)) for _,_,n in image_nodes(old) if n.get('output') in paths):
        raise NeedsInput('固定された画像の変更が必要です。固定を解除するか演出を指定してください。')


class CostLedger:
    """Run-wide, non-resetting upper-estimate reservations. Unknown sends retain cost."""
    def __init__(self,root):self.root=Path(root)
    def summary(self):
        rows=read_json(self.root,BASE+'/costs.json',{})
        return {'imageCount':sum(r['image_count'] for r in rows.values()),
                'reservedCostUsd':round(sum(r['cost_usd'] for r in rows.values()),8)}
    def reserve(self,key,*,image_count,cost_usd,max_images,max_cost_usd):
        if isinstance(image_count,bool) or not isinstance(image_count,int) or image_count<0:raise ValueError('invalid image count')
        if cost_usd is None or max_cost_usd is None:
            raise NeedsInput('追加生成の費用上限見積または予算が未設定です。')
        if any(isinstance(x,bool) or not isinstance(x,(float,int)) or not math.isfinite(x) or x<0 for x in (cost_usd,max_cost_usd)):
            raise ValueError('invalid cost')
        with sync_file_lock(self.root/'.locks/video_preparation_costs.lock'):
            rows=read_json(self.root,BASE+'/costs.json',{})
            if key in rows:
                if rows[key]!={'image_count':image_count,'cost_usd':cost_usd}:raise ValueError('reservation changed')
                return
            if sum(r['image_count'] for r in rows.values())+image_count>max_images:
                raise NeedsInput('追加画像の回数上限に達しました。')
            if sum(r['cost_usd'] for r in rows.values())+cost_usd>max_cost_usd+1e-9:
                raise NeedsInput('追加生成の費用枠が不足しています。')
            rows[key]={'image_count':image_count,'cost_usd':cost_usd}
            save_json(self.root,BASE+'/costs.json',rows)


def read_status(root,phase='video'):
    state=read_json(root,phase_base(phase)+'/current.json',{'runId':root.name,'enabled':False,
        'operationId':None,'status':'idle','scenes':[]})
    if state.get('enabled'):state['budget']=CostLedger(root).summary()
    return state


def is_enabled(root):return read_status(root).get('enabled',False)


def image_consistency_required(root,data):
    from toc.image_consistency import POLICY as image_policy
    metadata=data.get('video_metadata') or {}
    return (metadata.get('video_preparation_policy')==POLICY or
            metadata.get('image_consistency_policy')==image_policy or
            read_status(root,'images').get('enabled',False))


def require_images_ready(root,data):
    if not image_consistency_required(root,data):return
    for scene in data.get('scenes',[]):
        sid=str(scene['scene_id'])
        snap=preparation_snapshot(root,data,sid,'images')
        receipt=read_json(root,f'{phase_base("images")}/ready/{digest(sid)}.json',{})
        if receipt.get('snapshot')!=snap['digest'] or receipt.get('policy')!=phase_policy('images'):
            raise NeedsInput('ナレーション前の画像整合確認・修正が未完了です: scene '+sid)


def scenes_for_items(data, item_ids):
    wanted=set(item_ids);found=set();scenes=set()
    for scene in data.get('scenes',[]):
        for cut in scene.get('cuts',[]):
            selectors={str(cut.get('selector'))}|{str(s.get('selector')) for s in cut.get('shots') or []}
            matches=selectors&wanted
            if matches:found.update(matches);scenes.add(str(scene['scene_id']))
    if found!=wanted:raise ValueError('video preparation target not found')
    return scenes


def require_ready_for_items(root,data,item_ids):
    if not is_enabled(root) and (data.get('video_metadata') or {}).get('video_preparation_policy')!=POLICY:return
    require_ready(root,data,scenes_for_items(data,item_ids))


def require_ready(root,data,scene_ids=None):
    if not is_enabled(root) and (data.get('video_metadata') or {}).get('video_preparation_policy')!=POLICY:return
    for scene in data.get('scenes',[]):
        sid=str(scene['scene_id'])
        if scene_ids is not None and sid not in scene_ids:continue
        snap=scene_snapshot(root,data,sid)
        receipt=read_json(root,f'{BASE}/ready/{digest(sid)}.json',{})
        if receipt.get('snapshot')!=snap['digest'] or receipt.get('policy')!=POLICY:
            raise NeedsInput('動画生成前の演出調整が未完了か、素材が変更されました: scene '+sid)


def image_signature(node):
    # Compare only static source, excluding versioned destination names.
    return digest({k:node.get(k) for k in ('first_frame_visual_plan','character_ids','object_ids',
        'location_ids','references','aspect_ratio','image_size')})


def can_reuse(old,new):
    return bool(old.get('first_frame_visual_plan')) and image_signature(old)==image_signature(new)



async def prepare_run(root,hooks,options):
    """All entrypoints call this service. Hooks are the existing runtime adapters."""
    root=Path(root)
    phase=options.get('phase','video');base=phase_base(phase);policy=phase_policy(phase)
    revision=options.get('review_revision',0)
    if type(revision) is not int or not 0<=revision<=3:raise ValueError('review_revision must be between 0 and 3')
    async with async_file_lock(root/'.locks/video_preparation.lock',wait=False):
        data=hooks.load()
        ids=options.get('scene_ids') or [str(s['scene_id']) for s in data.get('scenes',[])]
        if len(set(ids))!=len(ids):raise ValueError('duplicate scene IDs')
        for sid in ids:_scene(data,sid)
        state={'runId':root.name,'enabled':True,'phase':phase,'operationId':uuid.uuid4().hex,'status':'running','scenes':[],
            'review_revision':revision,
            'fixed_image_paths':list(options.get('fixed_image_paths') or []),'target_video_model':options.get('target_video_model'),
            'limits':{'max_image_generations':options['max_image_generations'],'max_cost_usd':options.get('max_cost_usd')}}
        ledger=CostLedger(root)
        def save():
            state['budget']=ledger.summary();save_json(root,base+'/current.json',state)
            save_json(root,base+'/operations/'+state['operationId']+'.json',state)
        save()
        try:
            for sid in ids:
                row={'sceneId':sid,'status':'running','reason':'','changedCuts':[],'imageCount':0}
                state['scenes'].append(row);save()
                try:
                    data=hooks.load();snap=preparation_snapshot(root,data,sid,phase)
                    ready=read_json(root,f'{base}/ready/{digest(sid)}.json',{})
                    if ready.get('snapshot')==snap['digest'] and ready.get('policy')==policy and getattr(hooks,'target_satisfied',lambda scene:True)(snap['scene']):
                        row.update(status='unchanged',reason='同じ画像・視覚設計を確認済みです。' if phase=='images' else '同じ音声・画像・設計を確認済みです。');save();continue
                    if phase=='video':hooks.check_audio(data,sid)
                    context=hooks.context(data,sid,snap)
                    fixed=sorted(options.get('fixed_image_paths') or [])
                    for path in fixed:asset_bytes(root,path)
                    context['fixed_image_paths']=fixed
                    cache_key=digest({'snapshot':snap['digest'],'fixed':fixed,'target_model':options.get('target_video_model')})
                    from toc.preparation_review_revision import revision_path,revision_context,image_request_key,image_plan_keys
                    checkpoint_path=revision_path(base,cache_key,revision)
                    checkpoint=read_json(root,checkpoint_path,{})
                    if not checkpoint:
                        images=snap['images'];previous_plans={};previous_image_keys=[]
                        if revision:
                            for prior_revision in range(revision):
                                parent=read_json(root,revision_path(base,cache_key,prior_revision),{})
                                if parent.get('snapshot')!=snap['digest'] or (parent.get('review') or {}).get('status')!='needs_input':
                                    raise NeedsInput('同じ入力の画像不一致記録がないため再修正できません。')
                            context,images,previous_plans,previous_image_keys=revision_context(root,hooks,data,sid,snap,parent)
                            context['fixed_image_paths']=fixed
                        proposed=await hooks.author(context,[root/p for p in images])
                        if revision:
                            if proposed.get('status')!='revised':
                                raise NeedsInput('不一致が残る画像は具体的な設計修正が必要です。')
                            proposed['cuts']={**previous_plans,**(proposed.get('cuts') or {})}
                        checkpoint={'proposal':proposed,'images':{},'snapshot':snap['digest']}
                        if revision:
                            checkpoint['revision_parent']=revision_path(base,cache_key,revision-1)
                            checkpoint['previous_image_plan_keys']=previous_image_keys
                            checkpoint['image_plan_key_version']=2
                        save_json(root,checkpoint_path,checkpoint)
                    if revision and checkpoint.get('image_plan_key_version')!=2:
                        parent=read_json(root,revision_path(base,cache_key,revision-1),{})
                        if parent.get('snapshot')!=snap['digest']:
                            raise NeedsInput('再修正の元の入力記録が一致しません。')
                        _,_,_,previous_image_keys=revision_context(root,hooks,data,sid,snap,parent)
                        checkpoint['previous_image_plan_keys']=previous_image_keys
                        checkpoint['image_plan_key_version']=2
                        save_json(root,checkpoint_path,checkpoint)
                    proposed=checkpoint['proposal']
                    if proposed.get('status')=='needs_input':raise NeedsInput(str(proposed.get('reason') or '演出の指定が必要です。'))
                    if proposed.get('status') not in ('unchanged','revised'):raise ValueError('invalid author status')
                    old_scene=_scene(data,sid);new_scene=copy.deepcopy(old_scene)
                    plans=proposed.get('cuts') or {}
                    if not isinstance(plans,dict):raise ValueError('cuts must map selectors to shot plans')
                    valid_selectors={str(c.get('selector')) for c in old_scene.get('cuts',[])}
                    if set(plans)-valid_selectors:raise ValueError('author changed another scene')
                    if proposed['status']=='unchanged' and plans:raise ValueError('unchanged proposal contains edits')
                    repairs=[];reuses=[]
                    for i,old in enumerate(old_scene.get('cuts',[])):
                        selector=str(old.get('selector'))
                        if selector not in plans:continue
                        new=hooks.project(data,selector,plans[selector])
                        validate_visual_only(old,new);validate_fixed_images(old,new,fixed)
                        new_scene['cuts'][i]=new;row['changedCuts'].append(selector)
                        old_paths={n.get('output') for _,_,n in image_nodes(old)}
                        for item,kind,node in image_nodes(new):
                            if node.get('output') not in old_paths:
                                prior=next((n for _,_,n in image_nodes(old) if can_reuse(n,node)),None)
                                if prior:reuses.append((prior['output'],node['output']))
                                else:repairs.append((item,kind,node))
                    declared_repairs=proposed.get('image_repairs') or []
                    if not isinstance(declared_repairs,list) or any(not isinstance(x,str) for x in declared_repairs):
                        raise ValueError('image_repairs must contain shot selector:frame strings')
                    actual_repairs={item+':'+kind for item,kind,_ in repairs}
                    row['imageTargets']=sorted(actual_repairs)
                    if revision and image_plan_keys(new_scene)==checkpoint['previous_image_plan_keys']:
                        raise NeedsInput('不一致を修正する画像条件の変更がありません。同じ画像を再判定・再送しません。')
                    if set(declared_repairs)-actual_repairs:
                        raise NeedsInput('画像修正に必要な開始・終了画像の設計差分がありません。静的条件を具体化してください。')
                    # Validate even unchanged plans against adopted audio intervals.
                    hooks.validate(new_scene)
                    extra=hooks.extra_video_cost(old_scene,new_scene) if phase=='video' else 0
                    if repairs or extra is None or extra>0:
                        image_price=hooks.image_cost()
                        cost=None if (repairs and image_price is None) or extra is None else len(repairs)*(image_price or 0)+extra
                        if cost is None or options.get('max_cost_usd') is None:
                            raise NeedsInput('追加生成の費用上限見積または予算が未設定です。')
                        row['estimatedVideoCostUsd']=extra or 0
                        if (extra or 0)+ledger.summary()['reservedCostUsd']>options['max_cost_usd']:
                            raise NeedsInput('予定した動画候補の費用枠が不足しています。')
                    for source,destination in reuses:
                        await hooks.stage_image(source,destination)
                    for item,kind,node in repairs:
                        if preparation_snapshot(root,hooks.load(),sid,phase)['digest']!=snap['digest']:
                            raise NeedsInput('画像生成前に入力が変更されました。最新状態で再開してください。')
                        key=image_request_key(root,item,kind,node)
                        image_receipt=f'{BASE}/images/{key}.json'
                        record=read_json(root,image_receipt) or checkpoint['images'].get(key)
                        if record and record.get('status')=='completed':
                            if hashlib.sha256(asset_bytes(root,record['path'])).hexdigest()!=record['sha256']:
                                raise NeedsInput('保存済み画像候補の内容が変わりました。')
                        elif record:
                            raise NeedsInput('画像生成の送信結果が不明です。再送せず生成履歴を確認してください。')
                        else:
                            ledger.reserve('image-'+key,image_count=1,cost_usd=image_price,
                                max_images=options['max_image_generations'],max_cost_usd=options.get('max_cost_usd'))
                            record={'status':'submitting'};checkpoint['images'][key]=record
                            save_json(root,image_receipt,record)
                            save_json(root,checkpoint_path,checkpoint)
                            path=await hooks.generate_image(item,kind,node,key)
                            record.update(status='completed',path=path,sha256=hashlib.sha256(asset_bytes(root,path)).hexdigest())
                            save_json(root,image_receipt,record)
                            save_json(root,checkpoint_path,checkpoint)
                        await hooks.stage_image(record['path'],node['output'])
                        row['imageCount']+=1;save()
                    prepared_files={p:hashlib.sha256(asset_bytes(root,p)).hexdigest()
                        for c in new_scene['cuts'] for _,_,n in image_nodes(c)
                        for p in [n['output'],*(n.get('references') or [])]}
                    if repairs:
                        if checkpoint.get('review') is None:
                            context['prepared_image_hashes']=prepared_files
                            checkpoint['review']=await hooks.review(new_scene,context)
                            save_json(root,checkpoint_path,checkpoint)
                        if checkpoint['review'].get('status')!='ready':
                            raise NeedsInput(str(checkpoint['review'].get('reason') or '修正画像の追加確認が必要です。'))
                    after=await hooks.publish(sid,snap,new_scene,expected_outputs=prepared_files)
                    save_json(root,f'{base}/ready/{digest(sid)}.json',{'policy':policy,'snapshot':after['digest'],
                        'source_snapshot':snap['digest'],'operation_id':state['operationId'],'draft':checkpoint_path})
                    row.update(status='revised' if row['changedCuts'] else 'unchanged',reason=str(proposed.get('reason') or '準備完了'))
                except NeedsInput as exc:row.update(status='needs_input',reason=str(exc))
                except (ValueError,FileNotFoundError) as exc:row.update(status='needs_input',reason=str(exc))
                save()
            state['status']='needs_input' if any(r['status']=='needs_input' for r in state['scenes']) else 'completed'
        except BaseException as exc:
            state['status']='failed';state['error']='処理が中断されました。保存した履歴から再開してください。' if isinstance(exc,asyncio.CancelledError) else str(exc)
            for row in state['scenes']:
                if row['status']=='running':row.update(status='needs_input',reason=state['error'])
            save()
            getattr(hooks,'record_state',lambda _:None)(state)
            raise
        save()
        getattr(hooks,'record_state',lambda _:None)(state)
        return state
