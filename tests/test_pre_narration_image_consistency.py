import asyncio
import copy
import json
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from toc import scene_direction_service as service
from server import image_gen_app as app
from server import video_preparation_api as route
from test_scene_video_preparation import fixture, FakeHooks, opts
from test_automatic_narration import make_run


class ImageHooks(FakeHooks):
    def check_audio(self, data, sid):
        raise AssertionError('image-only preparation waited for narration')

    def extra_video_cost(self, old, new):
        raise AssertionError('image-only preparation priced future videos')

    async def publish(self, sid, snapshot, new_scene, *, expected_outputs):
        from toc.image_consistency import image_snapshot
        assert image_snapshot(self.root, self.data, sid)['digest'] == snapshot['digest']
        self.data['scenes'][0] = copy.deepcopy(new_scene)
        return image_snapshot(self.root, self.data, sid)


def test_images_are_checked_without_audio_and_receipt_survives_narration(tmp_path):
    root, data = fixture(tmp_path)
    data['video_metadata'] = {'video_preparation_policy': service.POLICY}
    narration = data['scenes'][0]['cuts'][0]['audio']['narration']
    narration.update(text='Not yet spoken', output='')
    script = {'scenes': [{'scene_id': '1', 'cuts': [{'cut_id': '1', 'narration': 'draft', 'tts_text': 'draft'}]}]}
    (root / 'script.md').write_text(json.dumps(script))
    hooks = ImageHooks(root, data, {'status': 'unchanged', 'cuts': {}})
    result = asyncio.run(service.prepare_run(root, hooks, opts(phase='images')))
    assert result['status'] == 'completed', result
    service.require_images_ready(root, hooks.data)
    assert not (root / service.BASE / 'ready').exists()
    with pytest.raises(service.NeedsInput):
        service.require_ready(root, hooks.data)

    hooks.data['scenes'][0]['cuts'][0]['audio']['narration'].update(text='final', tts_text='spoken', output='assets/audio.wav')
    script['scenes'][0]['cuts'][0].update(narration='final', tts_text='spoken', narration_authoring={'revision': 1})
    script['audio_story_plan'] = {'continuous_full_draft': 'final'}
    (root / 'script.md').write_text(json.dumps(script))
    (root / 'assets/audio.wav').write_bytes(b'new voice')
    service.require_images_ready(root, hooks.data)
    asyncio.run(service.prepare_run(root, hooks, opts(phase='images')))
    assert hooks.calls == 1
    Image.new('RGB', (16, 9), 'blue').save(root / 'assets/start.png')
    with pytest.raises(service.NeedsInput):
        service.require_images_ready(root, hooks.data)


def test_image_phase_repairs_and_preserves_existing_audio(tmp_path):
    root, data = fixture(tmp_path)
    before = copy.deepcopy(data['scenes'][0]['cuts'][0]['audio'])
    hooks = ImageHooks(root, data, {'status': 'revised', 'cuts': {'scene1_cut1': {}}, 'reason': 'contact mismatch'})
    result = asyncio.run(service.prepare_run(root, hooks, opts(phase='images')))
    assert result['status'] == 'completed', result
    assert hooks.generated == 1
    assert hooks.data['scenes'][0]['cuts'][0]['audio'] == before
    assert (root / 'assets/audio.wav').read_bytes() == b'audio'


def test_image_receipt_binds_visual_source_changes(tmp_path):
    from toc.image_consistency import image_snapshot
    root, data = fixture(tmp_path)
    before = image_snapshot(root, data, '1')['digest']
    data['scenes'][0]['cuts'][0]['cut_contract'] = {'first_frame_contract': {'first_frame_brief': 'different pose'}}
    assert image_snapshot(root, data, '1')['digest'] != before


def test_image_phase_context_has_no_measured_audio(tmp_path, monkeypatch):
    from test_video_preparation_api import setup
    root, data = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(app, '_narration_min_duration_seconds', lambda *a: (_ for _ in ()).throw(AssertionError('audio probe')))
    hooks = route.RuntimeHooks(root, phase='images')
    snapshot = hooks.snapshot(data, '10')
    context = hooks.context(data, '10', snapshot)
    assert context['phase'] == 'images'
    assert context['audio_measurements'] == {}
    assert 'audio' not in context['scene']['cuts'][0]


def test_image_failure_blocks_narration_author_and_tts(tmp_path, monkeypatch):
    run = make_run(tmp_path)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    monkeypatch.setattr(app, '_set_create_job', AsyncMock())
    images = AsyncMock(side_effect=service.NeedsInput('unresolved image inconsistency'))
    author = AsyncMock()
    tts = AsyncMock()
    monkeypatch.setattr(app, '_ensure_image_consistency_before_narration', images, raising=False)
    monkeypatch.setattr(app, '_author_automatic_narration', author)
    monkeypatch.setattr(app, '_resume_saved_media_operation', tts)
    with pytest.raises(service.NeedsInput, match='image inconsistency'):
        asyncio.run(app._continue_create_narration('job', run_id='sample'))
    author.assert_not_awaited()
    tts.assert_not_awaited()
    state = app.parse_state_file(run / 'state.txt')
    assert state['slot.p680.status'] == 'done'
    assert state['runtime.failure.phase'] == 'image_consistency'


def test_direct_tts_preparation_cannot_skip_image_readiness(tmp_path, monkeypatch):
    run = make_run(tmp_path)
    path, text, data = app._read_manifest_data(run)
    data['video_metadata'] = {'video_preparation_policy': service.POLICY}
    app._write_manifest_data(path, text, data)
    before = path.read_bytes()
    with pytest.raises(service.NeedsInput, match='画像'):
        app._prepare_manifest_narration_generation(run, [])
    assert path.read_bytes() == before


def test_ensure_repairs_missing_audio_and_reuses_receipt(tmp_path, monkeypatch):
    from test_video_preparation_api import setup
    from test_cut_direction_api import _plan
    root, data = setup(tmp_path, monkeypatch)
    data['video_metadata']['video_preparation_policy'] = service.POLICY
    narration = data['scenes'][0]['cuts'][0]['audio']['narration']
    narration['output'] = ''
    path, text, _ = app._read_manifest_data(root)
    app._write_manifest_data(path, text, data)
    before = copy.deepcopy(narration)
    seen = []
    async def author(self, context, images):
        seen.append(context['phase'])
        assert context['audio_measurements'] == {}
        return {'status': 'revised', 'cuts': {'scene10_cut01': _plan()}}
    async def generate(self, item, kind, node, key):
        dest = root / 'assets/scenes/candidate.png'
        Image.new('RGB', (16, 9), 'green').save(dest)
        return 'assets/scenes/candidate.png'
    monkeypatch.setattr(route.RuntimeHooks, 'author', author)
    monkeypatch.setattr(route.RuntimeHooks, 'generate_image', generate)
    monkeypatch.setattr(route.RuntimeHooks, 'review', AsyncMock(return_value={'status': 'ready'}))
    monkeypatch.delenv('TOC_PREPARATION_IMAGE_COST_UPPER_USD', raising=False)
    monkeypatch.delenv('TOC_PREPARATION_VIDEO_SECOND_COST_UPPER_USD', raising=False)
    asyncio.run(route.ensure_image_consistency(root))
    published = app._read_manifest_data(root)[2]
    assert published['scenes'][0]['cuts'][0]['audio']['narration'] == before
    service.require_images_ready(root, published)
    asyncio.run(route.ensure_image_consistency(root))
    assert seen == ['images']
    assert service.read_status(root, 'images')['budget']['imageCount'] == 1
    assert not service.read_status(root)['enabled']


@pytest.mark.parametrize('endpoint,request_type', [
    ('api_create_narration_drafts', 'NarrationDraftCreateRequest'),
    ('api_narration_generate', 'NarrationGenerateRequest'),
    ('api_narration_generate_bulk', 'BulkNarrationGenerateRequest'),
])
def test_manual_narration_failure_cannot_reach_writer(tmp_path, monkeypatch, endpoint, request_type):
    make_run(tmp_path)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    check = AsyncMock(side_effect=service.NeedsInput('画像確認が未完了'))
    monkeypatch.setattr(app, '_ensure_image_consistency_before_narration', check)
    from unittest.mock import Mock
    writer = Mock(side_effect=AssertionError('writer must not run'))
    monkeypatch.setattr(app, '_create_narration_drafts_in_manifest', writer)
    monkeypatch.setattr(app, '_prepare_manifest_narration_generation', writer)
    item = {'item_id': 'scene1_cut1', 'expected_revision': 0, 'expected_tts_hash': 'hash'}
    kwargs = {'items': [item]} if 'bulk' in endpoint else (item if endpoint == 'api_narration_generate' else {})
    request = getattr(app, request_type)(run_id='sample', **kwargs)
    from fastapi import HTTPException
    with pytest.raises((service.NeedsInput, HTTPException), match='画像'):
        asyncio.run(getattr(app, endpoint).__wrapped__(request))
    writer.assert_not_called()


def test_image_prerequisite_inherits_saved_fixed_image_constraints(tmp_path, monkeypatch):
    from test_video_preparation_api import setup
    root, data = setup(tmp_path, monkeypatch)
    data['video_metadata']['video_preparation_policy'] = service.POLICY
    path, text, _ = app._read_manifest_data(root)
    app._write_manifest_data(path, text, data)
    service.save_json(root, service.BASE + '/current.json', {
        'enabled': True, 'status': 'needs_input', 'fixed_image_paths': ['assets/scenes/scene10_cut01.png'],
        'target_video_model': 'higgsfield_kling_standard',
        'limits': {'max_image_generations': 3, 'max_cost_usd': 4},
    })
    execute = AsyncMock(return_value={'status': 'needs_input', 'scenes': [{'status': 'needs_input', 'reason': 'fixed'}]})
    monkeypatch.setattr(route, 'execute_preparation', execute)
    with pytest.raises(service.NeedsInput, match='fixed'):
        asyncio.run(route.ensure_image_consistency(root))
    request = execute.await_args.args[0]
    assert request.fixed_image_paths == ['assets/scenes/scene10_cut01.png']
    assert request.target_video_model == 'higgsfield_kling_standard'
    assert request.max_image_generations == 3 and request.max_cost_usd == 4


def test_cancel_different_phase_preserves_active_task(tmp_path, monkeypatch):
    root, _ = fixture(tmp_path)
    monkeypatch.setattr(app, 'safe_run_dir', lambda *args: root)
    monkeypatch.setattr(route, '_TASKS', {})
    monkeypatch.setattr(route, '_TASK_PHASES', {})
    from fastapi import HTTPException
    async def scenario():
        task = asyncio.create_task(asyncio.Event().wait())
        route._TASKS[root.name] = task
        route._TASK_PHASES[root.name] = 'images'
        try:
            with pytest.raises(HTTPException, match='phase'):
                await route.cancel_preparation(route.CancelRequest(run_id=root.name, phase='video'))
            assert not task.cancelling()
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
    asyncio.run(scenario())


def test_status_does_not_attribute_other_phase_lock_to_stale_operation(tmp_path, monkeypatch):
    root, _ = fixture(tmp_path)
    monkeypatch.setattr(app, 'safe_run_dir', lambda *args: root)
    monkeypatch.setattr(route, '_TASKS', {root.name: object()})
    monkeypatch.setattr(route, '_TASK_PHASES', {root.name: 'video'})
    path = service.phase_base('images') + '/current.json'
    service.save_json(root, path, {'enabled': True, 'status': 'running'})
    from toc.runtime_locks import sync_file_lock
    with sync_file_lock(root / '.locks/video_preparation.lock', wait=False):
        status = asyncio.run(route.get_preparation(root.name, 'images'))
    assert status['status'] == 'needs_input'
    assert service.read_json(root, path)['status'] == 'running'  # GET remains read-only.
