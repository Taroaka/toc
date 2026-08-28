from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server import image_gen_app
from server.codex_app_server import CodexAppServerTransportError


def _write_fake_scene_set_pack(run_dir: Path, cmd: list[str]) -> subprocess.CompletedProcess[str]:
    stage = "scene_set"
    paths = image_gen_app.semantic_review_relpaths(stage)
    review_dir = (run_dir / paths["collection"]).parent
    review_dir.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "id": f"scene:{scene_id}",
            "selector": f"scene{scene_id}",
            "time_of_day": time_of_day,
            "location_mode": "sequence",
            "location_sequence": [
                f"route-{scene_id}-entrance",
                f"route-{scene_id}-turn",
            ],
            "location_segments": [
                {
                    "location": f"route-{scene_id}-entrance",
                    "responsibility": f"route-duty-{scene_id}",
                    "primary_subject": f"hero-{scene_id}",
                    "required_roles": [
                        "protagonist",
                        f"witness-{scene_id}",
                    ],
                }
            ],
            "participants": [
                {
                    "character_id": f"hero-{scene_id}",
                    "scene_role": "protagonist",
                    "private_state": f"PRIVATE-PARTICIPANT-{scene_id}",
                },
                {
                    "character_id": f"witness-{scene_id}",
                    "scene_role": "witness",
                },
            ],
            "role_coverage": {
                "required_roles": [
                    "protagonist",
                    f"witness-{scene_id}",
                ],
                "must_not_collapse_to_protagonist_only": True,
                "private_role_note": f"PRIVATE-ROLE-{scene_id}",
            },
            "normalized_semantic_contract": {
                "dramatic_question": f"question-{scene_id}",
                "value_shift": f"value-{scene_id}",
                "causal_turn": f"turn-{scene_id}",
            },
            "scene_event": {
                "event_sequence": [
                    {
                        "beat_id": f"event-{scene_id}",
                        "source_story_beat_ids": [f"source-{scene_id}"],
                        "story_information_revealed_ids": [f"reveal-{scene_id}"],
                        "full_only_marker": f"FULL-SCENE-{scene_id}",
                    }
                ]
            },
            "handoff_to_next_scene": f"handoff-{scene_id}",
        }
        for scene_id, time_of_day in ((10, "朝"), (20, "昼"), (30, "夜"))
    ]
    collection_lines = ["# Semantic Review Collection: scene_set", ""]
    for entry in entries:
        collection_lines.extend(
            [
                f"## {entry['id']}",
                "",
                "```json",
                json.dumps(entry, ensure_ascii=False),
                "```",
                "",
            ]
        )
    (run_dir / paths["collection"]).write_text(
        "\n".join(collection_lines),
        encoding="utf-8",
    )
    (run_dir / paths["scope"]).write_text(
        json.dumps(
            {
                "entry_count": len(entries),
                "entry_ids": [entry["id"] for entry in entries],
                "source_artifacts": ["script.md"],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / paths["prompt"]).write_text("# review prompt\n", encoding="utf-8")
    (run_dir / paths["report"]).write_text("status: pending\n", encoding="utf-8")
    return subprocess.CompletedProcess(cmd, 0, "", "")


def _write_scene_set_pack_with_collection_gap(
    run_dir: Path,
    cmd: list[str],
) -> subprocess.CompletedProcess[str]:
    result = _write_fake_scene_set_pack(run_dir, cmd)
    paths = image_gen_app.semantic_review_relpaths("scene_set")
    collection_path = run_dir / paths["collection"]
    collection = collection_path.read_text(encoding="utf-8")
    start = collection.index("## scene:20")
    end = collection.index("## scene:30")
    collection_path.write_text(
        collection[:start] + collection[end:],
        encoding="utf-8",
    )
    return result


def _write_scene_set_pack_without_collection(
    run_dir: Path,
    cmd: list[str],
) -> subprocess.CompletedProcess[str]:
    result = _write_fake_scene_set_pack(run_dir, cmd)
    paths = image_gen_app.semantic_review_relpaths("scene_set")
    (run_dir / paths["collection"]).unlink()
    return result


def _entry_id_from_shard_prompt(text: str) -> str:
    return text.split("Review only shard entry `", 1)[1].split("`", 1)[0]


def _passed_transcript(text: str, entry_id: str) -> list[dict[str, object]]:
    report_path = Path(
        text.split("The pending report path is `", 1)[1].split("`", 1)[0]
    )
    scope_path = report_path.with_name(
        report_path.name.removesuffix(".report.md") + ".scope.json"
    )
    digest = json.loads(scope_path.read_text(encoding="utf-8"))[
        "semantic_review_input_digest"
    ]
    return [
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "agentMessage",
                    "phase": "final_answer",
                    "text": "\n".join(
                        [
                            "status: passed",
                            f"semantic_review_input_digest: {digest}",
                            f"reviewed_entries: [{entry_id}]",
                            "blocked_entries: []",
                            "findings: []",
                            "failed_selectors: []",
                            "reason_keys: []",
                        ]
                    ),
                }
            },
        }
    ]


class TestSceneSetSemanticSharding(unittest.TestCase):
    def test_collection_preflight_rejects_duplicate_unexpected_malformed_and_mismatched_entries(
        self,
    ) -> None:
        cases = {
            "duplicate": (
                "# collection\n\n"
                "## scene:10\n```json\n{\"id\": \"scene:10\"}\n```\n\n"
                "## scene:10\n```json\n{\"id\": \"scene:10\"}\n```\n",
                ["scene:10"],
                "duplicate entry heading: scene:10",
            ),
            "unexpected": (
                "# collection\n\n"
                "## scene:10\n```json\n{\"id\": \"scene:10\"}\n```\n\n"
                "## scene:20\n```json\n{\"id\": \"scene:20\"}\n```\n",
                ["scene:10"],
                "unexpected entry: scene:20",
            ),
            "malformed": (
                "# collection\n\n"
                "## scene:10\n```json\n{not-json}\n```\n",
                ["scene:10"],
                "invalid JSON payload: scene:10",
            ),
            "mismatched_id": (
                "# collection\n\n"
                "## scene:10\n```json\n{\"id\": \"scene:99\"}\n```\n",
                ["scene:10"],
                "payload id does not match its heading",
            ),
            "multiple_json_fences": (
                "# collection\n\n"
                "## scene:10\n```json\n{\"id\": \"scene:10\"}\n```\n"
                "```json\n{not-json}\n```\n",
                ["scene:10"],
                "exactly one JSON fence",
            ),
            "trailing_text": (
                "# collection\n\n"
                "## scene:10\n```json\n{\"id\": \"scene:10\"}\n```\n"
                "untrusted trailing material\n",
                ["scene:10"],
                "non-whitespace outside its JSON fence",
            ),
            "duplicate_json_key": (
                "# collection\n\n"
                "## scene:10\n```json\n"
                "{\"id\": \"scene:10\", \"id\": \"scene:99\"}\n```\n",
                ["scene:10"],
                "duplicate JSON key",
            ),
            "non_finite_json_number": (
                "# collection\n\n"
                "## scene:10\n```json\n"
                "{\"id\": \"scene:10\", \"duration\": NaN}\n```\n",
                ["scene:10"],
                "non-finite JSON value",
            ),
            "reordered": (
                "# collection\n\n"
                "## scene:20\n```json\n{\"id\": \"scene:20\"}\n```\n\n"
                "## scene:10\n```json\n{\"id\": \"scene:10\"}\n```\n",
                ["scene:10", "scene:20"],
                "entry order does not match scope",
            ),
        }
        for label, (collection, expected_ids, expected_issue) in cases.items():
            with self.subTest(label=label):
                _sections, issues = (
                    image_gen_app._semantic_collection_sections_for_scope(
                        collection,
                        expected_entry_ids=expected_ids,
                    )
                )
                self.assertTrue(
                    any(expected_issue in issue for issue in issues),
                    issues,
                )

    def test_scene_set_fails_closed_before_provider_when_collection_entry_is_missing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_scene_set_gap_") as td:
            root = Path(td)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            turns = 0

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, **_kwargs):
                    nonlocal turns
                    turns += 1
                    return []

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.subprocess.run",
                    lambda cmd, **_kwargs: _write_scene_set_pack_with_collection_gap(
                        run_dir,
                        cmd,
                    ),
                ),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage="scene_set",
                        attempt=1,
                        max_attempts=1,
                        final_attempt=True,
                    )
                )

            report = (
                run_dir / image_gen_app.semantic_review_relpaths("scene_set")["report"]
            ).read_text(encoding="utf-8")

        self.assertFalse(result.passed)
        self.assertEqual(turns, 0)
        self.assertIn("semantic_review_selector_coverage_invalid", report)

    def test_scene_set_fails_closed_when_collection_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_scene_set_missing_collection_") as td:
            root = Path(td)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            turns = 0

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, **_kwargs):
                    nonlocal turns
                    turns += 1
                    return []

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.subprocess.run",
                    lambda cmd, **_kwargs: _write_scene_set_pack_without_collection(
                        run_dir,
                        cmd,
                    ),
                ),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage="scene_set",
                        attempt=1,
                        max_attempts=1,
                        final_attempt=True,
                    )
                )

            paths = image_gen_app.semantic_review_relpaths("scene_set")
            report = (run_dir / paths["report"]).read_text(encoding="utf-8")
            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertFalse(result.passed)
        self.assertEqual(turns, 0)
        self.assertIn("semantic_review_selector_coverage_invalid", report)
        self.assertIn("cannot read canonical scene_set collection", report)
        self.assertEqual(
            state["review.semantic.scene_set.shards.coverage.status"],
            "invalid",
        )

    def test_scene_set_runs_bounded_per_scene_shards_with_compact_global_context(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_scene_set_shards_") as td:
            root = Path(td)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            active = 0
            max_active = 0
            reviewed: list[str] = []
            prompts: list[str] = []

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    nonlocal active, max_active
                    entry_id = _entry_id_from_shard_prompt(text)
                    reviewed.append(entry_id)
                    prompts.append(text)
                    active += 1
                    max_active = max(max_active, active)
                    try:
                        await asyncio.sleep(0.02)
                        return _passed_transcript(text, entry_id)
                    finally:
                        active -= 1

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.subprocess.run",
                    lambda cmd, **_kwargs: _write_fake_scene_set_pack(run_dir, cmd),
                ),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
                patch.dict(os.environ, {"TOC_SCENE_SET_REVIEW_CONCURRENCY": "2"}),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage="scene_set",
                        attempt=1,
                        max_attempts=1,
                        final_attempt=True,
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")
            shard_collections = sorted(
                (run_dir / "logs/review/semantic/scene_set_shards/attempt_01").glob(
                    "*.collection.md"
                )
            )
            shard_collection_texts = [
                path.read_text(encoding="utf-8") for path in shard_collections
            ]

        self.assertTrue(result.passed, result.errors)
        self.assertEqual(sorted(reviewed), ["scene:10", "scene:20", "scene:30"])
        self.assertEqual(max_active, 2)
        self.assertEqual(state["review.semantic.scene_set.shards.concurrency"], "2")
        self.assertEqual(state["review.semantic.scene_set.shards.status"], "passed")
        self.assertTrue(
            all(
                "never scan an entire story, script, or manifest by default"
                in prompt
                for prompt in prompts
            )
        )
        self.assertEqual(len(shard_collections), 3)
        for text in shard_collection_texts:
            self.assertIn("Compact ordered scene context", text)
            self.assertIn('"id": "scene:10"', text)
            self.assertIn('"id": "scene:20"', text)
            self.assertIn('"id": "scene:30"', text)
            self.assertIn('"location_sequence"', text)
            self.assertIn('"route-10-entrance"', text)
            self.assertIn('"route-20-entrance"', text)
            self.assertIn('"route-30-entrance"', text)
            self.assertIn('"participants"', text)
            self.assertIn('"witness-10"', text)
            self.assertIn('"witness-20"', text)
            self.assertIn('"witness-30"', text)
            self.assertIn('"role_coverage"', text)
            self.assertEqual(text.count("PRIVATE-PARTICIPANT-"), 1)
            self.assertEqual(text.count("PRIVATE-ROLE-"), 1)
            self.assertEqual(text.count("FULL-SCENE-"), 1)

    def test_scene_set_transport_retry_reruns_only_failed_shard(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_scene_set_retry_") as td:
            root = Path(td)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            turns: dict[str, int] = {}

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    entry_id = _entry_id_from_shard_prompt(text)
                    turns[entry_id] = turns.get(entry_id, 0) + 1
                    if entry_id == "scene:20" and turns[entry_id] == 1:
                        raise CodexAppServerTransportError("turn timed out")
                    return _passed_transcript(text, entry_id)

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.subprocess.run",
                    lambda cmd, **_kwargs: _write_fake_scene_set_pack(run_dir, cmd),
                ),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
                patch.dict(
                    os.environ,
                    {
                        "TOC_SCENE_SET_REVIEW_CONCURRENCY": "3",
                        "TOC_SCENE_SET_TRANSPORT_RETRY_ATTEMPTS": "2",
                    },
                ),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage="scene_set",
                        attempt=1,
                        max_attempts=1,
                        final_attempt=True,
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertTrue(result.passed, result.errors)
        self.assertEqual(turns, {"scene:10": 1, "scene:20": 2, "scene:30": 1})
        self.assertEqual(
            state["review.semantic.scene_set.shards.scene_20.transport.status"],
            "recovered",
        )

    def test_scene_set_output_contract_retry_reruns_only_failed_shard(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_scene_set_contract_retry_") as td:
            root = Path(td)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            turns: dict[str, int] = {}

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    entry_id = _entry_id_from_shard_prompt(text)
                    turns[entry_id] = turns.get(entry_id, 0) + 1
                    if entry_id == "scene:20" and turns[entry_id] == 1:
                        return [
                            {
                                "method": "item/completed",
                                "params": {
                                    "item": {
                                        "type": "agentMessage",
                                        "phase": "final_answer",
                                        "text": "review finished without the required verdict",
                                    }
                                },
                            }
                        ]
                    return _passed_transcript(text, entry_id)

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.subprocess.run",
                    lambda cmd, **_kwargs: _write_fake_scene_set_pack(run_dir, cmd),
                ),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
                patch.dict(
                    os.environ,
                    {
                        "TOC_SCENE_SET_REVIEW_CONCURRENCY": "3",
                        "TOC_SCENE_SET_TRANSPORT_RETRY_ATTEMPTS": "3",
                    },
                ),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage="scene_set",
                        attempt=1,
                        max_attempts=1,
                        final_attempt=True,
                    )
                )

            state = image_gen_app.parse_state_file(run_dir / "state.txt")

        self.assertTrue(result.passed, result.errors)
        self.assertEqual(turns, {"scene:10": 1, "scene:20": 2, "scene:30": 1})
        self.assertEqual(
            state["review.semantic.scene_set.shards.scene_20.transport.status"],
            "recovered",
        )

    def test_scene_set_rejects_canonical_collection_change_during_provider_review(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_scene_set_generation_race_") as td:
            root = Path(td)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")
            mutated = False

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    nonlocal mutated
                    entry_id = _entry_id_from_shard_prompt(text)
                    if not mutated:
                        mutated = True
                        paths = image_gen_app.semantic_review_relpaths("scene_set")
                        collection_path = run_dir / paths["collection"]
                        collection_path.write_text(
                            collection_path.read_text(encoding="utf-8") + "\n",
                            encoding="utf-8",
                        )
                    return _passed_transcript(text, entry_id)

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.subprocess.run",
                    lambda cmd, **_kwargs: _write_fake_scene_set_pack(run_dir, cmd),
                ),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
                patch.dict(
                    os.environ,
                    {"TOC_SCENE_SET_REVIEW_CONCURRENCY": "1"},
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "generation is invalid|generation changed",
                ):
                    asyncio.run(
                        image_gen_app._run_semantic_review_once(
                            "job-1",
                            run_dir=run_dir,
                            stage="scene_set",
                            attempt=1,
                            max_attempts=1,
                            final_attempt=True,
                        )
                    )

        self.assertTrue(mutated)

    def test_scene_set_currentness_rejects_shards_from_prior_generation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_scene_set_stale_generation_") as td:
            root = Path(td)
            run_dir = root / "output" / "sample_run"
            run_dir.mkdir(parents=True)
            (run_dir / "script.md").write_text("# script\n", encoding="utf-8")

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, text: str, **_kwargs):
                    return _passed_transcript(
                        text,
                        _entry_id_from_shard_prompt(text),
                    )

                async def stop(self):
                    return None

            with (
                patch("server.image_gen_app.ROOT", root),
                patch(
                    "server.image_gen_app.subprocess.run",
                    lambda cmd, **_kwargs: _write_fake_scene_set_pack(run_dir, cmd),
                ),
                patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ),
            ):
                result = asyncio.run(
                    image_gen_app._run_semantic_review_once(
                        "job-1",
                        run_dir=run_dir,
                        stage="scene_set",
                        attempt=1,
                        max_attempts=1,
                        final_attempt=True,
                    )
                )
                self.assertTrue(result.passed, result.errors)

                paths = image_gen_app.semantic_review_relpaths("scene_set")
                collection_path = run_dir / paths["collection"]
                scope_path = run_dir / paths["scope"]
                report_path = run_dir / paths["report"]
                collection_path.write_text(
                    collection_path.read_text(encoding="utf-8") + "\n",
                    encoding="utf-8",
                )
                scope = json.loads(scope_path.read_text(encoding="utf-8"))
                scope["review_generation_id"] = "f" * 32
                scope["review_generation_collection_sha256"] = (
                    image_gen_app.semantic_review_file_sha256(collection_path)
                )
                scope_path.write_text(
                    json.dumps(scope, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                image_gen_app._refresh_semantic_review_input_digest(
                    run_dir=run_dir,
                    scope_path=scope_path,
                    collection_path=collection_path,
                    prompt_path=run_dir / paths["prompt"],
                    report_path=report_path,
                )
                stale_result = image_gen_app.check_semantic_review(
                    run_dir,
                    "scene_set",
                )

        self.assertFalse(stale_result.passed)
        self.assertTrue(
            any(
                "canonical_review_generation_id does not match canonical scope"
                in issue
                for issue in stale_result.errors
            ),
            stale_result.errors,
        )


if __name__ == "__main__":
    unittest.main()
