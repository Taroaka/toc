"""Narration-only contracts; no harness, model, TTS, or production run is executed."""
from copy import deepcopy
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from server import image_gen_app
from tests.test_narration_frontend_workflow import _write_run, _manifest, _script


def _write_yaml(path, data):
    path.write_text('```yaml\n' + yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + '```\n')


@pytest.fixture
def isolated_run(tmp_path):
    run = _write_run(tmp_path)
    manifest = _manifest(run)
    first = manifest['scenes'][0]['cuts'][0]
    second = deepcopy(first)
    second['cut_id'] = 2
    second['audio']['narration'].update(
        text='この言葉は残す。', tts_text='このことばはのこす。',
        authoring_status='human_locked', output='assets/keep.mp3',
    )
    manifest['scenes'][0]['cuts'].append(second)
    script = _script(run)
    script['scenes'][0]['cuts'].append({
        'cut_id': 2, 'narration': 'この言葉は残す。',
        'tts_text': 'このことばはのこす。',
        'narration_authoring': {'status': 'human_locked'},
    })
    _write_yaml(run / 'video_manifest.md', manifest)
    _write_yaml(run / 'script.md', script)
    # Sentinel bytes test preservation, not media decoding.
    for name in ('story.md', 'research.md', 'assets/keep.mp3',
                 'assets/scenes/scene1_cut1.png', 'assets/clip.mp4'):
        path = run / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'preserve-existing-content')
    return run


def _unchanged_files(run):
    return {p: p.read_bytes() for p in run.rglob('*')
            if p.is_file() and (p.suffix in {'.mp3', '.mp4', '.png'}
                               or p.name in {'research.md', 'story.md'})}


@pytest.mark.parametrize('protected_status', ['human_locked', 'reviewed', 'silent'])
def test_replace_preparation_preserves_protected_cut_and_visuals(isolated_run, protected_status):
    run = isolated_run
    before = _manifest(run)
    cuts = before['scenes'][0]['cuts']
    cuts[0]['audio']['narration'].update(text='要改善の旧原稿。', tts_text='旧原稿。', authoring_status='draft')
    cuts[1]['audio']['narration']['authoring_status'] = protected_status
    if protected_status == 'silent':
        cuts[1]['audio']['narration'].update(text='', tts_text='', tool='silent', output='')
    _write_yaml(run / 'video_manifest.md', before)
    script_before = (run / 'script.md').read_bytes()
    files_before = _unchanged_files(run)
    with patch.object(image_gen_app, 'ROOT', run.parents[1]), patch.object(
        image_gen_app.subprocess, 'run', side_effect=AssertionError('No external process allowed')
    ):
        result = image_gen_app._create_narration_drafts_in_manifest(run, replace=True)
    after = _manifest(run)['scenes'][0]['cuts']
    assert result['updated'] == ['scene1_cut1']
    assert result['skipped'] == ['scene1_cut2']
    assert after[1] == cuts[1]
    assert after[0]['audio']['narration']['text'] == ''
    assert after[0]['audio']['narration']['authoring_status'] == 'missing'
    for old, new in zip(cuts, after):
        assert {k: v for k, v in old.items() if k != 'audio'} == {k: v for k, v in new.items() if k != 'audio'}
    assert (run / 'script.md').read_bytes() == script_before
    assert _unchanged_files(run) == files_before


def test_save_one_rewritten_cut_preserves_other_cut_and_existing_media(isolated_run):
    run = isolated_run
    before = _manifest(run)
    script_before = _script(run)
    files_before = _unchanged_files(run)
    new_text = '旅人は案内人に、日没になる前に広場を出ると約束した。'
    with patch.object(image_gen_app, 'ROOT', run.parents[1]), patch.object(
        image_gen_app.subprocess, 'run', side_effect=AssertionError('No external process allowed')
    ):
        image_gen_app._save_frontend_narration_text(run, image_gen_app.NarrationTextSaveRequest(
            run_id='sample_run', item_id='scene1_cut1', text=new_text,
            tts_text=new_text, tool='elevenlabs', authoring_status='human_locked', expected_revision=0,
        ))
    after = _manifest(run)
    script_after = _script(run)
    assert script_after['scenes'][0]['cuts'][0]['narration'] == new_text
    assert after['scenes'][0]['cuts'][0]['audio']['narration']['text'] == new_text
    assert after['scenes'][0]['cuts'][1] == before['scenes'][0]['cuts'][1]
    assert script_after['scenes'][0]['cuts'][1] == script_before['scenes'][0]['cuts'][1]
    for key in ('image_generation', 'video_generation'):
        assert after['scenes'][0]['cuts'][0][key] == before['scenes'][0]['cuts'][0][key]
    assert _unchanged_files(run) == files_before


def test_current_prompt_includes_clarity_rules_and_keeps_locked_seed(isolated_run):
    root = Path(image_gen_app.__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('narration_scoped_prepare', root / 'scripts/ai/toc-immersive-narration-multiagent.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = _manifest(isolated_run)
    before = deepcopy(data)
    prompt = module._prompt_text(data, ['1'])
    assert '音声だけで理解できる説明の具体性' in prompt
    assert 'どこから／どこへ、いつまでに、なぜ' in prompt
    assert '尺が足りない場合は意味に必要な語を削らず' in prompt
    assert '原作にない動機・帰宅条件・例外を創作せず' in prompt
    protected = data['scenes'][0]['cuts'][1]
    scratch = module._scene_cut_scratch('2', protected)
    assert scratch['read_only'] is True
    assert scratch['narration_text'] == protected['audio']['narration']['text']
    assert 'この言葉は残す。' in prompt
    assert data == before
