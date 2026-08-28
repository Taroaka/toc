from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from server import image_gen_app
from server.codex_app_server import CodexAppServerTransportError
from toc.run_root_binding import RunRootBindingError, bind_run_root
from toc.semantic_review import (
    SEMANTIC_REVIEW_INPUT_SCHEMA,
    semantic_review_input_digest,
    semantic_review_scope_binding_sha256,
)


def _agent_transcript(
    *,
    digest: str,
    reviewed_entries: list[str],
) -> list[dict[str, object]]:
    report = "\n".join(
        [
            "status: passed",
            f"semantic_review_input_digest: {digest}",
            "reviewed_entries: [" + ", ".join(reviewed_entries) + "]",
            "blocked_entries: []",
            "findings: []",
            "failed_selectors: []",
            "reason_keys: []",
            "notes: []",
            "",
        ]
    )
    return [
        {
            "method": "item/completed",
            "params": {
                "item": {
                    "type": "agentMessage",
                    "phase": "final_answer",
                    "text": report,
                }
            },
        }
    ]


def _workspace_scope(cwd: Path) -> tuple[Path, dict[str, object]]:
    matches = sorted(cwd.rglob("*.scope.json"))
    decoded = [
        (path, json.loads(path.read_text(encoding="utf-8")))
        for path in matches
    ]
    shard_scopes = [
        (path, scope)
        for path, scope in decoded
        if str(scope.get("review_scope") or "").startswith("single_scene")
    ]
    candidates = shard_scopes or decoded
    if len(candidates) != 1:
        raise AssertionError(f"expected one private review scope, got {matches}")
    return candidates[0]


class SemanticReviewWorkspaceSecurityTests(unittest.TestCase):
    def test_scene_scope_resolves_in_scope_nested_field_selectors(self) -> None:
        selectors = (
            "scene30.participants",
            "scene30.scene_event.event_sequence[0]",
            "scene120.role_coverage.required_roles",
            "scene140.scene_intent.character_state.start",
            "scene150.scene_intent.handoff_chain.incoming.visible_or_audible_form",
        )

        for selector in selectors:
            expected_scene = selector.split(".", 1)[0].removeprefix("scene")
            with self.subTest(selector=selector):
                self.assertEqual(
                    image_gen_app._semantic_failure_selector_scope_key(
                        selector,
                        scope_entry_ids=[f"scene:{expected_scene}"],
                    ),
                    f"scene:{expected_scene}",
                )

        self.assertIsNone(
            image_gen_app._semantic_failure_selector_scope_key(
                "scene40.participants",
                scope_entry_ids=["scene:30"],
            )
        )
        for selector in (
            "scene3.1",
            "scene3.1.participants",
            "scene:3.1.scene_event.event_sequence[0]",
        ):
            with self.subTest(selector=selector):
                self.assertEqual(
                    image_gen_app._semantic_failure_selector_scope_key(
                        selector,
                        scope_entry_ids=["scene:3.1"],
                    ),
                    "scene:3.1",
                )
        self.assertIsNone(
            image_gen_app._semantic_failure_selector_scope_key(
                "scene30..participants",
                scope_entry_ids=["scene:30"],
            )
        )
        report = "\n".join(
            [
                "status: failed",
                "reviewed_entries: [scene:30]",
                "blocked_entries: [scene:30]",
                "findings: [participants require repair]",
                "failed_selectors: [scene30.participants]",
                "reason_keys: [scene_set.role_coverage_missing]",
                "notes: []",
                "",
            ]
        )
        self.assertEqual(
            image_gen_app._semantic_negative_verdict_contract_errors(
                report,
                scope_entry_ids=["scene:30"],
            ),
            (),
        )

    def test_single_entry_scope_resolves_only_in_scope_artifact_field_selectors(
        self,
    ) -> None:
        scope_entry_ids = ["story:foundation"]
        source_artifacts = ["research.md", "story.md"]

        for selector in (
            "story.md:script.scenes[scene_id=2].story_event_obligations",
            "story.md:script.scenes[scene_id=3].location.segments",
            "story.md:script.scenes[scene_id=2, 3, 4, 5, 9, 10, 11, 12, 13, 14, 15].character_ids",
        ):
            with self.subTest(selector=selector):
                self.assertEqual(
                    image_gen_app._semantic_failure_selector_scope_key(
                        selector,
                        scope_entry_ids=scope_entry_ids,
                        source_artifacts=source_artifacts,
                    ),
                    "story:foundation",
                )

        self.assertIsNone(
            image_gen_app._semantic_failure_selector_scope_key(
                "video_manifest.md:scenes[scene_id=3].location.segments",
                scope_entry_ids=scope_entry_ids,
                source_artifacts=source_artifacts,
            )
        )
        self.assertIsNone(
            image_gen_app._semantic_failure_selector_scope_key(
                "story.md:script.scenes[scene_id=3]..location",
                scope_entry_ids=scope_entry_ids,
                source_artifacts=source_artifacts,
            )
        )
        self.assertIsNone(
            image_gen_app._semantic_failure_selector_scope_key(
                "story.md:script.scenes[scene_id=3].location.segments",
                scope_entry_ids=["scene:10", "scene:20"],
                source_artifacts=source_artifacts,
            )
        )

    def test_negative_story_verdict_accepts_in_scope_field_selectors(self) -> None:
        selectors = [
            "story.md:script.scenes[scene_id=2].story_event_obligations",
            "story.md:script.scenes[scene_id=3].location.segments",
            "story.md:script.scenes[scene_id=2, 3, 4, 5, 9, 10, 11, 12, 13, 14, 15].character_ids",
        ]
        report = "\n".join(
            [
                "status: failed",
                "reviewed_entries: [story:foundation]",
                "blocked_entries: [story:foundation]",
                "findings: [story fields require repair]",
                "failed_selectors: "
                + json.dumps(selectors, ensure_ascii=False),
                "reason_keys: [story_contract_mismatch]",
                "notes: []",
                "",
            ]
        )

        self.assertEqual(
            image_gen_app._semantic_negative_verdict_contract_errors(
                report,
                scope_entry_ids=["story:foundation"],
                source_artifacts=["research.md", "story.md"],
            ),
            (),
        )

    def test_negative_story_verdict_preserves_commas_inside_field_selector(self) -> None:
        report = "\n".join(
            [
                "status: failed",
                "reviewed_entries: [story:foundation]",
                "blocked_entries: [story:foundation]",
                "findings: [location fields require repair]",
                "failed_selectors: [story.md:script.scenes[scene_id=2, 3].location]",
                "reason_keys: [story_contract_mismatch]",
                "notes: []",
                "",
            ]
        )

        self.assertEqual(
            image_gen_app._semantic_negative_verdict_contract_errors(
                report,
                scope_entry_ids=["story:foundation"],
                source_artifacts=["story.md"],
            ),
            (),
        )

    def _write_failed_repair_pack(
        self,
        run_dir: Path,
        *,
        stage: str = "scene_set",
    ) -> None:
        source_path = run_dir / "script.md"
        source_path.write_text("# Script\n\nold scene meaning\n", encoding="utf-8")
        relpaths = image_gen_app.semantic_review_relpaths(stage)
        collection_path = run_dir / relpaths["collection"]
        scope_path = run_dir / relpaths["scope"]
        prompt_path = run_dir / relpaths["prompt"]
        report_path = run_dir / relpaths["report"]
        collection_path.parent.mkdir(parents=True, exist_ok=True)
        collection_path.write_text(
            "# collection\n\n## scene_1\nold scene meaning\n",
            encoding="utf-8",
        )
        prompt_path.write_text("# review prompt\n", encoding="utf-8")
        source_digests = [
            {
                "path": "script.md",
                "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
            }
        ]
        scope: dict[str, object] = {
            "stage": stage,
            "entry_count": 1,
            "entry_ids": ["scene_1"],
            "review_scope": "all_entries",
            "source_artifacts": ["script.md"],
            "semantic_review_input_schema": SEMANTIC_REVIEW_INPUT_SCHEMA,
            "source_artifact_digests": source_digests,
            "collection_sha256": hashlib.sha256(
                collection_path.read_bytes()
            ).hexdigest(),
            "prompt_sha256": hashlib.sha256(
                prompt_path.read_bytes()
            ).hexdigest(),
            "artifacts": {
                key: value.as_posix() for key, value in relpaths.items()
            },
        }
        scope_binding_sha256 = semantic_review_scope_binding_sha256(scope)
        digest = semantic_review_input_digest(
            stage=stage,
            entry_ids=["scene_1"],
            collection_sha256=str(scope["collection_sha256"]),
            prompt_sha256=str(scope["prompt_sha256"]),
            source_artifact_digests=source_digests,
            scope_binding_sha256=scope_binding_sha256,
        )
        scope["scope_binding_sha256"] = scope_binding_sha256
        scope["semantic_review_input_digest"] = digest
        scope_path.write_text(
            json.dumps(scope, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        report_path.write_text(
            "status: failed\n"
            f"semantic_review_input_digest: {digest}\n"
            "reviewed_entries: [scene_1]\n"
            "blocked_entries: [scene_1]\n"
            "findings: [scene meaning is wrong]\n"
            "failed_selectors: [scene_1]\n"
            "reason_keys: [semantic_timeline_mismatch]\n"
            "notes: []\n",
            encoding="utf-8",
        )

    def _write_canonical_scope(
        self,
        run_dir: Path,
        *,
        stage: str,
    ) -> tuple[Path, Path]:
        source_path = run_dir / f"{stage}.source.md"
        source_path.write_text("trusted source bytes\n", encoding="utf-8")
        base = run_dir / "logs" / "review" / "semantic"
        base.mkdir(parents=True, exist_ok=True)
        scope_path = base / f"{stage}.scope.json"
        report_path = base / f"{stage}.report.md"
        scope_path.write_text(
            json.dumps(
                {
                    "stage": stage,
                    "source_artifacts": [source_path.name],
                    "source_artifact_digests": [
                        {
                            "path": source_path.name,
                            "sha256": hashlib.sha256(
                                source_path.read_bytes()
                            ).hexdigest(),
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        report_path.write_text("status: pending\n", encoding="utf-8")
        return scope_path, report_path

    def _fake_pack_builder(
        self,
        run_dir: Path,
        stage: str,
        *,
        entry_ids: list[str] | None = None,
    ):
        ids = entry_ids or [f"{stage}_entry_1"]
        relpaths = image_gen_app.semantic_review_relpaths(stage)

        def build(command, **_kwargs):
            source = run_dir / f"{stage}.source.md"
            source.write_text("trusted source bytes\n", encoding="utf-8")
            for path in (run_dir / relpath for relpath in relpaths.values()):
                path.parent.mkdir(parents=True, exist_ok=True)
            (run_dir / relpaths["collection"]).write_text(
                "# collection\n\n"
                + "\n".join(f"## {entry_id}\ntrusted {entry_id}\n" for entry_id in ids),
                encoding="utf-8",
            )
            (run_dir / relpaths["scope"]).write_text(
                json.dumps(
                    {
                        "stage": stage,
                        "entry_count": len(ids),
                        "entry_ids": ids,
                        "selectors": ids,
                        "review_scope": "all_entries",
                        "source_artifacts": [source.name],
                        "artifacts": {
                            key: value.as_posix()
                            for key, value in relpaths.items()
                        },
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / relpaths["prompt"]).write_text(
                "# private semantic prompt\n",
                encoding="utf-8",
            )
            (run_dir / relpaths["report"]).write_text(
                "status: pending\nreviewed_entries: []\n"
                "blocked_entries: []\nfailed_selectors: []\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "", "")

        return build

    def test_semantic_repair_target_selectors_normalize_scene_aliases_without_merging_kinds(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            stage = "scene_set"
            report_path = (
                run_dir
                / image_gen_app.semantic_review_relpaths(stage)["report"]
            )
            report_path.parent.mkdir(parents=True)
            compact_scene_aliases = [
                f"scene{index * 10}" for index in range(1, 16)
            ]
            colon_scene_aliases = [
                f"scene:{index * 10}" for index in range(1, 16)
            ]
            report_path.write_text(
                "status: failed\n"
                "failed_selectors: ["
                + ", ".join(
                    [
                        *compact_scene_aliases,
                        "scene30.participants",
                        "scene3.1.participants",
                        "scene20_cut1",
                        "asset20",
                        "entry20",
                    ]
                )
                + "]\n"
                "blocked_entries: ["
                + ", ".join(colon_scene_aliases)
                + "]\n",
                encoding="utf-8",
            )

            selectors = image_gen_app._semantic_repair_target_selectors(
                run_dir,
                stage,
            )

        self.assertEqual(
            selectors,
            [
                *colon_scene_aliases,
                "scene:3.1",
                "scene20_cut1",
                "asset20",
                "entry20",
            ],
        )

    def test_bound_ordinary_review_uses_private_cwd_and_imports_valid_report(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "run"
            run_dir.mkdir(parents=True)
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)
            stage = "asset_plan"
            provider_cwds: list[Path] = []

            class FakeClient:
                def __init__(self, *, cwd: Path, **_kwargs):
                    provider_cwds.append(Path(cwd))

                async def start_thread(self, *, cwd: Path, **_kwargs):
                    provider_cwds.append(Path(cwd))
                    return "thread-1"

                async def run_turn(self, *, cwd: Path, **_kwargs):
                    provider_cwds.append(Path(cwd))
                    progress_callback = _kwargs.get("progress_callback")
                    if not callable(progress_callback):
                        raise AssertionError("semantic review progress callback is missing")
                    progress_callback(
                        {
                            "method": "turn/started",
                            "params": {"turnId": "turn-1"},
                        }
                    )
                    _scope_path, scope = _workspace_scope(Path(cwd))
                    return _agent_transcript(
                        digest=str(scope["semantic_review_input_digest"]),
                        reviewed_entries=["asset_plan_entry_1"],
                    )

                async def stop(self):
                    return None

            with bind_run_root(run_dir, expected_identity=identity):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch(
                        "server.image_gen_app.subprocess.run",
                        self._fake_pack_builder(run_dir, stage),
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
                            stage=stage,
                            attempt=1,
                            max_attempts=1,
                            final_attempt=True,
                        )
                    )

            self.assertTrue(result.passed, result.errors)
            activity_path = run_dir / image_gen_app._semantic_turn_activity_relpath(
                image_gen_app.semantic_review_relpaths(stage)["report"]
            )
            self.assertTrue(activity_path.is_file())
            self.assertTrue(provider_cwds)
            self.assertTrue(
                all(
                    os.path.commonpath((str(run_dir), str(cwd)))
                    != str(run_dir)
                    for cwd in provider_cwds
                )
            )
            self.assertTrue(all(not cwd.exists() for cwd in provider_cwds))

    def test_bound_image_prompt_shard_reviewer_uses_private_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)
            canonical_scope, canonical_report = self._write_canonical_scope(
                run_dir,
                stage="image_prompt",
            )
            artifacts = {
                "collection": "logs/review/semantic/image_prompt_shards/scene_10.collection.md",
                "scope": "logs/review/semantic/image_prompt_shards/scene_10.scope.json",
                "prompt": "logs/review/semantic/image_prompt_shards/scene_10.prompt.md",
                "report": "logs/review/semantic/image_prompt_shards/scene_10.report.md",
            }
            for relative in artifacts.values():
                path = run_dir / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            provider_cwds: list[Path] = []

            class FakeClient:
                def __init__(self, *, cwd: Path, **_kwargs):
                    provider_cwds.append(Path(cwd))

                async def start_thread(self, *, cwd: Path, **_kwargs):
                    provider_cwds.append(Path(cwd))
                    return "thread-1"

                async def run_turn(self, *, cwd: Path, **_kwargs):
                    provider_cwds.append(Path(cwd))
                    _scope_path, scope = _workspace_scope(Path(cwd))
                    return _agent_transcript(
                        digest=str(scope["semantic_review_input_digest"]),
                        reviewed_entries=["scene10_cut01"],
                    )

                async def stop(self):
                    return None

            with bind_run_root(run_dir, expected_identity=identity):
                with patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ):
                    result = asyncio.run(
                        image_gen_app._run_image_prompt_scene_shard_review(
                            "job-1",
                            run_dir=run_dir,
                            shard_dir=run_dir / "logs/review/semantic/image_prompt_shards",
                            shard={
                                "shard_id": "scene_10",
                                "scene_id": "10",
                                "entry_ids": ["scene10_cut01"],
                                "artifacts": artifacts,
                            },
                            shard_index=1,
                            total_shards=1,
                            collection_sections={
                                "scene10_cut01": "## scene10_cut01\ntrusted entry\n"
                            },
                            canonical_scope_path=canonical_scope,
                            canonical_report_path=canonical_report,
                            attempt=1,
                            max_attempts=1,
                            final_attempt=True,
                            semaphore=asyncio.Semaphore(1),
                            transport_attempt=1,
                            transport_max_attempts=1,
                        )
                    )

            self.assertEqual(result["status"], "passed", result)
            self.assertTrue(provider_cwds)
            self.assertTrue(
                all(
                    os.path.commonpath((str(run_dir), str(cwd)))
                    != str(run_dir)
                    for cwd in provider_cwds
                )
            )
            self.assertTrue(all(not cwd.exists() for cwd in provider_cwds))

    def test_bound_scene_detail_shard_reviewer_uses_private_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)
            canonical_scope, canonical_report = self._write_canonical_scope(
                run_dir,
                stage="scene_detail",
            )
            canonical_paths = image_gen_app.semantic_review_relpaths(
                "scene_detail"
            )
            canonical_collection = run_dir / canonical_paths["collection"]
            canonical_prompt = run_dir / canonical_paths["prompt"]
            collection_section = "## scene:10\ntrusted entry\n"
            canonical_collection.write_text(
                "# collection\n\n" + collection_section,
                encoding="utf-8",
            )
            canonical_prompt.write_text(
                "# canonical review prompt\n",
                encoding="utf-8",
            )
            scope_payload = json.loads(
                canonical_scope.read_text(encoding="utf-8")
            )
            collection_sha256 = hashlib.sha256(
                canonical_collection.read_bytes()
            ).hexdigest()
            projection_sha256 = hashlib.sha256(
                collection_section.encode("utf-8")
            ).hexdigest()
            scope_payload.update(
                {
                    "entry_count": 1,
                    "entry_ids": ["scene:10"],
                    "review_generation_id": "a" * 32,
                    "review_generation_collection_sha256": collection_sha256,
                    "entry_projection_sha256s": {
                        "scene:10": projection_sha256
                    },
                }
            )
            canonical_scope.write_text(
                json.dumps(scope_payload, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            provider_cwds: list[Path] = []

            class FakeClient:
                def __init__(self, *, cwd: Path, **_kwargs):
                    provider_cwds.append(Path(cwd))

                async def start_thread(self, *, cwd: Path, **_kwargs):
                    provider_cwds.append(Path(cwd))
                    return "thread-1"

                async def run_turn(self, *, cwd: Path, **_kwargs):
                    provider_cwds.append(Path(cwd))
                    _scope_path, scope = _workspace_scope(Path(cwd))
                    return _agent_transcript(
                        digest=str(scope["semantic_review_input_digest"]),
                        reviewed_entries=["scene:10"],
                    )

                async def stop(self):
                    return None

            with bind_run_root(run_dir, expected_identity=identity):
                image_gen_app._refresh_semantic_review_input_digest(
                    run_dir=run_dir,
                    scope_path=canonical_scope,
                    collection_path=canonical_collection,
                    prompt_path=canonical_prompt,
                    report_path=canonical_report,
                )
                canonical_generation = (
                    image_gen_app._capture_scene_semantic_review_generation(
                        run_dir=run_dir,
                        stage="scene_detail",
                        collection_path=canonical_collection,
                        scope_path=canonical_scope,
                    )
                )
                with patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ):
                    result = asyncio.run(
                        image_gen_app._run_scene_detail_shard_review(
                            "job-1",
                            run_dir=run_dir,
                            shard_dir=run_dir
                            / "logs/review/semantic/scene_detail_shards",
                            entry_id="scene:10",
                            entry_index=1,
                            total_entries=1,
                            collection_section=collection_section,
                            canonical_collection_path=canonical_collection,
                            canonical_scope_path=canonical_scope,
                            canonical_report_path=canonical_report,
                            canonical_generation=canonical_generation,
                            canonical_entry_projection_sha256=(
                                projection_sha256
                            ),
                            attempt=1,
                            max_attempts=1,
                            final_attempt=True,
                            semaphore=asyncio.Semaphore(1),
                        )
                    )

            self.assertEqual(result["status"], "passed", result)
            self.assertTrue(provider_cwds)
            self.assertTrue(
                all(
                    os.path.commonpath((str(run_dir), str(cwd)))
                    != str(run_dir)
                    for cwd in provider_cwds
                )
            )
            self.assertTrue(all(not cwd.exists() for cwd in provider_cwds))

    def test_bound_producer_repair_imports_only_validated_private_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            self._write_failed_repair_pack(run_dir)
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)
            provider_cwds: list[Path] = []

            class FakeClient:
                def __init__(self, *, cwd: Path, **_kwargs):
                    provider_cwds.append(Path(cwd))

                async def start_thread(self, *, cwd: Path, **_kwargs):
                    provider_cwds.append(Path(cwd))
                    return "thread-1"

                async def run_turn(self, *, cwd: Path, text: str, **_kwargs):
                    provider_cwds.append(Path(cwd))
                    digest_line = next(
                        line
                        for line in text.splitlines()
                        if line.startswith("- repair_input_digest:")
                    )
                    digest = digest_line.split(":", 1)[1].strip().strip("`")
                    (Path(cwd) / "script.md").write_text(
                        "# Script\n\nrepaired scene meaning\n",
                        encoding="utf-8",
                    )
                    report = Path(cwd) / image_gen_app.semantic_repair_relpaths(
                        "scene_set", 1
                    )["report"]
                    report.write_text(
                        "status: done\n"
                        f"repair_input_digest: {digest}\n"
                        "changed_artifacts: [script.md]\n"
                        "findings_addressed: [scene meaning]\n",
                        encoding="utf-8",
                    )
                    return []

                async def stop(self):
                    return None

            with bind_run_root(run_dir, expected_identity=identity):
                with patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ):
                    asyncio.run(
                        image_gen_app._run_semantic_review_producer_repair(
                            "job-1",
                            run_dir=run_dir,
                            stage="scene_set",
                            round_number=1,
                            max_attempts=2,
                            errors=("scene meaning is wrong",),
                        )
                    )

            self.assertIn(
                "repaired scene meaning",
                (run_dir / "script.md").read_text(encoding="utf-8"),
            )
            report = run_dir / image_gen_app.semantic_repair_relpaths(
                "scene_set", 1
            )["report"]
            self.assertIn("status: done", report.read_text(encoding="utf-8"))
            self.assertTrue(provider_cwds)
            self.assertTrue(
                all(
                    os.path.commonpath((str(run_dir), str(cwd)))
                    != str(run_dir)
                    for cwd in provider_cwds
                )
            )
            self.assertTrue(all(not cwd.exists() for cwd in provider_cwds))

    def test_bound_producer_repair_distinguishes_canonical_and_staged_review_hashes(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            stage = "scene_set"
            self._write_failed_repair_pack(run_dir, stage=stage)
            review_relpaths = image_gen_app.semantic_review_relpaths(stage)
            review_prompt_path = run_dir / review_relpaths["prompt"]
            review_prompt_path.write_text(
                f"# review prompt\n\nCanonical run: {run_dir}\n",
                encoding="utf-8",
            )
            scope_path = run_dir / review_relpaths["scope"]
            scope = json.loads(scope_path.read_text(encoding="utf-8"))
            scope["canonical_workspace_path"] = str(run_dir)
            scope["prompt_sha256"] = hashlib.sha256(
                review_prompt_path.read_bytes()
            ).hexdigest()
            scope["scope_binding_sha256"] = semantic_review_scope_binding_sha256(
                scope
            )
            scope["semantic_review_input_digest"] = semantic_review_input_digest(
                stage=stage,
                entry_ids=scope["entry_ids"],
                collection_sha256=scope["collection_sha256"],
                prompt_sha256=scope["prompt_sha256"],
                source_artifact_digests=scope["source_artifact_digests"],
                scope_binding_sha256=scope["scope_binding_sha256"],
            )
            scope_path.write_text(
                json.dumps(scope, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (run_dir / review_relpaths["report"]).write_text(
                "status: failed\n"
                f"semantic_review_input_digest: {scope['semantic_review_input_digest']}\n"
                "reviewed_entries: [scene_1]\n"
                "blocked_entries: [scene_1]\n"
                "findings: [scene meaning is wrong]\n"
                "failed_selectors: [scene_1]\n"
                "reason_keys: [semantic_timeline_mismatch]\n"
                "notes: []\n",
                encoding="utf-8",
            )
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)

            with bind_run_root(run_dir, expected_identity=identity) as binding:
                repair_paths = image_gen_app.write_semantic_repair_prompt(
                    run_dir,
                    stage,
                    round_number=1,
                    max_attempts=2,
                    errors=["scene meaning is wrong"],
                    expected_root_identity=identity,
                )
                committed_prompt = image_gen_app.read_committed_semantic_repair_prompt(
                    run_dir,
                    stage,
                    round_number=1,
                    expected_root_identity=identity,
                )
                workspace = image_gen_app._prepare_bound_semantic_repair_workspace(
                    run_dir=run_dir,
                    binding=binding,
                    stage=stage,
                    round_number=1,
                    committed_prompt=committed_prompt,
                )
                try:
                    staged_contract_text = workspace.submission_prompt.split(
                        "## Trusted Staged Immutable Review Artifacts",
                        1,
                    )[1]
                    staged_contract = json.loads(
                        staged_contract_text.split("```json", 1)[1].split(
                            "```",
                            1,
                        )[0]
                    )
                    staged_hashes = {
                        record["path"]: record["sha256"]
                        for record in staged_contract["artifacts"]
                    }
                    for relative in review_relpaths.values():
                        staged_sha256 = hashlib.sha256(
                            (workspace.root / relative).read_bytes()
                        ).hexdigest()
                        self.assertEqual(
                            staged_hashes[relative.as_posix()],
                            staged_sha256,
                        )
                    for key in ("scope", "prompt"):
                        relative = review_relpaths[key]
                        canonical_sha256 = hashlib.sha256(
                            (run_dir / relative).read_bytes()
                        ).hexdigest()
                        staged_sha256 = hashlib.sha256(
                            (workspace.root / relative).read_bytes()
                        ).hexdigest()
                        self.assertNotEqual(canonical_sha256, staged_sha256)

                    self.assertIn(
                        "canonical orchestrator binding",
                        workspace.submission_prompt,
                    )
                    self.assertIn(
                        "must not be compared to path-rebased staged-copy bytes",
                        workspace.submission_prompt,
                    )
                    self.assertIn(
                        "Trusted Staged Immutable Review Artifacts",
                        workspace.submission_prompt,
                    )
                    self.assertEqual(
                        set(staged_hashes),
                        {
                            relative.as_posix()
                            for relative in review_relpaths.values()
                        },
                    )
                    self.assertNotIn(
                        repair_paths["prompt"].relative_to(run_dir).as_posix(),
                        staged_hashes,
                    )
                    self.assertNotIn(
                        repair_paths["report"].relative_to(run_dir).as_posix(),
                        staged_hashes,
                    )
                    self.assertNotIn("script.md", staged_hashes)
                finally:
                    workspace.cleanup()

    def test_bound_producer_repair_rejects_mutated_staged_review_artifact(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            self._write_failed_repair_pack(run_dir)
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, cwd: Path, text: str, **_kwargs):
                    digest_line = next(
                        line
                        for line in text.splitlines()
                        if line.startswith("- repair_input_digest:")
                    )
                    digest = digest_line.split(":", 1)[1].strip().strip("`")
                    scope = Path(cwd) / image_gen_app.semantic_review_relpaths(
                        "scene_set"
                    )["scope"]
                    scope.chmod(0o600)
                    scope.write_text("provider mutation\n", encoding="utf-8")
                    (Path(cwd) / "script.md").write_text(
                        "# Script\n\nuntrusted repaired meaning\n",
                        encoding="utf-8",
                    )
                    report = Path(cwd) / image_gen_app.semantic_repair_relpaths(
                        "scene_set", 1
                    )["report"]
                    report.write_text(
                        "status: done\n"
                        f"repair_input_digest: {digest}\n"
                        "changed_artifacts: [script.md]\n",
                        encoding="utf-8",
                    )
                    return []

                async def stop(self):
                    return None

            with bind_run_root(run_dir, expected_identity=identity):
                with patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "immutable workspace input changed",
                    ):
                        asyncio.run(
                            image_gen_app._run_semantic_review_producer_repair(
                                "job-1",
                                run_dir=run_dir,
                                stage="scene_set",
                                round_number=1,
                                max_attempts=2,
                                errors=("scene meaning is wrong",),
                            )
                        )

            self.assertIn(
                "old scene meaning",
                (run_dir / "script.md").read_text(encoding="utf-8"),
            )

    def test_bound_producer_repair_uses_validated_diff_when_report_overstates_changes_or_lists_itself(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            self._write_failed_repair_pack(run_dir)
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, cwd: Path, text: str, **_kwargs):
                    digest_line = next(
                        line
                        for line in text.splitlines()
                        if line.startswith("- repair_input_digest:")
                    )
                    digest = digest_line.split(":", 1)[1].strip().strip("`")
                    (Path(cwd) / "script.md").write_text(
                        "# Script\n\nrepaired scene meaning\n",
                        encoding="utf-8",
                    )
                    report = Path(cwd) / image_gen_app.semantic_repair_relpaths(
                        "scene_set", 1
                    )["report"]
                    report_relative = report.relative_to(Path(cwd)).as_posix()
                    report.write_text(
                        "status: done\n"
                        f"repair_input_digest: {digest}\n"
                        "changed_artifacts: "
                        f"[script.md, video_manifest.md, {report_relative}]\n"
                        "findings_addressed: [scene meaning]\n",
                        encoding="utf-8",
                    )
                    return []

                async def stop(self):
                    return None

            with bind_run_root(run_dir, expected_identity=identity):
                with patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ):
                    asyncio.run(
                        image_gen_app._run_semantic_review_producer_repair(
                            "job-1",
                            run_dir=run_dir,
                            stage="scene_set",
                            round_number=1,
                            max_attempts=2,
                            errors=("scene meaning is wrong",),
                        )
                    )

            self.assertIn(
                "repaired scene meaning",
                (run_dir / "script.md").read_text(encoding="utf-8"),
            )
            self.assertFalse((run_dir / "video_manifest.md").exists())

    def test_bound_producer_repair_rejects_unreported_validated_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            self._write_failed_repair_pack(run_dir)
            (run_dir / "video_manifest.md").write_text(
                "# Manifest\n\nold scene meaning\n",
                encoding="utf-8",
            )
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, cwd: Path, text: str, **_kwargs):
                    digest_line = next(
                        line
                        for line in text.splitlines()
                        if line.startswith("- repair_input_digest:")
                    )
                    digest = digest_line.split(":", 1)[1].strip().strip("`")
                    (Path(cwd) / "script.md").write_text(
                        "# Script\n\nrepaired scene meaning\n",
                        encoding="utf-8",
                    )
                    (Path(cwd) / "video_manifest.md").write_text(
                        "# Manifest\n\nrepaired scene meaning\n",
                        encoding="utf-8",
                    )
                    report = Path(cwd) / image_gen_app.semantic_repair_relpaths(
                        "scene_set", 1
                    )["report"]
                    report.write_text(
                        "status: done\n"
                        f"repair_input_digest: {digest}\n"
                        "changed_artifacts: [script.md]\n"
                        "findings_addressed: [scene meaning]\n",
                        encoding="utf-8",
                    )
                    return []

                async def stop(self):
                    return None

            with bind_run_root(run_dir, expected_identity=identity):
                with patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ):
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "does not include every validated diff",
                    ):
                        asyncio.run(
                            image_gen_app._run_semantic_review_producer_repair(
                                "job-1",
                                run_dir=run_dir,
                                stage="scene_set",
                                round_number=1,
                                max_attempts=2,
                                errors=("scene meaning is wrong",),
                            )
                        )

            self.assertIn(
                "old scene meaning",
                (run_dir / "script.md").read_text(encoding="utf-8"),
            )
            self.assertIn(
                "old scene meaning",
                (run_dir / "video_manifest.md").read_text(encoding="utf-8"),
            )

    def test_bound_producer_repair_rejects_stale_private_report_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            self._write_failed_repair_pack(run_dir)
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, cwd: Path, **_kwargs):
                    (Path(cwd) / "script.md").write_text(
                        "# Script\n\nuntrusted stale repair\n",
                        encoding="utf-8",
                    )
                    report = Path(cwd) / image_gen_app.semantic_repair_relpaths(
                        "scene_set", 1
                    )["report"]
                    report.write_text(
                        "status: done\n"
                        f"repair_input_digest: sha256:{'0' * 64}\n"
                        "changed_artifacts: [script.md]\n",
                        encoding="utf-8",
                    )
                    return []

                async def stop(self):
                    return None

            with bind_run_root(run_dir, expected_identity=identity):
                with patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ):
                    with self.assertRaisesRegex(RuntimeError, "digest"):
                        asyncio.run(
                            image_gen_app._run_semantic_review_producer_repair(
                                "job-1",
                                run_dir=run_dir,
                                stage="scene_set",
                                round_number=1,
                                max_attempts=2,
                                errors=("scene meaning is wrong",),
                            )
                        )

            self.assertIn(
                "old scene meaning",
                (run_dir / "script.md").read_text(encoding="utf-8"),
            )
            report = run_dir / image_gen_app.semantic_repair_relpaths(
                "scene_set", 1
            )["report"]
            self.assertIn("status: pending", report.read_text(encoding="utf-8"))

    def test_bound_producer_repair_rejects_unapproved_private_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            self._write_failed_repair_pack(run_dir)
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, cwd: Path, text: str, **_kwargs):
                    digest_line = next(
                        line
                        for line in text.splitlines()
                        if line.startswith("- repair_input_digest:")
                    )
                    digest = digest_line.split(":", 1)[1].strip().strip("`")
                    (Path(cwd) / "script.md").write_text(
                        "# Script\n\nuntrusted repair\n",
                        encoding="utf-8",
                    )
                    (Path(cwd) / "state.txt").write_text(
                        "provider controlled\n",
                        encoding="utf-8",
                    )
                    report = Path(cwd) / image_gen_app.semantic_repair_relpaths(
                        "scene_set", 1
                    )["report"]
                    report.write_text(
                        "status: done\n"
                        f"repair_input_digest: {digest}\n"
                        "changed_artifacts: [script.md]\n",
                        encoding="utf-8",
                    )
                    return []

                async def stop(self):
                    return None

            with bind_run_root(run_dir, expected_identity=identity):
                with patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    FakeClient,
                ):
                    with self.assertRaisesRegex(RuntimeError, "unapproved"):
                        asyncio.run(
                            image_gen_app._run_semantic_review_producer_repair(
                                "job-1",
                                run_dir=run_dir,
                                stage="scene_set",
                                round_number=1,
                                max_attempts=2,
                                errors=("scene meaning is wrong",),
                            )
                        )

            self.assertIn(
                "old scene meaning",
                (run_dir / "script.md").read_text(encoding="utf-8"),
            )
            self.assertNotIn(
                "provider controlled",
                (run_dir / "state.txt").read_text(encoding="utf-8"),
            )

    def test_bound_producer_repair_replacement_during_await_is_untouched(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            original = root / "original"
            replacement_saved = root / "replacement"
            run_dir.mkdir()
            self._write_failed_repair_pack(run_dir)
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, cwd: Path, text: str, **_kwargs):
                    digest_line = next(
                        line
                        for line in text.splitlines()
                        if line.startswith("- repair_input_digest:")
                    )
                    digest = digest_line.split(":", 1)[1].strip().strip("`")
                    (Path(cwd) / "script.md").write_text(
                        "# Script\n\nprivate repaired meaning\n",
                        encoding="utf-8",
                    )
                    report = Path(cwd) / image_gen_app.semantic_repair_relpaths(
                        "scene_set", 1
                    )["report"]
                    report.write_text(
                        "status: done\n"
                        f"repair_input_digest: {digest}\n"
                        "changed_artifacts: [script.md]\n",
                        encoding="utf-8",
                    )
                    run_dir.rename(original)
                    run_dir.mkdir()
                    (run_dir / "sentinel.txt").write_text(
                        "replacement untouched",
                        encoding="utf-8",
                    )
                    return []

                async def stop(self):
                    return None

            with bind_run_root(run_dir, expected_identity=identity):
                try:
                    with patch(
                        "server.image_gen_app.create_codex_app_server_client",
                        FakeClient,
                    ):
                        with self.assertRaises(RunRootBindingError):
                            asyncio.run(
                                image_gen_app._run_semantic_review_producer_repair(
                                    "job-1",
                                    run_dir=run_dir,
                                    stage="scene_set",
                                    round_number=1,
                                    max_attempts=2,
                                    errors=("scene meaning is wrong",),
                                )
                            )
                finally:
                    if run_dir.exists() and original.exists():
                        run_dir.rename(replacement_saved)
                        original.rename(run_dir)

            self.assertEqual(
                (replacement_saved / "sentinel.txt").read_text(
                    encoding="utf-8"
                ),
                "replacement untouched",
            )
            self.assertFalse((replacement_saved / "script.md").exists())
            self.assertIn(
                "old scene meaning",
                (run_dir / "script.md").read_text(encoding="utf-8"),
            )

    def test_bound_review_replacement_during_turn_never_imports_to_replacement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "run"
            original = root / "original"
            replacement_saved = root / "replacement"
            run_dir.mkdir(parents=True)
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)
            stage = "asset_plan"
            turn_cwd: Path | None = None

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, cwd: Path, **_kwargs):
                    nonlocal turn_cwd
                    turn_cwd = Path(cwd)
                    _scope_path, scope = _workspace_scope(turn_cwd)
                    run_dir.rename(original)
                    run_dir.mkdir()
                    (run_dir / "sentinel.txt").write_text(
                        "replacement untouched",
                        encoding="utf-8",
                    )
                    return _agent_transcript(
                        digest=str(scope["semantic_review_input_digest"]),
                        reviewed_entries=["asset_plan_entry_1"],
                    )

                async def stop(self):
                    return None

            with bind_run_root(run_dir, expected_identity=identity):
                try:
                    with (
                        patch("server.image_gen_app.ROOT", root),
                        patch(
                            "server.image_gen_app.subprocess.run",
                            self._fake_pack_builder(run_dir, stage),
                        ),
                        patch(
                            "server.image_gen_app.create_codex_app_server_client",
                            FakeClient,
                        ),
                    ):
                        with self.assertRaises(RunRootBindingError):
                            asyncio.run(
                                image_gen_app._run_semantic_review_once(
                                    "job-1",
                                    run_dir=run_dir,
                                    stage=stage,
                                    attempt=1,
                                    max_attempts=1,
                                    final_attempt=True,
                                )
                            )
                finally:
                    if run_dir.exists() and original.exists():
                        run_dir.rename(replacement_saved)
                        original.rename(run_dir)

            self.assertIsNotNone(turn_cwd)
            self.assertNotEqual(turn_cwd, run_dir)
            self.assertEqual(
                (replacement_saved / "sentinel.txt").read_text(
                    encoding="utf-8"
                ),
                "replacement untouched",
            )
            self.assertFalse(
                (replacement_saved / "logs" / "review" / "semantic").exists()
            )

    def test_bound_review_replacement_before_submission_never_starts_turn(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "run"
            original = root / "original"
            replacement_saved = root / "replacement"
            run_dir.mkdir(parents=True)
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)
            stage = "asset_plan"
            start_called = False

            class FakeClient:
                def __init__(self, **_kwargs):
                    run_dir.rename(original)
                    run_dir.mkdir()
                    (run_dir / "sentinel.txt").write_text(
                        "replacement untouched",
                        encoding="utf-8",
                    )

                async def start_thread(self, **_kwargs):
                    nonlocal start_called
                    start_called = True
                    return "thread-1"

                async def stop(self):
                    return None

            with bind_run_root(run_dir, expected_identity=identity):
                try:
                    with (
                        patch("server.image_gen_app.ROOT", root),
                        patch(
                            "server.image_gen_app.subprocess.run",
                            self._fake_pack_builder(run_dir, stage),
                        ),
                        patch(
                            "server.image_gen_app.create_codex_app_server_client",
                            FakeClient,
                        ),
                    ):
                        with self.assertRaises(RunRootBindingError):
                            asyncio.run(
                                image_gen_app._run_semantic_review_once(
                                    "job-1",
                                    run_dir=run_dir,
                                    stage=stage,
                                    attempt=1,
                                    max_attempts=1,
                                    final_attempt=True,
                                )
                            )
                finally:
                    if run_dir.exists() and original.exists():
                        run_dir.rename(replacement_saved)
                        original.rename(run_dir)

            self.assertFalse(start_called)
            self.assertEqual(
                (replacement_saved / "sentinel.txt").read_text(
                    encoding="utf-8"
                ),
                "replacement untouched",
            )

    def test_bound_review_replacement_during_import_never_publishes_to_replacement(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "run"
            original = root / "original"
            replacement_saved = root / "replacement"
            run_dir.mkdir(parents=True)
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)
            stage = "asset_plan"
            real_import = image_gen_app._import_bound_semantic_review_report
            import_started = False

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, cwd: Path, **_kwargs):
                    _scope_path, scope = _workspace_scope(Path(cwd))
                    return _agent_transcript(
                        digest=str(scope["semantic_review_input_digest"]),
                        reviewed_entries=["asset_plan_entry_1"],
                    )

                async def stop(self):
                    return None

            def swap_during_import(workspace, **kwargs):
                nonlocal import_started
                import_started = True
                run_dir.rename(original)
                run_dir.mkdir()
                (run_dir / "sentinel.txt").write_text(
                    "replacement untouched",
                    encoding="utf-8",
                )
                return real_import(workspace, **kwargs)

            with bind_run_root(run_dir, expected_identity=identity):
                try:
                    with (
                        patch("server.image_gen_app.ROOT", root),
                        patch(
                            "server.image_gen_app.subprocess.run",
                            self._fake_pack_builder(run_dir, stage),
                        ),
                        patch(
                            "server.image_gen_app.create_codex_app_server_client",
                            FakeClient,
                        ),
                        patch(
                            "server.image_gen_app._import_bound_semantic_review_report",
                            side_effect=swap_during_import,
                        ),
                    ):
                        with self.assertRaises(RunRootBindingError):
                            asyncio.run(
                                image_gen_app._run_semantic_review_once(
                                    "job-1",
                                    run_dir=run_dir,
                                    stage=stage,
                                    attempt=1,
                                    max_attempts=1,
                                    final_attempt=True,
                                )
                            )
                finally:
                    if run_dir.exists() and original.exists():
                        run_dir.rename(replacement_saved)
                        original.rename(run_dir)

            self.assertTrue(import_started)
            self.assertEqual(
                (replacement_saved / "sentinel.txt").read_text(
                    encoding="utf-8"
                ),
                "replacement untouched",
            )
            self.assertFalse(
                (replacement_saved / "logs" / "review" / "semantic").exists()
            )

    def test_bound_review_rejects_stale_digest_before_canonical_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "output" / "run"
            run_dir.mkdir(parents=True)
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)
            stage = "asset_plan"

            class FakeClient:
                def __init__(self, **_kwargs):
                    pass

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, **_kwargs):
                    return _agent_transcript(
                        digest="sha256:" + ("0" * 64),
                        reviewed_entries=["asset_plan_entry_1"],
                    )

                async def stop(self):
                    return None

            with bind_run_root(run_dir, expected_identity=identity):
                with (
                    patch("server.image_gen_app.ROOT", root),
                    patch(
                        "server.image_gen_app.subprocess.run",
                        self._fake_pack_builder(run_dir, stage),
                    ),
                    patch(
                        "server.image_gen_app.create_codex_app_server_client",
                        FakeClient,
                    ),
                ):
                    with self.assertRaises(CodexAppServerTransportError):
                        asyncio.run(
                            image_gen_app._run_semantic_review_once(
                                "job-1",
                                run_dir=run_dir,
                                stage=stage,
                                attempt=1,
                                max_attempts=1,
                                final_attempt=True,
                            )
                        )

            report_path = run_dir / image_gen_app.semantic_review_relpaths(stage)[
                "report"
            ]
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("status: pending", report)
            self.assertNotIn("sha256:" + ("0" * 64), report)


if __name__ == "__main__":
    unittest.main()
