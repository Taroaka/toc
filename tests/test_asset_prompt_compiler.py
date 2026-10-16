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

        self.assertIn("2体のキャラクター群", prompt)
        self.assertIn("各memberの正面・側面・背面", prompt)
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

    def test_clothing_state_variant_keeps_parent_reference_without_locking_parent_costume(self) -> None:
        reference = "assets/characters/messenger.png"
        entry = {
            "asset_type": "character_reference",
            "generation_prompt": "同じ人物の外套だけを濡れた状態にする。",
            "reuse_contract": {"mode": "state_variant", "derived_from_asset_id": "messenger"},
            "state_transition": {"from_state": "外套が乾いている", "to_state": "外套が濡れている"},
            "subject_contract": {"identity_scope": "individual", "subject_count": 1, "member_ids": []},
            "appearance_contract": {
                "cast_design_schema_version": "cast_design_v1",
                "age_impression": "middle-aged",
                "face_shape": "broad angular face",
                "hair": "close-cropped silver hair",
                "build_silhouette": "broad shoulders",
                "palette_costume": "ochre travel mantle over charcoal clothing",
                "identifying_features": "creased dispatch tube across the chest",
                "intentional_similarities": [],
                "distinguish_from": [],
            },
            "generation_plan": {"reference_inputs": [reference]},
        }
        prompt = compile_asset_prompt(
            entry,
            topic_label="generic cast",
        )

        self.assertIn("派生元の対象参照画像から同一性と主要形状を保ち", prompt)
        self.assertIn("外套が乾いている", prompt)
        self.assertIn("外套が濡れている", prompt)
        self.assertIn("明示された特徴変化を優先", prompt)
        self.assertNotIn("broad angular face", prompt)
        self.assertNotIn("close-cropped silver hair", prompt)
        self.assertNotIn("ochre travel mantle over charcoal clothing", prompt)
        self.assertEqual(entry["generation_plan"]["reference_inputs"], [reference])

    def test_animal_to_human_variant_honors_authored_anatomy_change(self) -> None:
        prompt = compile_asset_prompt(
            {
                "asset_type": "character_reference",
                "generation_prompt": "小鳥の姿から、人間の子どもの姿へ変わる。二本の腕と二本の脚を持つ人間の身体にする。",
                "reuse_contract": {"mode": "state_variant", "derived_from_asset_id": "messenger"},
                "state_transition": {
                    "from_state": "青灰色の羽毛を持つ小鳥",
                    "to_state": "人間の子ども",
                },
                "appearance_contract": {
                    "cast_design_schema_version": "cast_design_v1",
                    "age_impression": "mature adult bird",
                    "face_shape": "short hooked beak profile",
                    "hair": "blue-gray feathers with a pale throat",
                    "build_silhouette": "compact bird body, wings, and long tail",
                    "palette_costume": "blue-gray plumage, no clothing",
                    "identifying_features": "white feather stripe above the right eye",
                },
                "generation_plan": {"reference_inputs": ["assets/characters/messenger.png"]},
            },
            topic_label="generic transformation",
        )

        self.assertIn("人間の子どもの姿", prompt)
        self.assertIn("二本の腕と二本の脚", prompt)
        self.assertNotIn("short hooked beak profile", prompt)
        self.assertNotIn("blue-gray feathers with a pale throat", prompt)
        self.assertNotIn("compact bird body, wings, and long tail", prompt)

    def test_age_and_hair_variant_does_not_restore_parent_age_or_hair(self) -> None:
        prompt = compile_asset_prompt(
            {
                "asset_type": "character_reference",
                "generation_prompt": "同じ人物が年老いた姿になり、髪は銀色の長い編み髪へ変わる。顔と体格の同一性は保つ。",
                "reuse_contract": {"mode": "state_variant", "derived_from_asset_id": "traveler"},
                "state_transition": {
                    "from_state": "若い成人で黒い短髪",
                    "to_state": "高齢で銀色の長い編み髪",
                },
                "appearance_contract": {
                    "cast_design_schema_version": "cast_design_v1",
                    "age_impression": "young adult",
                    "face_shape": "long oval face",
                    "hair": "short black hair",
                    "build_silhouette": "slim upright silhouette",
                    "palette_costume": "dark travel clothing",
                    "identifying_features": "small mole under the left eye",
                },
                "generation_plan": {"reference_inputs": ["assets/characters/traveler.png"]},
            },
            topic_label="generic aging state",
        )

        self.assertIn("高齢で銀色の長い編み髪", prompt)
        self.assertIn("顔と体格の同一性は保つ", prompt)
        self.assertNotIn("young adult", prompt)
        self.assertNotIn("short black hair", prompt)
        self.assertNotIn("dark travel clothing", prompt)

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

    def test_neutral_asset_preserves_period_context_without_treating_chronology_as_light(self) -> None:
        period = "年代を特定しない昔。深夜の出来事を描く。王朝は指定しない。"
        subject = f"旅人の全身参照。実写映画の同一人物として固定し、{period}の衣装・髪型・素材・身分表現を守る"
        entry = {
            "asset_type": "character_reference",
            "reuse_contract": {"mode": "neutral_anchor"},
            "visual_spec": {"subject": subject},
            "fixed_prompts": [subject],
        }
        prompt = compile_asset_prompt(entry, topic_label="創作", story_time=period)
        self.assertIn(period, prompt)
        self.assertIn("時間帯の記述を照明指定として使わない", prompt)
        self.assertIn("中性的な参照照明", prompt)
        # A lighting directive outside the exact adapter period clause still fails.
        entry["fixed_prompts"].append("月光を顔に当てる")
        with self.assertRaisesRegex(ValueError, "asset_prompt_scene_time_leak"):
            compile_asset_prompt(entry, topic_label="創作", story_time=period)

    def test_period_context_exception_cannot_hide_explicit_scene_light(self) -> None:
        period = "月光"
        for field in ("generation_prompt", "fixed_prompts"):
            entry = {
                "asset_type": "object_reference",
                "reuse_contract": {"mode": "neutral_anchor"},
                field: period if field == "generation_prompt" else [period],
            }
            with self.assertRaisesRegex(ValueError, "asset_prompt_scene_time_leak"):
                compile_asset_prompt(entry, topic_label="創作", story_time=period)

    def test_neutral_explicit_prompt_receives_lighting_contract(self) -> None:
        prompt = compile_asset_prompt({
            "asset_type": "object_reference",
            "reuse_contract": {"mode": "neutral_anchor"},
            "generation_prompt": "革の旅行鞄の単体参照。",
        }, topic_label="創作")
        self.assertIn("中性的な参照照明", prompt)
        self.assertIn("革の旅行鞄", prompt)

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
