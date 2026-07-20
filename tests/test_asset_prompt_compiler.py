from __future__ import annotations

import unittest

from toc.asset_prompt_compiler import compile_asset_prompt


class AssetPromptCompilerTests(unittest.TestCase):
    def test_explicit_prompt_is_prefixed_with_nonempty_story_time(self) -> None:
        prompt = compile_asset_prompt(
            {"generation_prompt": "人物の全身参照を実写で作る。"},
            topic_label="シンデレラ",
            story_time="17世紀末フランス・ルイ14世時代",
        )

        self.assertIn("物語の時代背景は17世紀末フランス・ルイ14世時代", prompt)
        self.assertIn("人物の全身参照を実写で作る。", prompt)

    def test_explicit_prompt_does_not_duplicate_existing_story_time(self) -> None:
        story_time = "江戸時代"
        prompt = compile_asset_prompt(
            {"generation_prompt": f"{story_time}の町人の全身参照。"},
            topic_label="創作",
            story_time=story_time,
        )

        self.assertEqual(prompt.count(story_time), 1)

    def test_empty_story_time_leaves_explicit_prompt_unchanged(self) -> None:
        explicit = "時代を限定しない架空世界の場所参照。"

        self.assertEqual(
            compile_asset_prompt(
                {"generation_prompt": explicit},
                topic_label="ユーザー創作",
                story_time="",
            ),
            explicit,
        )


if __name__ == "__main__":
    unittest.main()
