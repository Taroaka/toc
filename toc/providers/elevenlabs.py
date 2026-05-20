from __future__ import annotations

import json
import os
import urllib.parse
from dataclasses import dataclass
from typing import Any, Iterable

from toc.http import request_bytes

DEFAULT_ELEVENLABS_VOICE_ID = "JOcmGzB8OFjY8MhjHHEf"  # Jun - Calm, Clear and Husky (ja)
DEFAULT_ELEVENLABS_LANGUAGE_CODE = "ja"
ELEVENLABS_PRONUNCIATION_DICTIONARY_LOCATORS_ENV = "ELEVENLABS_PRONUNCIATION_DICTIONARY_LOCATORS"


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v


def _locator_from_mapping(value: dict[str, Any]) -> dict[str, str]:
    dictionary_id = str(
        value.get("pronunciation_dictionary_id") or value.get("dictionary_id") or value.get("id") or ""
    ).strip()
    version_id = str(value.get("version_id") or value.get("latest_version_id") or "").strip()
    if not dictionary_id or not version_id:
        raise ValueError("pronunciation dictionary locator requires pronunciation_dictionary_id and version_id")
    return {
        "pronunciation_dictionary_id": dictionary_id,
        "version_id": version_id,
    }


def _locator_from_token(token: str) -> dict[str, str]:
    raw = token.strip()
    if not raw:
        raise ValueError("empty pronunciation dictionary locator")
    if raw.startswith("{"):
        loaded = json.loads(raw)
        if not isinstance(loaded, dict):
            raise ValueError("pronunciation dictionary JSON locator must be an object")
        return _locator_from_mapping(loaded)
    for separator in (":", "@", "="):
        if separator in raw:
            dictionary_id, version_id = raw.split(separator, 1)
            return _locator_from_mapping(
                {
                    "pronunciation_dictionary_id": dictionary_id,
                    "version_id": version_id,
                }
            )
    raise ValueError("pronunciation dictionary locator must be id:version_id")


def parse_pronunciation_dictionary_locators(value: Any) -> tuple[dict[str, str], ...]:
    if value is None or value == "":
        return ()
    raw_items: Iterable[Any]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return ()
        if raw.startswith("["):
            loaded = json.loads(raw)
            if not isinstance(loaded, list):
                raise ValueError("pronunciation dictionary locators JSON must be a list")
            raw_items = loaded
        else:
            raw_items = [item for chunk in raw.splitlines() for item in chunk.split(",")]
    elif isinstance(value, (list, tuple)):
        raw_items = value
    else:
        raise ValueError("pronunciation dictionary locators must be a string or list")

    locators: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in raw_items:
        if isinstance(item, dict):
            locator = _locator_from_mapping(item)
        else:
            locator = _locator_from_token(str(item))
        key = (locator["pronunciation_dictionary_id"], locator["version_id"])
        if key in seen:
            continue
        seen.add(key)
        locators.append(locator)
    if len(locators) > 3:
        raise ValueError("ElevenLabs supports up to 3 pronunciation dictionary locators per TTS request")
    return tuple(locators)


@dataclass(frozen=True)
class ElevenLabsConfig:
    api_key: str
    api_base: str = "https://api.elevenlabs.io/v1"
    voice_id: str = DEFAULT_ELEVENLABS_VOICE_ID
    model_id: str = "eleven_v3"
    output_format: str = "mp3_44100_128"
    language_code: str = DEFAULT_ELEVENLABS_LANGUAGE_CODE
    pronunciation_dictionary_locators: tuple[dict[str, str], ...] = ()

    @staticmethod
    def from_env(
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        voice_id: str | None = None,
        model_id: str | None = None,
        output_format: str | None = None,
        language_code: str | None = None,
        pronunciation_dictionary_locators: Any = None,
    ) -> "ElevenLabsConfig":
        key = api_key or _env("ELEVENLABS_API_KEY")
        if not key:
            raise ValueError("Missing ELEVENLABS_API_KEY")
        v_id = (voice_id or _env("ELEVENLABS_VOICE_ID", "") or "").strip()
        if not v_id:
            v_id = DEFAULT_ELEVENLABS_VOICE_ID
        locators_source = (
            pronunciation_dictionary_locators
            if pronunciation_dictionary_locators is not None
            else _env(ELEVENLABS_PRONUNCIATION_DICTIONARY_LOCATORS_ENV)
        )
        return ElevenLabsConfig(
            api_key=key,
            api_base=api_base or _env("ELEVENLABS_API_BASE", "https://api.elevenlabs.io/v1") or "",
            voice_id=v_id,
            model_id=model_id or _env("ELEVENLABS_MODEL_ID", "eleven_v3") or "",
            output_format=output_format or _env("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128") or "",
            language_code=language_code or _env("ELEVENLABS_LANGUAGE_CODE", DEFAULT_ELEVENLABS_LANGUAGE_CODE) or "",
            pronunciation_dictionary_locators=parse_pronunciation_dictionary_locators(locators_source),
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
        language_code: str | None = None,
        pronunciation_dictionary_locators: Any = None,
        voice_settings: dict[str, Any] | None = None,
        timeout_seconds: float = 180.0,
    ) -> bytes:
        v_id = voice_id or self.config.voice_id
        m_id = model_id or self.config.model_id
        fmt = output_format or self.config.output_format
        lang = (
            language_code if language_code is not None else self.config.language_code
        ) or DEFAULT_ELEVENLABS_LANGUAGE_CODE

        base = self.config.api_base.rstrip("/")
        url = f"{base}/text-to-speech/{urllib.parse.quote(v_id)}"
        if fmt:
            url += "?" + urllib.parse.urlencode({"output_format": fmt})

        payload: dict[str, Any] = {
            "text": text,
            "model_id": m_id,
        }
        payload["language_code"] = lang
        locators = (
            parse_pronunciation_dictionary_locators(pronunciation_dictionary_locators)
            if pronunciation_dictionary_locators is not None
            else self.config.pronunciation_dictionary_locators
        )
        if locators:
            payload["pronunciation_dictionary_locators"] = list(locators)
        if voice_settings is not None:
            payload["voice_settings"] = voice_settings

        return request_bytes(
            url=url,
            method="POST",
            headers=self._headers(),
            json_payload=payload,
            timeout_seconds=timeout_seconds,
        )
