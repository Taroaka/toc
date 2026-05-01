import unittest

from toc.script_narration import (
    materialize_elevenlabs_tts_text,
    resolve_script_cut_elevenlabs_prompt,
    resolve_script_metadata_elevenlabs,
    resolve_script_cut_tts_text,
)


class TestScriptNarration(unittest.TestCase):
    def test_materialize_elevenlabs_tts_text_from_structured_prompt(self) -> None:
        actual = materialize_elevenlabs_tts_text(
            spoken_context="かのじょは こえを はずませながら いいました。",
            voice_tags=["excited", "laughs harder"],
            spoken_body="ほんとうに ありがとう！",
        )
        self.assertEqual(actual, "かのじょは こえを はずませながら いいました。 [excited][laughs harder] ほんとうに ありがとう！")

    def test_resolve_script_cut_elevenlabs_prompt_keeps_legacy_tts_text_compatible(self) -> None:
        cut = {
            "tts_text": "むかし、ある むらに しょうねんが いました。",
        }
        prompt = resolve_script_cut_elevenlabs_prompt(cut)
        self.assertEqual(prompt["spoken_context"], "")
        self.assertEqual(prompt["voice_tags"], [])
        self.assertEqual(prompt["spoken_body"], "むかし、ある むらに しょうねんが いました。")
        self.assertEqual(prompt["stability_profile"], "")

    def test_resolve_script_cut_tts_text_prefers_approved_value(self) -> None:
        cut = {
            "tts_text": "かのじょは [whispers] あるきだします。",
            "elevenlabs_prompt": {
                "spoken_context": "かのじょは ためらいながら いいました。",
                "voice_tags": ["whispers"],
                "spoken_body": "あるきだします。",
                "stability_profile": "creative",
            },
            "human_review": {
                "approved_tts_text": "[whispers] しょうにんずみです。",
            },
        }
        self.assertEqual(resolve_script_cut_tts_text(cut), "[whispers] しょうにんずみです。")

    def test_resolve_script_metadata_elevenlabs_merges_defaults(self) -> None:
        script_data = {
            "script_metadata": {
                "elevenlabs": {
                    "model_id": "eleven_v3",
                    "default_stability_profile": "natural",
                }
            }
        }
        actual = resolve_script_metadata_elevenlabs(script_data)
        self.assertEqual(actual["provider"], "elevenlabs")
        self.assertEqual(actual["model_id"], "eleven_v3")
        self.assertEqual(actual["voice_name"], "Shohei - Warm, Clear and Husky")
        self.assertEqual(actual["voice_id"], "8FuuqoKHuM48hIEwni5e")
        self.assertEqual(actual["prompt_contract_version"], "v3_tagged_context_v1")
        self.assertEqual(actual["default_stability_profile"], "natural")
        self.assertEqual(actual["text_policy"], "natural_japanese_plus_audio_tags")
