#!/usr/bin/env python3
"""Disabled legacy SeaDream/Seedream image generation entrypoint."""

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
from toc.providers.seadream import SeaDreamClient, SeaDreamConfig


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
    raise SystemExit(
        "Deprecated: external SeaDream image generation is disabled for this repo. "
        "Use codex_builtin_image / gpt-image-2 through the Codex app-server instead."
    )

    parser = argparse.ArgumentParser(description="Generate an image via SeaDream / Seedream.")
    parser.add_argument("--prompt", required=True, help="Text prompt.")
    parser.add_argument("--out", required=True, help="Output image path (recommended: .png).")
    parser.add_argument("--model", default=_env("SEADREAM_MODEL", "seedream-4-5-251128"))
    parser.add_argument("--size", default=_env("SEADREAM_SIZE", "1024x1536"), help='e.g. "1024x1024", "1024x1536"')
    parser.add_argument("--api-base", default=_env("SEADREAM_API_BASE", "https://ark.ap-southeast.bytepluses.com/api/v3"))
    parser.add_argument("--api-key", default=_env("SEADREAM_API_KEY"))
    parser.add_argument("--save-json", default=None, help="Optional path to save raw JSON response.")
    parser.add_argument("--dry-run", action="store_true", help="Print request and exit.")

    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("Missing API key. Set SEADREAM_API_KEY or pass --api-key.")

    url = f"{args.api_base.rstrip('/')}/images/generations"
    payload = {"model": args.model, "prompt": args.prompt, "n": 1, "size": args.size, "response_format": "b64_json"}

    if args.dry_run:
        print(url)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    client = SeaDreamClient(
        SeaDreamConfig(
            api_key=args.api_key,
            api_base=args.api_base,
            image_model=args.model,
        )
    )

    try:
        image_bytes, mime_type, resp = client.generate_image(prompt=args.prompt, size=args.size, model=args.model)
    except (HttpError, ValueError) as e:
        raise SystemExit(str(e)) from e

    if args.save_json:
        Path(args.save_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save_json).write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = _guess_suffix(mime_type or "image/png")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(image_bytes)

    try:
        try:
            _run_ffmpeg_convert_image(tmp_path, out_path)
        except FileNotFoundError:
            out_path.write_bytes(image_bytes)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
