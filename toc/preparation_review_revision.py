"""Explicit revisions of rejected preparation drafts; original receipts stay intact."""
import copy
import hashlib


def image_request_key(root, item, kind, node):
    from toc import scene_direction_service as s
    return s.digest({'selector':item,'kind':kind,'request':node,
        'references':{p:hashlib.sha256(s.asset_bytes(root,p)).hexdigest() for p in node.get('references') or []}})


def image_plan_keys(scene):
    """Compare planned conditions; dependent reference bytes may not exist yet."""
    from toc import scene_direction_service as s
    def condition(node):
        if node.get('first_frame_visual_plan'):return s.image_signature(node)
        return s.digest({k:v for k,v in node.items() if k not in ('output','candidates','generation','debug_prompt_source')})
    return sorted(s.digest({'selector':item,'kind':kind,'condition':condition(node)})
        for cut in scene['cuts'] for item,kind,node in s.image_nodes(cut))


def revision_path(base, key, revision):
    from toc import scene_direction_service as s
    suffix=key if revision==0 else s.digest({'original':key,'review_revision':revision})
    return f'{base}/drafts/{suffix}.json'


def revision_context(root, hooks, data, sid, snapshot, parent):
    """Reconstruct an unpublished draft and verify every attached image."""
    from toc import scene_direction_service as s
    if (parent.get('review') or {}).get('status')!='needs_input':
        raise s.NeedsInput('再修正の元になる画像確認の不一致記録がありません。')
    previous=parent.get('proposal') or {}
    original=s._scene(data,sid);candidate=copy.deepcopy(original)
    plans=previous.get('cuts') or {}
    valid={str(c.get('selector')) for c in original.get('cuts',[])}
    if set(plans)-valid:raise ValueError('revision parent contains another scene')
    for i,cut in enumerate(original['cuts']):
        selector=str(cut.get('selector'))
        if selector in plans:
            candidate['cuts'][i]=hooks.project(data,selector,plans[selector])
            s.validate_visual_only(cut,candidate['cuts'][i])
    files=dict(snapshot['files']);images=[]
    for old,cut in zip(original['cuts'],candidate['cuts'],strict=True):
        for item,kind,node in s.image_nodes(cut):
            path=node['output'];actual=hashlib.sha256(s.asset_bytes(root,path)).hexdigest()
            expected=snapshot['files'].get(path)
            if expected is None:
                record=s.read_json(root,f'{s.BASE}/images/{image_request_key(root,item,kind,node)}.json',{})
                if record.get('status')=='completed':
                    expected=record['sha256']
                    if hashlib.sha256(s.asset_bytes(root,record['path'])).hexdigest()!=expected:
                        raise s.NeedsInput('保存済み修正候補のbytesが変更されています。')
                else:
                    prior=next((n for _,_,n in s.image_nodes(old) if s.can_reuse(n,node)),None)
                    if prior:expected=snapshot['files'].get(prior['output'])
            if expected is None or actual!=expected:
                raise s.NeedsInput('再修正する画像のrequest/bytesが保存記録と一致しません。')
            for p in [path,*(node.get('references') or [])]:
                raw=s.asset_bytes(root,p)
                from io import BytesIO
                from PIL import Image
                with Image.open(BytesIO(raw)) as im:im.verify()
                files[p]=hashlib.sha256(raw).hexdigest()
                if p not in images:images.append(p)
    projected=copy.deepcopy(data)
    projected['scenes'][projected['scenes'].index(s._scene(projected,sid))]=candidate
    snap={**snapshot,'scene':candidate,'images':images,'files':files}
    context=hooks.context(projected,sid,snap)
    context['repair_feedback']={'reason':parent['review'].get('reason',''),
        'instruction':'実画像に残った指摘箇所だけを直す。正常な画像条件と原作・音声・尺を保持し、検証条件を緩めて通さない。'}
    return context,images,plans,image_plan_keys(candidate)
