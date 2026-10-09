import os
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
import asyncio
import subprocess

from server.app import app
from server import image_gen_app as api
from test_image_gen_server import write_valid_p650_artifacts
from toc.providers.higgsfield import IMAGE_MODEL, REFERENCE_MODEL
from toc.video_provider_capabilities import resolve_video_provider_capabilities


@pytest.mark.parametrize('mode', ['image_to_video', 'reference_images'])
def test_higgsfield_materialization_preserves_inputs_audio_and_recompiles(tmp_path, mode):
    run = write_valid_p650_artifacts(tmp_path, 'sample_run')
    item = {'item_id': 'scene10_cut1', 'kind': 'scene', 'output': 'assets/scenes/scene10_cut1.png',
        'video_prompt': '扉の手前で止まる', 'video_tool': 'higgsfield', 'video_duration_seconds': 8,
        'video_quality': '1080p', 'video_input_mode': mode, 'video_native_audio_mode': 'natural_sound',
        'video_first_reference': '' if mode == 'reference_images' else 'assets/scenes/scene10_cut1.png',
        'video_last_reference': '' if mode == 'reference_images' else 'assets/characters/hero.png',
        'video_references': ['assets/characters/hero.png'] if mode == 'reference_images' else []}
    with patch.dict(os.environ, {'TOC_SERVER_AUTH_DISABLED': '1'}), patch.object(api, 'ROOT', tmp_path):
        with TestClient(app) as client:
            response = client.post('/api/image-gen/video-prompts/create', json={'run_id': 'sample_run', 'items': [item]})
        assert response.status_code == 200, response.text
        _, _, manifest = api._read_manifest_data(run)
        vg = manifest['scenes'][0]['cuts'][0]['video_generation']
        payload = vg['api_prompt_payload']; binding = payload['provider_request_binding']
        assert binding['execution_options']['model'] == (REFERENCE_MODEL if mode == 'reference_images' else IMAGE_MODEL)
        assert binding['execution_options']['generate_audio'] is True
        assert vg['native_audio']['mode'] == 'natural_sound'
        assert '音楽や劇伴を生成しない' in payload['prompt']
        assert binding['references'] == item['video_references']
        assert binding['first_frame'] == item['video_first_reference']
        assert binding['last_frame'] == item['video_last_reference']
        _, recompiled = api._compile_frontend_video_prompt_payload(data=manifest, item=api.FrontendReviewItem(**item), run_dir=run)
        assert payload == recompiled
        bound = api._materialized_video_generate_item(run_dir=run, request=api.VideoGenerateItem(
            item_id=item['item_id'], prompt=item['video_prompt'], tool='higgsfield',
            first_reference=item['video_first_reference'] or None,
            last_reference=item['video_last_reference'] or None, references=item['video_references']))
        assert bound.provider_execution_options['generate_audio'] is True


def test_downloaded_video_requires_matching_duration_ratio_and_audio(tmp_path):
    import subprocess
    import shutil
    from toc.providers.video_validation import verify_generated_video
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('ffmpeg is required')
    video = tmp_path / 'sample.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=160x90:r=24:d=1',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)], check=True)
    assert verify_generated_video(video, duration_seconds=1, aspect_ratio='16:9', require_audio=False)['width'] == 160
    for settings, error in [({'duration_seconds': 2}, 'duration'), ({'aspect_ratio': '1:1'}, 'ratio'),
                            ({'require_audio': True}, 'audio')]:
        with pytest.raises(ValueError, match=error):
            verify_generated_video(video, **({'duration_seconds': 1, 'aspect_ratio': '16:9', 'require_audio': False} | settings))


def test_higgsfield_capabilities_do_not_inherit_seedance_1_limits():
    capability = resolve_video_provider_capabilities(tool='higgsfield', model=IMAGE_MODEL, input_mode='first_last_frame')
    assert capability.supported and capability.duration_max_seconds == 30
    assert capability.native_audio
    assert not resolve_video_provider_capabilities(tool='higgsfield', model=REFERENCE_MODEL, input_mode='first_last_frame').supported
    assert not resolve_video_provider_capabilities(tool='higgsfield', model='unknown', input_mode='image_to_video').supported


def test_higgsfield_rejects_frames_plus_references_before_transport():
    request = api.VideoGenerateItem(item_id='scene1_cut1', prompt='歩く', tool='higgsfield', duration_seconds=8,
        first_reference='assets/first.png', references=['assets/person.png'],
        provider_execution_options={'model': IMAGE_MODEL})
    with pytest.raises(ValueError, match='reference'):
        api._assert_video_request_within_provider_capabilities(request)


def test_generate_publishes_verified_candidate_and_resumes_without_resubmission(tmp_path):
    from toc.providers.higgsfield import HiggsfieldClient
    run = write_valid_p650_artifacts(tmp_path, 'sample_run')
    output = tmp_path / 'provider.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=black:s=160x90:r=24:d=8',
        '-f', 'lavfi', '-i', 'sine=frequency=550:duration=8', '-c:v', 'libx264', '-c:a', 'aac',
        '-pix_fmt', 'yuv420p', str(output)], check=True)
    body = output.read_bytes()
    item = {'item_id': 'scene10_cut1', 'kind': 'scene', 'video_prompt': '扉の手前で止まる',
        'video_tool': 'higgsfield', 'video_duration_seconds': 8, 'video_input_mode': 'reference_images',
        'video_native_audio_mode': 'natural_sound', 'video_first_reference': '', 'video_last_reference': '',
        'video_references': ['assets/characters/hero.png']}
    submitted = []
    request_id = '12345678-1234-1234-1234-123456789012'
    def transport(_self, **kwargs):
        if kwargs['method'] == 'POST':
            submitted.append(kwargs['json_payload'])
            return {'status': 'queued', 'request_id': request_id,
                    'status_url': f'https://api.higgsfield.ai/requests/{request_id}/status'}
        return {'status': 'completed', 'request_id': request_id, 'video': {'url': 'https://cdn.example.org/result.mp4'}}
    with patch.dict(os.environ, {'TOC_SERVER_AUTH_DISABLED': '1', 'HF_API_KEY': 'test:secret'}), patch.object(api, 'ROOT', tmp_path):
        with TestClient(app) as client:
            response = client.post('/api/image-gen/video-prompts/create', json={'run_id': 'sample_run', 'items': [item]})
            assert response.status_code == 200, response.text
        request = api._materialized_video_generate_item(run_dir=run, request=api.VideoGenerateItem(
            item_id=item['item_id'], prompt=item['video_prompt'], tool='higgsfield',
            references=item['video_references'], candidate_count=1))
        with patch.object(HiggsfieldClient, '_api_request_json', transport), \
             patch.object(HiggsfieldClient, '_upload_file', return_value='https://cdn.example.org/reference.png'), \
             patch('toc.providers.higgsfield.validate_media_url', side_effect=lambda url: url), \
             patch('toc.providers.higgsfield.request_public_media_bytes', return_value=body):
            first = asyncio.run(api._generate_video_one(run, request, 1))
            assert first['status'] == 'completed', first
            assert (run / first['path']).is_file()
            again = asyncio.run(api._generate_video_one(run, request, 1))
            assert again['status'] == 'completed', again
            assert len(submitted) == 1
        assert submitted[0]['generate_audio'] is True
        assert submitted[0]['image_urls'] == ['https://cdn.example.org/reference.png']
