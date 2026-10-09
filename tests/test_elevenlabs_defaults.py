import os
import unittest
from unittest.mock import patch

from toc.providers.elevenlabs import (
    DEFAULT_ELEVENLABS_LANGUAGE_CODE,
    DEFAULT_ELEVENLABS_MODEL_ID,
    DEFAULT_ELEVENLABS_VOICE_ID,
    ElevenLabsClient,
    ElevenLabsConfig,
    normalize_elevenlabs_model_id,
    normalize_elevenlabs_voice_settings,
    parse_pronunciation_dictionary_locators,
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

    def test_from_env_defaults_to_eleven_v4_model(self) -> None:
        old = os.environ.get("ELEVENLABS_MODEL_ID")
        try:
            os.environ.pop("ELEVENLABS_MODEL_ID", None)
            cfg = ElevenLabsConfig.from_env(api_key="test_key")
            self.assertEqual(cfg.model_id, DEFAULT_ELEVENLABS_MODEL_ID)
            self.assertEqual(cfg.model_id, "eleven_v4")
        finally:
            if old is None:
                os.environ.pop("ELEVENLABS_MODEL_ID", None)
            else:
                os.environ["ELEVENLABS_MODEL_ID"] = old

    def test_legacy_v3_model_selection_is_migrated_to_v4(self) -> None:
        self.assertEqual(normalize_elevenlabs_model_id("eleven_v3"), "eleven_v4")
        cfg = ElevenLabsConfig.from_env(api_key="test_key", model_id="eleven_v3")
        self.assertEqual(cfg.model_id, "eleven_v4")

        client = ElevenLabsClient(ElevenLabsConfig(api_key="test_key", model_id="eleven_v3"))
        with patch("toc.providers.elevenlabs.request_bytes", return_value=b"audio") as request_bytes:
            client.tts(text="こんにちは")
        payload = request_bytes.call_args.kwargs["json_payload"]
        self.assertEqual(payload["model_id"], "eleven_v4")

    def test_v4_drops_legacy_voice_settings(self) -> None:
        self.assertEqual(
            normalize_elevenlabs_voice_settings(
                {
                    "stability": 0.35,
                    "similarity_boost": 0.75,
                    "style": 0.4,
                    "speed": 1.1,
                    "use_speaker_boost": True,
                },
                model_id="eleven_v4",
            ),
            {"stability": 0.35, "similarity_boost": 0.75},
        )

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

    def test_parse_pronunciation_dictionary_locators_accepts_id_version_tokens(self) -> None:
        locators = parse_pronunciation_dictionary_locators("dict_1:ver_1,dict_2:ver_2")
        self.assertEqual(
            locators,
            (
                {"pronunciation_dictionary_id": "dict_1", "version_id": "ver_1"},
                {"pronunciation_dictionary_id": "dict_2", "version_id": "ver_2"},
            ),
        )

    def test_tts_sends_pronunciation_dictionary_locators(self) -> None:
        client = ElevenLabsClient(
            ElevenLabsConfig(
                api_key="test_key",
                pronunciation_dictionary_locators=(
                    {"pronunciation_dictionary_id": "dict_1", "version_id": "ver_1"},
                ),
            )
        )

        with patch("toc.providers.elevenlabs.request_bytes", return_value=b"audio") as request_bytes:
            client.tts(text="こんにちは")

        payload = request_bytes.call_args.kwargs["json_payload"]
        self.assertEqual(
            payload["pronunciation_dictionary_locators"],
            [{"pronunciation_dictionary_id": "dict_1", "version_id": "ver_1"}],
        )

    def test_tts_sends_adjacent_text_for_chunk_prosody_continuity(self) -> None:
        client = ElevenLabsClient(ElevenLabsConfig(api_key="test_key"))

        with patch("toc.providers.elevenlabs.request_bytes", return_value=b"audio") as request_bytes:
            client.tts(
                text="いまの文です。",
                previous_text="ひとつ前の文です。",
                next_text="次の文です。",
            )

        payload = request_bytes.call_args.kwargs["json_payload"]
        self.assertEqual(payload["previous_text"], "ひとつ前の文です。")
        self.assertEqual(payload["next_text"], "次の文です。")


if __name__ == "__main__":
    unittest.main()
