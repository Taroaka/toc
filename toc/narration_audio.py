"""Shared narration mastering, independent of TTS providers and story titles."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

POLICY = {'version': 'narration_audio_v1', 'integrated_lufs': -19, 'true_peak_dbtp': -1.5, 'loudness_range_lu': 11, 'sample_rate': 44100}
DEFAULT_LEAD_IN_SECONDS = 0.5


def normalize_narration(source: Path, output: Path, *, concat: bool = False,
                        offset_seconds: float = 0, duration_seconds: float | None = None) -> dict:
    """Two-pass normalize a raw cut or assembled narration; never mutate its source."""
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise ValueError('narration mastering must preserve the original file')
    if not math.isfinite(offset_seconds) or not 0 <= offset_seconds <= 120:
        raise ValueError('invalid narration offset')
    if duration_seconds is not None and (not math.isfinite(duration_seconds) or not 0 < duration_seconds <= 86400):
        raise ValueError('invalid narration duration')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise ValueError('ffmpeg is required for narration mastering')
    inputs = (['-f', 'concat', '-safe', '0'] if concat else []) + ['-i', str(source)]
    chain = f'adelay={offset_seconds * 1000:.3f}:all=1' if offset_seconds else 'anull'
    if duration_seconds is not None:
        chain += f',apad,atrim=duration={duration_seconds:.6f}'
    norm = f"loudnorm=I={POLICY['integrated_lufs']}:TP={POLICY['true_peak_dbtp']}:LRA={POLICY['loudness_range_lu']}"
    measured = subprocess.run([ffmpeg, '-hide_banner', *inputs, '-af', chain + ',' + norm + ':print_format=json', '-f', 'null', '-'], check=True, capture_output=True, text=True, timeout=600)
    blocks = re.findall(r'\{\s*"input_i".*?\}', measured.stderr, re.S)
    if not blocks:
        raise ValueError('narration loudness measurement is unavailable')
    values = json.loads(blocks[-1])
    silent = not math.isfinite(float(values['input_i']))
    if not silent:
        keys = ('input_i', 'input_tp', 'input_lra', 'input_thresh', 'target_offset')
        if not all(math.isfinite(float(values[k])) for k in keys):
            raise ValueError('invalid narration loudness measurement')
        chain += ',' + norm + ':measured_I={input_i}:measured_TP={input_tp}:measured_LRA={input_lra}:measured_thresh={input_thresh}:offset={target_offset}:linear=true'.format(**values)
    codec = ['-c:a', 'pcm_s16le'] if output.suffix == '.wav' else ['-c:a', 'libmp3lame', '-b:a', '192k']
    if output.suffix not in {'.wav', '.mp3'}:
        raise ValueError('narration mastering output must be WAV or MP3')
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.narration-', suffix=output.suffix, dir=output.parent)
    os.close(fd)
    try:
        subprocess.run([ffmpeg, '-v', 'error', '-y', *inputs, '-af', chain, '-ar', str(POLICY['sample_rate']), *codec, name], check=True, capture_output=True, timeout=600)
        os.replace(name, output)
    finally:
        Path(name).unlink(missing_ok=True)
    report = {'policy': dict(POLICY), 'source': str(source), 'concat': concat, 'offset_seconds': offset_seconds,
              'duration_seconds': duration_seconds, 'measurement': values, 'silent': silent,
              'output_sha256': hashlib.sha256(output.read_bytes()).hexdigest()}
    output.with_suffix(output.suffix + '.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def narration_preview(source: Path, directory: Path, *, offset_seconds: float, duration_seconds: float) -> Path:
    identity = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'policy': POLICY,
                'offset': offset_seconds, 'duration': duration_seconds}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    output = directory / f'{key}.mp3'
    from toc.runtime_locks import sync_file_lock
    directory.mkdir(parents=True, exist_ok=True)
    with sync_file_lock(directory / f'{key}.lock'):
        report = output.with_suffix('.mp3.json')
        if output.is_file() and report.is_file():
            try:
                if json.loads(report.read_text())['output_sha256'] == hashlib.sha256(output.read_bytes()).hexdigest():
                    return output
            except (ValueError, KeyError):
                pass
        normalize_narration(source, output, offset_seconds=offset_seconds, duration_seconds=duration_seconds)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--concat', action='store_true')
    args = parser.parse_args()
    normalize_narration(args.source, args.out, concat=args.concat)


if __name__ == '__main__':
    main()
