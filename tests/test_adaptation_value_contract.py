import sys
import unittest
import importlib.util
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.adaptation_value_contract import (
    ADAPTATION_VALUE_MARKER,
    manifest_adaptation_issues,
    script_adaptation_issues,
    source_value_ids,
    story_adaptation_issues,
    visual_value_adaptation_issues,
)
from toc.harness import load_structured_document
from toc.stage_evaluation.research_story import check_story, check_visual_value
from toc.stage_evaluation import pipeline as pipeline_evaluation
from toc.stage_evaluation.script import check_script_single
from toc.stage_evaluation.manifest import check_manifest_single


def _story() -> dict:
    return {
        "story_metadata": {"adaptation_value_contract": ADAPTATION_VALUE_MARKER},
        "adaptation_source_contract": {
            "schema_version": "adaptation_source_contract_v1",
            "mode": "existing_story",
            "source_story_promise": "善意を失わない主人公が、尊厳と居場所を取り戻す。",
            "core_values": [
                {
                    "value_id": "value_dignity_seen",
                    "statement": "虐げられても失われなかった尊厳が他者に認識される。",
                    "audience_effect": "耐えてきた時間が報われた安堵と高揚。",
                    "source_event_refs": ["event_ball_recognition", "event_slipper_proof"],
                }
            ],
            "non_negotiable_events": ["舞踏会で互いを選ぶ", "靴が本人の証拠になる"],
            "non_negotiable_meanings": ["救済は外見だけでなく、主人公の尊厳の承認である"],
            "iconic_moments": ["変身", "真夜中の退場", "靴による照合"],
            "forbidden_value_distortions": ["主人公を受動的な賞品としてだけ描く"],
        },
    }


def _scene_amplification() -> dict:
    return {
        "schema_version": "scene_value_amplification_v1",
        "source_value_refs": ["value_dignity_seen"],
        "why_this_scene_matters": "隠されていた尊厳が、公の場で初めて見える。",
        "audience_state_before": "主人公は誰にも見つけられないと思っている。",
        "audience_state_after": "主人公自身の存在が選ばれたと理解する。",
        "emotional_contradiction": "幸福の最中に、失う時刻が迫る。",
        "cinematic_gain": {
            "performance": "期待を抑える呼吸が、視線を受けて一度だけほどける。",
            "blocking_and_space": "群衆が割れ、二人の間に一本の進路が生まれる。",
            "camera_and_composition": "孤立した端の構図から、対等な二人の構図へ移る。",
            "edit_and_rhythm": "認識の前だけ編集を止め、反応を待つ。",
            "sound": "祝宴の音を遠ざけ、呼吸と一歩目を前景化する。",
        },
        "iconic_moment_target": "群衆の中で二人の視線だけが結ばれる瞬間。",
        "must_preserve_story_facts": ["二人はこの場で互いを選ぶ"],
        "must_not_reduce_to": ["豪華な会場を見せるだけの説明映像"],
        "success_evidence": ["台詞なしでも主人公が認識されたと分かる"],
    }


def _visual_value() -> dict:
    return {
        "visual_value_metadata": {"adaptation_value_contract": ADAPTATION_VALUE_MARKER},
        "adaptation_intent": {
            "schema_version": "adaptation_intent_v1",
            "source_value_ids": ["value_dignity_seen"],
            "effect_fidelity_goal": "原作の承認の喜びを、観客の身体感覚として再体験させる。",
            "adaptation_angle": "主人公が見られる側から、自分も選び返す側へ変わる過程を強調する。",
            "visual_principles": ["空間内の距離変化で関係の変化を見せる"],
            "performance_principles": ["感情名ではなく抑制と解放の差で演じる"],
            "sound_principles": ["価値が反転する直前に環境音の密度を下げる"],
            "editorial_principles": ["反応を出来事より先に切らない"],
            "forbidden_generic_treatments": ["豪華さだけで感動を代替する"],
        },
        "scene_visual_values": [
            {"scene_selector": "scene01", "scene_value_amplification": _scene_amplification()}
        ],
    }


def _script() -> dict:
    return {
        "script_metadata": {"adaptation_value_contract": ADAPTATION_VALUE_MARKER},
        "scenes": [
            {
                "scene_id": "1",
                "scene_intent": {"scene_value_amplification": _scene_amplification()},
                "cuts": [
                    {
                        "cut_id": "1",
                        "cut_contract": {
                            "expressive_contract": {
                                "schema_version": "cut_expressive_contract_v1",
                                "source_value_refs": ["value_dignity_seen"],
                                "scene_amplification_ref": "scene1.scene_intent.scene_value_amplification",
                                "audience_experience_delta": "孤立から、互いを認識した緊張へ。",
                                "expressive_function": "recognition",
                                "performance_beat": "呼吸を止めた後、視線だけを返す。",
                                "visual_pressure": "動く群衆の中で二人だけを静止に近づける。",
                                "attention_shift": "会場の壮麗さから、主人公の目元へ。",
                                "edit_trigger": "相手が主人公を見つけた瞬間に反応へ切る。",
                                "sound_function": "群衆音を薄くし、一歩の音を残す。",
                                "emotional_afterimage": "初めて対等に見つめ返せた感覚。",
                                "must_not_reduce_to": ["美しい人物の紹介ショット"],
                            }
                        },
                    }
                ],
            }
        ],
    }


class AdaptationValueContractTests(unittest.TestCase):
    def test_stage_evaluators_surface_declared_contract_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "story.md").write_text(
                "```yaml\n"
                + yaml.safe_dump(
                    {"story_metadata": {"adaptation_value_contract": ADAPTATION_VALUE_MARKER}},
                    allow_unicode=True,
                    sort_keys=False,
                )
                + "```\n",
                encoding="utf-8",
            )
            story_stage, _updates = check_story(run_dir, "fast")
            self.assertIn("story.adaptation_value_contract", story_stage["reason_keys"])

            (run_dir / "script.md").write_text(
                "```yaml\n"
                + yaml.safe_dump(
                    {
                        "script_metadata": {"adaptation_value_contract": ADAPTATION_VALUE_MARKER},
                        "scenes": [{"scene_id": 1, "scene_intent": {}, "cuts": []}],
                    },
                    allow_unicode=True,
                    sort_keys=False,
                )
                + "```\n",
                encoding="utf-8",
            )
            script_stage, _updates = check_script_single(run_dir, "fast")
            self.assertIn("script.adaptation_value_contract", script_stage["reason_keys"])

            (run_dir / "video_manifest.md").write_text(
                "```yaml\n"
                + yaml.safe_dump(
                    {
                        "manifest_phase": "production",
                        "video_metadata": {"adaptation_value_contract": ADAPTATION_VALUE_MARKER},
                        "scenes": [{"scene_id": 1, "scene_intent": {}, "cuts": []}],
                    },
                    allow_unicode=True,
                    sort_keys=False,
                )
                + "```\n",
                encoding="utf-8",
            )
            manifest_stage, _updates = check_manifest_single(
                run_dir,
                "fast",
                "immersive",
                require_review_artifacts=False,
            )
            self.assertIn("manifest.adaptation_value_contract", manifest_stage["reason_keys"])

    def test_verify_pipeline_story_policy_surfaces_declared_contract_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "story.md").write_text(
                "```yaml\nstory_metadata:\n  adaptation_value_contract: required_v1\n```\n",
                encoding="utf-8",
            )

            stage, _updates = pipeline_evaluation.check_story(run_dir, "fast")
            checks = {check["id"]: check for check in stage["checks"]}

            self.assertFalse(checks["story.adaptation_value_contract"]["passed"])

    def test_visual_stage_coverage_maps_runtime_ids_to_story_scene_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            story = _story()
            story["script"] = {"scenes": [{"scene_id": 1}]}
            visual = _visual_value()
            visual["scene_visual_values"][0]["scene_selector"] = 10
            (run_dir / "story.md").write_text(
                "```yaml\n" + yaml.safe_dump(story, allow_unicode=True, sort_keys=False) + "```\n",
                encoding="utf-8",
            )
            (run_dir / "visual_value.md").write_text(
                "```yaml\n" + yaml.safe_dump(visual, allow_unicode=True, sort_keys=False) + "```\n",
                encoding="utf-8",
            )

            stage, _updates = check_visual_value(run_dir, "fast")
            checks = {check["id"]: check for check in stage["checks"]}

            self.assertTrue(checks["visual_value.scene_coverage"]["passed"])

    def test_authoring_templates_expose_the_canonical_keys(self) -> None:
        story_text = (REPO_ROOT / "workflow" / "story-template.yaml").read_text(encoding="utf-8")
        visual_text = (REPO_ROOT / "workflow" / "visual-value-template.yaml").read_text(encoding="utf-8")
        script_text = (REPO_ROOT / "workflow" / "script-template.yaml").read_text(encoding="utf-8")
        manifest_text = (REPO_ROOT / "workflow" / "video-manifest-template.md").read_text(encoding="utf-8")
        story = yaml.safe_load(story_text)
        visual = yaml.safe_load(visual_text)
        script = yaml.safe_load(script_text)
        cut_blueprint = yaml.safe_load((REPO_ROOT / "workflow" / "cut-blueprint-template.yaml").read_text(encoding="utf-8"))
        _manifest_text, manifest = load_structured_document(REPO_ROOT / "workflow" / "video-manifest-template.md")

        for template_text in (story_text, visual_text, script_text, manifest_text):
            self.assertIn('# adaptation_value_contract: "required_v1"', template_text)
        self.assertNotIn("adaptation_value_contract", story["story_metadata"])
        self.assertNotIn("adaptation_value_contract", visual["visual_value_metadata"])
        self.assertNotIn("adaptation_value_contract", script["script_metadata"])
        self.assertNotIn("adaptation_value_contract", manifest["video_metadata"])
        self.assertIn("core_values", story["adaptation_source_contract"])
        self.assertIn("adaptation_intent", visual)
        self.assertIn("scene_value_amplification", visual["scene_visual_values"][0])
        self.assertIn("scene_value_amplification", script["scenes"][0]["scene_intent"])
        self.assertIn("expressive_contract", script["scenes"][0]["cuts"][0]["cut_contract"])
        self.assertIn("expressive_contract", cut_blueprint["cuts"][0]["cut_contract"])
        self.assertIn("scene_value_amplification", manifest["scenes"][0]["scene_intent"])
        self.assertIn("expressive_contract", manifest["scenes"][0]["cuts"][0]["cut_contract"])

    def test_valid_contract_chain_has_no_issues(self) -> None:
        self.assertEqual(story_adaptation_issues(_story()), [])
        self.assertEqual(
            visual_value_adaptation_issues(_visual_value(), source_value_ids={"value_dignity_seen"}),
            [],
        )
        self.assertEqual(
            script_adaptation_issues(_script(), source_value_ids={"value_dignity_seen"}),
            [],
        )

    def test_marker_makes_story_contract_blocking(self) -> None:
        story = _story()
        del story["adaptation_source_contract"]
        self.assertIn("adaptation_source_contract:missing", story_adaptation_issues(story))

    def test_legacy_artifact_without_marker_is_not_blocked(self) -> None:
        self.assertEqual(story_adaptation_issues({"story_metadata": {}}), [])
        self.assertEqual(script_adaptation_issues({"script_metadata": {}, "scenes": []}), [])

    def test_present_but_empty_or_null_marker_is_blocking(self) -> None:
        for marker in ("", None):
            with self.subTest(marker=marker):
                issues = story_adaptation_issues(
                    {"story_metadata": {"adaptation_value_contract": marker}}
                )
                self.assertIn(
                    "story_metadata.adaptation_value_contract:required_v1",
                    issues,
                )

    def test_unknown_value_reference_is_rejected_at_scene_and_cut(self) -> None:
        script = _script()
        scene = script["scenes"][0]
        scene["scene_intent"]["scene_value_amplification"]["source_value_refs"] = ["unknown_value"]
        scene["cuts"][0]["cut_contract"]["expressive_contract"]["source_value_refs"] = ["unknown_value"]

        issues = script_adaptation_issues(script, source_value_ids={"value_dignity_seen"})

        self.assertTrue(any("source_value_refs:unknown:unknown_value" in issue for issue in issues))

    def test_empty_upstream_value_set_does_not_disable_reference_validation(self) -> None:
        issues = visual_value_adaptation_issues(_visual_value(), source_value_ids=set())
        self.assertTrue(any("unknown:value_dignity_seen" in issue for issue in issues))

    def test_visual_scene_refs_must_be_declared_by_adaptation_intent(self) -> None:
        visual = _visual_value()
        visual["adaptation_intent"]["source_value_ids"] = ["value_other"]

        issues = visual_value_adaptation_issues(
            visual,
            source_value_ids={"value_dignity_seen", "value_other"},
        )

        self.assertTrue(any("source_value_refs:not_in_intent:value_dignity_seen" in issue for issue in issues))

    def test_cut_must_reference_its_own_scene_amplification_and_value_subset(self) -> None:
        script = _script()
        expressive = script["scenes"][0]["cuts"][0]["cut_contract"]["expressive_contract"]
        expressive["scene_amplification_ref"] = "scene99.scene_intent.scene_value_amplification"
        expressive["source_value_refs"] = ["value_not_in_scene"]

        issues = script_adaptation_issues(
            script,
            source_value_ids={"value_dignity_seen", "value_not_in_scene"},
        )

        self.assertTrue(any("scene_amplification_ref:mismatch" in issue for issue in issues))
        self.assertTrue(any("source_value_refs:not_in_scene:value_not_in_scene" in issue for issue in issues))

    def test_manifest_requires_exact_script_projection(self) -> None:
        script = _script()
        manifest = {
            "video_metadata": {"adaptation_value_contract": ADAPTATION_VALUE_MARKER},
            "scenes": deepcopy(script["scenes"]),
        }
        self.assertEqual(
            manifest_adaptation_issues(
                manifest,
                source_value_ids={"value_dignity_seen"},
                script=script,
            ),
            [],
        )

        manifest["scenes"][0]["cuts"][0]["cut_contract"].pop("expressive_contract")
        issues = manifest_adaptation_issues(
            manifest,
            source_value_ids={"value_dignity_seen"},
            script=script,
        )
        self.assertTrue(any("expressive_contract:missing" in issue for issue in issues))
        self.assertTrue(any("expressive_contract:projection_mismatch" in issue for issue in issues))

    def test_manifest_projection_rejects_extra_and_duplicate_nodes(self) -> None:
        script = _script()
        manifest = {
            "video_metadata": {"adaptation_value_contract": ADAPTATION_VALUE_MARKER},
            "scenes": deepcopy(script["scenes"]),
        }
        duplicate = deepcopy(manifest["scenes"][0])
        duplicate["cuts"].append(deepcopy(duplicate["cuts"][0]))
        manifest["scenes"].append(duplicate)
        extra = deepcopy(manifest["scenes"][0])
        extra["scene_id"] = "99"
        extra["scene_intent"]["scene_value_amplification"] = _scene_amplification()
        extra["cuts"][0]["cut_contract"]["expressive_contract"]["scene_amplification_ref"] = (
            "scene99.scene_intent.scene_value_amplification"
        )
        manifest["scenes"].append(extra)

        issues = manifest_adaptation_issues(
            manifest,
            source_value_ids={"value_dignity_seen"},
            script=script,
        )

        self.assertTrue(any("scene_id:duplicate:1" in issue for issue in issues))
        self.assertTrue(any("cut_key:duplicate:1" in issue for issue in issues))
        self.assertTrue(any("scenes[99]:unexpected_projection" in issue for issue in issues))

    def test_script_scene_amplification_must_match_visual_value(self) -> None:
        script = _script()
        visual = _visual_value()
        visual["scene_visual_values"][0]["scene_selector"] = "1"
        visual["scene_visual_values"][0]["scene_value_amplification"]["why_this_scene_matters"] = (
            "p300で承認された別の具体的理由"
        )

        issues = script_adaptation_issues(
            script,
            source_value_ids={"value_dignity_seen"},
            visual_value=visual,
        )

        self.assertTrue(any("scene_value_amplification:visual_projection_mismatch" in issue for issue in issues))

    def test_visual_projection_rejects_extra_and_duplicate_scene_selectors(self) -> None:
        visual = _visual_value()
        duplicate = deepcopy(visual["scene_visual_values"][0])
        visual["scene_visual_values"].append(duplicate)
        extra = deepcopy(duplicate)
        extra["scene_selector"] = "scene99"
        visual["scene_visual_values"].append(extra)

        issues = script_adaptation_issues(
            _script(),
            source_value_ids={"value_dignity_seen"},
            visual_value=visual,
        )

        self.assertTrue(any("duplicate_selector" in issue for issue in issues))
        self.assertTrue(any("scene_visual_values[99]:unexpected_projection" in issue for issue in issues))

    def test_script_rejects_duplicate_scene_and_cut_ids(self) -> None:
        script = _script()
        script["scenes"][0]["cuts"].append(deepcopy(script["scenes"][0]["cuts"][0]))
        script["scenes"].append(deepcopy(script["scenes"][0]))

        issues = script_adaptation_issues(
            script,
            source_value_ids={"value_dignity_seen"},
        )

        self.assertTrue(any("scene_id:duplicate:1" in issue for issue in issues))
        self.assertTrue(any("cut_id:duplicate:1" in issue for issue in issues))

    def test_cut_expressive_function_must_be_controlled(self) -> None:
        script = _script()
        expressive = script["scenes"][0]["cuts"][0]["cut_contract"]["expressive_contract"]
        expressive["expressive_function"] = "looks_cinematic"

        issues = script_adaptation_issues(script, source_value_ids={"value_dignity_seen"})

        self.assertTrue(any("expressive_function:enum" in issue for issue in issues))

    def test_required_string_lists_reject_empty_or_non_string_items(self) -> None:
        story = _story()
        story["adaptation_source_contract"]["non_negotiable_events"] = [""]
        story["adaptation_source_contract"]["core_values"][0]["source_event_refs"] = [{}]

        issues = story_adaptation_issues(story)

        self.assertTrue(any("non_negotiable_events:missing_or_non_string" in issue for issue in issues))
        self.assertTrue(any("source_event_refs:missing_or_non_string" in issue for issue in issues))

    def test_frontend_scaffold_helpers_emit_a_valid_lineage(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "toc_frontend_adaptation_contract_under_test",
            REPO_ROOT / "scripts" / "toc-immersive-frontend-run.py",
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        profile = {
            "protagonist_name": "灰かぶり",
            "artifact_name": "ガラスの靴",
            "motifs": ["灰", "月光", "ガラス"],
            "scene_titles": ["灰の部屋", "舞踏会", "靴の照合"],
            "research_event_ids": ["E01", "E02", "E03"],
        }

        source_contract = module._adaptation_source_contract_for_profile(profile)
        profile["adaptation_source_contract"] = source_contract
        amplification = module._scene_value_amplification_for_profile(
            profile=profile,
            idx=2,
            title="舞踏会",
        )
        expressive = module._cut_expressive_contract_for_scaffold(
            scene_id=2,
            scene_amplification=amplification,
            cut_function="turn",
            focal_character_name="灰かぶり",
            visual_beat="群衆が割れ、王子と主人公の視線が結ばれる",
            motion_brief="主人公が呼吸を止めてから視線を返す",
            motion_end_state="二人が互いを見た状態で止まる",
        )

        story = {
            "story_metadata": {"adaptation_value_contract": ADAPTATION_VALUE_MARKER},
            "adaptation_source_contract": source_contract,
        }
        script = {
            "script_metadata": {"adaptation_value_contract": ADAPTATION_VALUE_MARKER},
            "scenes": [
                {
                    "scene_id": 2,
                    "scene_intent": {"scene_value_amplification": amplification},
                    "cuts": [{"cut_id": 1, "cut_contract": {"expressive_contract": expressive}}],
                }
            ],
        }

        self.assertEqual(story_adaptation_issues(story), [])
        self.assertEqual(script_adaptation_issues(script, source_value_ids=source_value_ids(story)), [])

    def test_reviewed_visual_value_cannot_silently_fall_back_for_a_missing_scene(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "toc_frontend_reviewed_visual_contract_under_test",
            REPO_ROOT / "scripts" / "toc-immersive-frontend-run.py",
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        with self.assertRaisesRegex(RuntimeError, "deterministic fallback is forbidden"):
            module._scene_value_amplification_for_profile(
                profile={
                    "scene_titles": ["scene one"],
                    "scene_value_amplifications": {},
                },
                idx=1,
                title="scene one",
            )

    def test_frontend_builders_project_contract_through_every_scene_and_cut(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "toc_frontend_adaptation_builders_under_test",
            REPO_ROOT / "scripts" / "toc-immersive-frontend-run.py",
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        with patch.dict(os.environ, {"TOC_ENABLE_LEGACY_CINDERELLA_PROFILE": "1"}):
            profile = module._duration_aware_profile(
                module._story_profile("シンデレラ", "シンデレラ", variant_seed="adaptation-lineage"),
                target_duration_seconds=300,
            )
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            story = module._build_story("シンデレラ", run_dir, "2099-01-01T00:00:00+09:00", profile)
            profile = module._profile_from_reviewed_story(profile, story)
            visual = {
                "visual_value_metadata": {
                    "adaptation_value_contract": ADAPTATION_VALUE_MARKER,
                },
                "adaptation_intent": module._adaptation_intent_for_profile(profile),
                "scene_visual_values": [
                    {
                        "scene_selector": module._runtime_scene_id(idx),
                        "scene_value_amplification": module._scene_value_amplification_for_profile(
                            profile=profile,
                            idx=idx,
                            title=title,
                        ),
                    }
                    for idx, title in enumerate(profile["scene_titles"], start=1)
                ],
            }
            profile["scene_value_amplifications"] = {
                str(item["scene_selector"]): deepcopy(item["scene_value_amplification"])
                for item in visual["scene_visual_values"]
            }
            script, manifest, _selectors = module._build_script_and_manifest(
                "シンデレラ",
                run_dir,
                "2099-01-01T00:00:00+09:00",
                profile,
            )

        ids = source_value_ids(story)
        self.assertEqual(story_adaptation_issues(story), [])
        self.assertEqual(
            visual_value_adaptation_issues(visual, source_value_ids=ids),
            [],
        )
        self.assertEqual(
            script_adaptation_issues(
                script,
                source_value_ids=ids,
                visual_value=visual,
            ),
            [],
        )
        self.assertEqual(
            manifest_adaptation_issues(manifest, source_value_ids=ids, script=script),
            [],
        )
        self.assertEqual(manifest["video_metadata"]["adaptation_value_contract"], ADAPTATION_VALUE_MARKER)
        self.assertTrue(
            all(
                cut["cut_contract"].get("expressive_contract")
                for scene in manifest["scenes"]
                for cut in scene["cuts"]
            )
        )


if __name__ == "__main__":
    unittest.main()
