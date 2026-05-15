import os
import unittest
from unittest.mock import patch

from toc.providers.elevenlabs import (
    DEFAULT_ELEVENLABS_LANGUAGE_CODE,
    DEFAULT_ELEVENLABS_VOICE_ID,
    ElevenLabsClient,
    ElevenLabsConfig,
)


class TestElevenLabsDefaults(unittest.TestCase):
    def test_from_env_falls_back_to_default_voice_id(self) -> None:
        old = os.environ.get("ELEVENLABS_VOICE_ID")
        try:
            if "ELEVENLABS_VOICE_ID" in os.environ:
                del os.environ["ELEVENLABS_VOICE_ID"]
            cfg = ElevenLabsConfig.from_env(api_key="test_key")
            self.assertEqual(cfg.voice_id, DEFAULT_ELEVENLABS_VOICE_ID)
        finally:
            if old is None:
                os.environ.pop("ELEVENLABS_VOICE_ID", None)
            else:
                os.environ["ELEVENLABS_VOICE_ID"] = old

    def test_from_env_defaults_to_eleven_v3_model(self) -> None:
        old = os.environ.get("ELEVENLABS_MODEL_ID")
        try:
            os.environ.pop("ELEVENLABS_MODEL_ID", None)
            cfg = ElevenLabsConfig.from_env(api_key="test_key")
            self.assertEqual(cfg.model_id, "eleven_v3")
        finally:
            if old is None:
                os.environ.pop("ELEVENLABS_MODEL_ID", None)
            else:
                os.environ["ELEVENLABS_MODEL_ID"] = old

    def test_from_env_defaults_to_japanese_language_code(self) -> None:
        old = os.environ.get("ELEVENLABS_LANGUAGE_CODE")
        try:
            os.environ.pop("ELEVENLABS_LANGUAGE_CODE", None)
            cfg = ElevenLabsConfig.from_env(api_key="test_key")
            self.assertEqual(cfg.language_code, DEFAULT_ELEVENLABS_LANGUAGE_CODE)
            self.assertEqual(cfg.language_code, "ja")
        finally:
            if old is None:
                os.environ.pop("ELEVENLABS_LANGUAGE_CODE", None)
            else:
                os.environ["ELEVENLABS_LANGUAGE_CODE"] = old

    def test_tts_sends_japanese_language_code(self) -> None:
        client = ElevenLabsClient(ElevenLabsConfig(api_key="test_key"))

        with patch("toc.providers.elevenlabs.request_bytes", return_value=b"audio") as request_bytes:
            audio = client.tts(text="こんにちは")

        self.assertEqual(audio, b"audio")
        payload = request_bytes.call_args.kwargs["json_payload"]
        self.assertEqual(payload["language_code"], "ja")

    def test_tts_falls_back_to_japanese_when_config_language_is_blank(self) -> None:
        client = ElevenLabsClient(ElevenLabsConfig(api_key="test_key", language_code=""))

        with patch("toc.providers.elevenlabs.request_bytes", return_value=b"audio") as request_bytes:
            client.tts(text="こんにちは")

        payload = request_bytes.call_args.kwargs["json_payload"]
        self.assertEqual(payload["language_code"], "ja")


if __name__ == "__main__":
    unittest.main()
