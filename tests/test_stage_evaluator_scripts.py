import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import parse_state_file


def _good_research_yaml() -> str:
    sources = "\n".join(f"  - title: source{i}\n    url: https://example.com/{i}" for i in range(12))
    scene_plan = "\n".join(f"    - scene_id: {i}\n      summary: scene {i}" for i in range(1, 21))
    beat_sheet = "\n".join(f"        - beat: beat{i}\n          scene_ids: [{i}]" for i in range(1, 21))
    return "\n".join(
        [
            "```yaml",
            "sources:",
            sources,
            "scene_plan:",
            "  scenes:",
            scene_plan,
            "story_baseline:",
            "  canonical_synopsis:",
            "    short_summary: summary",
            "    beat_sheet:",
            beat_sheet,
            "conflicts: []",
            "evaluation_contract:",
            "  target_questions: [\"summary\"]",
            "  must_cover: [\"summary\"]",
            "  must_resolve_conflicts: []",
            "  done_when: [\"scene plan と beat sheet が埋まる\"]",
            "metadata:",
            "  confidence_score: 0.9",
            "```",
            "",
        ]
    )


class TestStageEvaluatorScripts(unittest.TestCase):
    def test_stage_evaluator_scripts_update_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "timestamp=2026-03-29T00:00:00+09:00",
                        "job_id=JOB_2026-03-29_000001",
                        "topic=桃太郎",
                        "status=VIDEO",
                        "review.video.status=pending",
                        "---",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "research.md").write_text(_good_research_yaml(), encoding="utf-8")
            (run_dir / "script.md").write_text(
                "```yaml\nevaluation_contract:\n  target_arc: \"opening,development,climax\"\n  must_cover: [\"桃太郎\"]\n  must_avoid: [\"TODO\"]\n  done_when: [\"主要 phase を含む\"]\nscript:\n  scenes:\n    - scene_id: 1\n      phase: \"opening\"\n      summary: \"桃太郎が村で育つ。十分な長さの台本本文です。十分な長さの台本本文です。\"\n      research_refs: [\"research.story_baseline.canonical_synopsis\"]\n    - scene_id: 2\n      phase: \"development\"\n      summary: \"桃太郎が旅支度を整える。十分な長さの台本本文です。十分な長さの台本本文です。\"\n      research_refs: [\"research.story_baseline.canonical_synopsis\"]\n    - scene_id: 3\n      phase: \"climax\"\n      summary: \"桃太郎が決戦へ向かう。十分な長さの台本本文です。十分な長さの台本本文です。\"\n      research_refs: [\"research.story_baseline.canonical_synopsis\"]\n```\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "scenes:",
                        "  - scene_id: 1",
                        "    cuts:",
                        "      - cut_id: 1",
                        "        scene_contract:",
                        "          target_beat: \"桃太郎\"",
                        "          must_show: [\"桃太郎\"]",
                        "          must_avoid: [\"TODO\"]",
                        "          done_when: [\"narration と prompt に桃太郎が出る\"]",
                        "        image_generation:",
                        "          prompt: \"桃太郎が朝の村をゆっくり歩く。藁屋根の家並み、土の道、やわらかな朝日、前景には風に揺れるのぼり、中央には桃太郎、背景には山並み。実写的で自然な衣装と光。\"",
                        "          character_ids: [\"momotaro\"]",
                        "          object_ids: [\"peach\"]",
                        "        video_generation:",
                        "          duration_seconds: 5",
                        "          motion_prompt: \"桃太郎が前へ進む。\"",
                        "        audio:",
                        "          narration:",
                        "            text: \"むかし、桃から生まれた子がいました。\"",
                        "            tool: \"elevenlabs\"",
                        "quality_check:",
                        "  review_contract:",
                        "    target_outcome: \"publishable_short\"",
                        "    must_have_artifacts: [\"video.mp4\"]",
                        "    must_avoid: []",
                        "    done_when: [\"video.mp4 が生成済み\"]",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "video.mp4").write_bytes(b"fake")

            commands = [
                "scripts/review-research-stage.py",
                "scripts/review-script-stage.py",
                "scripts/review-manifest-stage.py",
                "scripts/review-video-stage.py",
            ]
            for command in commands:
                result = subprocess.run(
                    [sys.executable, str(REPO_ROOT / command), "--run-dir", str(run_dir), "--profile", "standard"],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, msg=result.stderr)

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.research.status"], "approved")
            self.assertEqual(state["eval.script.status"], "approved")
            self.assertEqual(state["eval.manifest.status"], "approved")
            self.assertEqual(state["eval.video.status"], "approved")
            self.assertIn("eval.manifest.rubric.beat_clarity", state)
            self.assertIn("eval.video.overall_rubric", state)
            self.assertTrue((run_dir / "research_review.md").exists())
            self.assertTrue((run_dir / "script_review.md").exists())
            self.assertTrue((run_dir / "manifest_review.md").exists())
            self.assertTrue((run_dir / "video_review.md").exists())

    def test_research_evaluator_fails_without_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_fail_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0001"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-03-29T00:00:00+09:00\njob_id=JOB_2026-03-29_000001\ntopic=桃太郎\nstatus=RESEARCH\n---\n",
                encoding="utf-8",
            )
            (run_dir / "research.md").write_text("```yaml\nsources: []\nscene_plan:\n  scenes: []\nstory_baseline:\n  canonical_synopsis:\n    short_summary: \"\"\n    beat_sheet: []\nconflicts: []\nmetadata:\n  confidence_score: 0.1\n```\n", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/review-research-stage.py"), "--run-dir", str(run_dir), "--profile", "standard", "--fail-on-findings"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.research.status"], "changes_requested")

    def test_manifest_evaluator_fails_reveal_constraint_violation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_stage_eval_reveal_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0002"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text(
                "timestamp=2026-03-29T00:00:00+09:00\njob_id=JOB_2026-03-29_000001\ntopic=浦島太郎\nstatus=MANIFEST\n---\n",
                encoding="utf-8",
            )
            (run_dir / "script.md").write_text(
                "```yaml\n"
                "evaluation_contract:\n"
                "  target_arc: \"opening,development\"\n"
                "  must_cover: [\"竜宮城\"]\n"
                "  must_avoid: []\n"
                "  done_when: [\"reveal 順が守られる\"]\n"
                "  reveal_constraints:\n"
                "    - subject_type: \"character\"\n"
                "      subject_id: \"otohime\"\n"
                "      rule: \"must_not_appear_before\"\n"
                "      selector: \"scene05_cut01\"\n"
                "      rationale: \"宴まで乙姫を出さない\"\n"
                "scenes:\n"
                "  - scene_id: 4\n"
                "    phase: \"development\"\n"
                "    scene_summary: \"門が開く。\"\n"
                "    cuts: []\n"
                "```\n",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "```yaml",
                        "scenes:",
                        "  - scene_id: 4",
                        "    cuts:",
                        "      - cut_id: 1",
                        "        scene_contract:",
                        "          target_beat: \"門が開く\"",
                        "          must_show: [\"門\"]",
                        "          must_avoid: []",
                        "          done_when: [\"到着が読める\"]",
                        "        image_generation:",
                        "          prompt: \"乙姫が門の奥で浦島太郎を迎える。\"",
                        "          character_ids: [\"urashima\", \"otohime\"]",
                        "          object_ids: []",
                        "        video_generation:",
                        "          duration_seconds: 5",
                        "          motion_prompt: \"門へ進む。\"",
                        "        audio:",
                        "          narration:",
                        "            text: \"もんが ひらきます。\"",
                        "            tool: \"elevenlabs\"",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts/review-manifest-stage.py"), "--run-dir", str(run_dir), "--profile", "standard", "--fail-on-findings"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 1, msg=result.stderr)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.manifest.status"], "changes_requested")
