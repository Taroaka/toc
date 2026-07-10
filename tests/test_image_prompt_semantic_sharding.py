from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build-semantic-review-pack.py"
sys.path.insert(0, str(REPO_ROOT))

from server import image_gen_app  # noqa: E402
from server.codex_app_server import CodexAppServerTransportError  # noqa: E402


def _load_pack_builder():
    spec = importlib.util.spec_from_file_location("build_semantic_review_pack", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _collection(entries: list[dict[str, object]]) -> str:
    lines = ["# Semantic Review Collection: image_prompt", ""]
    for entry in entries:
        entry_id = str(entry["selector"])
        lines.extend(
            [
                f"## {entry_id}",
                "",
                "```json",
                json.dumps(entry, ensure_ascii=False),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def _scope_payload(entries: list[dict[str, object]]) -> dict[str, object]:
    builder = _load_pack_builder()
    return builder.image_prompt_scene_shard_plan(entries)


class ImagePromptSemanticPackShardTests(unittest.TestCase):
    def test_plan_groups_cut_and_scene_composite_entries_with_exact_deterministic_coverage(self) -> None:
        builder = _load_pack_builder()
        entries = [
            {"selector": "scene20_cut02", "scene_id": 20, "review_scope": "all_entries"},
            {"selector": "scene10_cut01", "scene_id": 10, "review_scope": "all_entries"},
            {"selector": "scene20", "scene_id": 20, "review_scope": "scene_composite"},
            {"selector": "scene20_cut01", "scene_id": 20, "review_scope": "all_entries"},
            {"selector": "scene10", "scene_id": 10, "review_scope": "scene_composite"},
        ]

        plan = builder.image_prompt_scene_shard_plan(entries)

        self.assertEqual(plan["review_scope"], "per_scene_shards")
        self.assertEqual(plan["coverage"]["status"], "valid")
        self.assertEqual(plan["coverage"]["expected_entry_count"], 5)
        self.assertEqual([shard["shard_id"] for shard in plan["shards"]], ["scene_10", "scene_20"])
        self.assertEqual(
            plan["shards"][0]["entry_ids"],
            ["scene10_cut01", "scene10"],
        )
        self.assertEqual(
            plan["shards"][1]["entry_ids"],
            ["scene20_cut02", "scene20", "scene20_cut01"],
        )
        self.assertEqual(
            plan["coverage"]["assigned_entry_ids"],
            ["scene10_cut01", "scene10", "scene20_cut02", "scene20", "scene20_cut01"],
        )

    def test_plan_fails_closed_for_zero_duplicate_or_unassigned_entries(self) -> None:
        builder = _load_pack_builder()

        with self.assertRaisesRegex(ValueError, "zero entries"):
            builder.image_prompt_scene_shard_plan([])
        with self.assertRaisesRegex(ValueError, "duplicate entry ids"):
            builder.image_prompt_scene_shard_plan(
                [
                    {"selector": "scene10_cut01", "scene_id": 10},
                    {"selector": "scene10_cut01", "scene_id": 10},
                ]
            )
        with self.assertRaisesRegex(ValueError, "cannot assign entry"):
            builder.image_prompt_scene_shard_plan([{"selector": "orphan_cut"}])

    def test_materialization_writes_scene_local_artifacts_and_scope_manifest(self) -> None:
        builder = _load_pack_builder()
        entries = [
            {"selector": "scene10_cut01", "scene_id": 10, "review_scope": "all_entries"},
            {"selector": "scene10", "scene_id": 10, "review_scope": "scene_composite"},
            {"selector": "scene20_cut01", "scene_id": 20, "review_scope": "all_entries"},
            {"selector": "scene20", "scene_id": 20, "review_scope": "scene_composite"},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            canonical_scope = run_dir / "logs/review/semantic/image_prompt.scope.json"
            canonical_report = run_dir / "logs/review/semantic/image_prompt.report.md"
            plan = builder.materialize_image_prompt_scene_shards(
                run_dir=run_dir,
                entries=entries,
                canonical_scope_path=canonical_scope,
                canonical_report_path=canonical_report,
            )

            first = plan["shards"][0]
            second = plan["shards"][1]
            first_collection = (run_dir / first["artifacts"]["collection"]).read_text(encoding="utf-8")
            second_collection = (run_dir / second["artifacts"]["collection"]).read_text(encoding="utf-8")
            first_scope = json.loads((run_dir / first["artifacts"]["scope"]).read_text(encoding="utf-8"))

        self.assertIn("scene10_cut01", first_collection)
        self.assertIn("## scene10", first_collection)
        self.assertNotIn("scene20_cut01", first_collection)
        self.assertIn("scene20_cut01", second_collection)
        self.assertNotIn("scene10_cut01", second_collection)
        self.assertEqual(first_scope["entry_ids"], ["scene10_cut01", "scene10"])
        self.assertEqual(first_scope["review_scope"], "single_scene_image_prompt_shard")
        self.assertEqual(first_scope["canonical_scope"], "logs/review/semantic/image_prompt.scope.json")


class ImagePromptSemanticServerShardTests(unittest.TestCase):
    @staticmethod
    def _write_pack(run_dir: Path, entries: list[dict[str, object]]) -> None:
        paths = image_gen_app.semantic_review_relpaths("image_prompt")
        collection_path = run_dir / paths["collection"]
        collection_path.parent.mkdir(parents=True, exist_ok=True)
        collection_path.write_text(_collection(entries), encoding="utf-8")
        scope = _scope_payload(entries)
        scope.update(
            {
                "stage": "image_prompt",
                "entry_count": len(entries),
                "entry_ids": [str(entry["selector"]) for entry in entries],
                "source_artifacts": ["video_manifest.md"],
            }
        )
        (run_dir / paths["scope"]).write_text(json.dumps(scope, ensure_ascii=False) + "\n", encoding="utf-8")
        (run_dir / paths["prompt"]).write_text("# canonical image prompt review\n", encoding="utf-8")
        (run_dir / paths["report"]).write_text("status: pending\n", encoding="utf-8")

    def test_runtime_reviews_one_shard_per_scene_with_bounded_concurrency_and_exact_coverage(self) -> None:
        entries = [
            {"selector": "scene10_cut01", "scene_id": 10, "review_scope": "all_entries"},
            {"selector": "scene10", "scene_id": 10, "review_scope": "scene_composite"},
            {"selector": "scene20_cut01", "scene_id": 20, "review_scope": "all_entries"},
            {"selector": "scene20", "scene_id": 20, "review_scope": "scene_composite"},
        ]
        active_turns = 0
        max_active_turns = 0
        review_turns = 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output/sample_run"
            run_dir.mkdir(parents=True)

            def fake_build_pack(cmd, **_kwargs):
                self._write_pack(run_dir, entries)
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    nonlocal active_turns, max_active_turns, review_turns
                    active_turns += 1
                    max_active_turns = max(max_active_turns, active_turns)
                    review_turns += 1
                    try:
                        await asyncio.sleep(0.02)
                        report_path = Path(text.split("Write the final report to `", 1)[1].split("`", 1)[0])
                        expected = json.loads(text.split("Expected reviewed_entries exactly once: ", 1)[1].splitlines()[0])
                        report_path.write_text(
                            "\n".join(
                                [
                                    "status: passed",
                                    "reviewed_entries: [" + ", ".join(expected) + "]",
                                    "blocked_entries: []",
                                    "findings: []",
                                    "failed_selectors: []",
                                    "reason_keys: []",
                                    "",
                                ]
                            ),
                            encoding="utf-8",
                        )
                        return []
                    finally:
                        active_turns -= 1

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", lambda **_kwargs: FakeClient()),
                patch.dict(os.environ, {"TOC_IMAGE_PROMPT_REVIEW_CONCURRENCY": "2"}),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage="image_prompt",
                        attempt=1,
                        max_attempts=1,
                        final_attempt=True,
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            report = (run_dir / image_gen_app.semantic_review_relpaths("image_prompt")["report"]).read_text(encoding="utf-8")

        self.assertTrue(result.passed)
        self.assertEqual(review_turns, 2)
        self.assertEqual(max_active_turns, 2)
        self.assertEqual(state["review.semantic.image_prompt.shards.count"], "2")
        self.assertEqual(state["review.semantic.image_prompt.shards.status"], "passed")
        self.assertIn("reviewed_entries:\n  - scene10_cut01\n  - scene10\n  - scene20_cut01\n  - scene20", report)

    def test_selector_coverage_error_blocks_only_its_scene_and_preserves_passing_scene(self) -> None:
        entries = [
            {"selector": "scene10_cut01", "scene_id": 10, "review_scope": "all_entries"},
            {"selector": "scene10", "scene_id": 10, "review_scope": "scene_composite"},
            {"selector": "scene20_cut01", "scene_id": 20, "review_scope": "all_entries"},
            {"selector": "scene20", "scene_id": 20, "review_scope": "scene_composite"},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output/sample_run"
            run_dir.mkdir(parents=True)

            def fake_build_pack(cmd, **_kwargs):
                self._write_pack(run_dir, entries)
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    report_path = Path(text.split("Write the final report to `", 1)[1].split("`", 1)[0])
                    expected = json.loads(text.split("Expected reviewed_entries exactly once: ", 1)[1].splitlines()[0])
                    reviewed = expected if expected[0].startswith("scene10") else [expected[0], expected[0]]
                    report_path.write_text(
                        "\n".join(
                            [
                                "status: passed",
                                "reviewed_entries: [" + ", ".join(reviewed) + "]",
                                "blocked_entries: []",
                                "findings: []",
                                "failed_selectors: []",
                                "reason_keys: []",
                                "",
                            ]
                        ),
                        encoding="utf-8",
                    )
                    return []

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", lambda **_kwargs: FakeClient()),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage="image_prompt",
                        attempt=1,
                        max_attempts=2,
                        final_attempt=False,
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            report = (run_dir / image_gen_app.semantic_review_relpaths("image_prompt")["report"]).read_text(encoding="utf-8")

        self.assertFalse(result.passed)
        self.assertEqual(state["review.semantic.image_prompt.shards.failed_count"], "1")
        self.assertEqual(state["review.semantic.image_prompt.shards.scene_10.status"], "passed")
        self.assertEqual(state["review.semantic.image_prompt.shards.scene_20.status"], "failed")
        self.assertEqual(
            state["review.semantic.image_prompt.shards.scene_20.blocked_entries"],
            "scene20_cut01, scene20",
        )
        self.assertIn("semantic_review_selector_coverage_invalid", report)
        self.assertIn("blocked_entries:\n  - scene20_cut01\n  - scene20", report)
        self.assertNotIn("blocked_entries:\n  - scene10_cut01", report)
        self.assertIn("reviewed_entries:\n  - scene10_cut01\n  - scene10\n  - scene20_cut01\n  - scene20", report)

    def test_transport_retry_reruns_only_failed_scene_shard(self) -> None:
        entries = [
            {"selector": "scene10_cut01", "scene_id": 10, "review_scope": "all_entries"},
            {"selector": "scene10", "scene_id": 10, "review_scope": "scene_composite"},
            {"selector": "scene20_cut01", "scene_id": 20, "review_scope": "all_entries"},
            {"selector": "scene20", "scene_id": 20, "review_scope": "scene_composite"},
        ]
        turn_counts: dict[str, int] = {}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output/sample_run"
            run_dir.mkdir(parents=True)

            def fake_build_pack(cmd, **_kwargs):
                self._write_pack(run_dir, entries)
                return subprocess.CompletedProcess(cmd, 0, "", "")

            class FakeClient:
                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    shard_id = text.split("Review only image_prompt scene shard `", 1)[1].split("`", 1)[0]
                    turn_counts[shard_id] = turn_counts.get(shard_id, 0) + 1
                    if shard_id == "scene_20" and turn_counts[shard_id] == 1:
                        raise CodexAppServerTransportError("turn timed out")
                    report_path = Path(text.split("Write the final report to `", 1)[1].split("`", 1)[0])
                    expected = json.loads(text.split("Expected reviewed_entries exactly once: ", 1)[1].splitlines()[0])
                    report_path.write_text(
                        "status: passed\n"
                        + "reviewed_entries: ["
                        + ", ".join(expected)
                        + "]\nblocked_entries: []\nfindings: []\nfailed_selectors: []\nreason_keys: []\n",
                        encoding="utf-8",
                    )
                    return []

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", lambda **_kwargs: FakeClient()),
                patch.dict(os.environ, {"TOC_IMAGE_PROMPT_TRANSPORT_RETRY_ATTEMPTS": "2"}),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage="image_prompt",
                        attempt=1,
                        max_attempts=1,
                        final_attempt=True,
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertTrue(result.passed)
        self.assertEqual(turn_counts, {"scene_10": 1, "scene_20": 2})
        self.assertEqual(state["review.semantic.image_prompt.shards.scene_20.transport.status"], "recovered")
        self.assertEqual(state["review.semantic.image_prompt.shards.scene_20.transport.retry_count"], "1")

    def test_scope_validation_fails_closed_on_zero_missing_duplicate_or_collection_gap(self) -> None:
        valid = {
            "entry_count": 2,
            "entry_ids": ["scene10_cut01", "scene10"],
            "shards": [
                {
                    "shard_id": "scene_10",
                    "scene_id": "10",
                    "entry_count": 2,
                    "entry_ids": ["scene10_cut01", "scene10"],
                }
            ],
        }
        sections = {"scene10_cut01": "...", "scene10": "..."}

        self.assertEqual(image_gen_app._validate_image_prompt_shard_scope(valid, sections), [])
        self.assertIn("zero entries", " ".join(image_gen_app._validate_image_prompt_shard_scope({"entry_count": 0, "entry_ids": [], "shards": []}, {})))
        duplicate = {**valid, "entry_ids": ["scene10_cut01", "scene10_cut01"]}
        self.assertIn("duplicate", " ".join(image_gen_app._validate_image_prompt_shard_scope(duplicate, sections)))
        missing = {**valid, "shards": [{**valid["shards"][0], "entry_ids": ["scene10_cut01"]}]}
        self.assertIn("missing", " ".join(image_gen_app._validate_image_prompt_shard_scope(missing, sections)))
        self.assertIn("collection section", " ".join(image_gen_app._validate_image_prompt_shard_scope(valid, {"scene10_cut01": "..."})))

    def test_runtime_zero_entry_scope_fails_without_starting_app_server_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output/sample_run"
            run_dir.mkdir(parents=True)
            paths = image_gen_app.semantic_review_relpaths("image_prompt")

            def fake_build_pack(cmd, **_kwargs):
                (run_dir / paths["collection"]).parent.mkdir(parents=True, exist_ok=True)
                (run_dir / paths["collection"]).write_text("# empty image_prompt collection\n", encoding="utf-8")
                (run_dir / paths["scope"]).write_text(
                    json.dumps(
                        {
                            "stage": "image_prompt",
                            "entry_count": 0,
                            "entry_ids": [],
                            "review_scope": "per_scene_shards",
                            "shards": [],
                            "coverage": {"status": "invalid", "errors": ["zero entries"]},
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (run_dir / paths["prompt"]).write_text("# pending\n", encoding="utf-8")
                (run_dir / paths["report"]).write_text("status: pending\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    side_effect=AssertionError("zero-entry scope must not start app-server"),
                ),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage="image_prompt",
                        attempt=1,
                        max_attempts=1,
                        final_attempt=True,
                    )
                )

            report = (run_dir / paths["report"]).read_text(encoding="utf-8")
            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertFalse(result.passed)
        self.assertIn("image_prompt scope has zero entries", report)
        self.assertEqual(state["review.semantic.image_prompt.shards.coverage.status"], "invalid")


if __name__ == "__main__":
    unittest.main()
