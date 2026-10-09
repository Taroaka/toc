import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from server import image_gen_app as api
from server import sound_design_api
from server.app import app
from toc import sound_design as sound


@pytest.fixture
def setup_run(tmp_path, monkeypatch):
    root = tmp_path / "output" / "sound_test"
    (root / "assets/videos").mkdir(parents=True)
    (root / "assets/audio").mkdir()
    (root / "assets/videos/clip.mp4").write_bytes(b"video")
    (root / "assets/audio/narration.mp3").write_bytes(b"narration")
    (root / "state.txt").write_text("slot.p840.status=done\n")
    manifest = {"scenes": [{"scene_id": 1, "cuts": [{"cut_id": 1,
        "video_generation": {"output": "assets/videos/clip.mp4", "duration_seconds": 4, "prompt": "扉が開く"},
        "render": {"video_duration_seconds": 4, "narration_offset_seconds": 0},
        "audio": {"narration": {"output": "assets/audio/narration.mp3", "text": "扉が開いた", "tool": "elevenlabs"}}}]}]}
    (root / "video_manifest.md").write_text("```yaml\n" + yaml.safe_dump(manifest, allow_unicode=True) + "```\n")
    monkeypatch.setattr(api, "ROOT", tmp_path)
    monkeypatch.setenv("TOC_SERVER_AUTH_DISABLED", "1")
    monkeypatch.setattr(api, "_probe_media_duration_seconds", lambda path: 4.0)
    monkeypatch.setattr(sound, "probe_audio", lambda path: 4.0)
    monkeypatch.setattr(sound, "generate_audio", lambda request: b"generated sound")
    monkeypatch.setattr(api, "_prepare_render_video_clip", lambda root, source, item, **kwargs: source)
    monkeypatch.setattr(api, "_prepare_render_narration", lambda root, source, item, **kwargs: source)
    with TestClient(app) as client:
        yield root, client


def status(root, client):
    response = client.get("/api/image-gen/sound-design", params={"run_id": root.name})
    assert response.status_code == 200, response.text
    return response.json()


def post(root, client, action, state, **extra):
    return client.post("/api/image-gen/sound-design/" + action, json={"run_id": root.name,
        "video_set_hash": state["context"]["video_set_hash"], "revision": (state["plan"] or {}).get("revision", 0), **extra})


def approve(root, client):
    response = post(root, client, "approve-video", status(root, client))
    assert response.status_code == 200, response.text
    state = response.json()
    if not state['plan']['cues']:
        plan = seeded_plan(state['context'], actor='test-fixture')
        plan['revision'] = state['plan']['revision']
        sound.save(root, plan)
    return status(root, client)


def test_full_approval_generation_selection_freeze(setup_run):
    root, client = setup_run
    initial = status(root, client)
    assert not initial["approved"]
    assert post(root, client, "generate", initial, item_id="bgm_main").status_code == 409
    request = api.RenderFreezeRequest(run_id=root.name, items=[api.RenderInputItem(item_id="scene1_cut1", video_duration_seconds=4)])
    with pytest.raises(ValueError, match="承認"):
        api._freeze_render_inputs(root, request)
    state = approve(root, client)
    generated = post(root, client, "generate", state, item_id="bgm_main")
    assert generated.status_code == 200, generated.text
    assert generated.json()["status"] == "completed", generated.text
    state = status(root, client)
    cue = state["plan"]["cues"][0]
    assert not cue["enabled"]
    saved = post(root, client, "cue", state, item_id=cue["id"], settings={**cue,
        "selected_candidate_id": cue["candidates"][0]["id"], "enabled": True})
    assert saved.status_code == 200, saved.text
    completed = post(root, client, "complete", saved.json())
    assert completed.status_code == 200, completed.text
    assert completed.json()["ready"]
    frozen = api._freeze_render_inputs(root, request)
    snapshot = json.loads((root / frozen["soundPlan"]).read_text())
    assert len(snapshot["tracks"]) == 1
    assert snapshot["sound_hash"] == frozen["soundHash"]
    assert sound_design_api.freeze(root, api._read_manifest_data(root)[2])["sound_hash"] == frozen["soundHash"]


def test_changed_video_bytes_require_new_approval_and_archive_old_plan(setup_run):
    root, client = setup_run
    state = approve(root, client)
    completed = post(root, client, "complete", state, without_sound=True).json()
    (root / "assets/videos/clip.mp4").write_bytes(b"regenerated")
    assert not status(root, client)["ready"]
    assert post(root, client, "generate", completed, item_id="bgm_main").status_code == 409
    approved = approve(root, client)
    assert approved["approved"] and not approved["ready"]
    assert list((root / "logs/sound_design").glob("previous_*.json"))


def test_generation_failure_is_visible_retry_preserves_history(setup_run, monkeypatch):
    root, client = setup_run
    state = approve(root, client)
    with monkeypatch.context() as patcher:
        patcher.setattr(sound, "generate_audio", lambda request: (_ for _ in ()).throw(RuntimeError("provider unavailable")))
        failed = post(root, client, "generate", state, item_id="se_001")
    assert failed.status_code == 200, failed.text
    assert failed.json()["status"] == "failed"
    retried = post(root, client, "generate", status(root, client), item_id="se_001")
    assert retried.status_code == 200, retried.text
    candidates = status(root, client)["plan"]["cues"][1]["candidates"]
    assert [candidate["status"] for candidate in candidates] == ["failed", "completed"]


def test_completion_and_old_browser_revision_rejected(setup_run):
    root, client = setup_run
    state = approve(root, client)
    assert post(root, client, "complete", state).status_code == 409
    cue = state["plan"]["cues"][0]
    assert post(root, client, "cue", state, item_id=cue["id"], settings={**cue, "volume_db": -25}).status_code == 200
    assert post(root, client, "complete", state, without_sound=True).status_code == 409


def test_render_cannot_override_approved_clip_or_duration(setup_run):
    root, client = setup_run
    state = approve(root, client)
    assert post(root, client, "complete", state, without_sound=True).status_code == 200
    (root / "assets/videos/other.mp4").write_bytes(b"other")
    req = api.RenderFreezeRequest(run_id=root.name, items=[api.RenderInputItem(item_id="scene1_cut1",
        video_path="assets/videos/other.mp4", video_duration_seconds=4)])
    with pytest.raises(ValueError, match="動画承認"):
        api._freeze_render_inputs(root, req)


def test_missing_video_has_no_approval_action(setup_run):
    root, client = setup_run
    (root / "assets/videos/clip.mp4").unlink()
    state = status(root, client)
    assert not state["approved"] and not state["context"]["videos"]


def test_current_candidate_wins_over_previous_render_path(setup_run, monkeypatch):
    root, client = setup_run
    path, text, data = api._read_manifest_data(root)
    data["scenes"][0]["cuts"][0]["render"]["video_path"] = "assets/videos/clip.mp4"
    api._write_manifest_data(path, text, data)
    (root / "assets/videos/new.mp4").write_bytes(b"new candidate")
    monkeypatch.setattr(api, "_candidate_video_output_for_item", lambda *args, **kwargs: "assets/videos/new.mp4")
    state = status(root, client)
    assert state["context"]["videos"][0]["path"] == "assets/videos/new.mp4"


def test_requested_native_audio_requires_and_binds_an_audio_stream(setup_run, monkeypatch):
    root, _client = setup_run
    path, text, data = api._read_manifest_data(root)
    data["scenes"][0]["cuts"][0]["video_generation"]["native_audio"] = {
        "mode": "natural_sound", "sound_events": [], "dialogue": []}
    api._write_manifest_data(path, text, data)
    monkeypatch.setattr(sound, "probe_audio_stream", lambda _path: {"index": 1, "identity": "sha256:audio-stream",
        "relative_audio_start_seconds": 0.5, "timing_identity": "sha256:audio-timing"})
    monkeypatch.setattr(sound_design_api.subprocess, "run", lambda *args, **kwargs: type("Result", (), {"returncode": 0})())
    context = sound_design_api.video_context(root)
    video = context["videos"][0]
    assert video["native_audio_mode"] == "natural_sound"
    assert video["audio_stream"]["index"] == 1
    assert video["audio_stream"]["relative_audio_start_seconds"] == 0.5
    assert video["candidate_revision"] is None
    monkeypatch.setattr(sound, "probe_audio_stream", lambda _path: None)
    with pytest.raises(ValueError, match="音声ストリームがありません"):
        sound_design_api.video_context(root)


def test_sound_api_uses_existing_authentication(setup_run, monkeypatch):
    root, client = setup_run
    monkeypatch.delenv("TOC_SERVER_AUTH_DISABLED")
    monkeypatch.setenv("TOC_SERVER_TOKEN", "test-only-token")
    assert client.get("/api/image-gen/sound-design", params={"run_id": root.name}).status_code == 401
    assert client.post("/api/image-gen/sound-design/complete", json={}).status_code == 401


def test_final_render_passes_frozen_sound_and_rejects_changed_video(setup_run, monkeypatch):
    root, client = setup_run
    state = approve(root, client)
    assert post(root, client, "complete", state, without_sound=True).status_code == 200
    observed = []

    async def fake_renderer(command, **kwargs):
        observed.extend(command)
        (root / "video.mp4").write_bytes(b"rendered")
        (root / "assets/videos/clip.mp4").write_bytes(b"changed during render")
        return b"", b""

    monkeypatch.setattr(api, "_run_resume_subprocess_command", fake_renderer)
    monkeypatch.setattr(api, "_require_frozen_render_narration_current", lambda *args: None)
    response = client.post("/api/image-gen/final-render", json={"run_id": root.name,
        "items": [{"item_id": "scene1_cut1", "video_duration_seconds": 4}], "output": "video.mp4"})
    assert response.status_code == 409, response.text
    assert "--sound-plan" in observed
    assert "slot.p920.status=blocked" in (root / "state.txt").read_text()


def test_saved_sound_operation_can_retry_without_regenerating_successful_candidates(setup_run, monkeypatch):
    root, client = setup_run
    state = approve(root, client)
    calls = []
    monkeypatch.setattr(sound, "generate_audio", lambda request: calls.append(request) or b"audio")
    generated = post(root, client, "generate", state, item_id="bgm_main")
    operation_id = generated.json()["operationId"]
    assert generated.status_code == 200, generated.text
    import asyncio
    from toc.run_root_binding import bind_run_root
    stat = root.stat()
    with bind_run_root(root, expected_identity=(stat.st_dev, stat.st_ino)):
        resumed = asyncio.run(api._resume_saved_media_operation(root, operation_id))
    assert resumed["status"] == "completed"
    assert len(calls) == 1


def test_mixer_save_persists_and_invalidates_old_revision(setup_run):
    root, client = setup_run
    state = post(root, client, 'complete', approve(root, client), without_sound=True).json()
    old = sound_design_api.freeze(root, api._read_manifest_data(root)[2])
    response = post(root, client, 'mix', state, settings={'narration': {'volume_db': -6}, 'se': {'volume_db': 24}, 'bgm': {'muted': True}})
    assert response.status_code == 200, response.text
    assert response.json()['ready']
    saved = status(root, client)
    assert saved['plan']['mix']['se']['volume_db'] == 24
    new = sound_design_api.freeze(root, api._read_manifest_data(root)[2])
    assert new['sound_hash'] != old['sound_hash']
    assert new['mix'] == saved['plan']['mix']
    assert post(root, client, 'mix', state, settings={}).status_code == 409
    assert post(root, client, 'mix', saved, settings={'se': {'volume_db': 100}}).status_code == 422


def test_mix_preview_is_ephemeral_and_rejects_stale_source(setup_run, monkeypatch):
    root, client = setup_run
    state = post(root, client, 'complete', approve(root, client), without_sound=True).json()
    original = (root / 'sound_design.json').read_bytes()
    manifest = (root / 'video_manifest.md').read_bytes()
    observed = []
    def fake_preview(root, plan, context, data, directory):
        observed.append(plan['mix'])
        output = directory / 'preview.mp4'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b'preview')
        return output
    monkeypatch.setattr(sound_design_api, 'build_mix_preview', fake_preview)
    result = post(root, client, 'mix-preview', state, settings={'narration': {'muted': True}, 'se': {'volume_db': 12}})
    assert result.status_code == 200, result.text
    assert result.json()['settings']['narration']['muted']
    assert observed[0]['se']['volume_db'] == 12
    assert (root / result.json()['path']).is_file()
    assert (root / 'sound_design.json').read_bytes() == original
    assert (root / 'video_manifest.md').read_bytes() == manifest
    def changed_preview(*args):
        output = fake_preview(*args)
        (root / 'assets/videos/clip.mp4').write_bytes(b'changed')
        return output
    monkeypatch.setattr(sound_design_api, 'build_mix_preview', changed_preview)
    assert post(root, client, 'mix-preview', state, settings={}).status_code == 409


def test_real_mix_preview_mutes_narration_without_modifying_inputs(setup_run):
    import shutil
    import subprocess
    if not shutil.which('ffmpeg'):
        pytest.skip('ffmpeg required')
    root, client = setup_run
    def media(*args):
        subprocess.run(['ffmpeg', '-v', 'error', '-y', *map(str, args)], check=True, capture_output=True)
    video = root / 'assets/videos/clip.mp4'
    narration = root / 'assets/audio/narration.mp3'
    media('-f', 'lavfi', '-i', 'color=c=blue:s=160x90:r=24:d=4', '-c:v', 'libx264', video)
    media('-f', 'lavfi', '-i', 'sine=frequency=440:duration=4', narration)
    hashes = [sound.file_hash(video), sound.file_hash(narration)]
    state = post(root, client, 'complete', approve(root, client), without_sound=True).json()
    response = post(root, client, 'mix-preview', state, settings={'narration': {'muted': True}})
    assert response.status_code == 200, response.text
    preview = root / response.json()['path']
    assert preview.is_file()
    import array
    pcm = array.array('f', subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(preview), '-f', 'f32le', '-ac', '1', '-']))
    assert max(abs(value) for value in pcm) < 0.001
    assert [sound.file_hash(video), sound.file_hash(narration)] == hashes
    assert {p.name for p in preview.parent.iterdir() if not p.name.startswith('.')} == {'preview.mp4', 'sound_snapshot.json'}


def seeded_plan(context, actor='test'):
    """Explicit fixture for pre-existing plans; approval itself now creates no cues."""
    plan = sound.approve(context, actor=actor)
    duration = context['duration_seconds']
    for kind, cue_id, selector, length in [('bgm', 'bgm_main', 'full_run', min(60, max(3,duration))), ('se','se_001',context['videos'][0]['item_id'],min(5,duration))]:
        plan['cues'].append({'id':cue_id,'kind':kind,'label':cue_id,'source_selector':selector,
            'prompt':'木の扉がゆっくり開く' if kind=='se' else '静かな楽器曲',
            'generation_duration_seconds':length,'start_seconds':0,'duration_seconds':duration if kind=='bgm' else length,
            'volume_db':-20 if kind=='bgm' else -12,'fade_in_seconds':0,'fade_out_seconds':0,'loop':kind=='bgm',
            'enabled':False,'selected_candidate_id':None,'candidates':[]})
    return plan


def design_cue(kind='se', start=0):
    return {'kind':kind,'label':'音の案','source_selector':'scene1_cut1','purpose':'動作を伝える','perspective':'劇中音','timing_reason':'扉が動く時','prompt':'扉のきしみ、声と音楽なし','generation_duration_seconds':3,'start_seconds':start,'duration_seconds':1,'volume_db':-12,'fade_in_seconds':0,'fade_out_seconds':0,'loop':False}


def author_sources(root):
    (root/'story.md').write_text('物語の結末と出来事')
    (root/'script.md').write_text('scenes: []')


def test_new_approval_empty_and_manual_multiple_cues(setup_run):
    root, client = setup_run
    state=post(root,client,'approve-video',status(root,client)).json()
    assert state['plan']['cues']==[]
    for kind in ['se','se','bgm','bgm']:
        result=post(root,client,'cue-create',state,cue=design_cue(kind))
        assert result.status_code==200,result.text
        state=result.json()
    assert len(state['plan']['cues'])==4
    item=state['plan']['cues'][0]
    deleted=post(root,client,'cue-delete',state,item_id=item['id'])
    assert deleted.status_code==200
    assert len(deleted.json()['plan']['cues'])==3
    assert deleted.json()['plan']['archived_cues'][0]['id']==item['id']
    assert post(root,client,'cue-delete',state,item_id=item['id']).status_code==409


def test_author_reads_docs_and_preserves_existing_plan(setup_run, monkeypatch):
    root,client=setup_run;state=approve(root,client);author_sources(root)
    from toc import sound_authoring
    repo=Path(__file__).resolve().parents[1]
    original=sound_authoring.source_snapshot
    monkeypatch.setattr(sound_authoring,'source_snapshot',lambda run,_repo:original(run,repo))
    async def fake(prompt, run):
        assert '音の視点' in prompt and '物語の結末と出来事' in prompt
        assert 'start_seconds' in prompt and 'TRANSPORT CONTRACT' in prompt
        return {'intent':'静けさを大切に','silence_regions':[],'cues':[design_cue(),design_cue(start=2)]},{'model':'fake'}
    monkeypatch.setattr(sound_authoring,'author',fake)
    before=state['plan']['cues']
    result=post(root,client,'design',state,instructions='声を優先する')
    assert result.status_code==200,result.text
    assert result.json()['plan']['cues'][:2]==before
    assert len(result.json()['plan']['cues'])==4
    assert result.json()['plan']['designs'][0]['source_hashes']
    assert all(not c['enabled'] for c in result.json()['plan']['cues'][2:])


@pytest.mark.parametrize('change',['source','revision','invalid','failure'])
def test_author_failure_or_input_change_never_overwrites_plan(setup_run,monkeypatch,change):
    root,client=setup_run;state=approve(root,client);author_sources(root)
    from toc import sound_authoring
    repo=Path(__file__).resolve().parents[1];original=sound_authoring.source_snapshot
    monkeypatch.setattr(sound_authoring,'source_snapshot',lambda run,_repo:original(run,repo))
    before=sound.load(root)
    async def fake(prompt,run):
        if change=='source':(root/'story.md').write_text('変更された物語')
        if change=='revision':
            current=sound.load(root);current['mix']['bgm']['volume_db']=-5;sound.save(root,current)
        if change=='failure':raise RuntimeError('transport unavailable')
        c=design_cue();c['source_selector']='missing' if change=='invalid' else 'scene1_cut1'
        return {'intent':'案','silence_regions':[],'cues':[c]},{}
    monkeypatch.setattr(sound_authoring,'author',fake)
    result=post(root,client,'design',state)
    assert result.status_code in (409,502)
    current=sound.load(root)
    assert current['cues']==before['cues'] and not current.get('designs')
    if change=='revision':assert current['mix']['bgm']['volume_db']==-5


def test_delete_during_sound_generation_keeps_result_archived(setup_run,monkeypatch):
    root,client=setup_run;state=approve(root,client)
    from toc.sound_authoring import archive_cue
    def generate(_request):
        p=sound.load(root);archive_cue(p,'se_001');sound.save(root,p)
        return b'generated'
    monkeypatch.setattr(sound,'generate_audio',generate)
    result=post(root,client,'generate',state,item_id='se_001')
    assert result.status_code==200 and result.json()['status']=='stale'
    p=sound.load(root);assert all(c['id']!='se_001' for c in p['cues'])
    assert p['archived_cues'][0]['candidates'][-1]['status']=='stale'
