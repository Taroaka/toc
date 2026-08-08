from __future__ import annotations

import asyncio
import hashlib
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
from toc.review_projection import (  # noqa: E402
    VIDEO_MANIFEST_REVIEW_PROJECTION_SCHEMA,
    review_source_fingerprint,
    video_manifest_review_projection_sha256,
)


def _load_pack_builder():
    spec = importlib.util.spec_from_file_location("build_semantic_review_pack", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _semantic_input_digest_for_report(report_path: Path) -> str:
    suffix = ".report.md"
    if not report_path.name.endswith(suffix):
        raise AssertionError(f"unexpected semantic report path: {report_path}")
    scope_path = report_path.with_name(report_path.name[: -len(suffix)] + ".scope.json")
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    digest = str(scope.get("semantic_review_input_digest") or "")
    if not digest.startswith("sha256:"):
        raise AssertionError(f"semantic scope has no input digest: {scope_path}")
    return digest


def _pending_report_path_from_prompt(text: str) -> Path:
    marker = "The pending report path is `"
    return Path(text.split(marker, 1)[1].split("`", 1)[0])


def _agent_message_transcript(report_text: str) -> list[dict[str, object]]:
    return [
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "agentMessage",
                    "phase": "final_answer",
                    "text": report_text,
                }
            },
        }
    ]


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
            first_collection_path = run_dir / first["artifacts"]["collection"]
            first_prompt_path = run_dir / first["artifacts"]["prompt"]
            first_report_path = run_dir / first["artifacts"]["report"]
            first_scope = json.loads((run_dir / first["artifacts"]["scope"]).read_text(encoding="utf-8"))
            first_report = first_report_path.read_text(encoding="utf-8")
            first_collection_sha256 = hashlib.sha256(first_collection_path.read_bytes()).hexdigest()
            first_prompt_sha256 = hashlib.sha256(first_prompt_path.read_bytes()).hexdigest()

        self.assertIn("scene10_cut01", first_collection)
        self.assertIn("## scene10", first_collection)
        self.assertNotIn("scene20_cut01", first_collection)
        self.assertIn("scene20_cut01", second_collection)
        self.assertNotIn("scene10_cut01", second_collection)
        self.assertEqual(first_scope["entry_ids"], ["scene10_cut01", "scene10"])
        self.assertEqual(first_scope["review_scope"], "single_scene_image_prompt_shard")
        self.assertEqual(first_scope["canonical_scope"], "logs/review/semantic/image_prompt.scope.json")
        self.assertEqual(first_scope["semantic_review_input_schema"], "semantic_review_input_v1")
        self.assertEqual(first_scope["source_artifact_digests"], [])
        self.assertEqual(
            first_scope["collection_sha256"],
            first_collection_sha256,
        )
        self.assertEqual(
            first_scope["prompt_sha256"],
            first_prompt_sha256,
        )
        self.assertRegex(first_scope["semantic_review_input_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertIn(
            f"semantic_review_input_digest: `{first_scope['semantic_review_input_digest']}`",
            first_report,
        )

    def test_materialization_reuses_source_fingerprints_across_scene_shards(
        self,
    ) -> None:
        builder = _load_pack_builder()
        entries = [
            {"selector": "scene10_cut01", "scene_id": 10},
            {"selector": "scene20_cut01", "scene_id": 20},
        ]

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "story.md").write_text("# story\n", encoding="utf-8")
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            (run_dir / "video_manifest.md").write_text(
                "```yaml\nvideo_metadata: {topic: shard-cache}\nscenes: []\n```\n",
                encoding="utf-8",
            )
            fingerprint_cache: dict[tuple[object, ...], object] = {}
            with patch.object(
                builder,
                "review_source_fingerprint",
                wraps=review_source_fingerprint,
            ) as fingerprint:
                builder.materialize_image_prompt_scene_shards(
                    run_dir=run_dir,
                    entries=entries,
                    canonical_scope_path=(
                        run_dir
                        / "logs/review/semantic/image_prompt.scope.json"
                    ),
                    canonical_report_path=(
                        run_dir
                        / "logs/review/semantic/image_prompt.report.md"
                    ),
                    source_fingerprint_cache=fingerprint_cache,
                )

            self.assertEqual(fingerprint.call_count, 3)


class ImagePromptSemanticServerShardTests(unittest.TestCase):
    @staticmethod
    def _write_pack(run_dir: Path, entries: list[dict[str, object]]) -> None:
        # The semantic shard reviewer is downstream of the deterministic
        # story/prompt gate.  Keep this fixture provider-ready instead of
        # accidentally testing the missing-gate failure path.
        for source_name in ("story.md", "script.md"):
            (run_dir / source_name).write_text(f"# {source_name}\n", encoding="utf-8")
        (run_dir / "video_manifest.md").write_text(
            "```yaml\n"
            "video_metadata:\n"
            "  topic: shard-test\n"
            "scenes: []\n"
            "```\n",
            encoding="utf-8",
        )
        deterministic_selectors = [
            str(entry["selector"])
            for entry in entries
            if "_cut" in str(entry.get("selector") or "")
        ]
        deterministic_sections = [
            line
            for selector in deterministic_selectors
            for line in (
                f"## {selector}",
                "",
                f"- output: `assets/scenes/{selector}.png`",
                "- narration: `(silent)`",
                "- overall_score: `1.000`",
                "- rubric_scores: `{}`",
                "- review: `PASS`",
                "",
            )
        ]
        (run_dir / "image_prompt_story_review.md").write_text(
            "\n".join(
                [
                    "# Image Prompt Story Review",
                    "",
                    "- review_format_version: `deterministic_image_prompt_review_v3`",
                    f"- manifest: `{run_dir / 'video_manifest.md'}`",
                    "- manifest_fingerprint_policy: "
                    f"`{VIDEO_MANIFEST_REVIEW_PROJECTION_SCHEMA}`",
                    f"- manifest_sha256: `{video_manifest_review_projection_sha256(run_dir / 'video_manifest.md')}`",
                    f"- story_sha256: `{image_gen_app._file_sha256(run_dir / 'story.md')}`",
                    f"- script_sha256: `{image_gen_app._file_sha256(run_dir / 'script.md')}`",
                    "- status: `PASS`",
                    f"- reviewed_entries: `{len(deterministic_selectors)}`",
                    "- empty_review_scope: `false`",
                    "- entries_with_findings: `0`",
                    "- findings: `0`",
                    "- hard_findings: `0`",
                    "- blocking_hard_findings: `0`",
                    "- soft_findings: `0`",
                    "- unresolved_entries: `0`",
                    "",
                    *deterministic_sections,
                ]
            ),
            encoding="utf-8",
        )
        # Use the production pack builder so the canonical scope and every
        # scene shard carry real artifact paths, source hashes, prompt hashes,
        # and a SHA-bound semantic_review_input_digest.
        builder = _load_pack_builder()
        with patch.object(builder, "collect_entries", return_value=entries):
            builder.build_pack(run_dir, "image_prompt")

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
                        report_path = _pending_report_path_from_prompt(text)
                        expected = json.loads(text.split("Expected reviewed_entries exactly once: ", 1)[1].splitlines()[0])
                        input_digest = _semantic_input_digest_for_report(report_path)
                        return _agent_message_transcript(
                            "\n".join(
                                [
                                    "status: passed",
                                    f"semantic_review_input_digest: {input_digest}",
                                    "reviewed_entries: [" + ", ".join(expected) + "]",
                                    "blocked_entries: []",
                                    "findings: []",
                                    "failed_selectors: []",
                                    "reason_keys: []",
                                ]
                            )
                        )
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

    def test_semantic_failure_preserves_only_reported_blocked_cut_set(
        self,
    ) -> None:
        entries = [
            {
                "selector": "scene10_cut01",
                "scene_id": 10,
                "review_scope": "all_entries",
            },
            {
                "selector": "scene10_cut02",
                "scene_id": 10,
                "review_scope": "all_entries",
            },
            {
                "selector": "scene10",
                "scene_id": 10,
                "review_scope": "scene_composite",
            },
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
                    report_path = _pending_report_path_from_prompt(text)
                    expected = json.loads(
                        text.split(
                            "Expected reviewed_entries exactly once: ",
                            1,
                        )[1].splitlines()[0]
                    )
                    return _agent_message_transcript(
                        "\n".join(
                            [
                                "status: failed",
                                "semantic_review_input_digest: "
                                + _semantic_input_digest_for_report(
                                    report_path
                                ),
                                "reviewed_entries: ["
                                + ", ".join(expected)
                                + "]",
                                "blocked_entries: [scene10_cut02]",
                                "findings: [scene10_cut02 reverses the intended action]",
                                "failed_selectors: [scene10_cut02]",
                                "reason_keys: [semantic_action_direction_mismatch]",
                            ]
                        )
                    )

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.subprocess.run",
                    fake_build_pack,
                ),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    lambda **_kwargs: FakeClient(),
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

            report = (
                run_dir
                / image_gen_app.semantic_review_relpaths("image_prompt")[
                    "report"
                ]
            ).read_text(encoding="utf-8")

        self.assertFalse(result.passed)
        self.assertIn("blocked_entries:\n  - scene10_cut02\n", report)
        self.assertNotIn("blocked_entries:\n  - scene10_cut01", report)
        self.assertNotIn(
            "blocked_entries:\n  - scene10_cut02\n  - scene10",
            report,
        )

    def test_contentless_failed_shard_is_output_contract_failure(self) -> None:
        entries = [
            {
                "selector": "scene10_cut01",
                "scene_id": 10,
                "review_scope": "all_entries",
            },
            {
                "selector": "scene10",
                "scene_id": 10,
                "review_scope": "scene_composite",
            },
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
                    report_path = _pending_report_path_from_prompt(text)
                    expected = json.loads(
                        text.split(
                            "Expected reviewed_entries exactly once: ",
                            1,
                        )[1].splitlines()[0]
                    )
                    return _agent_message_transcript(
                        "\n".join(
                            [
                                "status: failed",
                                "semantic_review_input_digest: "
                                + _semantic_input_digest_for_report(
                                    report_path
                                ),
                                "reviewed_entries: ["
                                + ", ".join(expected)
                                + "]",
                                "blocked_entries: []",
                                "findings: []",
                                "failed_selectors: []",
                                "reason_keys: []",
                            ]
                        )
                    )

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.subprocess.run",
                    fake_build_pack,
                ),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    lambda **_kwargs: FakeClient(),
                ),
                patch.dict(
                    os.environ,
                    {"TOC_IMAGE_PROMPT_TRANSPORT_RETRY_ATTEMPTS": "1"},
                ),
            ):
                with self.assertRaisesRegex(
                    CodexAppServerTransportError,
                    "image_prompt scene shard transport failed",
                ):
                    asyncio.run(
                        image_gen_app._run_semantic_review_once(
                            "job-1",
                            run_dir=run_dir,
                            stage="image_prompt",
                            attempt=1,
                            max_attempts=1,
                            final_attempt=True,
                        )
                    )

            state = image_gen_app.parse_state_file(
                run_dir / "state.txt"
            )

        self.assertEqual(
            state[
                "review.semantic.image_prompt.shards.scene_10.transport.error_kind"
            ],
            "output_contract_failed",
        )

    def test_selector_coverage_error_retries_only_its_scene_as_output_contract_failure(
        self,
    ) -> None:
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
                    shard_id = text.split(
                        "Review only image_prompt scene shard `",
                        1,
                    )[1].split("`", 1)[0]
                    turn_counts[shard_id] = turn_counts.get(shard_id, 0) + 1
                    report_path = _pending_report_path_from_prompt(text)
                    expected = json.loads(text.split("Expected reviewed_entries exactly once: ", 1)[1].splitlines()[0])
                    reviewed = expected if expected[0].startswith("scene10") else [expected[0], expected[0]]
                    input_digest = _semantic_input_digest_for_report(report_path)
                    return _agent_message_transcript(
                        "\n".join(
                            [
                                "status: passed",
                                f"semantic_review_input_digest: {input_digest}",
                                "reviewed_entries: [" + ", ".join(reviewed) + "]",
                                "blocked_entries: []",
                                "findings: []",
                                "failed_selectors: []",
                                "reason_keys: []",
                            ]
                        )
                    )

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch("server.image_gen_app.create_codex_app_server_client", lambda **_kwargs: FakeClient()),
                patch.dict(
                    os.environ,
                    {"TOC_IMAGE_PROMPT_TRANSPORT_RETRY_ATTEMPTS": "2"},
                ),
            ):
                with self.assertRaisesRegex(
                    CodexAppServerTransportError,
                    "image_prompt scene shard transport failed",
                ):
                    asyncio.run(
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

        self.assertEqual(turn_counts, {"scene_10": 1, "scene_20": 2})
        self.assertEqual(state["review.semantic.image_prompt.shards.failed_count"], "1")
        self.assertEqual(state["review.semantic.image_prompt.shards.scene_10.status"], "passed")
        self.assertEqual(
            state["review.semantic.image_prompt.shards.scene_20.status"],
            "transport_failed",
        )
        self.assertEqual(
            state[
                "review.semantic.image_prompt.shards.scene_20.transport.error_kind"
            ],
            "output_contract_failed",
        )
        self.assertEqual(
            state[
                "review.semantic.image_prompt.shards.scene_20.transport.retry_count"
            ],
            "1",
        )
        self.assertIn("image_prompt_shard_transport_failed", report)
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
                    report_path = _pending_report_path_from_prompt(text)
                    expected = json.loads(text.split("Expected reviewed_entries exactly once: ", 1)[1].splitlines()[0])
                    input_digest = _semantic_input_digest_for_report(report_path)
                    return _agent_message_transcript(
                        "status: passed\n"
                        + f"semantic_review_input_digest: {input_digest}\n"
                        + "reviewed_entries: ["
                        + ", ".join(expected)
                        + "]\nblocked_entries: []\nfindings: []\nfailed_selectors: []\nreason_keys: []\n"
                    )

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

    def test_missing_final_verdict_retries_as_image_prompt_output_contract_failure(self) -> None:
        entries = [
            {
                "selector": "scene10_cut01",
                "scene_id": 10,
                "review_scope": "all_entries",
            },
            {
                "selector": "scene10",
                "scene_id": 10,
                "review_scope": "scene_composite",
            },
        ]
        turn_count = 0

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

                async def run_turn(self, **_kwargs):
                    nonlocal turn_count
                    turn_count += 1
                    return _agent_message_transcript(
                        "Review completed without the required verdict."
                    )

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    lambda **_kwargs: FakeClient(),
                ),
                patch.dict(
                    os.environ,
                    {"TOC_IMAGE_PROMPT_TRANSPORT_RETRY_ATTEMPTS": "2"},
                ),
            ):
                with self.assertRaisesRegex(
                    CodexAppServerTransportError,
                    "image_prompt scene shard transport failed",
                ):
                    asyncio.run(
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

        self.assertEqual(turn_count, 2)
        self.assertEqual(
            state[
                "review.semantic.image_prompt.shards.scene_10.transport.error_kind"
            ],
            "output_contract_failed",
        )
        self.assertEqual(
            state[
                "review.semantic.image_prompt.shards.scene_10.transport.retry_count"
            ],
            "1",
        )

    def test_valid_commentary_with_malformed_final_answer_is_shard_output_contract_failure(
        self,
    ) -> None:
        entries = [
            {
                "selector": "scene10_cut01",
                "scene_id": 10,
                "review_scope": "all_entries",
            },
            {
                "selector": "scene10",
                "scene_id": 10,
                "review_scope": "scene_composite",
            },
        ]
        turn_count = 0

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
                    nonlocal turn_count
                    turn_count += 1
                    report_path = _pending_report_path_from_prompt(text)
                    expected = json.loads(
                        text.split(
                            "Expected reviewed_entries exactly once: ",
                            1,
                        )[1].splitlines()[0]
                    )
                    verdict = {
                        "status": "passed",
                        "semantic_review_input_digest": (
                            _semantic_input_digest_for_report(report_path)
                        ),
                        "reviewed_entries": expected,
                        "blocked_entries": [],
                        "findings": [],
                        "failed_selectors": [],
                        "reason_keys": [],
                        "notes": [],
                    }
                    return [
                        {
                            "method": "item/completed",
                            "params": {
                                "item": {
                                    "type": "agentMessage",
                                    "phase": "commentary",
                                    "text": json.dumps(
                                        verdict,
                                        ensure_ascii=False,
                                    ),
                                }
                            },
                        },
                        {
                            "method": "item/completed",
                            "params": {
                                "item": {
                                    "type": "agentMessage",
                                    "phase": "final_answer",
                                    "text": '{"status": "passed"',
                                }
                            },
                        },
                    ]

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch("server.image_gen_app.subprocess.run", fake_build_pack),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    lambda **_kwargs: FakeClient(),
                ),
                patch.dict(
                    os.environ,
                    {"TOC_IMAGE_PROMPT_TRANSPORT_RETRY_ATTEMPTS": "2"},
                ),
            ):
                with self.assertRaisesRegex(
                    CodexAppServerTransportError,
                    "image_prompt scene shard transport failed",
                ):
                    asyncio.run(
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

        self.assertEqual(turn_count, 2)
        self.assertEqual(
            state[
                "review.semantic.image_prompt.shards.scene_10.transport.error_kind"
            ],
            "output_contract_failed",
        )
        self.assertEqual(
            state[
                "review.semantic.image_prompt.shards.scene_10.transport.retry_count"
            ],
            "1",
        )

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
