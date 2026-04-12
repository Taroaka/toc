from __future__ import annotations

import base64
import os
import time
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from toc.http import request_bytes, request_json


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str
    api_base: str = "https://generativelanguage.googleapis.com/v1beta"
    image_model: str = "gemini-3-pro-image-preview"
    video_model: str = "veo-3.1-generate-preview"

    @staticmethod
    def from_env(
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        image_model: str | None = None,
        video_model: str | None = None,
    ) -> "GeminiConfig":
        key = api_key or _env("GEMINI_API_KEY")
        if not key:
            raise ValueError("Missing GEMINI_API_KEY")
        return GeminiConfig(
            api_key=key,
            api_base=api_base or _env("GEMINI_API_BASE", "https://generativelanguage.googleapis.com/v1beta") or "",
            image_model=image_model or _env("GEMINI_IMAGE_MODEL", "gemini-3-pro-image-preview") or "",
            video_model=video_model or _env("GEMINI_VIDEO_MODEL", "veo-3.1-generate-preview") or "",
        )


def _guess_mime(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".png":
        return "image/png"
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    return "application/octet-stream"


def _encode_reference_image(
    path: Path,
    *,
    max_side_px: int = 1536,
    jpeg_quality: int = 82,
) -> tuple[str, str]:
    raw = path.read_bytes()
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img = img.convert("RGBA") if img.mode in {"P", "LA"} else img.copy()
            if max(img.size) > max_side_px:
                img.thumbnail((max_side_px, max_side_px), Image.Resampling.LANCZOS)

            has_alpha = "A" in img.getbands()
            out = io.BytesIO()
            if has_alpha:
                img.save(out, format="PNG", optimize=True)
                mime = "image/png"
            else:
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(out, format="JPEG", quality=jpeg_quality, optimize=True)
                mime = "image/jpeg"
            return mime, base64.b64encode(out.getvalue()).decode("ascii")
    except Exception:
        return _guess_mime(path), base64.b64encode(raw).decode("ascii")


def _extract_first_inline_image(resp: dict[str, Any]) -> tuple[bytes, str | None]:
    candidates = resp.get("candidates") or []
    for cand in candidates:
        content = cand.get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data")
            if not inline:
                continue
            b64 = inline.get("data")
            if not b64:
                continue
            mime = inline.get("mimeType") or inline.get("mime_type")
            return base64.b64decode(b64), mime
    raise ValueError("No inline image found in Gemini response.")


def _extract_video_uri(operation: dict[str, Any]) -> str:
    resp = operation.get("response") or {}
    gvr = resp.get("generateVideoResponse") or resp.get("generate_video_response") or {}
    samples = gvr.get("generatedSamples") or gvr.get("generated_samples") or []
    if samples and isinstance(samples[0], dict):
        video = samples[0].get("video") or {}
        uri = video.get("uri")
        if uri:
            return str(uri)
    raise ValueError("Operation completed but no video URI found.")


class GeminiClient:
    def __init__(self, config: GeminiConfig):
        self.config = config

    @staticmethod
    def from_env(**overrides: Any) -> "GeminiClient":
        return GeminiClient(GeminiConfig.from_env(**overrides))

    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.config.api_key}

    def generate_image(
        self,
        *,
        prompt: str,
        aspect_ratio: str = "9:16",
        image_size: str = "2K",
        reference_images: list[Path] | None = None,
        model: str | None = None,
        timeout_seconds: float = 180.0,
    ) -> tuple[bytes, str | None, dict[str, Any]]:
        model_name = model or self.config.image_model
        url = f"{self.config.api_base.rstrip('/')}/models/{model_name}:generateContent"
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for ref in reference_images or []:
            mime, b64 = _encode_reference_image(ref)
            parts.append({"inlineData": {"mimeType": mime, "data": b64}})
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseModalities": ["Image"],
                "imageConfig": {"aspectRatio": aspect_ratio, "imageSize": image_size},
            },
        }
        resp = request_json(
            url=url,
            method="POST",
            headers={"content-type": "application/json", **self._headers()},
            json_payload=payload,
            timeout_seconds=timeout_seconds,
        )
        image_bytes, mime_type = _extract_first_inline_image(resp)
        return image_bytes, mime_type, resp

    def start_video_generation(
        self,
        *,
        prompt: str,
        duration_seconds: int,
        aspect_ratio: str = "9:16",
        resolution: str = "720p",
        input_image: Path | None = None,
        last_frame_image: Path | None = None,
        input_image_format: str = "inlineData",
        last_frame_field: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 180.0,
    ) -> dict[str, Any]:
        model_name = model or self.config.video_model
        url = f"{self.config.api_base.rstrip('/')}/models/{model_name}:predictLongRunning"
        instance: dict[str, Any] = {"prompt": prompt}
        if input_image is not None:
            mime = _guess_mime(input_image)
            b64 = base64.b64encode(input_image.read_bytes()).decode("ascii")
            if input_image_format == "inlineData":
                instance["image"] = {"inlineData": {"mimeType": mime, "data": b64}}
            elif input_image_format == "bytesBase64Encoded":
                instance["image"] = {"mimeType": mime, "bytesBase64Encoded": b64}
            elif input_image_format == "imageBytes":
                instance["imageBytes"] = b64
                instance["imageMimeType"] = mime
            else:
                raise ValueError(f"Unsupported input_image_format: {input_image_format}")
        if last_frame_image is not None:
            # Best-effort: Veo 3.1 may support end-frame conditioning. Field name can vary by API version.
            # Allow override via env for future compatibility.
            end_field = last_frame_field or (_env("GEMINI_VEO_LAST_IMAGE_FIELD", "endImage") or "endImage")
            mime = _guess_mime(last_frame_image)
            b64 = base64.b64encode(last_frame_image.read_bytes()).decode("ascii")
            if input_image_format == "inlineData":
                instance[end_field] = {"inlineData": {"mimeType": mime, "data": b64}}
            elif input_image_format == "bytesBase64Encoded":
                instance[end_field] = {"mimeType": mime, "bytesBase64Encoded": b64}
            elif input_image_format == "imageBytes":
                # Not sure this is supported; include a sibling field name for symmetry.
                instance[f"{end_field}Bytes"] = b64
                instance[f"{end_field}MimeType"] = mime
            else:
                raise ValueError(f"Unsupported input_image_format: {input_image_format}")
        payload = {
            "instances": [instance],
            "parameters": {
                "durationSeconds": int(duration_seconds),
                "aspectRatio": aspect_ratio,
                "resolution": resolution,
            },
        }
        return request_json(
            url=url,
            method="POST",
            headers={"content-type": "application/json", **self._headers()},
            json_payload=payload,
            timeout_seconds=timeout_seconds,
        )

    def poll_operation(
        self,
        *,
        op_name_or_url: str,
        poll_every_seconds: float = 5.0,
        timeout_seconds: float = 900.0,
    ) -> dict[str, Any]:
        op_url = (
            op_name_or_url
            if op_name_or_url.startswith("http")
            else f"{self.config.api_base.rstrip('/')}/{op_name_or_url.lstrip('/')}"
        )
        deadline = time.time() + float(timeout_seconds)
        while True:
            op = request_json(url=op_url, method="GET", headers=self._headers(), timeout_seconds=180.0)
            if op.get("done") is True:
                return op
            if time.time() > deadline:
                raise TimeoutError(f"Timed out waiting for operation: {op_name_or_url}")
            time.sleep(float(poll_every_seconds))

    def extract_video_uri(self, operation: dict[str, Any]) -> str:
        return _extract_video_uri(operation)

    def download_to_file(self, *, uri: str, out_path: Path, timeout_seconds: float = 600.0) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        data = request_bytes(url=uri, method="GET", headers=self._headers(), timeout_seconds=timeout_seconds)
        out_path.write_bytes(data)
