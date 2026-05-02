import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, parse_state_file


def _story_yaml() -> str:
    scene_lines: list[str] = []
    for i in range(1, 21):
        scene_lines.extend(
            [
                f"    - scene_id: {i}",
                "      phase: \"development\"",
                f"      purpose: \"Scene {i} の目的\"",
                f"      conflict: \"Scene {i} の葛藤\"",
                f"      turn: \"Scene {i} の転換\"",
                "      affect:",
                "        label_hint: \"curiosity\"",
                "        audience_job: \"hook\"",
                f"      visualizable_action: \"Scene {i} の画面化可能な行動\"",
                f"      grounding_note: \"Scene {i} の骨格は verified refs、心理は演出補完\"",
                f"      narration: \"Scene {i} の語り\"",
                f"      visual: \"Scene {i} の情景\"",
                f"      research_refs: [\"research.story_baseline.canonical_synopsis.beat_sheet[{i - 1}]\"]",
            ]
        )
    return "\n".join(
        [
            "```yaml",
            "selection:",
            "  candidates:",
            "    - candidate_id: \"A\"",
            "      logline: \"時間断絶案\"",
            "      why_it_scores: [\"後半の喪失が強い\"]",
            "      requires_hybridization_approval: false",
            "    - candidate_id: \"B\"",
            "      logline: \"教訓案\"",
            "      why_it_scores: [\"分かりやすい\"]",
            "      requires_hybridization_approval: false",
            "  chosen_candidate_id: \"A\"",
            "  rationale: \"映像化時の感情曲線が強い\"",
            "hybridization:",
            "  approval_status: \"not_needed\"",
            "script:",
            "  scenes:",
            *scene_lines,
            "```",
            "",
        ]
    )


class TestReviewStoryStage(unittest.TestCase):
    def test_review_story_stage_writes_report_and_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_story_review_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("timestamp=2099-01-01T00:00:00+09:00\ntopic=浦島太郎\n---\n", encoding="utf-8")
            (run_dir / "research.md").write_text("```yaml\ntopic: \"浦島太郎\"\n```\n", encoding="utf-8")
            (run_dir / "story.md").write_text(_story_yaml(), encoding="utf-8")
            append_state_snapshot(
                run_dir / "state.txt",
                {
                    "stage.story.grounding.status": "ready",
                    "stage.story.audit.status": "passed",
                    "stage.story.grounding.report": "logs/grounding/story.json",
                    "stage.story.readset.report": "logs/grounding/story.readset.json",
                    "stage.story.audit.report": "logs/grounding/story.audit.json",
                },
            )
            grounding_dir = run_dir / "logs" / "grounding"
            grounding_dir.mkdir(parents=True, exist_ok=True)
            (grounding_dir / "story.json").write_text("{\"status\":\"ready\"}", encoding="utf-8")
            (grounding_dir / "story.readset.json").write_text("{\"verified_before_edit\":true}", encoding="utf-8")
            (grounding_dir / "story.audit.json").write_text("{\"status\":\"passed\"}", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "review-story-stage.py"),
                    "--run-dir",
                    str(run_dir),
                    "--profile",
                    "fast",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue((run_dir / "story_review.md").exists())
            report = (run_dir / "story_review.md").read_text(encoding="utf-8")
            self.assertIn("# Story Evaluator Review", report)
            self.assertIn("scene_density", report)

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["artifact.story_review"], str((run_dir / "story_review.md").resolve()))
            self.assertEqual(state["eval.story.status"], "approved")
            self.assertEqual(state["review.story.status"], "approved")


if __name__ == "__main__":
    unittest.main()
