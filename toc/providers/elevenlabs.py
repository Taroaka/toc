from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass
from typing import Any

from toc.http import request_bytes

DEFAULT_ELEVENLABS_VOICE_ID = "JOcmGzB8OFjY8MhjHHEf"  # Jun - Calm, Clear and Husky (ja)


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


@dataclass(frozen=True)
class ElevenLabsConfig:
    api_key: str
    api_base: str = "https://api.elevenlabs.io/v1"
    voice_id: str = DEFAULT_ELEVENLABS_VOICE_ID
    model_id: str = "eleven_v3"
    output_format: str = "mp3_44100_128"

    @staticmethod
    def from_env(
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
        output_format: str | None = None,
    ) -> "ElevenLabsConfig":
        key = api_key or _env("ELEVENLABS_API_KEY")
        if not key:
            raise ValueError("Missing ELEVENLABS_API_KEY")
        v_id = (voice_id or _env("ELEVENLABS_VOICE_ID", "") or "").strip()
        if not v_id:
            v_id = DEFAULT_ELEVENLABS_VOICE_ID
        return ElevenLabsConfig(
            api_key=key,
            api_base=api_base or _env("ELEVENLABS_API_BASE", "https://api.elevenlabs.io/v1") or "",
            voice_id=v_id,
            model_id=model_id or _env("ELEVENLABS_MODEL_ID", "eleven_v3") or "",
            output_format=output_format or _env("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128") or "",
        )


class ElevenLabsClient:
    def __init__(self, config: ElevenLabsConfig):
        self.config = config

    @staticmethod
    def from_env(**overrides: Any) -> "ElevenLabsClient":
        return ElevenLabsClient(ElevenLabsConfig.from_env(**overrides))

    def _headers(self) -> dict[str, str]:
        return {
            "xi-api-key": self.config.api_key,
            "content-type": "application/json",
            "accept": "audio/mpeg",
        }

    def tts(
        self,
        *,
        text: str,
        voice_id: str | None = None,
        model_id: str | None = None,
        output_format: str | None = None,
        voice_settings: dict[str, Any] | None = None,
        timeout_seconds: float = 180.0,
    ) -> bytes:
        v_id = voice_id or self.config.voice_id
        m_id = model_id or self.config.model_id
        fmt = output_format or self.config.output_format

        base = self.config.api_base.rstrip("/")
        url = f"{base}/text-to-speech/{urllib.parse.quote(v_id)}"
        if fmt:
            url += "?" + urllib.parse.urlencode({"output_format": fmt})

        payload: dict[str, Any] = {
            "text": text,
            "model_id": m_id,
        }
        if voice_settings is not None:
            payload["voice_settings"] = voice_settings

        return request_bytes(
            url=url,
            method="POST",
            headers=self._headers(),
            json_payload=payload,
            timeout_seconds=timeout_seconds,
        )
