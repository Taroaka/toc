import hashlib
import os
import subprocess
import json
import array
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
import pytest
import yaml

from server import image_gen_app as api
from server.app import app


def fixture(root):
    run = root / 'output' / 'test_run'
    (run / 'assets/scenes').mkdir(parents=True)
    for name, color in [('base', 'red'), ('edit', 'blue')]:
        Image.new('RGB', (16, 9), color).save(run / f'assets/scenes/{name}.png')
    candidate = run / 'assets/test/image_gen_candidates/scene1_cut1/scene1_cut1_candidate_01.png'
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes((run / 'assets/scenes/edit.png').read_bytes())
    manifest = {'scenes': [{'scene_id': 1, 'cuts': [{'cut_id': '1',
        'image_generation': {'output': 'assets/scenes/base.png', 'references': []},
        'video_generation': {'output': 'assets/scenes/source.mp4', 'duration_seconds': 4},
        'audio': {'narration': {'tool': 'silent', 'text': '', 'silence_contract': {'intentional': True, 'kind': 'visual_value_hold', 'duration_seconds': 4}}}}]}]}
    (run / 'video_manifest.md').write_text('```yaml\n' + yaml.safe_dump(manifest) + '```\n')
    (run / 'state.txt').write_text('status=P680\n')
    return run


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_notes_variants_and_stale_note_conflict(tmp_path):
    run = fixture(tmp_path)
    with patch.object(api, 'ROOT', tmp_path), patch.dict(os.environ, {'TOC_SERVER_AUTH_DISABLED': '1'}), TestClient(app) as client:
        response = client.get('/api/image-gen/production-tools', params={'run_id': 'test_run', 'item_id': 'scene1_cut1', 'kind': 'image'})
        assert response.status_code == 200, response.text
        context = response.json()
        assert context['run_id'] == 'test_run'
        edited = next(c for c in context['candidates'] if 'candidate_' in c['path'])
        note = {'run_id': 'test_run', 'item_id': 'scene1_cut1', 'kind': 'image', 'candidate_path': edited['path'],
            'candidate_sha256': edited['sha256'], 'expected_revision': 0, 'disposition': 'undecided',
            'problem': '服の色が違う', 'change': '服だけ変更', 'result': ''}
        assert client.post('/api/image-gen/production-tools/notes', json=note).status_code == 200
        assert client.post('/api/image-gen/production-tools/notes', json=note).status_code == 409
        request = {'run_id': 'test_run', 'item_id': 'scene1_cut1', 'base_path': 'assets/scenes/base.png',
            'edited_path': edited['path'], 'base_sha256': sha(run / 'assets/scenes/base.png'),
            'edited_sha256': edited['sha256'], 'regions': [{'x': 0.5, 'y': 0, 'width': 0.5, 'height': 1}],
            'state_description': '衣服だけの差分'}
        result = client.post('/api/image-gen/production-tools/variant', json=request)
        assert result.status_code == 200, result.text
        variants = result.json()['variants']
        assert len(variants) == 1
        assert (run / variants[0]['path']).is_file()
        assert sha(run / 'assets/scenes/base.png') == request['base_sha256']
        forged = {**note, 'candidate_path': 'assets/scenes/edit.png', 'candidate_sha256': sha(run / 'assets/scenes/edit.png'), 'expected_revision': 1}
        assert client.post('/api/image-gen/production-tools/notes', json=forged).status_code == 400


def test_explicit_video_selection_beats_default_and_detects_changed_bytes(tmp_path):
    from server.production_tools_api import select_video_path
    run = fixture(tmp_path)
    source = run / 'assets/scenes/source.mp4'
    source.write_bytes(b'original')
    with patch.object(api, 'ROOT', tmp_path), patch.object(api, '_probe_media_duration_seconds', return_value=4):
        select_video_path(run, 'scene1_cut1', 'assets/scenes/source.mp4', sha(source))
        assert api._candidate_video_output_for_item(run, 'scene1_cut1') == 'assets/scenes/source.mp4'
        source.write_bytes(b'changed')
        with pytest.raises(ValueError, match='changed|stale'):
            api._candidate_video_output_for_item(run, 'scene1_cut1')


def test_video_edit_selection_invalidates_sound_and_reaches_final_render(tmp_path):
    run = fixture(tmp_path)
    source = run / 'assets/scenes/source.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=160x90:r=24:d=6',
        '-itsoffset', '1.5', '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=48000:duration=4.5',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(source)], check=True)
    original_hash = sha(source)
    path, text, manifest = api._read_manifest_data(run)
    manifest['scenes'][0]['cuts'][0]['video_generation']['native_audio'] = {'mode': 'natural_sound'}
    api._write_manifest_data(path, text, manifest)
    with patch.object(api, 'ROOT', tmp_path), patch.dict(os.environ, {'TOC_SERVER_AUTH_DISABLED': '1'}), TestClient(app) as client:
        before = client.get('/api/image-gen/sound-design', params={'run_id': 'test_run'}).json()
        approved = client.post('/api/image-gen/sound-design/approve-video', json={'run_id': 'test_run',
            'video_set_hash': before['context']['video_set_hash'], 'revision': 0})
        assert approved.status_code == 200, approved.text
        edit = client.post('/api/image-gen/production-tools/video-edit', json={'run_id': 'test_run', 'item_id': 'scene1_cut1',
            'source_path': 'assets/scenes/source.mp4', 'source_sha256': original_hash,
            'settings': {'start_seconds': 1, 'duration_seconds': 4, 'brightness': 0.1}})
        assert edit.status_code == 200, edit.text
        record = edit.json()['video_edits'][0]
        selected = client.post('/api/image-gen/production-tools/select-video', json={'run_id': 'test_run',
            'item_id': 'scene1_cut1', 'path': record['output_path'], 'sha256': record['output_sha256']})
        assert selected.status_code == 200, selected.text
        changed = client.get('/api/image-gen/sound-design', params={'run_id': 'test_run'}).json()
        assert changed['approved'] is False
        assert changed['context']['video_set_hash'] != before['context']['video_set_hash']
        approved = client.post('/api/image-gen/sound-design/approve-video', json={'run_id': 'test_run',
            'video_set_hash': changed['context']['video_set_hash'], 'revision': changed['plan']['revision']}).json()
        complete = client.post('/api/image-gen/sound-design/complete', json={'run_id': 'test_run',
            'video_set_hash': approved['context']['video_set_hash'], 'revision': approved['plan']['revision']})
        assert complete.status_code == 200, complete.text
        result = api._freeze_render_inputs(run, api.RenderFreezeRequest(run_id='test_run', output='video.mp4',
            items=[api.RenderInputItem(item_id='scene1_cut1', video_duration_seconds=4)]))
        snapshot = json.loads((run / result['soundPlan']).read_text())
        assert snapshot['native_tracks'][0]['path'] == record['output_path']
        from toc.sound_design import mix_audio
        mixed = tmp_path / 'mix.m4a'
        mix_audio(snapshot, run / result['narrationList'], mixed)
        raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(mixed), '-ar', '48000', '-ac', '1', '-f', 'f32le', '-'])
        samples = array.array('f', raw)
        rms = lambda start: (sum(v*v for v in samples[int(start*48000):int((start+.1)*48000)]) / 4800) ** .5
        assert rms(.1) < .01
        assert rms(.9) > .04
        assert sha(source) == original_hash
        refreshed = client.get('/api/image-gen/production-tools', params={'run_id':'test_run','item_id':'scene1_cut1','kind':'video'}).json()
        assert 'assets/scenes/source.mp4' in [candidate['path'] for candidate in refreshed['candidates']]
        path, text, changed_manifest = api._read_manifest_data(run)
        changed_manifest['scenes'][0]['cuts'][0]['video_generation']['prompt_authoring_source'] = '変更後の生成指示'
        api._write_manifest_data(path, text, changed_manifest)
        stale = client.get('/api/image-gen/production-tools', params={'run_id':'test_run','item_id':'scene1_cut1','kind':'video'}).json()
        assert stale['video_edits'][0]['is_stale']
        assert stale['selection_error']
        assert client.post('/api/image-gen/production-tools/select-video', json={'run_id':'test_run',
            'item_id':'scene1_cut1','path':record['output_path'],'sha256':record['output_sha256']}).status_code == 400


def test_saved_geometry_is_marked_stale_after_request_change(tmp_path):
    run = fixture(tmp_path)
    geometry = {'schema_version': 'shot_geometry_v1', 'camera': {'position': [0,-5,1], 'target': [0,0,1],
        'vertical_fov_degrees': 45, 'aspect_ratio': 16/9}, 'subjects': [], 'lights': []}
    with patch.object(api, 'ROOT', tmp_path), patch.dict(os.environ, {'TOC_SERVER_AUTH_DISABLED': '1'}), TestClient(app) as client:
        saved = client.post('/api/image-gen/production-tools/geometry', json={'run_id': 'test_run', 'item_id': 'scene1_cut1',
            'kind': 'video', 'expected_revision': 0, 'geometry': geometry})
        assert saved.status_code == 200, saved.text
        assert not saved.json()['geometry_stale']
        path,text,data = api._read_manifest_data(run)
        data['scenes'][0]['cuts'][0]['video_generation']['prompt_authoring_source'] = '新しい動作'
        api._write_manifest_data(path,text,data)
        context = client.get('/api/image-gen/production-tools', params={'run_id':'test_run','item_id':'scene1_cut1','kind':'video'}).json()
        assert context['geometry_stale']
