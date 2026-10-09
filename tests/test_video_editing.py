import array
import hashlib
import json
import shutil
import subprocess

import pytest

from toc.video_editing import (
    VideoEditSettings,
    create_video_edit,
    list_video_edits,
    verify_video_edit,
)


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg/ffprobe required",
)


def ffmpeg(*args):
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)],
        check=True,
        capture_output=True,
    )


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_source(root):
    source = root / "source.mp4"
    ffmpeg(
        "-f", "lavfi", "-i", "color=c=red:s=160x90:r=24:d=3",
        "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=3",
        "-map", "0:v:0", "-map", "1:a:0", "-t", "3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", source,
    )
    return source


def test_real_ffmpeg_trim_color_audio_and_immutable_receipt(tmp_path):
    source = make_source(tmp_path)
    original = source.read_bytes()
    receipt = create_video_edit(
        tmp_path,
        item_id="scene1_cut1.1",
        source_path="source.mp4",
        source_sha256=digest(source),
        request_revision="request-rev-1",
        settings=VideoEditSettings(
            start_seconds=0.5,
            duration_seconds=1.5,
            brightness=0.1,
            saturation=0,
            fade_in_seconds=0.2,
            fade_out_seconds=0.2,
        ),
    )

    output = tmp_path / receipt["output_path"]
    assert source.read_bytes() == original
    assert receipt["source_sha256"] == digest(source)
    assert receipt["output_sha256"] == digest(output)
    assert receipt["request_revision"] == "request-rev-1"
    assert receipt["streams"]["video"] is True
    assert receipt["streams"]["audio"] is True
    assert abs(receipt["actual_duration_seconds"] - 1.5) <= 1 / 24 + 0.001

    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(output)
    ]))
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    audio = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert abs(float(video["duration"]) - 1.5) <= 1 / 24 + 0.001
    assert abs(float(audio["duration"]) - 1.5) <= 0.08

    # The red source becomes neutral gray after saturation is removed; brightness lifts it.
    frame = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(output), "-vf", "select=eq(n\\,8)",
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ])
    pixel = frame[(45 * 160 + 80) * 3:(45 * 160 + 80) * 3 + 3]
    assert max(pixel) - min(pixel) < 8
    assert sum(pixel) > 80

    audio_samples = array.array("f", subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(output), "-vn", "-f", "f32le",
        "-ac", "1", "-ar", "48000", "-",
    ]))
    assert max(abs(sample) for sample in audio_samples[:4000]) < 0.2  # audio fade-in
    assert max(abs(sample) for sample in audio_samples[12000:48000]) > 0.05
    assert max(abs(sample) for sample in audio_samples[-4000:]) < 0.2  # audio fade-out

    assert receipt["output_path"].startswith("assets/test/video_edits/scene1_cut1.1/")
    verified = verify_video_edit(tmp_path, receipt["output_path"], request_revision="request-rev-1")
    assert verified["output_sha256"] == receipt["output_sha256"]
    listed = list_video_edits(tmp_path, "scene1_cut1.1")
    assert len(listed) == 1 and listed[0]["is_stale"] is False


def test_source_path_escape_and_stale_hash_rejected(tmp_path):
    source = make_source(tmp_path)
    with pytest.raises(ValueError, match="run-relative"):
        create_video_edit(tmp_path, item_id="item", source_path="../source.mp4",
                          source_sha256=digest(source), request_revision="rev",
                          settings=VideoEditSettings(start_seconds=0, duration_seconds=1))
    with pytest.raises(ValueError, match="source hash"):
        create_video_edit(tmp_path, item_id="item", source_path="source.mp4",
                          source_sha256="0" * 64, request_revision="rev",
                          settings=VideoEditSettings(start_seconds=0, duration_seconds=1))


@pytest.mark.parametrize("data", [
    {"start_seconds": -0.1, "duration_seconds": 1},
    {"start_seconds": 0, "duration_seconds": 0},
    {"start_seconds": 0, "duration_seconds": 601},
    {"start_seconds": 0, "duration_seconds": 1, "brightness": 0.26},
    {"start_seconds": 0, "duration_seconds": 1, "contrast": 2.1},
    {"start_seconds": 0, "duration_seconds": 1, "saturation": -0.1},
    {"start_seconds": 0, "duration_seconds": 1, "gamma": 2.1},
    {"start_seconds": 0, "duration_seconds": 1, "fade_in_seconds": 1.1},
    {"start_seconds": 0, "duration_seconds": 1, "fade_out_seconds": float("nan")},
    {"start_seconds": 0, "duration_seconds": float("inf")},
])
def test_settings_reject_invalid_bounds_and_nonfinite_numbers(data):
    with pytest.raises((ValueError, TypeError)):
        VideoEditSettings.model_validate(data)


def test_edit_path_escape_and_output_tampering_are_rejected(tmp_path):
    source = make_source(tmp_path)
    receipt = create_video_edit(
        tmp_path, item_id="item", source_path="source.mp4", source_sha256=digest(source),
        request_revision="rev", settings=VideoEditSettings(start_seconds=0, duration_seconds=1),
    )
    with pytest.raises(ValueError, match="run-relative"):
        verify_video_edit(tmp_path, "../outside.json")
    assert verify_video_edit(tmp_path, receipt["output_path"])["receipt_path"] == receipt["receipt_path"]
    (tmp_path / receipt["output_path"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="output hash"):
        verify_video_edit(tmp_path, receipt["receipt_path"])


def test_receipt_uuid_and_item_folder_binding_is_strict(tmp_path):
    source = make_source(tmp_path)
    receipt = create_video_edit(
        tmp_path, item_id="item", source_path="source.mp4", source_sha256=digest(source),
        request_revision="rev", settings=VideoEditSettings(start_seconds=0, duration_seconds=1),
    )
    candidate_path = tmp_path / receipt["output_path"]
    mismatched_receipt = candidate_path.with_name("00000000-0000-0000-0000-000000000000.json")
    mismatched_receipt.write_text(json.dumps({**receipt, "receipt_path": None}), encoding="utf-8")
    with pytest.raises(ValueError, match="UUID and item folder"):
        verify_video_edit(tmp_path, mismatched_receipt.relative_to(tmp_path).as_posix())


def test_symlinked_video_edit_directory_is_rejected(tmp_path):
    source = make_source(tmp_path)
    create_video_edit(
        tmp_path, item_id="item", source_path="source.mp4", source_sha256=digest(source),
        request_revision="rev", settings=VideoEditSettings(start_seconds=0, duration_seconds=1),
    )
    actual = tmp_path / "assets/test/video_edits/item"
    alternate = tmp_path / "alternate"
    alternate.mkdir()
    actual.rename(tmp_path / "actual")
    actual.symlink_to(alternate, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        list_video_edits(tmp_path, "item")


def test_listing_marks_changed_source_stale(tmp_path):
    source = make_source(tmp_path)
    create_video_edit(
        tmp_path, item_id="item", source_path="source.mp4", source_sha256=digest(source),
        request_revision="rev", settings=VideoEditSettings(start_seconds=0, duration_seconds=1),
    )
    source.write_bytes(source.read_bytes() + b"changed")
    listed = list_video_edits(tmp_path, "item")
    assert listed[0]["is_stale"] is True


def test_derived_edit_verification_recurses_to_original_source(tmp_path):
    source = make_source(tmp_path)
    first = create_video_edit(
        tmp_path, item_id="scene1_cut1.1", source_path="source.mp4", source_sha256=digest(source),
        request_revision="rev-1", settings=VideoEditSettings(start_seconds=0, duration_seconds=2),
    )
    first_output = tmp_path / first["output_path"]
    second = create_video_edit(
        tmp_path, item_id="scene1_cut1.1", source_path=first["output_path"],
        source_sha256=digest(first_output), request_revision="rev-1",
        settings=VideoEditSettings(start_seconds=0.25, duration_seconds=1),
    )
    assert verify_video_edit(tmp_path, second["output_path"], request_revision="rev-1")["output_sha256"] == second["output_sha256"]
    source.write_bytes(source.read_bytes() + b"original-source-changed")
    with pytest.raises(ValueError, match="source is stale"):
        verify_video_edit(tmp_path, second["output_path"], request_revision="rev-1")


def test_delayed_native_audio_offset_survives_trim_inside_leading_silence(tmp_path):
    source = tmp_path / "delayed-audio.mp4"
    ffmpeg(
        "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=24:d=4",
        "-itsoffset", "0.5", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000:duration=3.5",
        "-map", "0:v:0", "-map", "1:a:0", "-t", "4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", source,
    )
    before = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(source)
    ]))
    audio_start = float(next(s for s in before["streams"] if s["codec_type"] == "audio")["start_time"])
    assert audio_start >= 0.45

    receipt = create_video_edit(
        tmp_path, item_id="scene1_cut1.2", source_path="delayed-audio.mp4", source_sha256=digest(source),
        request_revision="rev", settings=VideoEditSettings(start_seconds=0.25, duration_seconds=1.5),
    )
    output = tmp_path / receipt["output_path"]
    after = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)
    ]))
    video_start = float(next(s for s in after["streams"] if s["codec_type"] == "video")["start_time"])
    audio_output_start = float(next(s for s in after["streams"] if s["codec_type"] == "audio")["start_time"])
    assert audio_output_start - video_start == pytest.approx(audio_start - 0.25, abs=0.04)

    samples = array.array("f", subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(output), "-vn", "-af", "aresample=async=1:first_pts=0",
        "-f", "f32le", "-ac", "1", "-ar", "48000", "-",
    ]))

    def rms(start, end):
        block = samples[int(start * 48000):int(end * 48000)]
        return (sum(value * value for value in block) / len(block)) ** 0.5

    assert rms(0.02, 0.15) < 0.01
    assert rms(0.35, 0.45) > 0.05


def test_nonzero_container_timeline_is_normalized_on_video_origin(tmp_path):
    source = tmp_path / "shifted.mp4"
    ffmpeg(
        "-f", "lavfi", "-i", "color=c=green:s=160x90:r=24:d=3",
        "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=48000:duration=3",
        "-map", "0:v:0", "-map", "1:a:0", "-t", "3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-output_ts_offset", "5", source,
    )
    source_probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(source)
    ]))
    assert all(float(stream["start_time"]) >= 4.9 for stream in source_probe["streams"])

    receipt = create_video_edit(
        tmp_path, item_id="shifted.1", source_path="shifted.mp4", source_sha256=digest(source),
        request_revision="rev", settings=VideoEditSettings(start_seconds=0.5, duration_seconds=1),
    )
    output = tmp_path / receipt["output_path"]
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)
    ]))
    assert abs(float(next(s for s in probe["streams"] if s["codec_type"] == "video")["duration"]) - 1) <= 1 / 24 + 0.001
    assert abs(float(next(s for s in probe["streams"] if s["codec_type"] == "audio")["duration"]) - 1) <= 0.08
    assert verify_video_edit(tmp_path, receipt["output_path"], request_revision="rev")["output_sha256"] == receipt["output_sha256"]


@pytest.mark.parametrize("start_seconds,duration_seconds", [(0, 0.25), (2, 0.5)])
def test_trim_without_audio_overlap_keeps_silent_audio_stream(tmp_path, start_seconds, duration_seconds):
    source = tmp_path / "short-audio.mp4"
    ffmpeg(
        "-f", "lavfi", "-i", "color=c=black:s=160x90:r=24:d=4",
        "-itsoffset", "0.5", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.5",
        "-map", "0:v:0", "-map", "1:a:0", "-t", "4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", source,
    )
    receipt = create_video_edit(
        tmp_path, item_id=f"silent-{start_seconds}", source_path="short-audio.mp4", source_sha256=digest(source),
        request_revision="rev", settings=VideoEditSettings(start_seconds=start_seconds, duration_seconds=duration_seconds),
    )
    output = tmp_path / receipt["output_path"]
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(output)
    ]))
    audio = next(stream for stream in probe["streams"] if stream["codec_type"] == "audio")
    assert abs(float(audio["duration"]) - duration_seconds) <= 0.08
    samples = array.array("f", subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(output), "-vn", "-af", "aresample=async=1:first_pts=0",
        "-f", "f32le", "-ac", "1", "-ar", "48000", "-",
    ]))
    assert samples and max(abs(value) for value in samples) < 0.01
