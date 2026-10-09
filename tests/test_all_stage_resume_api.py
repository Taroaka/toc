import asyncio
import hashlib
import json
from unittest.mock import AsyncMock
import pytest

from server import image_gen_app as app
from toc.media_resume import MediaJournal


def make_run(tmp_path):
    run = tmp_path / 'output' / 'sample'; (run / 'logs/orchestration').mkdir(parents=True)
    (run / 'state.txt').write_text('runtime.target_video_seconds=300\n---\n')
    (run / 'logs/orchestration/create_input.json').write_text(json.dumps({
        'schema_version': 'toc.create_input.v1', 'topic': '物語', 'source': '原文',
        'source_sha256': hashlib.sha256('原文'.encode()).hexdigest(), 'source_run': None,
        'experience': 'cinematic_story', 'target_duration_seconds': 300}))
    return run


def setup_api(monkeypatch, tmp_path):
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app.process_store, 'get_process_run', lambda **kwargs: None)
    monkeypatch.setattr(app, '_create_process_record_best_effort', lambda **kwargs: None)
    monkeypatch.setattr(app, '_sync_process_current_process', AsyncMock())
    monkeypatch.setattr(app, 'write_app_server_debug_log', lambda **kwargs: None)
    monkeypatch.setattr(app, '_create_jobs', {})
    monkeypatch.setattr(app, '_resume_tasks', {})
    monkeypatch.setattr(app, '_current_process_number_for_run', lambda _: 120)


def test_api_resumes_first_stage_then_existing_image_pipeline(tmp_path, monkeypatch):
    run = make_run(tmp_path); setup_api(monkeypatch, tmp_path)
    checks = iter([RuntimeError('not p680'), None])
    def validate(*args, **kwargs):
        value = next(checks)
        if value: raise value
    monkeypatch.setattr(app, '_validate_current_p680_run', validate)
    monkeypatch.setattr(app, '_validate_p650_run', lambda _: (_ for _ in ()).throw(RuntimeError('not ready')))
    author = AsyncMock()
    images = AsyncMock(return_value={'checkpointId': 'checkpoint', 'planToken': 'token'})
    monkeypatch.setattr(app, '_run_authoring_resume_subprocess', author)
    monkeypatch.setattr(app, '_run_p500_resume_subprocess', images)
    async def scenario():
        job = await app.api_resume_run('sample', app.ResumeRunRequest())
        assert job['resumeMode'] == 'authoring_subprocess'
        await app._resume_tasks[job['jobId']]
        assert app._create_jobs[job['jobId']]['status'] == 'completed'
        assert job['jobId'] not in app._run_execution_leases
    asyncio.run(scenario())
    author.assert_awaited_once()
    images.assert_awaited_once()
    assert author.await_args.kwargs['run_dir'] == run


@pytest.mark.parametrize("kind, stop_target", [("render", "p920"), ("sound", "p860")])
def test_api_routes_saved_media_without_restarting_images(tmp_path, monkeypatch, kind, stop_target):
    run = make_run(tmp_path); setup_api(monkeypatch, tmp_path)
    operation = MediaJournal.create(run, kind, {'run_id': 'sample'})
    operation.finish(False)
    media = AsyncMock(return_value={'status': 'rendered'})
    images = AsyncMock(side_effect=AssertionError('images must be preserved'))
    monkeypatch.setattr(app, '_resume_saved_media_operation', media)
    monkeypatch.setattr(app, '_run_p500_resume_subprocess', images)
    async def scenario():
        job = await app.api_resume_run('sample', app.ResumeRunRequest())
        assert job['resumeMode'] == 'media_operation'
        assert job['stopTarget'] == stop_target
        await app._resume_tasks[job['jobId']]
        assert app._create_jobs[job['jobId']]['status'] == 'completed'
    asyncio.run(scenario())
    media.assert_awaited_once_with(run, operation.id)
    images.assert_not_awaited()


def test_missing_or_corrupt_operation_is_a_client_error_and_releases_lease(tmp_path, monkeypatch):
    import pytest
    run = make_run(tmp_path); setup_api(monkeypatch, tmp_path)
    op_id = 'a' * 32
    async def missing():
        with pytest.raises(app.HTTPException) as error:
            await app.api_resume_run('sample', app.ResumeRunRequest(operation_id=op_id))
        assert error.value.status_code == 404
        assert not app._run_execution_leases
    asyncio.run(missing())
    (run / 'logs/media_operations').mkdir()
    (run / 'logs/media_operations' / (op_id + '.json')).write_text('{')
    async def corrupt():
        with pytest.raises(app.HTTPException) as error:
            await app.api_resume_run('sample', app.ResumeRunRequest(operation_id=op_id))
        assert error.value.status_code == 409
        assert not app._run_execution_leases
    asyncio.run(corrupt())


def test_saved_input_recovers_duration_when_partial_manifest_is_invalid(tmp_path):
    run = make_run(tmp_path)
    (run / 'video_manifest.md').write_text('broken yaml: [')
    (run / 'state.txt').write_text('')
    assert app._target_duration_seconds_for_run(run) == 300


def test_waiting_p710_starts_durable_narration_without_rebuilding_images(tmp_path, monkeypatch):
    run = make_run(tmp_path); setup_api(monkeypatch, tmp_path)
    from toc.harness import append_state_snapshot
    append_state_snapshot(run / 'state.txt', {'status': 'P680', 'runtime.stage': 'scene_images_generated', 'slot.p710.status': 'pending'})
    monkeypatch.setattr(app, '_validate_current_p680_run', lambda *a, **k: None)
    images = AsyncMock(side_effect=AssertionError('must not rebuild images'))
    media = AsyncMock(return_value={'status': 'completed'})
    monkeypatch.setattr(app, '_run_p500_resume_subprocess', images)
    monkeypatch.setattr(app, '_resume_saved_media_operation', media)
    async def scenario():
        job = await app.api_resume_run('sample', app.ResumeRunRequest(continue_waiting=True))
        assert job['resumeMode'] == 'narration_start'
        assert job['stopTarget'] == 'p710'
        await app._resume_tasks[job['jobId']]
        completed = app._create_jobs[job['jobId']]
        assert completed['status'] == 'completed'
        journal = MediaJournal.load(run, completed['mediaOperationId'])
        assert journal.data['kind'] == 'narration_drafts'
        assert journal.request['replace'] is False
        media.assert_awaited_once_with(run, journal.id)
        assert job['jobId'] not in app._run_execution_leases
    asyncio.run(scenario())
    images.assert_not_awaited()


def test_completed_images_need_explicit_waiting_opt_in(tmp_path, monkeypatch):
    import pytest
    run = make_run(tmp_path); setup_api(monkeypatch, tmp_path)
    monkeypatch.setattr(app, '_validate_current_p680_run', lambda *a, **k: None)
    async def scenario():
        with pytest.raises(app.HTTPException) as error:
            await app.api_resume_run('sample', app.ResumeRunRequest())
        assert error.value.status_code == 409
        assert not app._run_execution_leases
    asyncio.run(scenario())


def test_completed_narration_preparation_does_not_restart(tmp_path, monkeypatch):
    import pytest
    from toc.harness import append_state_snapshot
    run = make_run(tmp_path); setup_api(monkeypatch, tmp_path)
    append_state_snapshot(run / 'state.txt', {'status': 'P720', 'slot.p710.status': 'done'})
    monkeypatch.setattr(app, '_validate_current_p680_run', lambda *a, **k: None)
    async def scenario():
        with pytest.raises(app.HTTPException) as error:
            await app.api_resume_run('sample', app.ResumeRunRequest(continue_waiting=True))
        assert error.value.status_code == 409
        assert not app._run_execution_leases
    asyncio.run(scenario())


def test_waiting_narration_failure_is_resumable_and_preserves_image_handoff(tmp_path, monkeypatch):
    from toc.harness import append_state_snapshot, parse_state_file
    run = make_run(tmp_path); setup_api(monkeypatch, tmp_path)
    append_state_snapshot(run / 'state.txt', {'status': 'P680', 'slot.p710.status': 'pending', 'slot.p680.status': 'done'})
    monkeypatch.setattr(app, '_validate_current_p680_run', lambda *a, **k: None)
    monkeypatch.setattr(app, '_resume_saved_media_operation', AsyncMock(side_effect=RuntimeError('draft failure')))
    async def scenario():
        job = await app.api_resume_run('sample', app.ResumeRunRequest(continue_waiting=True))
        await app._resume_tasks[job['jobId']]
        assert app._create_jobs[job['jobId']]['status'] == 'failed'
        assert MediaJournal.latest_incomplete(run).data['kind'] == 'narration_drafts'
        state = parse_state_file(run / 'state.txt')
        assert state['status'] == 'FAILED'
        assert state['runtime.failure.stage'] == 'p710'
        assert state['slot.p680.status'] == 'done'
        assert job['jobId'] not in app._run_execution_leases
    asyncio.run(scenario())


def test_narration_journal_setup_failure_does_not_invalidate_images(tmp_path, monkeypatch):
    from toc.harness import append_state_snapshot, parse_state_file
    run = make_run(tmp_path); setup_api(monkeypatch, tmp_path)
    append_state_snapshot(run / 'state.txt', {'status': 'P680', 'slot.p710.status': 'pending', 'slot.p680.status': 'done'})
    monkeypatch.setattr(app, '_validate_current_p680_run', lambda *a, **k: None)
    original_create = MediaJournal.create
    monkeypatch.setattr(MediaJournal, 'create', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('journal setup failed')))
    from unittest.mock import Mock
    invalidate = Mock(side_effect=AssertionError('image handoff must be preserved'))
    monkeypatch.setattr(app, '_invalidate_published_image_generation_handoff', invalidate)
    async def scenario():
        job = await app.api_resume_run('sample', app.ResumeRunRequest(continue_waiting=True))
        await app._resume_tasks[job['jobId']]
        assert app._create_jobs[job['jobId']]['status'] == 'failed'
        assert parse_state_file(run / 'state.txt')['slot.p680.status'] == 'done'
        invalidate.assert_not_called()
        monkeypatch.setattr(MediaJournal, 'create', original_create)
        monkeypatch.setattr(app, '_resume_saved_media_operation', AsyncMock(return_value={'status': 'completed'}))
        retry = await app.api_resume_run('sample', app.ResumeRunRequest())
        assert retry['resumeMode'] == 'narration_start'
        await app._resume_tasks[retry['jobId']]
        assert app._create_jobs[retry['jobId']]['status'] == 'completed'
        invalidate.assert_not_called()
    asyncio.run(scenario())
