#!/usr/bin/env python3
"""
Generate a narration audio clip via ElevenLabs Text-to-Speech API.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.env import load_env_files
from toc.http import HttpError
from toc.providers.elevenlabs import DEFAULT_ELEVENLABS_VOICE_ID, ElevenLabsClient, ElevenLabsConfig


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


def _ffmpeg_normalize_mp3(src: Path, dst: Path, duration_seconds: int | None) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(src),
        "-ar",
        "44100",
        "-ac",
        "1",
        "-b:a",
        "128k",
        "-codec:a",
        "libmp3lame",
    ]
    if duration_seconds is not None:
        cmd += ["-af", "apad", "-t", str(duration_seconds)]
    cmd.append(str(dst))
    subprocess.run(cmd, check=True)


def main() -> None:
    load_env_files(repo_root=REPO_ROOT)

    parser = argparse.ArgumentParser(description="Generate TTS audio via ElevenLabs.")
    parser.add_argument("--text", required=True, help="Narration text.")
    parser.add_argument("--out", required=True, help="Output audio path (.mp3 recommended).")

    parser.add_argument("--api-key", default=_env("ELEVENLABS_API_KEY"))
    parser.add_argument("--api-base", default=_env("ELEVENLABS_API_BASE", "https://api.elevenlabs.io/v1"))
    parser.add_argument("--voice-id", default=_env("ELEVENLABS_VOICE_ID", DEFAULT_ELEVENLABS_VOICE_ID))
    parser.add_argument("--model-id", default=_env("ELEVENLABS_MODEL_ID", "eleven_v3"))
    parser.add_argument("--output-format", default=_env("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128"))

    parser.add_argument("--stability", type=float, default=0.35)
    parser.add_argument("--similarity-boost", type=float, default=0.75)
    parser.add_argument("--style", type=float, default=0.0)
    parser.add_argument("--use-speaker-boost", action="store_true")

    parser.add_argument("--duration-seconds", type=int, default=None, help="Pad/trim output to this length.")
    parser.add_argument("--save-request", default=None, help="Optional path to save request JSON (no secrets).")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("Missing ELEVENLABS_API_KEY or --api-key.")
    if not args.voice_id:
        args.voice_id = DEFAULT_ELEVENLABS_VOICE_ID

    base = args.api_base.rstrip("/")
    url = f"{base}/text-to-speech/{urllib.parse.quote(args.voice_id)}"
    if args.output_format:
        url += "?" + urllib.parse.urlencode({"output_format": args.output_format})

    payload: dict = {
        "text": args.text,
        "model_id": args.model_id,
        "voice_settings": {
            "stability": args.stability,
            "similarity_boost": args.similarity_boost,
            "style": args.style,
            "use_speaker_boost": bool(args.use_speaker_boost),
        },
    }

    if args.save_request:
        Path(args.save_request).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save_request).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print(url)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    client = ElevenLabsClient(
        ElevenLabsConfig(
            api_key=args.api_key,
            api_base=args.api_base,
            voice_id=args.voice_id,
            model_id=args.model_id,
            output_format=args.output_format,
        )
    )

    try:
        audio = client.tts(
            text=args.text,
            voice_settings=payload["voice_settings"],
        )
    except HttpError as e:
        raise SystemExit(str(e)) from e

    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(audio)

    try:
        try:
            _ffmpeg_normalize_mp3(tmp_path, out_path, args.duration_seconds)
        except FileNotFoundError:
            out_path.write_bytes(audio)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
