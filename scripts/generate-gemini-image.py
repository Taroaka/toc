#!/usr/bin/env python3
"""
Generate a single image via Google Gemini API (Image generation).

Defaults are tuned for Nano Banana 2 / Gemini 3.1 Flash Image (= gemini-3.1-flash-image-preview) but can be overridden.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.env import load_env_files
from toc.http import HttpError
from toc.providers.gemini import GeminiClient, GeminiConfig


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


def _guess_suffix(mime_type: str | None) -> str:
    if not mime_type:
        return ".bin"
    mt = mime_type.lower()
    if mt == "image/png":
        return ".png"
    if mt == "image/jpeg":
        return ".jpg"
    if mt == "image/webp":
        return ".webp"
    return ".bin"


def _run_ffmpeg_convert_image(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-i",
            str(src),
            "-frames:v",
            "1",
            str(dst),
        ],
        check=True,
    )


def main() -> None:
    load_env_files(repo_root=REPO_ROOT)

    parser = argparse.ArgumentParser(description="Generate an image via Gemini API.")
    parser.add_argument("--prompt", required=True, help="Text prompt.")
    parser.add_argument("--out", required=True, help="Output image path (recommended: .png).")
    parser.add_argument("--model", default=_env("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview"))
    parser.add_argument("--api-base", default=_env("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"))
    parser.add_argument("--api-key", default=_env("GEMINI_API_KEY"))
    parser.add_argument("--aspect-ratio", default="9:16", help='e.g. "9:16", "16:9", "1:1"')
    parser.add_argument("--image-size", default="2K", help='e.g. "1K", "2K", "4K" (provider-dependent)')
    parser.add_argument("--save-json", default=None, help="Optional path to save raw JSON response.")
    parser.add_argument("--dry-run", action="store_true", help="Print request and exit.")

    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("Missing API key. Set GEMINI_API_KEY or pass --api-key.")

    url = f"{args.api_base.rstrip('/')}/models/{args.model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": args.prompt}]}],
        "generationConfig": {
            "responseModalities": ["Image"],
            "imageConfig": {
                "aspectRatio": args.aspect_ratio,
                "imageSize": args.image_size,
            },
        },
    }

    if args.dry_run:
        print(url)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    client = GeminiClient(
        GeminiConfig(
            api_key=args.api_key,
            api_base=args.api_base,
            image_model=args.model,
            video_model=_env("GEMINI_VIDEO_MODEL", "veo-3.1-fast-generate-preview") or "veo-3.1-fast-generate-preview",
        )
    )

    try:
        image_bytes, mime_type, resp = client.generate_image(
            prompt=args.prompt,
            aspect_ratio=args.aspect_ratio,
            image_size=args.image_size,
            model=args.model,
        )
    except (HttpError, ValueError) as e:
        raise SystemExit(str(e)) from e

    if args.save_json:
        Path(args.save_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save_json).write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = _guess_suffix(mime_type)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(image_bytes)

    try:
        try:
            _run_ffmpeg_convert_image(tmp_path, out_path)
        except FileNotFoundError:
            # ffmpeg not available: write raw bytes as-is.
            out_path.write_bytes(image_bytes)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
