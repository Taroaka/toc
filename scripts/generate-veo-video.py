#!/usr/bin/env python3
"""
Generate a single video via Google Gemini API (Veo).

This uses the REST "predictLongRunning" flow and polls the operation until completion.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
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


def main() -> None:
    load_env_files(repo_root=REPO_ROOT)

    parser = argparse.ArgumentParser(description="Generate a video via Veo (Gemini API).")
    parser.add_argument("--prompt", required=True, help="Text prompt.")
    parser.add_argument("--out", required=True, help="Output video path (recommended: .mp4).")
    parser.add_argument("--input-image", default=None, help="Optional first-frame image path (image-to-video).")
    parser.add_argument("--last-image", default=None, help="Optional last-frame image path (first-last-frame-to-video).")
    parser.add_argument("--model", default=_env("GEMINI_VIDEO_MODEL", "veo-3.1-fast-generate-preview"))
    parser.add_argument("--api-base", default=_env("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta"))
    parser.add_argument("--api-key", default=_env("GEMINI_API_KEY"))
    parser.add_argument("--duration-seconds", type=int, default=6, help="Allowed: 4/6/8 (model-dependent).")
    parser.add_argument("--aspect-ratio", default="9:16", help='e.g. "9:16", "16:9"')
    parser.add_argument("--resolution", default="720p", help='e.g. "720p", "1080p", "4k"')
    parser.add_argument("--poll-every", type=float, default=5.0, help="Polling interval seconds.")
    parser.add_argument("--timeout-seconds", type=float, default=900.0, help="Overall timeout seconds.")
    parser.add_argument("--save-json", default=None, help="Optional path to save final operation JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Print request and exit.")

    args = parser.parse_args()

    if not args.dry_run:
        raise SystemExit(
            "Veo video generation is disabled in this repo for safety. "
            "Use Kling instead (e.g. scripts/generate-kling-video.py)."
        )

    if args.dry_run:
        url = f"{args.api_base.rstrip('/')}/models/{args.model}:predictLongRunning"
        payload = {
            "instances": [
                {
                    "prompt": args.prompt,
                    **(
                        {
                            "image": {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "data": "<base64 omitted>",
                                }
                            }
                        }
                        if args.input_image
                        else {}
                    ),
                    **(
                        {
                            (_env("GEMINI_VEO_LAST_IMAGE_FIELD", "endImage") or "endImage"): {
                                "inlineData": {
                                    "mimeType": "image/png",
                                    "data": "<base64 omitted>",
                                }
                            }
                        }
                        if args.last_image
                        else {}
                    ),
                }
            ],
            "parameters": {
                "durationSeconds": args.duration_seconds,
                "aspectRatio": args.aspect_ratio,
                "resolution": args.resolution,
            },
        }
        print(url)
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:2000])
        return

    try:
        config = GeminiConfig.from_env(api_key=args.api_key, api_base=args.api_base, video_model=args.model)
    except ValueError as e:
        raise SystemExit(str(e)) from e

    client = GeminiClient(config)

    input_image = Path(args.input_image) if args.input_image else None
    if input_image and not input_image.exists():
        raise SystemExit(f"Input image not found: {input_image}")
    last_image = Path(args.last_image) if args.last_image else None
    if last_image and not last_image.exists():
        raise SystemExit(f"Last image not found: {last_image}")

    try:
        op = client.start_video_generation(
            prompt=args.prompt,
            duration_seconds=args.duration_seconds,
            aspect_ratio=args.aspect_ratio,
            resolution=args.resolution,
            input_image=input_image,
            last_frame_image=last_image,
            model=args.model,
        )
    except HttpError as e:
        raise SystemExit(str(e)) from e

    op_name = op.get("name")
    if not op_name:
        raise SystemExit(f"No operation name returned. Response keys: {list(op.keys())}")

    try:
        op = client.poll_operation(
            op_name_or_url=str(op_name),
            poll_every_seconds=args.poll_every,
            timeout_seconds=args.timeout_seconds,
        )
    except TimeoutError:
        raise SystemExit(f"Timed out waiting for operation: {op_name}")
    except HttpError as e:
        raise SystemExit(str(e)) from e

    if args.save_json:
        Path(args.save_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save_json).write_text(json.dumps(op, ensure_ascii=False, indent=2), encoding="utf-8")

    if "error" in op and op["error"]:
        raise SystemExit(f"Operation failed: {json.dumps(op['error'], ensure_ascii=False)}")

    out_path = Path(args.out)
    try:
        video_uri = client.extract_video_uri(op)
        client.download_to_file(uri=video_uri, out_path=out_path)
    except (HttpError, ValueError) as e:
        raise SystemExit(str(e)) from e

    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
