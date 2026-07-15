from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from toc.harness import load_structured_document, parse_state_file
from toc.narration_revision import ensure_narration_revision
from toc.narration_semantic_review import (
    RESPONSE_SCHEMA_VERSION,
    SEMANTIC_CRITIC_PROFILES,
    aggregate_narration_critic_results,
    build_narration_semantic_review_pack,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "run-p720-narration-l3.py"


def _write_run(run_dir: Path, *, narration_text: str, tts_text: str, human_review_ok: bool = False) -> None:
    (run_dir / "script.md").write_text(
        "\n".join(
            [
                "```yaml",
                "scenes:",
                "  - scene_id: 10",
                "    phase: development",
                "    scene_summary: 主人公が浜辺で迷う。",
                "    cuts:",
                "      - cut_id: 1",
                "        narration: 主人公は迷いながら、浜辺で足を止めます。",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )
    manifest_lines = [
        "```yaml",
        "scenes:",
        "  - scene_id: 10",
        "    cuts:",
        "      - cut_id: 1",
        "        image_generation:",
        "          prompt: 主人公が浜辺で足を止め、波を見る。",
        "        video_generation:",
        "          duration_seconds: 8",
        "          motion_prompt: 波がゆれる。",
        "        audio:",
        "          narration:",
        "            contract:",
        "              target_function: inner_state",
        "              must_cover: [迷い]",
        "              must_avoid: []",
        "              done_when: [内面情報を足す]",
        f"            text: {narration_text}",
        f"            tts_text: {tts_text}",
        "            tool: elevenlabs",
        "            output: assets/audio/scene10_cut01.mp3",
    ]
    if human_review_ok:
        manifest_lines.extend(
            [
                "            review:",
                "              agent_review_ok: false",
                "              agent_review_reason_keys: []",
                "              agent_review_reason_messages: []",
                "              human_review_ok: true",
                "              human_review_reason: producer accepted this exception",
            ]
        )
    manifest_lines.extend(["```", ""])
    (run_dir / "video_manifest.md").write_text(
        "\n".join(manifest_lines),
        encoding="utf-8",
    )
    (run_dir / "state.txt").write_text(
        "timestamp=2026-05-20T00:00:00+09:00\n"
        "job_id=JOB_2026-05-20_000000\n"
        "topic=テスト\n"
        "status=NARRATION\n"
        "---\n",
        encoding="utf-8",
    )


def _make_revision_aware(run_dir: Path, *, valid_audio_story: bool) -> None:
    _, manifest = load_structured_document(run_dir / "video_manifest.md")
    narration = manifest["scenes"][0]["cuts"][0]["audio"]["narration"]
    narration["authoring_status"] = "human_locked"
    ensure_narration_revision(narration)
    if valid_audio_story:
        manifest["audio_story_plan"] = {
            "authoring_status": "authored",
            "authoring_provenance": "audio_story_director",
            "audience_promise": "主人公が迷いを越える瞬間まで見届ける",
            "narrator_bible": {
                "relationship_to_story": "companion",
                "emotional_permission": ["迷いに寄り添う"],
                "forbidden_attitudes": ["結末を先取りしない"],
            },
            "continuous_full_draft": narration["text"],
            "open_loops": [],
            "scene_arcs": [
                {
                    "scene_id": 10,
                    "attention_state": "release",
                    "audience_state_before": "迷いの理由を知らない",
                    "audience_state_after": "迷いを理解する",
                    "semantic_load": "medium",
                }
            ],
        }
        manifest["narration_spans"] = [
            {
                "span_id": "ns_001",
                "source_cut_ids": ["scene10_cut1"],
                "story_job": "aftertaste",
                "text": narration["text"],
                "tts_text": narration["tts_text"],
                "audio_visual_relation": "complement",
                "tts_generation_group_id": "scene10_flow",
            }
        ]
    dumped = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True, width=1000)
    (run_dir / "video_manifest.md").write_text(f"```yaml\n{dumped}```\n", encoding="utf-8")


def _persist_semantic_pass(run_dir: Path) -> None:
    _, manifest = load_structured_document(run_dir / "video_manifest.md")
    pack = build_narration_semantic_review_pack(manifest)
    text_hash = pack["narration_text_set_hash"]
    input_hash = pack["semantic_review_input_hash"]
    critics = [
        {
            "schema_version": RESPONSE_SCHEMA_VERSION,
            "critic_id": profile.critic_id,
            "narration_text_set_hash": text_hash,
            "semantic_review_input_hash": input_hash,
            "status": "passed",
            "summary": "物語全体を通した評価です。",
            "findings": [],
        }
        for profile in SEMANTIC_CRITIC_PROFILES
    ]
    aggregate = aggregate_narration_critic_results(
        critics,
        text_set_hash=text_hash,
        semantic_review_input_hash=input_hash,
        reviewed_at="2026-07-12T00:00:00Z",
    )
    review_dir = run_dir / "logs" / "eval" / "narration" / "semantic_critics"
    review_dir.mkdir(parents=True, exist_ok=True)
    report = review_dir / "review.md"
    artifact = review_dir / "review.json"
    report.write_text(aggregate["report"], encoding="utf-8")
    artifact.write_text(json.dumps(aggregate, ensure_ascii=False), encoding="utf-8")
    manifest.setdefault("narration_workflow", {})["semantic_critic_review"] = {
        key: aggregate[key]
        for key in (
            "schema_version",
            "status",
            "narration_text_set_hash",
            "semantic_review_input_hash",
            "reviewed_at",
            "critics",
            "findings",
        )
    }
    manifest["narration_workflow"]["semantic_critic_review"].update(
        {
            "report": report.relative_to(run_dir).as_posix(),
            "json": artifact.relative_to(run_dir).as_posix(),
        }
    )
    dumped = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True, width=1000)
    (run_dir / "video_manifest.md").write_text(f"```yaml\n{dumped}```\n", encoding="utf-8")


class TestP720L3NarrationRunner(unittest.TestCase):
    def test_revision_aware_runner_requires_and_hash_binds_full_run_arc_review(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_p720_arc_") as td:
            run_dir = Path(td)
            _write_run(
                run_dir,
                narration_text="主人公は迷いを抱えたまま、浜辺で足を止めます。",
                tts_text="主人公は迷いを抱えたまま、浜辺で足を止めます。",
            )
            _make_revision_aware(run_dir, valid_audio_story=False)
            blocked = subprocess.run(
                [sys.executable, str(RUNNER), "--run-dir", str(run_dir), "--fail-on-findings"],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            _, blocked_manifest = load_structured_document(run_dir / "video_manifest.md")

            self.assertEqual(blocked.returncode, 1)
            self.assertEqual(blocked_manifest["narration_workflow"]["arc_review"]["status"], "changes_requested")
            self.assertTrue(blocked_manifest["narration_workflow"]["arc_review"]["findings"])

            _make_revision_aware(run_dir, valid_audio_story=True)
            passed = subprocess.run(
                [sys.executable, str(RUNNER), "--run-dir", str(run_dir), "--fail-on-findings"],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            _, passed_manifest = load_structured_document(run_dir / "video_manifest.md")
            arc_review = passed_manifest["narration_workflow"]["arc_review"]
            passed_state = parse_state_file(run_dir / "state.txt")

            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertEqual(arc_review["status"], "passed")
            self.assertTrue(arc_review["narration_text_set_hash"].startswith("sha256:"))
            self.assertEqual(passed_state["slot.p720.status"], "in_progress")
            self.assertEqual(passed_state["slot.p730.status"], "blocked")
            self.assertEqual(passed_state["review.narration.status"], "pending")

    def test_revision_aware_runner_accepts_only_complete_current_semantic_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_p720_semantic_current_") as td:
            run_dir = Path(td)
            _write_run(
                run_dir,
                narration_text="主人公は迷いを抱えたまま、浜辺で足を止めます。",
                tts_text="主人公は迷いを抱えたまま、浜辺で足を止めます。",
            )
            _make_revision_aware(run_dir, valid_audio_story=True)
            _persist_semantic_pass(run_dir)

            result = subprocess.run(
                [sys.executable, str(RUNNER), "--run-dir", str(run_dir), "--fail-on-findings"],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["slot.p720.status"], "done")
            self.assertEqual(state["review.narration.status"], "approved")

    def test_runner_creates_l3_reports_and_blocks_failed_p720(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_p720_l3_") as td:
            run_dir = Path(td)
            _write_run(
                run_dir,
                narration_text="このフェーズでは、構造と観点を整理します。次のフレームで要素を見せます。",
                tts_text="このフェーズでは、構造と観点を整理します。次のフレームで要素を見せます。",
            )

            result = subprocess.run(
                [sys.executable, str(RUNNER), "--run-dir", str(run_dir)],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            round_dir = run_dir / "logs" / "eval" / "narration" / "round_01"
            for index in range(1, 6):
                report = round_dir / f"critic_{index}.md"
                prompt = round_dir / "prompts" / f"critic_{index}.prompt.md"
                self.assertTrue(report.exists(), report)
                self.assertTrue(prompt.exists(), prompt)
            self.assertTrue((round_dir / "aggregated_review.md").exists())
            final_report = run_dir / "narration_text_review.md"
            self.assertTrue(final_report.exists())
            self.assertIn("- status: changes_requested", final_report.read_text(encoding="utf-8"))
            self.assertIn("ai_thin_abstract_wording", final_report.read_text(encoding="utf-8"))

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.narration.loop.status"], "changes_requested")
            self.assertEqual(state["slot.p720.status"], "blocked")
            self.assertEqual(state["slot.p720.review_loop.status"], "changes_requested")
            self.assertEqual(
                state["eval.narration.loop.round_01.critic_5"],
                "logs/eval/narration/round_01/critic_5.md",
            )

            _, manifest = load_structured_document(run_dir / "video_manifest.md")
            review = manifest["scenes"][0]["cuts"][0]["audio"]["narration"]["review"]
            self.assertFalse(review["agent_review_ok"])
            self.assertIn("ai_thin_abstract_wording", review["agent_review_reason_keys"])

    def test_fail_on_findings_returns_nonzero_for_unresolved_p720(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_p720_l3_fail_") as td:
            run_dir = Path(td)
            _write_run(
                run_dir,
                narration_text="このフェーズでは、構造と観点を整理します。次のフレームで要素を見せます。",
                tts_text="このフェーズでは、構造と観点を整理します。次のフレームで要素を見せます。",
            )

            result = subprocess.run(
                [sys.executable, str(RUNNER), "--run-dir", str(run_dir), "--fail-on-findings"],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)

    def test_runner_marks_p720_done_when_l3_passes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_p720_l3_pass_") as td:
            run_dir = Path(td)
            _write_run(
                run_dir,
                narration_text="主人公は迷いを抱えたまま、浜辺で足を止めます。",
                tts_text="主人公は迷いを抱えたまま、浜辺で足を止めます。",
            )

            result = subprocess.run(
                [sys.executable, str(RUNNER), "--run-dir", str(run_dir), "--fail-on-findings"],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.narration.loop.status"], "passed")
            self.assertEqual(state["slot.p720.status"], "done")
            self.assertEqual(state["review.narration.status"], "approved")
            report = (run_dir / "narration_text_review.md").read_text(encoding="utf-8")
            self.assertIn("- status: passed", report)
            self.assertIn("## Blocking Findings\n\n- []", report)
            self.assertNotIn("(run).manifest", report)
            self.assertNotIn("scene10_cut01.tool", report)
            self.assertNotIn("scene10_cut01.review", report)

    def test_human_reviewed_findings_pass_as_accepted_context_not_blockers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_p720_l3_human_") as td:
            run_dir = Path(td)
            _write_run(
                run_dir,
                narration_text="このフェーズでは、構造と観点を整理します。次のフレームで要素を見せます。",
                tts_text="このフェーズでは、構造と観点を整理します。次のフレームで要素を見せます。",
                human_review_ok=True,
            )

            result = subprocess.run(
                [sys.executable, str(RUNNER), "--run-dir", str(run_dir), "--fail-on-findings"],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            report = (run_dir / "narration_text_review.md").read_text(encoding="utf-8")
            self.assertIn("- status: passed", report)
            self.assertIn("## Blocking Findings\n\n- []", report)
            self.assertIn("## Human-Accepted Findings", report)
            self.assertIn("ai_thin_abstract_wording", report)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["review.narration.status"], "approved")

    def test_deterministic_review_failure_marks_loop_failed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_p720_l3_error_") as td:
            run_dir = Path(td)
            (run_dir / "script.md").write_text("```yaml\nscenes: []\n```\n", encoding="utf-8")
            (run_dir / "video_manifest.md").write_text("not a structured manifest\n", encoding="utf-8")
            (run_dir / "state.txt").write_text(
                "timestamp=2026-05-20T00:00:00+09:00\njob_id=JOB_2026-05-20_000000\ntopic=テスト\nstatus=NARRATION\n---\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(RUNNER), "--run-dir", str(run_dir)],
                cwd=REPO_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.narration.loop.status"], "failed")
            self.assertEqual(state["slot.p720.status"], "blocked")
            self.assertEqual(state["slot.p720.review_loop.status"], "failed")


if __name__ == "__main__":
    unittest.main()
