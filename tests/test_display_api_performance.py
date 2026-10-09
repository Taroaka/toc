import asyncio
import threading
from unittest.mock import Mock

from server import image_gen_app as app


def test_narration_list_reuses_supplied_manifest_for_candidate_queries(tmp_path, monkeypatch):
    data = {'scenes': []}
    targets = [{'selector': f'scene1_cut{i}', 'cut': {}, 'scene': {}} for i in (1, 2)]
    monkeypatch.setattr(app, '_manifest_scene_targets', lambda _: targets)
    read = Mock(side_effect=AssertionError('must not reread manifest'))
    candidate = Mock(return_value=None)
    monkeypatch.setattr(app, '_read_manifest_data', read)
    monkeypatch.setattr(app, '_candidate_video_output_for_item', candidate)
    assert len(app._manifest_narration_items(tmp_path, data)) == 2
    assert all(call.kwargs.get('manifest_data') is data for call in candidate.call_args_list)
    read.assert_not_called()


def test_narration_endpoint_offloads_display_work(tmp_path, monkeypatch):
    run = tmp_path / 'output/sample'; run.mkdir(parents=True)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    main_thread = threading.get_ident()
    def payload(root):
        assert root == run
        assert threading.get_ident() != main_thread
        return {'items': [], 'progress': {}, 'audioSetHash': ''}
    monkeypatch.setattr(app, '_narration_display_payload', payload)
    assert asyncio.run(app.api_narration_items('sample'))['items'] == []


def test_progress_endpoint_does_not_run_generation_validation(tmp_path, monkeypatch):
    run = tmp_path / 'output/sample'; run.mkdir(parents=True)
    monkeypatch.setattr(app, 'ROOT', tmp_path)
    read = Mock(return_value={'status': 'P720'})
    monkeypatch.setattr(app, 'read_run_progress', read)
    assert asyncio.run(app.api_progress('sample'))['progress']['status'] == 'P720'
    read.assert_called_once_with(run, validate_request_outputs=False)


def test_video_display_preserves_progress_response(tmp_path, monkeypatch):
    from server import display_reads
    monkeypatch.setattr(display_reads, 'read_manifest', lambda *a: {})
    monkeypatch.setattr(app, '_manifest_video_items', lambda *a: [])
    monkeypatch.setattr(app, 'list_reference_options', lambda *a: [])
    read = Mock(return_value={'status': 'P720'})
    monkeypatch.setattr(app, 'read_run_progress', read)
    payload = app._video_display_payload(tmp_path)
    assert payload['progress'] == {'status': 'P720'}
    assert payload['items'] == []
    read.assert_called_once_with(tmp_path, validate_request_outputs=False)
