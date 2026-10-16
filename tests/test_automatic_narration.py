import asyncio
from unittest.mock import AsyncMock
import pytest
import yaml
from server import image_gen_app as app


@pytest.fixture(autouse=True)
def stub_full_run_author(monkeypatch):
    # These tests isolate TTS orchestration; real p710 is tested separately.
    monkeypatch.setattr(app, '_author_automatic_narration', AsyncMock(return_value={'status': 'reused'}))


def make_run(tmp_path):
    run = tmp_path / 'output' / 'sample'
    run.mkdir(parents=True)
    (run / 'state.txt').write_text('status=P680\nslot.p680.status=done\n')
    cuts = [
        {'cut_id': 1, 'audio': {'narration': {'tool': 'elevenlabs', 'text': '保存済みの語りです。', 'tts_text': 'ほぞんずみの語りです。'}}},
        {'cut_id': 2, 'audio': {'narration': {'tool': 'silent', 'text': '', 'tts_text': '', 'authoring_status': 'silent', 'silence_contract': {'intentional': True}}}},
    ]
    for name in ['script.md', 'video_manifest.md']:
        (run / name).write_text('```yaml\n' + yaml.safe_dump({'scenes': [{'scene_id': 1, 'cuts': cuts}]}, allow_unicode=True) + '```\n')
    return run


def test_create_defaults_to_audio_but_explicit_image_stop_survives():
    assert app.CreateRunRequest(title='sample').stop_target == 'p730'
    assert app.CreateRunRequest(title='sample', stop_target='p680').stop_target == 'p680'
    assert app.ResumeRunRequest(stop_target='p730').stop_target == 'p730'


def test_preparation_uses_script_nested_text_and_preserves_silence(tmp_path, monkeypatch):
    run = make_run(tmp_path)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    app._prepare_automatic_narration_text(run)
    _, _, data = app._read_manifest_data(run)
    spoken, silent = data['scenes'][0]['cuts']
    narration = spoken['audio']['narration']
    assert narration['text'] == '保存済みの語りです。'
    assert narration['tts_text'] == 'ほぞんずみの語りです。'
    assert narration['revision']['number'] > 0
    assert narration['source_binding']['script_selector']
    assert silent['audio']['narration']['tool'] == 'silent'
    assert silent['audio']['narration']['text'] == ''


def test_narration_failure_keeps_image_handoff(tmp_path, monkeypatch):
    run = make_run(tmp_path)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app, '_set_create_job', AsyncMock())
    monkeypatch.setattr(app, '_prepare_automatic_narration_text', lambda _: (_ for _ in ()).throw(ValueError('missing text')))
    with pytest.raises(ValueError, match='missing text'):
        asyncio.run(app._continue_create_narration('job', run_id='sample'))
    state = app.parse_state_file(run / 'state.txt')
    assert state['slot.p680.status'] == 'done'
    assert state['runtime.failure.stage'] == 'p710'
    assert state['runtime.resume.narration.status'] == 'failed'


def test_continuation_generates_once_and_reuses_current_audio(tmp_path, monkeypatch):
    import wave
    run = make_run(tmp_path)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app, '_set_create_job', AsyncMock())
    calls = []
    async def generate(root, req):
        calls.append(req.item_id)
        path = root / req.output
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), 'wb') as out:
            out.setnchannels(1); out.setsampwidth(2); out.setframerate(8000)
            out.writeframes(b'\x01\x00' * 8000)
        return {'itemId': req.item_id, 'status': 'completed', 'path': req.output, 'durationSeconds': 1.0}
    monkeypatch.setattr(app, '_generate_narration_one', generate)
    async def scenario():
        await app._continue_create_narration('job', run_id='sample')
        await app._continue_create_narration('job', run_id='sample')
    asyncio.run(scenario())
    assert calls == ['scene1_cut1']
    _, _, manifest = app._read_manifest_data(run)
    narration = manifest['scenes'][0]['cuts'][0]['audio']['narration']
    app._save_frontend_narration_text(run, app.NarrationTextSaveRequest(
        run_id='sample', item_id='scene1_cut1', text='表示原稿を変更しました。',
        tts_text=narration['tts_text'], expected_revision=narration['revision']['number']))
    assert [item.item_id for item in app._automatic_narration_requests(run)] == ['scene1_cut1']
    state = app.parse_state_file(run / 'state.txt')
    assert state['slot.p730.status'] == 'pending'
    assert state['slot.p680.status'] == 'done'


@pytest.mark.parametrize('stop_target,expected_calls', [('p730', 1), ('p680', 0), ('p650', 0)])
def test_create_runs_images_before_optional_narration(tmp_path, monkeypatch, stop_target, expected_calls):
    make_run(tmp_path)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app, '_run_execution_leases', {})
    monkeypatch.setattr(app, '_acquire_run_execution_lease', AsyncMock())
    monkeypatch.setattr(app, '_release_run_execution_lease', AsyncMock())
    monkeypatch.setattr(app, '_set_create_job', AsyncMock())
    monkeypatch.setattr(app, '_sync_process_current_process', AsyncMock())
    monkeypatch.setattr(app, 'write_app_server_debug_log', lambda **kw: None)
    monkeypatch.setattr(app, '_validate_created_run', lambda _: None)
    monkeypatch.setattr(app, '_validate_p650_run', lambda _: None)
    monkeypatch.setattr(app, '_validate_or_repair_image_outputs', AsyncMock())
    images = AsyncMock()
    audio = AsyncMock()
    monkeypatch.setattr(app, '_run_toc_immersive_frontend_cli_helper', images)
    monkeypatch.setattr(app, '_continue_create_narration', audio)
    asyncio.run(app._run_create_job_bound('job', title='sample', source='source', run_id='sample', stop_target=stop_target))
    assert images.await_args.kwargs['stop_target'] == ('p680' if stop_target == 'p730' else stop_target)
    assert audio.await_count == expected_calls


def test_create_narration_failure_does_not_invalidate_images(tmp_path, monkeypatch):
    run = make_run(tmp_path)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app, '_run_execution_leases', {})
    for name in ['_acquire_run_execution_lease', '_release_run_execution_lease', '_set_create_job', '_sync_process_current_process', '_run_toc_immersive_frontend_cli_helper', '_validate_or_repair_image_outputs']:
        monkeypatch.setattr(app, name, AsyncMock())
    monkeypatch.setattr(app, '_validate_created_run', lambda _: None)
    monkeypatch.setattr(app, 'write_app_server_debug_log', lambda **kw: None)
    monkeypatch.setattr(app, '_cleanup_unscaffolded_run', lambda *a, **kw: None)
    monkeypatch.setattr(app, '_continue_create_narration', AsyncMock(side_effect=RuntimeError('TTS failed')))
    from unittest.mock import Mock
    invalidate = Mock()
    monkeypatch.setattr(app, '_invalidate_published_image_generation_handoff', invalidate)
    asyncio.run(app._run_create_job_bound('job', title='sample', source='source', run_id='sample', stop_target='p730'))
    invalidate.assert_not_called()
    assert app.parse_state_file(run / 'state.txt')['slot.p680.status'] == 'done'


def test_flat_script_silence_is_authoritative(tmp_path, monkeypatch):
    run = make_run(tmp_path)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    script = {'scenes': [{'scene_id': 1, 'cuts': [
        {'cut_id': 1, 'narration': '', 'tts_text': '', 'narration_tool': 'silent', 'narration_authoring': {'status': 'silent'}},
        {'cut_id': 2, 'narration': '', 'tts_text': '', 'narration_tool': 'silent', 'narration_authoring': {'status': 'silent'}},
    ]}]}
    (run / 'script.md').write_text('```yaml\n' + yaml.safe_dump(script) + '```\n')
    app._prepare_automatic_narration_text(run)
    _, _, manifest = app._read_manifest_data(run)
    assert all(c['audio']['narration']['tool'] == 'silent' for c in manifest['scenes'][0]['cuts'])
    assert app._automatic_narration_requests(run) == []


def test_failed_saved_tts_is_still_narration_failure(tmp_path, monkeypatch):
    monkeypatch.setattr('toc.narration_authoring.full_run_narration_current', lambda *args, **kwargs: True)
    from toc.media_resume import MediaJournal
    run = make_run(tmp_path)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app, '_set_create_job', AsyncMock())
    journal = MediaJournal.create(run, 'narration_bulk', {'run_id': 'sample'})
    monkeypatch.setattr(app, '_resume_saved_media_operation', AsyncMock(side_effect=RuntimeError('provider failed again')))
    with pytest.raises(RuntimeError, match='provider failed again'):
        asyncio.run(app._continue_create_narration('job', run_id='sample', operation_id=journal.id))
    state = app.parse_state_file(run / 'state.txt')
    assert state['runtime.failure.stage'] == 'p730'
    assert state['slot.p680.status'] == 'done'
    assert state['last_error'] == 'provider failed again'


def test_resume_draft_journal_continues_to_requested_tts(tmp_path, monkeypatch):
    from toc.media_resume import MediaJournal
    run = make_run(tmp_path)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app.process_store, 'get_process_run', lambda **kw: None)
    monkeypatch.setattr(app, '_create_process_record_best_effort', lambda **kw: None)
    monkeypatch.setattr(app, '_sync_process_current_process', AsyncMock())
    monkeypatch.setattr(app, 'write_app_server_debug_log', lambda **kw: None)
    monkeypatch.setattr(app, '_create_jobs', {})
    monkeypatch.setattr(app, '_resume_tasks', {})
    monkeypatch.setattr(app, '_current_process_number_for_run', lambda _: 710)
    journal = MediaJournal.create(run, 'narration_drafts', {'run_id': 'sample'})
    journal.finish(False)
    continuation = AsyncMock()
    monkeypatch.setattr(app, '_continue_create_narration', continuation)
    async def scenario():
        job = await app.api_resume_run('sample', app.ResumeRunRequest(stop_target='p730'))
        assert job['stopTarget'] == 'p730'
        await app._resume_tasks[job['jobId']]
        continuation.assert_awaited_once_with(job['jobId'], run_id='sample', operation_id=journal.id)
    asyncio.run(scenario())


def test_full_run_authoring_failure_blocks_all_tts(tmp_path, monkeypatch):
    run = make_run(tmp_path)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app, '_set_create_job', AsyncMock())
    author = AsyncMock(side_effect=ValueError('full draft is incomplete'))
    tts = AsyncMock()
    monkeypatch.setattr(app, '_author_automatic_narration', author)
    monkeypatch.setattr(app, '_resume_saved_media_operation', tts)
    with pytest.raises(ValueError, match='full draft is incomplete'):
        asyncio.run(app._continue_create_narration('job', run_id='sample'))
    author.assert_awaited_once()
    tts.assert_not_awaited()
    assert app.parse_state_file(run/'state.txt')['runtime.failure.stage'] == 'p710'


def test_saved_tts_cannot_bypass_missing_full_draft(tmp_path, monkeypatch):
    from toc.media_resume import MediaJournal
    run = make_run(tmp_path)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app, '_set_create_job', AsyncMock())
    tts = AsyncMock()
    monkeypatch.setattr(app, '_resume_saved_media_operation', tts)
    journal = MediaJournal.create(run, 'narration_bulk', {'run_id':'sample'})
    with pytest.raises(ValueError, match='full-run authorship'):
        asyncio.run(app._continue_create_narration('job', run_id='sample', operation_id=journal.id))
    tts.assert_not_awaited()


def test_completed_run_can_explicitly_rewrite_narration_without_images(tmp_path,monkeypatch):
    run=make_run(tmp_path)
    (run/'state.txt').write_text('status=P730\nslot.p710.status=done\nslot.p730.status=done\nruntime.target_video_seconds=600\n')
    monkeypatch.setattr(app,'ROOT',tmp_path)
    monkeypatch.setattr(app.process_store,'get_process_run',lambda **kw:None)
    monkeypatch.setattr(app,'_create_process_record_best_effort',lambda **kw:None)
    monkeypatch.setattr(app,'_sync_process_current_process',AsyncMock())
    monkeypatch.setattr(app,'write_app_server_debug_log',lambda **kw:None)
    monkeypatch.setattr(app,'_create_jobs',{})
    monkeypatch.setattr(app,'_resume_tasks',{})
    monkeypatch.setattr(app,'_current_process_number_for_run',lambda _:730)
    monkeypatch.setattr(app,'_validate_current_p680_run',lambda *a,**kw:None)
    continuation=AsyncMock()
    images=AsyncMock(side_effect=AssertionError('images must not regenerate'))
    monkeypatch.setattr(app,'_continue_create_narration',continuation)
    monkeypatch.setattr(app,'_run_p500_resume_subprocess',images)
    async def scenario():
        job=await app.api_resume_run('sample',app.ResumeRunRequest(stop_target='p730',rewrite_narration=True))
        assert job['rewriteNarration'] is True and job['resumeMode']=='narration_start'
        await app._resume_tasks[job['jobId']]
        continuation.assert_awaited_once_with(job['jobId'],run_id='sample',operation_id=None,rewrite_narration=True)
    asyncio.run(scenario())
    images.assert_not_awaited()


def test_failed_rewrite_retry_does_not_pick_obsolete_tts_journal(tmp_path,monkeypatch):
    from toc.media_resume import MediaJournal
    run=make_run(tmp_path)
    (run/'state.txt').write_text('status=P730\nslot.p710.status=done\nruntime.target_video_seconds=600\n')
    monkeypatch.setattr(app,'ROOT',tmp_path)
    monkeypatch.setattr(app.process_store,'get_process_run',lambda **kw:None)
    monkeypatch.setattr(app,'_create_process_record_best_effort',lambda **kw:None)
    monkeypatch.setattr(app,'_sync_process_current_process',AsyncMock())
    monkeypatch.setattr(app,'write_app_server_debug_log',lambda **kw:None)
    monkeypatch.setattr(app,'_create_jobs',{})
    monkeypatch.setattr(app,'_resume_tasks',{})
    monkeypatch.setattr(app,'_current_process_number_for_run',lambda _:710)
    monkeypatch.setattr(app,'_validate_current_p680_run',lambda *a,**kw:None)
    old=MediaJournal.create(run,'narration_bulk',{'run_id':'sample','items':[{'item_id':'scene1_cut1'}]})
    old.finish(False)
    other=MediaJournal.create(run,'narration',{'run_id':'sample','item_id':'scene1_cut2'})
    other.finish(False)
    calls=[]
    async def continuation(job_id,**kwargs):
        calls.append(kwargs)
        if len(calls)==1:
            app.append_state_snapshot(run/'state.txt',{'status':'FAILED','runtime.resume.narration.status':'failed','slot.p710.status':'failed'})
            raise RuntimeError('author interrupted')
    monkeypatch.setattr(app,'_continue_create_narration',continuation)
    async def scenario():
        job=await app.api_resume_run('sample',app.ResumeRunRequest(stop_target='p730',rewrite_narration=True))
        await app._resume_tasks[job['jobId']]
        assert MediaJournal.load(run,old.id).data['status']=='superseded'
        assert MediaJournal.load(run,other.id).data['status']=='superseded'
        assert MediaJournal.latest_incomplete(run) is None
        next_job=await app.api_resume_run('sample',app.ResumeRunRequest(stop_target='p730'))
        await app._resume_tasks[next_job['jobId']]
    asyncio.run(scenario())
    assert len(calls)==2 and calls[1]['operation_id'] is None
    assert calls[0]['rewrite_narration'] is True
