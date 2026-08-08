from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toc.harness import parse_state_file
from toc.review_loop import (
    MAX_REVIEW_LOOP_ROUNDS,
    REVIEW_LOOP_CRITIC_COUNT,
    REVIEW_LOOP_SPECS,
    aggregator_prompt_relpath,
    aggregated_review_relpath,
    build_review_input_snapshot,
    critic_prompt_relpath,
    critic_relpath,
    loop_state_updates,
    render_aggregated_review,
    render_critic_prompt,
    review_input_snapshot_issues,
    review_input_snapshot_relpath,
    stage_for_slot,
)
from toc.review_projection import review_source_fingerprint
from toc.run_index import SLOT_BY_CODE, build_run_index_markdown, classify_run_file


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build-review-loop-round.py"
SPEC = importlib.util.spec_from_file_location("build_review_loop_round", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)

REVIEW_DIGEST = "a" * 64
P400_MANIFEST_BOUND_STAGES = (
    "scene_set",
    "scene_detail",
    "cut_blueprint",
    "script",
    "production_readiness",
)


def _review_manifest_text(revision: str = "one") -> str:
    return (
        "# Video Manifest\n\n"
        "```yaml\n"
        "schema_version: scene_event_v1\n"
        f"review_fixture_revision: {revision}\n"
        "scenes:\n"
        "  - scene_id: 1\n"
        "    cuts:\n"
        "      - cut_id: 1\n"
        "        duration_seconds: 8\n"
        "```\n"
    )


def _critic_reports(*, status: str, focus: str = "generic", digest: str = REVIEW_DIGEST) -> list[str]:
    return [
        "\n".join(
            [
                f"- critic_id: critic_{index}",
                f"- review_input_digest: {digest}",
                f"- critic_focus: {focus}",
                f"- status: {status}",
            ]
        )
        for index in range(1, REVIEW_LOOP_CRITIC_COUNT + 1)
    ]


class TestReviewLoop(unittest.TestCase):
    def test_review_slots_are_improvement_loops(self) -> None:
        expected_slots = {
            "p130",
            "p230",
            "p320",
            "p430",
            "p540",
            "p630",
            "p640",
            "p720",
            "p820",
            "p850",
            "p930",
        }
        for code in expected_slots:
            with self.subTest(code=code):
                slot = SLOT_BY_CODE[code]
                self.assertIn("Eval/Improve Loop", slot.title)
                self.assertIn("5", slot.purpose)
                self.assertIn("5 independent critics", slot.purpose)
                self.assertIn("1 aggregator", slot.purpose)

    def test_review_loop_paths_and_state_contract(self) -> None:
        self.assertEqual(MAX_REVIEW_LOOP_ROUNDS, 5)
        self.assertEqual(REVIEW_LOOP_CRITIC_COUNT, 5)
        self.assertEqual(critic_relpath("story", 1, 1).as_posix(), "logs/eval/story/round_01/critic_1.md")
        self.assertEqual(critic_prompt_relpath("story", 1, 1).as_posix(), "logs/eval/story/round_01/prompts/critic_1.prompt.md")
        self.assertEqual(aggregator_prompt_relpath("story", 1).as_posix(), "logs/eval/story/round_01/prompts/aggregator.prompt.md")
        self.assertEqual(aggregated_review_relpath("story", 1).as_posix(), "logs/eval/story/round_01/aggregated_review.md")

        updates = loop_state_updates(stage="story", status="running", current_round=1)
        self.assertEqual(updates["eval.story.loop.status"], "running")
        self.assertEqual(updates["eval.story.loop.current_round"], "1")
        self.assertEqual(updates["eval.story.loop.max_rounds"], "5")
        self.assertEqual(updates["eval.story.loop.final_report"], "story_review.md")
        self.assertEqual(stage_for_slot("p640"), "scene_implementation_judgment")
        self.assertEqual(stage_for_slot("p720"), "narration")
        self.assertEqual(stage_for_slot("850"), "video_generation_review")
        self.assertEqual(stage_for_slot("p410b"), "scene_set")
        self.assertEqual(stage_for_slot("410c"), "scene_detail")
        self.assertEqual(stage_for_slot("p420"), "cut_blueprint")
        self.assertEqual(stage_for_slot("p435"), "production_readiness")
        self.assertIn("scene_set", REVIEW_LOOP_SPECS)
        self.assertIn("scene_detail", REVIEW_LOOP_SPECS)
        self.assertIn("cut_blueprint", REVIEW_LOOP_SPECS)
        self.assertIn("production_readiness", REVIEW_LOOP_SPECS)
        self.assertIn("scene_intent", REVIEW_LOOP_SPECS)
        self.assertEqual(REVIEW_LOOP_SPECS["scene_set"].final_report, "scene_set_review.md")
        self.assertEqual(REVIEW_LOOP_SPECS["scene_detail"].final_report, "scene_detail_review.md")
        self.assertEqual(REVIEW_LOOP_SPECS["cut_blueprint"].final_report, "cut_blueprint_review.md")
        self.assertEqual(REVIEW_LOOP_SPECS["production_readiness"].final_report, "production_readiness_review.md")
        self.assertEqual(REVIEW_LOOP_SPECS["narration"].final_report, "narration_text_review.md")
        self.assertEqual(REVIEW_LOOP_SPECS["narration"].source_artifacts, ("script.md", "video_manifest.md"))

    def test_aggregated_review_requires_five_critics(self) -> None:
        reports = _critic_reports(status="changes_requested")
        review = render_aggregated_review(stage="script", round_number=2, critic_reports=reports)
        self.assertIn("# Script Eval/Improve Loop", review)
        self.assertIn("- round: 2/5", review)
        self.assertIn("## Generator Patch Brief", review)
        self.assertIn("root cause", review)
        self.assertIn("fix plan", review)
        self.assertIn("acceptance condition", review)
        self.assertIn("## Critic 5 Input", review)

        with self.assertRaises(ValueError):
            render_aggregated_review(stage="script", round_number=2, critic_reports=reports[:4])

    def test_build_review_loop_round_materializes_prompts_and_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_review_loop_") as td:
            run_dir = Path(td)
            for rel in REVIEW_LOOP_SPECS["story"].source_artifacts:
                (run_dir / rel).write_text(f"# {rel}\n", encoding="utf-8")

            MODULE.write_review_loop_round(run_dir=run_dir, stage="story", round_number=1)

            for idx in range(1, 6):
                report_path = run_dir / critic_relpath("story", 1, idx)
                prompt_path = run_dir / critic_prompt_relpath("story", 1, idx)
                self.assertFalse(report_path.exists(), report_path)
                self.assertTrue(prompt_path.exists(), prompt_path)
                prompt_text = prompt_path.read_text(encoding="utf-8")
                self.assertIn(f"critic_{idx}", prompt_text)
                self.assertIn("root_cause", prompt_text)
                self.assertIn("fix_direction", prompt_text)
            aggregate_prompt = run_dir / aggregator_prompt_relpath("story", 1)
            self.assertTrue(aggregate_prompt.exists())
            aggregate_text = aggregate_prompt.read_text(encoding="utf-8")
            self.assertIn("Wait until all 5 critic reports exist", aggregate_text)
            self.assertIn("essential cause", aggregate_text)
            self.assertIn("adopted_fix_plan", aggregate_text)

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.story.loop.status"], "running")
            self.assertEqual(state["eval.story.loop.round_01.critic_5"], "logs/eval/story/round_01/critic_5.md")
            self.assertEqual(
                state["eval.story.loop.round_01.critic_5_prompt"],
                "logs/eval/story/round_01/prompts/critic_5.prompt.md",
            )
            snapshot_path = run_dir / review_input_snapshot_relpath("story", 1)
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertRegex(snapshot["input_digest"], r"^[0-9a-f]{64}$")
            self.assertEqual(len(snapshot["prompt_sha256s"]), 6)
            self.assertEqual(
                state["eval.story.loop.round_01.input_digest"],
                snapshot["input_digest"],
            )

    def test_rematerializing_round_invalidates_stale_reports_and_source_digest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_review_loop_stale_") as td:
            run_dir = Path(td)
            for rel in REVIEW_LOOP_SPECS["story"].source_artifacts:
                (run_dir / rel).write_text(f"# {rel}\nrevision one\n", encoding="utf-8")
            MODULE.write_review_loop_round(run_dir=run_dir, stage="story", round_number=1)
            snapshot_path = run_dir / review_input_snapshot_relpath("story", 1)
            first_digest = json.loads(snapshot_path.read_text(encoding="utf-8"))["input_digest"]
            (run_dir / critic_relpath("story", 1, 1)).write_text("stale", encoding="utf-8")
            (run_dir / aggregated_review_relpath("story", 1)).write_text("stale", encoding="utf-8")
            (run_dir / REVIEW_LOOP_SPECS["story"].final_report).write_text("stale", encoding="utf-8")

            (run_dir / "story.md").write_text("# story.md\nrevision two\n", encoding="utf-8")
            MODULE.write_review_loop_round(run_dir=run_dir, stage="story", round_number=1)

            second_digest = json.loads(snapshot_path.read_text(encoding="utf-8"))["input_digest"]
            self.assertNotEqual(first_digest, second_digest)
            self.assertFalse((run_dir / critic_relpath("story", 1, 1)).exists())
            self.assertFalse((run_dir / aggregated_review_relpath("story", 1)).exists())
            self.assertFalse((run_dir / REVIEW_LOOP_SPECS["story"].final_report).exists())

    def test_p400_review_specs_bind_the_materialized_manifest(self) -> None:
        expected_sources = ("story.md", "visual_value.md", "script.md", "video_manifest.md")

        for stage in P400_MANIFEST_BOUND_STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(REVIEW_LOOP_SPECS[stage].source_artifacts, expected_sources)
        self.assertEqual(
            REVIEW_LOOP_SPECS["visual_value"].source_artifacts,
            ("research.md", "story.md", "visual_value.md"),
        )
        self.assertEqual(
            REVIEW_LOOP_SPECS["scene_intent"].source_artifacts,
            ("story.md", "visual_value.md", "script.md"),
        )

    def test_p400_snapshots_reuse_unchanged_source_fingerprints(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_review_fingerprint_cache_") as td:
            run_dir = Path(td)
            for relpath in ("story.md", "visual_value.md", "script.md"):
                (run_dir / relpath).write_text(f"# {relpath}\n", encoding="utf-8")
            (run_dir / "video_manifest.md").write_text(
                _review_manifest_text(),
                encoding="utf-8",
            )
            fingerprint_cache: dict[tuple[object, ...], object] = {}

            with patch(
                "toc.review_loop.review_source_fingerprint",
                wraps=review_source_fingerprint,
            ) as fingerprint:
                build_review_input_snapshot(
                    run_dir=run_dir,
                    stage="scene_set",
                    round_number=1,
                    source_fingerprint_cache=fingerprint_cache,
                )
                build_review_input_snapshot(
                    run_dir=run_dir,
                    stage="scene_detail",
                    round_number=1,
                    source_fingerprint_cache=fingerprint_cache,
                )

        self.assertEqual(fingerprint.call_count, 4)

    def test_p400_snapshot_validation_reuses_only_unchanged_source_fingerprints(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(
            prefix="toc_review_validation_fingerprint_cache_"
        ) as td:
            run_dir = Path(td)
            for relpath in ("story.md", "visual_value.md", "script.md"):
                (run_dir / relpath).write_text(
                    f"# {relpath}\n",
                    encoding="utf-8",
                )
            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text(
                _review_manifest_text("one"),
                encoding="utf-8",
            )
            for stage in ("scene_set", "scene_detail"):
                MODULE.write_review_loop_round(
                    run_dir=run_dir,
                    stage=stage,
                    round_number=1,
                )

            fingerprint_cache: dict[tuple[object, ...], object] = {}
            with patch(
                "toc.review_loop.review_source_fingerprint",
                wraps=review_source_fingerprint,
            ) as fingerprint:
                for stage in ("scene_set", "scene_detail"):
                    self.assertEqual(
                        review_input_snapshot_issues(
                            run_dir=run_dir,
                            stage=stage,
                            round_number=1,
                            source_fingerprint_cache=fingerprint_cache,
                        ),
                        [],
                    )

                self.assertEqual(fingerprint.call_count, 4)
                manifest_path.write_text(
                    _review_manifest_text("changed-and-longer"),
                    encoding="utf-8",
                )
                self.assertIn(
                    "stale review source sha256: video_manifest.md",
                    review_input_snapshot_issues(
                        run_dir=run_dir,
                        stage="scene_detail",
                        round_number=1,
                        source_fingerprint_cache=fingerprint_cache,
                    ),
                )
                self.assertEqual(fingerprint.call_count, 5)

    def test_manifest_mutation_stales_passing_p400_snapshots_until_rematerialized(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_review_loop_p400_manifest_stale_") as td:
            run_dir = Path(td)
            for relpath in ("story.md", "visual_value.md", "script.md"):
                (run_dir / relpath).write_text(f"# {relpath}\n", encoding="utf-8")
            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text(
                _review_manifest_text("one"),
                encoding="utf-8",
            )

            first_manifest_sha = review_source_fingerprint(
                manifest_path,
                artifact_relpath="video_manifest.md",
                review_kind="review_loop",
                stage="script",
            ).sha256
            first_input_digests: dict[str, str] = {}
            for stage in P400_MANIFEST_BOUND_STAGES:
                MODULE.write_review_loop_round(run_dir=run_dir, stage=stage, round_number=1)
                snapshot_path = run_dir / review_input_snapshot_relpath(stage, 1)
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                sources = {
                    str(item["path"]): str(item["sha256"])
                    for item in snapshot["source_artifacts"]
                }
                self.assertEqual(sources["video_manifest.md"], first_manifest_sha, stage)
                self.assertEqual(
                    review_input_snapshot_issues(run_dir=run_dir, stage=stage, round_number=1),
                    [],
                    stage,
                )

                digest = str(snapshot["input_digest"])
                first_input_digests[stage] = digest
                critic_reports = _critic_reports(status="passed", digest=digest)
                for critic_number, report in enumerate(critic_reports, start=1):
                    (run_dir / critic_relpath(stage, 1, critic_number)).write_text(
                        report,
                        encoding="utf-8",
                    )
                aggregate = render_aggregated_review(
                    stage=stage,
                    round_number=1,
                    critic_reports=critic_reports,
                    status="passed",
                    expected_input_digest=digest,
                )
                (run_dir / aggregated_review_relpath(stage, 1)).write_text(
                    aggregate,
                    encoding="utf-8",
                )
                (run_dir / REVIEW_LOOP_SPECS[stage].final_report).write_text(
                    aggregate.replace("- status: passed", "- status: approved", 1),
                    encoding="utf-8",
                )

            manifest_path.write_text(
                _review_manifest_text("two"),
                encoding="utf-8",
            )
            second_manifest_sha = review_source_fingerprint(
                manifest_path,
                artifact_relpath="video_manifest.md",
                review_kind="review_loop",
                stage="script",
            ).sha256
            self.assertNotEqual(first_manifest_sha, second_manifest_sha)

            for stage in P400_MANIFEST_BOUND_STAGES:
                with self.subTest(stage=stage):
                    self.assertEqual(
                        review_input_snapshot_issues(
                            run_dir=run_dir,
                            stage=stage,
                            round_number=1,
                        ),
                        ["stale review source sha256: video_manifest.md"],
                    )

                    MODULE.write_review_loop_round(
                        run_dir=run_dir,
                        stage=stage,
                        round_number=1,
                    )
                    snapshot_path = run_dir / review_input_snapshot_relpath(stage, 1)
                    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                    sources = {
                        str(item["path"]): str(item["sha256"])
                        for item in snapshot["source_artifacts"]
                    }
                    self.assertEqual(sources["video_manifest.md"], second_manifest_sha)
                    self.assertNotEqual(
                        snapshot["input_digest"],
                        first_input_digests[stage],
                    )
                    self.assertEqual(
                        review_input_snapshot_issues(
                            run_dir=run_dir,
                            stage=stage,
                            round_number=1,
                        ),
                        [],
                    )
                    for critic_number in range(1, REVIEW_LOOP_CRITIC_COUNT + 1):
                        self.assertFalse(
                            (run_dir / critic_relpath(stage, 1, critic_number)).exists()
                        )
                    self.assertFalse(
                        (run_dir / aggregated_review_relpath(stage, 1)).exists()
                    )
                    self.assertFalse(
                        (run_dir / REVIEW_LOOP_SPECS[stage].final_report).exists()
                    )

    def test_aggregate_rejects_failed_or_duplicate_critic_claims(self) -> None:
        failed_reports = _critic_reports(status="passed")
        failed_reports[2] = failed_reports[2].replace("status: passed", "status: changes_requested")
        with self.assertRaisesRegex(ValueError, "cannot pass"):
            render_aggregated_review(
                stage="script",
                round_number=1,
                critic_reports=failed_reports,
                status="passed",
            )

        duplicate_reports = _critic_reports(status="passed")
        duplicate_reports[1] = duplicate_reports[1].replace("critic_2", "critic_1")
        with self.assertRaisesRegex(ValueError, "identity"):
            render_aggregated_review(
                stage="script",
                round_number=1,
                critic_reports=duplicate_reports,
            )

    def test_loop_state_cannot_mint_round_zero_or_external_pass_report(self) -> None:
        with self.assertRaisesRegex(ValueError, "completed round"):
            loop_state_updates(stage="story", status="passed", current_round=0)
        with self.assertRaisesRegex(ValueError, "canonical"):
            loop_state_updates(
                stage="story",
                status="passed",
                current_round=1,
                final_report="../outside.md",
            )

    def test_p400_scene_and_cut_review_surfaces_materialize_by_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_p400_review_loop_") as td:
            run_dir = Path(td)
            for rel in REVIEW_LOOP_SPECS["scene_set"].source_artifacts:
                (run_dir / rel).write_text(
                    (
                        _review_manifest_text()
                        if rel == "video_manifest.md"
                        else f"# {rel}\n"
                    ),
                    encoding="utf-8",
                )

            MODULE.write_review_loop_round(run_dir=run_dir, stage="scene_set", round_number=1)
            MODULE.write_review_loop_round(run_dir=run_dir, stage="scene_detail", round_number=1)
            MODULE.write_review_loop_round(run_dir=run_dir, stage="cut_blueprint", round_number=1)
            MODULE.write_review_loop_round(run_dir=run_dir, stage="production_readiness", round_number=1)

            self.assertTrue((run_dir / critic_prompt_relpath("scene_set", 1, 1)).exists())
            scene_prompt = (run_dir / critic_prompt_relpath("scene_set", 1, 1)).read_text(encoding="utf-8")
            self.assertIn("visual_value.md", scene_prompt)
            self.assertIn("critic_focus: scene_count_coverage", scene_prompt)
            self.assertIn("maximal_meaningful", scene_prompt)
            self.assertIn("next scene's authored starting condition", scene_prompt)
            scene_handoff_prompt = (run_dir / critic_prompt_relpath("scene_set", 1, 5)).read_text(encoding="utf-8")
            self.assertIn("critic_focus: handoff_integrity", scene_handoff_prompt)
            self.assertIn("each scene ending must visibly or audibly generate", scene_handoff_prompt)
            scene_aggregate_prompt = (run_dir / aggregator_prompt_relpath("scene_set", 1)).read_text(encoding="utf-8")
            self.assertIn("scene_count_coverage", scene_aggregate_prompt)
            self.assertIn("scene_count_gate", scene_aggregate_prompt)
            self.assertIn("Scene Specificity Gate", scene_aggregate_prompt)
            self.assertIn("scene_specificity_gate", scene_aggregate_prompt)
            self.assertIn("Reveal Order Gate", scene_aggregate_prompt)
            self.assertIn("Handoff Chain Gate", scene_aggregate_prompt)
            scene_review = render_aggregated_review(
                stage="scene_set",
                round_number=1,
                critic_reports=_critic_reports(status="passed", focus="scene_count_coverage"),
                status="passed",
            )
            self.assertIn("## Scene Specificity Gate", scene_review)
            self.assertIn("anti_template_language", scene_review)
            self.assertIn("distinct dramatic question, value shift, causal turn, and audience knowledge delta", scene_review)
            self.assertIn("each scene ending leaves physical evidence or a visible cause", scene_review)
            self.assertIn("artifacts are introduced, withheld, transformed, lost, or proven", scene_review)
            self.assertIn("future authored evidence", scene_review)
            self.assertTrue((run_dir / critic_prompt_relpath("scene_detail", 1, 1)).exists())
            detail_prompt = (run_dir / critic_prompt_relpath("scene_detail", 1, 1)).read_text(encoding="utf-8")
            self.assertIn("5-10 minute video", detail_prompt)
            self.assertIn("provider/model/input-mode capability", detail_prompt)
            self.assertNotIn("one cut as roughly 4-15 seconds", detail_prompt)
            self.assertIn("next scene", detail_prompt)
            self.assertIn("critic_focus: scene_detail_structure", detail_prompt)
            self.assertIn("exact authored event_beat_inventory", detail_prompt)
            self.assertIn("arbitrary nonblank beat_function", detail_prompt)
            self.assertIn("must_be_seen != false", detail_prompt)
            self.assertIn("including must_be_seen=false opt-outs", detail_prompt)
            self.assertIn(
                "`importance`, `target_duration_seconds`, and `estimated_duration_seconds` are optional planning annotations",
                detail_prompt,
            )
            self.assertIn("their absence alone is non-blocking", detail_prompt)
            self.assertIn("authored reveal/emotional weight", detail_prompt)
            self.assertIn("scene_intent.causal_turn remains required", detail_prompt)
            self.assertIn("does not require a beat_function label named turn", detail_prompt)
            self.assertIn("Do not require a fixed cut count or fixed beat-function ladder", detail_prompt)
            self.assertIn("add a cut only when it is an authored, uncovered distinct semantic obligation", detail_prompt)
            self.assertNotIn("scene_event setup/pressure/turn/payoff sequence", detail_prompt)
            detail_density_prompt = (run_dir / critic_prompt_relpath("scene_detail", 1, 2)).read_text(encoding="utf-8")
            self.assertIn("critic_focus: scene_detail_density", detail_density_prompt)
            self.assertIn("Authored emotional weight remains review evidence", detail_density_prompt)
            self.assertNotIn("optional duration or emotional-weight annotations", detail_density_prompt)
            detail_handoff_prompt = (run_dir / critic_prompt_relpath("scene_detail", 1, 3)).read_text(encoding="utf-8")
            self.assertIn("critic_focus: scene_detail_handoff", detail_handoff_prompt)
            self.assertIn("Verify incoming and outgoing concrete handoff", detail_handoff_prompt)
            detail_aggregate_prompt = (run_dir / aggregator_prompt_relpath("scene_detail", 1)).read_text(encoding="utf-8")
            self.assertIn("scene_detail_gate", detail_aggregate_prompt)
            self.assertIn("their absence alone is non-blocking", detail_aggregate_prompt)
            self.assertNotIn("scene_count_gate: for p410 stages", detail_aggregate_prompt)
            detail_review = render_aggregated_review(
                stage="scene_detail",
                round_number=1,
                critic_reports=_critic_reports(status="passed", focus="scene_detail_structure"),
                status="passed",
            )
            self.assertIn("## Scene Detail Gate", detail_review)
            self.assertIn("only when the authored scene semantics require it", detail_review)
            self.assertIn("do not infer required pressure/turn beat_function labels", detail_review)
            self.assertIn("value_shift.from/to is proven", detail_review)
            self.assertNotIn("absence of a value-shift contract", detail_review)
            self.assertIn("scene_intent.causal_turn remains required", detail_review)
            self.assertIn("end_situation semantically matches", detail_review)
            self.assertIn("incoming and outgoing handoffs connect to adjacent scenes", detail_review)
            self.assertTrue((run_dir / critic_prompt_relpath("cut_blueprint", 1, 1)).exists())
            cut_prompt = (run_dir / critic_prompt_relpath("cut_blueprint", 1, 1)).read_text(encoding="utf-8")
            self.assertIn("critic_focus: cut_intent_isolation", cut_prompt)
            self.assertIn("one intent", cut_prompt)
            self.assertIn("exact authored event_beat_inventory", cut_prompt)
            self.assertIn("arbitrary nonblank beat_function", cut_prompt)
            self.assertIn("distinct visual obligations require separate cuts", cut_prompt)
            self.assertIn("including must_be_seen=false opt-outs", cut_prompt)
            self.assertIn("uncovered distinct semantic obligation", cut_prompt)
            self.assertIn("thicken or re-split existing cut boundaries without increasing the count", cut_prompt)
            self.assertIn("does not require fixed beat_function labels", cut_prompt)
            self.assertNotIn("must be split into setup / pressure", cut_prompt)
            cut_handoff_prompt = (run_dir / critic_prompt_relpath("cut_blueprint", 1, 5)).read_text(encoding="utf-8")
            self.assertIn("critic_focus: duration_density_and_handoff", cut_handoff_prompt)
            self.assertIn("final-cut handoff", cut_handoff_prompt)
            coverage_prompt = (run_dir / critic_prompt_relpath("cut_blueprint", 1, 2)).read_text(encoding="utf-8")
            self.assertIn("critic_focus: scene_event_coverage", coverage_prompt)
            self.assertIn("exact authored event_beat_inventory", coverage_prompt)
            self.assertIn("ordered scene_event.event_sequence", coverage_prompt)
            self.assertIn("must_be_seen != false", coverage_prompt)
            self.assertIn("arbitrary nonblank beat_function", coverage_prompt)
            cut_aggregate_prompt = (run_dir / aggregator_prompt_relpath("cut_blueprint", 1)).read_text(encoding="utf-8")
            cut_review = render_aggregated_review(
                stage="cut_blueprint",
                round_number=1,
                critic_reports=_critic_reports(status="passed", focus="cut_intent_isolation"),
                status="passed",
            )
            self.assertIn("Cut Blueprint Gate", cut_review)
            self.assertIn("event_beat_inventory mirrors every exact ordered nonblank scene_event beat ID and beat_function", cut_review)
            self.assertIn("only beats with must_be_seen != false require assignment", cut_review)
            self.assertIn("optional advisory annotations whose absence alone is non-blocking", cut_review)
            self.assertIn("final handoff are sufficient", cut_review)
            self.assertIn("each cut states what the audience newly understands", cut_review)
            self.assertNotIn("absence of an audience-knowledge delta", cut_review)
            self.assertIn("each cut states how cause and result are visible", cut_review)
            self.assertIn("cut_blueprint_gate", cut_aggregate_prompt)
            self.assertIn("exact authored event_beat_inventory", cut_aggregate_prompt)
            self.assertIn("ordered scene_event.event_sequence", cut_aggregate_prompt)
            self.assertIn("must_be_seen != false", cut_aggregate_prompt)
            self.assertIn("valid one-beat scene", cut_aggregate_prompt)
            self.assertIn("including must_be_seen=false opt-outs", cut_aggregate_prompt)
            self.assertIn("do not require fixed beat_function labels", cut_aggregate_prompt)
            self.assertIn("audience_knowledge_delta and causal_proof are concrete", cut_aggregate_prompt)
            self.assertIn("their absence alone is non-blocking", cut_aggregate_prompt)
            self.assertNotIn("cuts cover setup/pressure/turn/payoff", cut_aggregate_prompt)
            self.assertTrue((run_dir / critic_prompt_relpath("production_readiness", 1, 1)).exists())
            readiness_prompt = (run_dir / critic_prompt_relpath("production_readiness", 1, 1)).read_text(encoding="utf-8")
            self.assertIn("Structure Auditor", readiness_prompt)
            self.assertIn("Duration Auditor", readiness_prompt)
            self.assertIn("Quality Auditor", readiness_prompt)
            self.assertIn("only when it introduces an uncovered distinct semantic obligation", readiness_prompt)
            self.assertIn("same obligation, thicken or re-split existing cut boundaries", readiness_prompt)
            self.assertIn(
                "`importance`, `target_duration_seconds`, and `estimated_duration_seconds` are optional planning annotations",
                readiness_prompt,
            )
            self.assertIn("Orchestrator", readiness_prompt)
            self.assertIn("Design Owner", readiness_prompt)
            self.assertIn("only agent allowed to edit downstream design artifacts", readiness_prompt)
            readiness_aggregate_prompt = (run_dir / aggregator_prompt_relpath("production_readiness", 1)).read_text(encoding="utf-8")
            self.assertIn("Design Owner-facing brief", readiness_aggregate_prompt)
            self.assertIn("design_owner_patch_brief", readiness_aggregate_prompt)
            self.assertIn("do not route edits to", readiness_aggregate_prompt)
            self.assertIn("uncovered distinct semantic obligation", readiness_aggregate_prompt)
            self.assertIn("their absence alone is non-blocking", readiness_aggregate_prompt)
            self.assertIn("Scene-level `importance`", readiness_aggregate_prompt)
            self.assertIn("required `video_manifest.md.video_metadata.target_duration_seconds`", readiness_prompt)
            readiness_review = render_aggregated_review(
                stage="production_readiness",
                round_number=1,
                critic_reports=_critic_reports(status="passed"),
                status="passed",
            )
            self.assertIn("## Design Owner Patch Brief", readiness_review)
            self.assertNotIn("## Generator Patch Brief", readiness_review)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["eval.scene_set.loop.status"], "running")
            self.assertEqual(state["eval.scene_detail.loop.status"], "running")
            self.assertEqual(state["eval.cut_blueprint.loop.status"], "running")
            self.assertEqual(state["eval.production_readiness.loop.status"], "running")
            self.assertEqual(classify_run_file("logs/eval/scene_set/round_01/aggregated_review.md").slot, "p410")
            self.assertEqual(classify_run_file("logs/eval/scene_detail/round_01/aggregated_review.md").slot, "p410")
            self.assertEqual(classify_run_file("logs/eval/cut_blueprint/round_01/aggregated_review.md").slot, "p420")
            self.assertEqual(classify_run_file("logs/eval/production_readiness/round_01/aggregated_review.md").slot, "p435")
            self.assertEqual(classify_run_file("production_readiness_review.md").slot, "p435")

    def test_asset_review_prompt_includes_p500_coverage_criteria(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_asset_review_loop_") as td:
            run_dir = Path(td)
            for rel in REVIEW_LOOP_SPECS["asset"].source_artifacts:
                (run_dir / rel).write_text(
                    (
                        _review_manifest_text()
                        if rel == "video_manifest.md"
                        else f"# {rel}\n"
                    ),
                    encoding="utf-8",
                )

            prompt = render_critic_prompt(run_dir=run_dir, stage="asset", round_number=1, critic_number=1)

            self.assertIn("Treat p520 coverage as the first gate", prompt)
            self.assertIn("asset_inventory.md", prompt)
            self.assertIn("characters, story-specific items, used locations, setpieces", prompt)
            self.assertIn("full-body front / side / back", prompt)
            self.assertIn("source_script_selectors[]", prompt)
            self.assertIn("execution_lane=bootstrap_builtin", prompt)
            self.assertIn("canonical output path", prompt)
            self.assertIn("reference count/input consistency", prompt)
            self.assertIn("generation/review status readiness", prompt)
            self.assertIn("Hard review", prompt)
            self.assertIn("Judgment review", prompt)
            self.assertIn("物語「<topic>」の scene10", prompt)

    def test_build_review_loop_round_rejects_missing_sources_before_state_write(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_review_loop_missing_") as td:
            run_dir = Path(td)

            with self.assertRaises(FileNotFoundError):
                MODULE.write_review_loop_round(run_dir=run_dir, stage="story", round_number=1)

            self.assertFalse((run_dir / "state.txt").exists())

    def test_running_prompt_only_loop_is_not_marked_done(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_review_loop_index_") as td:
            run_dir = Path(td)
            for rel in REVIEW_LOOP_SPECS["story"].source_artifacts:
                (run_dir / rel).write_text(f"# {rel}\n", encoding="utf-8")

            MODULE.write_review_loop_round(run_dir=run_dir, stage="story", round_number=1)
            index_text = build_run_index_markdown(run_dir)
            p230_start = index_text.index("#### p230 Story Eval/Improve Loop")
            p300_start = index_text.index("### p300 Visual Planning", p230_start)
            p230_section = index_text[p230_start:p300_start]

            self.assertIn("- status: `in_progress`", p230_section)
            self.assertNotIn("- status: `done`", p230_section)

    def test_paired_review_surfaces_have_distinct_loop_artifacts(self) -> None:
        self.assertEqual(critic_relpath("scene_implementation_hard", 1, 1).as_posix(), "logs/eval/scene_implementation_hard/round_01/critic_1.md")
        self.assertEqual(critic_relpath("scene_implementation_judgment", 1, 1).as_posix(), "logs/eval/scene_implementation_judgment/round_01/critic_1.md")
        self.assertEqual(classify_run_file("logs/eval/scene_implementation_hard/round_01/aggregated_review.md").slot, "p630")
        self.assertEqual(classify_run_file("logs/eval/scene_implementation_judgment/round_01/aggregated_review.md").slot, "p640")
        self.assertEqual(classify_run_file("logs/eval/video_generation_motion/round_01/aggregated_review.md").slot, "p820")
        self.assertEqual(classify_run_file("logs/eval/video_generation_review/round_01/aggregated_review.md").slot, "p850")
        self.assertEqual(classify_run_file("logs/eval/narration/round_01/aggregated_review.md").slot, "p720")

    def test_run_index_classifies_review_loop_artifacts(self) -> None:
        entry = classify_run_file("logs/eval/story/round_01/aggregated_review.md")
        self.assertEqual(entry.slot, "p230")
        self.assertEqual(entry.role, "log")
        self.assertIn("evaluator-improvement loop", entry.note)

        index_text = build_run_index_markdown(Path("/tmp/nonexistent-review-loop"), state={})
        self.assertIn("p230` | Story | `optional` | Story Eval/Improve Loop", index_text)
        self.assertIn("p930` | Render / QA / Runtime | `optional` | QA Eval/Improve Loop", index_text)


if __name__ == "__main__":
    unittest.main()
