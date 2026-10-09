"""p860: approved-video-bound BGM/SE proposals, candidates and render handoff.

Writers hold the server's run_artifacts lock; provider work uses immutable requests.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from toc.http import request_bytes
from toc.run_root_binding import read_run_file_bytes, write_run_file_text

ARTIFACT = "sound_design.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts:
        raise ValueError("sound path must be run-relative")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("sound path escapes the run")
    return resolved


def load(root: Path) -> dict[str, Any]:
    try:
        result = json.loads(read_run_file_bytes(root, ARTIFACT))
    except FileNotFoundError:
        return {}
    if not isinstance(result, dict) or result.get("schema_version") != "sound_design_v1":
        raise ValueError("invalid sound design schema")
    return result


def write_json(root: Path, relative: str, value: dict[str, Any]) -> None:
    safe_path(root, relative)
    write_run_file_text(root, relative, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def save(root: Path, plan: dict[str, Any]) -> None:
    plan["revision"] = int(plan.get("revision", 0)) + 1
    plan["updated_at"] = now()
    write_json(root, ARTIFACT, plan)


class MixChannel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra='forbid')
    volume_db: float = Field(default=0, ge=-60, le=36)
    muted: bool = False


class MixSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    narration: MixChannel = Field(default_factory=MixChannel)
    se: MixChannel = Field(default_factory=MixChannel)
    bgm: MixChannel = Field(default_factory=MixChannel)


def channel_gain(channel: MixChannel, cue_db: float = 0) -> float:
    return 0.0 if channel.muted else 10 ** ((channel.volume_db + cue_db) / 20)


class CueSettings(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    prompt: str = Field(min_length=1, max_length=4100)
    generation_duration_seconds: float = Field(ge=0.5, le=600)
    start_seconds: float = Field(ge=0, le=86400)
    duration_seconds: float = Field(gt=0, le=86400)
    volume_db: float = Field(default=-18, ge=-60, le=36)
    fade_in_seconds: float = Field(default=0, ge=0, le=60)
    fade_out_seconds: float = Field(default=0, ge=0, le=60)
    loop: bool = False
    enabled: bool = False
    selected_candidate_id: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_fades(self):
        if not self.prompt.strip():
            raise ValueError("生成指示を入力してください")
        if self.fade_in_seconds + self.fade_out_seconds > self.duration_seconds:
            raise ValueError("フェードの合計は再生時間以内にしてください")
        return self


class NativeAudioSettings(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    enabled: bool = False
    volume_db: float = Field(default=0, ge=-60, le=36)
    fade_in_seconds: float = Field(default=0, ge=0, le=60)
    fade_out_seconds: float = Field(default=0, ge=0, le=60)
    overlap_policy: str = "preserve"

    @model_validator(mode="after")
    def validate_overlap_policy(self):
        if self.overlap_policy not in {"preserve", "duck_narration"}:
            raise ValueError("invalid dialogue overlap policy")
        return self


def provider_request(cue: dict[str, Any]) -> dict[str, Any]:
    settings = CueSettings.model_validate(cue)
    duration = settings.generation_duration_seconds
    if cue["kind"] == "bgm":
        if duration < 3:
            raise ValueError("BGMの生成尺は3〜600秒です")
        return {"endpoint": "music", "output_format": "mp3_44100_128", "payload": {
            "prompt": settings.prompt, "music_length_ms": round(duration * 1000),
            "model_id": "music_v2_5", "force_instrumental": True,
        }}
    if cue["kind"] != "se" or duration > 30:
        raise ValueError("SEの生成尺は0.5〜30秒です")
    return {"endpoint": "sound-generation", "output_format": "mp3_44100_128", "payload": {
        "text": settings.prompt, "duration_seconds": duration,
        "model_id": "eleven_text_to_sound_v2", "loop": settings.loop,
        "prompt_influence": 0.3,
    }}


def request_hash(cue: dict[str, Any]) -> str:
    return digest(provider_request(cue))


def generate_audio(request: dict[str, Any]) -> bytes:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise ValueError("ELEVENLABS_API_KEY が設定されていません")
    if request["endpoint"] not in {"music", "sound-generation"}:
        raise ValueError("unsupported sound endpoint")
    base = os.environ.get("ELEVENLABS_API_BASE", "https://api.elevenlabs.io/v1").rstrip("/")
    return request_bytes(url=f"{base}/{request['endpoint']}?output_format=mp3_44100_128",
                         method="POST", headers={"xi-api-key": key, "content-type": "application/json", "accept": "audio/mpeg"},
                         json_payload=request["payload"], timeout_seconds=600)


def approve(context: dict[str, Any], *, actor: str) -> dict[str, Any]:
    duration = float(context["duration_seconds"])
    if not context.get("videos") or duration <= 0:
        raise ValueError("承認できる動画がありません")
    cues: list[dict[str, Any]] = []
    native_tracks = []
    for video in context["videos"]:
        mode = video.get("native_audio_mode", "off")
        native_tracks.append({"item_id": video["item_id"], "mode": mode,
                              "available": bool(video.get("audio_stream")),
                              "audio_stream": video.get("audio_stream"),
                                  "path": video["path"], "source_video_sha256": video.get("sha256", ""),
                              "candidate_revision": video.get("candidate_revision"),
                              "start_seconds": video["start_seconds"],
                              "duration_seconds": video["duration_seconds"],
                              "enabled": bool(mode != "off" and video.get("audio_stream")),
                              "volume_db": 0.0, "fade_in_seconds": 0.0, "fade_out_seconds": 0.0,
                              "overlap_policy": "preserve"})
    return {"schema_version": "sound_design_v1", "status": "draft", "revision": 0,
            "video_approval": {"video_set_hash": context["video_set_hash"], "actor": actor, "at": now(), "videos": context["videos"]},
            "duration_seconds": duration, "cues": cues, "native_tracks": native_tracks,
            "mix": MixSettings().model_dump()}


def require_current(plan: dict[str, Any], context: dict[str, Any]) -> None:
    if not context.get("video_set_hash") or plan.get("video_approval", {}).get("video_set_hash") != context["video_set_hash"]:
        raise ValueError("現在の動画・尺を承認してからBGM・SEを設定してください")


def get_cue(plan: dict[str, Any], cue_id: str) -> dict[str, Any]:
    for cue in plan.get("cues", []):
        if cue["id"] == cue_id:
            return cue
    raise ValueError("BGM・SEの候補案が見つかりません")


def selected_candidate(root: Path, cue: dict[str, Any]) -> dict[str, Any]:
    candidate = next((c for c in cue.get("candidates", []) if c["id"] == cue.get("selected_candidate_id")), None)
    if not candidate or candidate.get("status") != "completed" or candidate.get("request_hash") != request_hash(cue):
        raise ValueError("現在の生成指示に対応する音声候補を採用してください")
    path = safe_path(root, candidate["path"])
    if not path.is_file() or file_hash(path) != candidate["sha256"]:
        raise ValueError("採用した音声ファイルが変更または削除されています")
    return candidate


def update_cue(root: Path, plan: dict[str, Any], cue_id: str, settings: CueSettings) -> None:
    cue = get_cue(plan, cue_id)
    updated = {**cue, **settings.model_dump()}
    provider_request(updated)
    if settings.start_seconds + settings.duration_seconds > float(plan["duration_seconds"]) + 0.001:
        raise ValueError("BGM・SEの終了位置は動画全体の尺以内にしてください")
    if request_hash(updated) != request_hash(cue):
        updated.update(selected_candidate_id=None, enabled=False)
    if updated["enabled"]:
        selected_candidate(root, updated)
    if all(cue.get(key) == updated.get(key) for key in CueSettings.model_fields):
        return
    cue.update(updated)
    plan["status"] = "draft"


def update_native_track(plan: dict[str, Any], item_id: str, settings: NativeAudioSettings) -> None:
    track = next((t for t in plan.get("native_tracks", []) if t.get("item_id") == item_id), None)
    if track is None:
        raise ValueError("動画の音声設定が見つかりません")
    if settings.enabled and (track.get("mode") == "off" or not track.get("available")):
        raise ValueError("この動画に採用できるネイティブ音声がありません")
    if settings.fade_in_seconds + settings.fade_out_seconds > float(track["duration_seconds"]):
        raise ValueError("フェードの合計は再生時間以内にしてください")
    track.update(settings.model_dump())
    plan["status"] = "draft"


def render_plan(root: Path, plan: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    require_current(plan, context)
    if plan.get("status") != "completed":
        raise ValueError("p860でBGM・SEの設定を確定してください")
    tracks = []
    for cue in plan["cues"]:
        settings = CueSettings.model_validate(cue)
        if not settings.enabled:
            continue
        candidate = selected_candidate(root, cue)
        if settings.start_seconds + settings.duration_seconds > context["duration_seconds"] + 0.001:
            raise ValueError("BGM・SEの終了位置が動画の尺を超えています")
        tracks.append({"cue_id": cue["id"], "kind": cue["kind"], **settings.model_dump(),
                       "path": candidate["path"], "sha256": candidate["sha256"]})
    native_tracks = []
    current_videos = {video["item_id"]: video for video in context["videos"]}
    for track in plan.get("native_tracks", []):
        settings = NativeAudioSettings.model_validate(track)
        if not settings.enabled:
            continue
        video = current_videos.get(track["item_id"])
        if (video is None or track.get("mode") == "off" or not track.get("audio_stream")
                or not video.get("audio_stream")
                or track.get("path") != video.get("path")
                or track.get("source_video_sha256") != video.get("sha256")
                or track.get("candidate_revision") != video.get("candidate_revision")
                or track.get("audio_stream") != video.get("audio_stream")):
            raise ValueError("採用した動画音声の候補・ストリームが変更されています")
        if settings.fade_in_seconds + settings.fade_out_seconds > float(track["duration_seconds"]):
            raise ValueError("フェードの合計は再生時間以内にしてください")
        native_tracks.append({"item_id": track["item_id"], "mode": track["mode"],
                              "path": track["path"], "sha256": track["source_video_sha256"],
                              "source_video_sha256": track["source_video_sha256"],
                              "stream_index": int(track["audio_stream"]["index"]),
                              "stream_identity": track["audio_stream"]["identity"],
                              "relative_audio_start_seconds": float(track["audio_stream"].get("relative_audio_start_seconds", 0.0)),
                              "timing_identity": track["audio_stream"].get("timing_identity"),
                              "candidate_revision": track.get("candidate_revision"),
                              "start_seconds": float(track["start_seconds"]),
                              "duration_seconds": float(track["duration_seconds"]),
                              **settings.model_dump()})
    result = {"schema_version": "sound_render_v1", "run_dir": str(root.resolve()),
              "video_set_hash": context["video_set_hash"], "duration_seconds": context["duration_seconds"],
              "tracks": tracks, "mix": MixSettings.model_validate(plan.get('mix', {})).model_dump()}
    if native_tracks:
        result["native_tracks"] = native_tracks
    result["sound_hash"] = digest(result)
    return result


def probe_audio(path: Path) -> float:
    result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_type:format=duration", "-of", "json", str(path)],
                            check=True, capture_output=True, text=True, timeout=30)
    data = json.loads(result.stdout)
    duration = float(data.get("format", {}).get("duration", 0))
    if not data.get("streams") or not math.isfinite(duration) or duration <= 0:
        raise ValueError("生成された音声をデコードできません")
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-f", "null", "-"],
                   check=True, capture_output=True, timeout=180)
    return duration


def probe_audio_stream(path: Path) -> dict[str, Any] | None:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "stream=index,codec_type,codec_name,channels,sample_rate,channel_layout,start_time,duration:stream_tags=language",
                             "-of", "json", str(path)], check=True, capture_output=True, text=True, timeout=30)
    all_streams = json.loads(result.stdout).get("streams", [])
    streams = [stream for stream in all_streams if stream.get("codec_type") == "audio"]
    if not streams:
        return None
    stream = streams[0]
    video_stream = next((candidate for candidate in all_streams if candidate.get("codec_type") == "video"), {})
    def stream_time(value: Any) -> float:
        try:
            parsed = float(value or 0)
            return parsed if math.isfinite(parsed) else 0.0
        except (TypeError, ValueError):
            return 0.0
    relative_start = stream_time(stream.get("start_time")) - stream_time(video_stream.get("start_time"))
    identity_fields = {key: stream.get(key) for key in
                       ("index", "codec_name", "channels", "sample_rate", "channel_layout", "start_time", "duration")}
    identity_fields["language"] = stream.get("tags", {}).get("language")
    identity = digest(identity_fields)
    timing_identity = digest({"stream_identity": identity, "relative_audio_start_seconds": relative_start,
                              "video_start_time": stream_time(video_stream.get("start_time"))})
    return {"index": int(stream["index"]), "identity": identity, **identity_fields,
            "relative_audio_start_seconds": relative_start, "timing_identity": timing_identity}


def mix_audio(plan: dict[str, Any], narration_list: Path, output: Path) -> None:
    """Mix a frozen p910 snapshot. Paths never enter the filter graph."""
    if plan.get("schema_version") != "sound_render_v1":
        raise ValueError("invalid sound render schema")
    expected = plan.get("sound_hash")
    if expected != digest({k: v for k, v in plan.items() if k != "sound_hash"}):
        raise ValueError("sound render snapshot changed")
    mix = MixSettings.model_validate(plan.get('mix', {}))
    root = Path(plan["run_dir"])
    duration = float(plan["duration_seconds"])
    if not math.isfinite(duration) or not 0 < duration <= 86400:
        raise ValueError("invalid sound timeline duration")
    from toc.narration_audio import normalize_narration
    output.parent.mkdir(parents=True, exist_ok=True)
    normalized = output.with_name(output.stem + "_narration_master.wav")
    normalize_narration(narration_list, normalized, concat=True)
    command = ["ffmpeg", "-hide_banner", "-y", "-i", str(normalized)]
    filters = [f"[0:a]aresample=48000,aformat=channel_layouts=stereo,apad,atrim=duration={duration},asetpts=PTS-STARTPTS,volume={channel_gain(mix.narration)}[narration]"]
    labels = ["[narration]"]
    dialogue_keys = []
    for index, track in enumerate(plan["tracks"], 1):
        settings = CueSettings.model_validate(track)
        # Old snapshots did not contain a kind; unity defaults preserve their output.
        kind = track.get('kind', 'se')
        if kind not in {'se', 'bgm'}:
            raise ValueError('invalid sound track kind')
        gain = channel_gain(getattr(mix, kind), settings.volume_db)
        path = safe_path(root, track["path"])
        if file_hash(path) != track["sha256"]:
            raise ValueError("sound render input changed")
        if settings.loop:
            command += ["-stream_loop", "-1"]
        command += ["-i", str(path)]
        chain = (f"[{index}:a]aresample=48000,aformat=channel_layouts=stereo,"
                 f"apad,atrim=duration={settings.duration_seconds},asetpts=PTS-STARTPTS,volume={gain}")
        if settings.fade_in_seconds:
            chain += f",afade=t=in:st=0:d={settings.fade_in_seconds}"
        if settings.fade_out_seconds:
            chain += f",afade=t=out:st={settings.duration_seconds - settings.fade_out_seconds}:d={settings.fade_out_seconds}"
        chain += f",adelay={round(settings.start_seconds * 1000)}:all=1[s{index}]"
        filters.append(chain)
        labels.append(f"[s{index}]")
    next_native_input = 1 + len(plan["tracks"])
    for offset, track in enumerate(plan.get("native_tracks", [])):
        path = safe_path(root, track["path"])
        if file_hash(path) != track["sha256"] or track.get("source_video_sha256") != track["sha256"]:
            raise ValueError("native audio render input changed")
        stream = probe_audio_stream(path)
        if stream is None or stream["index"] != int(track["stream_index"]) or stream["identity"] != track["stream_identity"]:
            raise ValueError("native audio stream identity changed")
        relative_start = float(track.get("relative_audio_start_seconds", 0.0))
        if not math.isfinite(relative_start):
            raise ValueError("invalid native audio relative start")
        if ("relative_audio_start_seconds" in track
                and not math.isclose(relative_start, float(stream.get("relative_audio_start_seconds", 0.0)), abs_tol=0.000001)):
            raise ValueError("native audio relative start changed")
        if track.get("timing_identity") and track["timing_identity"] != stream.get("timing_identity"):
            raise ValueError("native audio timing identity changed")
        start = float(track["start_seconds"])
        length = float(track["duration_seconds"])
        volume = float(track["volume_db"])
        fade_in = float(track["fade_in_seconds"])
        fade_out = float(track["fade_out_seconds"])
        if not all(math.isfinite(value) for value in (start, length, volume, fade_in, fade_out)) or start < 0 or length <= 0 or start + length > duration + 0.001:
            raise ValueError("invalid native audio timeline")
        trim_start = max(0.0, -relative_start)
        audio_length = max(0.0, length - max(0.0, relative_start))
        if audio_length <= 0:
            continue
        placement_start = start + max(0.0, relative_start)
        index = next_native_input
        next_native_input += 1
        command += ["-i", str(path)]
        chain = (f"[{index}:{int(track['stream_index'])}]aresample=48000,aformat=channel_layouts=stereo,"
                 f"asetpts=PTS-STARTPTS,atrim=start_sample={round(trim_start * 48000)}:duration={audio_length},"
                 f"asetpts=PTS-STARTPTS,volume={channel_gain(mix.se, volume)}")
        if fade_in:
            chain += f",afade=t=in:st=0:d={fade_in}"
        if fade_out:
            chain += f",afade=t=out:st={audio_length - fade_out}:d={fade_out}"
        chain += f",apad=whole_dur={duration},adelay={round(placement_start * 1000)}:all=1[n{offset}]"
        filters.append(chain)
        if track.get("mode") == "dialogue_and_sound" and track.get("overlap_policy") == "duck_narration":
            filters.append(f"[n{offset}]asplit=2[nf{offset}][nk{offset}]")
            labels.append(f"[nf{offset}]")
            dialogue_keys.append(f"[nk{offset}]")
        else:
            labels.append(f"[n{offset}]")
    if dialogue_keys:
        key_label = "dialogue_key"
        if len(dialogue_keys) > 1:
            filters.append("".join(dialogue_keys) + f"amix=inputs={len(dialogue_keys)}:duration=first:normalize=0[{key_label}]")
        else:
            key_label = dialogue_keys[0][1:-1]
        filters.append(f"[narration][{key_label}]sidechaincompress=threshold=0.025:ratio=4:attack=100:release=500[ducked_narration]")
        labels[0] = "[ducked_narration]"
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:duration=first:normalize=0,alimiter=limit=0.95:level=0:latency=1,atrim=duration={duration}[mix]")
    command += ["-filter_complex", ";".join(filters), "-map", "[mix]", "-t", str(duration), "-c:a", "aac", "-b:a", "192k", str(output)]
    subprocess.run(command, check=True, capture_output=True, timeout=1800)
    if abs(probe_audio(output) - duration) > 0.2:
        raise ValueError("mixed sound duration differs from the approved video timeline")
