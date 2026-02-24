#!/usr/bin/env python3
"""
Generate a single video via Kling API.

This CLI mirrors scripts/generate-veo-video.py but targets a separate Kling client.
Defaults are configurable via KLING_* environment variables.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.env import load_env_files
from toc.http import HttpError
from toc.providers.kling import KlingClient, KlingConfig


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _redact_image_b64(payload: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(json.dumps(payload))
    candidates = [redacted]
    input_node = redacted.get("input")
    if isinstance(input_node, dict):
        candidates.append(input_node)
    for cand in candidates:
        for key in ("first_frame_image", "last_frame_image"):
            node = cand.get(key)
            if not isinstance(node, dict):
                continue
            b64 = node.get("data")
            if isinstance(b64, str) and b64:
                node["data"] = f"<base64 omitted: {len(b64)} chars>"
    return redacted


def main() -> None:
    load_env_files(repo_root=REPO_ROOT)

    parser = argparse.ArgumentParser(description="Generate a video via Kling API.")
    parser.add_argument("--prompt", required=True, help="Text prompt.")
    parser.add_argument("--out", required=True, help="Output video path (recommended: .mp4).")
    parser.add_argument("--input-image", default=None, help="Optional first-frame image path.")
    parser.add_argument("--last-image", default=None, help="Optional last-frame image path.")
    parser.add_argument("--model", default=_env("KLING_VIDEO_MODEL", "kling-3.0"))
    parser.add_argument("--api-base", default=_env("KLING_API_BASE", "https://api.klingai.com"))
    parser.add_argument("--api-key", default=_env("KLING_API_KEY"), help="Gateway-style API key (optional).")
    parser.add_argument("--access-key", default=_env("KLING_ACCESS_KEY"), help="Official Kling AccessKey (recommended).")
    parser.add_argument("--secret-key", default=_env("KLING_SECRET_KEY"), help="Official Kling SecretKey (recommended).")
    parser.add_argument("--submit-path", default=_env("KLING_VIDEO_SUBMIT_PATH", "/v1/videos/image2video"))
    parser.add_argument(
        "--status-path-template",
        default=_env("KLING_VIDEO_STATUS_PATH_TEMPLATE", "/v1/videos/image2video/{operation_id}"),
        help="Polling endpoint path. Supports {operation_id}.",
    )
    parser.add_argument(
        "--operation-id-paths",
        default=_env("KLING_OPERATION_ID_PATHS", "data.id,id,task_id,data.task_id"),
        help="Comma-separated JSON paths in submit response used to find operation id.",
    )
    parser.add_argument(
        "--status-paths",
        default=_env("KLING_STATUS_PATHS", "status,data.status,task.status,data.task_status"),
        help="Comma-separated JSON paths in operation response used to read status.",
    )
    parser.add_argument(
        "--done-statuses",
        default=_env("KLING_DONE_STATUSES", "succeeded,success,completed,done,finished"),
        help="Comma-separated statuses considered successful completion.",
    )
    parser.add_argument(
        "--failed-statuses",
        default=_env("KLING_FAILED_STATUSES", "failed,error,cancelled,canceled,rejected"),
        help="Comma-separated statuses considered failed completion.",
    )
    parser.add_argument(
        "--video-url-paths",
        default=_env(
            "KLING_VIDEO_URL_PATHS",
            "data.video.url,data.video_url,data.output.url,video.url,video_url,output.video_url,result.video.url",
        ),
        help="Comma-separated JSON paths used to find downloadable video URL in final response.",
    )
    parser.add_argument("--duration-seconds", type=int, default=6, help="Requested clip duration.")
    parser.add_argument("--aspect-ratio", default="9:16", help='e.g. "9:16", "16:9"')
    parser.add_argument("--resolution", default="720p", help='e.g. "720p", "1080p"')
    parser.add_argument("--negative-prompt", default="", help="Optional negative prompt.")
    parser.add_argument("--extra-json", default=None, help="Optional extra JSON merged into request payload.")
    parser.add_argument("--poll-every", type=float, default=5.0, help="Polling interval seconds.")
    parser.add_argument("--timeout-seconds", type=float, default=900.0, help="Overall timeout seconds.")
    parser.add_argument("--save-json", default=None, help="Optional path to save final operation JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Print request payload and exit.")

    args = parser.parse_args()

    input_image = Path(args.input_image) if args.input_image else None
    if input_image and not input_image.exists():
        raise SystemExit(f"Input image not found: {input_image}")
    last_image = Path(args.last_image) if args.last_image else None
    if last_image and not last_image.exists():
        raise SystemExit(f"Last image not found: {last_image}")

    extra_payload: dict[str, Any] | None = None
    if args.extra_json:
        try:
            loaded = json.loads(args.extra_json)
        except json.JSONDecodeError as e:
            raise SystemExit(f"--extra-json is not valid JSON: {e}") from e
        if not isinstance(loaded, dict):
            raise SystemExit("--extra-json must be a JSON object.")
        extra_payload = loaded

    try:
        config = KlingConfig.from_env(
            api_key=args.api_key,
            access_key=args.access_key,
            secret_key=args.secret_key,
            api_base=args.api_base,
            video_model=args.model,
            submit_path=args.submit_path,
            status_path_template=args.status_path_template,
        )
    except ValueError as e:
        raise SystemExit(str(e)) from e

    client = KlingClient(config)
    payload = client.build_video_payload(
        prompt=args.prompt,
        duration_seconds=args.duration_seconds,
        aspect_ratio=args.aspect_ratio,
        resolution=args.resolution,
        input_image=input_image,
        last_frame_image=last_image,
        negative_prompt=args.negative_prompt,
        model=args.model,
        extra_payload=extra_payload,
    )

    if args.dry_run:
        submit_url = f"{config.api_base.rstrip('/')}{config.submit_path}"
        print(submit_url)
        print(json.dumps(_redact_image_b64(payload), ensure_ascii=False, indent=2)[:4000])
        return

    id_paths = _split_csv(args.operation_id_paths)
    status_paths = _split_csv(args.status_paths)
    done_statuses = _split_csv(args.done_statuses)
    failed_statuses = _split_csv(args.failed_statuses)
    video_url_paths = _split_csv(args.video_url_paths)

    try:
        submit_resp = client.start_video_generation(
            prompt=args.prompt,
            duration_seconds=args.duration_seconds,
            aspect_ratio=args.aspect_ratio,
            resolution=args.resolution,
            input_image=input_image,
            last_frame_image=last_image,
            negative_prompt=args.negative_prompt,
            model=args.model,
            extra_payload=extra_payload,
        )
        operation_id = client.extract_operation_id(submit_resp, id_paths=id_paths)
        op = client.poll_operation(
            operation_id_or_url=operation_id,
            status_paths=status_paths,
            done_statuses=done_statuses,
            failed_statuses=failed_statuses,
            poll_every_seconds=args.poll_every,
            timeout_seconds=args.timeout_seconds,
        )
    except (HttpError, TimeoutError, ValueError) as e:
        raise SystemExit(str(e)) from e

    if args.save_json:
        save_path = Path(args.save_json)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps(op, ensure_ascii=False, indent=2), encoding="utf-8")

    if client.is_failed_operation(op, status_paths=status_paths, failed_statuses=failed_statuses):
        raise SystemExit(f"Kling operation failed: {json.dumps(op, ensure_ascii=False)}")

    try:
        video_uri = client.extract_video_uri(op, video_url_paths=video_url_paths)
        client.download_to_file(uri=video_uri, out_path=Path(args.out))
    except (HttpError, ValueError) as e:
        raise SystemExit(str(e)) from e

    print(f"Wrote: {Path(args.out)}")


if __name__ == "__main__":
    main()
