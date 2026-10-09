from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from toc.http import request_json
from toc.providers.media_download import _SafeMediaRedirectHandler, request_public_media_bytes, validate_media_url


API_BASE = "https://api.higgsfield.ai"
IMAGE_MODEL = "bytedance/seedance-2.5/image-to-video"
REFERENCE_MODEL = "bytedance/seedance-2.5/reference-to-video"
SUPPORTED_MODELS = (IMAGE_MODEL, REFERENCE_MODEL)
SUPPORTED_OPERATIONS = {
    IMAGE_MODEL: "image_to_video",
    REFERENCE_MODEL: "reference_to_video",
}
_TERMINAL = {"completed", "failed", "nsfw", "canceled"}
_ASPECT_RATIOS = {"16:9": 16 / 9, "4:3": 4 / 3, "1:1": 1.0, "3:4": 3 / 4, "9:16": 9 / 16, "21:9": 21 / 9}


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def _https_url(value: Any, *, purpose: str, resolve_public: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"Higgsfield returned an invalid {purpose} URL")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError(f"Higgsfield returned an invalid {purpose} URL") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"Higgsfield {purpose} URL must use public HTTPS")
    if resolve_public:
        validate_media_url(value)
    return value


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


@dataclass(frozen=True)
class HiggsfieldConfig:
    api_key: str
    api_base: str = API_BASE

    def __post_init__(self) -> None:
        parsed = urlsplit(self.api_base)
        if parsed.scheme != "https" or parsed.hostname != "api.higgsfield.ai" or parsed.port or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise ValueError("Higgsfield API base must be https://api.higgsfield.ai")
        if not self.api_key or ":" not in self.api_key:
            raise ValueError("Missing Higgsfield key-id:key-secret credential")

    @staticmethod
    def from_env(*, api_key: str | None = None, api_base: str | None = None) -> "HiggsfieldConfig":
        key = (api_key or _env("HF_API_KEY") or "").strip()
        if not key or ":" not in key:
            raise ValueError("Missing HF_API_KEY (expected Higgsfield key-id:key-secret).")
        base = (api_base or API_BASE).rstrip("/")
        if not base.startswith("https://"):
            raise ValueError("Higgsfield API base must use HTTPS")
        return HiggsfieldConfig(api_key=key, api_base=base)


class HiggsfieldClient:
    """Server-side Seedance 2.5 adapter with durable submit/resume journaling."""

    def __init__(self, config: HiggsfieldConfig):
        self.config = config

    @staticmethod
    def from_env(**overrides: Any) -> "HiggsfieldClient":
        return HiggsfieldClient(HiggsfieldConfig.from_env(**overrides))

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Key {self.config.api_key}", "Content-Type": "application/json"}

    def _validate_api_url(self, url: str, *, request_id: str | None = None) -> str:
        if (not isinstance(url, str) or not url or url != url.strip()
                or any(ord(character) <= 32 or ord(character) == 127 for character in url)):
            raise ValueError("Higgsfield API URL is invalid")
        try:
            parsed = urlsplit(url)
        except ValueError:
            raise ValueError("Higgsfield API URL is invalid") from None
        if parsed.scheme != "https" or parsed.hostname != "api.higgsfield.ai" or parsed.port or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Higgsfield API URL must use the official HTTPS origin")
        expected_paths = {f"/{IMAGE_MODEL}", f"/{REFERENCE_MODEL}", "/files/generate-upload-url"}
        if request_id is not None:
            expected_paths.add(f"/requests/{request_id}/status")
        if parsed.path not in expected_paths:
            raise ValueError("Higgsfield API URL has an unexpected path")
        return url

    def _api_request_json(self, *, url: str, method: str, headers: dict[str, str], json_payload: dict[str, Any] | None, timeout_seconds: float, request_id: str | None = None) -> dict[str, Any]:
        safe_url = self._validate_api_url(url, request_id=request_id)
        body = json.dumps(json_payload).encode("utf-8") if json_payload is not None else None
        request = urllib.request.Request(safe_url, data=body, method=method, headers=headers)
        opener = urllib.request.build_opener(_NoRedirectHandler())
        try:
            with opener.open(request, timeout=timeout_seconds) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except Exception:
            raise RuntimeError("Higgsfield API request failed") from None
        if not isinstance(decoded, dict):
            raise RuntimeError("Higgsfield API returned an invalid response")
        return decoded

    @staticmethod
    def _image_ratio_matches(path: Path, aspect_ratio: str) -> bool:
        try:
            from PIL import Image

            with Image.open(path) as image:
                from PIL import ImageOps

                image = ImageOps.exif_transpose(image)
                width, height = image.size
        except Exception:
            raise ValueError("Higgsfield frame image could not be inspected") from None
        if width <= 0 or height <= 0:
            raise ValueError("Higgsfield frame image has invalid dimensions")
        actual = width / height
        expected = _ASPECT_RATIOS[aspect_ratio]
        return abs(actual - expected) / expected <= 0.025

    @staticmethod
    def _file_digest(path: Path | None) -> str | None:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path is not None else None

    def _request_fingerprint(self, *, model: str, prompt: str, duration_seconds: int, aspect_ratio: str, resolution: str, input_image: Path | None, last_frame_image: Path | None, reference_images: list[Path] | None, generate_audio: bool) -> str:
        identity = {
            "model": model, "prompt": prompt, "duration_seconds": duration_seconds,
            "aspect_ratio": aspect_ratio, "resolution": resolution, "generate_audio": generate_audio,
            "input_image_sha256": self._file_digest(input_image),
            "last_frame_image_sha256": self._file_digest(last_frame_image),
            "reference_images_sha256": [self._file_digest(path) for path in (reference_images or [])],
        }
        return hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _save_journal(self, path: Path, journal: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(journal, sort_keys=True, separators=(",", ":"))
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _upload_file(self, path: Path) -> str:
        mime = mimetypes.guess_type(path.name)[0]
        allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
        if mime not in allowed:
            raise ValueError("Higgsfield input image must be JPEG, PNG, WebP, or GIF")
        try:
            upload = self._api_request_json(
                url=f"{self.config.api_base}/files/generate-upload-url",
                method="POST",
                headers=self._headers(),
                json_payload={"content_type": mime},
                timeout_seconds=60,
            )
            upload_url = _https_url(upload.get("upload_url"), purpose="upload")
            public_url = _https_url(upload.get("public_url"), purpose="public media")
            headers = upload.get("upload_headers")
            if not isinstance(headers, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in headers.items()):
                raise ValueError("Higgsfield returned invalid upload headers")
            forbidden_headers = {"authorization", "proxy-authorization", "cookie", "set-cookie"}
            if any(name.lower() in forbidden_headers for name in headers):
                raise ValueError("Higgsfield supplied an unsafe upload header")
            request = urllib.request.Request(upload_url, data=path.read_bytes(), method="PUT", headers=headers)
            opener = urllib.request.build_opener(_SafeMediaRedirectHandler())
            with opener.open(request, timeout=180) as response:
                response.read(1)
            return public_url
        except Exception as exc:
            raise RuntimeError("Higgsfield input upload failed") from None

    def _build_payload(
        self, *, model: str, prompt: str, duration_seconds: int, aspect_ratio: str,
        resolution: str, input_image: Path | None, last_frame_image: Path | None,
        reference_images: list[Path] | None, generate_audio: bool,
    ) -> dict[str, Any]:
        if model not in SUPPORTED_MODELS:
            raise ValueError("Unsupported Higgsfield model/operation")
        if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int) or not 4 <= duration_seconds <= 30:
            raise ValueError("Seedance 2.5 duration_seconds must be an integer from 4 to 30")
        if resolution not in {"480p", "720p", "1080p"}:
            raise ValueError("Unsupported Seedance 2.5 resolution")
        if aspect_ratio not in {"16:9", "4:3", "1:1", "3:4", "9:16", "21:9"}:
            raise ValueError("Unsupported Seedance 2.5 aspect ratio")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Higgsfield prompt must be non-empty")
        if not isinstance(generate_audio, bool):
            raise ValueError("generate_audio must be a boolean")
        refs = list(reference_images or [])
        if model == IMAGE_MODEL:
            if input_image is None or refs:
                raise ValueError("Seedance image-to-video requires one first frame and cannot combine references")
            if not self._image_ratio_matches(input_image, aspect_ratio):
                raise ValueError("Seedance image-to-video inherits the first frame aspect ratio; image does not match requested aspect_ratio")
            if last_frame_image is not None and not self._image_ratio_matches(last_frame_image, aspect_ratio):
                raise ValueError("Seedance end frame does not match the first frame aspect ratio")
            payload: dict[str, Any] = {
                "prompt": prompt, "duration": duration_seconds,
                "resolution": resolution, "image_url": self._upload_file(input_image),
                "generate_audio": generate_audio,
            }
            if last_frame_image is not None:
                payload["end_image_url"] = self._upload_file(last_frame_image)
            return payload
        if input_image is not None or last_frame_image is not None:
            raise ValueError("Seedance reference-to-video references cannot combine with first/end frames")
        if not refs:
            raise ValueError("Seedance reference-to-video requires at least one image reference")
        return {
            "prompt": prompt, "duration": duration_seconds, "aspect_ratio": aspect_ratio,
            "resolution": resolution, "image_urls": [self._upload_file(path) for path in refs],
            "generate_audio": generate_audio,
        }

    def generate_video(
        self, *, model: str, prompt: str, duration_seconds: int, aspect_ratio: str,
        resolution: str, input_image: Path | None, last_frame_image: Path | None,
        reference_images: list[Path] | None, generate_audio: bool, out_path: Path,
        journal_path: Path, request_digest: str, poll: bool = True,
        poll_every_seconds: float = 2.0, timeout_seconds: float = 900.0,
    ) -> dict[str, Any]:
        if not isinstance(request_digest, str) or not request_digest:
            raise ValueError("request_digest is required")
        fingerprint = self._request_fingerprint(
            model=model, prompt=prompt, duration_seconds=duration_seconds, aspect_ratio=aspect_ratio,
            resolution=resolution, input_image=input_image, last_frame_image=last_frame_image,
            reference_images=reference_images, generate_audio=generate_audio,
        )
        journal: dict[str, Any]
        if journal_path.exists():
            try:
                journal = json.loads(journal_path.read_text(encoding="utf-8"))
            except Exception:
                raise ValueError("Higgsfield journal is unreadable") from None
            if (journal.get("request_digest") != request_digest
                    or journal.get("request_fingerprint") != fingerprint
                    or journal.get("model") != model):
                raise ValueError("Higgsfield journal is bound to a different request identity")
            if journal.get("state") in {"submitting", "uncertain"} and not journal.get("request_id"):
                raise RuntimeError("Higgsfield submission outcome is uncertain; manual recovery is required")
        else:
            journal = {
                "request_digest": request_digest, "request_fingerprint": fingerprint,
                "model": model, "state": "intent", "created_at": time.time(),
            }

        if isinstance(journal.get("payload"), dict):
            payload = journal["payload"]
            payload_digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if journal.get("payload_digest") != payload_digest or journal.get("model") != model:
                raise ValueError("Higgsfield journal payload failed integrity validation")
        else:
            if journal.get("request_id") or journal.get("state") != "intent":
                raise ValueError("Higgsfield journal is missing its saved request payload")
            payload = self._build_payload(
                model=model, prompt=prompt, duration_seconds=duration_seconds, aspect_ratio=aspect_ratio,
                resolution=resolution, input_image=input_image, last_frame_image=last_frame_image,
                reference_images=reference_images, generate_audio=generate_audio,
            )
            payload_digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            journal["payload"] = payload
            journal["payload_digest"] = payload_digest
            self._save_journal(journal_path, journal)

        if not journal.get("request_id"):
            journal["state"] = "submitting"
            self._save_journal(journal_path, journal)
            try:
                response = self._api_request_json(
                    url=f"{self.config.api_base}/{model}", method="POST", headers=self._headers(),
                    json_payload=payload, timeout_seconds=180,
                )
                request_id = response.get("request_id")
                if not isinstance(request_id, str) or not request_id:
                    raise RuntimeError("missing request ID")
                status_url = self._validate_api_url(
                    response.get("status_url") or f"{self.config.api_base}/requests/{request_id}/status",
                    request_id=request_id,
                )
                journal.update({"request_id": request_id, "status_url": status_url, "state": str(response.get("status") or "queued")})
                self._save_journal(journal_path, journal)
            except Exception:
                journal["state"] = "uncertain"
                self._save_journal(journal_path, journal)
                raise RuntimeError("Higgsfield submission outcome is uncertain; it will not be resubmitted automatically") from None
            task = response
        else:
            task = {"request_id": journal["request_id"], "status": journal.get("state", "queued")}

        status = str(task.get("status") or journal.get("state") or "queued").lower()
        has_result = bool(journal.get("result_url")) or (isinstance(task.get("video"), dict) and bool(task["video"].get("url")))
        should_fetch_status = bool(journal.get("request_id")) and status not in {"failed", "nsfw", "canceled"} and (
            (poll and status != "completed") or (status == "completed" and not has_result)
        )
        if should_fetch_status:
            self._validate_api_url(journal.get("status_url", ""), request_id=str(journal.get("request_id")))
            started = time.monotonic()
            delay = max(0.0, poll_every_seconds)
            forced_result_lookup_done = False
            while True:
                status = str(task.get("status") or "").lower()
                has_video = isinstance(task.get("video"), dict) and bool(task["video"].get("url"))
                if status in {"failed", "nsfw", "canceled"} or (status == "completed" and has_video):
                    break
                needs_completed_result = status == "completed" and not has_video and not forced_result_lookup_done
                if (not poll and not needs_completed_result) or time.monotonic() - started > timeout_seconds:
                    break
                try:
                    task = self._api_request_json(
                        url=journal["status_url"], method="GET", headers=self._headers(),
                        json_payload=None, timeout_seconds=60, request_id=str(journal["request_id"]),
                    )
                except Exception:
                    raise RuntimeError("Higgsfield status lookup failed") from None
                status = str(task.get("status") or "").lower()
                if needs_completed_result:
                    forced_result_lookup_done = True
                returned_id = task.get("request_id")
                if returned_id is not None and returned_id != journal["request_id"]:
                    raise RuntimeError("Higgsfield status response did not match the saved request")
                journal["state"] = status or "in_progress"
                if status == "completed" and isinstance(task.get("video"), dict):
                    candidate_url = task["video"].get("url")
                    if candidate_url:
                        journal["result_url"] = _https_url(candidate_url, purpose="output")
                self._save_journal(journal_path, journal)
                has_video = isinstance(task.get("video"), dict) and bool(task["video"].get("url"))
                if status in {"failed", "nsfw", "canceled"} or (status == "completed" and has_video):
                    break
                time.sleep(delay)
                delay = min(10.0, max(2.0, delay * 1.5))

        status = str(task.get("status") or journal.get("state") or "queued").lower()
        journal["state"] = status
        if status == "completed" and isinstance(task.get("video"), dict):
            candidate_url = task["video"].get("url")
            if candidate_url:
                journal["result_url"] = _https_url(candidate_url, purpose="output")
        self._save_journal(journal_path, journal)
        if status in {"failed", "nsfw", "canceled"}:
            error = "Generation failed" if status == "failed" else "Generation was rejected or canceled"
            return {"status": status, "request_id": journal.get("request_id"), "error": error}
        if status != "completed":
            return {"status": status, "request_id": journal.get("request_id")}
        try:
            safe_url = _https_url(journal.get("result_url"), purpose="output")
            data = request_public_media_bytes(url=safe_url, timeout_seconds=600)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix=f".{out_path.name}.", dir=out_path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, out_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        except Exception:
            raise RuntimeError("Higgsfield completed output could not be safely downloaded") from None
        return {"status": "completed", "request_id": journal.get("request_id"), "out_path": str(out_path)}
