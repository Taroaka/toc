#!/usr/bin/env python3
"""
Manual smoke test for the official ElevenLabs Python SDK.

This is intentionally NOT wired into the main pipeline. It exists to:
- mirror the official SDK usage pattern (text_to_speech.convert)
- confirm a voice_id works end-to-end using the SDK

Usage:
  python testcode/elevenlabs_official_sdk_smoke.py \
    --voice-id JBFqnCBsd6RMkjVDRZzb \
    --text "The first move is what sets everything in motion."

Notes:
- Requires ELEVENLABS_API_KEY in env (or in .env at repo root).
- Requires the `elevenlabs` package installed.
- Optionally requires `python-dotenv` if you want to use load_dotenv().
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _load_env_best_effort() -> None:
    try:
        from dotenv import load_dotenv  # type: ignore[import-not-found]

        load_dotenv()
        return
    except Exception:
        pass

    try:
        repo_root = Path(__file__).resolve().parents[1]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from toc.env import load_env_files

        load_env_files(repo_root=repo_root)
    except Exception:
        # Best-effort only.
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="ElevenLabs official SDK smoke test (manual).")
    parser.add_argument("--text", default="The first move is what sets everything in motion.")
    parser.add_argument("--voice-id", default="JOcmGzB8OFjY8MhjHHEf")
    parser.add_argument("--model-id", default="eleven_v3")
    parser.add_argument("--output-format", default="mp3_44100_128")
    parser.add_argument("--out", default="output/_smoke/elevenlabs_sdk_smoke.mp3")
    args = parser.parse_args()

    _load_env_best_effort()

    api_key = os.getenv("ELEVENLABS_API_KEY") or ""
    if not api_key.strip():
        raise SystemExit("Missing ELEVENLABS_API_KEY (set env var or put it in .env).")

    try:
        from elevenlabs.client import ElevenLabs  # type: ignore[import-not-found]
    except Exception as e:
        raise SystemExit(
            "Missing dependency: elevenlabs\n"
            "Install:\n"
            "  pip install elevenlabs\n"
            "(Optional) for .env loading:\n"
            "  pip install python-dotenv\n"
        ) from e

    elevenlabs = ElevenLabs(api_key=api_key)

    audio = elevenlabs.text_to_speech.convert(
        text=str(args.text),
        voice_id=str(args.voice_id),
        model_id=str(args.model_id),
        output_format=str(args.output_format),
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(audio)
    print(f"OK: wrote {out_path} ({len(audio)} bytes)")


if __name__ == "__main__":
    main()
