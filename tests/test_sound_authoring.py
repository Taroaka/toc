import copy
import pytest
from toc import sound_design as sound


def context():
    return {'video_set_hash':'sha256:test','duration_seconds':12,'videos':[{'item_id':'scene1_cut1','start_seconds':0,'duration_seconds':12,'context':'動作','path':'assets/clip.mp4','sha256':'sha256:clip'}]}


def cue(kind='se', start=1):
    return {'kind':kind,'label':'布の音','source_selector':'scene1_cut1','purpose':'接触を伝える','perspective':'劇中音','timing_reason':'手を動かす瞬間','prompt':'柔らかな布の単発音、音楽と声なし','generation_duration_seconds':3,'start_seconds':start,'duration_seconds':3,'volume_db':-18,'fade_in_seconds':0,'fade_out_seconds':.1,'loop':False}


def test_approval_does_not_invent_a_soundtrack():
    assert sound.approve(context(), actor='test')['cues']==[]


def test_multiple_cues_same_target_keep_selected_assets_and_mix():
    from toc.sound_authoring import CueDraft, add_cue, apply_design, SoundDesignDraft
    p=sound.approve(context(),actor='test')
    a=add_cue(p,context(),CueDraft.model_validate(cue()))
    a.update(selected_candidate_id='selected',enabled=True,candidates=[{'id':'selected','path':'assets/keep.mp3'}])
    p['mix']['bgm']['volume_db']=-3
    before=copy.deepcopy(p)
    proposal=SoundDesignDraft.model_validate({'intent':'静けさから安堵へ','silence_regions':[], 'cues':[cue(start=4),cue('bgm',0),cue('bgm',8)]})
    apply_design(p,context(),proposal,design_id='test')
    assert p['cues'][0]==before['cues'][0] and p['mix']==before['mix']
    assert len(p['cues'])==4 and len({x['id'] for x in p['cues']})==4
    assert all(not x['enabled'] and not x['candidates'] for x in p['cues'][1:])


@pytest.mark.parametrize('changes',[{'source_selector':'scene9_cut8'},{'start_seconds':11},{'duration_seconds':float('nan')},{'generation_duration_seconds':40},{'enabled':True},{'path':'/tmp/fake.mp3'}])
def test_author_payload_is_validated_before_plan_mutation(changes):
    from toc.sound_authoring import CueDraft, add_cue
    p=sound.approve(context(),actor='test');before=copy.deepcopy(p)
    with pytest.raises(ValueError):add_cue(p,context(),CueDraft.model_validate({**cue(),**changes}))
    assert p==before


def test_delete_archives_media_and_does_not_reset_mixer():
    from toc.sound_authoring import CueDraft,add_cue,archive_cue
    p=sound.approve(context(),actor='test');c=add_cue(p,context(),CueDraft.model_validate(cue()))
    c['candidates']=[{'id':'saved','path':'assets/sound/saved.mp3'}];mix=copy.deepcopy(p['mix'])
    archive_cue(p,c['id'])
    assert not p['cues'] and p['archived_cues'][0]['candidates']==c['candidates'] and p['mix']==mix


def test_runtime_uses_structured_read_only_author_transport(monkeypatch,tmp_path):
    import asyncio,json
    from types import SimpleNamespace
    from toc import sound_authoring as author
    import toc.story_author_runtime as runtime
    async def fake(**kwargs):
        assert kwargs['model']==runtime.DEFAULT_STORY_AUTHOR_MODEL
        assert kwargs['output_schema']==runtime.STORY_AUTHOR_TRANSPORT_SCHEMA
        assert kwargs['cwd']==tmp_path
        return SimpleNamespace(payload={'result_json':json.dumps({'intent':'余韻','silence_regions':[],'cues':[]})},provenance=SimpleNamespace(as_dict=lambda:{'sandbox':'read-only'}))
    monkeypatch.setattr(runtime,'run_structured_story_turn',fake)
    payload,provenance=asyncio.run(author.author('structured prompt',tmp_path))
    assert payload['cues']==[] and provenance['sandbox']=='read-only'


@pytest.mark.parametrize('story',['山で再会する物語','砂漠で別れる物語'])
def test_prompt_reads_different_stories_through_same_contract(story):
    from toc.sound_authoring import build_prompt
    p=build_prompt({'documents':{'policy':'音の視点を決める'},'sources':{'story.md':story,'script.md':'scenes: []'}},context(),{'cues':[]},'静けさを大切に')
    assert story in p and '静けさを大切に' in p and 'TRANSPORT CONTRACT' in p
