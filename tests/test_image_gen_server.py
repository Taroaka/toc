from __future__ import annotations

import tempfile
import unittest
import sys
import os
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server import image_gen
from server.app import app


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


SAMPLE_REQUESTS = """# Image Generation Requests

## scene1_cut1

- tool: `google_nanobanana_2`
- generation_status: `created`
- asset_type: `reusable_still`
- execution_lane: `standard`
- reference_count: `2`
- output: `assets/scenes/scene01_cut01.png`
- references:
  - `人物参照画像1`: `assets/characters/hero.png`
  - `人物参照画像2`: `assets/objects/box.png`

```text
cinematic prompt
line two
```

## scene2_cut1

- tool: `google_nanobanana_2`
- reference_count: `0`
- output: `assets/scenes/scene02_cut01.png`
- references: `[]`

```text
no reference prompt
```
"""


class ImageGenParserTests(unittest.TestCase):
    def test_parse_request_markdown_extracts_prompt_refs_and_lane(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "assets/scenes").mkdir(parents=True)
            (run_dir / "assets/scenes/scene01_cut01.png").write_bytes(b"image")

            items = image_gen.parse_request_markdown(SAMPLE_REQUESTS, kind="scene", run_dir=run_dir)

        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].id, "scene1_cut1")
        self.assertEqual(items[0].prompt, "cinematic prompt\nline two")
        self.assertEqual(items[0].references, ["assets/characters/hero.png", "assets/objects/box.png"])
        self.assertEqual(items[0].reference_count, 2)
        self.assertEqual(items[0].execution_lane, "standard")
        self.assertEqual(items[0].existing_image, "assets/scenes/scene01_cut01.png")
        self.assertEqual(items[1].reference_count, 0)
        self.assertEqual(items[1].execution_lane, "bootstrap_builtin")

    def test_reference_options_use_extensionless_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "assets/characters").mkdir(parents=True)
            (run_dir / "assets/characters/hero.png").write_bytes(b"png")
            (run_dir / "assets/characters/hero.txt").write_text("ignore", encoding="utf-8")

            refs = image_gen.list_reference_options(run_dir)

        self.assertEqual([r.path for r in refs], ["assets/characters/hero.png"])
        self.assertEqual([r.label for r in refs], ["hero"])

    def test_insert_candidate_backs_up_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            candidate = run_dir / "assets/test/image_gen_candidates/scene1/candidate_01.png"
            output = run_dir / "assets/scenes/scene01.png"
            candidate.parent.mkdir(parents=True)
            output.parent.mkdir(parents=True)
            candidate.write_bytes(b"new")
            output.write_bytes(b"old")

            result = image_gen.insert_candidate(run_dir, candidate, "assets/scenes/scene01.png")

            self.assertEqual(output.read_bytes(), b"new")
            self.assertIsNotNone(result["backup"])
            self.assertTrue((run_dir / str(result["backup"])).exists())

    def test_insert_candidate_rejects_non_candidate_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            source = run_dir / "assets/scenes/other.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"not a candidate")

            with self.assertRaises(ValueError):
                image_gen.insert_candidate(run_dir, source, "assets/scenes/scene01.png")

    def test_insert_candidate_rejects_non_assets_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            candidate = run_dir / "assets/test/image_gen_candidates/scene1/candidate_01.png"
            candidate.parent.mkdir(parents=True)
            candidate.write_bytes(b"new")

            with self.assertRaises(ValueError):
                image_gen.insert_candidate(run_dir, candidate, "video_manifest.md")


class ImageGenApiTests(unittest.TestCase):
    def test_runs_endpoint_lists_output_folders(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/image-gen/runs")

        self.assertEqual(response.status_code, 200)
        self.assertIn("runs", response.json())

    def test_generate_uses_saved_path_and_does_not_scan_latest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            saved = Path(tmp) / "generated.png"
            saved.write_bytes(PNG_BYTES)

            class FakeResult:
                saved_path = saved
                revised_prompt = None
                status = "completed"

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **_kwargs):
                    return FakeResult()

            with patch("server.app.ROOT", Path(tmp)), patch("server.app.CodexAppServerClient", FakeClient):
                with TestClient(app) as client:
                    response = client.post(
                        "/api/image-gen/generate",
                        json={
                            "run_id": "sample_run",
                            "kind": "scene",
                            "item_id": "scene1_cut1",
                            "prompt": "prompt",
                            "references": [],
                            "candidate_count": 1,
                        },
                    )

            self.assertEqual(response.status_code, 200)
            path = response.json()["candidates"][0]["path"]
            self.assertEqual((run_dir / path).read_bytes(), PNG_BYTES)

    def test_api_requires_token_when_configured(self) -> None:
        with patch.dict(os.environ, {"TOC_SERVER_TOKEN": "secret"}):
            with TestClient(app) as client:
                blocked = client.get("/api/image-gen/runs")
                allowed = client.get("/api/image-gen/runs", headers={"X-ToC-Local-Token": "secret"})

        self.assertEqual(blocked.status_code, 401)
        self.assertEqual(allowed.status_code, 200)

    def test_invalid_run_id_returns_400(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/image-gen/requests?run_id=../x&kind=scene")

        self.assertEqual(response.status_code, 400)

    def test_file_endpoint_rejects_non_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "video_manifest.md").write_text("manifest", encoding="utf-8")

            with patch("server.app.ROOT", Path(tmp)):
                with TestClient(app) as client:
                    response = client.get("/api/image-gen/file?run_id=sample_run&path=video_manifest.md")

        self.assertEqual(response.status_code, 400)

    def test_bulk_generation_uses_parent_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent_run = root / "output" / "parent"
            child_run = root / "output" / "child"
            parent_run.mkdir(parents=True)
            child_run.mkdir(parents=True)
            saved = root / "generated.png"
            saved.write_bytes(PNG_BYTES)
            test_case = self

            class FakeResult:
                saved_path = saved
                revised_prompt = None
                status = "completed"

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start(self):
                    return None

                async def stop(self):
                    return None

                async def generate_image(self, **kwargs):
                    test_case.assertEqual(kwargs["run_dir"].name, "parent")
                    return FakeResult()

            with patch("server.app.ROOT", root), patch("server.app.CodexAppServerClient", FakeClient):
                with TestClient(app) as client:
                    response = client.post(
                        "/api/image-gen/generate-bulk",
                        json={
                            "run_id": "parent",
                            "kind": "scene",
                            "items": [
                                {
                                    "run_id": "child",
                                    "kind": "asset",
                                    "item_id": "scene1_cut1",
                                    "prompt": "prompt",
                                    "references": [],
                                    "candidate_count": 1,
                                }
                            ],
                        },
                    )
                    generated_exists = (
                        parent_run / "assets/test/image_gen_candidates/scene1_cut1/candidate_01.png"
                    ).resolve().exists()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(generated_exists)


if __name__ == "__main__":
    unittest.main()
