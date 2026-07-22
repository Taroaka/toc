from __future__ import annotations

import unittest

from toc.asset_prompt_compiler import compile_asset_prompt


class AssetPromptCompilerTests(unittest.TestCase):
    def test_ensemble_character_keeps_multiple_identities_in_reference_sheet(self) -> None:
        prompt = compile_asset_prompt(
            {
                "asset_type": "character_reference",
                "story_purpose": "主人公へ圧力をかける二人組",
                "subject_contract": {
                    "identity_scope": "ensemble",
                    "subject_count": 2,
                    "member_ids": ["older_sister", "younger_sister"],
                },
                "appearance_contract": {
                    "social_position": "裕福な商家の娘",
                    "occupation_or_role": "競争者",
                    "occasion_or_state": "外出前の正装",
                    "silhouette": "二人を異なる輪郭と髪型で識別できる",
                    "materials": ["絹", "レース"],
                    "condition": "手入れされている",
                    "palette": ["深紅", "青緑"],
                    "must_avoid": ["二人を同じ顔にしない"],
                },
                "visual_spec": {"subject": "姉妹二人の全身参照"},
                "generation_plan": {"reference_inputs": []},
            },
            topic_label="古典物語",
            story_time="17世紀末フランス",
        )

        self.assertIn("2人をそれぞれ別人として", prompt)
        self.assertIn("各人物の正面・側面・背面", prompt)
        self.assertNotIn("主対象は人物1人", prompt)
        self.assertNotIn("生活感のある衣装", prompt)

    def test_role_specific_appearance_contract_is_rendered(self) -> None:
        prompt = compile_asset_prompt(
            {
                "asset_type": "character_reference",
                "subject_contract": {
                    "identity_scope": "individual",
                    "subject_count": 1,
                    "member_ids": ["court_heir"],
                },
                "appearance_contract": {
                    "social_position": "王位継承者",
                    "occupation_or_role": "宮廷の公人",
                    "occasion_or_state": "夜会の礼装",
                    "silhouette": "直立した細身の宮廷服",
                    "materials": ["絹", "銀糸"],
                    "condition": "仕立て直後",
                    "palette": ["深紺", "銀"],
                    "must_avoid": ["労働着"],
                },
                "visual_spec": {"subject": "若い王子の全身参照"},
                "generation_plan": {"reference_inputs": []},
            },
            topic_label="古典物語",
            story_time="17世紀末フランス",
        )

        for expected in ("王位継承者", "夜会の礼装", "絹、銀糸", "深紺、銀", "労働着"):
            self.assertIn(expected, prompt)
        self.assertNotIn("生活感のある衣装", prompt)

    def test_neutral_reusable_asset_rejects_scene_specific_lighting(self) -> None:
        entry = {
            "asset_type": "object_reference",
            "reuse_contract": {
                "mode": "neutral_anchor",
                "time_of_day": "",
                "derived_from_asset_id": "",
            },
            "visual_spec": {"subject": "重い馬車、月光を受ける車輪"},
        }

        with self.assertRaisesRegex(ValueError, "asset_prompt_scene_time_leak"):
            compile_asset_prompt(entry, topic_label="物語", story_time="17世紀")

    def test_time_variant_uses_explicit_contract_instead_of_keyword_inference(self) -> None:
        prompt = compile_asset_prompt(
            {
                "asset_type": "location_reference",
                "reuse_contract": {
                    "mode": "time_variant",
                    "time_of_day": "真夜中",
                    "derived_from_asset_id": "palace_stairs_neutral",
                },
                "visual_spec": {"subject": "宮殿の大階段、人物なし"},
            },
            topic_label="物語",
            story_time="17世紀",
        )

        self.assertIn("この素材の時間帯は真夜中", prompt)
        self.assertIn("派生元の場所参照画像", prompt)
        self.assertNotIn("palace_stairs_neutral", prompt)
        self.assertNotIn("深夜または夜として生成する", prompt)

    def test_explicit_prompt_cannot_bypass_neutral_time_leak_gate(self) -> None:
        with self.assertRaisesRegex(ValueError, "asset_prompt_scene_time_leak"):
            compile_asset_prompt(
                {
                    "asset_type": "object_reference",
                    "generation_prompt": "月明かりを受ける馬車の単体参照。",
                    "reuse_contract": {"mode": "neutral_anchor", "time_of_day": ""},
                },
                topic_label="物語",
                story_time="17世紀",
            )

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
