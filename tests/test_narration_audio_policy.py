import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch

import pytest

from toc.providers.elevenlabs import ElevenLabsClient, ElevenLabsConfig


def test_v4_provider_defaults_are_explicit_and_overrides_survive():
    client = ElevenLabsClient(ElevenLabsConfig(api_key='test'))
    with patch('toc.providers.elevenlabs.request_bytes', return_value=b'audio') as req:
        client.tts(text='こんにちは')
        assert req.call_args.kwargs['json_payload']['voice_settings'] == {'stability': .5, 'similarity_boost': .75}
        client.tts(text='こんにちは', voice_settings={'stability': .8})
        assert req.call_args.kwargs['json_payload']['voice_settings'] == {'stability': .8, 'similarity_boost': .75}


def run(*args):
    return subprocess.run(['ffmpeg','-hide_banner','-y',*map(str,args)],check=True,capture_output=True,text=True)


@pytest.mark.skipif(not shutil.which('ffmpeg'),reason='ffmpeg required')
def test_normalization_preserves_raw_timing_and_handles_silence(tmp_path):
    from toc.narration_audio import normalize_narration
    src=tmp_path/'quiet.wav';dst=tmp_path/'preview.wav'
    run('-f','lavfi','-i','sine=frequency=440:duration=3','-af','volume=0.1',src)
    before=hashlib.sha256(src.read_bytes()).hexdigest()
    report=normalize_narration(src,dst,offset_seconds=.5,duration_seconds=4)
    assert hashlib.sha256(src.read_bytes()).hexdigest()==before
    import array
    pcm=subprocess.check_output(['ffmpeg','-v','error','-i',str(dst),'-f','f32le','-ac','1','-ar','44100','-'])
    samples=array.array('f',pcm)
    assert abs(len(samples)/44100-4)<.03
    assert max(abs(x) for x in samples[2000:16000])<.001
    assert max(abs(x) for x in samples[30000:50000])>.03
    assert report['policy']['integrated_lufs']==-19
    measured=run('-i',dst,'-af','loudnorm=I=-19:TP=-1.5:LRA=11:print_format=json','-f','null','-').stderr
    import re
    values=json.loads(re.findall(r'\{\s*"input_i".*?\}',measured,re.S)[-1])
    assert abs(float(values['input_i'])+19)<.6
    silent=tmp_path/'silent.wav';run('-f','lavfi','-i','anullsrc=r=44100:cl=mono','-t',2,silent)
    assert normalize_narration(silent,tmp_path/'silent-out.wav')['silent'] is True
    with pytest.raises(ValueError):normalize_narration(src,src)


@pytest.mark.skipif(not shutil.which('ffmpeg'),reason='ffmpeg required')
def test_frontend_preview_preserves_original_and_reuses_derived_audio(tmp_path):
    from server import image_gen_app as app
    src=tmp_path/'assets/audio/voice.wav';src.parent.mkdir(parents=True)
    run('-f','lavfi','-i','sine=frequency=440:duration=2',src)
    target={'cut':{'audio':{'narration':{'output':'assets/audio/voice.wav'}},'render':{'narration_offset_seconds':.5},'video_generation':{'duration_seconds':3}}}
    with patch.object(app,'safe_run_dir',return_value=tmp_path),patch.object(app,'_read_manifest_data',return_value=(tmp_path/'video_manifest.md','',{})),patch.object(app,'_target_by_item_id',return_value=target):
        raw=asyncio.run(app.api_audio_file('run','assets/audio/voice.wav'))
        preview=asyncio.run(app.api_audio_file('run','assets/audio/voice.wav',preview_item='scene1_cut1'))
        assert Path(raw.path)==src
        assert Path(preview.path)!=src and Path(preview.path).is_file()
        mtime=Path(preview.path).stat().st_mtime_ns
        again=asyncio.run(app.api_audio_file('run','assets/audio/voice.wav',preview_item='scene1_cut1'))
        assert Path(again.path).stat().st_mtime_ns==mtime
        target['cut']['audio']['narration']['tool'] = 'silent'
        silent_preview = asyncio.run(app.api_audio_file('run','assets/audio/voice.wav',preview_item='scene1_cut1'))
        assert Path(silent_preview.path) == src  # Do not add a lead-in to intentional silence.
