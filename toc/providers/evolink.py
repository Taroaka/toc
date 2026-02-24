from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from toc.http import request_bytes, request_json


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".png":
        return "image/png"
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    return "application/octet-stream"


@dataclass(frozen=True)
class EvoLinkConfig:
    api_key: str
    api_base: str = "https://api.evolink.ai"
    files_api_base: str = "https://files-api.evolink.ai"
    file_upload_base64_path: str = "/api/v1/files/upload/base64"
    video_submit_path: str = "/v1/videos/generations"
    task_status_path_template: str = "/v1/tasks/{task_id}"

    @staticmethod
    def from_env(
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        files_api_base: str | None = None,
        file_upload_base64_path: str | None = None,
        video_submit_path: str | None = None,
        task_status_path_template: str | None = None,
    ) -> "EvoLinkConfig":
        key = (api_key or _env("EVOLINK_API_KEY") or "").strip()
        if not key:
            raise ValueError("Missing EVOLINK_API_KEY")
        return EvoLinkConfig(
            api_key=key,
            api_base=api_base or _env("EVOLINK_API_BASE", "https://api.evolink.ai") or "",
            files_api_base=files_api_base or _env("EVOLINK_FILES_API_BASE", "https://files-api.evolink.ai") or "",
            file_upload_base64_path=file_upload_base64_path
            or _env("EVOLINK_FILE_UPLOAD_BASE64_PATH", "/api/v1/files/upload/base64")
            or "",
            video_submit_path=video_submit_path or _env("EVOLINK_VIDEO_SUBMIT_PATH", "/v1/videos/generations") or "",
            task_status_path_template=task_status_path_template
            or _env("EVOLINK_TASK_STATUS_PATH_TEMPLATE", "/v1/tasks/{task_id}")
            or "",
        )


class EvoLinkClient:
    def __init__(self, config: EvoLinkConfig):
        self.config = config

    @staticmethod
    def from_env(**overrides: Any) -> "EvoLinkClient":
        return EvoLinkClient(EvoLinkConfig.from_env(**overrides))

    def _headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.config.api_key}"}

    def _resolve_api_url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        if path_or_url.startswith("/"):
            return f"{self.config.api_base.rstrip('/')}{path_or_url}"
        return f"{self.config.api_base.rstrip('/')}/{path_or_url}"

    def _resolve_files_url(self, path_or_url: str) -> str:
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            return path_or_url
        if path_or_url.startswith("/"):
            return f"{self.config.files_api_base.rstrip('/')}{path_or_url}"
        return f"{self.config.files_api_base.rstrip('/')}/{path_or_url}"

    def upload_image_base64(self, *, path: Path, timeout_seconds: float = 180.0) -> str:
        mime = _guess_mime(path)
        data_url = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        payload = {"content_type": mime, "file_name": path.name, "base64": data_url}
        resp = request_json(
            url=self._resolve_files_url(self.config.file_upload_base64_path),
            method="POST",
            headers={"content-type": "application/json", **self._headers()},
            json_payload=payload,
            timeout_seconds=timeout_seconds,
        )
        file_url = resp.get("file_url") or resp.get("url") or resp.get("data", {}).get("file_url")
        if not isinstance(file_url, str) or not file_url.strip():
            raise ValueError("EvoLink upload response missing file_url")
        return file_url.strip()

    def submit_video_task(self, *, payload: dict[str, Any], timeout_seconds: float = 180.0) -> dict[str, Any]:
        return request_json(
            url=self._resolve_api_url(self.config.video_submit_path),
            method="POST",
            headers={"content-type": "application/json", **self._headers()},
            json_payload=payload,
            timeout_seconds=timeout_seconds,
        )

    def get_task(self, *, task_id: str, timeout_seconds: float = 180.0) -> dict[str, Any]:
        url = self._resolve_api_url(self.config.task_status_path_template.format(task_id=task_id))
        return request_json(url=url, method="GET", headers=self._headers(), timeout_seconds=timeout_seconds)

    def poll_task(
        self,
        *,
        task_id: str,
        poll_every_seconds: float = 5.0,
        timeout_seconds: float = 900.0,
    ) -> dict[str, Any]:
        deadline = time.time() + float(timeout_seconds)
        while True:
            task = self.get_task(task_id=task_id, timeout_seconds=180.0)
            status = (task.get("status") or "").strip().lower()
            if status in {"completed", "succeeded", "success", "done"}:
                return task
            if status in {"failed", "error", "canceled", "cancelled", "rejected"}:
                return task
            if time.time() > deadline:
                raise TimeoutError(f"Timed out waiting for EvoLink task: {task_id}")
            time.sleep(float(poll_every_seconds))

    def extract_task_id(self, submit_response: dict[str, Any]) -> str:
        task_id = submit_response.get("task_id") or submit_response.get("id") or submit_response.get("data", {}).get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise ValueError("EvoLink submit response missing task_id")
        return task_id.strip()

    def extract_video_url(self, task: dict[str, Any]) -> str:
        results = task.get("results")
        if isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, str) and first.strip():
                return first.strip()
            if isinstance(first, dict):
                url = first.get("url") or first.get("uri")
                if isinstance(url, str) and url.strip():
                    return url.strip()
        raise ValueError("EvoLink task missing results[0] URL")

    def download_to_file(self, *, url: str, out_path: Path, timeout_seconds: float = 600.0) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        data = request_bytes(url=url, method="GET", headers=None, timeout_seconds=timeout_seconds)
        out_path.write_bytes(data)

