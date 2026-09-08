from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from server.image_gen import read_run_progress
from toc.production_contract import RETIRED_REVIEW_SLOTS
from toc.run_index import SLOT_BY_CODE, build_run_index_markdown


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestProductionContract(unittest.TestCase):
    def test_retired_review_slots_are_not_active_slots(self) -> None:
        expected = {
            "p130",
            "p230",
            "p320",
            "p430",
            "p435",
            "p540",
            "p630",
            "p640",
            "p720",
            "p820",
            "p850",
            "p930",
        }
        self.assertEqual(set(RETIRED_REVIEW_SLOTS), expected)
        self.assertTrue(expected.isdisjoint(SLOT_BY_CODE))
        for code in ("p410", "p420", "p570", "p680", "p750"):
            self.assertIn(code, SLOT_BY_CODE)

    def test_run_index_ignores_historical_review_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_production_contract_") as td:
            run_dir = Path(td) / "topic_20990101_0000"
            run_dir.mkdir(parents=True)
            index = build_run_index_markdown(
                run_dir,
                state={
                    "status": "SCRIPT",
                    "runtime.review_mode": "preapproved",
                    "gate.story_review": "required",
                    "review.story.status": "pending",
                    "slot.p230.status": "blocked",
                    "slot.p410.status": "done",
                    "slot.p420.status": "pending",
                },
            )
            self.assertNotIn("review_mode:", index)
            self.assertNotIn("pending_gates:", index)
            self.assertNotIn("p230", index)
            self.assertIn("#### p410 Scene Completion", index)
            self.assertIn("#### p420 Cut Blueprint / Script Authoring", index)

    def test_progress_ignores_retired_slot_blockers_and_review_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_production_contract_") as td:
            run_dir = Path(td) / "topic_20990101_0001"
            run_dir.mkdir(parents=True)
            (run_dir / "p000_index.md").write_text(
                build_run_index_markdown(run_dir, state={"status": "INIT"})
                + "\n#### p230 Historical Story Review\n\n- status: `blocked`\n",
                encoding="utf-8",
            )
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "status=SCRIPT",
                        "slot.p230.status=blocked",
                        "slot.p410.status=done",
                        "slot.p420.status=in_progress",
                        "gate.story_review=required",
                        "review.story.status=pending",
                        "runtime.review_mode=preapproved",
                        "---",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            progress = read_run_progress(run_dir, validate_request_outputs=False)
            self.assertNotIn("reviewMode", progress)
            self.assertNotIn("reviewPolicy", progress)
            self.assertNotIn("pendingGates", progress)
            self.assertFalse(any(slot["code"] == "p230" for slot in progress["slots"]))

    def test_grounding_contract_has_no_approval_input_requirements(self) -> None:
        contract = yaml.safe_load(
            (REPO_ROOT / "workflow" / "stage-grounding.yaml").read_text(
                encoding="utf-8"
            )
        )
        for stage in contract["stages"].values():
            self.assertNotIn("requires_approved_input", stage)
            for check in stage.get("required_state", []):
                self.assertNotIn("review.", str(check.get("key", "")))
                self.assertNotIn("eval.", str(check.get("key", "")))


if __name__ == "__main__":
    unittest.main()
