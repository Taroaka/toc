import tempfile
import unittest
from pathlib import Path

from toc.tts_text import (
    PronunciationAlias,
    load_pronunciation_aliases,
    parse_pronunciation_aliases,
    prepare_elevenlabs_tts_text,
)


class TestTtsText(unittest.TestCase):
    def test_parse_pronunciation_aliases_from_tsv(self) -> None:
        aliases = parse_pronunciation_aliases("売上\tうりあげ\n取得=>しゅとく\n")
        self.assertEqual(
            aliases,
            (
                PronunciationAlias(surface="売上", alias="うりあげ"),
                PronunciationAlias(surface="取得", alias="しゅとく"),
            ),
        )

    def test_prepare_elevenlabs_tts_text_applies_longest_alias_first(self) -> None:
        prepared = prepare_elevenlabs_tts_text(
            "売上を取得しました。",
            pronunciation_aliases=(
                PronunciationAlias(surface="売上", alias="うりあげ"),
                PronunciationAlias(surface="売上を取得", alias="うりあげをしゅとく"),
            ),
        )
        self.assertEqual(prepared.text, "うりあげをしゅとくしました。")
        self.assertEqual(prepared.applied_aliases, ("売上を取得",))

    def test_load_pronunciation_aliases_from_json_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_tts_aliases_") as td:
            path = Path(td) / "aliases.json"
            path.write_text('{"aliases": [{"surface": "Claude Code", "alias": "クロードコード"}]}', encoding="utf-8")

            aliases = load_pronunciation_aliases(path)

        self.assertEqual(aliases, (PronunciationAlias(surface="Claude Code", alias="クロードコード"),))


if __name__ == "__main__":
    unittest.main()
