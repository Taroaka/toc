from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from server import image_gen_app
from server.app import app
from toc.harness import parse_state_file
from toc.runtime_locks import sync_file_lock


class P500ResumeServerLockTests(unittest.TestCase):
    def tearDown(self) -> None:
        image_gen_app._bulk_generation_jobs.clear()
        image_gen_app._bulk_generation_tasks.clear()

    def test_bulk_generation_cannot_start_during_create_resume_lease(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "output" / "sample"
            run_dir.mkdir(parents=True)
            request_item = image_gen_app.GenerateRequest(
                run_id="sample",
                kind="scene",
                item_id="scene1_cut1",
                prompt="cinematic prompt",
                references=[],
                candidate_count=1,
            )
            plan_item = image_gen_app._BulkGenerationPlanItem(
                id="scene1_cut1",
                output="assets/scenes/scene1_cut1.png",
                references=[],
                dependency_references=[],
                request=request_item,
            )
            payload = {
                "run_id": "sample",
                "kind": "scene",
                "items": [request_item.model_dump()],
                "concurrency": 1,
            }

            with (
                patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}),
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._prepare_bulk_generation_plan",
                    return_value=[[plan_item]],
                ),
                sync_file_lock(
                    run_dir / ".locks/create_resume.lock",
                    wait=False,
                ),
                TestClient(app) as client,
            ):
                foreground = client.post(
                    "/api/image-gen/generate-bulk",
                    json={**payload, "background": False},
                )
                background = client.post(
                    "/api/image-gen/generate-bulk",
                    json={**payload, "background": True},
                )
                single = client.post(
                    "/api/image-gen/generate",
                    json=request_item.model_dump(),
                )

        self.assertEqual(foreground.status_code, 409)
        self.assertEqual(background.status_code, 409)
        self.assertEqual(single.status_code, 409)
        self.assertEqual(
            foreground.json()["detail"],
            "run create/resume is already active",
        )
        self.assertEqual(
            background.json()["detail"],
            "run create/resume is already active",
        )
        self.assertEqual(
            single.json()["detail"],
            "run create/resume is already active",
        )

    def test_background_bulk_releases_create_resume_lease_on_completion(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run_dir = root / "output" / "sample"
            run_dir.mkdir(parents=True)
            request_item = image_gen_app.GenerateRequest(
                run_id="sample",
                kind="scene",
                item_id="scene1_cut1",
                prompt="cinematic prompt",
                references=[],
                candidate_count=1,
            )
            plan_item = image_gen_app._BulkGenerationPlanItem(
                id="scene1_cut1",
                output="assets/scenes/scene1_cut1.png",
                references=[],
                dependency_references=[],
                request=request_item,
            )

            async def no_output(*_args, **_kwargs):
                return {"status": "failed", "path": None}

            with (
                patch.dict(os.environ, {"TOC_SERVER_AUTH_DISABLED": "1"}),
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app._prepare_bulk_generation_plan",
                    return_value=[[plan_item]],
                ),
                patch(
                    "server.image_gen_app._generate_one",
                    side_effect=no_output,
                ),
                TestClient(app) as client,
            ):
                response = client.post(
                    "/api/image-gen/generate-bulk",
                    json={
                        "run_id": "sample",
                        "kind": "scene",
                        "items": [request_item.model_dump()],
                        "concurrency": 1,
                        "background": True,
                    },
                )
                self.assertEqual(response.status_code, 202)
                job_id = response.json()["jobId"]
                for _attempt in range(100):
                    status = client.get(
                        f"/api/image-gen/generate-bulk/{job_id}"
                    ).json()["status"]
                    if status not in {"queued", "running"}:
                        break
                    time.sleep(0.01)
                else:
                    self.fail("background bulk job did not finish")

            with sync_file_lock(
                run_dir / ".locks/create_resume.lock",
                wait=False,
            ):
                pass

    def test_materialized_p650_allows_pending_nonexecuted_asset_media(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            required = (
                "research.md",
                "story.md",
                "visual_value.md",
                "script.md",
                "asset_generation_requests.md",
                "asset_generation_manifest.md",
                "asset_generation_request_snapshot.json",
                "image_generation_requests.md",
                "image_generation_request_snapshot.json",
                "p000_index.md",
            )
            for name in required:
                (run_dir / name).write_text("x" * 100, encoding="utf-8")
            (run_dir / "video_manifest.md").write_text(
                "scenes:\n  - scene_id: scene1\nassets:\n  characters: []\n"
                + ("# current authored manifest\n" * 4),
                encoding="utf-8",
            )
            state_lines = [
                "runtime.scaffold.content_status=authored",
                "review.image_prompt.request_freeze.status=reviewed_draft",
                "review.image_prompt.request_freeze.reviewed_request_revision=revision-1",
            ]
            for slot in image_gen_app.P650_FIXED_SLOTS:
                status = "pending" if slot in {"p560", "p570", "p650"} else "done"
                state_lines.append(f"slot.{slot}.status={status}")
            (run_dir / "state.txt").write_text(
                "\n".join(state_lines) + "\n---\n",
                encoding="utf-8",
            )
            request_item = SimpleNamespace(output="assets/example.png")
            with (
                patch(
                    "server.image_gen_app.safe_run_dir",
                    return_value=run_dir,
                ),
                patch(
                    "server.image_gen_app._manifest_cut_contract",
                    return_value=([], set()),
                ),
                patch(
                    "server.image_gen_app.load_request_items",
                    return_value=[request_item],
                ),
                patch(
                    "server.image_gen_app._validate_image_prompt_request_revision",
                    return_value="revision-1",
                ),
                patch("server.image_gen_app._validate_semantic_reviews"),
                patch(
                    "server.image_gen_app._validate_semantic_reviews_for_media_generation"
                ),
                patch(
                    "server.image_gen_app._refresh_deterministic_image_prompt_review_if_stale"
                ),
            ):
                image_gen_app._validate_materialized_p650_run("sample")


class P500ResumeAssetGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_p680_marks_asset_slots_before_p650_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td)
            (run_dir / "state.txt").write_text(
                "slot.p550.status=pending\nslot.p560.status=pending\n"
                "slot.p570.status=pending\n---\n",
                encoding="utf-8",
            )
            observed_before_preflight: dict[str, str] = {}

            async def record_preflight(*_args, **_kwargs) -> None:
                observed_before_preflight.update(
                    parse_state_file(run_dir / "state.txt")
                )

            with (
                patch("server.image_gen_app.safe_run_dir", return_value=run_dir),
                patch(
                    "server.image_gen_app._set_create_job",
                    new=AsyncMock(),
                ),
                patch(
                    "server.image_gen_app._run_pre_asset_semantic_fixed_point",
                    new=AsyncMock(return_value=None),
                ),
                patch("server.image_gen_app._validate_pre_asset_provider_gate"),
                patch(
                    "server.image_gen_app._run_semantic_review_for_media_generation",
                    new=AsyncMock(return_value=None),
                ),
                patch(
                    "server.image_gen_app._generate_request_outputs",
                    new=AsyncMock(),
                ),
                patch("server.image_gen_app._validate_p560_asset_quality"),
                patch(
                    "server.image_gen_app._generate_scene_outputs_after_p650_preflight",
                    new=AsyncMock(side_effect=record_preflight),
                ),
            ):
                result = await image_gen_app._generate_create_images(
                    "resume-p680",
                    run_id="sample",
                )

            self.assertTrue(result)
            self.assertEqual(observed_before_preflight["slot.p550.status"], "done")
            self.assertEqual(observed_before_preflight["slot.p560.status"], "done")
            self.assertEqual(observed_before_preflight["slot.p570.status"], "done")


if __name__ == "__main__":
    unittest.main()
