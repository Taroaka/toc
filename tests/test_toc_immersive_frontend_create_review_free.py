"""Contracts for the review-free frontend create runner.

These tests intentionally exercise the runner boundary rather than the shared
review modules.  A frontend create must materialize real authored artifacts,
freeze concrete provider requests, and keep structural output validation.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = REPO_ROOT / "scripts" / "toc-immersive-frontend-run.py"


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "toc_immersive_frontend_create_review_free_under_test",
        RUNNER_PATH,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestFrontendCreateReviewFree(unittest.TestCase):
    def test_legacy_review_mode_is_accepted_but_has_no_production_effect(self) -> None:
        runner = load_runner()
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "output") as tmp:
            run_dir = Path(tmp)
            input_path = runner._write_create_input_contract(
                run_dir=run_dir,
                topic="創作",
                source="研究済みの素材から作る物語",
                experience="cinematic_story",
                source_run=None,
                target_duration_seconds=300,
                review_mode="preapproved",
            )
            payload = json.loads(input_path.read_text(encoding="utf-8"))

        self.assertNotIn("review_mode", payload)
        self.assertNotIn("review", payload)

    def test_retired_review_slots_are_not_part_of_frontend_sequence(self) -> None:
        runner = load_runner()
        retired = {
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
        self.assertTrue({"p410", "p420"}.issubset(set(runner.P650_SLOTS)))
        self.assertTrue(retired.isdisjoint(runner.P650_SLOTS))
        self.assertTrue(retired.isdisjoint(runner.P680_SLOTS))

    def test_runner_source_has_no_review_materialization_entrypoints(self) -> None:
        source = RUNNER_PATH.read_text(encoding="utf-8")
        forbidden = (
            "_review_foundation_stage",
            "_run_foundation_semantic_review",
            "materialize_review_loop_round",
            "write_review_input_snapshot",
            "_refresh_p400_review_artifacts",
            "_refresh_downstream_review_artifacts",
            "_refresh_review_loop_artifacts",
            "_refresh_downstream_review_input_snapshots",
            "run_pre_media_semantic_pipeline",
        )
        for symbol in forbidden:
            with self.subTest(symbol=symbol):
                self.assertNotIn(symbol, source)

    def test_p650_generation_freezes_requests_after_assets_without_semantic_review(self) -> None:
        runner = load_runner()
        from server import image_gen_app

        events: list[str] = []

        async def generate(*, run_dir: Path, kind: str) -> None:
            events.append(f"generate:{kind}")

        def asset_quality(_run_dir: Path) -> None:
            events.append("validate_assets")

        def asset_handoff(_run_dir: Path, *, asset_quality_passed: bool) -> None:
            self.assertTrue(asset_quality_passed)
            events.append("asset_handoff")

        def freeze(_run_dir: Path, **_kwargs) -> None:
            events.append("freeze_scene_requests")

        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "output") as tmp:
            run_dir = Path(tmp)
            with (
                patch.object(
                    image_gen_app,
                    "_generate_request_outputs",
                    side_effect=generate,
                ),
                patch.object(
                    image_gen_app,
                    "_validate_p560_asset_quality",
                    side_effect=asset_quality,
                ),
                patch.object(
                    image_gen_app,
                    "_mark_asset_generation_handoff",
                    side_effect=asset_handoff,
                ),
                patch.object(
                    image_gen_app,
                    "_mark_image_prompt_request_freeze_done",
                    side_effect=freeze,
                ),
            ):
                asyncio.run(runner.generate_images(run_dir, "p650"))

        self.assertEqual(
            events,
            [
                "generate:asset",
                "validate_assets",
                "asset_handoff",
                "freeze_scene_requests",
            ],
        )

    def test_p680_generation_delegates_provider_ready_create_lane(self) -> None:
        runner = load_runner()
        from server import image_gen_app

        create_images = AsyncMock(return_value=True)
        with patch.object(image_gen_app, "_generate_create_images", create_images):
            asyncio.run(runner.generate_images(Path("/tmp/example-run"), "p680"))

        create_images.assert_awaited_once_with(
            "toc-immersive-frontend-run",
            run_id="example-run",
        )


if __name__ == "__main__":
    unittest.main()
