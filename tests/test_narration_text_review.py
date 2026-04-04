import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import load_structured_document, parse_state_file


def _load_review_module(repo_root: Path):
    script = repo_root / "scripts" / "review-narration-text-quality.py"
    spec = importlib.util.spec_from_file_location("review_narration_text_quality", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[assignment]
    return mod


class TestNarrationTextReview(unittest.TestCase):
    def test_review_flags_v2_unfriendly_patterns(self) -> None:
        mod = _load_review_module(REPO_ROOT)
        entries = [
            mod.NarrationEntry(
                scene_id=10,
                cut_id=1,
                selector="scene10_cut01",
                text="[whispers] 2026ねん3がつ29にちに www.example.com をみてください カメラがズームする",
                tts_text="[whispers] 2026ねん3がつ29にちに www.example.com を みてください カメラがズームする",
                tool="elevenlabs",
                output="assets/audio/scene10_cut01.mp3",
                duration_seconds=8,
                image_prompt="浜辺で主人公が前を見る。",
                motion_prompt="ゆっくり前進する。",
                story_role="middle",
                phase="development",
                scene_summary="主人公は浜辺で何かを探している。",
                script_narration="主人公は浜辺で立ち止まります。",
                contract={},
                agent_review_ok=True,
                human_review_ok=False,
                human_review_reason="",
                agent_review_reason_keys=[],
                agent_review_reason_messages=[],
                rubric_scores={},
                overall_score=1.0,
            )
        ]

        results = mod.review_entries(entries)
        codes = [finding.code for outcome in results for finding in outcome.findings]

        self.assertIn("unsupported_audio_tag_for_v2", codes)
        self.assertIn("needs_text_normalization", codes)
        self.assertIn("tts_unfriendly_literal", codes)
        self.assertIn("visual_direction_leaked_into_narration", codes)
        self.assertLess(results[0].rubric_scores["tts_readiness"], 0.7)

    def test_opening_narration_can_be_scene_faithful_without_penalty(self) -> None:
        mod = _load_review_module(REPO_ROOT)
        entries = [
            mod.NarrationEntry(
                scene_id=10,
                cut_id=1,
                selector="scene10_cut01",
                text="しゅじんこうが はまべにたち、うみをみます。",
                tts_text="しゅじんこうが はまべにたち、うみをみます。",
                tool="elevenlabs",
                output="assets/audio/scene10_cut01.mp3",
                duration_seconds=8,
                image_prompt="主人公が浜辺に立ち、海を見る。夕方の浜辺。",
                motion_prompt="波がゆれる。",
                story_role="opening",
                phase="opening",
                scene_summary="主人公が浜辺に立ち、海を見ます。",
                script_narration="主人公が浜辺に立ち、海を見る。",
                contract={},
                agent_review_ok=True,
                human_review_ok=False,
                human_review_reason="",
                agent_review_reason_keys=[],
                agent_review_reason_messages=[],
                rubric_scores={},
                overall_score=1.0,
            )
        ]

        results = mod.review_entries(entries)
        codes = [finding.code for outcome in results for finding in outcome.findings]
        self.assertNotIn("narration_story_role_mismatch", codes)
        self.assertNotIn("narration_too_visual_redundant", codes)
        self.assertGreaterEqual(results[0].rubric_scores["story_role_fit"], 0.55)

    def test_opening_narration_flags_overwritten_abstract_setup(self) -> None:
        mod = _load_review_module(REPO_ROOT)
        entries = [
            mod.NarrationEntry(
                scene_id=1,
                cut_id=1,
                selector="scene01_cut01",
                text="あるあさ、うんめいだけが さきへすすみ、たろうは ことばをなくします。",
                tts_text="あるあさ、うんめいだけが さきへすすみ、たろうは ことばをなくします。",
                tool="elevenlabs",
                output="assets/audio/scene01_cut01.mp3",
                duration_seconds=8,
                image_prompt="浜辺で太郎が亀を助ける。",
                motion_prompt="波がゆれる。",
                story_role="opening",
                phase="opening",
                scene_summary="ある朝、浦島太郎は浜でいじめられていた亀を助けます。",
                script_narration="ある朝、浦島太郎は浜でいじめられていた亀を助けます。",
                contract={},
                agent_review_ok=True,
                human_review_ok=False,
                human_review_reason="",
                agent_review_reason_keys=[],
                agent_review_reason_messages=[],
                rubric_scores={},
                overall_score=1.0,
            )
        ]

        results = mod.review_entries(entries)
        codes = [finding.code for outcome in results for finding in outcome.findings]
        self.assertIn("narration_story_role_mismatch", codes)
        self.assertLess(results[0].rubric_scores["story_role_fit"], 0.55)

    def test_review_uses_contract(self) -> None:
        mod = _load_review_module(REPO_ROOT)
        entries = [
            mod.NarrationEntry(
                scene_id=10,
                cut_id=1,
                selector="scene10_cut01",
                text="しゅじんこうが はまべにたち、うみをみます。",
                tts_text="しゅじんこうが はまべにたち、うみをみます。",
                tool="elevenlabs",
                output="assets/audio/scene10_cut01.mp3",
                duration_seconds=8,
                image_prompt="主人公が浜辺に立ち、海を見る。夕方の浜辺。",
                motion_prompt="波がゆれる。",
                story_role="middle",
                phase="development",
                scene_summary="主人公は迷いながら浜辺に立ちます。",
                script_narration="主人公が浜辺に立ち、海を見る。",
                contract={
                    "target_function": "inner_state",
                    "must_cover": ["迷い"],
                    "must_avoid": ["うみをみます"],
                    "done_when": ["内面情報を1つ足す"],
                },
                agent_review_ok=True,
                human_review_ok=False,
                human_review_reason="",
                agent_review_reason_keys=[],
                agent_review_reason_messages=[],
                rubric_scores={},
                overall_score=1.0,
            )
        ]
        results = mod.review_entries(entries)
        codes = [finding.code for outcome in results for finding in outcome.findings]
        self.assertIn("narration_contract_must_cover_unmet", codes)
        self.assertIn("narration_contract_must_avoid_violated", codes)
        self.assertIn("narration_contract_target_function_unmet", codes)

    def test_contract_semantic_anchor_allows_near_expression(self) -> None:
        mod = _load_review_module(REPO_ROOT)
        entries = [
            mod.NarrationEntry(
                scene_id=10,
                cut_id=1,
                selector="scene10_cut01",
                text="かれは ためらいをかかえたまま、そのため いっぽをとめます。",
                tts_text="かれは ためらいをかかえたまま、そのため いっぽをとめます。",
                tool="elevenlabs",
                output="assets/audio/scene10_cut01.mp3",
                duration_seconds=8,
                image_prompt="主人公が浜辺で立ち止まる。",
                motion_prompt="波がゆれる。",
                story_role="middle",
                phase="development",
                scene_summary="主人公は迷って立ち止まります。",
                script_narration="主人公は迷って立ち止まります。",
                contract={
                    "target_function": "causality",
                    "must_cover": ["理由", "迷い"],
                    "must_avoid": ["海を見る"],
                    "done_when": ["因果と内面を1つずつ足す"],
                },
                agent_review_ok=True,
                human_review_ok=False,
                human_review_reason="",
                agent_review_reason_keys=[],
                agent_review_reason_messages=[],
                rubric_scores={},
                overall_score=1.0,
            )
        ]
        results = mod.review_entries(entries)
        codes = [finding.code for outcome in results for finding in outcome.findings]
        self.assertNotIn("narration_contract_must_cover_unmet", codes)
        self.assertNotIn("narration_contract_target_function_unmet", codes)

    def test_script_writes_review_metadata_back_to_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_narration_review_") as td:
            run_dir = Path(td)
            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text(
                "\n".join(
                    [
                        "```yaml",
                        "scenes:",
                        "  - scene_id: 10",
                        "    cuts:",
                        "      - cut_id: 1",
                        "        image_generation:",
                        "          prompt: |",
                        "            主人公が浜辺に立ち、海を見る。",
                        "        video_generation:",
                        "          duration_seconds: 8",
                        "          motion_prompt: \"波がゆれる。\"",
                        "        audio:",
                        "          narration:",
                        "            contract:",
                        "              target_function: \"causality\"",
                        "              must_cover: [\"理由\"]",
                        "              must_avoid: [\"www.example.com\"]",
                        "              done_when: [\"因果情報を1つ足す\"]",
                        "            text: \"TODO: 2026ねん3がつ29にちに www.example.com をみる\"",
                        "            tts_text: \"とぅーどぅー 2026ねん3がつ29にちに www.example.com をみる\"",
                        "            tool: \"elevenlabs\"",
                        "            output: \"assets/audio/scene10_cut01.mp3\"",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "state.txt").write_text(
                "timestamp=2026-03-29T00:00:00+09:00\njob_id=JOB_2026-03-29_000001\ntopic=浦島太郎\nstatus=VIDEO\n---\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "review-narration-text-quality.py"),
                    "--manifest",
                    str(manifest_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            _, manifest = load_structured_document(manifest_path)
            review = manifest["scenes"][0]["cuts"][0]["audio"]["narration"]["review"]
            self.assertFalse(review["agent_review_ok"])
            self.assertIn("narration_contains_meta_marker", review["agent_review_reason_keys"])
            self.assertIn("needs_text_normalization", review["agent_review_reason_keys"])
            self.assertIn("tts_unfriendly_literal", review["agent_review_reason_keys"])
            self.assertIn("narration_text_not_hiragana_only", review["agent_review_reason_keys"])
            self.assertIn("tts_text_not_hiragana_only", review["agent_review_reason_keys"])
            self.assertIn("rubric_scores", review)
            self.assertIn("overall_score", review)
            state = parse_state_file(run_dir / "state.txt")
            self.assertIn("eval.narration.score", state)
            self.assertIn("eval.narration.unresolved_entries", state)
