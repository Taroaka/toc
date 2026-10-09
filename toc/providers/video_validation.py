"""Validate downloaded video before publishing it as a selectable candidate."""
import hashlib
import json
import math
from pathlib import Path
import subprocess


def verify_generated_video(path: Path, *, duration_seconds: float, aspect_ratio: str,
                           require_audio: bool) -> dict:
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                           check=True, capture_output=True, text=True, timeout=30)
    data = json.loads(probe.stdout)
    videos = [row for row in data.get('streams', []) if row.get('codec_type') == 'video']
    if not videos or not videos[0].get('width') or not videos[0].get('height'):
        raise ValueError('generated output has no decodable video stream')
    video = videos[0]
    duration = float(video.get('duration') or data.get('format', {}).get('duration') or 0)
    if not math.isfinite(duration) or abs(duration - duration_seconds) > 0.35:
        raise ValueError('generated video duration does not match the requested duration')
    width, height = (float(v) for v in aspect_ratio.split(':'))
    if abs((video['width'] / video['height']) / (width / height) - 1) > 0.025:
        raise ValueError('generated video aspect ratio does not match the requested ratio')
    audio = [row for row in data.get('streams', []) if row.get('codec_type') == 'audio']
    if require_audio and not audio:
        raise ValueError('generated video is missing requested synchronized audio')
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(path), '-map', '0:v:0',
                    '-map', '0:a?', '-f', 'null', '-'], check=True, capture_output=True, timeout=180)
    sha = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            sha.update(chunk)
    return {'duration_seconds': duration, 'width': video['width'], 'height': video['height'],
            'audio_streams': len(audio), 'sha256': sha.hexdigest()}
