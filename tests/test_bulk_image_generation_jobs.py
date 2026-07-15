from __future__ import annotations

import asyncio
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import image_gen_app
from server.app import app


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


REQUESTS = """# Image Generation Requests

## scene1

- tool: `codex_builtin_image`
- output: `assets/scenes/scene1.png`
- references: `[]`

```text
scene one
```

## scene2

- tool: `codex_builtin_image`
- output: `assets/scenes/scene2.png`
- references:
  - `previous scene`: `assets/scenes/scene1.png`

```text
scene two
```

## scene3

- tool: `codex_builtin_image`
- output: `assets/scenes/scene3.png`
- references: `[]`

```text
scene three
```
"""


def _payload(*, background: bool = True) -> dict:
    return {
        "run_id": "sample_run",
        "kind": "scene",
        "background": background,
        "items": [
            {
                "run_id": "sample_run",
                "kind": "scene",
                "item_id": "scene1",
                "prompt": "scene one",
                "references": [],
                "candidate_count": 1,
            },
            {
                "run_id": "sample_run",
                "kind": "scene",
                "item_id": "scene2",
                "prompt": "scene two",
                # This intentionally mirrors the old UI bug. The backend must
                # retain the canonical deferred reference instead of treating
                # scene2 as a no-reference image.
                "references": [],
                "candidate_count": 1,
            },
            {
                "run_id": "sample_run",
                "kind": "scene",
                "item_id": "scene3",
                "prompt": "scene three",
                "references": [],
                "candidate_count": 1,
            },
        ],
    }


def _wait_for_job(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/api/image-gen/generate-bulk/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["status"] in {"completed", "failed", "interrupted"}:
            return job
        time.sleep(0.01)
    raise AssertionError("bulk generation job did not finish")


def _clear_jobs() -> None:
    for task in list(getattr(image_gen_app, "_bulk_generation_tasks", {}).values()):
        task.cancel()
    getattr(image_gen_app, "_bulk_generation_tasks", {}).clear()
    getattr(image_gen_app, "_bulk_generation_jobs", {}).clear()


def test_background_bulk_job_orders_groups_and_imports_candidates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "output" / "sample_run"
        run_dir.mkdir(parents=True)
        (run_dir / "image_generation_requests.md").write_text(REQUESTS, encoding="utf-8")
        calls: list[tuple[str, list[str]]] = []
        scene1_completed = False

        async def fake_generate_one(actual_run_dir: Path, req, index: int) -> dict:
            nonlocal scene1_completed
            if req.item_id == "scene2":
                assert scene1_completed
                assert req.references == [
                    "assets/test/image_gen_candidates/scene1/scene1_candidate_01.png"
                ]
            calls.append((req.item_id, list(req.references)))
            await asyncio.sleep(0.01)
            destination = image_gen_app.candidate_path(actual_run_dir, req.item_id, index)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(PNG_BYTES)
            if req.item_id == "scene1":
                scene1_completed = True
            return {
                "index": index,
                "status": "completed",
                "path": destination.relative_to(actual_run_dir).as_posix(),
            }

        _clear_jobs()
        with (
            patch.dict("os.environ", {"TOC_SERVER_AUTH_DISABLED": "1"}),
            patch("server.image_gen_app.ROOT", root),
            patch("server.image_gen_app._generate_one", fake_generate_one),
            TestClient(app) as client,
        ):
            started = time.monotonic()
            response = client.post("/api/image-gen/generate-bulk", json=_payload())
            elapsed = time.monotonic() - started
            assert response.status_code == 202, response.text
            assert elapsed < 0.5
            created = response.json()
            assert created["status"] in {"queued", "running"}

            duplicate = client.post("/api/image-gen/generate-bulk", json=_payload())
            assert duplicate.status_code == 202
            assert duplicate.json()["jobId"] == created["jobId"]

            job = _wait_for_job(client, created["jobId"])
            # Simulate losing process-local lookup state. The reload endpoint
            # must rediscover the persisted snapshot from the run directory.
            image_gen_app._bulk_generation_jobs.clear()
            active = client.get(
                "/api/image-gen/runs/sample_run/generate-bulk/active?kind=scene"
            )

        assert job["status"] == "completed"
        assert job["groupCount"] == 2
        assert job["completedCount"] == 3
        assert [item_id for item_id, _refs in calls].index("scene2") > [
            item_id for item_id, _refs in calls
        ].index("scene1")
        assert active.status_code == 200
        assert active.json()["jobId"] == created["jobId"]
        assert (
            run_dir
            / "assets/test/image_gen_candidates/scene2/scene2_candidate_01.png"
        ).is_file()
        assert (
            run_dir / "logs/image_generation_jobs" / f"{created['jobId']}.json"
        ).is_file()
        _clear_jobs()


def test_background_bulk_job_blocks_only_failed_dependencies() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "output" / "sample_run"
        run_dir.mkdir(parents=True)
        (run_dir / "image_generation_requests.md").write_text(REQUESTS, encoding="utf-8")
        extra_reference = run_dir / "assets/references/extra.png"
        extra_reference.parent.mkdir(parents=True)
        extra_reference.write_bytes(PNG_BYTES)
        payload = _payload()
        payload["items"][1]["references"] = ["assets/references/extra.png"]
        calls: list[str] = []

        async def fake_generate_one(actual_run_dir: Path, req, index: int) -> dict:
            calls.append(req.item_id)
            if req.item_id == "scene1":
                raise RuntimeError("scene1 failed")
            destination = image_gen_app.candidate_path(actual_run_dir, req.item_id, index)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(PNG_BYTES)
            return {
                "index": index,
                "status": "completed",
                "path": destination.relative_to(actual_run_dir).as_posix(),
            }

        _clear_jobs()
        with (
            patch.dict("os.environ", {"TOC_SERVER_AUTH_DISABLED": "1"}),
            patch("server.image_gen_app.ROOT", root),
            patch("server.image_gen_app._generate_one", fake_generate_one),
            TestClient(app) as client,
        ):
            response = client.post("/api/image-gen/generate-bulk", json=payload)
            assert response.status_code == 202, response.text
            job = _wait_for_job(client, response.json()["jobId"])

        by_id = {result["itemId"]: result for result in job["results"]}
        assert job["status"] == "failed"
        assert by_id["scene1"]["status"] == "failed"
        assert by_id["scene2"]["status"] == "blocked"
        assert by_id["scene3"]["status"] == "completed"
        assert "scene2" not in calls
        assert "scene3" in calls
        _clear_jobs()


def test_background_bulk_job_keeps_canonical_dependency_when_references_are_edited() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        run_dir = root / "output" / "sample_run"
        run_dir.mkdir(parents=True)
        (run_dir / "image_generation_requests.md").write_text(REQUESTS, encoding="utf-8")
        extra_reference = run_dir / "assets/references/extra.png"
        extra_reference.parent.mkdir(parents=True)
        extra_reference.write_bytes(PNG_BYTES)
        payload = _payload()
        payload["items"][1]["references"] = ["assets/references/extra.png"]
        scene1_completed = False
        observed_scene2_references: list[str] = []

        async def fake_generate_one(actual_run_dir: Path, req, index: int) -> dict:
            nonlocal scene1_completed
            if req.item_id == "scene2":
                assert scene1_completed
                observed_scene2_references.extend(req.references)
            destination = image_gen_app.candidate_path(actual_run_dir, req.item_id, index)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(PNG_BYTES)
            if req.item_id == "scene1":
                scene1_completed = True
            return {
                "index": index,
                "status": "completed",
                "path": destination.relative_to(actual_run_dir).as_posix(),
            }

        _clear_jobs()
        with (
            patch.dict("os.environ", {"TOC_SERVER_AUTH_DISABLED": "1"}),
            patch("server.image_gen_app.ROOT", root),
            patch("server.image_gen_app._generate_one", fake_generate_one),
            TestClient(app) as client,
        ):
            response = client.post("/api/image-gen/generate-bulk", json=payload)
            assert response.status_code == 202, response.text
            job = _wait_for_job(client, response.json()["jobId"])

        assert job["status"] == "completed"
        assert job["groupCount"] == 2
        # The canonical producer is immutable for ordering and continuity;
        # explicit edits may add references without replacing that producer.
        assert observed_scene2_references == [
            "assets/test/image_gen_candidates/scene1/scene1_candidate_01.png",
            "assets/references/extra.png",
        ]
        _clear_jobs()


def test_global_slot_uses_queue_timeout_not_generation_timeout() -> None:
    observed: list[tuple[str, float]] = []

    @asynccontextmanager
    async def fake_slot(_lock_dir: Path, *, namespace: str, slots: int, timeout_seconds: float):
        assert namespace == "request-bound"
        assert slots > 0
        observed.append(("slot", timeout_seconds))
        yield "slot-1"

    @asynccontextmanager
    async def fake_mode(_lock_dir: Path, *, exclusive: bool, timeout_seconds: float):
        assert not exclusive
        observed.append(("mode", timeout_seconds))
        yield

    async def run_case() -> None:
        with (
            patch.object(image_gen_app, "IMAGE_GENERATION_ITEM_TIMEOUT_SECONDS", 11),
            patch.object(image_gen_app, "IMAGE_GENERATION_QUEUE_TIMEOUT_SECONDS", 123),
            patch.object(image_gen_app, "async_file_slot", fake_slot),
            patch.object(image_gen_app, "_global_image_generation_mode_lock", fake_mode),
        ):
            async with image_gen_app._global_image_generation_slot("request_bound_v2"):
                pass

    asyncio.run(run_case())
    assert observed == [("slot", 123), ("mode", 123)]


def test_bulk_job_reconcile_preserves_valid_disk_candidate_during_running_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "output" / "sample_run"
        run_dir.mkdir(parents=True)
        destination = image_gen_app.candidate_path(run_dir, "scene1", 1)
        destination.parent.mkdir(parents=True)
        destination.write_bytes(PNG_BYTES)
        job = {
            "results": [
                {
                    "itemId": "scene1",
                    "status": "running",
                    "candidates": [
                        {"index": 1, "status": "running", "path": None}
                    ],
                }
            ]
        }

        image_gen_app._reconcile_bulk_generation_job_candidates(job, run_dir)

    candidate = job["results"][0]["candidates"][0]
    assert candidate["status"] == "running"
    assert candidate["path"] == "assets/test/image_gen_candidates/scene1/scene1_candidate_01.png"


def test_bulk_job_interruption_does_not_erase_an_imported_candidate_path() -> None:
    path = "assets/test/image_gen_candidates/scene1/scene1_candidate_01.png"
    job = {
        "results": [
            {
                "itemId": "scene1",
                "status": "running",
                "candidates": [
                    {"index": 1, "status": "running", "path": path}
                ],
            }
        ]
    }

    image_gen_app._interrupt_bulk_generation_job(job, "server restarted")

    candidate = job["results"][0]["candidates"][0]
    assert candidate["status"] == "failed"
    assert candidate["path"] == path
