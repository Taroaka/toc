import array
import json
import math
from pathlib import Path
import shutil
import subprocess

import pytest

from toc import sound_design as sound


pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg/ffprobe required")


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)], check=True, capture_output=True)


def magnitude(samples, frequency, start, length=0.2):
    rate = 48000
    window = samples[int(start * rate):int((start + length) * rate)]
    real = sum(value * math.cos(2 * math.pi * frequency * i / rate) for i, value in enumerate(window))
    imaginary = sum(value * math.sin(2 * math.pi * frequency * i / rate) for i, value in enumerate(window))
    return 2 * math.hypot(real, imaginary) / len(window)


def test_real_mix_and_render_keep_duration_loop_bgm_and_place_se(tmp_path):
    narration = tmp_path / "narration.wav"
    bgm = tmp_path / "bgm.wav"
    se = tmp_path / "se.wav"
    ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "4", narration)
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=1:sample_rate=48000", bgm)
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=880:duration=0.5:sample_rate=48000", se)
    narration_list = tmp_path / "narration.txt"
    narration_list.write_text(f"file '{narration}'\n")
    settings = {"prompt": "test", "generation_duration_seconds": 3, "start_seconds": 0, "duration_seconds": 4,
                "volume_db": -12, "fade_in_seconds": 0, "fade_out_seconds": 0,
                "loop": True, "enabled": True, "selected_candidate_id": "test"}
    plan = {"schema_version": "sound_render_v1", "run_dir": str(tmp_path), "duration_seconds": 4, "video_set_hash": "video",
            "tracks": [{**settings, "path": "bgm.wav", "sha256": sound.file_hash(bgm)},
                       {**settings, "path": "se.wav", "sha256": sound.file_hash(se), "start_seconds": 2, "duration_seconds": 0.5, "loop": False, "volume_db": 0}]}
    plan["sound_hash"] = sound.digest(plan)
    output = tmp_path / "mix.m4a"
    sound.mix_audio(plan, narration_list, output)
    assert abs(sound.probe_audio(output) - 4) < 0.1
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(output), "-f", "f32le", "-ac", "1", "-ar", "48000", "-"])
    samples = array.array("f", raw)
    assert magnitude(samples, 220, 0.3) > 0.01
    assert magnitude(samples, 220, 3.3) > 0.01  # One-second BGM is looped through the full video.
    assert magnitude(samples, 880, 0.3) < 0.002
    assert magnitude(samples, 880, 2.1) > 0.05
    assert magnitude(samples, 880, 3.1) < 0.002
    video = tmp_path / "clip.mp4"
    ffmpeg("-f", "lavfi", "-i", "color=c=blue:s=160x90:r=24:d=4", "-an", video)
    clips = tmp_path / "clips.txt"
    clips.write_text(f"file '{video}'\n")
    frozen = tmp_path / "sound.json"
    frozen.write_text(json.dumps(plan))
    final = tmp_path / "final.mp4"
    subprocess.run(["bash", str(Path(__file__).resolve().parents[1] / "scripts/render-video.sh"),
                    "--clip-list", str(clips), "--narration-list", str(narration_list),
                    "--sound-plan", str(frozen), "--out", str(final)], check=True, capture_output=True)
    assert abs(sound.probe_audio(final) - 4) < 0.1


def test_mix_rejects_changed_snapshot_before_ffmpeg(tmp_path):
    with pytest.raises(ValueError, match="snapshot changed"):
        sound.mix_audio({"schema_version": "sound_render_v1", "sound_hash": "wrong"}, tmp_path / "none", tmp_path / "none.m4a")


def test_category_gain_mute_and_preview_use_final_mixer(tmp_path):
    # Three distinguishable frequencies expose cross-channel leakage and ignored gains.
    for name, hz in [('narration', 440), ('se', 880), ('bgm', 220)]:
        ffmpeg('-f', 'lavfi', '-i', f'sine=frequency={hz}:duration=2:sample_rate=48000', tmp_path / f'{name}.wav')
    listing = tmp_path / 'narration.txt'
    listing.write_text(f"file '{tmp_path / 'narration.wav'}'\n")
    settings = {'prompt': 'fixture', 'generation_duration_seconds': 2, 'start_seconds': 0,
                'duration_seconds': 2, 'volume_db': -12, 'enabled': True}
    base = {'schema_version': 'sound_render_v1', 'run_dir': str(tmp_path), 'duration_seconds': 2,
            'video_set_hash': 'fixture', 'tracks': [{**settings, 'kind': kind, 'path': f'{kind}.wav',
                'sha256': sound.file_hash(tmp_path / f'{kind}.wav')} for kind in ['se', 'bgm']]}
    def samples(mix, name):
        plan = {**base, 'mix': mix}
        plan['sound_hash'] = sound.digest(plan)
        output = tmp_path / f'{name}.m4a'
        sound.mix_audio(plan, listing, output)
        return array.array('f', subprocess.check_output(['ffmpeg', '-v', 'error', '-i', str(output),
            '-f', 'f32le', '-ac', '1', '-ar', '48000', '-']))
    normal = samples({}, 'normal')
    changed = samples({'narration': {'muted': True}, 'bgm': {'muted': True}, 'se': {'volume_db': 6}}, 'changed')
    assert magnitude(changed, 440, 0.5) < 0.002
    assert magnitude(changed, 220, 0.5) < 0.002
    assert magnitude(changed, 880, 0.5) / magnitude(normal, 880, 0.5) == pytest.approx(2, rel=0.06)
    silent = samples({k: {'muted': True} for k in ['narration', 'se', 'bgm']}, 'silent')
    assert max(abs(value) for value in silent) < 0.001


def test_native_video_audio_is_mixed_at_video_relative_offset_and_trimmed(tmp_path):
    narration = tmp_path / "narration.wav"
    source = tmp_path / "source.mp4"
    ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "4", narration)
    ffmpeg("-f", "lavfi", "-i", "color=c=black:s=160x90:r=24:d=4",
           "-f", "lavfi", "-i", "sine=frequency=880:duration=4:sample_rate=48000",
           "-map", "0:v:0", "-map", "1:a:0", "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", source)
    listing = tmp_path / "narration.txt"
    listing.write_text(f"file '{narration}'\n")
    stream = sound.probe_audio_stream(source)
    assert stream is not None
    plan = {"schema_version": "sound_render_v1", "run_dir": str(tmp_path), "duration_seconds": 4,
            "video_set_hash": "video", "tracks": [], "native_tracks": [{
                "item_id": "scene1_cut1", "mode": "natural_sound", "path": "source.mp4",
                "sha256": sound.file_hash(source), "source_video_sha256": sound.file_hash(source),
                "stream_index": stream["index"], "stream_identity": stream["identity"],
                "candidate_revision": "candidate-revision", "start_seconds": 1, "duration_seconds": 2.5,
                "enabled": True, "volume_db": 0, "fade_in_seconds": 0, "fade_out_seconds": 0,
                "overlap_policy": "preserve"}]}
    plan["sound_hash"] = sound.digest(plan)
    output = tmp_path / "mixed.m4a"
    sound.mix_audio(plan, listing, output)
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(output), "-f", "f32le", "-ac", "1", "-ar", "48000", "-"])
    samples = array.array("f", raw)
    assert magnitude(samples, 880, 1.2) > 0.05
    assert magnitude(samples, 880, 0.3) < 0.002
    assert magnitude(samples, 880, 3.7) < 0.002
    assert abs(sound.probe_audio(output) - 4) < 0.1


@pytest.mark.parametrize("offset,extension", [(0.5, "mp4"), (-0.5, "mkv")])
def test_native_audio_relative_start_survives_freeze_and_mix(tmp_path, offset, extension):
    source = tmp_path / f"offset-source.{extension}"
    narration = tmp_path / "offset-narration.wav"
    if offset > 0:
        ffmpeg("-f", "lavfi", "-i", "color=c=black:s=160x90:r=24:d=4",
               "-itsoffset", str(offset), "-f", "lavfi", "-i", "sine=frequency=880:duration=3.5:sample_rate=48000",
               "-map", "0:v:0", "-map", "1:a:0", "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", source)
    else:
        ffmpeg("-f", "lavfi", "-i", "color=c=black:s=160x90:r=24:d=4",
               "-itsoffset", str(offset), "-f", "lavfi", "-i", "sine=frequency=880:duration=4.5:sample_rate=48000",
               "-map", "0:v:0", "-map", "1:a:0", "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
               "-avoid_negative_ts", "disabled", source)
    ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "6", narration)
    listing = tmp_path / "offset-narration.txt"
    listing.write_text(f"file '{narration}'\n")
    stream = sound.probe_audio_stream(source)
    assert stream is not None
    if offset > 0:
        assert stream["relative_audio_start_seconds"] == pytest.approx(offset, abs=0.04)
        expected_tone_start = 1 + stream["relative_audio_start_seconds"]
    else:
        assert stream["relative_audio_start_seconds"] < -0.45
        expected_tone_start = 1.0
    video = {"item_id": "scene1_cut1", "path": source.name, "sha256": sound.file_hash(source),
             "start_seconds": 1.0, "duration_seconds": 4.0, "context": "delayed clip audio",
             "native_audio_mode": "natural_sound", "audio_stream": stream, "candidate_revision": "rev-1"}
    context = {"video_set_hash": "sha256:offset-video", "duration_seconds": 6.0, "videos": [video]}
    plan = sound.approve(context, actor="test")
    plan["status"] = "completed"
    snapshot = sound.render_plan(tmp_path, plan, context)
    assert snapshot["native_tracks"][0]["relative_audio_start_seconds"] == pytest.approx(stream["relative_audio_start_seconds"])
    output = tmp_path / f"offset-mix.{extension}.m4a"
    sound.mix_audio(snapshot, listing, output)
    samples = array.array("f", subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(output), "-f", "f32le", "-ac", "1", "-ar", "48000", "-",
    ]))
    assert magnitude(samples, 880, expected_tone_start + 0.15) > 0.05
    assert magnitude(samples, 880, expected_tone_start - 0.2) < 0.002
    assert magnitude(samples, 880, 5.3) < 0.002
    assert abs(sound.probe_audio(output) - 6) < 0.1


@pytest.mark.parametrize("dialogue_count", [1, 2])
def test_dialogue_ducking_splits_tracks_and_keeps_full_timeline(tmp_path, dialogue_count):
    narration = tmp_path / "narration.wav"
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=5:sample_rate=48000", "-t", "5", narration)
    listing = tmp_path / "narration.txt"
    listing.write_text(f"file '{narration}'\n")
    native_tracks = []
    for index in range(dialogue_count):
        source = tmp_path / f"dialogue-{index}.mp4"
        ffmpeg("-f", "lavfi", "-i", "color=c=black:s=160x90:r=24:d=5",
               "-f", "lavfi", "-i", f"sine=frequency={880 + index * 220}:duration=5:sample_rate=48000",
               "-map", "0:v:0", "-map", "1:a:0", "-t", "5", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", source)
        stream = sound.probe_audio_stream(source)
        assert stream is not None
        native_tracks.append({
            "item_id": f"scene1_cut{index + 1}", "mode": "dialogue_and_sound", "path": source.name,
            "sha256": sound.file_hash(source), "source_video_sha256": sound.file_hash(source),
            "stream_index": stream["index"], "stream_identity": stream["identity"],
            "candidate_revision": f"candidate-{index + 1}", "start_seconds": 1 + index * 2,
            "duration_seconds": 1, "enabled": True, "volume_db": 0, "fade_in_seconds": 0,
            "fade_out_seconds": 0, "overlap_policy": "duck_narration",
        })
    plan = {"schema_version": "sound_render_v1", "run_dir": str(tmp_path), "duration_seconds": 5,
            "video_set_hash": "video", "tracks": [], "native_tracks": native_tracks}
    plan["sound_hash"] = sound.digest(plan)
    output = tmp_path / f"dialogue-{dialogue_count}-mix.m4a"
    sound.mix_audio(plan, listing, output)
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(output), "-f", "f32le", "-ac", "1", "-ar", "48000", "-"])
    samples = array.array("f", raw)
    baseline = magnitude(samples, 440, 0.3)
    assert baseline > 0.03
    assert magnitude(samples, 440, 1.2) < baseline * 0.75
    assert magnitude(samples, 440, 2.5) > baseline * 0.75
    if dialogue_count == 2:
        assert magnitude(samples, 440, 3.2) < baseline * 0.75
        assert magnitude(samples, 440, 4.5) > baseline * 0.75
    assert abs(sound.probe_audio(output) - 5) < 0.1
