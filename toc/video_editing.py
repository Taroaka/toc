"""Local, immutable ffmpeg-derived video candidates."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ITEM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_FFPROBE_TIMEOUT_SECONDS = 60
_FFMPEG_TIMEOUT_SECONDS = 1800


class VideoEditSettings(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")

    start_seconds: float = Field(ge=0)
    duration_seconds: float = Field(gt=0, le=600)
    brightness: float = Field(default=0, ge=-0.25, le=0.25)
    contrast: float = Field(default=1, ge=0.5, le=2)
    saturation: float = Field(default=1, ge=0, le=2)
    gamma: float = Field(default=1, ge=0.5, le=2)
    fade_in_seconds: float = Field(default=0, ge=0)
    fade_out_seconds: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def fades_fit_duration(self):
        if self.fade_in_seconds > self.duration_seconds or self.fade_out_seconds > self.duration_seconds:
            raise ValueError("video fades must not exceed duration_seconds")
        return self


def _safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("video edit path must be run-relative")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("video edit path must be run-relative")
    base = root.resolve()
    lexical = base / candidate
    current = base
    for part in candidate.parts:
        current = current / part
        try:
            current.lstat()
        except FileNotFoundError:
            continue
        if current.is_symlink():
            raise ValueError("video edit paths must not contain symlinks")
    resolved = lexical.resolve()
    if not resolved.is_relative_to(base):
        raise ValueError("video edit path escapes the run")
    return resolved


def _reject_symlink_components(root: Path, path: Path, *, include_leaf: bool = True) -> None:
    """Require every existing path component to be an ordinary non-symlink entry."""
    relative = path.relative_to(root)
    parts = relative.parts if include_leaf else relative.parts[:-1]
    current = root
    for part in parts:
        current = current / part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            continue
        if current.is_symlink():
            raise ValueError("video edit paths must not contain symlinks")
        if current != path and not current.is_dir():
            raise ValueError("video edit parent path must be a directory")
        if current == path and not (current.is_file() or current.is_dir()):
            raise ValueError("video edit artifact must be a regular file")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        check=True, capture_output=True, text=True, timeout=_FFPROBE_TIMEOUT_SECONDS,
    )
    try:
        data = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("ffprobe returned malformed media data") from exc
    streams = data.get("streams")
    if not isinstance(streams, list):
        raise ValueError("ffprobe returned no stream list")
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if video is None:
        raise ValueError("video edit source must contain a video stream")

    def duration_of(stream: dict[str, Any] | None) -> float | None:
        candidates = [stream.get("duration") if stream else None, data.get("format", {}).get("duration")]
        for value in candidates:
            try:
                duration = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(duration) and duration > 0:
                return duration
        return None

    duration = duration_of(video)
    if duration is None:
        raise ValueError("video stream duration is unavailable")
    frame_rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "24/1"
    try:
        numerator, denominator = (float(part) for part in frame_rate.split("/", 1))
        frame_seconds = numerator and denominator and denominator / numerator
        if not frame_seconds or not math.isfinite(frame_seconds):
            raise ValueError
    except (ValueError, ZeroDivisionError):
        frame_seconds = 1 / 24
    return {
        "duration_seconds": duration,
        "frame_seconds": float(frame_seconds),
        "video_start_time": _finite_float(video.get("start_time"), 0.0),
        "video": video,
        "audio": audio,
        "audio_start_time": _finite_float(audio.get("start_time"), 0.0) if audio else None,
        "audio_duration_seconds": _finite_float(
            audio.get("duration"), _finite_float(data.get("format", {}).get("duration"), duration)
        ) if audio else None,
        "format_duration_seconds": duration_of(None) or duration,
    }


def _finite_float(value: Any, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _ffnum(value: float) -> str:
    return format(float(value), ".12g")


def _atomic_publish(temp_path: Path, destination: Path) -> None:
    """Publish a same-filesystem file without replacing an existing candidate."""
    try:
        os.link(temp_path, destination)
    except FileExistsError as exc:
        raise ValueError("video edit candidate already exists") from exc
    finally:
        temp_path.unlink(missing_ok=True)


def _atomic_json(destination: Path, record: dict[str, Any]) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=".receipt-", suffix=".tmp", dir=destination.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        _atomic_publish(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def create_video_edit(
    root: Path,
    *,
    item_id: str,
    source_path: str,
    source_sha256: str,
    request_revision: str,
    settings: VideoEditSettings,
) -> dict[str, Any]:
    """Create and verify a new local candidate while leaving source bytes untouched."""
    root = Path(root).resolve()
    if not isinstance(item_id, str) or not _SAFE_ITEM_RE.fullmatch(item_id):
        raise ValueError("item_id must start with a letter or digit and contain only letters, digits, dot, underscore, or dash")
    if not isinstance(request_revision, str) or not request_revision.strip():
        raise ValueError("request_revision is required")
    if not isinstance(settings, VideoEditSettings):
        settings = VideoEditSettings.model_validate(settings)
    if not isinstance(source_sha256, str) or not _SHA256_RE.fullmatch(source_sha256):
        raise ValueError("source hash must be plain lowercase SHA-256 hex")
    source = _safe_path(root, source_path)
    _reject_symlink_components(root, source)
    if not source.is_file() or source.is_symlink():
        raise ValueError("video edit source is not a regular file")
    if _file_hash(source) != source_sha256:
        raise ValueError("source hash does not match current source bytes")

    source_info = _probe(source)
    start = settings.start_seconds
    requested_duration = settings.duration_seconds
    frame_tolerance = source_info["frame_seconds"]
    if start >= source_info["duration_seconds"] + frame_tolerance:
        raise ValueError("video edit trim starts beyond source duration")
    remaining = source_info["duration_seconds"] - start
    if requested_duration > remaining + frame_tolerance:
        raise ValueError("video edit trim exceeds source duration")
    # A one-frame container timestamp discrepancy is accepted, but output still ends at media.
    edit_duration = min(requested_duration, remaining)
    if edit_duration <= 0:
        raise ValueError("video edit trim has no media duration")

    target_dir = root / "assets" / "test" / "video_edits" / item_id
    target_dir.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(root, target_dir)
    if not target_dir.resolve().is_relative_to(root):
        raise ValueError("video edit output directory escapes the run")
    edit_id = str(uuid.uuid4())
    output_name = f"{edit_id}.mp4"
    receipt_name = f"{edit_id}.json"
    output = target_dir / output_name
    receipt_path = target_dir / receipt_name
    fd, temp_name = tempfile.mkstemp(prefix=f".{edit_id}-", suffix=".mp4", dir=target_dir)
    os.close(fd)
    temp_output = Path(temp_name)
    temp_output.unlink()
    video_filters = [
        f"setpts=PTS-{_ffnum(source_info['video_start_time'])}/TB",
        f"trim=start={_ffnum(start)}:duration={_ffnum(edit_duration)}",
        f"setpts=PTS-{_ffnum(start)}/TB",
        "setsar=1",
        "eq=" + ":".join((
            f"brightness={_ffnum(settings.brightness)}",
            f"contrast={_ffnum(settings.contrast)}",
            f"saturation={_ffnum(settings.saturation)}",
            f"gamma={_ffnum(settings.gamma)}",
        )),
    ]
    if settings.fade_in_seconds:
        video_filters.append(f"fade=t=in:st=0:d={_ffnum(settings.fade_in_seconds)}")
    if settings.fade_out_seconds:
        video_filters.append(
            f"fade=t=out:st={_ffnum(max(0, edit_duration - settings.fade_out_seconds))}:d={_ffnum(settings.fade_out_seconds)}"
        )
    filter_graph = f"[0:v:0]{','.join(video_filters)}[v]"
    maps = ["-map", "[v]"]
    has_audio = source_info["audio"] is not None
    audio_overlap = False
    if has_audio:
        audio_start = source_info["audio_start_time"] - source_info["video_start_time"]
        audio_end = audio_start + source_info["audio_duration_seconds"]
        audio_overlap = start < audio_end and start + edit_duration > audio_start
    if has_audio and audio_overlap:
        audio_filters = [
            f"asetpts=PTS-{_ffnum(source_info['video_start_time'])}/TB",
            f"atrim=start={_ffnum(start)}:duration={_ffnum(edit_duration)}",
            f"asetpts=PTS-{_ffnum(start)}/TB",
        ]
        audio_fade_start = max(
            0.0,
            source_info["audio_start_time"] - source_info["video_start_time"] - start,
        )
        if settings.fade_in_seconds:
            audio_filters.append(
                f"afade=t=in:st={_ffnum(audio_fade_start)}:d={_ffnum(settings.fade_in_seconds)}"
            )
        if settings.fade_out_seconds:
            audio_filters.append(
                f"afade=t=out:st={_ffnum(max(0, edit_duration - settings.fade_out_seconds))}:d={_ffnum(settings.fade_out_seconds)}"
            )
        audio_filters.append(f"apad=whole_dur={_ffnum(edit_duration)}")
        filter_graph += f";[0:a:0]{','.join(audio_filters)}[a]"
        maps.extend(["-map", "[a]"])
    elif has_audio:
        channel_layout = source_info["audio"].get("channel_layout")
        if channel_layout not in {"mono", "stereo", "2.1", "3.0", "4.0", "4.1", "5.0", "5.1", "7.1"}:
            channel_layout = "mono" if source_info["audio"].get("channels") == 1 else "stereo"
        sample_rate = source_info["audio"].get("sample_rate")
        sample_rate = str(sample_rate) if isinstance(sample_rate, str) and sample_rate.isdigit() else "48000"
        filter_graph += (
            f";anullsrc=r={sample_rate}:cl={channel_layout},"
            f"atrim=duration={_ffnum(edit_duration)},asetpts=PTS-STARTPTS[a]"
        )
        maps.extend(["-map", "[a]"])
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-copyts", "-i", str(source),
        "-filter_complex", filter_graph, *maps, "-t", _ffnum(edit_duration),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
    ]
    if source_info["audio"] is not None:
        command.extend(["-c:a", "aac", "-b:a", "192k"])
    command.extend(["-movflags", "+faststart", str(temp_output)])
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=_FFMPEG_TIMEOUT_SECONDS)
        output_info = _probe(temp_output)
        if (output_info["audio"] is not None) != (source_info["audio"] is not None):
            raise ValueError("edited candidate audio stream does not match source")
        tolerance = max(frame_tolerance, 0.04)
        if abs(output_info["duration_seconds"] - edit_duration) > tolerance + 0.001:
            raise ValueError("edited candidate duration does not match requested trim")
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-v", "error", "-nostdin", "-i", str(temp_output), "-f", "null", "-"],
            check=True, capture_output=True, timeout=_FFMPEG_TIMEOUT_SECONDS,
        )
        if _file_hash(source) != source_sha256:
            raise ValueError("source hash changed while video edit was processing")
        output_sha256 = _file_hash(temp_output)
        _atomic_publish(temp_output, output)
        record = {
            "schema_version": "video_edit_receipt_v1",
            "item_id": item_id,
            "source_path": source_path,
            "source_sha256": source_sha256,
            "request_revision": request_revision,
            "output_path": output.relative_to(root).as_posix(),
            "output_sha256": output_sha256,
            "settings": settings.model_dump(mode="json"),
            "actual_duration_seconds": output_info["duration_seconds"],
            "streams": {
                "video": True,
                "audio": source_info["audio"] is not None,
                "video_codec": output_info["video"].get("codec_name"),
                "audio_codec": output_info["audio"].get("codec_name") if output_info["audio"] else None,
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_json(receipt_path, record)
        record["receipt_path"] = receipt_path.relative_to(root).as_posix()
        return record
    finally:
        temp_output.unlink(missing_ok=True)


def verify_video_edit(root: Path, path: str, request_revision: str | None = None) -> dict[str, Any]:
    """Verify a candidate by its media or receipt path and reject stale bindings."""
    root = Path(root).resolve()
    requested_path = _safe_path(root, path)
    _reject_symlink_components(root, requested_path)
    if requested_path.suffix.lower() == ".mp4":
        receipt_path = requested_path.with_suffix(".json")
        _reject_symlink_components(root, receipt_path)
    elif requested_path.suffix.lower() == ".json":
        receipt_path = requested_path
    else:
        raise ValueError("video edit path must name an .mp4 candidate or .json receipt")

    def verify_receipt(receipt: Path, visited: set[Path], depth: int) -> dict[str, Any]:
        if depth > 32:
            raise ValueError("video edit lineage exceeds the maximum depth")
        receipt = receipt.resolve()
        if receipt in visited:
            raise ValueError("video edit lineage contains a cycle")
        visited.add(receipt)
        _reject_symlink_components(root, receipt)
        try:
            raw = receipt.read_bytes()
            record = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("video edit receipt is missing or malformed") from exc
        if not isinstance(record, dict) or record.get("schema_version") != "video_edit_receipt_v1":
            raise ValueError("video edit receipt is malformed")
        if not isinstance(record.get("source_sha256"), str) or not _SHA256_RE.fullmatch(record["source_sha256"]):
            raise ValueError("video edit receipt has an invalid source hash")
        if not isinstance(record.get("output_sha256"), str) or not _SHA256_RE.fullmatch(record["output_sha256"]):
            raise ValueError("video edit receipt has an invalid output hash")
        if request_revision is not None and record.get("request_revision") != request_revision:
            raise ValueError("video edit request revision is stale")
        item_id = record.get("item_id")
        if not isinstance(item_id, str) or not _SAFE_ITEM_RE.fullmatch(item_id):
            raise ValueError("video edit receipt has an invalid item_id")
        relative_dir = Path("assets") / "test" / "video_edits" / item_id
        expected_output = relative_dir / f"{receipt.stem}.mp4"
        expected_receipt = relative_dir / f"{receipt.stem}.json"
        try:
            parsed_uuid = uuid.UUID(receipt.stem)
        except ValueError as exc:
            raise ValueError("video edit receipt name must contain its candidate UUID") from exc
        if str(parsed_uuid) != receipt.stem:
            raise ValueError("video edit receipt UUID must be canonical lowercase")
        if receipt.relative_to(root) != expected_receipt or record.get("output_path") != expected_output.as_posix():
            raise ValueError("video edit receipt and output paths do not match the candidate UUID and item folder")
        if depth == 0 and requested_path.suffix.lower() == ".mp4" and requested_path.relative_to(root) != expected_output:
            raise ValueError("video edit media path does not match its receipt")
        source = _safe_path(root, record.get("source_path"))
        output = _safe_path(root, record.get("output_path"))
        _reject_symlink_components(root, source)
        _reject_symlink_components(root, output)
        if not source.is_file() or source.is_symlink() or _file_hash(source) != record["source_sha256"]:
            raise ValueError("video edit source is stale")
        if not output.is_file() or output.is_symlink() or _file_hash(output) != record["output_sha256"]:
            raise ValueError("video edit output hash does not match receipt")

        source_relative = source.relative_to(root)
        if source_relative.parts[:3] == ("assets", "test", "video_edits"):
            if len(source_relative.parts) != 5 or source.suffix.lower() != ".mp4":
                raise ValueError("video edit lineage source path is malformed")
            ancestor = verify_receipt(source.with_suffix(".json"), visited, depth + 1)
            if ancestor.get("output_path") != source_relative.as_posix() or ancestor.get("output_sha256") != record["source_sha256"]:
                raise ValueError("video edit lineage source does not match its ancestor receipt")

        if not isinstance(record.get("settings"), dict) or not isinstance(record.get("streams"), dict):
            raise ValueError("video edit receipt is malformed")
        try:
            VideoEditSettings.model_validate(record["settings"])
        except Exception as exc:
            raise ValueError("video edit receipt settings are malformed") from exc
        return {**record, "receipt_path": receipt.relative_to(root).as_posix()}

    return verify_receipt(receipt_path, set(), 0)


def list_video_edits(root: Path, item_id: str) -> list[dict[str, Any]]:
    """List per-item receipts, marking records stale if a binding no longer matches."""
    if not isinstance(item_id, str) or not _SAFE_ITEM_RE.fullmatch(item_id):
        raise ValueError("item_id must start with a letter or digit and contain only letters, digits, dot, underscore, or dash")
    root = Path(root).resolve()
    directory = _safe_path(root, f"assets/test/video_edits/{item_id}")
    _reject_symlink_components(root, directory)
    if not directory.exists():
        return []
    records = []
    for receipt in sorted(directory.glob("*.json")):
        relative = receipt.relative_to(root).as_posix()
        try:
            record = verify_video_edit(root, relative)
            record["is_stale"] = False
        except ValueError as exc:
            try:
                record = json.loads(receipt.read_text(encoding="utf-8"))
                if not isinstance(record, dict):
                    record = {"receipt_path": relative}
            except (OSError, json.JSONDecodeError):
                record = {"receipt_path": relative}
            record.update(receipt_path=relative, is_stale=True, stale_reason=str(exc))
        records.append(record)
    return records
