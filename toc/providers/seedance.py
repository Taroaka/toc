from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from toc.http import request_json
from toc.providers.media_download import request_public_media_bytes
from toc.video_provider_capabilities import resolve_video_provider_capabilities


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _guess_image_format(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    if ext in {"jpg", "jpeg"}:
        return "jpeg"
    if ext == "png":
        return "png"
    if ext == "webp":
        return "webp"
    raise ValueError(f"Unsupported image format: {path.suffix} (expected .png/.jpg/.jpeg/.webp)")


def encode_image_as_data_url(path: Path) -> str:
    """
    Encode a local image as a `data:image/<fmt>;base64,...` URL.

    BytePlus ModelArk video generation docs specify this format for base64 image inputs.
    """

    fmt = _guess_image_format(path)
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{fmt};base64,{b64}"


def _lookup_path(data: Any, path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        part = part.strip()
        if part == "":
            return None
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current.get(part)
            continue
        return None
    return current


def _first_non_empty(data: dict[str, Any], paths: list[str]) -> Any:
    for path in paths:
        value = _lookup_path(data, path)
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        return value
    return None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


_PROTECTED_VIDEO_EXTRA_KEYS = {
    "model",
    "content",
    "resolution",
    "ratio",
    "duration",
    "watermark",
    "generate_audio",
}


def _validate_video_extra_payload(extra_payload: dict[str, Any] | None) -> None:
    if not extra_payload:
        return
    conflicts = sorted(_PROTECTED_VIDEO_EXTRA_KEYS.intersection(extra_payload))
    if conflicts:
        raise ValueError(
            "video extra_payload cannot override protected reviewed fields: "
            + ", ".join(conflicts)
        )


@dataclass(frozen=True)
class SeedanceConfig:
    """
    BytePlus ModelArk (Seedance) video generation client config.

    API shape:
      - Create:  POST {api_base}/contents/generations/tasks
      - Retrieve: GET {api_base}/contents/generations/tasks/{id}
    """

    api_key: str
    api_base: str = "https://ark.ap-southeast.bytepluses.com/api/v3"
    submit_path: str = "/contents/generations/tasks"
    status_path_template: str = "/contents/generations/tasks/{task_id}"

    @staticmethod
    def from_env(
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        submit_path: str | None = None,
        status_path_template: str | None = None,
    ) -> "SeedanceConfig":
        key = (api_key or _env("ARK_API_KEY") or _env("SEADREAM_API_KEY") or "").strip()
        if not key:
            raise ValueError("Missing ARK_API_KEY (or SEADREAM_API_KEY).")

        return SeedanceConfig(
            api_key=key,
            api_base=(api_base or _env("ARK_API_BASE") or _env("SEADREAM_API_BASE") or "https://ark.ap-southeast.bytepluses.com/api/v3"),
            submit_path=submit_path or _env("ARK_CONTENTS_GENERATIONS_SUBMIT_PATH", "/contents/generations/tasks") or "",
            status_path_template=status_path_template
            or _env("ARK_CONTENTS_GENERATIONS_STATUS_PATH_TEMPLATE", "/contents/generations/tasks/{task_id}")
            or "",
        )


class SeedanceClient:
    def __init__(self, config: SeedanceConfig):
        self.config = config

    @staticmethod
    def from_env(**overrides: Any) -> "SeedanceClient":
        return SeedanceClient(SeedanceConfig.from_env(**overrides))

    def _headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.config.api_key}"}

    def _resolve_url(self, path_or_url: str, *, task_id: str | None = None) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url

        path = path_or_url
        if task_id is not None:
            path = path.format(task_id=task_id)

        if path.startswith("/"):
            return f"{self.config.api_base.rstrip('/')}{path}"
        return f"{self.config.api_base.rstrip('/')}/{path}"

    def create_task(self, *, payload: dict[str, Any], timeout_seconds: float = 180.0) -> dict[str, Any]:
        return request_json(
            url=self._resolve_url(self.config.submit_path),
            method="POST",
            headers={"content-type": "application/json", **self._headers()},
            json_payload=payload,
            timeout_seconds=timeout_seconds,
        )

    def get_task(self, *, task_id: str, timeout_seconds: float = 60.0) -> dict[str, Any]:
        return request_json(
            url=self._resolve_url(self.config.status_path_template, task_id=task_id),
            method="GET",
            headers=self._headers(),
            timeout_seconds=timeout_seconds,
        )

    def poll_task(
        self,
        *,
        task_id: str,
        poll_every_seconds: float = 5.0,
        timeout_seconds: float = 900.0,
    ) -> dict[str, Any]:
        start = time.time()
        last: dict[str, Any] | None = None
        while True:
            if time.time() - start > timeout_seconds:
                raise TimeoutError(f"Seedance task timed out after {timeout_seconds:.1f}s: {task_id}")

            task = self.get_task(task_id=task_id, timeout_seconds=max(60.0, float(poll_every_seconds) * 4.0))
            last = task
            status = str(task.get("status") or "").strip().lower()

            if status in {"succeeded", "success", "succeed", "completed", "done"}:
                return task
            if status in {"failed", "error", "canceled", "cancelled", "rejected"}:
                return task

            time.sleep(max(0.5, float(poll_every_seconds)))

    def is_failed_task(self, task: dict[str, Any]) -> bool:
        status = str(task.get("status") or "").strip().lower()
        return status in {"failed", "error", "canceled", "cancelled", "rejected"}

    def extract_task_id(self, resp: dict[str, Any]) -> str:
        task_id = _first_non_empty(resp, ["id", "task_id", "data.id"])
        if not task_id:
            raise ValueError(f"Seedance create_task response missing id: {resp}")
        return str(task_id)

    def extract_video_url(self, task: dict[str, Any]) -> str:
        url = _first_non_empty(task, ["content.video_url", "content.url", "video_url", "url"])
        if not url:
            raise ValueError(f"Seedance task missing video_url: {task}")
        return str(url)

    def download_to_file(self, *, url: str, out_path: Path, timeout_seconds: float = 600.0) -> None:
        data = request_public_media_bytes(url=url, timeout_seconds=timeout_seconds)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)

    def build_video_payload(
        self,
        *,
        model: str,
        prompt: str,
        duration_seconds: int,
        ratio: str,
        resolution: str = "720p",
        input_image: Path | None = None,
        last_frame_image: Path | None = None,
        reference_images: list[Path] | None = None,
        generate_audio: bool = False,
        watermark: bool = False,
        extra_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        _validate_video_extra_payload(extra_payload)
        references = [path for path in reference_images or [] if path is not None]
        if references and (input_image is not None or last_frame_image is not None):
            raise ValueError(
                "Seedance frame-boundary and multimodal reference modes are mutually exclusive"
            )
        if last_frame_image is not None and input_image is None:
            raise ValueError("Seedance last_frame requires first_frame")
        input_mode = (
            "reference_images"
            if references
            else "image_to_video"
            if input_image is not None
            else "text_to_video"
        )
        capabilities = resolve_video_provider_capabilities(
            tool="seedance",
            model=model,
            input_mode=input_mode,
        )
        if not capabilities.supported:
            raise ValueError(capabilities.unsupported_reason)
        duration = int(duration_seconds)
        if not (
            capabilities.duration_min_seconds
            <= duration
            <= capabilities.duration_max_seconds
        ):
            raise ValueError(
                "Seedance duration is outside the reviewed capability range: "
                f"{duration}s (expected {capabilities.duration_min_seconds}-"
                f"{capabilities.duration_max_seconds}s)"
            )
        if not (
            capabilities.reference_images_min
            <= len(references)
            <= capabilities.reference_images_max
        ):
            raise ValueError(
                "Seedance reference image count is outside the reviewed capability range: "
                f"{len(references)} (expected {capabilities.reference_images_min}-"
                f"{capabilities.reference_images_max})"
            )
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

        if input_image is not None:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": encode_image_as_data_url(input_image)},
                    "role": "first_frame",
                }
            )
        if last_frame_image is not None:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": encode_image_as_data_url(last_frame_image)},
                    "role": "last_frame",
                }
            )

        for ref in references:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": encode_image_as_data_url(ref)},
                    "role": "reference_image",
                }
            )

        payload: dict[str, Any] = {
            "model": model,
            "content": content,
            "resolution": resolution,
            "ratio": ratio,
            "duration": duration,
            "watermark": bool(watermark),
            "generate_audio": bool(generate_audio),
        }
        if extra_payload:
            payload = _deep_merge(payload, extra_payload)
        return payload
