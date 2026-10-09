import pytest
from toc.media_resume import MediaJournal


def test_media_resume_preserves_completed_item_and_exact_settings(tmp_path):
    (tmp_path / 'video_manifest.md').write_text('manifest')
    request = {'run_id': 'run', 'voice_id': 'selected-voice', 'items': [1, 2]}
    journal = MediaJournal.create(tmp_path, 'narration', request)
    (tmp_path / 'audio.wav').write_bytes(b'valid media')
    result = {'status': 'completed', 'path': 'audio.wav'}
    journal.complete_item('first', {'text': 'hello'}, result)
    journal.finish(False)
    resumed = MediaJournal.load(tmp_path, journal.id)
    resumed.verify_inputs()
    assert resumed.request == request
    assert resumed.cached('first', {'text': 'hello'}) == result
    assert resumed.cached('second', {}) is None
    (tmp_path / 'audio.wav').write_bytes(b'changed')
    assert resumed.cached('first', {'text': 'hello'}) is None


def test_media_resume_rejects_changed_canonical_input(tmp_path):
    (tmp_path / 'video_manifest.md').write_text('manifest')
    journal = MediaJournal.create(tmp_path, 'video', {'run_id': 'run'})
    (tmp_path / 'video_manifest.md').write_text('edited prompt')
    with pytest.raises(ValueError, match='inputs changed'):
        MediaJournal.load(tmp_path, journal.id).verify_inputs()


def test_failed_result_is_not_a_cache_hit(tmp_path):
    journal = MediaJournal.create(tmp_path, 'video', {})
    journal.complete_item('cut', {}, {'candidates': [{'status': 'failed', 'path': None}]})
    assert journal.cached('cut', {}) is None
    journal.finish(False)
    assert MediaJournal.latest_incomplete(tmp_path).id == journal.id


def test_saved_operation_id_and_output_paths_are_confined(tmp_path):
    with pytest.raises(ValueError):
        MediaJournal.load(tmp_path, '../outside')
    journal = MediaJournal.create(tmp_path, 'video', {})
    with pytest.raises(ValueError):
        journal.complete_item('cut', {}, {'status': 'completed', 'path': '../outside'})


def test_bulk_narration_resume_only_retries_failed_item(tmp_path, monkeypatch):
    import asyncio
    from collections import Counter
    from server import image_gen_app as app
    root = tmp_path / 'output' / 'run'
    root.mkdir(parents=True)
    (root / 'video_manifest.md').write_text('manifest')
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app, 'read_run_progress', lambda _: {})
    monkeypatch.setattr(app, '_probe_media_duration_seconds', lambda _: 1.0)
    calls = Counter()
    @app._durable_media_operation('narration')
    async def generate(req):
        calls[req.item_id] += 1
        if req.item_id == 'second' and calls['second'] == 1:
            return {'status': 'failed', 'item': {'status': 'failed', 'error': 'provider unavailable'}}
        path = req.item_id + '.wav'
        (root / path).write_bytes(b'audio')
        return {'status': 'candidate', 'item': {'status': 'candidate', 'path': path}, 'updated': [req.item_id]}
    monkeypatch.setattr(app, 'api_narration_generate', generate)
    request = app.BulkNarrationGenerateRequest(run_id='run', items=[
        app.NarrationGenerateItem(item_id=i, text='line', expected_revision=1, expected_tts_hash='hash', voice_id='selected')
        for i in ('first', 'second')])
    result = asyncio.run(app.api_narration_generate_bulk(request))
    assert result['status'] == 'partial_failure'
    operation_id = result['operationId']
    retry = asyncio.run(app._resume_saved_media_operation(root, operation_id))
    assert retry['status'] == 'completed'
    assert calls == {'first': 1, 'second': 2}
    assert MediaJournal.load(root, operation_id).request['items'][0]['voice_id'] == 'selected'


def test_resume_video_keeps_successful_candidates(tmp_path, monkeypatch):
    import asyncio
    from collections import Counter
    from server import image_gen_app as app
    root = tmp_path / 'output' / 'run'; root.mkdir(parents=True)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app, '_assert_video_request_within_provider_capabilities', lambda _: None)
    monkeypatch.setattr(app, '_narration_min_duration_seconds', lambda *args: None)
    monkeypatch.setattr(app, '_probe_media_duration_seconds', lambda _: 1.0)
    calls = Counter()
    async def candidate(run, req, index):
        calls[index] += 1
        if index == 2 and calls[index] == 1:
            return {'status': 'failed', 'error': 'timeout', 'index': index}
        path = f'clip{index}.mp4'; (root / path).write_bytes(b'clip')
        return {'status': 'completed', 'path': path, 'index': index}
    monkeypatch.setattr(app, '_generate_video_one', candidate)
    @app._durable_media_operation('video')
    async def generate(req):
        return await app._generate_video_candidates(root, req)
    monkeypatch.setattr(app, 'api_video_generate', generate)
    req = app.VideoGenerateRequest(run_id='run', item_id='cut', prompt='prompt', candidate_count=2)
    result = asyncio.run(generate(req))
    retry = asyncio.run(app._resume_saved_media_operation(root, result['operationId']))
    assert len(retry['candidates']) == 2
    assert calls == {1: 1, 2: 2}


def test_render_retry_uses_saved_settings_and_input_bindings(tmp_path, monkeypatch):
    import asyncio
    from server import image_gen_app as app
    root = tmp_path / 'output' / 'run'; root.mkdir(parents=True)
    (root / 'clip.mp4').write_bytes(b'input')
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    calls = []
    @app._durable_media_operation('render')
    async def render(req):
        calls.append(req.model_dump())
        if len(calls) == 1:
            raise RuntimeError('encoder failed')
        (root / req.output).write_bytes(b'output')
        return {'status': 'rendered', 'finalOutput': req.output}
    monkeypatch.setattr(app, 'api_final_render', render)
    req = app.FinalRenderRequest(run_id='run', output='final.mp4', reencode=True,
        items=[app.RenderInputItem(item_id='cut', video_path='clip.mp4')])
    with pytest.raises(RuntimeError, match='encoder failed'):
        asyncio.run(render(req))
    operation = MediaJournal.latest_incomplete(root)
    result = asyncio.run(app._resume_saved_media_operation(root, operation.id))
    assert result['finalOutput'] == 'final.mp4'
    assert calls[0] == calls[1]


def test_cancellation_retains_lease_until_provider_result_is_recorded(tmp_path, monkeypatch):
    import asyncio
    from server import image_gen_app as app
    root = tmp_path / 'output' / 'run'; root.mkdir(parents=True)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    async def scenario():
        entered, finish = asyncio.Event(), asyncio.Event()
        @app._durable_media_operation('render')
        async def render(req):
            entered.set()
            await finish.wait()
            (root / req.output).write_bytes(b'output')
            return {'status': 'rendered', 'finalOutput': req.output}
        req = app.FinalRenderRequest(run_id='run', items=[app.RenderInputItem(item_id='cut')])
        task = asyncio.create_task(render(req))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert any(key.startswith('media-') for key in app._run_execution_leases)
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not any(key.startswith('media-') for key in app._run_execution_leases)
        assert MediaJournal.latest_incomplete(root) is None
    asyncio.run(scenario())


def test_recording_result_does_not_adopt_external_input_changes(tmp_path):
    (tmp_path / 'video_manifest.md').write_text('original')
    journal = MediaJournal.create(tmp_path, 'video', {})
    (tmp_path / 'video_manifest.md').write_text('changed elsewhere')
    (tmp_path / 'clip.mp4').write_bytes(b'clip')
    journal.complete_item('one', {}, {'status': 'completed', 'path': 'clip.mp4'})
    journal.finish(False)
    with pytest.raises(ValueError, match='inputs changed'):
        MediaJournal.load(tmp_path, journal.id).verify_inputs()


def test_own_manifest_publication_and_rollback_remain_resumable(tmp_path):
    (tmp_path / 'video_manifest.md').write_text('original')
    journal = MediaJournal.create(tmp_path, 'narration', {})
    journal.authorize_manifest_update('with candidates')
    (tmp_path / 'video_manifest.md').write_text('with candidates')
    journal.verify_inputs()
    journal.confirm_manifest_update('video_manifest.md')
    journal.authorize_manifest_update('original')
    (tmp_path / 'video_manifest.md').write_text('original')
    MediaJournal.load(tmp_path, journal.id).verify_inputs()


def test_success_in_another_item_does_not_hide_failed_operation(tmp_path):
    failed = MediaJournal.create(tmp_path, 'video', {'item_id': 'a'})
    failed.finish(False)
    success = MediaJournal.create(tmp_path, 'video', {'item_id': 'b'})
    success.finish(True)
    assert MediaJournal.latest_incomplete(tmp_path).id == failed.id
    replacement = MediaJournal.create(tmp_path, 'video', {'item_id': 'a'})
    replacement.finish(True)
    assert MediaJournal.latest_incomplete(tmp_path) is None


def test_old_publication_cannot_be_accepted_as_external_rollback(tmp_path):
    (tmp_path / 'video_manifest.md').write_text('v1')
    journal = MediaJournal.create(tmp_path, 'narration', {})
    journal.authorize_manifest_update('v2')
    (tmp_path / 'video_manifest.md').write_text('v2')
    journal.confirm_manifest_update('video_manifest.md')
    (tmp_path / 'video_manifest.md').write_text('v1')
    with pytest.raises(ValueError, match='inputs changed'):
        MediaJournal.load(tmp_path, journal.id).verify_inputs()


def test_external_drift_prevents_manifest_overwrite(tmp_path):
    from server import image_gen_app as app
    from toc.media_resume import ACTIVE_MEDIA_JOURNAL
    manifest = tmp_path / 'video_manifest.md'
    manifest.write_text('original')
    journal = MediaJournal.create(tmp_path, 'video', {})
    manifest.write_text('external edit')
    token = ACTIVE_MEDIA_JOURNAL.set(journal)
    try:
        with pytest.raises(ValueError, match='refusing to overwrite'):
            app._write_manifest_data(manifest, 'original', {'scenes': []})
        assert manifest.read_text() == 'external edit'
    finally:
        ACTIVE_MEDIA_JOURNAL.reset(token)


def test_success_without_output_is_not_reported_as_complete(tmp_path, monkeypatch):
    import asyncio
    from server import image_gen_app as app
    root = tmp_path / 'output' / 'run'; root.mkdir(parents=True)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    @app._durable_media_operation('render')
    async def render(req):
        return {'status': 'rendered'}
    req = app.FinalRenderRequest(run_id='run', items=[app.RenderInputItem(item_id='cut')])
    with pytest.raises(RuntimeError, match='could not be verified'):
        asyncio.run(render(req))
    assert MediaJournal.latest_incomplete(root) is not None


def test_bulk_video_limit_is_enforced_before_provider_work(tmp_path, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    from server import image_gen_app as app
    root = tmp_path / 'output' / 'run'; root.mkdir(parents=True)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app, '_validate_video_request_reference_paths', lambda *args: None)
    monkeypatch.setattr(app, '_require_narration_ready_for_video', lambda *args: None)
    monkeypatch.setattr(app, '_materialized_video_generate_item', lambda **kwargs: kwargs['request'])
    provider = AsyncMock()
    monkeypatch.setattr(app, '_generate_video_candidates', provider)
    req = app.BulkVideoGenerateRequest(run_id='run', items=[
        app.VideoGenerateItem(item_id=f'cut{i}', prompt='prompt', candidate_count=8) for i in range(13)])
    with pytest.raises(app.HTTPException) as error:
        asyncio.run(app.api_video_generate_bulk(req))
    assert error.value.status_code == 400
    provider.assert_not_awaited()


def test_bulk_narration_rejects_duplicate_items(tmp_path, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    from server import image_gen_app as app
    root = tmp_path / 'output' / 'run'; root.mkdir(parents=True)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    provider = AsyncMock()
    monkeypatch.setattr(app, 'api_narration_generate', provider)
    item = app.NarrationGenerateItem(item_id='cut', expected_revision=1, expected_tts_hash='hash')
    with pytest.raises(ValueError, match='duplicate'):
        asyncio.run(app.api_narration_generate_bulk(app.BulkNarrationGenerateRequest(run_id='run', items=[item, item])))
    provider.assert_not_awaited()
