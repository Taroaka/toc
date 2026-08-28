import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from server import image_gen_app
from toc.scene_acceptance_contract import resolve_criterion
from toc.scene_acceptance_contract import criterion_registry_payload
from toc.review_loop import review_guidance_for_stage
from toc.semantic_review import SemanticReviewStatus
from toc.semantic_review import semantic_review_relpaths


class TestSceneAcceptanceShiftLeftRuntime(unittest.TestCase):
    def test_scene_set_reviewer_prompts_project_the_canonical_registry(self) -> None:
        guidance_lines, reason_key_contract = (
            image_gen_app._scene_shard_review_guidance("scene_set")
        )
        runtime_guidance = "\n".join(guidance_lines) + "\n" + reason_key_contract
        review_loop_guidance = review_guidance_for_stage("scene_set")

        for criterion in criterion_registry_payload():
            if "scene_set" not in criterion["semantic_recheck_stages"]:
                continue
            self.assertIn(criterion["criterion_id"], runtime_guidance)
            self.assertIn(criterion["canonical_reason_key"], runtime_guidance)
            self.assertIn(criterion["criterion_id"], review_loop_guidance)
            self.assertIn(
                criterion["canonical_reason_key"],
                review_loop_guidance,
            )

    def test_recheckable_canonical_reason_allows_bounded_producer_repair(self) -> None:
        criterion = resolve_criterion(
            "scene_set.causal_proof_weak",
            stage="scene_set",
        )

        self.assertIsNotNone(criterion)
        self.assertEqual(criterion["owner"], "deterministic")
        self.assertFalse(criterion["provider_repair_allowed"])

        nonrepairable = resolve_criterion(
            "scene.canonical_event_ownership",
            stage="scene_set",
        )
        self.assertIsNotNone(nonrepairable)
        self.assertFalse(nonrepairable["provider_repair_allowed"])

    def test_repairable_recheck_does_not_trigger_shift_left_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            image_gen_app.append_state_snapshot(
                run_dir / "state.txt",
                {
                    "authoring.scene_set.preflight.status": "passed",
                    "authoring.scene_set.preflight.digest": "sha256:" + "a" * 64,
                },
            )
            report_path = run_dir / semantic_review_relpaths("scene_set")["report"]
            report_path.parent.mkdir(parents=True)
            report_path.write_text(
                "status: failed\n"
                "reason_keys: ["
                + ", ".join(
                    [
                        "scene_set.causal_proof_weak",
                        "scene_set.handoff_state_mismatch",
                        "scene_set.scene_event_missing_source_grounding",
                        *image_gen_app.SCENE_SET_PROMPT_SEMANTIC_REASON_KEYS,
                    ]
                )
                + "]\n",
                encoding="utf-8",
            )

            self.assertEqual(
                image_gen_app._scene_set_shift_left_escape_reason_keys(
                    run_dir,
                    "scene_set",
                ),
                [],
            )

    def test_criterion_id_and_unknown_reason_fail_closed_as_shift_left(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            image_gen_app.append_state_snapshot(
                run_dir / "state.txt",
                {
                    "authoring.scene_set.preflight.status": "passed",
                    "authoring.scene_set.preflight.digest": "sha256:" + "a" * 64,
                },
            )
            report_path = run_dir / semantic_review_relpaths("scene_set")["report"]
            report_path.parent.mkdir(parents=True)
            report_path.write_text(
                "status: failed\n"
                "reason_keys: [scene.canonical_event_ownership, scene_set.unknown_reason]\n",
                encoding="utf-8",
            )

            self.assertEqual(
                image_gen_app._scene_set_shift_left_escape_reason_keys(
                    run_dir,
                    "scene_set",
                ),
                [
                    "scene_set.scene_event_canonical_event_missing",
                    "scene_set.unknown_reason",
                ],
            )

    def test_nonrepairable_shift_left_escape_skips_producer_repair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            image_gen_app.append_state_snapshot(
                run_dir / "state.txt",
                {
                    "authoring.scene_set.preflight.status": "passed",
                    "authoring.scene_set.preflight.digest": "sha256:"
                    + "a" * 64,
                },
            )
            report_path = (
                run_dir / semantic_review_relpaths("scene_set")["report"]
            )
            report_path.parent.mkdir(parents=True)
            report_path.write_text(
                "\n".join(
                    [
                        "status: failed",
                        "blocked_entries: [scene:1]",
                        "reason_keys: [scene_set.scene_event_canonical_event_missing]",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            failed = SemanticReviewStatus(
                status="failed",
                entry_count=1,
                errors=("scene:1: causal proof is missing",),
            )
            repair = AsyncMock()

            with (
                patch.object(
                    image_gen_app,
                    "_reusable_passed_semantic_review",
                    return_value=None,
                ),
                patch.object(
                    image_gen_app,
                    "_run_semantic_review_once",
                    AsyncMock(return_value=failed),
                ),
                patch.object(
                    image_gen_app,
                    "_run_semantic_review_producer_repair",
                    repair,
                ),
                patch.object(
                    image_gen_app,
                    "write_app_server_debug_log",
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "shift-left escape"):
                    asyncio.run(
                        image_gen_app._run_semantic_review(
                            "job-1",
                            run_dir=run_dir,
                            stage="scene_set",
                            max_attempts=2,
                        )
                    )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        repair.assert_not_awaited()
        self.assertEqual(
            state["review.semantic.scene_set.shift_left_escape.routing"],
            "authoring_contract_defect",
        )
        self.assertEqual(
            state["review.semantic.scene_set.shift_left_escape.reason_keys"],
            "scene_set.scene_event_canonical_event_missing",
        )
        self.assertEqual(
            state["review.semantic.scene_set.repair.skipped_reason"],
            "shift_left_escape",
        )
        self.assertEqual(state["slot.p410.status"], "failed")


if __name__ == "__main__":
    unittest.main()
